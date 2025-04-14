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

import aiohttp
from quart import Quart, render_template, request, redirect, url_for, session, jsonify, flash
from quart_cors import cors
import asyncpg
import bcrypt
from dotenv import load_dotenv
from flask_babel import Babel, gettext as _
from babel_compat import *

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

async def setup_db_pool():
    """Crea il pool di connessioni al database."""
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(
            user=DB_USER,
            password=DB_PASS,
            database=DB_NAME,
            host=DB_HOST
        )
        logger.info("Connessione al database PostgreSQL stabilita")
    except Exception as e:
        logger.error(f"Errore nella connessione al database: {e}")
        # Per lo sviluppo, è utile poter continuare anche senza database
        # In produzione, questo dovrebbe terminare l'applicazione
        logger.warning("L'applicazione continuerà senza database (solo per sviluppo)")

async def setup_bot_client():
    """Crea la connessione al bot."""
    global bot_client
    try:
        # Configura il client HTTP per comunicare con il bot
        bot_client = aiohttp.ClientSession()
        logger.info("Client HTTP per la comunicazione con il bot inizializzato")
    except Exception as e:
        logger.error(f"Errore nell'inizializzazione del client HTTP: {e}")
        logger.warning("L'applicazione continuerà senza connessione al bot")
    
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
    # Priorità: 1. Parametro URL, 2. Cookie, 3. Preferenza browser, 4. Default (it)
    lang = request.args.get('lang')
    if lang and lang in ['it', 'en', 'es', 'fr', 'de']:
        # In Quart, dobbiamo differire l'impostazione del cookie alla risposta
        session['preferred_language'] = lang
        return lang
    
    # Verifica cookie
    saved_lang = session.get('preferred_language')
    if saved_lang and saved_lang in ['it', 'en', 'es', 'fr', 'de']:
        return saved_lang
        
    # Altrimenti usa la preferenza del browser o default
    return request.accept_languages.best_match(['it', 'en', 'es', 'fr', 'de'], default='it')

@app.context_processor
async def inject_language_info():
    current_lang = await get_locale()
    language_names = {
        'it': 'Italiano',
        'en': 'English',
        'es': 'Español',
        'fr': 'Français',
        'de': 'Deutsch'
    }
    return {
        'current_language': current_lang,
        'current_language_name': language_names.get(current_lang, 'Italiano'),
        'available_languages': language_names
    }

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
async def system_health():
    """Pagina di monitoraggio della salute del bot."""
    try:
        # Ottieni lo stato del sistema dal bot
        if bot_client:
            async with bot_client.get('http://localhost:5000/api/health', timeout=5) as response:
                if response.status == 200:
                    health_data = await response.json()
                else:
                    health_data = {"status": "error", "message": "Impossibile ottenere lo stato del bot"}
        else:
            health_data = {
                "status": "unknown",
                "uptime": 0,
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "disk_usage": 0.0,
                "last_check": datetime.now().isoformat(),
                "services": {
                    "database": False,
                    "api": False,
                    "websocket": False
                }
            }
        
        return await render_template('system_health.html', health_data=health_data)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di stato del sistema: {e}")
        return await render_template('system_health.html', error=str(e))

@app.route('/backup_management')
@admin_required
async def backup_management():
    """Pagina di gestione dei backup del database."""
    try:
        # Ottieni la lista dei backup disponibili
        if bot_client:
            async with bot_client.get('http://localhost:5000/api/backups', timeout=5) as response:
                if response.status == 200:
                    backups = await response.json()
                else:
                    backups = []
        else:
            backups = []
        
        return await render_template('backup_management.html', backups=backups)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di gestione dei backup: {e}")
        return await render_template('backup_management.html', error=str(e))

