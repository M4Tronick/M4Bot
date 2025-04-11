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

import aiohttp
from quart import Quart, render_template, request, redirect, url_for, session, jsonify
from quart_cors import cors
import asyncpg
import bcrypt

# Aggiungi la directory principale al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.config import *

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

async def setup_db_pool():
    """Crea il pool di connessioni al database."""
    global db_pool
    db_pool = await asyncpg.create_pool(
        user=DB_USER,
        password=DB_PASS,
        database=DB_NAME,
        host=DB_HOST
    )
    
# Funzioni di utilità
def login_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return await f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
            
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
    
    async with db_pool.acquire() as conn:
        # Ottieni i dati dell'utente
        user = await conn.fetchrow(
            'SELECT id, username, email, is_admin FROM users WHERE id = $1',
            user_id
        )
        
        # Ottieni i canali configurati dall'utente
        channels = await conn.fetch('''
            SELECT c.id, c.name, c.kick_channel_id, c.created_at
            FROM channels c
            WHERE c.owner_id = $1
            ORDER BY c.name
        ''', user_id)
        
        # Ottieni statistiche di base
        stats = {}
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
    
    if request.method == 'POST':
        form = await request.form
        channel_name = form.get('channel_name')
        
        if not channel_name:
            error = "Nome del canale richiesto"
        else:
            try:
                # Genera i parametri PKCE
                code_verifier, code_challenge = generate_pkce_challenge()
                state = generate_state()
                
                # Salva i dati nella sessione per l'uso successivo
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
                logger.error(f"Errore nella preparazione OAuth: {e}")
                error = "Si è verificato un errore nella preparazione dell'autenticazione"
    
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
        settings = {}
        settings_rows = await conn.fetch('''
            SELECT key, value
            FROM settings
            WHERE channel_id = $1
        ''', channel_id)
        
        for row in settings_rows:
            settings[row['key']] = row['value']
    
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
                async with db_pool.acquire() as conn:
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
            
            async with db_pool.acquire() as conn:
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
            
            async with db_pool.acquire() as conn:
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
    async with db_pool.acquire() as conn:
        commands = await conn.fetch('''
            SELECT id, name, response, cooldown, user_level, enabled, usage_count, updated_at
            FROM commands
            WHERE channel_id = $1
            ORDER BY name
        ''', channel_id)
    
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
        settings = {
            'welcome_message': form.get('welcome_message', ''),
            'auto_shoutout': form.get('auto_shoutout', 'false'),
            'points_per_minute': form.get('points_per_minute', '1'),
            'command_cooldown': form.get('command_cooldown', '5'),
            'bot_prefix': form.get('bot_prefix', '!'),
            'mod_only_commands': form.get('mod_only_commands', '')
        }
        
        async with db_pool.acquire() as conn:
            try:
                # Salva ogni impostazione
                for key, value in settings.items():
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
    async with db_pool.acquire() as conn:
        settings = {}
        settings_rows = await conn.fetch('''
            SELECT key, value
            FROM settings
            WHERE channel_id = $1
        ''', channel_id)
        
        for row in settings_rows:
            settings[row['key']] = row['value']
        
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
            
            # Qui chiameremmo l'API del bot per avviare il gioco
            # Per ora, simula solo un successo
            success = f"Gioco {game_type} avviato"
    
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
        
        # Ottieni l'attività per ora del giorno
        hourly_activity = await conn.fetch('''
            SELECT 
                EXTRACT(HOUR FROM created_at) as hour,
                COUNT(*) as message_count
            FROM chat_messages
            WHERE channel_id = $1
            GROUP BY hour
            ORDER BY hour
        ''', channel_id)
        
        # Formatta i dati per i grafici
        hourly_data = {
            'labels': [str(h) for h in range(24)],
            'data': [0] * 24
        }
        
        for row in hourly_activity:
            hour = int(row['hour'])
            hourly_data['data'][hour] = row['message_count']
    
    return await render_template(
        'channel_stats.html',
        channel=channel,
        stats=stats,
        top_chatters=top_chatters,
        top_commands=top_commands,
        top_points=top_points,
        hourly_data=json.dumps(hourly_data)
    )

