#!/usr/bin/env python3
"""
M4Bot - Bot per Kick.com
Un bot avanzato per Kick.com con funzionalità di moderazione, comandi personalizzati,
giochi in chat, sistema di punti e altro ancora.
"""

import os
import sys
import logging
import asyncio
import json
import time
import datetime
import random
import string
import hashlib
import base64
import secrets
from typing import Dict, List, Optional, Any, Union, Callable

import aiohttp
import asyncpg
import websockets
import requests
from cryptography.fernet import Fernet

# Importa la configurazione
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bot.config import *

# Importazione dei moduli
from bot.kick_channel_points import KickChannelPoints
from stability.monitoring.integrated_monitor import IntegratedMonitor

# Assicurati che tutte le directory necessarie esistano
directories_to_check = [
    os.path.dirname(LOG_FILE),  # Directory principale dei log
    "logs/channels",            # Log specifici per canale
    "logs/webhooks",            # Log per i webhook
    "logs/security",            # Log di sicurezza
    "logs/errors",              # Log degli errori
    "logs/connections"          # Log delle connessioni
]

for directory in directories_to_check:
    if directory and not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)
        print(f"Directory creata: {directory}")

# Configura il logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('M4Bot')

class Database:
    """Gestisce la connessione e le operazioni del database."""
    
    def __init__(self):
        """Inizializza il gestore del database."""
        self.pool = None
        self.connection_string = os.environ.get(
            "DATABASE_URL", 
            "postgresql://postgres:postgres@localhost/m4bot"
        )
        
    async def connect(self):
        """Connette al database PostgreSQL."""
        retry_count = 0
        max_retries = 5
        retry_delay = 2  # secondi
        
        while retry_count < max_retries:
            try:
                logger.info(f"Tentativo di connessione al database: {retry_count + 1}")
                
                self.pool = await asyncpg.create_pool(
                    dsn=self.connection_string,
                    min_size=1,
                    max_size=10
                )
                
                # Verifica la connessione eseguendo una query semplice
                async with self.pool.acquire() as conn:
                    version = await conn.fetchval("SELECT version()")
                    logger.info(f"Connesso al database: {version}")
                
                # Inizializza le tabelle necessarie
                await self._initialize_tables()
                
                return True
            except Exception as e:
                retry_count += 1
                logger.error(f"Errore nella connessione al database: {e}")
                
                if retry_count < max_retries:
                    logger.info(f"Ritentativo tra {retry_delay} secondi...")
                    await asyncio.sleep(retry_delay)
                    # Aumenta il ritardo per i prossimi tentativi
                    retry_delay *= 2
                else:
                    logger.critical("Numero massimo di tentativi di connessione raggiunto")
                    break
        
        # Se arriviamo qui, non siamo riusciti a connetterci dopo tutti i tentativi
        logger.critical("Impossibile avviare il bot senza connessione al database")
        return False
            
    async def _initialize_tables(self):
        """Crea le tabelle necessarie se non esistono."""
        async with self.pool.acquire() as conn:
            # Tabella utenti
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    kick_id VARCHAR(255) UNIQUE NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE,
                    password_hash VARCHAR(255),
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    last_login TIMESTAMP WITH TIME ZONE
                )
            ''')
            
            # Tabella canali
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS channels (
                    id SERIAL PRIMARY KEY,
                    kick_channel_id VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    owner_id INTEGER REFERENCES users(id),
                    access_token TEXT,
                    refresh_token TEXT,
                    token_expires_at TIMESTAMP WITH TIME ZONE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            ''')
            
            # Tabella comandi personalizzati
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS commands (
                    id SERIAL PRIMARY KEY,
                    channel_id INTEGER REFERENCES channels(id),
                    name VARCHAR(255) NOT NULL,
                    response TEXT NOT NULL,
                    cooldown INTEGER DEFAULT 5,
                    user_level VARCHAR(50) DEFAULT 'everyone',
                    enabled BOOLEAN DEFAULT TRUE,
                    usage_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(channel_id, name)
                )
            ''')
            
            # Tabella punti canale
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS channel_points (
                    id SERIAL PRIMARY KEY,
                    channel_id INTEGER REFERENCES channels(id),
                    user_id INTEGER REFERENCES users(id),
                    points INTEGER DEFAULT 0,
                    watch_time INTEGER DEFAULT 0,
                    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(channel_id, user_id)
                )
            ''')
            
            # Tabella impostazioni
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    id SERIAL PRIMARY KEY,
                    channel_id INTEGER REFERENCES channels(id),
                    key VARCHAR(255) NOT NULL,
                    value TEXT,
                    UNIQUE(channel_id, key)
                )
            ''')
            
            # Tabella log eventi
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS event_logs (
                    id SERIAL PRIMARY KEY,
                    channel_id INTEGER REFERENCES channels(id),
                    event_type VARCHAR(255) NOT NULL,
                    user_id INTEGER REFERENCES users(id),
                    data JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            ''')
            
            # Tabella ruoli utente
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_roles (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id),
                    channel_id INTEGER REFERENCES channels(id),
                    role VARCHAR(50) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    UNIQUE(user_id, channel_id)
                )
            ''')
            
            # Tabella messaggi chat
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    channel_id INTEGER REFERENCES channels(id),
                    user_id VARCHAR(255) NOT NULL,
                    username VARCHAR(255) NOT NULL,
                    content TEXT NOT NULL,
                    is_command BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            ''')
            
            logger.info("Inizializzazione delle tabelle completata")

