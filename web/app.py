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
import platform

import aiohttp
from quart import Quart, render_template, request, redirect, url_for, session, jsonify, flash, websocket
from quart_cors import cors
import asyncpg
import bcrypt
from dotenv import load_dotenv
import redis.asyncio as redis

# Import per rate limiting
from quart_rate_limiter import RateLimiter, rate_limit
from quart_rate_limiter.redis_store import RedisStore

# Definizione della versione dell'applicazione
APP_VERSION = "3.1.0"

# Aggiungi la directory principale al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carica le variabili d'ambiente dal file .env
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(env_path)

# Verifica se siamo su Linux
IS_LINUX = platform.system() == 'Linux'

# Importazione di flask-babel e compatibilità
try:
    # Prima importa babel_compat per applicare i patch necessari
    from babel_compat import Babel, logger as babel_logger
    # Ora importa gettext da flask_babel
    from flask_babel import gettext as _
    babel_available = True
    babel_logger.info("Flask-Babel importato correttamente")
except ImportError as e:
    # Fallback se flask-babel non è disponibile
    babel_available = False
    # Funzione fittizia per gettext
    def _(text):
        return text
    logging.warning(f"Impossibile importare Flask-Babel: {e}")
    
import redis.asyncio as redis

# Encoder JSON personalizzato per gestire stringhe di traduzione "lazy"
from quart.json import JSONEncoder
class CustomJSONEncoder(JSONEncoder):
    """Classe personalizzata per la codifica JSON che supporta le stringhe
    di traduzione lazy. È necessario per usare flash() con testi tradotti."""
    def default(self, obj):
        try:
            from speaklater import is_lazy_string
            if is_lazy_string(obj):
                try:
                    return str(obj)  # Per Python 3
                except Exception as e:
                    # Fallback in caso di errore
                    logging.warning(f"Errore nella codifica di stringa lazy: {e}")
                    return str(obj)
        except ImportError:
            pass
        return super().default(obj)

# Aggiungi la directory principale al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Carica le variabili d'ambiente dal file .env
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(env_path)

# Configurazione
CLIENT_ID = os.getenv('KICK_CLIENT_ID', 'your_kick_client_id')
CLIENT_SECRET = os.getenv('KICK_CLIENT_SECRET', 'your_kick_client_secret')
REDIRECT_URI = os.getenv('REDIRECT_URI', 'https://your-domain.com/auth/callback')
SCOPE = "public"
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', secrets.token_hex(16))
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

# Configurazione refresh token
REFRESH_TOKEN_EXPIRY = int(os.getenv('REFRESH_TOKEN_EXPIRY', '604800'))  # 7 giorni in secondi
ACCESS_TOKEN_EXPIRY = int(os.getenv('ACCESS_TOKEN_EXPIRY', '3600'))  # 1 ora in secondi

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
app.config['BABEL_DEFAULT_TIMEZONE'] = 'Europe/Rome'
app.json_encoder = CustomJSONEncoder  # Usa il custom JSON encoder per gestire lazy strings

# Inizializzazione del rate limiter con Redis
# Setup Redis per rate limiting
limiter = RateLimiter(app)

# Utilizza Redis per il rate limiter se disponibile
@app.before_serving
async def setup_rate_limiter():
    global redis_client
    if redis_client:
        # Configura Redis per il rate limiting
        limiter.storage = RedisStore(redis_client)
        logger.info("Rate limiter configurato con Redis")
    else:
        logger.warning("Rate limiter utilizzerà memoria locale (non persistente)")

# Configurazione per VPS Linux - assicura percorsi assoluti
if IS_LINUX:
    # Correzione percorsi per traduzioni
    translations_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'translations')
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = translations_path
    logger.info(f"Percorso traduzioni impostato per Linux: {translations_path}")
else:
    app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'

# Inizializzazione di Babel con il nuovo modulo di compatibilità
if babel_available:
    babel = Babel(app)
    # Assicurati che l'estensione babel sia registrata
    babel.ensure_babel_extension(app)
    logger.info("Babel inizializzato correttamente")
else:
    # Fallback se non disponibile (già definito in babel_compat)
    from babel_compat import Babel
    babel = Babel(app)
    # Assicurati che l'estensione babel sia registrata
    babel.ensure_babel_extension(app)
    logger.warning("Flask-Babel non disponibile, utilizzando stub")

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

# Configurazione GDPR
GDPR_ENABLED = True  # Abilita le funzionalità GDPR
PRIVACY_POLICY_VERSION = "1.0"  # Versione corrente della privacy policy
COOKIE_POLICY_VERSION = "1.0"  # Versione corrente della cookie policy

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

