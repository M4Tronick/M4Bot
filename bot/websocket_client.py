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
        self.ping_interval = 30  # Secondi tra un ping e l'altro
        
    async def connect(self):
        """Stabilisce una connessione WebSocket con Kick."""
        try:
            self.ws = await websockets.connect(self.WEBSOCKET_URL)
            self.connected = True
            self.last_pong = time.time()
            
            # Invia un messaggio di connessione
            await self._send_message({
                "event": "pusher:connection",
                "data": {}
            })
            
            # Avvia il ping periodico
            asyncio.create_task(self._ping_loop())
            
            # Avvia il task di ascolto
            self.reconnect_task = asyncio.create_task(self._listen())
            
            logger.info("Connesso al WebSocket di Kick")
            return True
        except Exception as e:
            logger.error(f"Errore nella connessione al WebSocket: {e}")
            self.connected = False
            return False
            
    async def _ping_loop(self):
        """Invia ping periodici per mantenere attiva la connessione."""
        try:
            while self.connected:
                await asyncio.sleep(self.ping_interval)
                
                # Invia un ping solo se connessi
                if self.ws and self.connected:
                    await self._send_message({
                        "event": "pusher:ping",
                        "data": {}
                    })
                    
                    # Se non riceviamo un pong entro 30 secondi, riconnetti
                    if time.time() - self.last_pong > 60:
                        logger.warning("Nessun pong ricevuto, riconnessione...")
                        asyncio.create_task(self._reconnect())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Errore nel ping loop: {e}")
            
    async def _listen(self):
        """Ascolta i messaggi in arrivo dal WebSocket."""
        try:
            while self.connected:
                try:
                    message = await self.ws.recv()
                    await self._handle_message(message)
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Connessione WebSocket chiusa, riconnessione...")
                    self.connected = False
                    await self._reconnect()
                    break
        except asyncio.CancelledError:
            logger.info("Task di ascolto WebSocket cancellato")
        except Exception as e:
            logger.error(f"Errore nell'ascolto WebSocket: {e}")
            self.connected = False
            await self._reconnect()
            
    async def _reconnect(self):
        """Tenta di ristabilire la connessione WebSocket."""
        # Evita riconnessioni multiple
        if not self.connected:
            logger.info("Tentativo di riconnessione al WebSocket...")
            
            # Attendi un po' prima di riconnetterti
            await asyncio.sleep(5)
            
            # Riconnetti
            success = await self.connect()
            
            if success:
                # Rinnova tutte le sottoscrizioni ai canali
                for channel_name, channel_id in self.channel_subscriptions.items():
                    handler = self.message_handlers.get(channel_id)
                    if handler:
                        await self.subscribe_to_channel_chat(channel_name, handler)
                        
                logger.info("Riconnessione al WebSocket riuscita")
            else:
                logger.error("Riconnessione al WebSocket fallita, ritentativo tra 30 secondi")
                await asyncio.sleep(30)
                asyncio.create_task(self._reconnect())
            
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
        """Invia un messaggio tramite la connessione WebSocket."""
        if self.ws and self.connected:
        try:
            await self.ws.send(json.dumps(message))
            return True
        except Exception as e:
            logger.error(f"Errore nell'invio del messaggio WebSocket: {e}")
            self.connected = False
                await self._reconnect()
                return False
        else:
            logger.warning("Tentativo di invio di un messaggio senza una connessione WebSocket attiva")
            return False
            
    async def _handle_message(self, message_str: str):
        """Gestisce i messaggi ricevuti dal WebSocket."""
        try:
            message = json.loads(message_str)
            event = message.get("event", "")
            channel = message.get("channel", "")
            
            # Gestisce i messaggi di sistema
            if event == "pusher:connection_established":
                # Salva la chiave del socket
                data = json.loads(message.get("data", "{}"))
                self.socket_key = data.get("socket_id", "")
                logger.info(f"Connessione WebSocket stabilita, socket_id: {self.socket_key}")
                
            elif event == "pusher:pong":
                self.last_pong = time.time()
                
            # Gestisce eventi di chat
            elif event == "App\\Events\\ChatMessageSentEvent" and channel in self.message_handlers:
                callback = self.message_handlers[channel]
                data = json.loads(message.get("data", "{}"))
                await callback(channel, data)
                
            # Gestisce eventi di sottoscrizione
            elif event == "pusher_internal:subscription_succeeded":
                logger.info(f"Sottoscrizione al canale {channel} riuscita")
                
            # Altri tipi di eventi
            elif event and event != "pusher:pong":
                logger.debug(f"Ricevuto evento: {event} dal canale: {channel}")
                
        except json.JSONDecodeError:
            logger.error(f"Errore nel parsing del messaggio JSON: {message_str}")
        except Exception as e:
            logger.error(f"Errore nella gestione del messaggio: {e}")
            
    async def handle_chat_message(self, channel_name: str, message_data: Dict):
        """Gestisce un messaggio di chat ricevuto dal WebSocket."""
        # Ottieni le informazioni dell'utente e del messaggio
        try:
            user = {
                "id": message_data.get("sender", {}).get("id"),
                "username": message_data.get("sender", {}).get("username"),
                "is_moderator": message_data.get("sender", {}).get("is_moderator", False),
                "is_subscriber": message_data.get("sender", {}).get("is_subscriber", False),
                "is_vip": "VIP" in message_data.get("sender", {}).get("follower_badges", [])
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
                
            # Gestisci i punti canale per l'utente
            if hasattr(self.bot, "kick_channel_points") and self.bot.kick_channel_points:
                await self.bot.kick_channel_points.handle_chat_message(
                    channel_id, 
                    int(user["id"]), 
                    user["username"],
                    user["is_subscriber"],
                    user["is_moderator"],
                    user["is_vip"]
                )
                
            # Se è un comando, passalo al gestore comandi
            if content.startswith("!"):
                command_parts = content.split(" ", 1)
                command = command_parts[0][1:].lower()  # Rimuovi il ! e converti in minuscolo
                
                # Gestisci i comandi del sistema di punti canale
                if command in ["punti", "points"]:
                    # Ottieni i punti dell'utente
                    points = await self.bot.point_system.get_user_points(channel_id, int(user["id"]))
                    points_name = self.bot.kick_channel_points.config.points_name
                    
                    # Invia un messaggio con i punti dell'utente
                    message = f"{user['username']}, hai {points} {points_name}!"
                    await self.bot.api.send_chat_message(channel_id, channel_name, message)
                    return
                    
                elif command in ["classifica", "leaderboard", "top"]:
                    # Ottieni la classifica dei punti
                    top_users = await self.bot.point_system.get_top_points(channel_id, 5)
                    points_name = self.bot.kick_channel_points.config.points_name
                    
                    # Formatta la classifica
                    message = f"Classifica {points_name}:\n"
                    for i, user_data in enumerate(top_users):
                        message += f"{i+1}. {user_data['username']}: {user_data['points']} {points_name}\n"
                    
                    # Invia la classifica in chat
                    await self.bot.api.send_chat_message(channel_id, channel_name, message)
                    return
                    
                elif command in ["premi", "rewards"]:
                    # Ottieni la lista dei premi disponibili
                    rewards = await self.bot.kick_channel_points.get_rewards(channel_id)
                    
                    if not rewards:
                        await self.bot.api.send_chat_message(channel_id, channel_name, "Nessun premio disponibile al momento.")
                        return
                    
                    # Formatta la lista dei premi
                    message = "Premi disponibili:\n"
                    for reward in rewards:
                        if reward.get("enabled", True):
                            message += f"{reward.get('title')}: {reward.get('cost')} punti - {reward.get('description')}\n"
                    
                    # Invia la lista in chat
                    await self.bot.api.send_chat_message(channel_id, channel_name, message)
                    return
                
                # Gestisci altri comandi standard
                await self.bot.command_handler.handle_command(
                    channel_id, 
                    channel_name, 
                    user, 
                    content
                )
        except Exception as e:
            logger.error(f"Errore nella gestione del messaggio di chat: {e}")
            
    async def handle_subscription_event(self, channel_name: str, message_data: Dict):
        """Gestisce un evento di abbonamento."""
        try:
            # Estrai le informazioni sull'abbonamento
            user_id = message_data.get("user_id")
            username = message_data.get("username")
            
            if not user_id or not username:
                logger.warning(f"Dati incompleti per l'evento di abbonamento: {message_data}")
                return
                
            # Trova il canale nel database
            async with self.bot.db.pool.acquire() as conn:
                channel = await conn.fetchrow('''
                    SELECT id FROM channels WHERE name = $1
                ''', channel_name)
                
                if not channel:
                    logger.warning(f"Ricevuto evento di abbonamento per canale non registrato: {channel_name}")
                    return
                    
                channel_id = channel["id"]
            
            # Gestisci i punti canale per l'abbonamento
            if hasattr(self.bot, "kick_channel_points") and self.bot.kick_channel_points:
                await self.bot.kick_channel_points.handle_subscription(channel_id, int(user_id), username)
                
            # Registro dell'evento
            await self.bot.log_event(channel_id, "subscription", int(user_id), message_data)
            
        except Exception as e:
            logger.error(f"Errore nella gestione dell'evento di abbonamento: {e}")
            
    async def handle_follow_event(self, channel_name: str, message_data: Dict):
        """Gestisce un evento di nuovo follower."""
        try:
            # Estrai le informazioni sul follow
            user_id = message_data.get("user_id")
            username = message_data.get("username")
            
            if not user_id or not username:
                logger.warning(f"Dati incompleti per l'evento di follow: {message_data}")
                return
                
            # Trova il canale nel database
            async with self.bot.db.pool.acquire() as conn:
                channel = await conn.fetchrow('''
                    SELECT id FROM channels WHERE name = $1
                ''', channel_name)
                
                if not channel:
                    logger.warning(f"Ricevuto evento di follow per canale non registrato: {channel_name}")
                    return
                    
                channel_id = channel["id"]
            
            # Gestisci i punti canale per il follow
            if hasattr(self.bot, "kick_channel_points") and self.bot.kick_channel_points:
                await self.bot.kick_channel_points.handle_follow(channel_id, int(user_id), username)
                
            # Registro dell'evento
            await self.bot.log_event(channel_id, "follow", int(user_id), message_data)
            
        except Exception as e:
            logger.error(f"Errore nella gestione dell'evento di follow: {e}")
