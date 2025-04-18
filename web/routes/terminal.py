#!/usr/bin/env python3
"""
M4Bot - Terminal Routes
Gestione del terminale SSH per il pannello di controllo
"""

import os
import json
import uuid
import logging
import asyncio
import datetime
from typing import Dict, List, Optional, Any

import paramiko
import websockets
from quart import Blueprint, render_template, request, jsonify, websocket
from quart_auth import login_required, current_user

# Setup logging
logger = logging.getLogger('m4bot.terminal')

# Blueprint
terminal_bp = Blueprint('terminal', __name__)

# Sessioni SSH attive
active_sessions: Dict[str, Dict[str, Any]] = {}

# Classe per gestire la connessione SSH
class SSHTerminal:
    def __init__(self, host: str, port: int = 22, username: str = None, 
                 password: str = None, key_data: str = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_data = key_data
        self.client = None
        self.channel = None
        self.session_id = str(uuid.uuid4())
        
    async def connect(self) -> bool:
        """Stabilisce una connessione SSH"""
        try:
            # Crea client SSH
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Prepara l'autenticazione
            connect_kwargs = {
                'hostname': self.host,
                'port': self.port,
                'username': self.username,
                'timeout': 10
            }
            
            # Usa chiave o password
            if self.key_data:
                key_file = paramiko.RSAKey.from_private_key(
                    file_obj=io.StringIO(self.key_data), 
                    password=None
                )
                connect_kwargs['pkey'] = key_file
            elif self.password:
                connect_kwargs['password'] = self.password
            
            # Connessione
            self.client.connect(**connect_kwargs)
            
            # Apri canale e crea shell interattiva
            self.channel = self.client.invoke_shell(term='xterm')
            self.channel.setblocking(0)
            
            logger.info(f"Connessione SSH stabilita con {self.host} (utente: {self.username})")
            return True
            
        except Exception as e:
            logger.error(f"Errore nella connessione SSH a {self.host}: {e}")
            if self.client:
                self.client.close()
            return False
    
    async def disconnect(self) -> None:
        """Chiude la connessione SSH"""
        try:
            if self.channel:
                self.channel.close()
            if self.client:
                self.client.close()
            logger.info(f"Connessione SSH a {self.host} terminata")
        except Exception as e:
            logger.error(f"Errore durante la disconnessione da {self.host}: {e}")
    
    async def resize(self, rows: int, cols: int) -> None:
        """Ridimensiona il terminale"""
        if self.channel:
            self.channel.resize_pty(width=cols, height=rows)
    
    async def send(self, data: str) -> None:
        """Invia dati al terminale SSH"""
        if self.channel:
            self.channel.send(data)
    
    async def recv(self, size: int = 1024) -> Optional[str]:
        """Riceve dati dal terminale SSH"""
        if not self.channel:
            return None
        
        if self.channel.recv_ready():
            return self.channel.recv(size).decode('utf-8', errors='replace')
        return None

# Gestori delle sessioni SSH
async def create_session(host_id: str, username: str, auth_method: str, 
                         password: str = None, ssh_key: str = None) -> Optional[Dict[str, Any]]:
    """Crea una nuova sessione SSH"""
    try:
        # In un'implementazione reale, verifica l'host_id nel database
        # Per ora, usiamo un host hardcoded per test
        host = get_host_by_id(host_id)
        if not host:
            logger.error(f"Host con ID {host_id} non trovato")
            return None
        
        # Crea sessione SSH
        terminal = SSHTerminal(
            host=host['ip'],
            port=host.get('port', 22),
            username=username,
            password=password if auth_method == 'password' else None,
            key_data=ssh_key if auth_method == 'key' else None
        )
        
        # Connetti
        if await terminal.connect():
            # Registra sessione attiva
            session = {
                'id': terminal.session_id,
                'terminal': terminal,
                'host_id': host_id,
                'host_name': host['name'],
                'host_ip': host['ip'],
                'username': username,
                'start_time': datetime.datetime.now(),
                'last_activity': datetime.datetime.now(),
                'user_id': current_user.id if hasattr(current_user, 'id') else 'anonymous'
            }
            
            active_sessions[terminal.session_id] = session
            logger.info(f"Nuova sessione creata: {terminal.session_id} per {username}@{host['ip']}")
            return session
        
        return None
    
    except Exception as e:
        logger.error(f"Errore nella creazione della sessione: {e}")
        return None

def get_host_by_id(host_id: str) -> Optional[Dict[str, Any]]:
    """Recupera informazioni host dal database"""
    # In un'implementazione reale, questa funzione dovrebbe
    # interrogare il database per ottenere le informazioni sull'host
    # Per ora, restituiamo alcuni host hardcoded
    hosts = {
        "1": {"id": "1", "name": "Principale", "ip": "127.0.0.1", "port": 22},
        "2": {"id": "2", "name": "Web Server", "ip": "192.168.1.10", "port": 22},
        "3": {"id": "3", "name": "Database", "ip": "192.168.1.11", "port": 22}
    }
    return hosts.get(host_id)

def get_monitored_hosts() -> List[Dict[str, Any]]:
    """Recupera la lista degli host monitorati"""
    # In un'implementazione reale, questa funzione dovrebbe
    # recuperare gli host dal database
    return [
        {"id": "1", "name": "Principale", "ip": "127.0.0.1", "port": 22},
        {"id": "2", "name": "Web Server", "ip": "192.168.1.10", "port": 22},
        {"id": "3", "name": "Database", "ip": "192.168.1.11", "port": 22}
    ]

def format_duration(start_time: datetime.datetime) -> str:
    """Formatta la durata della sessione"""
    duration = datetime.datetime.now() - start_time
    hours, remainder = divmod(duration.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def get_session_info() -> List[Dict[str, Any]]:
    """Recupera informazioni sulle sessioni attive"""
    sessions_info = []
    for session_id, session in active_sessions.items():
        sessions_info.append({
            "id": session_id,
            "username": session["username"],
            "host_name": session["host_name"],
            "host_id": session["host_id"],
            "start_time": session["start_time"].isoformat(),
            "duration": format_duration(session["start_time"]),
            "user_id": session["user_id"]
        })
    return sessions_info

async def terminate_session(session_id: str) -> bool:
    """Termina una sessione SSH attiva"""
    if session_id in active_sessions:
        session = active_sessions[session_id]
        await session["terminal"].disconnect()
        del active_sessions[session_id]
        logger.info(f"Sessione {session_id} terminata")
        return True
    return False

# Pulizia sessioni scadute
async def cleanup_sessions() -> None:
    """Pulisce sessioni inattive da troppo tempo"""
    now = datetime.datetime.now()
    to_remove = []
    
    for session_id, session in active_sessions.items():
        # Sessioni inattive da più di 30 minuti
        if (now - session["last_activity"]).total_seconds() > 1800:
            await session["terminal"].disconnect()
            to_remove.append(session_id)
    
    for session_id in to_remove:
        del active_sessions[session_id]
        logger.info(f"Sessione {session_id} rimossa per inattività")

# Routes
@terminal_bp.route('/terminal')
@login_required
async def terminal_page():
    """Pagina del terminale SSH"""
    hosts = get_monitored_hosts()
    return await render_template('tools/terminal.html', hosts=hosts, page="tools")

@terminal_bp.route('/api/terminal/sessions')
@login_required
async def get_sessions():
    """API per ottenere le sessioni attive"""
    return jsonify({"success": True, "sessions": get_session_info()})

@terminal_bp.route('/api/terminal/terminate', methods=['POST'])
@login_required
async def terminate_session_api():
    """API per terminare una sessione"""
    data = await request.get_json()
    session_id = data.get('session_id')
    
    if not session_id:
        return jsonify({"success": False, "error": "ID sessione mancante"})
    
    result = await terminate_session(session_id)
    return jsonify({"success": result})

# WebSocket per il terminale
@terminal_bp.websocket('/api/terminal/connect')
async def terminal_ws():
    """WebSocket per la comunicazione con il terminale SSH"""
    terminal_instance = None
    session_id = None
    
    try:
        while True:
            # Ricevi messaggio
            message = await websocket.receive()
            data = json.loads(message)
            message_type = data.get('type')
            
            # Gestisci i diversi tipi di messaggi
            if message_type == 'connect':
                # Crea nuova sessione
                host_id = data.get('host_id')
                username = data.get('username')
                auth_method = data.get('auth_method')
                password = data.get('password')
                ssh_key = data.get('ssh_key')
                
                session = await create_session(
                    host_id=host_id,
                    username=username,
                    auth_method=auth_method,
                    password=password,
                    ssh_key=ssh_key
                )
                
                if session:
                    terminal_instance = session['terminal']
                    session_id = terminal_instance.session_id
                    
                    # Configura dimensioni terminale
                    term_data = data.get('terminal', {})
                    rows = term_data.get('rows', 24)
                    cols = term_data.get('cols', 80)
                    await terminal_instance.resize(rows, cols)
                    
                    # Notifica successo
                    await websocket.send(json.dumps({
                        'type': 'connect_success',
                        'host_name': session['host_name'],
                        'host_ip': session['host_ip']
                    }))
                    
                    # Avvia un task per leggere l'output
                    asyncio.create_task(
                        read_terminal_output(terminal_instance, session_id)
                    )
                else:
                    # Notifica errore
                    await websocket.send(json.dumps({
                        'type': 'connect_error',
                        'error': 'Impossibile stabilire la connessione SSH'
                    }))
            
            elif message_type == 'data':
                # Invia dati al terminale
                if terminal_instance:
                    content = data.get('content', '')
                    await terminal_instance.send(content)
                    
                    # Aggiorna timestamp ultima attività
                    if session_id in active_sessions:
                        active_sessions[session_id]['last_activity'] = datetime.datetime.now()
            
            elif message_type == 'resize':
                # Ridimensiona terminale
                if terminal_instance:
                    rows = data.get('rows', 24)
                    cols = data.get('cols', 80)
                    await terminal_instance.resize(rows, cols)
    
    except websockets.exceptions.ConnectionClosed:
        logger.info("Connessione WebSocket chiusa")
    
    except Exception as e:
        logger.error(f"Errore nella gestione WebSocket: {e}")
        try:
            await websocket.send(json.dumps({
                'type': 'error',
                'error': str(e)
            }))
        except:
            pass
    
    finally:
        # Pulisci in caso di errore o disconnessione
        if terminal_instance and session_id in active_sessions:
            await terminal_instance.disconnect()
            del active_sessions[session_id]
            logger.info(f"Sessione {session_id} terminata (WebSocket chiuso)")

async def read_terminal_output(terminal, session_id):
    """Task per leggere l'output dal terminale e inviarlo al client"""
    try:
        while session_id in active_sessions:
            # Leggi dati dal terminale
            data = await terminal.recv()
            
            if data:
                # Invia dati al client WebSocket
                await websocket.send(json.dumps({
                    'type': 'data',
                    'content': data
                }))
            
            # Piccola pausa per evitare di consumare troppe risorse
            await asyncio.sleep(0.05)
    
    except Exception as e:
        logger.error(f"Errore nella lettura dell'output del terminale: {e}")
        try:
            await websocket.send(json.dumps({
                'type': 'error',
                'error': str(e)
            }))
        except:
            pass

# Inizializzazione del blueprint
def init_terminal_bp(app):
    """Inizializza il blueprint del terminale"""
    app.register_blueprint(terminal_bp)
    
    # Avvia task di pulizia delle sessioni
    @app.before_serving
    async def setup_cleanup():
        app.add_background_task(periodic_cleanup)
    
    logger.info("Blueprint del terminale inizializzato")

async def periodic_cleanup():
    """Task periodico per pulire le sessioni SSH scadute"""
    while True:
        await cleanup_sessions()
        await asyncio.sleep(300)  # Ogni 5 minuti 