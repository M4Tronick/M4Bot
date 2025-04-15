#!/usr/bin/env python3
"""
Applicazione web per la gestione di M4Bot
Fornisce un'interfaccia per la configurazione e il monitoraggio del bot.
"""

import os
import sys
import json
import logging
import secrets
import hashlib
import base64
from functools import wraps
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
import time
import asyncio
import re
import random
import functools
import uuid

import aiohttp
from quart import Quart, render_template, request, redirect, url_for, session, jsonify, flash, websocket
from quart_cors import cors
import asyncpg
import bcrypt
from dotenv import load_dotenv
from flask_babel import Babel, gettext as _
from babel_compat import *
import redis.asyncio as redis

# Aggiungi la directory principale al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carica le variabili d'ambiente dal file .env
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(env_path)

# Configurazione
CLIENT_ID = "your_kick_client_id"
CLIENT_SECRET = "your_kick_client_secret"
REDIRECT_URI = "https://your-domain.com/auth/callback"
SCOPE = "public"
ENCRYPTION_KEY = "your_secret_key"
LOG_LEVEL = "INFO"
LOG_FILE = "m4bot.log"
DB_USER = os.getenv('DB_USER', 'm4bot_user')
DB_PASS = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'm4bot_db')
DB_HOST = os.getenv('DB_HOST', 'localhost')

# Configurazione Redis per caching avanzato e WebSocket
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_DB = int(os.getenv('REDIS_DB', '0'))
REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', '')
REDIS_URL = f"redis://{':' + REDIS_PASSWORD + '@' if REDIS_PASSWORD else ''}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Assicurati che le directory necessarie esistano
log_dir = os.path.dirname(LOG_FILE)
if log_dir and not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)
    print(f"Directory di log creata: {log_dir}")

# Assicurati che la directory delle traduzioni esista
translations_dir = 'translations'
if not os.path.exists(translations_dir):
    os.makedirs(translations_dir, exist_ok=True)
    print(f"Directory delle traduzioni creata: {translations_dir}")

# Configura il logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('M4Bot-Web')

# Crea l'applicazione Quart (Flask asincrono)
app = Quart(__name__)
app = cors(app)
app.secret_key = ENCRYPTION_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', secrets.token_hex(16))
app.config['BABEL_DEFAULT_LOCALE'] = 'it'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'
babel = Babel(app)

# Pool di connessioni al database
db_pool = None

# Connessioni con il bot
bot_client = None

# Redis client per caching avanzato e pubsub
redis_client = None
redis_pubsub = None

# Connessioni WebSocket attive
websocket_clients = {}

# Cache in-memory per migliorare le prestazioni
cache_store = {}
cache_stats = {'hits': 0, 'misses': 0, 'size': 0}

def cached_response(timeout=300):
    """Decorator che aggiunge caching per le route Flask.
    
    Args:
        timeout: Tempo di validità della cache in secondi
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Estrai l'utente dalla sessione se presente
            user_id = session.get('user_id', 'anonymous')
            
            # Crea una chiave unica basata sulla funzione, utente e parametri
            cache_key = f"{func.__name__}:{user_id}:{str(args)}:{str(sorted(kwargs.items()))}"
            cache_key_hash = hashlib.md5(cache_key.encode()).hexdigest()
            
            # Verifica se è nella cache e non scaduta
            current_time = time.time()
            if cache_key_hash in cache_store:
                result, timestamp = cache_store[cache_key_hash]
                if current_time - timestamp < timeout:
                    # Cache hit
                    cache_stats['hits'] += 1
                    logger.debug(f"Cache hit per {func.__name__}")
                    return result
            
            # Cache miss
            cache_stats['misses'] += 1
            
            # Esegui la funzione e salva il risultato
            result = await func(*args, **kwargs)
            cache_store[cache_key_hash] = (result, current_time)
            cache_stats['size'] = len(cache_store)
            
            # Pulizia periodica della cache (1% delle volte)
            if random.random() < 0.01:
                cleanup_cache()
                
            return result
        return wrapper
    return decorator

def cleanup_cache():
    """Rimuove le voci di cache scadute"""
    current_time = time.time()
    keys_to_delete = []
    
    for key, (_, timestamp) in cache_store.items():
        # Rimuovi entries più vecchie di un'ora
        if current_time - timestamp > 3600:
            keys_to_delete.append(key)
    
    for key in keys_to_delete:
        del cache_store[key]
    
    cache_stats['size'] = len(cache_store)
    logger.debug(f"Cache pulita: rimosse {len(keys_to_delete)} voci. Dimensione: {cache_stats['size']}")

def clear_cache(pattern=None):
    """Cancella l'intera cache o le voci che corrispondono a un pattern"""
    if pattern:
        keys_to_delete = [k for k in cache_store.keys() if pattern in k]
        for key in keys_to_delete:
            del cache_store[key]
        cache_stats['size'] = len(cache_store)
        logger.debug(f"Cache parziale pulita: rimosse {len(keys_to_delete)} voci con pattern '{pattern}'")
    else:
        cache_store.clear()
        cache_stats['size'] = 0
        logger.debug("Cache completamente pulita")