# GDPR relegate functions
def has_gdpr_consent():
    """Verifica se l'utente ha dato il consenso GDPR"""
    if not GDPR_ENABLED:
        return True
    
    # Verifica il cookie di consenso
    consent = request.cookies.get('m4bot_cookie_consent')
    return consent == 'true'

def get_privacy_settings():
    """Ottiene le impostazioni sulla privacy dell'utente"""
    if not GDPR_ENABLED:
        return {
            "necessary": True,
            "functional": True,
            "analytics": True,
            "marketing": True
        }
    
    # Verifica il cookie delle impostazioni
    settings_cookie = request.cookies.get('m4bot_cookie_settings')
    if not settings_cookie:
        return {
            "necessary": True,
            "functional": False,
            "analytics": False,
            "marketing": False
        }
    
    try:
        import base64
        settings = json.loads(base64.b64decode(settings_cookie).decode())
        # Assicura che necessary sia sempre True
        settings["necessary"] = True
        return settings
    except Exception as e:
        logger.error(f"Errore nel decodificare le impostazioni privacy: {e}")
        return {
            "necessary": True,
            "functional": False,
            "analytics": False,
            "marketing": False
        }

# Funzioni di utilità
def login_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            # Controlla se c'è un token di accesso nei cookie
            access_token = request.cookies.get('access_token')
            
            if access_token:
                user_id = await validate_token(access_token)
                if user_id:
                    # Reimpostare la sessione con l'utente
                    session['user_id'] = user_id
                    return await f(*args, **kwargs)
            
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
    # Funzione per ottenere la lingua dell'utente
    try:
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
    except Exception as e:
        logger.error(f"Errore nella selezione della lingua: {e}")
        return 'it'

@app.context_processor
async def inject_version():
    """Inietta la versione dell'applicazione in tutti i template."""
    return {
        'app_version': APP_VERSION
    }

@app.context_processor
async def inject_common_data():
    """Inietta dati comuni in tutti i template."""
    return {
        'now': datetime.now,
        'gdpr_enabled': GDPR_ENABLED,
        'privacy_settings': get_privacy_settings() if GDPR_ENABLED else None,
        'has_gdpr_consent': has_gdpr_consent() if GDPR_ENABLED else True,
        'privacy_policy_version': PRIVACY_POLICY_VERSION,
        'cookie_policy_version': COOKIE_POLICY_VERSION
    }

@app.after_request
async def add_language_switcher(response):
    """Aggiunge un cookie sicuro per il language switcher"""
    lang = session.get('preferred_language')
    if lang:
        response.set_cookie(
            'preferred_language', 
            lang, 
            httponly=True,  # Non accessibile via JavaScript per sicurezza
            secure=request.is_secure,  # Solo HTTPS in produzione
            samesite='Lax',  # Protegge contro CSRF
            max_age=60*60*24*365  # 1 anno
        )
    return response

# Registra i blueprint per le varie route dell'applicazione
@app.before_serving
async def register_blueprints():
    # Importa i moduli blueprint qui (dopo inizializzazione) per evitare
    # problemi di importazione circolare
    from web.routes.admin import init_admin_bp
    from web.routes.dashboard import dashboard_blueprint
    from web.routes.timer import timer
    from web.routes.gdpr import init_gdpr_bp
    
    # Registra i blueprint
    app.register_blueprint(dashboard_blueprint)
    app.register_blueprint(timer)
    
    # Inizializza blueprint che richiedono configurazione avanzata
    init_admin_bp(app)
    init_gdpr_bp(app)
    
    logger.info("Blueprint registrati con successo")

# Startup tasks
@app.before_serving
async def startup():
    # Crea il pool di connessioni al database
    await setup_db_pool()
    
    # Imposta la connessione al bot
    await setup_bot_client()
    
    # Connettiti a Redis per caching avanzato
    await setup_redis_client()
    
    logger.info(f"M4Bot Web v{APP_VERSION} avviato con successo")

# Cleanup tasks
@app.after_serving
async def cleanup():
    # Chiudi la connessione al bot
    if bot_client:
        await bot_client.close()
    
    # Chiudi la connessione Redis
    if redis_client:
        await redis_client.close()
    
    logger.info("Risorse liberate con successo")

# Le route dell'applicazione rimangono le stesse...
# ... per brevità, non includo nuovamente tutte le route ...

# Se eseguito direttamente (non come modulo)
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