@app.route('/create_backup', methods=['POST'])
@admin_required
async def create_backup():
    """Crea un nuovo backup del database."""
    try:
        if bot_client:
            async with bot_client.post('http://localhost:5000/api/backups/create', timeout=30) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('success'):
                        return jsonify({"success": True, "message": "Backup creato con successo"})
                    else:
                        return jsonify({"success": False, "message": result.get('message', 'Errore nella creazione del backup')})
                else:
                    return jsonify({"success": False, "message": "Errore nella richiesta di backup"})
        else:
            return jsonify({"success": False, "message": "Connessione al bot non disponibile"})
    except Exception as e:
        logger.error(f"Errore nella creazione del backup: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

@app.route('/restore_backup/<backup_id>', methods=['POST'])
@admin_required
async def restore_backup(backup_id):
    """Ripristina un backup del database."""
    try:
        if bot_client:
            async with bot_client.post(f'http://localhost:5000/api/backups/restore/{backup_id}', timeout=60) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get('success'):
                        return jsonify({"success": True, "message": "Backup ripristinato con successo"})
                    else:
                        return jsonify({"success": False, "message": result.get('message', 'Errore nel ripristino del backup')})
                else:
                    return jsonify({"success": False, "message": "Errore nella richiesta di ripristino"})
        else:
            return jsonify({"success": False, "message": "Connessione al bot non disponibile"})
    except Exception as e:
        logger.error(f"Errore nel ripristino del backup: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

@app.route('/discord_integration')
@login_required
async def discord_integration():
    """Pagina di integrazione con Discord."""
    try:
        # Ottieni lo stato dell'integrazione Discord
        if bot_client:
            async with bot_client.get('http://localhost:5000/api/discord/status', timeout=5) as response:
                if response.status == 200:
                    discord_data = await response.json()
                else:
                    discord_data = {"connected": False, "error": "Impossibile ottenere lo stato dell'integrazione Discord"}
        else:
            discord_data = {"connected": False, "error": "Connessione al bot non disponibile"}
        
        # Ottieni i canali Discord configurati
        discord_channels = []
        if bot_client and discord_data.get('connected'):
            async with bot_client.get('http://localhost:5000/api/discord/channels', timeout=5) as response:
                if response.status == 200:
                    discord_channels = await response.json()
        
        return await render_template('discord_integration.html', discord_data=discord_data, channels=discord_channels)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di integrazione Discord: {e}")
        return await render_template('discord_integration.html', error=str(e))

@app.route('/obs_integration')
@login_required
async def obs_integration():
    """Pagina di integrazione con OBS."""
    try:
        # Ottieni lo stato dell'integrazione OBS
        if bot_client:
            async with bot_client.get('http://localhost:5000/api/obs/status', timeout=5) as response:
                if response.status == 200:
                    obs_data = await response.json()
                else:
                    obs_data = {"connected": False, "error": "Impossibile ottenere lo stato dell'integrazione OBS"}
        else:
            obs_data = {"connected": False, "error": "Connessione al bot non disponibile"}
        
        # Ottieni le scene OBS disponibili
        obs_scenes = []
        if bot_client and obs_data.get('connected'):
            async with bot_client.get('http://localhost:5000/api/obs/scenes', timeout=5) as response:
                if response.status == 200:
                    obs_scenes = await response.json()
        
        return await render_template('obs_integration.html', obs_data=obs_data, scenes=obs_scenes)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di integrazione OBS: {e}")
        return await render_template('obs_integration.html', error=str(e))

@app.route('/webhook_management')
@login_required
async def webhook_management():
    """Pagina di gestione dei webhook."""
    try:
        # Ottieni la lista dei webhook configurati
        if bot_client:
            async with bot_client.get('http://localhost:5000/api/webhooks', timeout=5) as response:
                if response.status == 200:
                    webhooks = await response.json()
                else:
                    webhooks = []
        else:
            webhooks = []
        
        return await render_template('webhook_management.html', webhooks=webhooks)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di gestione dei webhook: {e}")
        return await render_template('webhook_management.html', error=str(e))

@app.route('/translation_management')
@admin_required
async def translation_management():
    """Pagina di gestione delle traduzioni."""
    try:
        # Ottieni le statistiche delle traduzioni
        if bot_client:
            async with bot_client.get('http://localhost:5000/api/translations/stats', timeout=5) as response:
                if response.status == 200:
                    translation_stats = await response.json()
                else:
                    translation_stats = {}
        else:
            translation_stats = {}
        
        # Ottieni le lingue disponibili
        if bot_client:
            async with bot_client.get('http://localhost:5000/api/translations/languages', timeout=5) as response:
                if response.status == 200:
                    available_languages = await response.json()
                else:
                    available_languages = []
        else:
            available_languages = []
        
        return await render_template('translation_management.html', translation_stats=translation_stats, available_languages=available_languages)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di gestione delle traduzioni: {e}")
        return await render_template('translation_management.html', error=str(e))

@app.route('/auto_updater')
@admin_required
async def auto_updater():
    """Pagina di gestione degli aggiornamenti automatici."""
    try:
        # Ottieni le informazioni sull'aggiornamento
        if bot_client:
            async with bot_client.get('http://localhost:5000/api/updater/info', timeout=5) as response:
                if response.status == 200:
                    update_info = await response.json()
                else:
                    update_info = {"current_version": "Unknown", "available": False}
        else:
            update_info = {"current_version": "Unknown", "available": False}
        
        # Ottieni i backup disponibili per il ripristino
        if bot_client:
            async with bot_client.get('http://localhost:5000/api/updater/backups', timeout=5) as response:
                if response.status == 200:
                    available_backups = await response.json()
                else:
                    available_backups = []
        else:
            available_backups = []
        
        return await render_template('auto_updater.html', update_info=update_info, available_backups=available_backups)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di gestione degli aggiornamenti: {e}")
        return await render_template('auto_updater.html', error=str(e))

@app.route('/check_updates', methods=['POST'])
@admin_required
async def check_updates():
    """Controlla se ci sono aggiornamenti disponibili."""
    try:
        if bot_client:
            async with bot_client.post('http://localhost:5000/api/updater/check', timeout=30) as response:
                if response.status == 200:
                    result = await response.json()
                    return jsonify(result)
                else:
                    return jsonify({"success": False, "message": "Errore nella richiesta di controllo aggiornamenti"})
        else:
            return jsonify({"success": False, "message": "Connessione al bot non disponibile"})
    except Exception as e:
        logger.error(f"Errore nel controllo degli aggiornamenti: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

@app.route('/install_update', methods=['POST'])
@admin_required
async def install_update():
    """Installa un aggiornamento."""
    try:
        if bot_client:
            async with bot_client.post('http://localhost:5000/api/updater/update', timeout=300) as response:
                if response.status == 200:
                    result = await response.json()
                    return jsonify(result)
                else:
                    return jsonify({"success": False, "message": "Errore nella richiesta di installazione aggiornamento"})
        else:
            return jsonify({"success": False, "message": "Connessione al bot non disponibile"})
    except Exception as e:
        logger.error(f"Errore nell'installazione dell'aggiornamento: {e}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"})

@app.route('/ai_moderation')
@admin_required
async def ai_moderation():
    """Pagina di configurazione della moderazione AI."""
    try:
        # Ottieni lo stato della moderazione AI
        if bot_client:
            async with bot_client.get('http://localhost:5000/api/moderation/status', timeout=5) as response:
                if response.status == 200:
                    moderation_status = await response.json()
                else:
                    moderation_status = {"enabled": False, "error": "Impossibile ottenere lo stato della moderazione AI"}
        else:
            moderation_status = {"enabled": False, "error": "Connessione al bot non disponibile"}
        
        return await render_template('ai_moderation.html', moderation_status=moderation_status)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina di moderazione AI: {e}")
        return await render_template('ai_moderation.html', error=str(e))

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
                    name = form.get('name')
                    response = form.get('response')
                    cooldown = int(form.get('cooldown', 5))
                    user_level = form.get('user_level', 'everyone')
                    
                    if not name or not response:
                        error = "Nome e risposta del comando sono richiesti"
                    elif not name.startswith('!'):
                        error = "Il nome del comando deve iniziare con !"
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
async def channel_stats(channel_id):
    """Mostra le statistiche di un canale."""
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
    await setup_db_pool()
    await setup_bot_client()

@app.after_serving
async def after_serving():
    """Eseguito dopo l'arresto del server."""
    global db_pool, bot_client
    
    if db_pool:
        await db_pool.close()
    
    if bot_client:
        await bot_client.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