async def setup_db_pool():
    """Crea il pool di connessioni al database."""
    global db_pool
    retry_count = 0
    max_retries = 3
    retry_delay = 5  # secondi
    
    while retry_count < max_retries:
        try:
            db_pool = await asyncpg.create_pool(
                user=DB_USER,
                password=DB_PASS,
                database=DB_NAME,
                host=DB_HOST,
                command_timeout=60.0,  # Timeout più lungo per comandi
                min_size=2,            # Minimo numero di connessioni nel pool
                max_size=10            # Massimo numero di connessioni nel pool
            )
            logger.info("Connessione al database PostgreSQL stabilita")
            return
        except asyncpg.exceptions.PostgresError as e:
            retry_count += 1
            logger.error(f"Errore nella connessione al database (tentativo {retry_count}/{max_retries}): {e}")
            
            if retry_count < max_retries:
                logger.info(f"Nuovo tentativo tra {retry_delay} secondi...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Aumenta il ritardo ad ogni tentativo
            else:
                logger.critical("Impossibile connettersi al database dopo multipli tentativi")
        except Exception as e:
            logger.critical(f"Errore critico nella connessione al database: {e}")
            break
    
    # Se siamo qui, non siamo riusciti a connetterci
    logger.warning("L'applicazione continuerà senza database (solo per sviluppo)")
    # In produzione, potremmo voler terminare qui l'applicazione
    # import sys; sys.exit(1)

async def setup_bot_client():
    """Crea la connessione al bot."""
    global bot_client
    try:
        # Configura il client HTTP per comunicare con il bot
        timeout = aiohttp.ClientTimeout(total=30)  # Aumento del timeout a 30 secondi
        bot_client = aiohttp.ClientSession(timeout=timeout)
        logger.info("Client HTTP per la comunicazione con il bot inizializzato")
    except Exception as e:
        logger.error(f"Errore nell'inizializzazione del client HTTP: {e}")
        logger.warning("L'applicazione continuerà senza connessione al bot")

async def setup_redis_client():
    """Inizializza il client Redis per caching avanzato e pubsub."""
    global redis_client, redis_pubsub
    try:
        # Connessione a Redis
        redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        # Verifica la connessione
        await redis_client.ping()
        
        # Inizializza il client pubsub per WebSocket
        redis_pubsub = redis_client.pubsub()
        await redis_pubsub.subscribe("m4bot_notifications", "m4bot_metrics")
        
        logger.info("Connessione a Redis stabilita con successo")
    except Exception as e:
        logger.error(f"Errore nella connessione a Redis: {e}")
        logger.warning("L'applicazione continuerà senza caching avanzato e WebSocket")
        redis_client = None
        redis_pubsub = None

# Funzione per ottenere o impostare dati nella cache Redis
async def redis_cache(key, callback, expire=300):
    """Helper per il caching con Redis."""
    if not redis_client:
        # Se Redis non è disponibile, esegui la callback direttamente
        return await callback()
    
    # Prova a ottenere dalla cache
    cached = await redis_client.get(key)
    if cached:
        return json.loads(cached)
    
    # Se non in cache, esegui la callback
    result = await callback()
    
    # Salva in cache se il risultato non è None
    if result is not None:
        await redis_client.set(key, json.dumps(result), ex=expire)
    
    return result

async def api_request(url, method='GET', data=None, timeout=10, retries=3):
    """Helper per richieste API con retry automatico"""
    if not bot_client:
        return None
        
    for attempt in range(retries):
        try:
            if method.upper() == 'GET':
                async with bot_client.get(url, timeout=timeout) as response:
                    if response.status < 200 or response.status >= 300:
                        logger.warning(f"API request error: {response.status} on {url}, attempt {attempt+1}/{retries}")
                        if attempt < retries - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        return None
                    return await response.json()
            elif method.upper() == 'POST':
                async with bot_client.post(url, json=data, timeout=timeout) as response:
                    if response.status < 200 or response.status >= 300:
                        logger.warning(f"API request error: {response.status} on {url}, attempt {attempt+1}/{retries}")
                        if attempt < retries - 1:
                            await asyncio.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        return None
                    return await response.json()
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            logger.warning(f"API request failed: {e} on {url}, attempt {attempt+1}/{retries}")
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            return None
    return None

# Funzioni di utilità
def login_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        try:
            return await f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Errore in {f.__name__}: {e}")
            return await render_template('error.html', message=f"Errore del server: {str(e)}"), 500
    return decorated_function

def admin_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
            
        if not db_pool:
            return await render_template('error.html', message="Database non disponibile"), 500
            
        async with db_pool.acquire() as conn:
            user = await conn.fetchrow(
                'SELECT is_admin FROM users WHERE id = $1',
                session['user_id']
            )
            
            if not user or not user['is_admin']:
                return redirect(url_for('dashboard'))
                
        return await f(*args, **kwargs)
    return decorated_function

def generate_pkce_challenge():
    """Genera un challenge PKCE per l'autenticazione OAuth."""
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode().rstrip("=")
    
    return code_verifier, code_challenge

def generate_state():
    """Genera un token di stato univoco per le richieste OAuth."""
    return secrets.token_urlsafe(32)

@babel.localeselector
async def get_locale():
    # Aggiungi log per debug
    logger.info(f"Richiesta lingua: parametro URL={request.args.get('lang')}, sessione={session.get('preferred_language')}")
    
    # Priorità: 1. Parametro URL, 2. Cookie, 3. Preferenza browser, 4. Default (it)
    lang = request.args.get('lang')
    if lang and lang in ['it', 'en', 'es', 'fr', 'de']:
        # Salva la preferenza nella sessione
        session['preferred_language'] = lang
        logger.info(f"Lingua impostata da parametro URL: {lang}")
        return lang
    
    # Verifica cookie/sessione
    saved_lang = session.get('preferred_language')
    if saved_lang and saved_lang in ['it', 'en', 'es', 'fr', 'de']:
        logger.info(f"Lingua impostata da sessione: {saved_lang}")
        return saved_lang
        
    # Verifica header Accept-Language
    best_match = request.accept_languages.best_match(['it', 'en', 'es', 'fr', 'de'])
    if best_match:
        logger.info(f"Lingua impostata da header: {best_match}")
        return best_match
    
    # Default
    logger.info("Lingua impostata a default: it")
    return 'it'

@app.context_processor
async def inject_language_info():
    """Inietta informazioni sulla lingua nel contesto dei template."""
    current_lang = await get_locale()
    language_names = {
        'it': 'Italiano',
        'en': 'English',
        'es': 'Español',
        'fr': 'Français',
        'de': 'Deutsch'
    }
    
    # Aggiungi log per debug
    logger.info(f"Lingua corrente nel contesto: {current_lang}")
    
    return {
        'current_language': current_lang,
        'current_language_name': language_names.get(current_lang, 'Italiano'),
        'available_languages': language_names
    }

# Middleware per inserire il selettore lingua nella barra
@app.after_request
async def add_language_switcher(response):
    """Aggiunge il selettore di lingua a tutte le pagine HTML."""
    if response.content_type and 'text/html' in response.content_type:
        # Assicuriamoci che l'URL corrente mantenga gli altri parametri
        current_url = request.url
        base_url = request.base_url
        
        # Log di diagnostica
        logger.debug(f"URL corrente: {current_url}, base URL: {base_url}")
        
    return response

# Rotte dell'applicazione
@app.route('/')
async def index():
    """Pagina principale."""
    return await render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
async def login():
    """Pagina di login."""
    error = None
    
    if request.method == 'POST':
        form = await request.form
        email = form.get('email')
        password = form.get('password')
        
        if not email or not password:
            error = "Email e password sono richiesti"
        else:
            if not db_pool:
                return await render_template('error.html', message="Database non disponibile"), 500
                
            async with db_pool.acquire() as conn:
                user = await conn.fetchrow(
                    'SELECT id, password_hash, is_admin FROM users WHERE email = $1',
                    email
                )
                
                if user and bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
                    session['user_id'] = user['id']
                    session['is_admin'] = user['is_admin']
                    
                    # Aggiorna l'ultimo accesso
                    await conn.execute(
                        'UPDATE users SET last_login = NOW() WHERE id = $1',
                        user['id']
                    )
                    
                    next_url = request.args.get('next')
                    if next_url:
                        return redirect(next_url)
                    return redirect(url_for('dashboard'))
                else:
                    error = "Email o password non validi"
    
    return await render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
async def register():
    """Pagina di registrazione."""
    error = None
    
    if request.method == 'POST':
        form = await request.form
        username = form.get('username')
        email = form.get('email')
        password = form.get('password')
        confirm_password = form.get('confirm_password')
        
        if not username or not email or not password:
            error = "Tutti i campi sono richiesti"
        elif password != confirm_password:
            error = "Le password non corrispondono"
        else:
            try:
                if not db_pool:
                    return await render_template('error.html', message="Database non disponibile"), 500
                    
                # Hash della password
                password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                
                async with db_pool.acquire() as conn:
                    # Verifica se l'email è già registrata
                    existing_user = await conn.fetchval(
                        'SELECT id FROM users WHERE email = $1',
                        email
                    )
                    
                    if existing_user:
                        error = "Email già registrata"
                    else:
                        # Crea un nuovo utente
                        user_id = await conn.fetchval('''
                            INSERT INTO users (kick_id, username, email, password_hash, created_at)
                            VALUES ($1, $2, $3, $4, NOW())
                            RETURNING id
                        ''', '0', username, email, password_hash)
                        
                        if user_id:
                            session['user_id'] = user_id
                            session['is_admin'] = False
                            return redirect(url_for('dashboard'))
                        else:
                            error = "Errore nella registrazione dell'utente"
            except Exception as e:
                logger.error(f"Errore nella registrazione: {e}")
                error = "Si è verificato un errore durante la registrazione"
    
    return await render_template('register.html', error=error)

@app.route('/logout')
async def logout():
    """Gestisce il logout."""
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
async def dashboard():
    """Dashboard principale dell'utente."""
    user_id = session.get('user_id')
    
    # Valori predefiniti in caso di errore del database
    user = {'id': user_id, 'username': 'Utente', 'email': 'N/A', 'is_admin': False}
    channels = []
    stats = {}
    
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                # Ottieni i dati dell'utente
                db_user = await conn.fetchrow(
                    'SELECT id, username, email, is_admin FROM users WHERE id = $1',
                    user_id
                )
                
                if db_user:
                    user = dict(db_user)
                
                # Ottieni i canali configurati dall'utente
                channels = await conn.fetch('''
                    SELECT c.id, c.name, c.kick_channel_id, c.created_at
                    FROM channels c
                    WHERE c.owner_id = $1
                    ORDER BY c.name
                ''', user_id)
                
                # Ottieni statistiche di base
                for channel in channels:
                    channel_stats = await conn.fetchrow('''
                        SELECT 
                            COUNT(DISTINCT cm.user_id) AS unique_chatters,
                            COUNT(*) AS total_messages,
                            COUNT(*) FILTER (WHERE cm.is_command) AS total_commands
                        FROM chat_messages cm
                        WHERE cm.channel_id = $1
                    ''', channel['id'])
                    
                    stats[channel['id']] = channel_stats
        except Exception as e:
            logger.error(f"Errore nel caricamento della dashboard: {e}")
            # Continua con i valori predefiniti
    
    return await render_template(
        'dashboard.html', 
        user=user, 
        channels=channels,
        stats=stats
    )

@app.route('/system_health')
@login_required
@cached_response(timeout=60)  # Cache per 60 secondi
async def system_health():
    """Mostra lo stato del sistema e le metriche di salute."""
    user_id = session.get('user_id')
    
    # Valori predefiniti
    system_metrics = {
        'cpu_usage': 0,
        'memory_usage': 0,
        'disk_usage': 0
    }
    
    service_status = {
        'bot': 'offline',
        'web': 'online',
        'database': 'unknown'
    }
    
    cache_metrics = {
        'hits': cache_stats['hits'],
        'misses': cache_stats['misses'],
        'size': cache_stats['size'],
        'hit_ratio': round(cache_stats['hits'] / max(1, (cache_stats['hits'] + cache_stats['misses'])) * 100, 2)
    }
    
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                # Verifica stato database
                service_status['database'] = 'online'
                
                # Ottieni metriche di sistema se disponibili
                system_data = await conn.fetchrow('''
                    SELECT 
                        cpu_usage, memory_usage, disk_usage,
                        bot_status, updated_at
                    FROM system_metrics
                    ORDER BY updated_at DESC
                    LIMIT 1
                ''')
                
                if system_data:
                    system_metrics['cpu_usage'] = system_data['cpu_usage']
                    system_metrics['memory_usage'] = system_data['memory_usage']
                    system_metrics['disk_usage'] = system_data['disk_usage']
                    service_status['bot'] = system_data['bot_status']
                
                # Ottieni log recenti
                logs = await conn.fetch('''
                    SELECT 
                        timestamp, level, message, source
                    FROM system_logs
                    ORDER BY timestamp DESC
                    LIMIT 100
                ''')
        except Exception as e:
            logger.error(f"Errore nel caricamento dei dati di salute: {e}")
            service_status['database'] = 'error'
            logs = []
    else:
        service_status['database'] = 'offline'
        logs = []
    
    return await render_template(
        'system_health.html',
        system_metrics=system_metrics,
        service_status=service_status,
        cache_metrics=cache_metrics,
        logs=logs
    )

@app.route('/backup_management')
@admin_required
async def backup_management():
    """Gestione dei backup del sistema."""
    backups = []
    
    try:
        # Ottieni la lista dei backup dal bot
        backup_data = await api_request('http://localhost:5000/api/backups')
        if backup_data:
            backups = backup_data.get('backups', [])
    except Exception as e:
        logger.error(f"Errore nel recupero dei backup: {e}")
    
    return await render_template('backup_management.html', backups=backups)

@app.route('/create_backup', methods=['POST'])
@admin_required
async def create_backup():
    """Crea un nuovo backup del sistema."""
    try:
        # Richiedi la creazione di un nuovo backup
        result = await api_request('http://localhost:5000/api/backups/create', method='POST', timeout=120)
        if result and result.get('success'):
            flash('Backup creato con successo!', 'success')
        else:
            flash('Errore nella creazione del backup.', 'error')
    except Exception as e:
        logger.error(f"Errore nella creazione del backup: {e}")
        flash(f'Errore nella creazione del backup: {str(e)}', 'error')
    
    return redirect(url_for('backup_management'))

@app.route('/restore_backup/<backup_id>', methods=['POST'])
@admin_required
async def restore_backup(backup_id):
    """Ripristina un backup del sistema."""
    try:
        # Richiedi il ripristino del backup
        result = await api_request(f'http://localhost:5000/api/backups/restore/{backup_id}', method='POST', timeout=180)
        if result and result.get('success'):
            flash('Backup ripristinato con successo!', 'success')
        else:
            flash('Errore nel ripristino del backup.', 'error')
    except Exception as e:
        logger.error(f"Errore nel ripristino del backup: {e}")
        flash(f'Errore nel ripristino del backup: {str(e)}', 'error')
    
    return redirect(url_for('backup_management'))

@app.route('/discord_integration')
@login_required
async def discord_integration():
    """Pagina di integrazione con Discord."""
    try:
        # Ottieni lo stato dell'integrazione Discord
        discord_data = await api_request('http://localhost:5000/api/discord/status')
        if not discord_data:
            discord_data = {"connected": False, "status": "Non connesso", "username": "N/A"}
        
        # Se connesso, ottieni i canali Discord
        discord_channels = []
        if discord_data.get('connected'):
            channels_data = await api_request('http://localhost:5000/api/discord/channels')
            if channels_data:
                discord_channels = channels_data.get('channels', [])
        
        return await render_template('discord_integration.html', 
                                     discord_data=discord_data,
                                     discord_channels=discord_channels)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di integrazione Discord: {e}")
        return await render_template('discord_integration.html', 
                                     error=str(e),
                                     discord_data={"connected": False, "status": "Errore", "username": "N/A"}, 
                                     discord_channels=[])

@app.route('/obs_integration')
@login_required
async def obs_integration():
    """Pagina di integrazione con OBS Studio."""
    try:
        # Ottieni lo stato dell'integrazione OBS
        obs_data = await api_request('http://localhost:5000/api/obs/status')
        if not obs_data:
            obs_data = {"connected": False, "status": "Non connesso", "version": "N/A"}
        
        # Se connesso, ottieni le scenes OBS
        obs_scenes = []
        if obs_data.get('connected'):
            scenes_data = await api_request('http://localhost:5000/api/obs/scenes')
            if scenes_data:
                obs_scenes = scenes_data.get('scenes', [])
        
        return await render_template('obs_integration.html', 
                                     obs_data=obs_data, 
                                     obs_scenes=obs_scenes)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di integrazione OBS: {e}")
        return await render_template('obs_integration.html', 
                                     error=str(e),
                                     obs_data={"connected": False, "status": "Errore", "version": "N/A"},
                                     obs_scenes=[])

@app.route('/webhook_management')
@login_required
async def webhook_management():
    """Pagina di gestione dei webhook."""
    try:
        # Ottieni la lista dei webhook configurati
        webhook_data = await api_request('http://localhost:5000/api/webhooks')
        webhooks = webhook_data.get('webhooks', []) if webhook_data else []
        
        return await render_template('webhook_management.html', webhooks=webhooks)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di gestione dei webhook: {e}")
        return await render_template('webhook_management.html', error=str(e), webhooks=[])

@app.route('/translation_management')
@admin_required
async def translation_management():
    """Pagina di gestione delle traduzioni."""
    try:
        # Ottieni le statistiche delle traduzioni
        translation_stats = await api_request('http://localhost:5000/api/translations/stats')
        if not translation_stats:
            translation_stats = {"total_strings": 0, "languages": {}}
        
        # Ottieni le lingue disponibili
        languages_data = await api_request('http://localhost:5000/api/translations/languages')
        available_languages = languages_data.get('languages', []) if languages_data else []
        
        return await render_template('translation_management.html', 
                                    stats=translation_stats, 
                                    languages=available_languages)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di gestione delle traduzioni: {e}")
        return await render_template('translation_management.html', error=str(e), stats={}, languages=[])

@app.route('/auto_updater')
@admin_required
async def auto_updater():
    """Pagina di gestione degli aggiornamenti automatici."""
    try:
        # Ottieni le informazioni sull'aggiornamento
        updater_info = await api_request('http://localhost:5000/api/updater/info')
        if not updater_info:
            updater_info = {"current_version": "sconosciuta", "available_update": False}
        
        # Ottieni i backup disponibili
        backup_data = await api_request('http://localhost:5000/api/updater/backups')
        backups = backup_data.get('backups', []) if backup_data else []
        
        return await render_template('auto_updater.html', 
                                    updater_info=updater_info, 
                                    backups=backups)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina dell'aggiornatore automatico: {e}")
        return await render_template('auto_updater.html', 
                                    error=str(e), 
                                    updater_info={"current_version": "sconosciuta", "available_update": False}, 
                                    backups=[])

@app.route('/check_updates', methods=['POST'])
@admin_required
async def check_updates():
    """Controlla se ci sono aggiornamenti disponibili."""
    try:
        # Richiedi il controllo degli aggiornamenti
        result = await api_request('http://localhost:5000/api/updater/check', method='POST', timeout=30)
        if result and result.get('success'):
            return jsonify({"success": True, "update_available": result.get('update_available', False), 
                           "version": result.get('version', ''), "changes": result.get('changes', '')})
        else:
            return jsonify({"success": False, "message": "Errore nel controllo degli aggiornamenti"})
    except Exception as e:
        logger.error(f"Errore nel controllo degli aggiornamenti: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

@app.route('/install_update', methods=['POST'])
@admin_required
async def install_update():
    """Installa un aggiornamento disponibile."""
    try:
        # Crea un backup prima dell'aggiornamento
        backup_result = await api_request('http://localhost:5000/api/backups/create', 
                                        method='POST', 
                                        data={"auto_backup": True, "before_update": True},
                                        timeout=120)
        
        if not backup_result or not backup_result.get('success'):
            logger.warning("Impossibile creare backup automatico prima dell'aggiornamento")
            
        # Richiedi l'installazione dell'aggiornamento
        result = await api_request('http://localhost:5000/api/updater/update', 
                                 method='POST', 
                                 timeout=300, 
                                 retries=1)  # No retry per operazione critica
        
        if result and result.get('success'):
            return jsonify({
                "success": True, 
                "message": "Aggiornamento installato con successo",
                "restart_required": result.get('restart_required', False),
                "version": result.get('version', '')
            })
        else:
            error_msg = result.get('message', 'Errore nell\'installazione dell\'aggiornamento') if result else 'Errore di comunicazione con il bot'
            return jsonify({"success": False, "message": error_msg})
    except Exception as e:
        logger.error(f"Errore nell'installazione dell'aggiornamento: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

@app.route('/ai_moderation')
@admin_required
async def ai_moderation():
    """Pagina di gestione della moderazione AI."""
    try:
        # Ottieni le informazioni sulla moderazione AI
        moderation_data = await api_request('http://localhost:5000/api/moderation/status')
        if not moderation_data:
            moderation_data = {"enabled": False, "model": "unknown", "sensitivity": "medium"}
        
        return await render_template('ai_moderation.html', moderation_data=moderation_data)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di moderazione AI: {e}")
        return await render_template('ai_moderation.html', 
                                    error=str(e), 
                                    moderation_data={"enabled": False, "model": "unknown", "sensitivity": "medium"})

@app.route('/channels/add', methods=['GET', 'POST'])
@login_required
async def add_channel():
    """Aggiunge un nuovo canale Kick."""
    error = None
    
    try:
        # Verifica se l'utente esiste nel database
        user_id = session.get('user_id')
        user = {'id': user_id, 'username': 'Utente'}
        
        if db_pool:
            async with db_pool.acquire() as conn:
                db_user = await conn.fetchrow('SELECT id, username FROM users WHERE id = $1', user_id)
                
                if db_user:
                    user = dict(db_user)
        
        if request.method == 'POST':
            form = await request.form
            channel_name = form.get('channel_name')
            
            if not channel_name:
                error = "Nome del canale richiesto"
            else:
                # Genera i parametri PKCE in modo sicuro
                code_verifier = secrets.token_urlsafe(64)
                code_challenge = base64.urlsafe_b64encode(
                    hashlib.sha256(code_verifier.encode()).digest()
                ).decode().rstrip("=")
                state = secrets.token_urlsafe(32)
                
                # Salva i dati nella sessione
                session['code_verifier'] = code_verifier
                session['channel_name'] = channel_name
                
                # Costruisci l'URL OAuth
                oauth_params = {
                    "response_type": "code",
                    "client_id": CLIENT_ID,
                    "redirect_uri": REDIRECT_URI,
                    "scope": SCOPE,
                    "code_challenge": code_challenge,
                    "code_challenge_method": "S256",
                    "state": state
                }
                
                oauth_url = f"https://id.kick.com/oauth/authorize?{urlencode(oauth_params)}"
                return redirect(oauth_url)
    except Exception as e:
        logger.error(f"Errore in add_channel: {e}")
        error = f"Si è verificato un errore: {str(e)}"
    
    return await render_template('add_channel.html', error=error)

@app.route('/auth/callback')
async def auth_callback():
    """Callback per l'autenticazione OAuth di Kick."""
    code = request.args.get('code')
    state = request.args.get('state')
    
    if not code:
        return redirect(url_for('add_channel', error="Autorizzazione negata"))
        
    try:
        # Ottieni il code_verifier dalla sessione
        code_verifier = session.get('code_verifier')
        channel_name = session.get('channel_name')
        
        if not code_verifier or not channel_name:
            return redirect(url_for('add_channel', error="Sessione scaduta o invalida"))
        
        # Scambia il codice di autorizzazione con un token di accesso
        token_data = {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": code,
            "code_verifier": code_verifier
        }
        
        # Questa operazione asincrona in Quart
        async with aiohttp.ClientSession() as session:
            async with session.post("https://id.kick.com/oauth/token", data=token_data) as response:
                if response.status != 200:
                    error_message = await response.text()
                    logger.error(f"Errore nell'ottenimento del token: {error_message}")
                    return redirect(url_for('add_channel', error="Errore nell'autenticazione con Kick"))
                
                token_response = await response.json()
                access_token = token_response.get("access_token")
                refresh_token = token_response.get("refresh_token")
                
                if not access_token or not refresh_token:
                    logger.error("Token o refresh token mancanti nella risposta")
                    return redirect(url_for('add_channel', error="Risposta di autenticazione incompleta"))
                
                # Ottieni le informazioni dell'utente Kick
                headers = {"Authorization": f"Bearer {access_token}"}
                async with session.get("https://kick.com/api/v1/user", headers=headers) as user_response:
                    if user_response.status != 200:
                        error_message = await user_response.text()
                        logger.error(f"Errore nell'ottenimento delle informazioni dell'utente: {error_message}")
                        return redirect(url_for('add_channel', error="Errore nell'ottenimento delle informazioni dell'utente"))
                    
                    user_data = await user_response.json()
                    kick_id = user_data.get("id")
                    kick_username = user_data.get("username", "unknown")
                    
                    if not kick_id:
                        logger.error("ID utente Kick mancante nella risposta")
                        return redirect(url_for('add_channel', error="Risposta di Kick incompleta"))
                    
                    # Salva il canale nel database
                    if not db_pool:
                        return redirect(url_for('add_channel', error="Database non disponibile"))
                    
                    async with db_pool.acquire() as conn:
                        # Verifica se il canale esiste già
                        existing_channel = await conn.fetchrow(
                            'SELECT id FROM channels WHERE kick_channel_id = $1',
                            str(kick_id)
                        )
                        
                        if existing_channel:
                            logger.warning(f"Canale Kick già registrato: {kick_id}")
                            return redirect(url_for('dashboard', message="Canale già registrato"))
                        
                        # Crea il nuovo canale
                        channel_id = await conn.fetchval('''
                            INSERT INTO channels (
                                kick_channel_id, name, owner_id, 
                                access_token, refresh_token, 
                                settings, created_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, NOW())
                            RETURNING id
                        ''', 
                        str(kick_id), 
                        channel_name or kick_username, 
                        session.get('user_id'), 
                        access_token, 
                        refresh_token,
                        json.dumps({"auto_connect": True})
                        )
                        
                        if not channel_id:
                            logger.error("Errore nella creazione del canale nel database")
                            return redirect(url_for('add_channel', error="Errore nella creazione del canale"))
                        
                        # Imposta il canale come corrente per l'utente
                        await conn.execute(
                            'UPDATE users SET current_channel_id = $1 WHERE id = $2',
                            channel_id, session.get('user_id')
                        )
                        
                        # Pulisci i dati della sessione
                        if 'code_verifier' in session:
                            del session['code_verifier']
                        if 'channel_name' in session:
                            del session['channel_name']
                        
                        return redirect(url_for('channel_detail', channel_id=channel_id))
                        
    except Exception as e:
        logger.error(f"Errore in auth_callback: {e}")
        return redirect(url_for('add_channel', error=f"Si è verificato un errore: {str(e)}"))

@app.route('/channel/<int:channel_id>')
@login_required
async def channel_detail(channel_id):
    """Mostra i dettagli di un canale."""
    user_id = session.get('user_id')
    
    # Valori predefiniti in caso di errore del database
    channel = None
    commands = []
    stats = {'unique_chatters': 0, 'total_messages': 0, 'total_commands': 0, 'top_user': None}
    settings = {}
    
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                # Verifica che l'utente sia il proprietario del canale
                channel = await conn.fetchrow('''
                    SELECT c.id, c.name, c.kick_channel_id, c.created_at, c.updated_at
                    FROM channels c
                    WHERE c.id = $1 AND c.owner_id = $2
                ''', channel_id, user_id)
                
                if not channel:
                    return redirect(url_for('dashboard', error="Canale non trovato o non autorizzato"))
                    
                # Ottieni i comandi configurati
                commands = await conn.fetch('''
                    SELECT id, name, response, cooldown, user_level, enabled, usage_count, updated_at
                    FROM commands
                    WHERE channel_id = $1
                    ORDER BY name
                ''', channel_id)
                
                # Ottieni le statistiche del canale
                stats = await conn.fetchrow('''
                    SELECT 
                        COUNT(DISTINCT cm.user_id) AS unique_chatters,
                        COUNT(*) AS total_messages,
                        COUNT(*) FILTER (WHERE cm.is_command) AS total_commands,
                        (SELECT username FROM users 
                         JOIN channel_points cp ON users.id = cp.user_id 
                         WHERE cp.channel_id = $1 
                         ORDER BY cp.points DESC LIMIT 1) AS top_user
                    FROM chat_messages cm
                    WHERE cm.channel_id = $1
                ''', channel_id)
                
                # Ottieni le impostazioni del canale
                settings_rows = await conn.fetch('''
                    SELECT key, value
                    FROM settings
                    WHERE channel_id = $1
                ''', channel_id)
                
                for row in settings_rows:
                    settings[row['key']] = row['value']
        except Exception as e:
            logger.error(f"Errore nel caricamento dei dettagli del canale: {e}")
            return await render_template('error.html', message=f"Errore del server: {str(e)}"), 500
    else:
        return await render_template('error.html', message="Database non disponibile"), 500
    
    if not channel:
        return redirect(url_for('dashboard', error="Canale non trovato o non autorizzato"))
    
    return await render_template(
        'channel_detail.html',
        channel=channel,
        commands=commands,
        stats=stats,
        settings=settings
    )

@app.route('/channel/<int:channel_id>/commands', methods=['GET', 'POST'])
@login_required
async def manage_commands(channel_id):
    """Gestisce i comandi di un canale."""
    user_id = session.get('user_id')
    error = None
    success = None
    channel = None
    commands = []
    
    if not db_pool:
        return await render_template('error.html', message="Database non disponibile"), 500
        
    try:
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            channel = await conn.fetchrow('''
                SELECT c.id, c.name
                FROM channels c
                WHERE c.id = $1 AND c.owner_id = $2
            ''', channel_id, user_id)
            
            if not channel:
                return redirect(url_for('dashboard', error="Canale non trovato o non autorizzato"))
        
            if request.method == 'POST':
                form = await request.form
                action = form.get('action')
                
                if action == 'add':
                    # Aggiungi un nuovo comando
                    name = form.get('name', '').strip()
                    response = form.get('response', '').strip()
                    
                    try:
                        cooldown = int(form.get('cooldown', 5))
                        if cooldown < 0:
                            cooldown = 0
                        elif cooldown > 3600:  # max 1 ora
                            cooldown = 3600
                    except ValueError:
                        cooldown = 5
                    
                    user_level = form.get('user_level', 'everyone')
                    
                    # Validazione input
                    if not name:
                        error = "Il nome del comando è obbligatorio"
                    elif not response:
                        error = "La risposta del comando è obbligatoria"
                    elif not name.startswith('!'):
                        error = "Il nome del comando deve iniziare con !"
                    elif len(name) > 50:
                        error = "Il nome del comando non può superare i 50 caratteri"
                    elif len(response) > 500:
                        error = "La risposta non può superare i 500 caratteri"
                    elif user_level not in ['everyone', 'subscriber', 'moderator', 'admin']:
                        error = "Livello utente non valido"
                    else:
                        try:
                            # Verifica se il comando esiste già
                            existing_cmd = await conn.fetchval('''
                                SELECT id FROM commands
                                WHERE channel_id = $1 AND name = $2
                            ''', channel_id, name)
                            
                            if existing_cmd:
                                # Aggiorna il comando esistente
                                await conn.execute('''
                                    UPDATE commands
                                    SET response = $1, cooldown = $2, user_level = $3, updated_at = NOW()
                                    WHERE id = $4
                                ''', response, cooldown, user_level, existing_cmd)
                                success = f"Comando {name} aggiornato"
                            else:
                                # Crea un nuovo comando
                                await conn.execute('''
                                    INSERT INTO commands 
                                    (channel_id, name, response, cooldown, user_level, created_at, updated_at)
                                    VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
                                ''', channel_id, name, response, cooldown, user_level)
                                success = f"Comando {name} aggiunto"
                        except Exception as e:
                            logger.error(f"Errore nell'aggiunta del comando: {e}")
                            error = "Errore nell'aggiunta del comando"
                
                elif action == 'delete':
                    # Elimina un comando
                    command_id = int(form.get('command_id'))
                    
                    try:
                        # Verifica che il comando appartenga a questo canale
                        cmd = await conn.fetchrow('''
                            SELECT name FROM commands
                            WHERE id = $1 AND channel_id = $2
                        ''', command_id, channel_id)
                        
                        if cmd:
                            await conn.execute('DELETE FROM commands WHERE id = $1', command_id)
                            success = f"Comando {cmd['name']} eliminato"
                        else:
                            error = "Comando non trovato o non autorizzato"
                    except Exception as e:
                        logger.error(f"Errore nell'eliminazione del comando: {e}")
                        error = "Errore nell'eliminazione del comando"
                
                elif action == 'toggle':
                    # Attiva/disattiva un comando
                    command_id = int(form.get('command_id'))
                    
                    try:
                        # Ottieni lo stato attuale e invertilo
                        cmd = await conn.fetchrow('''
                            SELECT name, enabled FROM commands
                            WHERE id = $1 AND channel_id = $2
                        ''', command_id, channel_id)
                        
                        if cmd:
                            new_state = not cmd['enabled']
                            await conn.execute('''
                                UPDATE commands
                                SET enabled = $1, updated_at = NOW()
                                WHERE id = $2
                            ''', new_state, command_id)
                            
                            status = "attivato" if new_state else "disattivato"
                            success = f"Comando {cmd['name']} {status}"
                        else:
                            error = "Comando non trovato o non autorizzato"
                    except Exception as e:
                        logger.error(f"Errore nell'aggiornamento del comando: {e}")
                        error = "Errore nell'aggiornamento del comando"
            
            # Ottieni tutti i comandi
            commands = await conn.fetch('''
                SELECT id, name, response, cooldown, user_level, enabled, usage_count, updated_at
                FROM commands
                WHERE channel_id = $1
                ORDER BY name
            ''', channel_id)
    except Exception as e:
        logger.error(f"Errore nella gestione dei comandi: {e}")
        return await render_template('error.html', message=f"Errore del server: {str(e)}"), 500
    
    if not channel:
        return redirect(url_for('dashboard', error="Canale non trovato o non autorizzato"))
    
    return await render_template(
        'manage_commands.html',
        channel=channel,
        commands=commands,
        error=error,
        success=success
    )

@app.route('/channel/<int:channel_id>/settings', methods=['GET', 'POST'])
@login_required
async def channel_settings(channel_id):
    """Gestisce le impostazioni di un canale."""
    user_id = session.get('user_id')
    error = None
    success = None
    channel = None
    settings = {}
    
    if not db_pool:
        return await render_template('error.html', message="Database non disponibile"), 500
        
    try:
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            channel = await conn.fetchrow('''
                SELECT c.id, c.name
                FROM channels c
                WHERE c.id = $1 AND c.owner_id = $2
            ''', channel_id, user_id)
            
            if not channel:
                return redirect(url_for('dashboard', error="Canale non trovato o non autorizzato"))
        
            if request.method == 'POST':
                form = await request.form
                
                # Impostazioni da salvare
                settings_to_save = {
                    'welcome_message': form.get('welcome_message', ''),
                    'auto_shoutout': form.get('auto_shoutout', 'false'),
                    'points_per_minute': form.get('points_per_minute', '1'),
                    'command_cooldown': form.get('command_cooldown', '5'),
                    'bot_prefix': form.get('bot_prefix', '!'),
                    'mod_only_commands': form.get('mod_only_commands', '')
                }
                
                try:
                    # Salva ogni impostazione
                    for key, value in settings_to_save.items():
                        await conn.execute('''
                            INSERT INTO settings (channel_id, key, value)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (channel_id, key) 
                            DO UPDATE SET value = $3
                        ''', channel_id, key, value)
                    
                    success = "Impostazioni salvate con successo"
                except Exception as e:
                    logger.error(f"Errore nel salvataggio delle impostazioni: {e}")
                    error = "Errore nel salvataggio delle impostazioni"
        
            # Ottieni le impostazioni attuali
            settings_rows = await conn.fetch('''
                SELECT key, value
                FROM settings
                WHERE channel_id = $1
            ''', channel_id)
            
            for row in settings_rows:
                settings[row['key']] = row['value']
    except Exception as e:
        logger.error(f"Errore nella gestione delle impostazioni: {e}")
        return await render_template('error.html', message=f"Errore del server: {str(e)}"), 500
    
    if not channel:
        return redirect(url_for('dashboard', error="Canale non trovato o non autorizzato"))
        
    # Imposta i valori predefiniti per le impostazioni mancanti
    default_settings = {
        'welcome_message': 'Benvenuto nella chat, {user}!',
        'auto_shoutout': 'false',
        'points_per_minute': '1',
        'command_cooldown': '5',
        'bot_prefix': '!',
        'mod_only_commands': '!ban !timeout !clear'
    }
    
    for key, value in default_settings.items():
        if key not in settings:
            settings[key] = value
    
    return await render_template(
        'channel_settings.html',
        channel=channel,
        settings=settings,
        error=error,
        success=success
    )

@app.route('/channel/<int:channel_id>/games', methods=['GET', 'POST'])
@login_required
async def channel_games(channel_id):
    """Gestisce i giochi di un canale."""
    user_id = session.get('user_id')
    error = None
    success = None
    channel = None
    
    if not db_pool:
        return await render_template('error.html', message="Database non disponibile"), 500
        
    try:
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            channel = await conn.fetchrow('''
                SELECT c.id, c.name
                FROM channels c
                WHERE c.id = $1 AND c.owner_id = $2
            ''', channel_id, user_id)
            
            if not channel:
                return redirect(url_for('dashboard', error="Canale non trovato o non autorizzato"))
        
            if request.method == 'POST':
                form = await request.form
                action = form.get('action')
                
                if action == 'start_game':
                    game_type = form.get('game_type')
                    min_points = int(form.get('min_points', 10))
                    duration = int(form.get('duration', 60))
                    
                    # Qui chiameremmo l'API del bot per avviare il gioco
                    # Per ora, simula solo un successo
                    success = f"Gioco {game_type} avviato"
    except Exception as e:
        logger.error(f"Errore nella gestione dei giochi: {e}")
        return await render_template('error.html', message=f"Errore del server: {str(e)}"), 500
    
    if not channel:
        return redirect(url_for('dashboard', error="Canale non trovato o non autorizzato"))
    
    return await render_template(
        'channel_games.html',
        channel=channel,
        error=error,
        success=success
    )

@app.route('/channel/<int:channel_id>/stats')
@login_required
@cached_response(timeout=300)  # Cache per 5 minuti
async def channel_stats(channel_id):
    """Mostra statistiche dettagliate del canale."""
    user_id = session.get('user_id')
    channel = None
    stats = {'unique_chatters': 0, 'total_messages': 0, 'total_commands': 0, 'command_count': 0}
    top_chatters = []
    top_commands = []
    top_points = []
    
    if not db_pool:
        return await render_template('error.html', message="Database non disponibile"), 500
        
    try:
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            channel = await conn.fetchrow('''
                SELECT c.id, c.name
                FROM channels c
                WHERE c.id = $1 AND c.owner_id = $2
            ''', channel_id, user_id)
            
            if not channel:
                return redirect(url_for('dashboard', error="Canale non trovato o non autorizzato"))
                
            # Ottieni statistiche generali
            stats = await conn.fetchrow('''
                SELECT 
                    COUNT(DISTINCT cm.user_id) AS unique_chatters,
                    COUNT(*) AS total_messages,
                    COUNT(*) FILTER (WHERE cm.is_command) AS total_commands,
                    (SELECT COUNT(*) FROM commands WHERE channel_id = $1) AS command_count
                FROM chat_messages cm
                WHERE cm.channel_id = $1
            ''', channel_id)
            
            # Ottieni i top chatters
            top_chatters = await conn.fetch('''
                SELECT 
                    cm.username,
                    COUNT(*) as message_count
                FROM chat_messages cm
                WHERE cm.channel_id = $1
                GROUP BY cm.username
                ORDER BY message_count DESC
                LIMIT 10
            ''', channel_id)
            
            # Ottieni i comandi più usati
            top_commands = await conn.fetch('''
                SELECT 
                    cm.content,
                    COUNT(*) as usage_count
                FROM chat_messages cm
                WHERE cm.channel_id = $1 AND cm.is_command = true
                GROUP BY cm.content
                ORDER BY usage_count DESC
                LIMIT 10
            ''', channel_id)
            
            # Ottieni i punti dei top utenti
            top_points = await conn.fetch('''
                SELECT 
                    u.username,
                    cp.points
                FROM channel_points cp
                JOIN users u ON cp.user_id = u.id
                WHERE cp.channel_id = $1
                ORDER BY cp.points DESC
                LIMIT 10
            ''', channel_id)
    except Exception as e:
        logger.error(f"Errore nel caricamento delle statistiche: {e}")
        return await render_template('error.html', message=f"Errore del server: {str(e)}"), 500
    
    if not channel:
        return redirect(url_for('dashboard', error="Canale non trovato o non autorizzato"))
    
    return await render_template(
        'channel_stats.html',
        channel=channel,
        stats=stats,
        top_chatters=top_chatters,
        top_commands=top_commands,
        top_points=top_points
    )

@app.route('/api/bot/start', methods=['POST'])
@login_required
async def api_start_bot():
    """API per avviare il bot per un canale."""
    if request.method == 'POST':
        data = await request.json
        channel_id = data.get('channel_id')
        user_id = session.get('user_id')
        
        if not channel_id:
            return jsonify({'error': 'ID canale richiesto'}), 400
            
        if not db_pool:
            return jsonify({'error': 'Database non disponibile'}), 500
            
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            channel = await conn.fetchrow('''
                SELECT c.id, c.name
                FROM channels c
                WHERE c.id = $1 AND c.owner_id = $2
            ''', channel_id, user_id)
            
            if not channel:
                return jsonify({'error': 'Canale non trovato o non autorizzato'}), 403
                
            # Qui chiameremmo l'API del bot per avviarlo
            # Per ora, simula solo un successo
            return jsonify({'success': True, 'message': f'Bot avviato per il canale {channel["name"]}'})

@app.route('/api/bot/stop', methods=['POST'])
@login_required
async def api_stop_bot():
    """API per fermare il bot per un canale."""
    if request.method == 'POST':
        data = await request.json
        channel_id = data.get('channel_id')
        user_id = session.get('user_id')
        
        if not channel_id:
            return jsonify({'error': 'ID canale richiesto'}), 400
            
        if not db_pool:
            return jsonify({'error': 'Database non disponibile'}), 500
            
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            channel = await conn.fetchrow('''
                SELECT c.id, c.name
                FROM channels c
                WHERE c.id = $1 AND c.owner_id = $2
            ''', channel_id, user_id)
            
            if not channel:
                return jsonify({'error': 'Canale non trovato o non autorizzato'}), 403
                
            # Qui chiameremmo l'API del bot per fermarlo
            # Per ora, simula solo un successo
            return jsonify({'success': True, 'message': f'Bot fermato per il canale {channel["name"]}'})

@app.route('/api/channel/<int:channel_id>/commands', methods=['GET'])
async def api_get_commands(channel_id):
    """API per ottenere i comandi di un canale."""
    try:
        if not db_pool:
            return jsonify({'error': 'Database non disponibile'}), 500
            
        async with db_pool.acquire() as conn:
            # Verifica che il canale esista
            channel = await conn.fetchrow('''
                SELECT c.id, c.name
                FROM channels c
                WHERE c.id = $1
            ''', channel_id)
            
            if not channel:
                return jsonify({'error': 'Canale non trovato'}), 404
                
            # Ottieni i comandi attivi
            commands = await conn.fetch('''
                SELECT id, name, response, cooldown, user_level, enabled
                FROM commands
                WHERE channel_id = $1 AND enabled = true
                ORDER BY name
            ''', channel_id)
            
            commands_list = []
            for cmd in commands:
                commands_list.append({
                    'id': cmd['id'],
                    'name': cmd['name'],
                    'response': cmd['response'],
                    'cooldown': cmd['cooldown'],
                    'user_level': cmd['user_level'],
                    'enabled': cmd['enabled']
                })
                
            return jsonify({
                'channel_id': channel_id,
                'channel_name': channel['name'],
                'commands': commands_list
            })
    except Exception as e:
        logger.error(f"Errore nell'API comandi: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/commands/<channel_name>')
async def public_commands(channel_name):
    """Pagina pubblica che mostra i comandi disponibili per un canale."""
    try:
        if not db_pool:
            return await render_template('error.html', message="Database non disponibile"), 500
            
        async with db_pool.acquire() as conn:
            # Ottieni l'ID del canale dal nome
            channel = await conn.fetchrow('''
                SELECT id, name
                FROM channels
                WHERE name = $1
            ''', channel_name)
            
            if not channel:
                return await render_template('error.html', message="Canale non trovato"), 404
                
            # Ottieni i comandi attivi
            commands = await conn.fetch('''
                SELECT name, response, cooldown, user_level
                FROM commands
                WHERE channel_id = $1 AND enabled = true
                ORDER BY name
            ''', channel['id'])
            
        return await render_template(
            'public_commands.html',
            channel_name=channel_name,
            commands=commands
        )
    except Exception as e:
        logger.error(f"Errore nella pagina pubblica comandi: {e}")
        return await render_template('error.html', message=f"Errore del server: {str(e)}"), 500

@app.route('/features')
async def features():
    """Pagina delle funzionalità di M4Bot."""
    return await render_template('features.html')

@app.route('/password_recovery', methods=['GET', 'POST'])
async def password_recovery():
    """Pagina di recupero password."""
    if request.method == 'POST':
        email = request.form.get('email')
        
        # Verifica se l'email esiste nel sistema
        async with app.pool.acquire() as conn:
            user = await conn.fetchrow('SELECT id, username FROM users WHERE email = $1', email)
            
            if user:
                # Genera un token di recupero
                token = secrets.token_urlsafe(32)
                expiry = datetime.now() + timedelta(hours=2)
                
                # Salva il token nel database
                await conn.execute(
                    'INSERT INTO password_reset_tokens (user_id, token, expires_at) VALUES ($1, $2, $3)',
                    user['id'], token, expiry
                )
                
                # Qui si dovrebbe inviare l'email di recupero
                # Per semplicità, facciamo finta che l'email sia stata inviata
                flash('Ti abbiamo inviato un\'email con le istruzioni per reimpostare la password.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Nessun account trovato con questa email.', 'danger')
    
    return await render_template('password_recovery.html')

@app.route('/command_editor', methods=['GET', 'POST'])
@login_required
async def command_editor():
    """Editor visuale dei comandi."""
    channel_id = request.args.get('channel_id')
    
    if not channel_id:
        return redirect(url_for('dashboard'))
    
    # Verifica che il canale appartenga all'utente corrente
    async with app.pool.acquire() as conn:
        channel = await conn.fetchrow(
            'SELECT * FROM channels WHERE id = $1 AND user_id = $2',
            channel_id, session.get('user_id')
        )
        
        if not channel:
            flash('Canale non trovato o non autorizzato.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Carica i comandi esistenti
        commands = await conn.fetch(
            'SELECT * FROM commands WHERE channel_id = $1 ORDER BY name',
            channel_id
        )
    
    return await render_template('command_editor.html', channel=channel, commands=commands)

@app.route('/user/profile', methods=['GET', 'POST'])
@login_required
async def user_profile():
    """Gestione del profilo utente"""
    user_id = session.get('user_id')
    error = None
    success = None

    # Verifica connessione database
    if not db_pool:
        error = "Impossibile connettersi al database. Riprova più tardi."
        return await render_template('user_profile.html', error=error)

    # Ottieni informazioni utente dal database
    try:
        async with db_pool.acquire() as conn:
            # Query per ottenere i dati dell'utente
            user_data = await conn.fetchrow('''
                SELECT username, email, is_admin, created_at, last_login, 
                       COALESCE(two_factor_enabled, false) as two_factor_enabled 
                FROM users WHERE id = $1
            ''', user_id)
            
            if not user_data:
                return redirect(url_for('logout'))
            
            # Formatta le date in modo leggibile
            created_at = user_data['created_at'].strftime('%d/%m/%Y') if user_data['created_at'] else 'N/A'
            last_login = user_data['last_login'].strftime('%d/%m/%Y %H:%M') if user_data['last_login'] else 'N/A'
            
            # Gestione delle richieste POST (aggiornamento profilo)
            if request.method == 'POST':
                form = await request.form
                action = form.get('action')
                
                if action == 'update_profile':
                    # Aggiornamento informazioni profilo
                    new_username = form.get('username')
                    new_email = form.get('email')
                    
                    # Validazione input
                    if len(new_username) < 3:
                        error = "Il nome utente deve essere di almeno 3 caratteri."
                    elif not re.match(r"[^@]+@[^@]+\.[^@]+", new_email):
                        error = "Inserisci un indirizzo email valido."
                    else:
                        # Verifica se l'email è già in uso da un altro utente
                        existing_user = await conn.fetchval('''
                            SELECT id FROM users WHERE email = $1 AND id != $2
                        ''', new_email, user_id)
                        
                        if existing_user:
                            error = "Questa email è già in uso da un altro account."
                        else:
                            # Aggiorna il profilo
                            await conn.execute('''
                                UPDATE users SET username = $1, email = $2 WHERE id = $3
                            ''', new_username, new_email, user_id)
                            
                            success = "Profilo aggiornato con successo!"
                            
                            # Aggiorna i dati dell'utente per la visualizzazione
                            user_data = dict(user_data)
                            user_data['username'] = new_username
                            user_data['email'] = new_email
                
                elif action == 'change_password':
                    # Cambio password
                    current_password = form.get('current_password')
                    new_password = form.get('new_password')
                    confirm_password = form.get('confirm_password')
                    
                    # Validazione input
                    if not current_password or not new_password or not confirm_password:
                        error = "Tutti i campi sono obbligatori."
                    elif new_password != confirm_password:
                        error = "Le password non corrispondono."
                    elif len(new_password) < 8:
                        error = "La password deve essere di almeno 8 caratteri."
                    else:
                        # Verifica la password attuale
                        stored_hash = await conn.fetchval('''
                            SELECT password_hash FROM users WHERE id = $1
                        ''', user_id)
                        
                        if not bcrypt.checkpw(current_password.encode(), stored_hash.encode()):
                            error = "La password attuale non è corretta."
                        else:
                            # Genera il nuovo hash della password
                            new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
                            
                            # Aggiorna la password
                            await conn.execute('''
                                UPDATE users SET password_hash = $1 WHERE id = $2
                            ''', new_hash, user_id)
                            
                            success = "Password aggiornata con successo!"
                
                elif action == 'toggle_2fa':
                    # Toggle per l'autenticazione a due fattori
                    enabled = form.get('enabled') == 'true'
                    
                    await conn.execute('''
                        UPDATE users SET two_factor_enabled = $1 WHERE id = $2
                    ''', enabled, user_id)
                    
                    user_data = dict(user_data)
                    user_data['two_factor_enabled'] = enabled
                    success = f"Autenticazione a due fattori {'attivata' if enabled else 'disattivata'} con successo!"
        
        return await render_template('user_profile.html', 
                                user=user_data, 
                                created_at=created_at,
                                last_login=last_login,
                                error=error,
                                success=success)
    
    except Exception as e:
        logger.error(f"Errore nel profilo utente: {str(e)}")
        error = "Si è verificato un errore durante il caricamento del profilo. Riprova più tardi."
        return await render_template('user_profile.html', error=error)

@app.errorhandler(404)
async def page_not_found(e):
    """Gestisce gli errori 404."""
    return await render_template('error.html', message="Pagina non trovata"), 404

@app.errorhandler(500)
async def server_error(e):
    """Gestisce gli errori 500."""
    return await render_template('error.html', message="Errore interno del server"), 500

@app.before_serving
async def before_serving():
    """Eseguito prima di avviare il server."""
    # Verifica le chiavi di sicurezza
    verify_security_keys()
    
    # Inizializza le connessioni
    await setup_db_pool()
    await setup_bot_client()
    await setup_redis_client()
    
    # Avvia il task di ascolto per le notifiche Redis (WebSocket)
    if redis_pubsub:
        asyncio.create_task(listen_redis_messages())
    
    # Inizializza i plugin
    setup_plugins(app)

def verify_security_keys():
    """Verifica che le chiavi di sicurezza siano correttamente impostate."""
    warnings = []
    
    # Verifica la chiave segreta dell'app
    if app.secret_key == ENCRYPTION_KEY:
        warnings.append("ATTENZIONE: La chiave segreta dell'app è uguale alla chiave di crittografia.")
    
    # Verifica se la chiave di crittografia è quella predefinita
    if ENCRYPTION_KEY.startswith("temporary_"):
        warnings.append("ATTENZIONE: Stai utilizzando una chiave di crittografia temporanea.")
    
    # Visualizza gli avvisi
    for warning in warnings:
        logger.warning(warning)
        print(warning)

@app.before_request
async def secure_request():
    """Middleware per applicare requisiti di sicurezza alle richieste."""
    # Verifica se l'app richiede HTTPS
    if os.getenv("REQUIRE_HTTPS", "false").lower() == "true":
        if request.headers.get("X-Forwarded-Proto", "http") != "https" and request.url.startswith("http://"):
            # Reindirizza a HTTPS
            url = request.url.replace("http://", "https://", 1)
            return redirect(url, code=301)

@app.after_serving
async def after_serving():
    """Eseguito dopo l'arresto del server."""
    global db_pool, bot_client, redis_client, redis_pubsub
    
    if db_pool:
        await db_pool.close()
    
    if bot_client:
        await bot_client.close()
        
    if redis_client:
        if redis_pubsub:
            await redis_pubsub.unsubscribe()
        await redis_client.close()

async def listen_redis_messages():
    """Ascolta i messaggi da Redis e li invia ai client WebSocket."""
    if not redis_pubsub:
        return
        
    try:
        while True:
            message = await redis_pubsub.get_message(ignore_subscribe_messages=True)
            if message and message['type'] == 'message':
                channel = message['channel']
                data = message['data']
                
                # Invia a tutti i client WebSocket interessati
                clients_to_remove = []
                for client_id, client_info in websocket_clients.items():
                    if channel in client_info['subscriptions']:
                        try:
                            if client_info['websocket'].connected:
                                await client_info['websocket'].send(json.dumps({
                                    'channel': channel,
                                    'data': json.loads(data) if isinstance(data, str) else data
                                }))
                            else:
                                clients_to_remove.append(client_id)
                        except Exception as e:
                            logger.error(f"Errore nell'invio al client WebSocket {client_id}: {e}")
                            clients_to_remove.append(client_id)
                
                # Rimuovi client disconnessi
                for client_id in clients_to_remove:
                    if client_id in websocket_clients:
                        del websocket_clients[client_id]
                        
            # Piccola pausa per non sovraccaricare la CPU
            await asyncio.sleep(0.01)
    except Exception as e:
        logger.error(f"Errore nel listener Redis: {e}")
        # Riprova tra 5 secondi
        await asyncio.sleep(5)
        asyncio.create_task(listen_redis_messages())

@app.route('/api/system/status')
@login_required
@cached_response(timeout=30)  # Cache per 30 secondi
async def api_system_status():
    """Ottiene lo stato completo del sistema."""
    try:
        # Ottieni lo stato dal bot
        status_data = await api_request('http://localhost:5000/api/system/status')
        
        # Se non possiamo ottenere i dati dal bot, restituisci informazioni limitate
        if not status_data:
            status_data = {
                "bot": {
                    "running": False,
                    "status": "Non connesso",
                    "version": "sconosciuta",
                    "uptime": 0
                },
                "database": {
                    "connected": db_pool is not None,
                    "status": "Connesso" if db_pool is not None else "Disconnesso"
                },
                "cache": cache_stats
            }
        else:
            # Aggiungi info sulla cache
            status_data["cache"] = cache_stats
            
        return jsonify(status_data)
    except Exception as e:
        logger.error(f"Errore nell'ottenere lo stato del sistema: {e}")
        return jsonify({
            "error": str(e),
            "bot": {"running": False, "status": "Errore"},
            "database": {"connected": False, "status": "Errore"},
            "cache": cache_stats
        })

@app.route('/system/diagnostics', methods=['GET'])
@admin_required
@cached_response(timeout=30)  # Cache per 30 secondi
async def system_diagnostics():
    """Pagina di diagnostica per verificare lo stato delle connessioni."""
    diagnostics = {
        "database": {
            "connected": False,
            "status": "Non verificato",
            "error": None,
            "tables": []
        },
        "bot_api": {
            "connected": False,
            "status": "Non verificato",
            "error": None,
            "version": None
        },
        "integrations": {
            "discord": {"connected": False, "status": "Non verificato"},
            "obs": {"connected": False, "status": "Non verificato"},
            "webhook": {"enabled": False, "status": "Non verificato"}
        },
        "environment": {
            "python_version": sys.version,
            "web_server": "Quart/ASGI",
            "dependencies": []
        }
    }
    
    # Verifica connessione database
    try:
        if db_pool:
            async with db_pool.acquire() as conn:
                # Verifica se possiamo eseguire query
                db_version = await conn.fetchval("SELECT version()")
                
                # Ottieni lista tabelle
                tables = await conn.fetch('''
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public'
                ''')
                
                diagnostics["database"]["connected"] = True
                diagnostics["database"]["status"] = "Connesso"
                diagnostics["database"]["tables"] = [t["table_name"] for t in tables]
                diagnostics["database"]["version"] = db_version
        else:
            diagnostics["database"]["status"] = "Non connesso"
    except Exception as e:
        diagnostics["database"]["status"] = "Errore"
    
    # Verifica connessione API bot
    try:
        bot_status = await api_request('http://localhost:5000/api/system/status')
        if bot_status:
            diagnostics["bot_api"]["connected"] = True
            diagnostics["bot_api"]["status"] = "Connesso"
            diagnostics["bot_api"]["version"] = bot_status.get("bot", {}).get("version", "sconosciuta")
            
            # Aggiorna stato integrazioni
            integrations = bot_status.get("integrations", {})
            if "discord" in integrations:
                diagnostics["integrations"]["discord"] = integrations["discord"]
            if "obs" in integrations:
                diagnostics["integrations"]["obs"] = integrations["obs"]
            if "webhooks" in integrations:
                diagnostics["integrations"]["webhook"] = integrations["webhooks"]
        else:
            diagnostics["bot_api"]["status"] = "Non connesso"
    except Exception as e:
        diagnostics["bot_api"]["status"] = "Errore"
        diagnostics["bot_api"]["error"] = str(e)
    
    # Verifica dipendenze
    diagnostics["environment"]["dependencies"] = [
        {"name": "aiohttp", "version": aiohttp.__version__},
        {"name": "asyncpg", "version": asyncpg.__version__},
        {"name": "quart", "version": getattr(app, "__version__", "N/A")},
        {"name": "bcrypt", "version": bcrypt.__version__}
    ]
    
    return await render_template('system_diagnostics.html', diagnostics=diagnostics)

@app.route('/channel_stats')
async def channel_stats():
    """Pagina delle statistiche del canale."""
    return await render_template('channel_stats.html')

@app.route('/advanced_analytics')
async def advanced_analytics():
    """Pagina delle analytics avanzate."""
    # Ottieni i canali dell'utente
    channels = await get_user_channels(session.get('user_id'))
    
    # Genera statistiche di esempio per demo
    stats = {
        'streaming_hours': 87.5,
        'new_followers': 342,
        'chat_messages': 15728,
        'new_subscribers': 28
    }
    
    # Questo sarebbe sostituito da dati reali in produzione
    return await render_template('advanced_analytics.html', 
                                channels=channels,
                                stats=stats)

@app.route('/youtube_integration')
@login_required
async def youtube_integration():
    """Pagina di integrazione con YouTube."""
    try:
        # Ottieni lo stato dell'integrazione YouTube
        youtube_data = await api_request('http://localhost:5000/api/youtube/status')
        if not youtube_data:
            youtube_data = {"connected": False, "status": "Non connesso", "channel": {"title": "N/A"}}
        
        # Se connesso, ottieni statistiche del canale YouTube
        youtube_stats = {}
        if youtube_data.get('connected'):
            stats_data = await api_request('http://localhost:5000/api/youtube/stats')
            if stats_data:
                youtube_stats = stats_data
        
        # Ottieni le impostazioni di sincronizzazione
        sync_settings = await api_request('http://localhost:5000/api/youtube/settings')
        if not sync_settings:
            sync_settings = {
                "sync_chat_enabled": False,
                "auto_reply_enabled": False
            }
        
        # Ottieni la lista delle dirette programmate e passate
        upcoming_streams = []
        past_streams = []
        if youtube_data.get('connected'):
            streams_data = await api_request('http://localhost:5000/api/youtube/streams')
            if streams_data:
                upcoming_streams = streams_data.get('upcoming', [])
                past_streams = streams_data.get('past', [])
        
        return await render_template('youtube_integration.html', 
                                    youtube_data=youtube_data,
                                    youtube_stats=youtube_stats,
                                    sync_settings=sync_settings,
                                    upcoming_streams=upcoming_streams,
                                    past_streams=past_streams)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di integrazione YouTube: {e}")
        return await render_template('youtube_integration.html', 
                                    error=str(e),
                                    youtube_data={"connected": False, "status": "Errore", "channel": {"title": "N/A"}},
                                    youtube_stats={},
                                    sync_settings={},
                                    upcoming_streams=[],
                                    past_streams=[])

@app.route('/api/youtube/connect', methods=['POST'])
@login_required
async def youtube_connect():
    """Connette l'applicazione a YouTube."""
    try:
        form = await request.form
        client_id = form.get('client_id')
        client_secret = form.get('client_secret')
        api_key = form.get('api_key')
        
        if not client_id or not client_secret:
            return jsonify({"success": False, "message": "Client ID e Client Secret sono richiesti"})
        
        # Dati di configurazione per il connettore YouTube
        config_data = {
            "youtube_oauth_client_id": client_id,
            "youtube_oauth_client_secret": client_secret
        }
        
        if api_key:
            config_data["youtube_api_key"] = api_key
        
        # Invia la richiesta di connessione
        result = await api_request('http://localhost:5000/api/youtube/connect', 
                                  method='POST', 
                                  data=config_data)
        
        if result and result.get('success'):
            # Se la connessione richiede autenticazione OAuth, restituisci l'URL di autenticazione
            if result.get('auth_url'):
                return jsonify({"success": True, "auth_required": True, "auth_url": result.get('auth_url')})
            else:
                return jsonify({"success": True, "message": "Connessione a YouTube completata con successo"})
        else:
            error_msg = result.get('message', 'Errore nella connessione a YouTube') if result else 'Errore nella comunicazione con il server'
            return jsonify({"success": False, "message": error_msg})
    except Exception as e:
        logger.error(f"Errore nella connessione a YouTube: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

@app.route('/api/youtube/oauth_callback')
@login_required
async def youtube_oauth_callback():
    """Gestisce il callback OAuth di YouTube."""
    try:
        # Recupera il codice di autorizzazione
        code = request.args.get('code')
        if not code:
            return await render_template('error.html', message="Codice di autorizzazione mancante")
        
        # Completa il processo di autenticazione
        result = await api_request('http://localhost:5000/api/youtube/oauth_callback', 
                                  method='POST', 
                                  data={"code": code})
        
        if result and result.get('success'):
            return redirect(url_for('youtube_integration'))
        else:
            error_msg = result.get('message', 'Errore di autenticazione') if result else 'Errore nella comunicazione con il server'
            return await render_template('error.html', message=error_msg)
    except Exception as e:
        logger.error(f"Errore nel callback OAuth di YouTube: {e}")
        return await render_template('error.html', message=f"Errore: {str(e)}")

@app.route('/api/youtube/disconnect', methods=['POST'])
@login_required
async def youtube_disconnect():
    """Disconnette l'applicazione da YouTube."""
    try:
        # Invia la richiesta di disconnessione
        result = await api_request('http://localhost:5000/api/youtube/disconnect', method='POST')
        
        if result and result.get('success'):
            return jsonify({"success": True, "message": "Disconnessione da YouTube completata con successo"})
        else:
            error_msg = result.get('message', 'Errore nella disconnessione da YouTube') if result else 'Errore nella comunicazione con il server'
            return jsonify({"success": False, "message": error_msg})
    except Exception as e:
        logger.error(f"Errore nella disconnessione da YouTube: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

@app.route('/api/youtube/update_settings', methods=['POST'])
@login_required
async def youtube_update_settings():
    """Aggiorna le impostazioni di sincronizzazione YouTube."""
    try:
        data = await request.json
        
        # Impostazioni da aggiornare
        settings = {
            "sync_chat_enabled": data.get('sync_chat_enabled', False),
            "auto_reply_enabled": data.get('auto_reply_enabled', False)
        }
        
        # Invia la richiesta di aggiornamento
        result = await api_request('http://localhost:5000/api/youtube/settings', 
                                  method='POST', 
                                  data=settings)
        
        if result and result.get('success'):
            return jsonify({"success": True, "message": "Impostazioni aggiornate con successo"})
        else:
            error_msg = result.get('message', 'Errore nell\'aggiornamento delle impostazioni') if result else 'Errore nella comunicazione con il server'
            return jsonify({"success": False, "message": error_msg})
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento delle impostazioni YouTube: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

@app.route('/api/youtube/create_stream', methods=['POST'])
@login_required
async def youtube_create_stream():
    """Crea una nuova diretta YouTube."""
    try:
        form = await request.form
        
        # Dati della diretta
        stream_data = {
            "title": form.get('title'),
            "description": form.get('description'),
            "scheduled_start_time": form.get('scheduled_start_time'),
            "privacy_status": form.get('privacy_status', 'private'),
            "enable_chat": form.get('enable_chat') == 'on'
        }
        
        # Invia la richiesta di creazione
        result = await api_request('http://localhost:5000/api/youtube/streams/create', 
                                  method='POST', 
                                  data=stream_data)
        
        if result and result.get('success'):
            return jsonify({"success": True, "message": "Diretta creata con successo", "stream": result.get('stream')})
        else:
            error_msg = result.get('message', 'Errore nella creazione della diretta') if result else 'Errore nella comunicazione con il server'
            return jsonify({"success": False, "message": error_msg})
    except Exception as e:
        logger.error(f"Errore nella creazione della diretta YouTube: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

@app.route('/api/youtube/update_stream/<stream_id>', methods=['POST'])
@login_required
async def youtube_update_stream(stream_id):
    """Aggiorna una diretta YouTube esistente."""
    try:
        form = await request.form
        
        # Dati della diretta
        stream_data = {
            "stream_id": stream_id,
            "title": form.get('title'),
            "description": form.get('description'),
            "scheduled_start_time": form.get('scheduled_start_time'),
            "privacy_status": form.get('privacy_status', 'private')
        }
        
        # Invia la richiesta di aggiornamento
        result = await api_request('http://localhost:5000/api/youtube/streams/update', 
                                  method='POST', 
                                  data=stream_data)
        
        if result and result.get('success'):
            return jsonify({"success": True, "message": "Diretta aggiornata con successo"})
        else:
            error_msg = result.get('message', 'Errore nell\'aggiornamento della diretta') if result else 'Errore nella comunicazione con il server'
            return jsonify({"success": False, "message": error_msg})
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento della diretta YouTube: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

@app.route('/api/youtube/delete_stream/<stream_id>', methods=['POST'])
@login_required
async def youtube_delete_stream(stream_id):
    """Elimina una diretta YouTube."""
    try:
        # Invia la richiesta di eliminazione
        result = await api_request(f'http://localhost:5000/api/youtube/streams/delete/{stream_id}', 
                                  method='POST')
        
        if result and result.get('success'):
            return jsonify({"success": True, "message": "Diretta eliminata con successo"})
        else:
            error_msg = result.get('message', 'Errore nell\'eliminazione della diretta') if result else 'Errore nella comunicazione con il server'
            return jsonify({"success": False, "message": error_msg})
    except Exception as e:
        logger.error(f"Errore nell'eliminazione della diretta YouTube: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

# Importazioni per i nuovi moduli
from routes.metrics import metrics_blueprint
from routes.templates import templates_blueprint
from api.youtube_metrics import create_youtube_metrics
from api.kick_metrics import create_kick_metrics
from api.telegram_connector import create_telegram_connector
from bot.whatsapp_connector import create_whatsapp_connector

# Importazioni per i nuovi moduli avanzati
from routes.dashboard import dashboard_blueprint
from routes.workflows import workflows_blueprint
from routes.notifications import notifications_blueprint
from routes.preview import preview_blueprint

# Registra i nuovi blueprint
app.register_blueprint(metrics_blueprint)
app.register_blueprint(templates_blueprint)
app.register_blueprint(dashboard_blueprint)
app.register_blueprint(workflows_blueprint)
app.register_blueprint(notifications_blueprint)
app.register_blueprint(preview_blueprint)

# Inizializza i gestori di metriche e connettori
@app.before_first_request
def initialize_services():
    """Inizializza i servizi necessari all'avvio dell'app"""
    try:
        # Crea l'event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Configura YouTube Metrics
        youtube_config = {
            "youtube_api_key": app.config.get("YOUTUBE_API_KEY", ""),
            "youtube_channel_id": app.config.get("YOUTUBE_CHANNEL_ID", ""),
            "youtube_metrics_update_interval": app.config.get("YOUTUBE_METRICS_UPDATE_INTERVAL", 60)
        }
        app.youtube_metrics = create_youtube_metrics(youtube_config)
        
        # Configura Kick Metrics
        kick_config = {
            "kick_channel_name": app.config.get("KICK_CHANNEL_NAME", ""),
            "kick_metrics_update_interval": app.config.get("KICK_METRICS_UPDATE_INTERVAL", 60)
        }
        app.kick_metrics = create_kick_metrics(kick_config)
        
        # Configura Telegram Connector
        telegram_config = {
            "telegram_bot_token": app.config.get("TELEGRAM_BOT_TOKEN", ""),
            "telegram_webhook_url": app.config.get("TELEGRAM_WEBHOOK_URL", ""),
            "telegram_message_templates": app.config.get("TELEGRAM_MESSAGE_TEMPLATES", {})
        }
        app.telegram_connector = create_telegram_connector(telegram_config)
        
        # Configura WhatsApp Connector (se non è già stato configurato)
        if not hasattr(app, 'whatsapp_connector'):
            whatsapp_config = {
                "whatsapp_api_version": app.config.get("WHATSAPP_API_VERSION", "v16.0"),
                "whatsapp_phone_number_id": app.config.get("WHATSAPP_PHONE_NUMBER_ID", ""),
                "whatsapp_token": app.config.get("WHATSAPP_TOKEN", ""),
                "whatsapp_verify_token": app.config.get("WHATSAPP_VERIFY_TOKEN", ""),
                "whatsapp_message_templates": app.config.get("WHATSAPP_MESSAGE_TEMPLATES", {})
            }
            app.whatsapp_connector = create_whatsapp_connector(whatsapp_config)
        
        # Avvia i servizi
        loop.run_until_complete(app.youtube_metrics.start())
        loop.run_until_complete(app.kick_metrics.start())
        loop.run_until_complete(app.telegram_connector.start())
        loop.run_until_complete(app.whatsapp_connector.start())
        
        app.logger.info("Servizi inizializzati con successo")
    except Exception as e:
        app.logger.error(f"Errore nell'inizializzazione dei servizi: {e}")

# Gestione chiusura applicazione
@app.teardown_appcontext
def shutdown_services(exception=None):
    """Chiude i servizi quando l'app viene terminata."""
    pass

@app.websocket('/ws/notifications')
async def notifications_ws():
    """WebSocket per le notifiche in tempo reale."""
    client_id = str(uuid.uuid4())
    try:
        # Registra il client
        websocket_clients[client_id] = {
            'websocket': websocket._get_current_object(),
            'subscriptions': ['m4bot_notifications'],
            'connected_at': datetime.now().isoformat()
        }
        
        # Invia messaggio di benvenuto
        await websocket.send(json.dumps({
            'type': 'connected',
            'message': 'Connesso al server di notifiche',
            'client_id': client_id
        }))
        
        # Mantieni la connessione attiva finché il client è connesso
        while True:
            # Aspetta e processa i messaggi dal client
            # (potrebbero essere usati per modificare le sottoscrizioni)
            data = await websocket.receive()
            try:
                msg = json.loads(data)
                if msg.get('action') == 'subscribe' and 'channel' in msg:
                    if msg['channel'] not in websocket_clients[client_id]['subscriptions']:
                        websocket_clients[client_id]['subscriptions'].append(msg['channel'])
                elif msg.get('action') == 'unsubscribe' and 'channel' in msg:
                    if msg['channel'] in websocket_clients[client_id]['subscriptions']:
                        websocket_clients[client_id]['subscriptions'].remove(msg['channel'])
                elif msg.get('action') == 'ping':
                    await websocket.send(json.dumps({'type': 'pong', 'timestamp': time.time()}))
            except json.JSONDecodeError:
                pass
            
            # Piccola pausa per non sovraccaricare la CPU
            await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Errore nella connessione WebSocket: {e}")
    finally:
        # Rimuovi il client quando si disconnette
        if client_id in websocket_clients:
            del websocket_clients[client_id]

@app.websocket('/ws/metrics')
async def metrics_ws():
    """WebSocket per le metriche in tempo reale."""
    client_id = str(uuid.uuid4())
    try:
        # Registra il client
        websocket_clients[client_id] = {
            'websocket': websocket._get_current_object(),
            'subscriptions': ['m4bot_metrics'],
            'connected_at': datetime.now().isoformat()
        }
        
        # Invia messaggio di benvenuto
        await websocket.send(json.dumps({
            'type': 'connected',
            'message': 'Connesso al server di metriche',
            'client_id': client_id
        }))
        
        # Invia immediatamente i dati correnti
        if hasattr(app, 'youtube_metrics'):
            await websocket.send(json.dumps({
                'channel': 'm4bot_metrics',
                'data': {
                    'source': 'youtube',
                    'metrics': app.youtube_metrics.current_metrics
                }
            }))
        
        if hasattr(app, 'kick_metrics'):
            await websocket.send(json.dumps({
                'channel': 'm4bot_metrics',
                'data': {
                    'source': 'kick',
                    'metrics': app.kick_metrics.current_metrics
                }
            }))
        
        # Mantieni la connessione attiva finché il client è connesso
        while True:
            # Aspetta e processa i messaggi dal client
            data = await websocket.receive()
            try:
                msg = json.loads(data)
                if msg.get('action') == 'ping':
                    await websocket.send(json.dumps({'type': 'pong', 'timestamp': time.time()}))
            except json.JSONDecodeError:
                pass
            
            await asyncio.sleep(0.1)
    except Exception as e:
        logger.error(f"Errore nella connessione WebSocket metrics: {e}")
    finally:
        # Rimuovi il client quando si disconnette
        if client_id in websocket_clients:
            del websocket_clients[client_id]

@app.route('/api/webhook/whatsapp', methods=['GET', 'POST'])
def whatsapp_webhook():
    """Gestisce il webhook di WhatsApp"""
    if request.method == 'GET':
        # Verifica della configurazione webhook
        if hasattr(app, 'whatsapp_connector'):
            verify_token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')
            mode = request.args.get('hub.mode')
            
            # Verifica il token
            if app.whatsapp_connector.verify_webhook(request.args):
                return challenge
            else:
                return 'Token di verifica non valido', 403
        else:
            return 'Connettore WhatsApp non inizializzato', 500
    elif request.method == 'POST':
        # Gestione degli eventi webhook
        if hasattr(app, 'whatsapp_connector'):
            # Crea l'event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Processa il webhook
            data = request.json
            result = loop.run_until_complete(app.whatsapp_connector.process_webhook(data))
            
            if result:
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'Errore nel processamento del webhook'}), 500
        else:
            return jsonify({'success': False, 'error': 'Connettore WhatsApp non inizializzato'}), 500

# Webhook per Telegram
@app.route('/api/webhook/telegram', methods=['POST'])
def telegram_webhook():
    """Gestisce il webhook di Telegram"""
    if hasattr(app, 'telegram_connector'):
        # Crea l'event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Processa il webhook
        data = request.json
        result = loop.run_until_complete(app.telegram_connector.process_webhook(data))
        
        if result:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Errore nel processamento del webhook'}), 500
    else:
        return jsonify({'success': False, 'error': 'Connettore Telegram non inizializzato'}), 500

# Importazioni per i plugin
from plugins import setup_plugins

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
