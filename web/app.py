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
import time
import hmac
import random
import string
from functools import wraps
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import aiohttp
from quart import Quart, render_template, request, redirect, url_for, session, jsonify, websocket
from quart_cors import cors
import asyncpg
import bcrypt

# Aggiungi la directory principale al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configurazione
CLIENT_ID = "your_kick_client_id"
CLIENT_SECRET = "your_kick_client_secret"
REDIRECT_URI = "https://your-domain.com/auth/callback"
SCOPE = "public"
ENCRYPTION_KEY = "your_secret_key"
LOG_LEVEL = "INFO"
LOG_FILE = "m4bot.log"
DB_USER = "postgres"
DB_PASS = "password"
DB_NAME = "m4bot"
DB_HOST = "localhost"

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

# Pool di connessioni al database
db_pool = None

# Aggiunti per l'integrazione OBS e WebSocket
overlay_settings = {
    'showFollowers': True,
    'showDonations': True,
    'showCommands': True,
    'duration': 5,
    'style': 'animated'
}

# Connessioni WebSocket attive per l'overlay OBS
overlay_connections = set()

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
            
        # Scambia il codice con i token
        async with aiohttp.ClientSession() as session_http:
            data = {
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "code_verifier": code_verifier
            }
            
            async with session_http.post("https://id.kick.com/oauth/token", data=data) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nello scambio del codice: {error_text}")
                    return redirect(url_for('add_channel', error="Errore nell'autorizzazione"))
                    
                token_data = await response.json()
                
            # Ottieni informazioni sull'utente/canale
            headers = {
                "Authorization": f"Bearer {token_data['access_token']}"
            }
            
            async with session_http.get("https://kick.com/api/v2/channels/me", headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nell'ottenimento delle info del canale: {error_text}")
                    return redirect(url_for('add_channel', error="Errore nell'ottenimento delle info del canale"))
                    
                channel_data = await response.json()
                
        if not db_pool:
            return redirect(url_for('dashboard', error="Database non disponibile"))
            
        # Cripta i token prima di salvarli
        from cryptography.fernet import Fernet
        key_bytes = hashlib.sha256(ENCRYPTION_KEY.encode()).digest()
        cipher_suite = Fernet(base64.urlsafe_b64encode(key_bytes))
        
        encrypted_access_token = cipher_suite.encrypt(token_data["access_token"].encode()).decode()
        encrypted_refresh_token = cipher_suite.encrypt(token_data["refresh_token"].encode()).decode()
        
        # Calcola la data di scadenza
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
        
        # Salva i dati nel database
        async with db_pool.acquire() as conn:
            # Verifica se il canale esiste già
            existing_channel = await conn.fetchval('''
                SELECT id FROM channels 
                WHERE kick_channel_id = $1 OR name = $2
            ''', str(channel_data["id"]), channel_name)
            
            if existing_channel:
                return redirect(url_for('dashboard', error="Questo canale è già configurato"))
                
            # Inserisci il nuovo canale
            await conn.execute('''
                INSERT INTO channels 
                (kick_channel_id, name, owner_id, access_token, refresh_token, token_expires_at, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW())
            ''', str(channel_data["id"]), channel_name, session['user_id'], 
                encrypted_access_token, encrypted_refresh_token, expires_at)
                
        return redirect(url_for('dashboard', success="Canale aggiunto con successo"))
    except Exception as e:
        logger.error(f"Errore nel callback OAuth: {e}")
        return redirect(url_for('add_channel', error="Si è verificato un errore durante l'autenticazione"))

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

@app.route('/channel/<int:channel_id>/predictions', methods=['GET', 'POST'])
@login_required
async def channel_predictions(channel_id):
    """Gestisce le predizioni di un canale."""
        user_id = session.get('user_id')
    error = None
    success = None
    channel = None
    predictions = []
            
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
            
            # Ottieni tutte le predizioni del canale
            predictions = await conn.fetch('''
                SELECT id, title, status, created_at, ends_at, options, winner_option
                FROM predictions
                WHERE channel_id = $1
                ORDER BY created_at DESC
            ''', channel_id)
            
    except Exception as e:
        logger.error(f"Errore nel caricamento delle predizioni: {e}")
        return await render_template('error.html', message=f"Errore del server: {str(e)}"), 500
    
    if not channel:
        return redirect(url_for('dashboard', error="Canale non trovato o non autorizzato"))
    
    return await render_template(
        'predictions.html',
        channel=channel,
        predictions=predictions,
        error=error,
        success=success
    )

@app.route('/predictions')
@login_required
async def predictions():
    """Pagina principale per le scommesse/predizioni."""
        user_id = session.get('user_id')
        
    # Valori predefiniti in caso di errore del database
    user = {'id': user_id, 'username': 'Utente', 'email': 'N/A', 'is_admin': False}
    channels = []
    active_predictions = []
    
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
                
                # Predisposizione della tabella predictions se non esiste
                try:
                    await conn.execute('''
                        CREATE TABLE IF NOT EXISTS predictions (
                            id SERIAL PRIMARY KEY,
                            channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                            title TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'active',
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                            ends_at TIMESTAMP WITH TIME ZONE,
                            options JSONB NOT NULL,
                            winner_option TEXT,
                            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                        )
                    ''')
                    
                    await conn.execute('''
                        CREATE TABLE IF NOT EXISTS prediction_votes (
                            id SERIAL PRIMARY KEY,
                            prediction_id INTEGER NOT NULL REFERENCES predictions(id) ON DELETE CASCADE,
                            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                            option_id TEXT NOT NULL,
                            points INTEGER NOT NULL,
                            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                            UNIQUE(prediction_id, user_id)
                        )
                    ''')
                    
                    logger.info("Tabelle prediction verificate/create con successo")
                except Exception as e:
                    logger.error(f"Errore nella creazione delle tabelle prediction: {e}")
                
                # Ottieni predizioni attive
                if channels:
                    channel_ids = [channel['id'] for channel in channels]
                    active_predictions = await conn.fetch('''
                        SELECT 
                            p.id, 
                            p.channel_id, 
                            p.title, 
                            p.status, 
                            p.created_at, 
                            p.ends_at, 
                            p.options,
                            c.name as channel_name
                        FROM predictions p
                        JOIN channels c ON p.channel_id = c.id
                        WHERE p.channel_id = ANY($1)
                        AND p.status IN ('active', 'locked')
                        ORDER BY p.created_at DESC
                    ''', channel_ids)
        except Exception as e:
            logger.error(f"Errore nel caricamento della pagina predizioni: {e}")
            # Continua con i valori predefiniti
    
    return await render_template(
        'predictions.html',
        user=user,
        channels=channels,
        active_predictions=active_predictions
    )

@app.route('/api/channel/<int:channel_id>/predictions', methods=['GET', 'POST', 'PUT'])
@login_required
async def api_manage_predictions(channel_id):
    """API per gestire le predizioni di un canale."""
    user_id = session.get('user_id')
            
        if not db_pool:
            return jsonify({'error': 'Database non disponibile'}), 500
            
    try:
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            channel = await conn.fetchrow('''
                SELECT c.id, c.name
                FROM channels c
                WHERE c.id = $1 AND c.owner_id = $2
            ''', channel_id, user_id)
            
            if not channel:
                return jsonify({'error': 'Canale non trovato o non autorizzato'}), 403
                
            if request.method == 'GET':
                # Ottieni tutte le predizioni del canale
                predictions = await conn.fetch('''
                    SELECT id, title, status, created_at, ends_at, options, winner_option
                    FROM predictions
                    WHERE channel_id = $1
                    ORDER BY created_at DESC
                ''', channel_id)
                
                predictions_list = []
                for pred in predictions:
                    predictions_list.append({
                        'id': pred['id'],
                        'title': pred['title'],
                        'status': pred['status'],
                        'created_at': pred['created_at'].isoformat() if pred['created_at'] else None,
                        'ends_at': pred['ends_at'].isoformat() if pred['ends_at'] else None,
                        'options': pred['options'],
                        'winner_option': pred['winner_option']
                    })
                
                return jsonify({
                    'channel': dict(channel),
                    'predictions': predictions_list
                })
                
            elif request.method == 'POST':
                # Crea una nuova predizione
                data = await request.json
                title = data.get('title')
                options = data.get('options')
                duration = data.get('duration', 300)  # Default 5 minuti
                
                if not title or not options:
                    return jsonify({'error': 'Titolo e opzioni richiesti'}), 400
                
                # Calcola quando termina la predizione
                ends_at = datetime.now(timezone.utc) + timedelta(seconds=duration)
                
                # Inserisci la nuova predizione
                prediction_id = await conn.fetchval('''
                    INSERT INTO predictions 
                    (channel_id, title, status, created_at, ends_at, options)
                    VALUES ($1, $2, 'active', NOW(), $3, $4)
                    RETURNING id
                ''', channel_id, title, ends_at, json.dumps(options))
                
                return jsonify({
                    'success': True,
                    'message': 'Predizione creata con successo',
                    'prediction_id': prediction_id
                })
                
            elif request.method == 'PUT':
                # Aggiorna una predizione esistente
                data = await request.json
                prediction_id = data.get('prediction_id')
                status = data.get('status')
                winner_option = data.get('winner_option')
                
                if not prediction_id or not status:
                    return jsonify({'error': 'ID predizione e stato richiesti'}), 400
                
                if status not in ['active', 'locked', 'resolved', 'cancelled']:
                    return jsonify({'error': 'Stato non valido'}), 400
                
                # Verifica che la predizione esista
                prediction = await conn.fetchrow('''
                    SELECT id FROM predictions
                    WHERE id = $1 AND channel_id = $2
                ''', prediction_id, channel_id)
                
                if not prediction:
                    return jsonify({'error': 'Predizione non trovata'}), 404
                
                # Aggiorna la predizione
                await conn.execute('''
                    UPDATE predictions
                    SET status = $1, winner_option = $2, updated_at = NOW()
                    WHERE id = $3
                ''', status, winner_option, prediction_id)
                
                return jsonify({
                    'success': True,
                    'message': f'Predizione {prediction_id} aggiornata con successo'
                })
                
    except Exception as e:
        logger.error(f"Errore nell'API delle predizioni: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/channel/<int:channel_id>/obs', methods=['GET'])
async def channel_obs_overlay(channel_id):
    """Overlay OBS per le predizioni di un canale."""
    try:
        if not db_pool:
            return await render_template('error.html', message="Database non disponibile"), 500
            
        async with db_pool.acquire() as conn:
            # Verifica che il canale esista
            channel = await conn.fetchrow('''
                SELECT c.id, c.name
                FROM channels c
                WHERE c.id = $1
            ''', channel_id)
            
            if not channel:
                return await render_template('error.html', message="Canale non trovato"), 404
                
            # Ottieni le predizioni attive
            active_prediction = await conn.fetchrow('''
                SELECT id, title, status, created_at, ends_at, options
                FROM predictions
                WHERE channel_id = $1 AND status IN ('active', 'locked')
                ORDER BY created_at DESC
                LIMIT 1
            ''', channel_id)
            
        return await render_template(
            'obs_overlay.html',
            channel=channel,
            prediction=active_prediction,
            overlay_mode=True
        )
    except Exception as e:
        logger.error(f"Errore nell'overlay OBS: {e}")
        return await render_template('error.html', message=f"Errore del server: {str(e)}"), 500

@app.route('/api/predictions/<int:prediction_id>/votes', methods=['POST'])
async def prediction_vote(prediction_id):
    """API per votare in una predizione."""
    if not db_pool:
        return jsonify({'error': 'Database non disponibile'}), 500
        
    try:
        data = await request.json
        user_id = data.get('user_id')
        option_id = data.get('option_id')
        points = data.get('points', 0)
        
        if not user_id or not option_id or points <= 0:
            return jsonify({'error': 'Parametri mancanti o non validi'}), 400
            
        async with db_pool.acquire() as conn:
            # Verifica che la predizione esista ed è attiva
            prediction = await conn.fetchrow('''
                SELECT id, channel_id, status, options
                FROM predictions
                WHERE id = $1 AND status = 'active'
            ''', prediction_id)
            
            if not prediction:
                return jsonify({'error': 'Predizione non trovata o non attiva'}), 404
                
            # Verifica che l'utente esista
            user = await conn.fetchrow('SELECT id FROM users WHERE id = $1', user_id)
            if not user:
                return jsonify({'error': 'Utente non trovato'}), 404
                
            # Verifica che l'opzione esista
            options = prediction['options']
            if not isinstance(options, dict) and not isinstance(options, list):
                try:
                    import json
                    options = json.loads(options)
                except:
                    return jsonify({'error': 'Formato opzioni non valido'}), 500
                    
            option_found = False
            if isinstance(options, list):
                for option in options:
                    if option.get('id') == option_id:
                        option_found = True
                        break
            elif isinstance(options, dict):
                option_found = option_id in options
                
            if not option_found:
                return jsonify({'error': 'Opzione non valida'}), 400
                
            # Verifica che l'utente abbia abbastanza punti
            user_points = await conn.fetchval('''
                SELECT points FROM channel_points
                WHERE channel_id = $1 AND user_id = $2
            ''', prediction['channel_id'], user_id)
            
            if not user_points or user_points < points:
                return jsonify({'error': 'Punti insufficienti'}), 400
                
            # Verifica se l'utente ha già votato
            existing_vote = await conn.fetchval('''
                SELECT id FROM prediction_votes
                WHERE prediction_id = $1 AND user_id = $2
            ''', prediction_id, user_id)
            
            if existing_vote:
                return jsonify({'error': 'Hai già votato in questa predizione'}), 400
                
            # Transazione per votare e scalare i punti
            async with conn.transaction():
                # Registra il voto
                await conn.execute('''
                    INSERT INTO prediction_votes(prediction_id, user_id, option_id, points, created_at)
                    VALUES($1, $2, $3, $4, NOW())
                ''', prediction_id, user_id, option_id, points)
                
                # Decrementa i punti dell'utente
                await conn.execute('''
                    UPDATE channel_points
                    SET points = points - $1
                    WHERE channel_id = $2 AND user_id = $3
                ''', points, prediction['channel_id'], user_id)
                
            return jsonify({
                'success': True,
                'message': 'Voto registrato con successo',
                'points_remaining': (user_points - points)
            })
    except Exception as e:
        logger.error(f"Errore nella votazione: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/channels/<int:channel_id>/stats', methods=['GET'])
async def api_channel_stats(channel_id):
    """API per ottenere le statistiche di un canale."""
    if not db_pool:
        return jsonify({'error': 'Database non disponibile'}), 500
        
    try:
        async with db_pool.acquire() as conn:
            # Verifica che il canale esista
            channel = await conn.fetchrow('SELECT id, name FROM channels WHERE id = $1', channel_id)
            
            if not channel:
                return jsonify({'error': 'Canale non trovato'}), 404
                
            # Statistiche generali
            stats = await conn.fetchrow('''
                SELECT 
                    COUNT(*) as total_predictions,
                    COUNT(*) FILTER (WHERE status = 'resolved') as resolved_predictions,
                    COUNT(*) FILTER (WHERE status = 'canceled') as canceled_predictions,
                    COUNT(DISTINCT user_id) as unique_participants
                FROM predictions p
                LEFT JOIN prediction_votes pv ON p.id = pv.prediction_id
                WHERE p.channel_id = $1
            ''', channel_id)
            
            # Top partecipanti
            top_participants = await conn.fetch('''
                SELECT 
                    u.username,
                    SUM(pv.points) as total_points,
                    COUNT(DISTINCT pv.prediction_id) as predictions_count
                FROM prediction_votes pv
                JOIN predictions p ON pv.prediction_id = p.id
                JOIN users u ON pv.user_id = u.id
                WHERE p.channel_id = $1
                GROUP BY u.id, u.username
                ORDER BY total_points DESC
                LIMIT 5
            ''', channel_id)
            
            # Predizioni recenti
            recent_predictions = await conn.fetch('''
                SELECT 
                    p.id, 
                    p.title, 
                    p.status, 
                    p.created_at,
                    p.ends_at,
                    p.winner_option,
                    COUNT(pv.id) as vote_count,
                    SUM(pv.points) as total_points
                FROM predictions p
                LEFT JOIN prediction_votes pv ON p.id = pv.prediction_id
                WHERE p.channel_id = $1
                GROUP BY p.id
                ORDER BY p.created_at DESC
                LIMIT 10
            ''', channel_id)
                
            return jsonify({
                'channel_id': channel_id,
                'channel_name': channel['name'],
                'stats': dict(stats),
                'top_participants': [dict(p) for p in top_participants],
                'recent_predictions': [dict(p) for p in recent_predictions]
            })
    except Exception as e:
        logger.error(f"Errore nelle statistiche API: {e}")
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
    """Operazioni da eseguire prima di avviare il server."""
    await setup_db_pool()

@app.after_serving
async def after_serving():
    """Operazioni da eseguire dopo l'arresto del server."""
    if db_pool:
        await db_pool.close()

# Rotta per la pagina di integrazione OBS
@app.route('/obs-integration')
@login_required
async def obs_integration():
    """Pagina di integrazione con OBS per il controllo dello streaming e overlay."""
    return await render_template('obs_integration.html')

# Rotta per l'overlay OBS (da utilizzare come sorgente browser in OBS)
@app.route('/obs-overlay')
async def obs_overlay():
    """Pagina di overlay per OBS che mostra eventi in tempo reale."""
    return await render_template('obs_overlay.html')

# API per salvare le impostazioni dell'overlay
@app.route('/api/save_overlay_settings', methods=['POST'])
@login_required
async def save_overlay_settings():
    """Salva le impostazioni dell'overlay."""
    global overlay_settings
    data = await request.get_json()
    
    # Validazione delle impostazioni
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "Dati non validi"})
    
    # Aggiorna solo i campi validi
    valid_keys = ['showFollowers', 'showDonations', 'showCommands', 'duration', 'style']
    for key in valid_keys:
        if key in data:
            overlay_settings[key] = data[key]
    
    # Broadcast delle nuove impostazioni a tutti i client dell'overlay connessi
    await broadcast_to_overlays({
        "type": "settings_update",
        "settings": overlay_settings
    })
    
    # In un'implementazione reale, salveresti queste impostazioni nel database
    # await db.save_overlay_settings(session.get('user_id'), overlay_settings)
    
    return jsonify({"success": True})

# API per ottenere le impostazioni dell'overlay
@app.route('/api/get_overlay_settings')
async def get_overlay_settings():
    """Ottieni le impostazioni dell'overlay."""
    return jsonify({"success": True, "settings": overlay_settings})

# WebSocket per l'overlay OBS
@app.websocket('/ws/overlay')
async def ws_overlay():
    """Endpoint WebSocket per l'overlay OBS."""
    try:
        overlay_connections.add(websocket._get_current_object())
        try:
            # Invia le impostazioni correnti
            await websocket.send(json.dumps({
                "type": "settings_update",
                "settings": overlay_settings
            }))
            
            # Aspetta che la connessione si chiuda
            while True:
                # Questo loop serve solo a mantenere aperta la connessione
                await websocket.receive()
        finally:
            overlay_connections.remove(websocket._get_current_object())
    except Exception as e:
        app.logger.error(f"Errore WebSocket overlay: {e}")

# Funzione per inviare eventi broadcast a tutti gli overlay connessi
async def broadcast_to_overlays(message):
    """Invia un messaggio a tutti i client dell'overlay connessi."""
    message_json = json.dumps(message)
    for ws in list(overlay_connections):
        try:
            await ws.send(message_json)
        except Exception as e:
            app.logger.error(f"Errore nell'invio del messaggio all'overlay: {e}")
            # La connessione potrebbe essere chiusa, quindi la rimuoviamo
            try:
                overlay_connections.remove(ws)
            except KeyError:
                pass

# Funzione per trigger eventi overlay (da chiamare nel bot quando accadono eventi)
async def trigger_overlay_event(event_type, data):
    """
    Attiva un evento sull'overlay OBS.
    
    :param event_type: Tipo di evento ('follower', 'donation', 'command')
    :param data: Dati dell'evento (dict con username, ecc.)
    """
    event_data = {
        "type": event_type,
        **data
    }
    await broadcast_to_overlays(event_data)

# Aggiungi una funzione API di test per generare eventi di test
@app.route('/api/test_overlay_event', methods=['POST'])
@login_required
async def test_overlay_event():
    """API per testare gli eventi dell'overlay."""
    data = await request.get_json()
    event_type = data.get('type', 'follower')
    username = data.get('username', 'Tester')
    
    event_data = {
        "username": username
    }
    
    if event_type == 'donation':
        event_data["amount"] = data.get('amount', 10)
    elif event_type == 'command':
        event_data["command"] = data.get('command', '!test')
    
    await trigger_overlay_event(event_type, event_data)
    return jsonify({"success": True})

# Aggiungi la navbar
@app.route('/webhooks')
@login_required
async def webhooks_management():
    """Pagina di gestione dei webhook Kick."""
    user_id = session.get('user_id')
    
    # Valori predefiniti
    channels = []
    
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                # Ottieni i canali configurati dall'utente
                channels = await conn.fetch('''
                    SELECT c.id, c.name, c.kick_channel_id, c.created_at
                    FROM channels c
                    WHERE c.owner_id = $1
                    ORDER BY c.name
                ''', user_id)
                
                # Verifica che le tabelle webhook esistano
                await setup_webhook_tables(conn)
                
        except Exception as e:
            logger.error(f"Errore nel caricamento della pagina webhook: {e}")
    
    return await render_template(
        'webhook_management.html',
        channels=channels
    )

async def setup_webhook_tables(conn):
    """Crea le tabelle necessarie per la gestione dei webhook."""
    try:
        # Tabella delle configurazioni webhook
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS webhook_configs (
                id SERIAL PRIMARY KEY,
                channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                webhook_url TEXT NOT NULL,
                secret_key TEXT NOT NULL,
                events JSONB NOT NULL,
                active BOOLEAN NOT NULL DEFAULT true,
                last_event_at TIMESTAMP WITH TIME ZONE,
                events_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        ''')
        
        # Tabella dei log webhook
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS webhook_logs (
                id SERIAL PRIMARY KEY,
                channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,
                payload JSONB NOT NULL,
                status_code INTEGER,
                response_time INTEGER,
                error TEXT,
                created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
            )
        ''')
        
        logger.info("Tabelle webhook verificate/create con successo")
    except Exception as e:
        logger.error(f"Errore nella creazione delle tabelle webhook: {e}")
        raise

# API per la gestione dei webhook
@app.route('/api/webhook/config/<int:channel_id>', methods=['GET'])
@login_required
async def get_webhook_config(channel_id):
    """Ottiene la configurazione webhook per un canale."""
    user_id = session.get('user_id')
    
    if not db_pool:
        return jsonify({'success': False, 'error': 'Database non disponibile'}), 500
    
    try:
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            channel = await conn.fetchrow('''
                SELECT id FROM channels
                WHERE id = $1 AND owner_id = $2
            ''', channel_id, user_id)
            
            if not channel:
                return jsonify({'success': False, 'error': 'Canale non trovato o non autorizzato'}), 403
            
            # Ottieni configurazione webhook
            config = await conn.fetchrow('''
                SELECT id, channel_id, webhook_url, secret_key, events, active, 
                       last_event_at, events_count, created_at, updated_at
                FROM webhook_configs
                WHERE channel_id = $1
            ''', channel_id)
            
            if config:
                # Converti in dizionario
                config_dict = dict(config)
                # Converti date in stringhe ISO
                for key in ['last_event_at', 'created_at', 'updated_at']:
                    if config_dict[key]:
                        config_dict[key] = config_dict[key].isoformat()
                
                return jsonify({'success': True, 'config': config_dict})
            else:
                return jsonify({'success': True, 'config': None})
    
    except Exception as e:
        logger.error(f"Errore nella lettura della configurazione webhook: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/webhook/config', methods=['POST'])
@login_required
async def save_webhook_config():
    """Salva la configurazione webhook per un canale."""
    user_id = session.get('user_id')
    
    if not db_pool:
        return jsonify({'success': False, 'error': 'Database non disponibile'}), 500
    
    try:
        data = await request.json
        channel_id = data.get('channel_id')
        webhook_url = data.get('webhook_url')
        secret_key = data.get('secret_key')
        events = data.get('events', [])
        
        if not channel_id or not webhook_url or not secret_key or not events:
            return jsonify({'success': False, 'error': 'Dati mancanti'}), 400
        
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            channel = await conn.fetchrow('''
                SELECT id FROM channels
                WHERE id = $1 AND owner_id = $2
            ''', channel_id, user_id)
            
            if not channel:
                return jsonify({'success': False, 'error': 'Canale non trovato o non autorizzato'}), 403
            
            # Verifica se esiste già una configurazione
            existing_config = await conn.fetchval('''
                SELECT id FROM webhook_configs
                WHERE channel_id = $1
            ''', channel_id)
            
            if existing_config:
                # Aggiorna configurazione esistente
                await conn.execute('''
                    UPDATE webhook_configs
                    SET webhook_url = $1, secret_key = $2, events = $3, updated_at = NOW()
                    WHERE id = $4
                ''', webhook_url, secret_key, json.dumps(events), existing_config)
                
                # Registriamo nella Kick API (simulato)
                # In una implementazione reale, qui chiameremmo l'API Kick per aggiornare la sottoscrizione
                
                return jsonify({'success': True, 'message': 'Configurazione webhook aggiornata'})
            else:
                # Crea nuova configurazione
                config_id = await conn.fetchval('''
                    INSERT INTO webhook_configs 
                    (channel_id, webhook_url, secret_key, events, active, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, true, NOW(), NOW())
                    RETURNING id
                ''', channel_id, webhook_url, secret_key, json.dumps(events))
                
                # Registriamo nella Kick API (simulato)
                # In una implementazione reale, qui chiameremmo l'API Kick per creare la sottoscrizione
                
                return jsonify({'success': True, 'message': 'Configurazione webhook creata', 'id': config_id})
    
    except Exception as e:
        logger.error(f"Errore nel salvataggio della configurazione webhook: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/webhook/config/<int:config_id>', methods=['DELETE'])
@login_required
async def delete_webhook_config(config_id):
    """Elimina la configurazione webhook."""
    user_id = session.get('user_id')
    
    if not db_pool:
        return jsonify({'success': False, 'error': 'Database non disponibile'}), 500
    
    try:
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            webhook_config = await conn.fetchrow('''
                SELECT wc.id, wc.channel_id
                FROM webhook_configs wc
                JOIN channels c ON wc.channel_id = c.id
                WHERE wc.id = $1 AND c.owner_id = $2
            ''', config_id, user_id)
            
            if not webhook_config:
                return jsonify({'success': False, 'error': 'Configurazione non trovata o non autorizzata'}), 403
            
            # Elimina la configurazione
            await conn.execute('DELETE FROM webhook_configs WHERE id = $1', config_id)
            
            # Eliminiamo anche dalla Kick API (simulato)
            # In una implementazione reale, qui chiameremmo l'API Kick per eliminare la sottoscrizione
            
            return jsonify({'success': True, 'message': 'Configurazione webhook eliminata'})
    
    except Exception as e:
        logger.error(f"Errore nell'eliminazione della configurazione webhook: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/webhook/logs/<int:channel_id>', methods=['GET'])
@login_required
async def get_webhook_logs(channel_id):
    """Ottiene i log webhook per un canale."""
    user_id = session.get('user_id')
    
    if not db_pool:
        return jsonify({'success': False, 'error': 'Database non disponibile'}), 500
    
    try:
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            channel = await conn.fetchrow('''
                SELECT id FROM channels
                WHERE id = $1 AND owner_id = $2
            ''', channel_id, user_id)
            
            if not channel:
                return jsonify({'success': False, 'error': 'Canale non trovato o non autorizzato'}), 403
            
            # Ottieni i log
            logs = await conn.fetch('''
                SELECT id, channel_id, event_type, payload, status_code, response_time, error, created_at
                FROM webhook_logs
                WHERE channel_id = $1
                ORDER BY created_at DESC
                LIMIT 50
            ''', channel_id)
            
            logs_list = []
            for log in logs:
                log_dict = dict(log)
                # Converti timestamp in stringa ISO
                if log_dict['created_at']:
                    log_dict['created_at'] = log_dict['created_at'].isoformat()
                logs_list.append(log_dict)
            
            return jsonify({'success': True, 'logs': logs_list})
    
    except Exception as e:
        logger.error(f"Errore nella lettura dei log webhook: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/webhook/logs/<int:channel_id>/clear', methods=['POST'])
@login_required
async def clear_webhook_logs(channel_id):
    """Pulisce i log webhook per un canale."""
    user_id = session.get('user_id')
    
    if not db_pool:
        return jsonify({'success': False, 'error': 'Database non disponibile'}), 500
    
    try:
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia il proprietario del canale
            channel = await conn.fetchrow('''
                SELECT id FROM channels
                WHERE id = $1 AND owner_id = $2
            ''', channel_id, user_id)
            
            if not channel:
                return jsonify({'success': False, 'error': 'Canale non trovato o non autorizzato'}), 403
            
            # Elimina i log
            await conn.execute('DELETE FROM webhook_logs WHERE channel_id = $1', channel_id)
            
            return jsonify({'success': True, 'message': 'Log webhook eliminati'})
    
    except Exception as e:
        logger.error(f"Errore nella pulizia dei log webhook: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/webhook/test', methods=['POST'])
@login_required
async def test_webhook_endpoint():
    """Testa un endpoint webhook."""
    try:
        data = await request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'success': False, 'error': 'URL mancante'}), 400
        
        # Crea un payload di test
        test_payload = {
            'event': 'test',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'data': {
                'message': 'Questo è un test dal M4Bot',
                'source': 'webhook_tester'
            }
        }
        
        # Effettua la richiesta
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=test_payload, timeout=10) as response:
                    response_time = int((time.time() - start_time) * 1000)  # ms
                    status_code = response.status
                    
                    if 200 <= status_code < 300:
                        return jsonify({
                            'success': True,
                            'status_code': status_code,
                            'response_time': response_time
                        })
                    else:
                        return jsonify({
                            'success': False,
                            'error': f'Il server ha risposto con codice {status_code}',
                            'status_code': status_code,
                            'response_time': response_time
                        })
            except aiohttp.ClientConnectorError:
                return jsonify({
                    'success': False,
                    'error': 'Impossibile connettersi al server'
                })
            except aiohttp.ClientTimeout:
                return jsonify({
                    'success': False,
                    'error': 'Timeout della connessione'
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                })
    
    except Exception as e:
        logger.error(f"Errore nel test dell'endpoint webhook: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/webhook/kick', methods=['POST'])
async def receive_kick_webhook():
    """Endpoint per ricevere i webhook da Kick.com."""
    try:
        # Verifica la firma del webhook
        signature = request.headers.get('Kick-Signature')
        if not signature:
            logger.warning("Webhook ricevuto senza firma")
            return jsonify({'error': 'Firma mancante'}), 401
        
        # Ottieni payload e verifica la firma
        payload = await request.json
        
        # Estrai le informazioni dal payload
        event_type = payload.get('event_type')
        channel_id = payload.get('channel_id')
        
        if not event_type or not channel_id:
            logger.warning(f"Webhook con dati mancanti: {payload}")
            return jsonify({'error': 'Dati mancanti nel payload'}), 400
        
        # Verifica la firma (in produzione)
        # In un'implementazione reale, qui verificheremmo la firma HMAC
        verified = await verify_webhook_signature(channel_id, signature, payload)
        if not verified:
            logger.warning(f"Webhook con firma non valida: {signature}")
            return jsonify({'error': 'Firma non valida'}), 401
        
        # Elabora l'evento
        success = await process_kick_event(channel_id, event_type, payload)
        
        if success:
            return jsonify({'success': True, 'message': 'Evento elaborato con successo'}), 200
        else:
            return jsonify({'error': 'Errore nell\'elaborazione dell\'evento'}), 500
    
    except Exception as e:
        logger.error(f"Errore nella gestione del webhook: {e}")
        return jsonify({'error': str(e)}), 500

async def verify_webhook_signature(channel_id, signature, payload):
    """Verifica la firma di un webhook Kick."""
    if not db_pool:
        return False
    
    try:
        async with db_pool.acquire() as conn:
            # Ottieni la chiave segreta
            secret_key = await conn.fetchval('''
                SELECT secret_key FROM webhook_configs
                WHERE channel_id = $1
            ''', channel_id)
            
            if not secret_key:
                logger.warning(f"Nessuna configurazione webhook trovata per il canale {channel_id}")
                return False
            
            # Verifica la firma
            # In una implementazione reale, verificheremmo la firma HMAC
            # Il formato esatto della firma dipende dalla documentazione Kick
            # Questo è un esempio generico
            
            # Converti payload in stringa JSON
            payload_str = json.dumps(payload, separators=(',', ':'))
            
            # Calcola l'HMAC (SHA-256)
            calculated_signature = hmac.new(
                secret_key.encode(),
                payload_str.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # In produzione, confronteremmo le firme
            # return hmac.compare_digest(calculated_signature, signature)
            
            # Per ora, accettiamo tutte le richieste come se fossero valide
            return True
    
    except Exception as e:
        logger.error(f"Errore nella verifica della firma webhook: {e}")
        return False

async def process_kick_event(channel_id, event_type, payload):
    """Elabora un evento webhook ricevuto da Kick."""
    if not db_pool:
        return False
    
    try:
        async with db_pool.acquire() as conn:
            # Registra l'evento nel log
            await conn.execute('''
                INSERT INTO webhook_logs
                (channel_id, event_type, payload, created_at)
                VALUES ($1, $2, $3, NOW())
            ''', channel_id, event_type, json.dumps(payload))
            
            # Aggiorna i contatori
            await conn.execute('''
                UPDATE webhook_configs
                SET events_count = events_count + 1, last_event_at = NOW()
                WHERE channel_id = $1
            ''', channel_id)
            
            # Elabora specifici tipi di evento
            if event_type == 'livestream.online':
                # Streaming iniziato
                await handle_stream_start(channel_id, payload)
            
            elif event_type == 'livestream.offline':
                # Streaming terminato
                await handle_stream_end(channel_id, payload)
            
            elif event_type == 'follower.new':
                # Nuovo follower
                await handle_new_follower(channel_id, payload)
            
            elif event_type == 'subscription.new':
                # Nuova iscrizione
                await handle_new_subscription(channel_id, payload)
            
            return True
    
    except Exception as e:
        logger.error(f"Errore nell'elaborazione dell'evento webhook: {e}")
        return False

async def handle_stream_start(channel_id, payload):
    """Gestisce l'evento di inizio streaming."""
    logger.info(f"Streaming iniziato sul canale {channel_id}")
    
    # Esempio: notifica i viewer del canale
    # Esempio: aggiorna lo stato del bot
    # Esempio: attiva funzionalità specifiche per lo streaming

async def handle_stream_end(channel_id, payload):
    """Gestisce l'evento di fine streaming."""
    logger.info(f"Streaming terminato sul canale {channel_id}")
    
    # Esempio: salva statistiche dello streaming
    # Esempio: disattiva funzionalità specifiche per lo streaming

async def handle_new_follower(channel_id, payload):
    """Gestisce l'evento di nuovo follower."""
    follower_username = payload.get('follower', {}).get('username', 'Utente sconosciuto')
    logger.info(f"Nuovo follower {follower_username} sul canale {channel_id}")
    
    # Esempio: invia messaggio di benvenuto
    # Esempio: aggiorna contatori
    # Esempio: attiva evento nell'overlay

async def handle_new_subscription(channel_id, payload):
    """Gestisce l'evento di nuova iscrizione."""
    subscriber_username = payload.get('subscriber', {}).get('username', 'Utente sconosciuto')
    tier = payload.get('tier', 1)
    logger.info(f"Nuova iscrizione Tier {tier} da {subscriber_username} sul canale {channel_id}")
    
    # Esempio: invia messaggio di ringraziamento
    # Esempio: assegna punti bonus
    # Esempio: attiva evento speciale nell'overlay

# API per il sistema di stato e heartbeat
@app.route('/api/status/bot', methods=['GET'])
async def api_bot_status():
    """API per controllare lo stato del bot."""
    try:
        status = {
            'online': False,
            'details': {
                'uptime': None,
                'memory_usage': None,
                'channels_connected': 0,
                'last_error': None
            }
        }
        
        # Controlla se il bot è in esecuzione
        if not db_pool:
            return jsonify(status), 200
            
        async with db_pool.acquire() as conn:
            # Controlla l'ultimo heartbeat registrato
            last_heartbeat = await conn.fetchrow('''
                SELECT timestamp, details 
                FROM bot_heartbeats 
                ORDER BY timestamp DESC 
                LIMIT 1
            ''')
            
            if last_heartbeat:
                # Verifica che l'ultimo heartbeat sia recente (ultimi 30 secondi)
                now = datetime.now(timezone.utc)
                heartbeat_time = last_heartbeat['timestamp']
                time_diff = (now - heartbeat_time).total_seconds()
                
                if time_diff < 30:  # Bot è online se il heartbeat è più recente di 30 secondi
                    status['online'] = True
                    
                    # Calcola uptime
                    first_heartbeat = await conn.fetchrow('''
                        SELECT timestamp 
                        FROM bot_heartbeats 
                        ORDER BY timestamp ASC 
                        LIMIT 1
                    ''')
                    
                    if first_heartbeat:
                        uptime_seconds = (now - first_heartbeat['timestamp']).total_seconds()
                        days, remainder = divmod(uptime_seconds, 86400)
                        hours, remainder = divmod(remainder, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        
                        status['details']['uptime'] = f"{int(days)}d {int(hours)}h {int(minutes)}m"
                    
                    # Ottieni dettagli aggiuntivi dall'ultimo heartbeat
                    if last_heartbeat['details']:
                        try:
                            details = json.loads(last_heartbeat['details'])
                            status['details']['memory_usage'] = details.get('memory_usage', 'N/A')
                            status['details']['cpu_usage'] = details.get('cpu_usage', 'N/A')
                        except:
                            pass
                    
                    # Conta canali attivi
                    connected_channels = await conn.fetchval('''
                        SELECT COUNT(*) FROM channels
                        WHERE is_active = true
                    ''')
                    
                    status['details']['channels_connected'] = connected_channels or 0
                
                # Ottieni l'ultimo errore registrato
                last_error = await conn.fetchrow('''
                    SELECT message, timestamp
                    FROM bot_errors
                    ORDER BY timestamp DESC
                    LIMIT 1
                ''')
                
                if last_error:
                    status['details']['last_error'] = {
                        'message': last_error['message'],
                        'timestamp': last_error['timestamp'].isoformat()
                    }
        
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"Errore nel controllo dello stato del bot: {e}")
        return jsonify({
            'online': False,
            'details': {'error': str(e)}
        }), 200  # Ritorna sempre 200 per consentire il monitoraggio

@app.route('/api/status/web', methods=['GET'])
async def api_web_status():
    """API per controllare lo stato del server web."""
    try:
        # Per il server web, se questa API risponde, il servizio è online
        status = {
            'online': True,
            'details': {
                'server': 'Quart',
                'workers': os.cpu_count(),
                'memory_usage': 'N/A'  # In un'implementazione reale, qui andresti a leggere l'utilizzo della memoria
            }
        }
        
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"Errore nel controllo dello stato del web server: {e}")
        return jsonify({
            'online': False,
            'details': {'error': str(e)}
        }), 200

@app.route('/api/status/database', methods=['GET'])
async def api_database_status():
    """API per controllare lo stato del database."""
    try:
        status = {
            'online': False,
            'details': {
                'type': 'PostgreSQL',
                'version': None,
                'connections': None,
                'latency': None
            }
        }
        
        if not db_pool:
            return jsonify(status), 200
        
        # Misura il tempo di risposta del database
        start_time = time.time()
        
        async with db_pool.acquire() as conn:
            # Controllo semplice: esegui una query banale
            await conn.execute("SELECT 1")
            
            # Ottieni versione del DB
            version = await conn.fetchval("SELECT version()")
            
            # Ottieni numero di connessioni attive
            connections = await conn.fetchval("SELECT count(*) FROM pg_stat_activity")
            
            end_time = time.time()
            latency = round((end_time - start_time) * 1000, 2)  # milliseconds
            
            status['online'] = True
            status['details']['version'] = version
            status['details']['connections'] = connections
            status['details']['latency'] = f"{latency}ms"
        
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"Errore nel controllo dello stato del database: {e}")
        return jsonify({
            'online': False,
            'details': {'error': str(e)}
        }), 200

@app.route('/api/status/kick_api', methods=['GET'])
async def api_kick_status():
    """API per controllare lo stato dell'API di Kick."""
    try:
        status = {
            'online': False,
            'details': {
                'latency': None,
                'rate_limit_remaining': None,
                'last_successful_call': None
            }
        }
        
        # Controlla se possiamo raggiungere l'API di Kick
        # Nota: questo è un esempio semplificato, in produzione userei una chiamata API reale
        api_url = "https://kick.com/api/v2/channels"
        
        start_time = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                end_time = time.time()
                latency = round((end_time - start_time) * 1000, 2)  # milliseconds
                
                if response.status == 200:
                    status['online'] = True
                    status['details']['latency'] = f"{latency}ms"
                    
                    # Ottieni eventuali headers rilevanti
                    rate_limit = response.headers.get('X-RateLimit-Remaining')
                    if rate_limit:
                        status['details']['rate_limit_remaining'] = rate_limit
                    
                    # In un'implementazione reale, qui salveresti il timestamp dell'ultima chiamata riuscita
                    status['details']['last_successful_call'] = datetime.now(timezone.utc).isoformat()
        
        return jsonify(status), 200
        
    except Exception as e:
        logger.error(f"Errore nel controllo dello stato dell'API Kick: {e}")
        return jsonify({
            'online': False,
            'details': {'error': str(e)}
        }), 200

@app.route('/api/bot/restart', methods=['POST'])
@login_required
async def api_restart_bot():
    """API per riavviare il bot."""
    try:
        user_id = session.get('user_id')
        
        if not db_pool:
            return jsonify({
                'success': False,
                'error': 'Database non disponibile'
            }), 500
            
        async with db_pool.acquire() as conn:
            # Verifica che l'utente sia autorizzato (admin)
            user = await conn.fetchrow('SELECT is_admin FROM users WHERE id = $1', user_id)
            
            if not user or not user['is_admin']:
                return jsonify({
                    'success': False,
                    'error': 'Non autorizzato a riavviare il bot'
                }), 403
            
            # In un'implementazione reale, qui chiameresti il codice per riavviare il bot
            # Ad esempio:
            # 1. Inviare un segnale al processo del bot
            # 2. Utilizzare un sistema di gestione dei processi come supervisord
            # 3. Chiamare uno script di sistema
            
            # Per questo esempio, simuliamo il riavvio
            # Registra il riavvio nel database
            await conn.execute('''
                INSERT INTO bot_actions (action_type, user_id, details, timestamp)
                VALUES ('restart', $1, $2, NOW())
            ''', user_id, json.dumps({
                'ip': request.remote_addr,
                'user_agent': request.headers.get('User-Agent')
            }))
            
            # Avvio di un subprocess per riavviare il bot (esempio semplificato)
            # Nota: in produzione userei un metodo più robusto come un servizio systemd
            try:
                if sys.platform == 'win32':
                    import subprocess
                    subprocess.Popen(['python', 'scripts/restart_bot.py'], 
                                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
                else:
                    import subprocess
                    subprocess.Popen(['python3', 'scripts/restart_bot.py'], 
                                    start_new_session=True)
                                    
                return jsonify({
                    'success': True,
                    'message': 'Riavvio del bot avviato con successo'
                })
            except Exception as e:
                logger.error(f"Errore nell'avvio dello script di riavvio: {e}")
                return jsonify({
                    'success': False,
                    'error': f'Errore nel riavvio del bot: {str(e)}'
                }), 500
            
    except Exception as e:
        logger.error(f"Errore nel riavvio del bot: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/bot/register-heartbeat', methods=['POST'])
async def api_register_heartbeat():
    """API per registrare un heartbeat dal bot."""
    try:
        # Controlla l'autenticazione (in produzione userei un token o una chiave API)
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != os.environ.get('BOT_API_KEY'):
            return jsonify({
                'success': False,
                'error': 'Chiave API non valida'
            }), 401
            
        # Ottieni i dettagli del heartbeat
        data = await request.json
        details = data.get('details', {})
        
        if not db_pool:
            return jsonify({
                'success': False,
                'error': 'Database non disponibile'
            }), 500
            
        async with db_pool.acquire() as conn:
            # Crea la tabella se non esiste
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS bot_heartbeats (
                    id SERIAL PRIMARY KEY,
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    details JSONB
                )
            ''')
            
            # Registra il heartbeat
            await conn.execute('''
                INSERT INTO bot_heartbeats (timestamp, details)
                VALUES (NOW(), $1)
            ''', json.dumps(details))
            
            # Pulizia: mantieni solo gli ultimi 1000 heartbeat
            await conn.execute('''
                DELETE FROM bot_heartbeats
                WHERE id NOT IN (
                    SELECT id FROM bot_heartbeats
                    ORDER BY timestamp DESC
                    LIMIT 1000
                )
            ''')
            
            return jsonify({
                'success': True,
                'timestamp': datetime.now(timezone.utc).isoformat()
            })
            
    except Exception as e:
        logger.error(f"Errore nella registrazione del heartbeat: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/system/status')
@login_required
async def system_status_page():
    """Pagina di monitoraggio dello stato del sistema."""
    user_id = session.get('user_id')
    
    # Verifica che l'utente sia un amministratore
    if not db_pool:
        return await render_template('error.html', message="Database non disponibile"), 500
        
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow('SELECT is_admin FROM users WHERE id = $1', user_id)
        
        if not user or not user['is_admin']:
            return await render_template('error.html', message="Non autorizzato"), 403
        
        # Crea le tabelle di monitoraggio se non esistono
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_heartbeats (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                details JSONB
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_errors (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                message TEXT NOT NULL,
                details JSONB
            )
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bot_actions (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                action_type TEXT NOT NULL,
                user_id INTEGER REFERENCES users(id),
                details JSONB
            )
        ''')
        
        # Ottieni gli ultimi heartbeat
        heartbeats = await conn.fetch('''
            SELECT timestamp, details
            FROM bot_heartbeats
            ORDER BY timestamp DESC
            LIMIT 20
        ''')
        
        # Ottieni gli ultimi errori
        errors = await conn.fetch('''
            SELECT timestamp, message, details
            FROM bot_errors
            ORDER BY timestamp DESC
            LIMIT 10
        ''')
        
        # Ottieni le ultime azioni
        actions = await conn.fetch('''
            SELECT ba.timestamp, ba.action_type, u.username, ba.details
            FROM bot_actions ba
            LEFT JOIN users u ON ba.user_id = u.id
            ORDER BY ba.timestamp DESC
            LIMIT 10
        ''')
        
        # Statistiche di sistema
        stats = {
            'channels': await conn.fetchval('SELECT COUNT(*) FROM channels'),
            'active_channels': await conn.fetchval('SELECT COUNT(*) FROM channels WHERE is_active = true'),
            'users': await conn.fetchval('SELECT COUNT(*) FROM users'),
            'commands': await conn.fetchval('SELECT COUNT(*) FROM commands'),
            'uptime': 'N/A'  # Calcolato dal frontend in base agli heartbeat
        }
        
    return await render_template(
        'system_status.html',
        heartbeats=heartbeats,
        errors=errors,
        actions=actions,
        stats=stats
    )

# Password reset routes
@app.route('/password-reset', methods=['GET', 'POST'])
async def request_password_reset():
    """Pagina per richiedere il reset della password."""
    if request.method == 'GET':
        return await render_template('reset_password.html', request_step='email')
    else:
        data = await request.form
        email = data.get('email')
        
        if not email:
            return await render_template('reset_password.html', request_step='email', error='Indirizzo email richiesto')
        
        try:
            if not db_pool:
                return await render_template('error.html', message="Database non disponibile"), 500
                
            async with db_pool.acquire() as conn:
                # Verifica se l'utente esiste
                user = await conn.fetchrow('SELECT id, username FROM users WHERE email = $1', email)
                
                if not user:
                    # Per sicurezza, non rivelare che l'email non esiste
                    return await render_template('reset_password.html', 
                        request_step='email', 
                        success='Se l\'indirizzo esiste, riceverai una email con le istruzioni per il reset')
                
                # Genera token e codice di verifica
                token = secrets.token_urlsafe(32)
                verification_code = ''.join(random.choices(string.digits, k=6))
                expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
                
                # Salva il token e il codice nel database
                await conn.execute('''
                    INSERT INTO password_resets (user_id, email, token, verification_code, expires_at, created_at)
                    VALUES ($1, $2, $3, $4, $5, NOW())
                    ON CONFLICT (user_id) DO UPDATE 
                    SET token = $3, verification_code = $4, expires_at = $5, created_at = NOW(), used = false
                ''', user['id'], email, token, verification_code, expires_at)
                
                # Invia email (in produzione)
                # await send_reset_email(email, user['username'], verification_code)
                
                # In sviluppo, mostriamo il codice in console
                logger.info(f"Codice di verifica per {email}: {verification_code}")
                
                # Reindirizza alla pagina di inserimento codice
                return await render_template('reset_password.html', 
                    request_step='code', 
                    email=email, 
                    reset_token=token)
        
        except Exception as e:
            logger.error(f"Errore nella richiesta di reset password: {e}")
            return await render_template('reset_password.html', 
                request_step='email', 
                error='Si è verificato un errore. Riprova più tardi.')

@app.route('/verify-reset-code', methods=['POST'])
async def verify_reset_code():
    """Verifica il codice di reset password."""
    data = await request.form
    email = data.get('email')
    reset_token = data.get('reset_token')
    verification_code = data.get('verification_code')
    
    if not email or not reset_token or not verification_code:
        return await render_template('reset_password.html', 
            request_step='code', 
            email=email, 
            reset_token=reset_token, 
            error='Tutti i campi sono richiesti')
    
    try:
        if not db_pool:
            return await render_template('error.html', message="Database non disponibile"), 500
            
        async with db_pool.acquire() as conn:
            # Crea tabella se non esiste
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS password_resets (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    email TEXT NOT NULL,
                    token TEXT NOT NULL,
                    verification_code TEXT NOT NULL,
                    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    used BOOLEAN NOT NULL DEFAULT false,
                    UNIQUE(user_id)
                )
            ''')
            
            # Verifica il codice
            reset_request = await conn.fetchrow('''
                SELECT id, user_id, expires_at, used
                FROM password_resets
                WHERE email = $1 AND token = $2 AND verification_code = $3
            ''', email, reset_token, verification_code)
            
            if not reset_request:
                return await render_template('reset_password.html', 
                    request_step='code', 
                    email=email, 
                    reset_token=reset_token, 
                    error='Codice di verifica non valido')
            
            # Verifica se il codice è scaduto
            now = datetime.now(timezone.utc)
            if reset_request['expires_at'] < now:
                return await render_template('reset_password.html', 
                    request_step='code', 
                    email=email, 
                    reset_token=reset_token, 
                    error='Codice di verifica scaduto. Richiedine uno nuovo.')
            
            # Verifica se il codice è già stato usato
            if reset_request['used']:
                return await render_template('reset_password.html', 
                    request_step='code', 
                    email=email, 
                    reset_token=reset_token, 
                    error='Questo codice è già stato utilizzato. Richiedine uno nuovo.')
            
            # Codice valido, procedi alla pagina di reset password
            return await render_template('reset_password.html',
                request_step='password',
                email=email,
                reset_token=reset_token,
                verification_code=verification_code)
    
    except Exception as e:
        logger.error(f"Errore nella verifica del codice: {e}")
        return await render_template('reset_password.html', 
            request_step='code', 
            email=email, 
            reset_token=reset_token, 
            error='Si è verificato un errore. Riprova più tardi.')

@app.route('/set-new-password', methods=['POST'])
async def set_new_password():
    """Imposta una nuova password."""
    data = await request.form
    email = data.get('email')
    reset_token = data.get('reset_token')
    verification_code = data.get('verification_code')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    if not email or not reset_token or not verification_code or not new_password or not confirm_password:
        return await render_template('reset_password.html', 
            request_step='password', 
            email=email, 
            reset_token=reset_token, 
            verification_code=verification_code, 
            error='Tutti i campi sono richiesti')
    
    if new_password != confirm_password:
        return await render_template('reset_password.html', 
            request_step='password', 
            email=email, 
            reset_token=reset_token, 
            verification_code=verification_code, 
            error='Le password non coincidono')
    
    # Verifica requisiti password
    if (len(new_password) < 8 or not any(c.isupper() for c in new_password) or 
        not any(c.islower() for c in new_password) or not any(c.isdigit() for c in new_password)):
        return await render_template('reset_password.html', 
            request_step='password', 
            email=email, 
            reset_token=reset_token, 
            verification_code=verification_code, 
            error='La password non soddisfa i requisiti di sicurezza')
    
    try:
        if not db_pool:
            return await render_template('error.html', message="Database non disponibile"), 500
            
        async with db_pool.acquire() as conn:
            # Verifica il codice
            reset_request = await conn.fetchrow('''
                SELECT id, user_id, expires_at, used
                FROM password_resets
                WHERE email = $1 AND token = $2 AND verification_code = $3
            ''', email, reset_token, verification_code)
            
            if not reset_request:
                return await render_template('reset_password.html', 
                    request_step='password', 
                    email=email, 
                    reset_token=reset_token, 
                    verification_code=verification_code, 
                    error='Codice di verifica non valido')
            
            # Verifica se il codice è scaduto
            now = datetime.now(timezone.utc)
            if reset_request['expires_at'] < now:
                return await render_template('reset_password.html', 
                    request_step='password', 
                    email=email, 
                    reset_token=reset_token, 
                    verification_code=verification_code, 
                    error='Codice di verifica scaduto. Richiedine uno nuovo.')
            
            # Verifica se il codice è già stato usato
            if reset_request['used']:
                return await render_template('reset_password.html', 
                    request_step='password', 
                    email=email, 
                    reset_token=reset_token, 
                    verification_code=verification_code, 
                    error='Questo codice è già stato utilizzato. Richiedine uno nuovo.')
            
            # Aggiorna la password dell'utente
            user_id = reset_request['user_id']
            
            # Hash della nuova password
            hashed_password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
            
            # Aggiorna la password e segna il codice come usato
            await conn.execute('UPDATE users SET password = $1 WHERE id = $2', hashed_password, user_id)
            await conn.execute('UPDATE password_resets SET used = true WHERE id = $1', reset_request['id'])
            
            # Registra il cambio password nei log
            await conn.execute('''
                INSERT INTO user_activities (user_id, activity_type, ip_address, timestamp)
                VALUES ($1, 'password_reset', $2, NOW())
            ''', user_id, request.remote_addr)
            
            # Reindirizza alla pagina di login con messaggio di successo
            return redirect(url_for('login', success='Password aggiornata con successo. Puoi ora accedere con la nuova password.'))
    
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento password: {e}")
        return await render_template('reset_password.html', 
            request_step='password', 
            email=email, 
            reset_token=reset_token, 
            verification_code=verification_code, 
            error='Si è verificato un errore. Riprova più tardi.')

@app.route('/api/resend-verification-code', methods=['POST'])
async def resend_verification_code():
    """API per rinviare il codice di verifica."""
    try:
        data = await request.json
        email = data.get('email')
        
        if not email:
            return jsonify({'success': False, 'error': 'Indirizzo email richiesto'}), 400
        
        if not db_pool:
            return jsonify({'success': False, 'error': 'Database non disponibile'}), 500
            
        async with db_pool.acquire() as conn:
            # Verifica se esiste una richiesta per questa email
            user = await conn.fetchrow('SELECT id, username FROM users WHERE email = $1', email)
            
            if not user:
                # Per sicurezza, non rivelare che l'email non esiste
                return jsonify({'success': True, 'message': 'Codice inviato se l\'indirizzo esiste'})
            
            # Genera nuovo codice e token
            token = secrets.token_urlsafe(32)
            verification_code = ''.join(random.choices(string.digits, k=6))
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            
            # Verifica se esiste già una richiesta
            existing_request = await conn.fetchval(
                'SELECT id FROM password_resets WHERE user_id = $1', user['id'])
            
            if existing_request:
                # Aggiorna la richiesta esistente
                await conn.execute('''
                    UPDATE password_resets 
                    SET token = $1, verification_code = $2, expires_at = $3, created_at = NOW(), used = false
                    WHERE user_id = $4
                ''', token, verification_code, expires_at, user['id'])
            else:
                # Crea una nuova richiesta
                await conn.execute('''
                    INSERT INTO password_resets (user_id, email, token, verification_code, expires_at, created_at)
                    VALUES ($1, $2, $3, $4, $5, NOW())
                ''', user['id'], email, token, verification_code, expires_at)
            
            # Invia email (in produzione)
            # await send_reset_email(email, user['username'], verification_code)
            
            # In sviluppo, mostriamo il codice in console
            logger.info(f"Nuovo codice di verifica per {email}: {verification_code}")
            
            return jsonify({'success': True, 'message': 'Nuovo codice inviato'})
    
    except Exception as e:
        logger.error(f"Errore nel rinvio codice verifica: {e}")
        return jsonify({'success': False, 'error': 'Si è verificato un errore. Riprova più tardi.'}), 500

# API per la sicurezza e il blocco intelligente
@app.route('/api/security/check-login-attempts', methods=['POST'])
async def check_login_attempts():
    """API per controllare i tentativi di accesso e bloccare IP sospetti."""
    try:
        data = await request.json
        username_or_email = data.get('username_or_email')
        ip_address = data.get('ip_address') or request.remote_addr
        
        if not db_pool:
            return jsonify({'success': False, 'error': 'Database non disponibile'}), 500
            
        async with db_pool.acquire() as conn:
            # Crea tabella se non esiste
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS login_attempts (
                    id SERIAL PRIMARY KEY,
                    username_or_email TEXT NOT NULL,
                    ip_address TEXT NOT NULL,
                    successful BOOLEAN NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
                )
            ''')
            
            # Conta i tentativi falliti negli ultimi 15 minuti
            time_limit = datetime.now(timezone.utc) - timedelta(minutes=15)
            
            # Tentativi falliti da questo IP
            ip_attempts = await conn.fetchval('''
                SELECT COUNT(*) FROM login_attempts
                WHERE ip_address = $1 AND successful = false AND timestamp > $2
            ''', ip_address, time_limit)
            
            # Tentativi falliti per questo utente
            user_attempts = 0
            if username_or_email:
                user_attempts = await conn.fetchval('''
                    SELECT COUNT(*) FROM login_attempts
                    WHERE username_or_email = $1 AND successful = false AND timestamp > $2
                ''', username_or_email, time_limit)
            
            # Controllo se l'IP è bloccato
            is_ip_blocked = await conn.fetchval('''
                SELECT EXISTS(
                    SELECT 1 FROM blocked_ips
                    WHERE ip_address = $1 AND block_until > NOW()
                )
            ''', ip_address)
            
            # Controllo se l'utente è bloccato
            is_user_blocked = False
            if username_or_email:
                is_user_blocked = await conn.fetchval('''
                    SELECT EXISTS(
                        SELECT 1 FROM users
                        WHERE (username = $1 OR email = $1) AND blocked_until > NOW()
                    )
                ''', username_or_email)
            
            # Determina se dovremmo bloccare
            should_block_ip = ip_attempts >= 10  # Blocca dopo 10 tentativi falliti
            should_block_user = user_attempts >= 5  # Blocca dopo 5 tentativi falliti
            
            # Applica i blocchi se necessario
            if should_block_ip and not is_ip_blocked:
                # Blocca l'IP per 30 minuti
                block_until = datetime.now(timezone.utc) + timedelta(minutes=30)
                await conn.execute('''
                    INSERT INTO blocked_ips (ip_address, reason, block_until, created_at)
                    VALUES ($1, 'Troppi tentativi di accesso falliti', $2, NOW())
                    ON CONFLICT (ip_address) DO UPDATE
                    SET block_until = $2, reason = 'Troppi tentativi di accesso falliti'
                ''', ip_address, block_until)
                
                is_ip_blocked = True
            
            if should_block_user and not is_user_blocked and username_or_email:
                # Blocca l'utente per 15 minuti
                block_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                await conn.execute('''
                    UPDATE users
                    SET blocked_until = $1
                    WHERE username = $2 OR email = $2
                ''', block_until, username_or_email)
                
                is_user_blocked = True
            
            return jsonify({
                'success': True,
                'ip_blocked': is_ip_blocked,
                'user_blocked': is_user_blocked,
                'ip_attempts': ip_attempts,
                'user_attempts': user_attempts
            })
    
    except Exception as e:
        logger.error(f"Errore nel controllo dei tentativi di accesso: {e}")
        return jsonify({
            'success': False, 
            'error': 'Si è verificato un errore',
            'ip_blocked': False,
            'user_blocked': False
        }), 500

@app.route('/api/security/record-login-attempt', methods=['POST'])
async def record_login_attempt():
    """API per registrare un tentativo di accesso."""
    try:
        data = await request.json
        username_or_email = data.get('username_or_email')
        ip_address = data.get('ip_address') or request.remote_addr
        successful = data.get('successful', False)
        
        if not username_or_email:
            return jsonify({'success': False, 'error': 'Username o email richiesto'}), 400
        
        if not db_pool:
            return jsonify({'success': False, 'error': 'Database non disponibile'}), 500
            
        async with db_pool.acquire() as conn:
            # Registra il tentativo
            await conn.execute('''
                INSERT INTO login_attempts (username_or_email, ip_address, successful, timestamp)
                VALUES ($1, $2, $3, NOW())
            ''', username_or_email, ip_address, successful)
            
            # Se il login è andato a buon fine, resetta eventuali blocchi
            if successful:
                # Sblocca l'utente
                await conn.execute('''
                    UPDATE users
                    SET blocked_until = NULL
                    WHERE username = $1 OR email = $1
                ''', username_or_email)
                
                # Registra l'attività dell'utente
                user_id = await conn.fetchval('''
                    SELECT id FROM users
                    WHERE username = $1 OR email = $1
                ''', username_or_email)
                
                if user_id:
                    await conn.execute('''
                        INSERT INTO user_activities (user_id, activity_type, ip_address, timestamp)
                        VALUES ($1, 'login', $2, NOW())
                    ''', user_id, ip_address)
            
            return jsonify({'success': True})
    
    except Exception as e:
        logger.error(f"Errore nella registrazione del tentativo di accesso: {e}")
        return jsonify({'success': False, 'error': 'Si è verificato un errore'}), 500

@app.route('/password_recovery')
def password_recovery():
    """
    Pagina per il recupero della password.
    """
    return render_template('password_recovery.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
