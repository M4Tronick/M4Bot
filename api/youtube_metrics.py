import os
import json
import logging
import asyncio
import aiohttp
import time
from typing import Dict, List, Optional, Any, Callable, Union
from datetime import datetime, timedelta

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/youtube_metrics.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("YouTubeMetrics")

class YouTubeMetrics:
    """Gestore per il recupero delle metriche di YouTube come like e spettatori in diretta"""
    
    def __init__(self, config: Dict[str, Any], update_callback: Optional[Callable] = None):
        """
        Inizializza il gestore delle metriche di YouTube
        
        Args:
            config: Configurazione del gestore
            update_callback: Funzione di callback chiamata quando ci sono aggiornamenti
        """
        # Inizializza le variabili
        self.config = config
        self.api_key = config.get("youtube_api_key", "")
        self.update_callback = update_callback
        self.update_interval = config.get("youtube_metrics_update_interval", 60)  # Secondi
        self.channel_id = config.get("youtube_channel_id", "")
        self.metrics_file = "data/youtube_metrics.json"
        
        # Metriche correnti
        self.current_metrics = {
            "likes": 0,
            "live_viewers": 0,
            "live_status": False,
            "last_updated": 0,
            "live_video_id": None,
            "channel_info": {}
        }
        
        # Client HTTP
        self.session = None
        
        # Task di aggiornamento
        self.update_task = None
        
        # Flag per indicare se il gestore è in esecuzione
        self.is_running = False
        
        # Crea le directory necessarie
        os.makedirs("logs", exist_ok=True)
        os.makedirs("data", exist_ok=True)
        
        # Carica le metriche salvate se esistono
        self._load_saved_metrics()
        
        logger.info("Gestore metriche YouTube inizializzato")
    
    def _load_saved_metrics(self):
        """Carica le metriche salvate dal file"""
        try:
            if os.path.exists(self.metrics_file):
                with open(self.metrics_file, 'r') as f:
                    saved_metrics = json.load(f)
                    self.current_metrics.update(saved_metrics)
                logger.info("Metriche YouTube caricate dal file")
        except Exception as e:
            logger.error(f"Errore nel caricamento delle metriche salvate: {e}")
    
    def _save_metrics(self):
        """Salva le metriche correnti nel file"""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump(self.current_metrics, f)
            logger.debug("Metriche YouTube salvate nel file")
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle metriche: {e}")
    
    async def start(self):
        """Avvia il gestore delle metriche"""
        if not self.api_key:
            logger.error("API key di YouTube non configurata")
            return False
        
        try:
            # Crea la sessione HTTP
            self.session = aiohttp.ClientSession()
            
            # Verifica che l'API key sia valida
            status = await self._check_api_key()
            if not status:
                logger.error("Impossibile connettersi all'API di YouTube. Verifica l'API key.")
                await self.session.close()
                self.session = None
                return False
            
            self.is_running = True
            
            # Avvia il task di aggiornamento
            self.update_task = asyncio.create_task(self._update_loop())
            
            logger.info("Gestore metriche YouTube avviato")
            return True
        except Exception as e:
            logger.error(f"Errore nell'avvio del gestore metriche YouTube: {e}")
            if self.session:
                await self.session.close()
                self.session = None
            return False
    
    async def stop(self):
        """Ferma il gestore delle metriche"""
        if self.is_running:
            try:
                self.is_running = False
                
                if self.update_task:
                    self.update_task.cancel()
                    try:
                        await self.update_task
                    except asyncio.CancelledError:
                        pass
                    self.update_task = None
                
                if self.session:
                    await self.session.close()
                    self.session = None
                
                # Salva le metriche correnti
                self._save_metrics()
                
                logger.info("Gestore metriche YouTube fermato")
                return True
            except Exception as e:
                logger.error(f"Errore nella chiusura del gestore metriche YouTube: {e}")
                return False
        return True
    
    async def _check_api_key(self) -> bool:
        """
        Verifica che l'API key sia valida
        
        Returns:
            bool: True se l'API key è valida, False altrimenti
        """
        if not self.session:
            return False
        
        try:
            # Semplice richiesta per verificare che l'API key sia valida
            params = {
                "part": "snippet",
                "id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",  # Canale ufficiale di Google
                "key": self.api_key
            }
            
            async with self.session.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella verifica dell'API key: {error_text}")
                    return False
                
                data = await response.json()
                return True
        except Exception as e:
            logger.error(f"Eccezione nella verifica dell'API key: {e}")
            return False
    
    async def _update_loop(self):
        """Loop di aggiornamento delle metriche"""
        try:
            while self.is_running:
                try:
                    # Aggiorna le metriche
                    updated = await self._update_metrics()
                    
                    if updated and self.update_callback:
                        # Chiama il callback con le metriche aggiornate
                        await self.update_callback(self.current_metrics)
                    
                    # Salva le metriche
                    self._save_metrics()
                except Exception as e:
                    logger.error(f"Errore nell'aggiornamento delle metriche: {e}")
                
                # Attendi il prossimo aggiornamento
                await asyncio.sleep(self.update_interval)
        except asyncio.CancelledError:
            logger.info("Loop di aggiornamento metriche YouTube interrotto")
            raise
        except Exception as e:
            logger.error(f"Errore nel loop di aggiornamento: {e}")
    
    async def _update_metrics(self) -> bool:
        """
        Aggiorna le metriche di YouTube
        
        Returns:
            bool: True se l'aggiornamento è riuscito, False altrimenti
        """
        if not self.session or not self.is_running:
            return False
        
        try:
            # Verifica se il canale è in diretta e ottieni l'ID del video
            live_id = await self._check_live_status()
            
            if live_id:
                # Se è in diretta, ottieni le metriche
                await self._get_live_metrics(live_id)
            else:
                # Se non è in diretta, azzera le metriche di diretta
                self.current_metrics["live_viewers"] = 0
                self.current_metrics["live_status"] = False
                self.current_metrics["live_video_id"] = None
            
            # Aggiorna il timestamp
            self.current_metrics["last_updated"] = int(time.time())
            
            return True
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento delle metriche: {e}")
            return False
    
    async def _check_live_status(self) -> Optional[str]:
        """
        Verifica se il canale è in diretta
        
        Returns:
            Optional[str]: ID del video in diretta se il canale è in diretta, None altrimenti
        """
        if not self.channel_id:
            logger.error("ID del canale YouTube non configurato")
            return None
        
        try:
            # Parametri per la richiesta
            params = {
                "part": "snippet",
                "channelId": self.channel_id,
                "eventType": "live",
                "type": "video",
                "key": self.api_key
            }
            
            # Effettua la richiesta
            async with self.session.get(
                "https://www.googleapis.com/youtube/v3/search",
                params=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella verifica dello stato di diretta: {error_text}")
                    return None
                
                data = await response.json()
                
                # Verifica se ci sono risultati
                if data.get("items", []):
                    # Ottieni l'ID del primo video in diretta
                    video_id = data["items"][0]["id"]["videoId"]
                    self.current_metrics["live_status"] = True
                    self.current_metrics["live_video_id"] = video_id
                    return video_id
                else:
                    self.current_metrics["live_status"] = False
                    return None
        except Exception as e:
            logger.error(f"Eccezione nella verifica dello stato di diretta: {e}")
            return None
    
    async def _get_live_metrics(self, video_id: str) -> bool:
        """
        Ottiene le metriche di un video in diretta
        
        Args:
            video_id: ID del video in diretta
            
        Returns:
            bool: True se l'operazione è riuscita, False altrimenti
        """
        try:
            # Parametri per la richiesta delle statistiche del video
            params = {
                "part": "statistics,liveStreamingDetails",
                "id": video_id,
                "key": self.api_key
            }
            
            # Effettua la richiesta
            async with self.session.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nell'ottenimento delle metriche del video: {error_text}")
                    return False
                
                data = await response.json()
                
                # Verifica se ci sono risultati
                if data.get("items", []):
                    item = data["items"][0]
                    
                    # Estrai le metriche
                    statistics = item.get("statistics", {})
                    live_details = item.get("liveStreamingDetails", {})
                    
                    # Aggiorna le metriche
                    self.current_metrics["likes"] = int(statistics.get("likeCount", 0))
                    self.current_metrics["live_viewers"] = int(live_details.get("concurrentViewers", 0))
                    
                    return True
                else:
                    logger.warning(f"Nessun risultato per il video {video_id}")
                    return False
        except Exception as e:
            logger.error(f"Eccezione nell'ottenimento delle metriche del video: {e}")
            return False
    
    async def get_current_metrics(self) -> Dict[str, Any]:
        """
        Ottiene le metriche correnti
        
        Returns:
            Dict[str, Any]: Metriche correnti
        """
        return self.current_metrics
    
    async def force_update(self) -> bool:
        """
        Forza un aggiornamento delle metriche
        
        Returns:
            bool: True se l'aggiornamento è riuscito, False altrimenti
        """
        if not self.is_running:
            return False
        
        return await self._update_metrics()

# Funzione per creare un'istanza del gestore delle metriche YouTube
def create_youtube_metrics(config: Dict[str, Any], update_callback: Optional[Callable] = None) -> YouTubeMetrics:
    """
    Crea un'istanza del gestore delle metriche YouTube
    
    Args:
        config: Configurazione del gestore
        update_callback: Funzione di callback chiamata quando ci sono aggiornamenti
        
    Returns:
        YouTubeMetrics: Istanza del gestore delle metriche YouTube
    """
    return YouTubeMetrics(config, update_callback) 