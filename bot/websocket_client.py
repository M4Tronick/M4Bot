#!/usr/bin/env python3
"""
Gestione delle connessioni WebSocket con Kick.com
Consente di ricevere eventi in tempo reale dalla piattaforma.
"""

import json
import logging
import asyncio
import time
from typing import Dict, List, Optional, Any, Callable

import websockets
import aiohttp

# Configura il logger
logger = logging.getLogger('WebSocketClient')

class KickWebSocketClient:
    """Cliente WebSocket per connettersi agli endpoint di Kick.com."""
    
    # URL del WebSocket di Kick
    WEBSOCKET_URL = "wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c"
    
    def __init__(self, bot):
        self.bot = bot
        self.ws = None
        self.connected = False
        self.channel_subscriptions = {}
        self.message_handlers = {}
        self.reconnect_task = None
        self.last_pong = 0
        self.socket_key = ""
        
    async def connect(self):
        """Stabilisce una connessione WebSocket con Kick."""
        try:
            # Ottieni un socket_key valido dall'API prima della connessione
            self.socket_key = await self._get_socket_key()
            if not self.socket_key:
                logger.error("Impossibile ottenere una socket_key valida")
                return False
                
            # Connessione al WebSocket
            self.ws = await websockets.connect(
                f"{self.WEBSOCKET_URL}?protocol=7&client=js&version=7.4.0&flash=false"
            )
            
            # Invia il messaggio di connessione con la socket_key
            await self._send_message({
                "event": "pusher:subscribe",
                "data": {
                    "auth": "",
                    "channel": "private-app.eb1d5f283081a78b932c"
                }
            })
            
            # Avvia il ping per mantenere viva la connessione
            self.last_pong = time.time()
            asyncio.create_task(self._ping_handler())
            
            # Avvia il task di ascolto dei messaggi
            asyncio.create_task(self._message_listener())
            
            self.connected = True
            logger.info("Connessione WebSocket stabilita con Kick")
            
            # Avvia il task di controllo della connessione
            self.reconnect_task = asyncio.create_task(self._connection_watchdog())
            
            return True
        except Exception as e:
            logger.error(f"Errore durante la connessione WebSocket: {e}")
            return False
            
    async def disconnect(self):
        """Chiude la connessione WebSocket."""
        if self.ws:
            await self.ws.close()
            self.ws = None
            
        if self.reconnect_task and not self.reconnect_task.done():
            self.reconnect_task.cancel()
            
        self.connected = False
        logger.info("Disconnesso dal WebSocket di Kick")
        
    async def subscribe_to_channel_chat(self, channel_name: str, callback: Callable):
        """Sottoscrive agli eventi di chat di un canale specifico."""
        channel_id = f"channel.{channel_name}.chat"
        
        # Registra il callback per questo canale
        self.message_handlers[channel_id] = callback
        
        # Invia la richiesta di sottoscrizione
        await self._send_message({
            "event": "pusher:subscribe",
            "data": {
                "auth": "",
                "channel": channel_id
            }
        })
        
        self.channel_subscriptions[channel_name] = channel_id
        logger.info(f"Sottoscritto al canale chat: {channel_name}")
        
    async def unsubscribe_from_channel(self, channel_name: str):
        """Annulla la sottoscrizione da un canale."""
        if channel_name in self.channel_subscriptions:
            channel_id = self.channel_subscriptions[channel_name]
            
            # Rimuovi l'handler
            if channel_id in self.message_handlers:
                del self.message_handlers[channel_id]
                
            # Invia la richiesta di cancellazione della sottoscrizione
            await self._send_message({
                "event": "pusher:unsubscribe",
                "data": {
                    "channel": channel_id
                }
            })
            
            del self.channel_subscriptions[channel_name]
            logger.info(f"Cancellata la sottoscrizione al canale: {channel_name}")
            
    async def _send_message(self, message: Dict):
        """Invia un messaggio attraverso la connessione WebSocket."""
        if not self.ws:
            logger.error("Tentativo di invio messaggio senza connessione WebSocket")
            return False
            
        try:
            await self.ws.send(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Errore nell'invio del messaggio WebSocket: {e}")
            self.connected = False
            return False
            
    async def _message_listener(self):
        """Ascolta i messaggi in arrivo dalla connessione WebSocket."""
        if not self.ws:
            return
            
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    
                    # Gestisci i pong per mantenere viva la connessione
                    if data.get("event") == "pusher:pong":
                        self.last_pong = time.time()
                        continue
                        
                    # Gestisci le risposte alle sottoscrizioni
                    if data.get("event") == "pusher_internal:subscription_succeeded":
                        channel = data.get("channel", "")
                        logger.info(f"Sottoscrizione completata per il canale: {channel}")
                        continue
                        
                    # Gestisci i messaggi degli eventi
                    channel = data.get("channel", "")
                    event = data.get("event", "")
                    
                    if channel and event and channel in self.message_handlers:
                        # Estrai i dati dell'evento
                        try:
                            event_data = json.loads(data.get("data", "{}"))
                            
                            # Chiama il callback registrato per questo canale
                            handler = self.message_handlers[channel]
                            asyncio.create_task(handler(event, event_data))
                        except json.JSONDecodeError:
                            logger.error(f"Errore nel parsing dei dati dell'evento: {data.get('data')}")
                    
                except json.JSONDecodeError:
                    logger.error(f"Messaggio WebSocket non valido: {message}")
                except Exception as e:
                    logger.error(f"Errore nella gestione del messaggio WebSocket: {e}")
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Connessione WebSocket chiusa")
            self.connected = False
        except Exception as e:
            logger.error(f"Errore nell'ascolto dei messaggi WebSocket: {e}")
            self.connected = False
            
    async def _ping_handler(self):
        """Invia ping periodici per mantenere viva la connessione."""
        while self.ws and not self.ws.closed:
            try:
                await self._send_message({
                    "event": "pusher:ping",
                    "data": {}
                })
                await asyncio.sleep(30)  # Invia un ping ogni 30 secondi
            except Exception as e:
                logger.error(f"Errore nell'invio del ping: {e}")
                break
                
    async def _connection_watchdog(self):
        """Monitora la connessione e riconnette se necessario."""
        while True:
            await asyncio.sleep(60)  # Controlla ogni minuto
            
            # Se non siamo connessi, prova a riconnetterti
            if not self.connected or (self.ws and self.ws.closed):
                logger.warning("Connessione WebSocket persa, tentativo di riconnessione...")
                await self.connect()
                
                # Se la riconnessione ha avuto successo, ristabilisci le sottoscrizioni
                if self.connected:
                    for channel_name in list(self.channel_subscriptions.keys()):
                        channel_id = self.channel_subscriptions[channel_name]
                        callback = self.message_handlers.get(channel_id)
                        if callback:
                            await self.subscribe_to_channel_chat(channel_name, callback)
                            
            # Controlla se abbiamo ricevuto un pong negli ultimi 2 minuti
            if time.time() - self.last_pong > 120:
                logger.warning("Nessun pong ricevuto di recente, reconnessione...")
                await self.disconnect()
                await self.connect()
                
    async def _get_socket_key(self):
        """Ottiene una socket_key dall'API di Kick."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://kick.com/api/v2/channels") as response:
                    if response.status == 200:
                        data = await response.json()
                        # La socket_key dovrebbe essere inclusa nella risposta
                        # Questa è una semplificazione, potrebbe essere necessario estrarre 
                        # la chiave da un'altra chiamata API
                        return data.get("socket_key", "")
            return ""
        except Exception as e:
            logger.error(f"Errore nell'ottenimento della socket_key: {e}")
            return ""
            
    async def handle_chat_message(self, channel_name: str, message_data: Dict):
        """Gestisce un messaggio di chat ricevuto dal WebSocket."""
        # Ottieni le informazioni dell'utente e del messaggio
        try:
            user = {
                "id": message_data.get("sender", {}).get("id"),
                "username": message_data.get("sender", {}).get("username"),
                "is_moderator": message_data.get("sender", {}).get("is_moderator", False),
                "is_subscriber": message_data.get("sender", {}).get("is_subscriber", False)
            }
            
            content = message_data.get("content", "")
            
            # Trova il canale nel database
            async with self.bot.db.pool.acquire() as conn:
                channel = await conn.fetchrow('''
                    SELECT id FROM channels WHERE name = $1
                ''', channel_name)
                
                if not channel:
                    logger.warning(f"Ricevuto messaggio per canale non registrato: {channel_name}")
                    return
                    
                channel_id = channel["id"]
                
                # Logga il messaggio nel database
                await conn.execute('''
                    INSERT INTO chat_messages 
                    (channel_id, user_id, username, content, is_command, created_at)
                    VALUES ($1, $2, $3, $4, $5, NOW())
                ''', channel_id, user["id"], user["username"], content, content.startswith("!"))
                
            # Se è un comando, passalo al gestore comandi
            if content.startswith("!"):
                await self.bot.command_handler.handle_command(
                    channel_id, 
                    channel_name, 
                    user, 
                    content
                )
                
            # Se c'è un gioco attivo, passa il messaggio al gestore del gioco
            if channel_id in self.bot.active_games and self.bot.active_games[channel_id].active:
                await self.bot.active_games[channel_id].handle_message(user, content)
                
        except Exception as e:
            logger.error(f"Errore nella gestione del messaggio di chat: {e}")
