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
        logging.FileHandler("logs/kick_metrics.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("KickMetrics")

class KickMetrics:
    """Gestore per il recupero delle metriche di Kick.com come visualizzatori in diretta"""
    
    def __init__(self, config: Dict[str, Any], update_callback: Optional[Callable] = None):
        """
        Inizializza il gestore delle metriche di Kick.com
        
        Args:
            config: Configurazione del gestore
            update_callback: Funzione di callback chiamata quando ci sono aggiornamenti
        """
        # Inizializza le variabili
        self.config = config
        self.channel_name = config.get("kick_channel_name", "")
        self.update_callback = update_callback
        self.update_interval = config.get("kick_metrics_update_interval", 60)  # Secondi
        self.metrics_file = "data/kick_metrics.json"
        
        # Metriche correnti
        self.current_metrics = {
            "live_viewers": 0,
            "live_status": False,
            "last_updated": 0,
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
        
        logger.info("Gestore metriche Kick inizializzato")
    
    def _load_saved_metrics(self):
        """Carica le metriche salvate dal file"""
        try:
            if os.path.exists(self.metrics_file):
                with open(self.metrics_file, 'r') as f:
                    saved_metrics = json.load(f)
                    self.current_metrics.update(saved_metrics)
                logger.info("Metriche Kick caricate dal file")
        except Exception as e:
            logger.error(f"Errore nel caricamento delle metriche salvate: {e}")
    
    def _save_metrics(self):
        """Salva le metriche correnti nel file"""
        try:
            with open(self.metrics_file, 'w') as f:
                json.dump(self.current_metrics, f)
            logger.debug("Metriche Kick salvate nel file")
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle metriche: {e}")
    
    async def start(self):
        """Avvia il gestore delle metriche"""
        if not self.channel_name:
            logger.error("Nome del canale Kick non configurato")
            return False
        
        try:
            # Crea la sessione HTTP
            self.session = aiohttp.ClientSession()
            
            # Verifica che il canale esista
            status = await self._check_channel()
            if not status:
                logger.error(f"Impossibile trovare il canale Kick {self.channel_name}.")
                await self.session.close()
                self.session = None
                return False
            
            self.is_running = True
            
            # Avvia il task di aggiornamento
            self.update_task = asyncio.create_task(self._update_loop())
            
            logger.info("Gestore metriche Kick avviato")
            return True
        except Exception as e:
            logger.error(f"Errore nell'avvio del gestore metriche Kick: {e}")
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
                
                logger.info("Gestore metriche Kick fermato")
                return True
            except Exception as e:
                logger.error(f"Errore nella chiusura del gestore metriche Kick: {e}")
                return False
        return True
    
    async def _check_channel(self) -> bool:
        """
        Verifica che il canale esista
        
        Returns:
            bool: True se il canale esiste, False altrimenti
        """
        if not self.session:
            return False
        
        try:
            # Effettua la richiesta all'API pubblica di Kick
            async with self.session.get(
                f"https://kick.com/api/v1/channels/{self.channel_name}"
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella verifica del canale: {error_text}")
                    return False
                
                data = await response.json()
                
                # Salva le informazioni del canale
                self.current_metrics["channel_info"] = {
                    "id": data.get("id", ""),
                    "name": data.get("name", ""),
                    "slug": data.get("slug", ""),
                    "playback_url": data.get("playback_url", "")
                }
                
                return True
        except Exception as e:
            logger.error(f"Eccezione nella verifica del canale: {e}")
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
            logger.info("Loop di aggiornamento metriche Kick interrotto")
            raise
        except Exception as e:
            logger.error(f"Errore nel loop di aggiornamento: {e}")
    
    async def _update_metrics(self) -> bool:
        """
        Aggiorna le metriche di Kick
        
        Returns:
            bool: True se l'aggiornamento è riuscito, False altrimenti
        """
        if not self.session or not self.is_running:
            return False
        
        try:
            # Effettua la richiesta all'API pubblica di Kick
            async with self.session.get(
                f"https://kick.com/api/v1/channels/{self.channel_name}"
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nell'ottenimento delle metriche del canale: {error_text}")
                    return False
                
                data = await response.json()
                
                # Verifica se il canale è in diretta
                self.current_metrics["live_status"] = data.get("is_live", False)
                
                if self.current_metrics["live_status"]:
                    # Se è in diretta, aggiorna le metriche
                    self.current_metrics["live_viewers"] = data.get("viewer_count", 0)
                else:
                    # Se non è in diretta, azzera le metriche
                    self.current_metrics["live_viewers"] = 0
                
                # Aggiorna il timestamp
                self.current_metrics["last_updated"] = int(time.time())
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento delle metriche: {e}")
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

# Funzione per creare un'istanza del gestore delle metriche Kick
def create_kick_metrics(config: Dict[str, Any], update_callback: Optional[Callable] = None) -> KickMetrics:
    """
    Crea un'istanza del gestore delle metriche Kick
    
    Args:
        config: Configurazione del gestore
        update_callback: Funzione di callback chiamata quando ci sono aggiornamenti
        
    Returns:
        KickMetrics: Istanza del gestore delle metriche Kick
    """
    return KickMetrics(config, update_callback) 