@app.route('/api/bot/start', methods=['POST'])
@login_required
async def api_start_bot():
    """API per avviare il bot."""
    user_id = session.get('user_id')
    data = await request.json
    channel_id = data.get('channel_id')
    
    async with db_pool.acquire() as conn:
        # Verifica che l'utente sia il proprietario del canale
        channel = await conn.fetchrow('''
            SELECT c.id, c.name
            FROM channels c
            WHERE c.id = $1 AND c.owner_id = $2
        ''', channel_id, user_id)
        
        if not channel:
            return jsonify({'success': False, 'error': 'Canale non trovato o non autorizzato'})
    
    # Qui chiameremo l'API del bot per avviarlo
    # Per ora, simula solo un successo
    return jsonify({'success': True, 'message': f"Bot avviato per il canale {channel['name']}"})

@app.route('/api/bot/stop', methods=['POST'])
@login_required
async def api_stop_bot():
    """API per fermare il bot."""
    user_id = session.get('user_id')
    data = await request.json
    channel_id = data.get('channel_id')
    
    async with db_pool.acquire() as conn:
        # Verifica che l'utente sia il proprietario del canale
        channel = await conn.fetchrow('''
            SELECT c.id, c.name
            FROM channels c
            WHERE c.id = $1 AND c.owner_id = $2
        ''', channel_id, user_id)
        
        if not channel:
            return jsonify({'success': False, 'error': 'Canale non trovato o non autorizzato'})
    
    # Qui chiameremo l'API del bot per fermarlo
    # Per ora, simula solo un successo
    return jsonify({'success': True, 'message': f"Bot fermato per il canale {channel['name']}"})

@app.route('/api/channel/<int:channel_id>/commands', methods=['GET'])
async def api_get_commands(channel_id):
    """API pubblica per ottenere i comandi di un canale."""
    async with db_pool.acquire() as conn:
        # Verifica che il canale esista
        channel = await conn.fetchrow('''
            SELECT c.id, c.name
            FROM channels c
            WHERE c.id = $1
        ''', channel_id)
        
        if not channel:
            return jsonify({'success': False, 'error': 'Canale non trovato'})
            
        # Ottieni i comandi attivi
        commands = await conn.fetch('''
            SELECT name, response, user_level
            FROM commands
            WHERE channel_id = $1 AND enabled = true
            ORDER BY name
        ''', channel_id)
        
        # Formatta i comandi per la risposta JSON
        command_list = [
            {
                'name': cmd['name'],
                'description': cmd['response'],
                'permission': cmd['user_level']
            }
            for cmd in commands
        ]
    
    return jsonify({
        'success': True,
        'channel': channel['name'],
        'commands': command_list
    })

@app.route('/commands/<channel_name>')
async def public_commands(channel_name):
    """Pagina pubblica per visualizzare i comandi di un canale."""
    async with db_pool.acquire() as conn:
        # Trova il canale dal nome
        channel = await conn.fetchrow('''
            SELECT id, name
            FROM channels
            WHERE name = $1
        ''', channel_name)
        
        if not channel:
            return await render_template('error.html', message="Canale non trovato")
            
        # Ottieni i comandi attivi
        commands = await conn.fetch('''
            SELECT name, response, user_level
            FROM commands
            WHERE channel_id = $1 AND enabled = true
            ORDER BY name
        ''', channel['id'])
    
    return await render_template(
        'public_commands.html',
        channel=channel,
        commands=commands
    )

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
    """Inizializza il pool di connessioni prima di avviare il server."""
    await setup_db_pool()

@app.after_serving
async def after_serving():
    """Chiude il pool di connessioni dopo l'arresto del server."""
    if db_pool:
        await db_pool.close()

if __name__ == "__main__":
    app.run(
        host=WEB_HOST,
        port=WEB_PORT,
        certfile=SSL_CERT,
        keyfile=SSL_KEY
    )
