import os
import json
import logging
import asyncio
import aiohttp
import time
from typing import Dict, List, Optional, Any, Callable, Union
from datetime import datetime

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/youtube_connector.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("YouTubeConnector")

class YouTubeConnector:
    """Connettore per YouTube che gestisce l'integrazione con l'API YouTube"""
    
    def __init__(self, config: Dict[str, Any], message_callback: Optional[Callable] = None):
        """
        Inizializza il connettore YouTube
        
        Args:
            config: Configurazione del connettore
            message_callback: Callback per gestire i messaggi ricevuti da YouTube
        """
        # Inizializza le variabili
        self.config = config
        self.api_key = config.get("youtube_api_key", "")
        self.channel_id = config.get("youtube_channel_id", "")
        self.oauth_client_id = config.get("youtube_oauth_client_id", "")
        self.oauth_client_secret = config.get("youtube_oauth_client_secret", "")
        self.oauth_refresh_token = config.get("youtube_oauth_refresh_token", "")
        self.access_token = None
        self.token_expiry = 0
        self.message_callback = message_callback
        
        # Polling interval (in secondi) per le nuove chat/commenti
        self.poll_interval = config.get("youtube_poll_interval", 10)
        
        # Client HTTP
        self.session = None
        
        # Flag per indicare se il bot è in esecuzione
        self.is_running = False
        
        # Task di polling
        self.live_chat_task = None
        self.comments_task = None
        
        # Ultimo ID di chat e commento elaborato
        self.last_chat_id = ""
        self.last_comment_id = ""
        
        # Flag live
        self.is_live = False
        self.current_live_id = None
        
        # Registro dei messaggi sincronizzati per evitare duplicati
        self.synced_messages = {}
        
        # Crea le directory necessarie
        os.makedirs("logs", exist_ok=True)
        
        logger.info("Connettore YouTube inizializzato")
    
    async def start(self):
        """Avvia il connettore YouTube"""
        if not self.api_key and not (self.oauth_client_id and self.oauth_client_secret and self.oauth_refresh_token):
            logger.error("Credenziali YouTube non configurate")
            return False
        
        try:
            # Crea la sessione HTTP
            self.session = aiohttp.ClientSession()
            
            # Verifica le credenziali
            if self.oauth_refresh_token:
                # Se abbiamo un refresh token, otteniamo un access token
                success = await self._refresh_access_token()
                if not success:
                    logger.error("Impossibile ottenere l'access token. Verifica le credenziali OAuth.")
                    await self.session.close()
                    self.session = None
                    return False
            else:
                # Altrimenti verifichiamo l'API key
                channel = await self.get_channel_info()
                if not channel:
                    logger.error("Impossibile ottenere le informazioni del canale. Verifica l'API key.")
                    await self.session.close()
                    self.session = None
                    return False
            
            self.is_running = True
            
            # Avvia i task di polling se configurati
            if self.config.get("youtube_monitor_live_chat", True):
                self.live_chat_task = asyncio.create_task(self._live_chat_polling_loop())
            
            if self.config.get("youtube_monitor_comments", True):
                self.comments_task = asyncio.create_task(self._comments_polling_loop())
            
            logger.info("Connettore YouTube avviato")
            return True
        except Exception as e:
            logger.error(f"Errore nell'avvio del connettore YouTube: {e}")
            if self.session:
                await self.session.close()
                self.session = None
            return False
    
    async def stop(self):
        """Ferma il connettore YouTube"""
        if self.is_running:
            try:
                self.is_running = False
                
                # Ferma i task di polling
                if self.live_chat_task:
                    self.live_chat_task.cancel()
                    try:
                        await self.live_chat_task
                    except asyncio.CancelledError:
                        pass
                    self.live_chat_task = None
                
                if self.comments_task:
                    self.comments_task.cancel()
                    try:
                        await self.comments_task
                    except asyncio.CancelledError:
                        pass
                    self.comments_task = None
                
                if self.session:
                    await self.session.close()
                    self.session = None
                
                logger.info("Connettore YouTube fermato")
                return True
            except Exception as e:
                logger.error(f"Errore nella chiusura del connettore YouTube: {e}")
                return False
        return True
    
    async def _refresh_access_token(self) -> bool:
        """
        Aggiorna l'access token usando il refresh token
        
        Returns:
            bool: True se l'access token è stato aggiornato con successo, False altrimenti
        """
        if not self.session:
            return False
        
        try:
            # Prepara i dati per la richiesta
            data = {
                "client_id": self.oauth_client_id,
                "client_secret": self.oauth_client_secret,
                "refresh_token": self.oauth_refresh_token,
                "grant_type": "refresh_token"
            }
            
            # Invia la richiesta
            async with self.session.post(
                "https://oauth2.googleapis.com/token",
                data=data
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nel refresh dell'access token: {error_text}")
                    return False
                
                token_data = await response.json()
                
                # Salva l'access token e la sua scadenza
                self.access_token = token_data.get("access_token")
                expires_in = token_data.get("expires_in", 3600)
                self.token_expiry = time.time() + expires_in - 300  # Rinnova 5 minuti prima della scadenza
                
                logger.info(f"Access token aggiornato, scadrà tra {expires_in} secondi")
                return True
        except Exception as e:
            logger.error(f"Eccezione nel refresh dell'access token: {e}")
            return False
    
    async def _check_token(self) -> bool:
        """
        Verifica se l'access token è valido e lo aggiorna se necessario
        
        Returns:
            bool: True se l'access token è valido, False altrimenti
        """
        if not self.oauth_refresh_token:
            # Stiamo usando l'API key, non l'OAuth
            return True
        
        if not self.access_token or time.time() > self.token_expiry:
            return await self._refresh_access_token()
        
        return True
    
    async def get_channel_info(self) -> Optional[Dict[str, Any]]:
        """
        Ottiene informazioni sul canale
        
        Returns:
            Dict[str, Any] | None: Informazioni sul canale o None in caso di errore
        """
        if not self.session:
            return None
        
        try:
            # Prepara i parametri per la richiesta
            params = {
                "part": "snippet,statistics,contentDetails",
                "id": self.channel_id
            }
            
            # Aggiungi la chiave di autenticazione
            if self.access_token:
                headers = {"Authorization": f"Bearer {self.access_token}"}
                # Se usiamo OAuth, non serve l'API key
            else:
                headers = {}
                params["key"] = self.api_key
            
            # Invia la richiesta
            async with self.session.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params=params,
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella richiesta delle informazioni del canale: {error_text}")
                    return None
                
                data = await response.json()
                
                # Verifica se il canale esiste
                items = data.get("items", [])
                if not items:
                    logger.error(f"Canale con ID {self.channel_id} non trovato")
                    return None
                
                return items[0]
        except Exception as e:
            logger.error(f"Eccezione nella richiesta delle informazioni del canale: {e}")
            return None
    
    async def _get_live_broadcast(self) -> Optional[Dict[str, Any]]:
        """
        Ottiene informazioni sulla trasmissione in diretta attuale
        
        Returns:
            Dict[str, Any] | None: Informazioni sulla diretta o None se non c'è una diretta attiva
        """
        if not self.session:
            return None
        
        try:
            # Verifica il token
            if not await self._check_token():
                return None
            
            # Prepara i parametri per la richiesta
            params = {
                "part": "snippet,contentDetails,status",
                "broadcastType": "all",
                "broadcastStatus": "active"
            }
            
            # Se abbiamo l'ID del canale, filtriamo per quello
            if self.channel_id:
                params["channelId"] = self.channel_id
            
            # Aggiungi la chiave di autenticazione
            if self.access_token:
                headers = {"Authorization": f"Bearer {self.access_token}"}
                # Se usiamo OAuth, non serve l'API key
            else:
                headers = {}
                params["key"] = self.api_key
            
            # Invia la richiesta
            async with self.session.get(
                "https://www.googleapis.com/youtube/v3/liveBroadcasts",
                params=params,
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella richiesta delle dirette attive: {error_text}")
                    return None
                
                data = await response.json()
                
                # Verifica se ci sono dirette attive
                items = data.get("items", [])
                if not items:
                    return None
                
                # Prendi la prima diretta attiva
                return items[0]
        except Exception as e:
            logger.error(f"Eccezione nella richiesta delle dirette attive: {e}")
            return None
    
    async def _get_live_chat_id(self, video_id: str) -> Optional[str]:
        """
        Ottiene l'ID della chat in diretta per un video
        
        Args:
            video_id: ID del video
            
        Returns:
            str | None: ID della chat in diretta o None se non trovato
        """
        if not self.session:
            return None
        
        try:
            # Verifica il token
            if not await self._check_token():
                return None
            
            # Prepara i parametri per la richiesta
            params = {
                "part": "liveStreamingDetails",
                "id": video_id
            }
            
            # Aggiungi la chiave di autenticazione
            if self.access_token:
                headers = {"Authorization": f"Bearer {self.access_token}"}
                # Se usiamo OAuth, non serve l'API key
            else:
                headers = {}
                params["key"] = self.api_key
            
            # Invia la richiesta
            async with self.session.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params=params,
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella richiesta delle informazioni di streaming: {error_text}")
                    return None
                
                data = await response.json()
                
                # Verifica se il video esiste
                items = data.get("items", [])
                if not items:
                    logger.error(f"Video con ID {video_id} non trovato")
                    return None
                
                # Ottieni l'ID della chat in diretta
                return items[0].get("liveStreamingDetails", {}).get("activeLiveChatId")
        except Exception as e:
            logger.error(f"Eccezione nella richiesta delle informazioni di streaming: {e}")
            return None
    
    async def _get_live_chat_messages(self, live_chat_id: str, page_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Ottiene i messaggi dalla chat in diretta
        
        Args:
            live_chat_id: ID della chat in diretta
            page_token: Token di paginazione
            
        Returns:
            Dict[str, Any]: Risposta con i messaggi della chat
        """
        if not self.session:
            return {"items": [], "nextPageToken": None}
        
        try:
            # Verifica il token
            if not await self._check_token():
                return {"items": [], "nextPageToken": None}
            
            # Prepara i parametri per la richiesta
            params = {
                "part": "snippet,authorDetails",
                "liveChatId": live_chat_id,
                "maxResults": 200  # Massimo numero di messaggi da recuperare
            }
            
            if page_token:
                params["pageToken"] = page_token
            
            # Aggiungi la chiave di autenticazione
            if self.access_token:
                headers = {"Authorization": f"Bearer {self.access_token}"}
                # Se usiamo OAuth, non serve l'API key
            else:
                headers = {}
                params["key"] = self.api_key
            
            # Invia la richiesta
            async with self.session.get(
                "https://www.googleapis.com/youtube/v3/liveChat/messages",
                params=params,
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella richiesta dei messaggi della chat: {error_text}")
                    return {"items": [], "nextPageToken": None}
                
                data = await response.json()
                return data
        except Exception as e:
            logger.error(f"Eccezione nella richiesta dei messaggi della chat: {e}")
            return {"items": [], "nextPageToken": None}
    
    async def _get_video_comments(self, video_id: str, page_token: Optional[str] = None) -> Dict[str, Any]:
        """
        Ottiene i commenti di un video
        
        Args:
            video_id: ID del video
            page_token: Token di paginazione
            
        Returns:
            Dict[str, Any]: Risposta con i commenti del video
        """
        if not self.session:
            return {"items": [], "nextPageToken": None}
        
        try:
            # Verifica il token
            if not await self._check_token():
                return {"items": [], "nextPageToken": None}
            
            # Prepara i parametri per la richiesta
            params = {
                "part": "snippet",
                "videoId": video_id,
                "maxResults": 100,  # Massimo numero di commenti da recuperare
                "order": "time"     # Ordina per i più recenti
            }
            
            if page_token:
                params["pageToken"] = page_token
            
            # Aggiungi la chiave di autenticazione
            if self.access_token:
                headers = {"Authorization": f"Bearer {self.access_token}"}
                # Se usiamo OAuth, non serve l'API key
            else:
                headers = {}
                params["key"] = self.api_key
            
            # Invia la richiesta
            async with self.session.get(
                "https://www.googleapis.com/youtube/v3/commentThreads",
                params=params,
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella richiesta dei commenti: {error_text}")
                    return {"items": [], "nextPageToken": None}
                
                data = await response.json()
                return data
        except Exception as e:
            logger.error(f"Eccezione nella richiesta dei commenti: {e}")
            return {"items": [], "nextPageToken": None}
    
    async def _process_live_chat_message(self, message: Dict[str, Any]):
        """
        Processa un messaggio dalla chat in diretta
        
        Args:
            message: Messaggio dalla chat in diretta
        """
        try:
            # Estrai le informazioni principali
            snippet = message.get("snippet", {})
            author_details = message.get("authorDetails", {})
            
            message_id = message.get("id", "")
            type = snippet.get("type", "")
            timestamp = snippet.get("publishedAt", "")
            
            # Verifica se è un messaggio di testo
            if type != "textMessageEvent":
                return
            
            # Converte la stringa timestamp in un timestamp Unix
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                unix_timestamp = dt.timestamp()
            except Exception:
                unix_timestamp = time.time()
            
            # Verifica se il messaggio è già stato sincronizzato
            unique_id = f"youtube_chat_{message_id}"
            if unique_id in self.synced_messages:
                return
            
            # Aggiunge il messaggio al registro dei messaggi sincronizzati
            self.synced_messages[unique_id] = {
                "timestamp": unix_timestamp,
                "platform": "youtube",
                "type": "live_chat"
            }
            
            # Mantieni solo gli ultimi 1000 messaggi nel registro
            if len(self.synced_messages) > 1000:
                # Ordina per timestamp e rimuovi i più vecchi
                sorted_messages = sorted(
                    self.synced_messages.items(),
                    key=lambda x: x[1]["timestamp"]
                )
                self.synced_messages = dict(sorted_messages[500:])
            
            # Formatta il messaggio per la sincronizzazione
            formatted_message = {
                "id": unique_id,
                "platform": "youtube",
                "channel_id": self.channel_id,
                "channel_name": "YouTube",
                "video_id": self.current_live_id,
                "author": {
                    "id": author_details.get("channelId", ""),
                    "username": author_details.get("displayName", ""),
                    "display_name": author_details.get("displayName", ""),
                    "is_mod": author_details.get("isChatModerator", False),
                    "is_owner": author_details.get("isChatOwner", False),
                    "is_sponsor": author_details.get("isChatSponsor", False)
                },
                "content": snippet.get("displayMessage", ""),
                "timestamp": unix_timestamp,
                "type": "live_chat",
                "raw_message": message
            }
            
            # Invia il messaggio al callback se presente
            if self.message_callback:
                try:
                    await self.message_callback(formatted_message)
                except Exception as e:
                    logger.error(f"Errore nel callback del messaggio: {e}")
        except Exception as e:
            logger.error(f"Errore nel processamento del messaggio della chat: {e}")
    
    async def _process_comment(self, comment: Dict[str, Any]):
        """
        Processa un commento
        
        Args:
            comment: Commento da processare
        """
        try:
            # Estrai le informazioni principali
            snippet = comment.get("snippet", {})
            top_level_comment = snippet.get("topLevelComment", {})
            comment_snippet = top_level_comment.get("snippet", {})
            
            comment_id = comment.get("id", "")
            video_id = snippet.get("videoId", "")
            author_display_name = comment_snippet.get("authorDisplayName", "")
            author_channel_id = comment_snippet.get("authorChannelId", {}).get("value", "")
            text = comment_snippet.get("textDisplay", "")
            timestamp = comment_snippet.get("publishedAt", "")
            
            # Converte la stringa timestamp in un timestamp Unix
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                unix_timestamp = dt.timestamp()
            except Exception:
                unix_timestamp = time.time()
            
            # Verifica se il commento è già stato sincronizzato
            unique_id = f"youtube_comment_{comment_id}"
            if unique_id in self.synced_messages:
                return
            
            # Aggiunge il commento al registro dei messaggi sincronizzati
            self.synced_messages[unique_id] = {
                "timestamp": unix_timestamp,
                "platform": "youtube",
                "type": "comment"
            }
            
            # Mantieni solo gli ultimi 1000 messaggi nel registro
            if len(self.synced_messages) > 1000:
                # Ordina per timestamp e rimuovi i più vecchi
                sorted_messages = sorted(
                    self.synced_messages.items(),
                    key=lambda x: x[1]["timestamp"]
                )
                self.synced_messages = dict(sorted_messages[500:])
            
            # Formatta il commento per la sincronizzazione
            formatted_message = {
                "id": unique_id,
                "platform": "youtube",
                "channel_id": self.channel_id,
                "channel_name": "YouTube",
                "video_id": video_id,
                "author": {
                    "id": author_channel_id,
                    "username": author_display_name,
                    "display_name": author_display_name,
                    "is_mod": False
                },
                "content": text,
                "timestamp": unix_timestamp,
                "type": "comment",
                "raw_message": comment
            }
            
            # Invia il commento al callback se presente
            if self.message_callback:
                try:
                    await self.message_callback(formatted_message)
                except Exception as e:
                    logger.error(f"Errore nel callback del commento: {e}")
        except Exception as e:
            logger.error(f"Errore nel processamento del commento: {e}")
    
    async def _live_chat_polling_loop(self):
        """Loop di polling per la chat in diretta"""
        try:
            page_token = None
            check_live_interval = 60  # Controlla per nuove dirette ogni 60 secondi
            last_live_check = 0
            
            while self.is_running:
                try:
                    current_time = time.time()
                    
                    # Controlla per nuove dirette se necessario
                    if not self.is_live or current_time - last_live_check > check_live_interval:
                        live_broadcast = await self._get_live_broadcast()
                        last_live_check = current_time
                        
                        if live_broadcast:
                            # Abbiamo una diretta attiva
                            video_id = live_broadcast.get("id", "")
                            
                            if not self.is_live or self.current_live_id != video_id:
                                # Nuova diretta rilevata
                                self.is_live = True
                                self.current_live_id = video_id
                                self.last_chat_id = ""
                                page_token = None
                                
                                # Ottieni l'ID della chat in diretta
                                live_chat_id = await self._get_live_chat_id(video_id)
                                if not live_chat_id:
                                    self.is_live = False
                                    self.current_live_id = None
                                    await asyncio.sleep(check_live_interval)
                                    continue
                                
                                logger.info(f"Rilevata nuova diretta: {video_id}, chat ID: {live_chat_id}")
                        else:
                            # Nessuna diretta attiva
                            if self.is_live:
                                logger.info("Diretta terminata")
                                self.is_live = False
                                self.current_live_id = None
                                await asyncio.sleep(check_live_interval)
                                continue
                    
                    # Se non siamo in diretta, salta al prossimo controllo
                    if not self.is_live:
                        await asyncio.sleep(check_live_interval)
                        continue
                    
                    # Ottieni l'ID della chat in diretta
                    live_chat_id = await self._get_live_chat_id(self.current_live_id)
                    if not live_chat_id:
                        self.is_live = False
                        self.current_live_id = None
                        await asyncio.sleep(check_live_interval)
                        continue
                    
                    # Ottieni i messaggi dalla chat in diretta
                    chat_response = await self._get_live_chat_messages(live_chat_id, page_token)
                    messages = chat_response.get("items", [])
                    page_token = chat_response.get("nextPageToken")
                    
                    # Processa i messaggi
                    for message in messages:
                        message_id = message.get("id", "")
                        
                        # Salva l'ultimo ID processato
                        if not self.last_chat_id or message_id > self.last_chat_id:
                            self.last_chat_id = message_id
                        
                        await self._process_live_chat_message(message)
                    
                    # Ottieni il polling interval dal server
                    polling_interval_ms = chat_response.get("pollingIntervalMillis", 10000)
                    polling_interval = polling_interval_ms / 1000.0
                    
                    # Pausa prima del prossimo polling
                    await asyncio.sleep(polling_interval)
                except asyncio.CancelledError:
                    # Il task è stato cancellato, esci dal loop
                    raise
                except Exception as e:
                    logger.error(f"Errore nel polling della chat in diretta: {e}")
                    # Pausa più lunga in caso di errore
                    await asyncio.sleep(30)
        except asyncio.CancelledError:
            # Task cancellato
            pass
        finally:
            logger.info("Polling loop della chat in diretta terminato")
    
    async def _comments_polling_loop(self):
        """Loop di polling per i commenti"""
        try:
            while self.is_running:
                try:
                    # Se abbiamo una diretta attiva, controlla i commenti
                    if self.is_live and self.current_live_id:
                        # Ottieni i commenti del video in diretta
                        comments_response = await self._get_video_comments(self.current_live_id)
                        comments = comments_response.get("items", [])
                        
                        # Processa i commenti
                        for comment in comments:
                            comment_id = comment.get("id", "")
                            
                            # Salva l'ultimo ID processato
                            if not self.last_comment_id or comment_id > self.last_comment_id:
                                self.last_comment_id = comment_id
                            
                            await self._process_comment(comment)
                    
                    # Pausa prima del prossimo polling
                    await asyncio.sleep(self.poll_interval)
                except asyncio.CancelledError:
                    # Il task è stato cancellato, esci dal loop
                    raise
                except Exception as e:
                    logger.error(f"Errore nel polling dei commenti: {e}")
                    # Pausa più lunga in caso di errore
                    await asyncio.sleep(30)
        except asyncio.CancelledError:
            # Task cancellato
            pass
        finally:
            logger.info("Polling loop dei commenti terminato")
    
    async def send_live_chat_message(self, message: str) -> bool:
        """
        Invia un messaggio alla chat in diretta
        
        Args:
            message: Messaggio da inviare
            
        Returns:
            bool: True se l'invio è riuscito, False altrimenti
        """
        if not self.session or not self.is_running or not self.access_token:
            return False
        
        # Verifica che siamo in diretta
        if not self.is_live or not self.current_live_id:
            logger.error("Nessuna diretta attiva")
            return False
        
        try:
            # Verifica il token
            if not await self._check_token():
                return False
            
            # Ottieni l'ID della chat in diretta
            live_chat_id = await self._get_live_chat_id(self.current_live_id)
            if not live_chat_id:
                logger.error("ID della chat in diretta non trovato")
                return False
            
            # Prepara l'header con il token
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Prepara il payload
            payload = {
                "snippet": {
                    "liveChatId": live_chat_id,
                    "type": "textMessageEvent",
                    "textMessageDetails": {
                        "messageText": message
                    }
                }
            }
            
            # Invia il messaggio
            async with self.session.post(
                "https://www.googleapis.com/youtube/v3/liveChat/messages",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nell'invio del messaggio alla chat in diretta: {error_text}")
                    return False
                
                data = await response.json()
                return True
        except Exception as e:
            logger.error(f"Eccezione nell'invio del messaggio alla chat in diretta: {e}")
            return False
    
    async def add_comment(self, video_id: str, text: str) -> bool:
        """
        Aggiunge un commento a un video
        
        Args:
            video_id: ID del video
            text: Testo del commento
            
        Returns:
            bool: True se l'aggiunta è riuscita, False altrimenti
        """
        if not self.session or not self.is_running or not self.access_token:
            return False
        
        try:
            # Verifica il token
            if not await self._check_token():
                return False
            
            # Prepara l'header con il token
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            # Prepara il payload
            payload = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": text
                        }
                    }
                }
            }
            
            # Invia il commento
            async with self.session.post(
                "https://www.googleapis.com/youtube/v3/commentThreads",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nell'aggiunta del commento: {error_text}")
                    return False
                
                data = await response.json()
                return True
        except Exception as e:
            logger.error(f"Eccezione nell'aggiunta del commento: {e}")
            return False
    
    async def sync_message_to_youtube(self, message: Dict[str, Any]) -> bool:
        """
        Sincronizza un messaggio da un'altra piattaforma a YouTube
        
        Args:
            message: Il messaggio da sincronizzare
            
        Returns:
            bool: True se il messaggio è stato sincronizzato con successo, False altrimenti
        """
        try:
            # Verifica se il messaggio è già stato sincronizzato
            message_id = message.get("id", "")
            if message_id in self.synced_messages:
                return True
            
            # Aggiunge il messaggio al registro dei messaggi sincronizzati
            self.synced_messages[message_id] = {
                "timestamp": message.get("timestamp", 0),
                "platform": message.get("platform", "unknown"),
                "type": "sync"
            }
            
            # Mantieni solo gli ultimi 1000 messaggi nel registro
            if len(self.synced_messages) > 1000:
                # Ordina per timestamp e rimuovi i più vecchi
                sorted_messages = sorted(
                    self.synced_messages.items(),
                    key=lambda x: x[1]["timestamp"]
                )
                self.synced_messages = dict(sorted_messages[500:])
            
            # Verifica se siamo in diretta
            if not self.is_live or not self.current_live_id:
                logger.warning("Impossibile sincronizzare il messaggio: nessuna diretta attiva")
                return False
            
            # Formatta il messaggio per YouTube
            platform = message.get("platform", "unknown")
            author_name = message.get("author", {}).get("display_name", "Utente")
            content = message.get("content", "")
            
            formatted_content = f"[{platform.upper()}] {author_name}: {content}"
            
            # Invia il messaggio alla chat in diretta
            return await self.send_live_chat_message(formatted_content)
            
        except Exception as e:
            logger.error(f"Errore nella sincronizzazione del messaggio a YouTube: {e}")
            return False
    
    async def is_connected(self) -> bool:
        """
        Verifica se il connettore è connesso a YouTube
        
        Returns:
            bool: True se il connettore è connesso, False altrimenti
        """
        if not self.is_running or not self.session:
            return False
        
        # Verifica che le credenziali siano valide
        if self.oauth_refresh_token:
            return await self._check_token()
        else:
            # Semplice controllo dell'API key
            channel = await self.get_channel_info()
            return channel is not None

# Funzione per creare un'istanza del connettore YouTube
def create_youtube_connector(config: Dict[str, Any], message_callback: Optional[Callable] = None) -> YouTubeConnector:
    """
    Crea un'istanza del connettore YouTube
    
    Args:
        config: Configurazione del connettore
        message_callback: Callback per gestire i messaggi ricevuti da YouTube
        
    Returns:
        YouTubeConnector: Istanza del connettore YouTube
    """
    return YouTubeConnector(config, message_callback) 