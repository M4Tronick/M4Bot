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
        self.pool = None
        
    async def connect(self):
        """Crea un pool di connessioni al database PostgreSQL."""
        try:
            self.pool = await asyncpg.create_pool(
                user=DB_USER,
                password=DB_PASS,
                database=DB_NAME,
                host=DB_HOST
            )
            logger.info("Connessione al database stabilita")
            
            # Inizializza le tabelle se non esistono
            await self._initialize_tables()
        except Exception as e:
            logger.error(f"Errore nella connessione al database: {e}")
            raise
            
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
    """Gestisce la crittografia dei dati sensibili."""
    
    def __init__(self, key: str):
        # Genera una chiave Fernet da una stringa
        key_bytes = hashlib.sha256(key.encode()).digest()
        self.cipher_suite = Fernet(base64.urlsafe_b64encode(key_bytes))
        
    def encrypt(self, data: str) -> str:
        """Cripta una stringa."""
        return self.cipher_suite.encrypt(data.encode()).decode()
        
    def decrypt(self, encrypted_data: str) -> str:
        """Decripta una stringa criptata."""
        return self.cipher_suite.decrypt(encrypted_data.encode()).decode()

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
        self.active_games = {}
        self.timed_tasks = {}
        
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
                
        logger.info("Shutdown del bot completato")
        
    async def connect_to_channel(self, channel_id: int, channel_name: str):
        """Connette il bot a un canale e inizia ad ascoltare i messaggi."""
        # Carica i comandi per questo canale
        await self.command_handler.load_commands(channel_id)
        
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

async def main():
    """Funzione principale per l'avvio del bot."""
    bot = M4Bot()
    if await bot.initialize():
        try:
            # Esempio: connessione a un canale
            # await bot.connect_to_channel(1, "nome_canale")
            
            # Mantieni il bot in esecuzione
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Interruzione da tastiera ricevuta, arresto in corso...")
        except Exception as e:
            logger.error(f"Errore durante l'esecuzione del bot: {e}")
        finally:
            await bot.shutdown()
    else:
        logger.error("Impossibile inizializzare il bot, arresto in corso...")

if __name__ == "__main__":
    try:
        # Controlla se esiste la directory dei log
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        
        # Avvia il loop asincrono
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Errore critico durante l'avvio del bot: {e}")
        sys.exit(1)
