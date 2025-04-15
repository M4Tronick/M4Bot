import os
import json
import logging
import aiohttp
import asyncio
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configurazione del logger
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("YouTubeConnector")

# Percorso per salvare i dati dell'utente
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'youtube')
os.makedirs(DATA_DIR, exist_ok=True)

# Scopes OAuth richiesti per l'accesso alle API YouTube
SCOPES = [
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/youtube',
    'https://www.googleapis.com/auth/youtube.force-ssl'
]

class YouTubeConnector:
    """Gestisce l'integrazione con l'API YouTube."""
    
    def __init__(self):
        self.credentials = {}
        self.services = {}
        self.channel_info = {}
        self.settings = {}
        self.load_settings()
    
    def load_settings(self):
        """Carica le impostazioni e le credenziali salvate."""
        try:
            # Carica le impostazioni generali
            settings_path = os.path.join(DATA_DIR, 'settings.json')
            if os.path.exists(settings_path):
                with open(settings_path, 'r') as f:
                    self.settings = json.load(f)
            
            # Carica le credenziali utente
            creds_dir = os.path.join(DATA_DIR, 'credentials')
            os.makedirs(creds_dir, exist_ok=True)
            
            for file in os.listdir(creds_dir):
                if file.endswith('.json'):
                    user_id = file.split('.')[0]
                    creds_path = os.path.join(creds_dir, file)
                    with open(creds_path, 'r') as f:
                        creds_data = json.load(f)
                        
                    if 'token' in creds_data:
                        self.credentials[user_id] = Credentials(
                            token=creds_data.get('token'),
                            refresh_token=creds_data.get('refresh_token'),
                            token_uri=creds_data.get('token_uri', 'https://oauth2.googleapis.com/token'),
                            client_id=creds_data.get('client_id'),
                            client_secret=creds_data.get('client_secret'),
                            scopes=creds_data.get('scopes', SCOPES)
                        )
                        
                        # Carica le informazioni sul canale
                        channel_path = os.path.join(DATA_DIR, 'channels', f"{user_id}.json")
                        if os.path.exists(channel_path):
                            with open(channel_path, 'r') as f:
                                self.channel_info[user_id] = json.load(f)
        
        except Exception as e:
            logger.error(f"Errore nel caricamento delle impostazioni YouTube: {e}")
    
    def save_credentials(self, user_id, credentials_data):
        """Salva le credenziali dell'utente."""
        try:
            creds_dir = os.path.join(DATA_DIR, 'credentials')
            os.makedirs(creds_dir, exist_ok=True)
            
            creds_path = os.path.join(creds_dir, f"{user_id}.json")
            with open(creds_path, 'w') as f:
                json.dump(credentials_data, f)
                
            logger.info(f"Credenziali salvate per l'utente {user_id}")
            return True
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle credenziali: {e}")
            return False
    
    def save_channel_info(self, user_id, channel_info):
        """Salva le informazioni sul canale dell'utente."""
        try:
            channel_dir = os.path.join(DATA_DIR, 'channels')
            os.makedirs(channel_dir, exist_ok=True)
            
            channel_path = os.path.join(channel_dir, f"{user_id}.json")
            with open(channel_path, 'w') as f:
                json.dump(channel_info, f)
                
            self.channel_info[user_id] = channel_info
            logger.info(f"Informazioni sul canale salvate per l'utente {user_id}")
            return True
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle informazioni sul canale: {e}")
            return False
    
    def save_settings(self):
        """Salva le impostazioni generali."""
        try:
            settings_path = os.path.join(DATA_DIR, 'settings.json')
            with open(settings_path, 'w') as f:
                json.dump(self.settings, f)
                
            logger.info("Impostazioni YouTube salvate")
            return True
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle impostazioni: {e}")
            return False
    
    def get_service(self, user_id):
        """Ottiene un'istanza del servizio YouTube API per l'utente."""
        try:
            if user_id not in self.services:
                if user_id in self.credentials:
                    self.services[user_id] = build('youtube', 'v3', credentials=self.credentials[user_id])
                else:
                    logger.error(f"Credenziali non trovate per l'utente {user_id}")
                    return None
            
            return self.services[user_id]
        except Exception as e:
            logger.error(f"Errore nella creazione del servizio YouTube: {e}")
            return None
    
    async def get_connection_status(self, user_id):
        """Verifica lo stato della connessione YouTube per l'utente."""
        try:
            if user_id not in self.credentials:
                return {
                    "connected": False,
                    "status": "Non connesso",
                    "channel_name": "N/A"
                }
            
            # Verifica se le credenziali sono valide
            service = self.get_service(user_id)
            if not service:
                return {
                    "connected": False,
                    "status": "Errore di connessione",
                    "channel_name": "N/A"
                }
            
            # Ottieni le informazioni sul canale se non sono già disponibili
            if user_id not in self.channel_info:
                channel_response = service.channels().list(
                    part="snippet,statistics",
                    mine=True
                ).execute()
                
                if channel_response.get("items"):
                    channel = channel_response["items"][0]
                    channel_info = {
                        "id": channel["id"],
                        "title": channel["snippet"]["title"],
                        "description": channel["snippet"]["description"],
                        "customUrl": channel["snippet"].get("customUrl", ""),
                        "thumbnails": channel["snippet"]["thumbnails"],
                        "statistics": channel["statistics"]
                    }
                    self.save_channel_info(user_id, channel_info)
                else:
                    logger.error(f"Nessun canale trovato per l'utente {user_id}")
                    return {
                        "connected": False,
                        "status": "Nessun canale trovato",
                        "channel_name": "N/A"
                    }
            
            return {
                "connected": True,
                "status": "Connesso",
                "channel_name": self.channel_info[user_id]["title"],
                "channel_id": self.channel_info[user_id]["id"],
                "custom_url": self.channel_info[user_id].get("customUrl", "")
            }
        
        except HttpError as e:
            if e.resp.status == 401:
                # Token scaduto o revocato
                logger.error(f"Token non valido per l'utente {user_id}: {e}")
                return {
                    "connected": False,
                    "status": "Token non valido",
                    "channel_name": "N/A"
                }
            else:
                logger.error(f"Errore API YouTube: {e}")
                return {
                    "connected": False,
                    "status": f"Errore API: {e.resp.status}",
                    "channel_name": "N/A"
                }
        except Exception as e:
            logger.error(f"Errore nella verifica dello stato di connessione: {e}")
            return {
                "connected": False,
                "status": f"Errore: {str(e)}",
                "channel_name": "N/A"
            }
    
    async def get_channel_stats(self, user_id):
        """Ottiene le statistiche del canale YouTube."""
        try:
            # Verifica se l'utente è connesso
            status = await self.get_connection_status(user_id)
            if not status["connected"]:
                return {"success": False, "message": status["status"]}
            
            # Ottieni le statistiche dal canale memorizzato
            if user_id in self.channel_info and "statistics" in self.channel_info[user_id]:
                stats = self.channel_info[user_id]["statistics"]
                
                # Aggiorna le statistiche in tempo reale
                service = self.get_service(user_id)
                if service:
                    channel_response = service.channels().list(
                        part="statistics",
                        id=self.channel_info[user_id]["id"]
                    ).execute()
                    
                    if channel_response.get("items"):
                        stats = channel_response["items"][0]["statistics"]
                        self.channel_info[user_id]["statistics"] = stats
                        self.save_channel_info(user_id, self.channel_info[user_id])
                
                return {
                    "success": True,
                    "stats": {
                        "subscribers": stats.get("subscriberCount", "0"),
                        "views": stats.get("viewCount", "0"),
                        "videos": stats.get("videoCount", "0"),
                        "comments": stats.get("commentCount", "0")
                    }
                }
            else:
                return {"success": False, "message": "Statistiche non disponibili"}
        
        except Exception as e:
            logger.error(f"Errore nell'ottenimento delle statistiche del canale: {e}")
            return {"success": False, "message": str(e)}
    
    async def get_streams(self, user_id):
        """Ottiene gli stream programmati su YouTube."""
        try:
            # Verifica se l'utente è connesso
            status = await self.get_connection_status(user_id)
            if not status["connected"]:
                return {"success": False, "message": status["status"]}
            
            service = self.get_service(user_id)
            if not service:
                return {"success": False, "message": "Servizio YouTube non disponibile"}
            
            # Ottieni gli stream programmati
            upcoming_streams = []
            past_streams = []
            
            # Cerca prima gli stream programmati
            upcoming_response = service.liveBroadcasts().list(
                part="id,snippet,status,contentDetails",
                broadcastStatus="upcoming",
                maxResults=10
            ).execute()
            
            if upcoming_response.get("items"):
                for stream in upcoming_response["items"]:
                    upcoming_streams.append({
                        "id": stream["id"],
                        "title": stream["snippet"]["title"],
                        "description": stream["snippet"]["description"],
                        "scheduled_start_time": stream["snippet"].get("scheduledStartTime", ""),
                        "thumbnail": stream["snippet"]["thumbnails"].get("high", {}).get("url", ""),
                        "status": stream["status"]["lifeCycleStatus"]
                    })
            
            # Cerca gli stream passati
            past_response = service.liveBroadcasts().list(
                part="id,snippet,status,contentDetails",
                broadcastStatus="completed",
                maxResults=5
            ).execute()
            
            if past_response.get("items"):
                for stream in past_response["items"]:
                    past_streams.append({
                        "id": stream["id"],
                        "title": stream["snippet"]["title"],
                        "description": stream["snippet"]["description"],
                        "actual_start_time": stream["snippet"].get("actualStartTime", ""),
                        "actual_end_time": stream["snippet"].get("actualEndTime", ""),
                        "thumbnail": stream["snippet"]["thumbnails"].get("high", {}).get("url", ""),
                        "status": stream["status"]["lifeCycleStatus"]
                    })
            
            return {
                "success": True,
                "streams": {
                    "upcoming": upcoming_streams,
                    "past": past_streams
                }
            }
        
        except Exception as e:
            logger.error(f"Errore nell'ottenimento degli stream: {e}")
            return {"success": False, "message": str(e)}
    
    async def create_oauth_flow(self, client_id, client_secret, redirect_uri):
        """Crea un flusso OAuth per l'autorizzazione YouTube."""
        try:
            client_config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uris": [redirect_uri],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            }
            
            flow = InstalledAppFlow.from_client_config(
                client_config=client_config,
                scopes=SCOPES,
                redirect_uri=redirect_uri
            )
            
            auth_url, _ = flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'
            )
            
            return {"success": True, "auth_url": auth_url, "flow": flow}
        
        except Exception as e:
            logger.error(f"Errore nella creazione del flusso OAuth: {e}")
            return {"success": False, "message": str(e)}
    
    async def exchange_code(self, user_id, code, client_id, client_secret, redirect_uri):
        """Scambia il codice di autorizzazione con i token di accesso."""
        try:
            client_config = {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uris": [redirect_uri],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            }
            
            flow = InstalledAppFlow.from_client_config(
                client_config=client_config,
                scopes=SCOPES,
                redirect_uri=redirect_uri
            )
            
            flow.fetch_token(code=code)
            credentials = flow.credentials
            
            # Salva le credenziali
            creds_data = {
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
                "expiry": credentials.expiry.isoformat() if credentials.expiry else None
            }
            
            self.save_credentials(user_id, creds_data)
            self.credentials[user_id] = credentials
            
            # Crea il servizio
            service = build('youtube', 'v3', credentials=credentials)
            self.services[user_id] = service
            
            # Ottieni le informazioni sul canale
            channel_response = service.channels().list(
                part="snippet,statistics",
                mine=True
            ).execute()
            
            if channel_response.get("items"):
                channel = channel_response["items"][0]
                channel_info = {
                    "id": channel["id"],
                    "title": channel["snippet"]["title"],
                    "description": channel["snippet"]["description"],
                    "customUrl": channel["snippet"].get("customUrl", ""),
                    "thumbnails": channel["snippet"]["thumbnails"],
                    "statistics": channel["statistics"]
                }
                self.save_channel_info(user_id, channel_info)
                
                return {"success": True, "channel_name": channel_info["title"]}
            else:
                return {"success": False, "message": "Nessun canale trovato"}
        
        except Exception as e:
            logger.error(f"Errore nello scambio del codice di autorizzazione: {e}")
            return {"success": False, "message": str(e)}
    
    async def disconnect(self, user_id):
        """Disconnette l'account YouTube dell'utente."""
        try:
            # Rimuovi le credenziali
            if user_id in self.credentials:
                del self.credentials[user_id]
            
            # Rimuovi il servizio
            if user_id in self.services:
                del self.services[user_id]
            
            # Rimuovi le informazioni sul canale
            if user_id in self.channel_info:
                del self.channel_info[user_id]
            
            # Elimina i file salvati
            creds_path = os.path.join(DATA_DIR, 'credentials', f"{user_id}.json")
            if os.path.exists(creds_path):
                os.remove(creds_path)
            
            channel_path = os.path.join(DATA_DIR, 'channels', f"{user_id}.json")
            if os.path.exists(channel_path):
                os.remove(channel_path)
            
            return {"success": True, "message": "Account YouTube disconnesso con successo"}
        
        except Exception as e:
            logger.error(f"Errore nella disconnessione dell'account: {e}")
            return {"success": False, "message": str(e)}
    
    async def update_settings(self, user_id, settings_data):
        """Aggiorna le impostazioni dell'integrazione YouTube."""
        try:
            if not settings_data:
                return {"success": False, "message": "Nessun dato fornito"}
            
            # Verifica se l'utente è connesso
            status = await self.get_connection_status(user_id)
            if not status["connected"]:
                return {"success": False, "message": "Utente non connesso a YouTube"}
            
            # Aggiorna le impostazioni utente
            user_settings = self.settings.get(user_id, {})
            user_settings.update(settings_data)
            self.settings[user_id] = user_settings
            
            # Salva le impostazioni
            self.save_settings()
            
            return {"success": True, "message": "Impostazioni aggiornate con successo"}
        
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento delle impostazioni: {e}")
            return {"success": False, "message": str(e)}
    
    async def create_live_stream(self, user_id, stream_data):
        """Crea un nuovo stream YouTube programmato."""
        try:
            # Verifica se l'utente è connesso
            status = await self.get_connection_status(user_id)
            if not status["connected"]:
                return {"success": False, "message": status["status"]}
            
            service = self.get_service(user_id)
            if not service:
                return {"success": False, "message": "Servizio YouTube non disponibile"}
            
            title = stream_data.get("title", "Live stream")
            description = stream_data.get("description", "")
            scheduled_start_time = stream_data.get("scheduled_start_time")
            privacy_status = stream_data.get("privacy_status", "unlisted")
            
            # Crea la trasmissione
            broadcast_insert_response = service.liveBroadcasts().insert(
                part="snippet,status,contentDetails",
                body={
                    "snippet": {
                        "title": title,
                        "description": description,
                        "scheduledStartTime": scheduled_start_time
                    },
                    "status": {
                        "privacyStatus": privacy_status
                    },
                    "contentDetails": {
                        "enableAutoStart": False,
                        "enableAutoStop": True
                    }
                }
            ).execute()
            
            # Crea lo stream
            stream_insert_response = service.liveStreams().insert(
                part="snippet,cdn",
                body={
                    "snippet": {
                        "title": title
                    },
                    "cdn": {
                        "frameRate": "variable",
                        "ingestionType": "rtmp",
                        "resolution": "variable"
                    }
                }
            ).execute()
            
            # Collega lo stream alla trasmissione
            service.liveBroadcasts().bind(
                part="id,snippet",
                id=broadcast_insert_response["id"],
                streamId=stream_insert_response["id"]
            ).execute()
            
            return {
                "success": True,
                "message": "Stream creato con successo",
                "stream_id": broadcast_insert_response["id"],
                "stream_details": {
                    "id": broadcast_insert_response["id"],
                    "title": broadcast_insert_response["snippet"]["title"],
                    "description": broadcast_insert_response["snippet"]["description"],
                    "scheduled_start_time": broadcast_insert_response["snippet"].get("scheduledStartTime", ""),
                    "stream_key": stream_insert_response["cdn"]["ingestionInfo"]["streamName"],
                    "ingestion_address": stream_insert_response["cdn"]["ingestionInfo"]["ingestionAddress"]
                }
            }
        
        except Exception as e:
            logger.error(f"Errore nella creazione dello stream: {e}")
            return {"success": False, "message": str(e)}
    
    async def update_live_stream(self, user_id, stream_data):
        """Aggiorna uno stream YouTube esistente."""
        try:
            # Verifica se l'utente è connesso
            status = await self.get_connection_status(user_id)
            if not status["connected"]:
                return {"success": False, "message": status["status"]}
            
            service = self.get_service(user_id)
            if not service:
                return {"success": False, "message": "Servizio YouTube non disponibile"}
            
            stream_id = stream_data.get("stream_id")
            if not stream_id:
                return {"success": False, "message": "ID dello stream mancante"}
            
            # Ottieni lo stream esistente
            broadcast_response = service.liveBroadcasts().list(
                part="snippet,status",
                id=stream_id
            ).execute()
            
            if not broadcast_response.get("items"):
                return {"success": False, "message": "Stream non trovato"}
            
            broadcast = broadcast_response["items"][0]
            
            # Aggiorna i campi forniti
            if "title" in stream_data:
                broadcast["snippet"]["title"] = stream_data["title"]
            
            if "description" in stream_data:
                broadcast["snippet"]["description"] = stream_data["description"]
            
            if "scheduled_start_time" in stream_data:
                broadcast["snippet"]["scheduledStartTime"] = stream_data["scheduled_start_time"]
            
            if "privacy_status" in stream_data:
                broadcast["status"]["privacyStatus"] = stream_data["privacy_status"]
            
            # Invia l'aggiornamento
            service.liveBroadcasts().update(
                part="snippet,status",
                body=broadcast
            ).execute()
            
            return {"success": True, "message": "Stream aggiornato con successo"}
        
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento dello stream: {e}")
            return {"success": False, "message": str(e)}
    
    async def delete_live_stream(self, user_id, stream_id):
        """Elimina uno stream YouTube programmato."""
        try:
            # Verifica se l'utente è connesso
            status = await self.get_connection_status(user_id)
            if not status["connected"]:
                return {"success": False, "message": status["status"]}
            
            service = self.get_service(user_id)
            if not service:
                return {"success": False, "message": "Servizio YouTube non disponibile"}
            
            if not stream_id:
                return {"success": False, "message": "ID dello stream mancante"}
            
            # Elimina lo stream
            service.liveBroadcasts().delete(
                id=stream_id
            ).execute()
            
            return {"success": True, "message": "Stream eliminato con successo"}
        
        except Exception as e:
            logger.error(f"Errore nell'eliminazione dello stream: {e}")
            return {"success": False, "message": str(e)}

# Istanza del connettore
youtube_connector = YouTubeConnector()

# API per altre applicazioni
async def get_status(user_id):
    """Ottiene lo stato dell'integrazione YouTube."""
    return await youtube_connector.get_connection_status(user_id)

async def get_stats(user_id):
    """Ottiene le statistiche del canale YouTube."""
    return await youtube_connector.get_channel_stats(user_id)

async def get_streams(user_id):
    """Ottiene gli stream programmati su YouTube."""
    return await youtube_connector.get_streams(user_id)

async def connect(user_id, client_id, client_secret, api_key, redirect_uri):
    """Inizia il processo di connessione a YouTube."""
    result = await youtube_connector.create_oauth_flow(client_id, client_secret, redirect_uri)
    if result.get("success"):
        # Salva le informazioni di configurazione temporanee
        config_data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "api_key": api_key
        }
        temp_dir = os.path.join(DATA_DIR, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        with open(os.path.join(temp_dir, f"{user_id}.json"), 'w') as f:
            json.dump(config_data, f)
        
        return {"success": True, "auth_url": result["auth_url"]}
    else:
        return {"success": False, "message": result.get("message", "Errore nella creazione del flusso OAuth")}

async def oauth_callback(user_id, code, state):
    """Gestisce il callback OAuth per completare la connessione."""
    try:
        # Carica le informazioni di configurazione temporanee
        temp_path = os.path.join(DATA_DIR, 'temp', f"{user_id}.json")
        if not os.path.exists(temp_path):
            return {"success": False, "message": "Configurazione non trovata"}
        
        with open(temp_path, 'r') as f:
            config = json.load(f)
        
        client_id = config.get("client_id")
        client_secret = config.get("client_secret")
        
        if not client_id or not client_secret:
            return {"success": False, "message": "Dati di configurazione incompleti"}
        
        # Scambia il codice con i token
        redirect_uri = "http://localhost:8000/youtube/oauth/callback"
        result = await youtube_connector.exchange_code(user_id, code, client_id, client_secret, redirect_uri)
        
        # Pulisci i file temporanei
        if os.path.exists(temp_path):
            os.remove(temp_path)
        
        return result
    
    except Exception as e:
        logger.error(f"Errore nel callback OAuth: {e}")
        return {"success": False, "message": str(e)}

async def disconnect(user_id):
    """Disconnette l'account YouTube."""
    return await youtube_connector.disconnect(user_id)

async def update_settings(user_id, settings_data):
    """Aggiorna le impostazioni dell'integrazione YouTube."""
    return await youtube_connector.update_settings(user_id, settings_data)

async def create_stream(user_id, stream_data):
    """Crea un nuovo stream YouTube programmato."""
    return await youtube_connector.create_live_stream(user_id, stream_data)

async def update_stream(user_id, stream_data):
    """Aggiorna uno stream YouTube esistente."""
    return await youtube_connector.update_live_stream(user_id, stream_data)

async def delete_stream(user_id, stream_id):
    """Elimina uno stream YouTube programmato."""
    return await youtube_connector.delete_live_stream(user_id, stream_id) 