class KickApi:
    """Classe per interagire con l'API di Kick.com."""
    
    BASE_URL = "https://kick.com/api/v2"
    AUTH_URL = "https://id.kick.com/oauth"
    
    def __init__(self, db):
        self.db = db
        self.session = None
        self.encryption = Encryption(ENCRYPTION_KEY)
        
    async def create_session(self):
        """Crea una sessione HTTP per le richieste API."""
        self.session = aiohttp.ClientSession()
        
    async def close_session(self):
        """Chiude la sessione HTTP."""
        if self.session:
            await self.session.close()
            
    def generate_pkce_challenge(self):
        """Genera un challenge PKCE per l'autenticazione OAuth."""
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip("=")
        
        return code_verifier, code_challenge
        
    def get_oauth_url(self, state: str, code_challenge: str):
        """Genera l'URL per l'autenticazione OAuth."""
        params = {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state
        }
        
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.AUTH_URL}/authorize?{query_string}"
        
    async def exchange_code_for_token(self, code: str, code_verifier: str):
        """Scambia il codice di autorizzazione con i token di accesso e refresh."""
        if not self.session:
            await self.create_session()
            
        data = {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier
        }
        
        async with self.session.post(f"{self.AUTH_URL}/token", data=data) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"Errore nello scambio del codice: {error_text}")
                return None
                
            token_data = await response.json()
            return token_data
            
    async def refresh_access_token(self, channel_id: int, refresh_token: str):
        """Aggiorna il token di accesso usando il refresh token."""
        if not self.session:
            await self.create_session()
            
        data = {
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": refresh_token
        }
        
        async with self.session.post(f"{self.AUTH_URL}/token", data=data) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"Errore nel refresh del token: {error_text}")
                return None
                
            token_data = await response.json()
            
            # Aggiorna i token nel database
            async with self.db.pool.acquire() as conn:
                encrypted_access_token = self.encryption.encrypt(token_data["access_token"])
                encrypted_refresh_token = self.encryption.encrypt(token_data["refresh_token"])
                expires_at = datetime.datetime.now(datetime.timezone.utc) + \
                            datetime.timedelta(seconds=token_data["expires_in"])
                
                await conn.execute('''
                    UPDATE channels 
                    SET access_token = $1, refresh_token = $2, token_expires_at = $3, updated_at = NOW()
                    WHERE id = $4
                ''', encrypted_access_token, encrypted_refresh_token, expires_at, channel_id)
                
            return token_data
            
    async def get_valid_token(self, channel_id: int):
        """Ottiene un token di accesso valido per un canale."""
        async with self.db.pool.acquire() as conn:
            channel = await conn.fetchrow('''
                SELECT id, access_token, refresh_token, token_expires_at
                FROM channels
                WHERE id = $1
            ''', channel_id)
            
            if not channel:
                logger.error(f"Canale con ID {channel_id} non trovato")
                return None
                
            access_token = self.encryption.decrypt(channel["access_token"])
            expires_at = channel["token_expires_at"]
            
            # Controlla se il token è scaduto o sta per scadere (entro 5 minuti)
            if not expires_at or expires_at <= (datetime.datetime.now(datetime.timezone.utc) + 
                                              datetime.timedelta(minutes=5)):
                # Refresh del token
                refresh_token = self.encryption.decrypt(channel["refresh_token"])
                token_data = await self.refresh_access_token(channel_id, refresh_token)
                if token_data:
                    return token_data["access_token"]
                return None
                
            return access_token
            
    async def api_request(self, method: str, endpoint: str, channel_id: int = None, 
                         params: dict = None, data: dict = None):
        """Esegue una richiesta all'API di Kick."""
        if not self.session:
            await self.create_session()
            
        url = f"{self.BASE_URL}/{endpoint}"
        headers = {}
        
        if channel_id:
            token = await self.get_valid_token(channel_id)
            if not token:
                logger.error(f"Impossibile ottenere un token valido per il canale {channel_id}")
                return None
            headers["Authorization"] = f"Bearer {token}"
            
        try:
            if method.upper() == "GET":
                async with self.session.get(url, params=params, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Errore nella richiesta API GET {url}: {error_text}")
                        return None
                    return await response.json()
            elif method.upper() == "POST":
                async with self.session.post(url, json=data, headers=headers) as response:
                    if response.status != 200 and response.status != 201:
                        error_text = await response.text()
                        logger.error(f"Errore nella richiesta API POST {url}: {error_text}")
                        return None
                    return await response.json()
            elif method.upper() == "PUT":
                async with self.session.put(url, json=data, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Errore nella richiesta API PUT {url}: {error_text}")
                        return None
                    return await response.json()
            elif method.upper() == "DELETE":
                async with self.session.delete(url, params=params, headers=headers) as response:
                    if response.status != 200 and response.status != 204:
                        error_text = await response.text()
                        logger.error(f"Errore nella richiesta API DELETE {url}: {error_text}")
                        return None
                    if response.status == 204:
                        return True
                    return await response.json()
        except Exception as e:
            logger.error(f"Eccezione nella richiesta API {url}: {e}")
            return None
            
    async def send_chat_message(self, channel_id: int, channel_name: str, message: str):
        """Invia un messaggio in chat."""
        endpoint = f"channels/{channel_name}/chat"
        data = {"content": message}
        return await self.api_request("POST", endpoint, channel_id, data=data)
        
    async def ban_user(self, channel_id: int, channel_name: str, user_id: str, reason: str = None):
        """Banna un utente dal canale."""
        endpoint = f"channels/{channel_name}/bans"
        data = {"user_id": user_id}
        if reason:
            data["reason"] = reason
        return await self.api_request("POST", endpoint, channel_id, data=data)
        
    async def timeout_user(self, channel_id: int, channel_name: str, user_id: str, 
                          duration: int, reason: str = None):
        """Mette in timeout un utente per una durata specificata (in secondi)."""
        endpoint = f"channels/{channel_name}/timeouts"
        data = {"user_id": user_id, "duration": duration}
        if reason:
            data["reason"] = reason
        return await self.api_request("POST", endpoint, channel_id, data=data)
        
    async def get_channel_info(self, channel_name: str):
        """Ottiene informazioni su un canale."""
        endpoint = f"channels/{channel_name}"
        return await self.api_request("GET", endpoint)
        
    async def get_user_info(self, user_id: str = None, username: str = None):
        """Ottiene informazioni su un utente."""
        if user_id:
            endpoint = f"users/{user_id}"
        elif username:
            endpoint = f"users?username={username}"
        else:
            logger.error("Devi specificare user_id o username")
            return None
        return await self.api_request("GET", endpoint)

class Encryption:
    """Classe per la crittografia e decrittografia dei dati sensibili."""
    
    def __init__(self, key: str):
        """
        Inizializza la classe di crittografia
        
        Args:
            key: Chiave di crittografia (Fernet key)
        """
        # Assicurati che la chiave sia di 32 byte base64-encoded
        self.temp_key_used = False
        self.key = key
        
        try:
            if not key:
                raise ValueError("La chiave di crittografia non può essere vuota")
                
            if not isinstance(key, bytes):
                key = key.encode('utf-8')
                
            # Verifica se la chiave è già una chiave Fernet valida
            base64.urlsafe_b64decode(key + b'=' * (4 - len(key) % 4))
            self.fernet = Fernet(key)
            logger.info("Inizializzazione crittografia completata con la chiave fornita")
        except Exception as e:
            logger.critical(f"Errore nell'inizializzazione della chiave Fernet: {e}")
            logger.critical("ATTENZIONE: Utilizzo di una chiave temporanea. I dati crittografati non saranno recuperabili al riavvio!")
            
            # Genera una nuova chiave Fernet valida
            from cryptography.fernet import Fernet
            temp_key = Fernet.generate_key()
            self.fernet = Fernet(temp_key)
            self.temp_key_used = True
            
            # Scrivi nel log la chiave generata per consentire un possibile recupero
            logger.critical(f"Chiave temporanea generata: {temp_key.decode('utf-8')}")
            logger.critical("Salvare questa chiave e impostarla come ENCRYPTION_KEY per recuperare i dati!")
            
            # Aggiungi al file di log per il recupero di emergenza
            try:
                with open("logs/security/encryption_emergency.log", "a") as f:
                    f.write(f"{datetime.datetime.now().isoformat()} - CHIAVE TEMPORANEA: {temp_key.decode('utf-8')}\n")
            except Exception as log_error:
                logger.critical(f"Impossibile salvare la chiave temporanea nel log di emergenza: {log_error}")
    
    def encrypt(self, data: str) -> str:
        """
        Cripta un dato
        
        Args:
            data: Dato da criptare
            
        Returns:
            str: Dato criptato (base64)
        """
        if self.temp_key_used:
            logger.warning("Crittografia con chiave temporanea. I dati potrebbero non essere recuperabili al riavvio!")
            
        if not data:
            logger.error("Tentativo di crittografare dati vuoti")
            return ""
            
        try:
            return self.fernet.encrypt(data.encode('utf-8')).decode('utf-8')
        except Exception as e:
            error_msg = f"Errore nella crittografia dei dati: {e}"
            logger.error(error_msg)
            
            # Registra l'errore in un file separato con più dettagli per il debug
            self._log_encryption_error("encrypt", error_msg)
            
            # Rilancia l'eccezione per consentire all'applicazione di gestirla
            raise EncryptionError(f"Impossibile crittografare i dati: {e}")
    
    def decrypt(self, encrypted_data: str) -> str:
        """
        Decripta un dato
        
        Args:
            encrypted_data: Dato criptato (base64)
            
        Returns:
            str: Dato decriptato
        """
        if self.temp_key_used:
            logger.warning("Decrittografia con chiave temporanea. I dati potrebbero non essere recuperabili al riavvio!")
            
        if not encrypted_data:
            logger.error("Tentativo di decrittografare dati vuoti")
            return ""
            
        try:
            return self.fernet.decrypt(encrypted_data.encode('utf-8')).decode('utf-8')
        except Exception as e:
            error_msg = f"Errore nella decrittografia dei dati: {e}"
            logger.error(error_msg)
            
            # Registra l'errore in un file separato per il debug
            self._log_encryption_error("decrypt", error_msg)
            
            # Rilancia l'eccezione per consentire all'applicazione di gestirla
            raise EncryptionError(f"Impossibile decrittografare i dati: {e}")
    
    def is_using_temp_key(self) -> bool:
        """
        Verifica se si sta utilizzando una chiave temporanea
        
        Returns:
            bool: True se si sta utilizzando una chiave temporanea
        """
        return self.temp_key_used
    
    def _log_encryption_error(self, operation: str, error_msg: str):
        """
        Registra un errore di crittografia in un file separato
        
        Args:
            operation: Operazione che ha causato l'errore (encrypt/decrypt)
            error_msg: Messaggio di errore
        """
        try:
            os.makedirs("logs/security", exist_ok=True)
            
            with open("logs/security/encryption_errors.log", "a") as f:
                f.write(f"{datetime.datetime.now().isoformat()} - {operation.upper()}: {error_msg}\n")
        except Exception as log_error:
            logger.error(f"Impossibile registrare l'errore di crittografia nel file di log: {log_error}")

class EncryptionError(Exception):
    """Eccezione per errori di crittografia/decrittografia"""
    pass

class CommandHandler:
    """Gestisce i comandi del bot."""
    
    def __init__(self, bot):
        self.bot = bot
        self.commands = {}
        self.cooldowns = {}
        
    async def load_commands(self, channel_id: int):
        """Carica i comandi dal database per un canale specifico."""
        async with self.bot.db.pool.acquire() as conn:
            commands = await conn.fetch('''
                SELECT id, name, response, cooldown, user_level
                FROM commands
                WHERE channel_id = $1 AND enabled = TRUE
            ''', channel_id)
            
            self.commands[channel_id] = {}
            for cmd in commands:
                self.commands[channel_id][cmd["name"]] = {
                    "id": cmd["id"],
                    "response": cmd["response"],
                    "cooldown": cmd["cooldown"],
                    "user_level": cmd["user_level"]
                }
                
            logger.info(f"Caricati {len(commands)} comandi per il canale {channel_id}")
            
    async def add_command(self, channel_id: int, name: str, response: str, 
                         cooldown: int = 5, user_level: str = "everyone"):
        """Aggiunge un nuovo comando al database."""
        async with self.bot.db.pool.acquire() as conn:
            try:
                command_id = await conn.fetchval('''
                    INSERT INTO commands (channel_id, name, response, cooldown, user_level)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (channel_id, name) 
                    DO UPDATE SET response = $3, cooldown = $4, user_level = $5, updated_at = NOW()
                    RETURNING id
                ''', channel_id, name, response, cooldown, user_level)
                
                if channel_id not in self.commands:
                    self.commands[channel_id] = {}
                    
                self.commands[channel_id][name] = {
                    "id": command_id,
                    "response": response,
                    "cooldown": cooldown,
                    "user_level": user_level
                }
                
                return True
            except Exception as e:
                logger.error(f"Errore nell'aggiunta del comando: {e}")
                return False
                
    async def remove_command(self, channel_id: int, name: str):
        """Rimuove un comando dal database."""
        async with self.bot.db.pool.acquire() as conn:
            try:
                await conn.execute('''
                    DELETE FROM commands
                    WHERE channel_id = $1 AND name = $2
                ''', channel_id, name)
                
                if channel_id in self.commands and name in self.commands[channel_id]:
                    del self.commands[channel_id][name]
                    
                return True
            except Exception as e:
                logger.error(f"Errore nella rimozione del comando: {e}")
                return False
                
    async def handle_command(self, channel_id: int, channel_name: str, user: dict, message: str):
        """Gestisce un comando ricevuto in chat."""
        if not message.startswith("!"):
            return
            
        # Estrae il nome del comando e gli argomenti
        parts = message.split(" ", 1)
        command_name = parts[0][1:]  # Rimuove il ! iniziale
        args = parts[1] if len(parts) > 1 else ""
        
        # Controlla se il comando esiste
        if (channel_id not in self.commands or 
            command_name not in self.commands[channel_id]):
            return
            
        # Controlla i cooldown
        current_time = time.time()
        cmd_info = self.commands[channel_id][command_name]
        cooldown_key = f"{channel_id}:{command_name}"
        user_cooldown_key = f"{channel_id}:{command_name}:{user['id']}"
        
        # Cooldown globale del comando
        if cooldown_key in self.cooldowns:
            if current_time - self.cooldowns[cooldown_key] < DEFAULT_GLOBAL_COOLDOWN:
                return
                
        # Cooldown specifico dell'utente per questo comando
        if user_cooldown_key in self.cooldowns:
            if current_time - self.cooldowns[user_cooldown_key] < cmd_info["cooldown"]:
                return
                
        # Controlla il livello di permesso richiesto
        # Da implementare il controllo dei permessi dell'utente
        
        # Processa il comando
        response = cmd_info["response"]
        
        # Sostituisci i placeholder con i valori reali
        response = response.replace("{user}", user.get("username", "utente"))
        response = response.replace("{args}", args)
        
        # Aggiorna i cooldown
        self.cooldowns[cooldown_key] = current_time
        self.cooldowns[user_cooldown_key] = current_time
        
        # Invia la risposta in chat
        await self.bot.api.send_chat_message(channel_id, channel_name, response)
        
        # Aggiorna il contatore di utilizzo
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute('''
                UPDATE commands
                SET usage_count = usage_count + 1
                WHERE id = $1
            ''', cmd_info["id"])

class ChatGame:
    """Classe base per i giochi in chat."""
    
    def __init__(self, bot, channel_id: int, channel_name: str):
        self.bot = bot
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.active = False
        self.participants = {}
        
    async def start(self):
        """Avvia il gioco."""
        self.active = True
        
    async def stop(self):
        """Ferma il gioco."""
        self.active = False
        
    async def handle_message(self, user: dict, message: str):
        """Gestisce un messaggio ricevuto durante il gioco."""
        pass
        
class DiceGame(ChatGame):
    """Implementazione di un gioco di dadi in chat."""
    
    async def start(self):
        """Avvia il gioco dei dadi."""
        await super().start()
        
        # Annuncia l'inizio del gioco
        await self.bot.api.send_chat_message(
            self.channel_id, 
            self.channel_name,
            "🎲 Gioco dei dadi iniziato! Scrivi !dadi per partecipare. Hai 60 secondi!"
        )
        
        # Attende 60 secondi per le partecipazioni
        await asyncio.sleep(60)
        
        # Termina il gioco e annuncia il vincitore
        if not self.participants:
            await self.bot.api.send_chat_message(
                self.channel_id,
                self.channel_name,
                "Nessuno ha partecipato al gioco dei dadi! 😢"
            )
        else:
            # Tira i dadi per tutti i partecipanti e trova il vincitore
            winner = None
            max_roll = 0
            
            for user_id, user_info in self.participants.items():
                roll = random.randint(1, 6)
                user_info["roll"] = roll
                
                if roll > max_roll:
                    max_roll = roll
                    winner = user_info
                    
            # Annuncia i risultati
            results = "\n".join([
                f"{info['username']}: 🎲 {info['roll']}" 
                for _, info in self.participants.items()
            ])
            
            await self.bot.api.send_chat_message(
                self.channel_id,
                self.channel_name,
                f"Risultati del gioco dei dadi:\n{results}\n\n🏆 Il vincitore è {winner['username']} con {max_roll}!"
            )
            
            # Assegna punti al vincitore
            await self.bot.update_user_points(
                self.channel_id, 
                winner["id"], 
                50  # Punti da assegnare al vincitore
            )
            
        await self.stop()
        
    async def handle_message(self, user: dict, message: str):
        """Gestisce i messaggi durante il gioco dei dadi."""
        if not self.active:
            return
            
        if message.strip().lower() == "!dadi":
            # Aggiungi l'utente ai partecipanti
            if user["id"] not in self.participants:
                self.participants[user["id"]] = {
                    "id": user["id"],
                    "username": user["username"]
                }
                
                await self.bot.api.send_chat_message(
                    self.channel_id,
                    self.channel_name,
                    f"{user['username']} si è unito al gioco dei dadi! 🎲"
                )

class MarbleGame(ChatGame):
    """Implementazione di un gioco marble in chat."""
    
    def __init__(self, bot, channel_id: int, channel_name: str):
        super().__init__(bot, channel_id, channel_name)
        self.track_length = 10  # Lunghezza del percorso
        self.marble_positions = {}  # Posizioni delle biglie
        self.finished_marbles = []  # Biglie che hanno completato il percorso
        self.race_active = False  # Indica se la gara è attualmente in corso
        self.duration = 60  # Durata in secondi per le iscrizioni
        self.betting_phase = False  # Indica se le scommesse sono aperte
        self.betting_duration = 30  # Durata in secondi della fase di scommesse
        self.bets = {}  # Scommesse degli utenti {better_id: {"target_id": id, "amount": punti}}
        
    async def start(self):
        """Avvia il gioco marble."""
        await super().start()
        
        # Annuncia l'inizio del gioco
        await self.bot.api.send_chat_message(
            self.channel_id, 
            self.channel_name,
            "🔮 Gioco Marble iniziato! Scrivi !marble per far partecipare la tua biglia alla gara. Hai 60 secondi per iscriverti!"
        )
        
        # Attende il tempo stabilito per le partecipazioni
        await asyncio.sleep(self.duration)
        
        # Inizia la gara se ci sono partecipanti
        if not self.participants:
            await self.bot.api.send_chat_message(
                self.channel_id,
                self.channel_name,
                "Nessuno ha iscritto la propria biglia! La gara è annullata. 😢"
            )
            await self.stop()
            return
            
        # Apri le scommesse se ci sono almeno 2 partecipanti
        if len(self.participants) >= 2:
            await self.open_betting()
        else:
            # Se c'è un solo partecipante, vai direttamente alla gara
            await self.start_race()
        
    async def open_betting(self):
        """Apre la fase di scommesse."""
        self.betting_phase = True
        
        # Crea una lista di partecipanti per scommettere
        participants_list = "\n".join([
            f"{i+1}. {info['username']}" 
            for i, (_, info) in enumerate(self.participants.items())
        ])
        
        # Annuncia l'apertura delle scommesse
        await self.bot.api.send_chat_message(
            self.channel_id,
            self.channel_name,
            f"💰 Fase di scommesse aperta! Scrivi !bet [numero] [punti] per scommettere.\n\nPartecipanti:\n{participants_list}\n\nHai {self.betting_duration} secondi per scommettere!"
        )
        
        # Attende il tempo stabilito per le scommesse
        await asyncio.sleep(self.betting_duration)
        
        # Chiude la fase di scommesse
        self.betting_phase = False
        
        # Annuncia la fine delle scommesse
        await self.bot.api.send_chat_message(
            self.channel_id,
            self.channel_name,
            "💰 Fase di scommesse chiusa! La gara sta per iniziare..."
        )
        
        # Inizia la gara
        await self.start_race()
        
    async def start_race(self):
        """Inizia la gara delle biglie."""
        self.race_active = True
        
        # Inizializza le posizioni
        for user_id in self.participants:
            self.marble_positions[user_id] = 0
            
        # Annuncia l'inizio della gara
        participants_count = len(self.participants)
        await self.bot.api.send_chat_message(
            self.channel_id,
            self.channel_name,
            f"🏁 La gara di biglie inizia! {participants_count} biglie sono sulla linea di partenza!"
        )
        
        # Simula la gara con aggiornamenti periodici
        round_count = 0
        max_rounds = 10  # Limite massimo di round per evitare gare infinite
        
        while self.race_active and round_count < max_rounds:
            round_count += 1
            
            # Muovi le biglie
            await self.update_race()
            
            # Mostra lo stato della gara
            await self.show_race_status()
            
            # Verifica se la gara è finita
            if len(self.finished_marbles) >= len(self.participants) or round_count >= max_rounds:
                self.race_active = False
            else:
                # Piccola pausa tra i round
                await asyncio.sleep(2)
        
        # Annuncia i risultati finali
        await self.announce_results()
        
        # Distribuisci le vincite delle scommesse
        await self.payout_bets()
        
        # Termina il gioco
        await self.stop()
        
    async def update_race(self):
        """Aggiorna le posizioni delle biglie nella gara."""
        # Per ogni biglia ancora in gara
        for user_id, position in list(self.marble_positions.items()):
            if user_id in self.marble_positions and position < self.track_length:
                # Calcola un movimento casuale per la biglia (1-3 spazi)
                move = random.randint(1, 3)
                new_position = position + move
                
                # Aggiorna la posizione
                if new_position >= self.track_length:
                    # La biglia ha raggiunto il traguardo
                    self.marble_positions[user_id] = self.track_length
                    self.finished_marbles.append(user_id)
                else:
                    self.marble_positions[user_id] = new_position
    
    async def show_race_status(self):
        """Mostra lo stato attuale della gara."""
        # Crea una rappresentazione visiva della gara
        status_lines = []
        
        for user_id, position in sorted(self.marble_positions.items(), 
                                       key=lambda x: x[1], 
                                       reverse=True):
            username = self.participants[user_id]["username"]
            progress = position / self.track_length * 100
            
            if user_id in self.finished_marbles:
                # Biglia che ha completato il percorso
                status = f"{username}: 🏁 ARRIVATO! ({progress:.0f}%)"
            else:
                # Biglia ancora in gara
                track = "▒" * position + "░" * (self.track_length - position)
                marble = "🔮"
                status = f"{username}: {marble}{track} ({progress:.0f}%)"
                
            status_lines.append(status)
            
        # Invia l'aggiornamento in chat
        status_message = "\n".join(status_lines)
        await self.bot.api.send_chat_message(
            self.channel_id,
            self.channel_name,
            f"Stato della gara di biglie:\n{status_message}"
        )
        
    async def announce_results(self):
        """Annuncia i risultati finali della gara."""
        if not self.finished_marbles and not self.participants:
            await self.bot.api.send_chat_message(
                self.channel_id,
                self.channel_name,
                "La gara è terminata, ma nessuna biglia ha completato il percorso!"
            )
            return
            
        # Prepara i risultati
        results = []
        position = 1
        
        # Prima i giocatori che hanno completato il percorso
        for user_id in self.finished_marbles:
            username = self.participants[user_id]["username"]
            results.append(f"{position}° posto: {username}")
            position += 1
            
        # Poi i giocatori ancora in gara, ordinati per posizione
        remaining = [(user_id, pos) for user_id, pos in self.marble_positions.items() 
                    if user_id not in self.finished_marbles]
        remaining.sort(key=lambda x: x[1], reverse=True)
        
        for user_id, _ in remaining:
            username = self.participants[user_id]["username"]
            results.append(f"{position}° posto: {username}")
            position += 1
            
        # Invia i risultati in chat
        results_message = "\n".join(results)
        await self.bot.api.send_chat_message(
            self.channel_id,
            self.channel_name,
            f"🏆 Risultati finali della gara di biglie:\n{results_message}"
        )
        
        # Assegna punti ai vincitori
        if self.finished_marbles:
            winner_id = self.finished_marbles[0]
            winner_name = self.participants[winner_id]["username"]
            
            # Assegna punti al vincitore
            await self.bot.update_user_points(
                self.channel_id,
                winner_id,
                100  # Punti da assegnare al vincitore
            )
            
            await self.bot.api.send_chat_message(
                self.channel_id,
                self.channel_name,
                f"Congratulazioni {winner_name}! Hai vinto 100 punti come vincitore della gara di biglie! 🎉"
            )
            
            # Assegna punti anche al secondo e terzo posto, se presenti
            if len(self.finished_marbles) > 1:
                second_id = self.finished_marbles[1]
                second_name = self.participants[second_id]["username"]
                await self.bot.update_user_points(
                    self.channel_id,
                    second_id,
                    50  # Punti da assegnare al secondo posto
                )
                await self.bot.api.send_chat_message(
                    self.channel_id,
                    self.channel_name,
                    f"Complimenti a {second_name}! Hai guadagnato 50 punti per il secondo posto! 🥈"
                )
                
            if len(self.finished_marbles) > 2:
                third_id = self.finished_marbles[2]
                third_name = self.participants[third_id]["username"]
                await self.bot.update_user_points(
                    self.channel_id,
                    third_id,
                    25  # Punti da assegnare al terzo posto
                )
                await self.bot.api.send_chat_message(
                    self.channel_id,
                    self.channel_name,
                    f"Complimenti a {third_name}! Hai guadagnato 25 punti per il terzo posto! 🥉"
                )
    
    async def payout_bets(self):
        """Paga le scommesse vincenti."""
        if not self.bets or not self.finished_marbles:
            return
            
        # Crea una lista dei vincitori delle scommesse
        bet_winners = []
        
        # Per ogni scommessa
        for better_id, bet_info in self.bets.items():
            target_id = bet_info["target_id"]
            amount = bet_info["amount"]
            
            # Verifica se il bersaglio della scommessa è arrivato primo
            if target_id in self.finished_marbles and self.finished_marbles[0] == target_id:
                # Calcola la vincita (2.5x la scommessa)
                winnings = int(amount * 2.5)
                
                # Assegna i punti
                await self.bot.update_user_points(
                    self.channel_id,
                    better_id,
                    winnings
                )
                
                # Aggiungi alla lista dei vincitori
                better_name = bet_info.get("better_name", "Scommettitore")
                bet_winners.append(f"{better_name} (+{winnings} punti)")
            
            # Se il bersaglio è arrivato secondo (1.5x)
            elif len(self.finished_marbles) > 1 and target_id in self.finished_marbles and self.finished_marbles[1] == target_id:
                winnings = int(amount * 1.5)
                await self.bot.update_user_points(
                    self.channel_id,
                    better_id,
                    winnings
                )
                better_name = bet_info.get("better_name", "Scommettitore")
                bet_winners.append(f"{better_name} (+{winnings} punti)")
                
            # Se il bersaglio è arrivato terzo (1.2x)
            elif len(self.finished_marbles) > 2 and target_id in self.finished_marbles and self.finished_marbles[2] == target_id:
                winnings = int(amount * 1.2)
                await self.bot.update_user_points(
                    self.channel_id,
                    better_id,
                    winnings
                )
                better_name = bet_info.get("better_name", "Scommettitore")
                bet_winners.append(f"{better_name} (+{winnings} punti)")
                
        # Annuncia i vincitori delle scommesse, se ce ne sono
        if bet_winners:
            winners_message = "\n".join(bet_winners)
            await self.bot.api.send_chat_message(
                self.channel_id,
                self.channel_name,
                f"💰 Vincitori delle scommesse:\n{winners_message}"
            )
        
    async def handle_message(self, user: dict, message: str):
        """Gestisce i messaggi durante il gioco marble."""
        if not self.active:
            return
            
        message_parts = message.strip().lower().split()
        
        # Gestione comando !marble per partecipare
        if message_parts[0] == "!marble":
            # Non accetta più partecipanti se la gara è già iniziata o se sono in corso le scommesse
            if self.race_active or self.betting_phase:
                return
                
            # Aggiungi l'utente ai partecipanti
            if user["id"] not in self.participants:
                self.participants[user["id"]] = {
                    "id": user["id"],
                    "username": user["username"]
                }
                
                await self.bot.api.send_chat_message(
                    self.channel_id,
                    self.channel_name,
                    f"{user['username']} ha iscritto la sua biglia alla gara! 🔮"
                )
                
        # Gestione comando !bet per scommettere
        elif self.betting_phase and message_parts[0] == "!bet" and len(message_parts) >= 3:
            try:
                # Estrai il numero del partecipante e l'importo della scommessa
                participant_num = int(message_parts[1])
                bet_amount = int(message_parts[2])
                
                # Verifica se il numero del partecipante è valido
                if participant_num < 1 or participant_num > len(self.participants):
                    await self.bot.api.send_chat_message(
                        self.channel_id,
                        self.channel_name,
                        f"{user['username']}, il numero del partecipante non è valido. Usa un numero da 1 a {len(self.participants)}."
                    )
                    return
                    
                # Verifica se l'importo della scommessa è valido
                if bet_amount < 10:
                    await self.bot.api.send_chat_message(
                        self.channel_id,
                        self.channel_name,
                        f"{user['username']}, la scommessa minima è di 10 punti."
                    )
                    return
                    
                # Verifica se l'utente ha abbastanza punti
                user_points = await self.bot.point_system.get_user_points(self.channel_id, user["id"])
                if user_points < bet_amount:
                    await self.bot.api.send_chat_message(
                        self.channel_id,
                        self.channel_name,
                        f"{user['username']}, non hai abbastanza punti per questa scommessa. Hai {user_points} punti."
                    )
                    return
                
                # Ottieni l'ID del partecipante selezionato
                participant_id = list(self.participants.keys())[participant_num - 1]
                participant_name = self.participants[participant_id]["username"]
                
                # Rimuovi i punti scommessi
                await self.bot.update_user_points(self.channel_id, user["id"], -bet_amount)
                
                # Salva la scommessa
                self.bets[user["id"]] = {
                    "target_id": participant_id,
                    "amount": bet_amount,
                    "better_name": user["username"]
                }
                
                # Conferma la scommessa
                await self.bot.api.send_chat_message(
                    self.channel_id,
                    self.channel_name,
                    f"💰 {user['username']} ha scommesso {bet_amount} punti su {participant_name}!"
                )
                
            except (ValueError, IndexError):
                await self.bot.api.send_chat_message(
                    self.channel_id,
                    self.channel_name,
                    f"{user['username']}, formato scommessa non valido. Usa !bet [numero] [punti]"
                )

class PointSystem:
    """Gestisce il sistema di punti del canale."""
    
    def __init__(self, bot):
        self.bot = bot
        
    async def update_points(self, channel_id: int, user_id: int, points: int):
        """Aggiorna i punti di un utente."""
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO channel_points (channel_id, user_id, points)
                VALUES ($1, $2, $3)
                ON CONFLICT (channel_id, user_id)
                DO UPDATE SET points = channel_points.points + $3,
                              last_updated = NOW()
            ''', channel_id, user_id, points)
            
    async def get_user_points(self, channel_id: int, user_id: int):
        """Ottiene i punti di un utente."""
        async with self.bot.db.pool.acquire() as conn:
            points = await conn.fetchval('''
                SELECT points
                FROM channel_points
                WHERE channel_id = $1 AND user_id = $2
            ''', channel_id, user_id)
            
            return points or 0
            
    async def update_watch_time(self, channel_id: int, user_id: int, seconds: int):
        """Aggiorna il tempo di visione di un utente."""
        async with self.bot.db.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO channel_points (channel_id, user_id, watch_time)
                VALUES ($1, $2, $3)
                ON CONFLICT (channel_id, user_id)
                DO UPDATE SET watch_time = channel_points.watch_time + $3,
                              last_updated = NOW()
            ''', channel_id, user_id, seconds)
            
    async def get_top_points(self, channel_id: int, limit: int = 10):
        """Ottiene la classifica dei punti del canale."""
        async with self.bot.db.pool.acquire() as conn:
            top_users = await conn.fetch('''
                SELECT cp.user_id, u.username, cp.points
                FROM channel_points cp
                JOIN users u ON cp.user_id = u.id
                WHERE cp.channel_id = $1
                ORDER BY cp.points DESC
                LIMIT $2
            ''', channel_id, limit)
            
            return top_users

class M4Bot:
    """Classe principale del bot."""
    
    def __init__(self):
        self.db = Database()
        self.api = None
        self.command_handler = None
        self.point_system = None
        self.kick_channel_points = None  # Nuovo sistema di punti canale di Kick
        self.active_games = {}
        self.timed_tasks = {}
        self.start_time = time.time()
        self.channels = {}  # Dizionario per tracciare i canali connessi
        self.monitor = None  # Sistema di monitoraggio integrato
        
    async def initialize(self):
        """Inizializza il bot e si connette alle risorse necessarie."""
        try:
            # Connessione al database
            await self.db.connect()
            
            # Inizializzazione dell'API
            self.api = KickApi(self.db)
            await self.api.create_session()
            
            # Inizializzazione del gestore comandi
            self.command_handler = CommandHandler(self)
            
            # Inizializzazione del sistema punti
            self.point_system = PointSystem(self)
            
            # Inizializzazione del sistema di punti canale di Kick
            self.kick_channel_points = KickChannelPoints(self)
            await self.kick_channel_points.setup_database()
            
            # Inizializzazione del sistema di monitoraggio integrato
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                     "config", "monitoring.json")
            schema_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 
                                    "config", "schemas")
            
            self.monitor = IntegratedMonitor(config_path, schema_dir)
            await self.monitor.start()
            logger.info("Sistema di monitoraggio integrato avviato")
            
            logger.info("Inizializzazione del bot completata")
            return True
        except Exception as e:
            logger.error(f"Errore durante l'inizializzazione del bot: {e}")
            return False
            
    async def shutdown(self):
        """Chiude tutte le connessioni e risorse."""
        if self.api:
            await self.api.close_session()
            
        # Ferma tutti i task pianificati
        for task in self.timed_tasks.values():
            if not task.done():
                task.cancel()
                
        # Ferma tutti i tracker dei punti canale
        if self.kick_channel_points:
            for channel_id in list(self.kick_channel_points.update_tasks.keys()):
                await self.kick_channel_points.stop_points_tracker(channel_id)
        
        # Ferma il sistema di monitoraggio integrato
        if self.monitor:
            await self.monitor.stop()
            logger.info("Sistema di monitoraggio integrato arrestato")
                
        logger.info("Shutdown del bot completato")
        
    async def connect_to_channel(self, channel_id: int, channel_name: str):
        """Connette il bot a un canale e inizia ad ascoltare i messaggi."""
        # Carica i comandi per questo canale
        await self.command_handler.load_commands(channel_id)
        
        # Carica la configurazione dei punti canale e avvia il tracker
        if self.kick_channel_points:
            await self.kick_channel_points.load_channel_config(channel_id)
            await self.kick_channel_points.start_points_tracker(channel_id)
            # Reset dei limiti dei premi per un nuovo stream
            await self.kick_channel_points.reset_reward_limits(channel_id)
        
        # Registra il canale nella lista dei canali connessi
        self.channels[channel_id] = {
            "id": channel_id,
            "name": channel_name,
            "connected_at": datetime.datetime.now(datetime.timezone.utc)
        }
        
        # TODO: Implementare la connessione al WebSocket per ricevere messaggi in tempo reale
        
        logger.info(f"Bot connesso al canale: {channel_name}")
        
    async def update_user_points(self, channel_id: int, user_id: int, points: int):
        """Aggiorna i punti di un utente."""
        await self.point_system.update_points(channel_id, user_id, points)
        
    async def start_game(self, game_type: str, channel_id: int, channel_name: str):
        """Avvia un gioco in chat."""
        # Ferma eventuali giochi attivi
        if channel_id in self.active_games and self.active_games[channel_id].active:
            await self.active_games[channel_id].stop()
            
        # Crea un nuovo gioco
        if game_type.lower() == "dadi":
            game = DiceGame(self, channel_id, channel_name)
        elif game_type.lower() == "marble":
            game = MarbleGame(self, channel_id, channel_name)
        else:
            logger.error(f"Tipo di gioco non supportato: {game_type}")
            return False
            
        self.active_games[channel_id] = game
        await game.start()
        return True
        
    async def register_timed_event(self, channel_id: int, channel_name: str, 
                                  event_name: str, callback: Callable, interval: int):
        """Registra un evento pianificato."""
        # Cancella l'evento precedente con lo stesso nome se esiste
        event_key = f"{channel_id}:{event_name}"
        if event_key in self.timed_tasks:
            if not self.timed_tasks[event_key].done():
                self.timed_tasks[event_key].cancel()
                
        # Crea un nuovo task per l'evento pianificato
        async def timed_event_task():
            while True:
                try:
                    await callback()
                except Exception as e:
                    logger.error(f"Errore nell'esecuzione dell'evento pianificato {event_name}: {e}")
                await asyncio.sleep(interval)
                
        task = asyncio.create_task(timed_event_task())
        self.timed_tasks[event_key] = task
        
        logger.info(f"Evento pianificato registrato: {event_name} ogni {interval} secondi")
        return True
        
    async def unregister_timed_event(self, channel_id: int, event_name: str):
        """Annulla un evento pianificato."""
        event_key = f"{channel_id}:{event_name}"
        if event_key in self.timed_tasks:
            if not self.timed_tasks[event_key].done():
                self.timed_tasks[event_key].cancel()
            del self.timed_tasks[event_key]
            logger.info(f"Evento pianificato annullato: {event_name}")
            return True
        return False
        
    async def log_event(self, channel_id: int, event_type: str, user_id: int = None, data: dict = None):
        """Registra un evento nel database."""
        async with self.db.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO event_logs (channel_id, event_type, user_id, data)
                VALUES ($1, $2, $3, $4)
            ''', channel_id, event_type, user_id, json.dumps(data) if data else None)

    async def check_system_status(self) -> Dict[str, Any]:
        """
        Verifica lo stato di tutte le connessioni e integrazioni
        
        Returns:
            Dict: Stato del sistema
        """
        status = {
            "bot": {
                "version": VERSION,
                "uptime": int(time.time() - self.start_time) if hasattr(self, 'start_time') else 0,
                "running": True,
                "channels_connected": len(self.channels) if hasattr(self, 'channels') else 0
            },
            "integrations": {
                "discord": {
                    "connected": False,
                    "status": "Non inizializzato",
                    "channels": 0
                },
                "obs": {
                    "connected": False,
                    "status": "Non inizializzato",
                    "version": "N/A"
                },
                "webhooks": {
                    "enabled": False,
                    "count": 0
                }
            },
            "database": {
                "connected": self.db.pool is not None if hasattr(self, 'db') else False,
                "status": "Connesso" if self.db.pool is not None else "Disconnesso" if hasattr(self, 'db') else "Non inizializzato"
            },
            "monitoring": {
                "active": self.monitor is not None and self.monitor.running if hasattr(self, 'monitor') else False,
                "metrics_count": len(self.monitor.metrics) if hasattr(self, 'monitor') and self.monitor else 0,
                "services_monitored": len(self.monitor.services_status) if hasattr(self, 'monitor') and self.monitor else 0,
                "configs_validated": len(self.monitor.config_status) if hasattr(self, 'monitor') and self.monitor else 0
            }
        }
        
        # Verifica lo stato di Discord
        if hasattr(self, 'discord_connector'):
            discord_connected = await self.discord_connector.is_connected()
            status["integrations"]["discord"] = {
                "connected": discord_connected,
                "status": "Connesso" if discord_connected else "Disconnesso",
                "channels": len(self.discord_connector.sync_channels) if discord_connected else 0
            }
        
        # Verifica lo stato di OBS
        if hasattr(self, 'obs_connector'):
            obs_connected = self.obs_connector.is_connected()
            status["integrations"]["obs"] = {
                "connected": obs_connected,
                "status": "Connesso" if obs_connected else "Disconnesso",
                "version": self.obs_connector.version if obs_connected else "N/A"
            }
        
        # Verifica lo stato dei webhook
        if hasattr(self, 'webhook_handler'):
            webhooks = self.webhook_handler.get_webhooks()
            status["integrations"]["webhooks"] = {
                "enabled": True,
                "count": len(webhooks)
            }
        
        # Aggiungi le metriche di sistema dal monitor se attivo
        if self.monitor and self.monitor.running:
            # Aggiungi le metriche principali
            if "system.cpu.usage_percent" in self.monitor.metrics:
                status["monitoring"]["cpu_usage"] = self.monitor.metrics["system.cpu.usage_percent"].value
            
            if "system.memory.usage_percent" in self.monitor.metrics:
                status["monitoring"]["memory_usage"] = self.monitor.metrics["system.memory.usage_percent"].value
            
            if "system.disk.usage_percent" in self.monitor.metrics:
                status["monitoring"]["disk_usage"] = self.monitor.metrics["system.disk.usage_percent"].value
        
        return status

    async def handle_message(self, channel_id: int, channel_name: str, user: dict, message: str):
        """Gestisce un messaggio ricevuto."""
        # Controlla se c'è un gioco attivo in questo canale
        if channel_id in self.active_games and self.active_games[channel_id].active:
            # Passa il messaggio al gestore del gioco
            await self.active_games[channel_id].handle_message(user, message)
            
            # Controlla se è un comando !bet e il gioco è Marble
            msg_parts = message.strip().lower().split()
            if len(msg_parts) > 0 and msg_parts[0] == "!bet" and isinstance(self.active_games[channel_id], MarbleGame):
                # Questo messaggio è già gestito dal gioco, qui possiamo fare log o altre operazioni supplementari
                logger.info(f"Scommessa ricevuta da {user['username']} nel canale {channel_name}")
            
            # Se è un comando, non elaborarlo di nuovo
            if message.startswith("!"):
                return
        
        # Tenta di gestire il messaggio come un comando
        await self.command_handler.handle_command(channel_id, channel_name, user, message)

async def main():
    """Funzione principale per l'avvio del bot."""
    # Inizializza il bot
    bot = M4Bot()
    await bot.initialize()
    
    # Crea un'app Quart per le API
    from quart import Quart, request, jsonify
    app = Quart(__name__)
    
    @app.route('/api/system/status', methods=['GET'])
    async def api_system_status():
        """Endpoint per ottenere lo stato del sistema."""
        status = await bot.check_system_status()
        return jsonify(status)
    
    # Altri endpoint API...
    
    # Avvia il server API
    import uvicorn
    import asyncio
    from hypercorn.asyncio import serve
    from hypercorn.config import Config
    
    config = Config()
    config.bind = ["0.0.0.0:5000"]
    
    # Crea un task per il server API
    api_server = asyncio.create_task(serve(app, config))
    
    try:
        # Mantieni il bot in esecuzione
        await asyncio.gather(api_server)
    except KeyboardInterrupt:
        # Gestisci l'interruzione del programma
        logger.info("Interruzione del bot rilevata")
    finally:
        # Chiudi le connessioni
        await bot.shutdown()
        logger.info("Bot terminato con successo")

if __name__ == "__main__":
    try:
        # Controlla se esiste la directory dei log
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        
        # Avvia il loop asincrono
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Errore critico durante l'avvio del bot: {e}")
        sys.exit(1)
