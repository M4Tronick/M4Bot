import os
import time
import json
import logging
import asyncio
import psutil
import aiohttp
import platform
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/health_monitor.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("HealthMonitor")

class HealthMonitor:
    """Sistema di monitoraggio della salute per M4Bot"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Inizializza il monitor di salute
        
        Args:
            config: Configurazione del monitor
        """
        self.config = config
        self.process = psutil.Process(os.getpid())
        self.start_time = datetime.now()
        self.last_heartbeat = datetime.now()
        self.status = {
            "online": True,
            "uptime": 0,
            "cpu_usage": 0.0,
            "memory_usage": 0.0,
            "disk_usage": 0.0,
            "system_info": self._get_system_info(),
            "last_errors": [],
            "last_check": datetime.now().isoformat(),
            "services": {
                "database": True,
                "api": True,
                "websocket": True
            }
        }
        
        # Crea la directory dei log se non esiste
        os.makedirs("logs", exist_ok=True)
        
        # Task di monitoraggio
        self.monitor_task = None
        
        logger.info("Monitor di salute inizializzato")
    
    async def start_monitoring(self):
        """Avvia il task di monitoraggio"""
        self.monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Monitoraggio avviato")
    
    async def stop_monitoring(self):
        """Ferma il monitoraggio"""
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
            self.monitor_task = None
            logger.info("Monitoraggio fermato")
    
    def _get_system_info(self) -> Dict[str, str]:
        """Raccoglie informazioni sul sistema"""
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "python_version": platform.python_version(),
            "processor": platform.processor(),
            "hostname": platform.node()
        }
    
    async def _monitor_loop(self):
        """Loop principale di monitoraggio"""
        while True:
            try:
                # Aggiorna le statistiche
                self._update_stats()
                
                # Verifica i servizi
                await self._check_services()
                
                # Salva lo stato attuale
                self._save_status()
                
                # Invia heartbeat al server web se configurato
                if "api_url" in self.config and "api_key" in self.config:
                    await self._send_heartbeat()
                
            except Exception as e:
                logger.error(f"Errore durante il monitoraggio: {e}")
                
                # Aggiungi l'errore alla lista degli ultimi errori
                self.status["last_errors"].append({
                    "timestamp": datetime.now().isoformat(),
                    "error": str(e)
                })
                
                # Mantieni solo gli ultimi 10 errori
                self.status["last_errors"] = self.status["last_errors"][-10:]
            
            # Attendi prima del prossimo controllo
            await asyncio.sleep(self.config.get("monitor_interval", 30))
    
    def _update_stats(self):
        """Aggiorna le statistiche di sistema"""
        try:
            # Calcola uptime
            uptime = datetime.now() - self.start_time
            uptime_seconds = int(uptime.total_seconds())
            
            # Ottieni utilizzo CPU
            cpu_percent = self.process.cpu_percent(interval=1.0)
            
            # Ottieni utilizzo memoria
            mem_info = self.process.memory_info()
            mem_usage_mb = mem_info.rss / (1024 * 1024)
            
            # Ottieni spazio su disco
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # Aggiorna lo stato
            self.status.update({
                "uptime": uptime_seconds,
                "cpu_usage": cpu_percent,
                "memory_usage": mem_usage_mb,
                "disk_usage": disk_percent,
                "last_check": datetime.now().isoformat()
            })
            
            logger.debug(f"Statistiche aggiornate: CPU={cpu_percent}%, MEM={mem_usage_mb:.2f}MB, DISK={disk_percent}%")
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento delle statistiche: {e}")
    
    async def _check_services(self):
        """Verifica lo stato dei servizi collegati"""
        # Controllo database
        await self._check_database()
        
        # Controllo API
        await self._check_api()
        
        # Controllo WebSocket
        await self._check_websocket()
    
    async def _check_database(self):
        """Verifica la connessione al database"""
        try:
            # Qui implementare il controllo effettivo del database
            # Per ora simula un risultato positivo
            self.status["services"]["database"] = True
        except Exception as e:
            logger.error(f"Errore di connessione al database: {e}")
            self.status["services"]["database"] = False
    
    async def _check_api(self):
        """Verifica la connessione all'API"""
        try:
            if "api_url" in self.config:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.config['api_url']}/api/status", timeout=5) as response:
                        self.status["services"]["api"] = response.status == 200
            else:
                # Se l'API non è configurata, la consideriamo attiva
                self.status["services"]["api"] = True
        except Exception as e:
            logger.error(f"Errore di connessione all'API: {e}")
            self.status["services"]["api"] = False
    
    async def _check_websocket(self):
        """Verifica la connessione WebSocket"""
        try:
            if "websocket_url" in self.config:
                # Implementare la verifica del WebSocket
                # Per ora simula un risultato positivo
                self.status["services"]["websocket"] = True
            else:
                # Se il WebSocket non è configurato, lo consideriamo attivo
                self.status["services"]["websocket"] = True
        except Exception as e:
            logger.error(f"Errore di connessione al WebSocket: {e}")
            self.status["services"]["websocket"] = False
    
    async def _send_heartbeat(self):
        """Invia heartbeat al server web"""
        try:
            if "api_url" in self.config and "api_key" in self.config:
                async with aiohttp.ClientSession() as session:
                    headers = {"X-API-Key": self.config["api_key"]}
                    async with session.post(
                        f"{self.config['api_url']}/api/heartbeat", 
                        json=self.status,
                        headers=headers,
                        timeout=5
                    ) as response:
                        if response.status == 200:
                            self.last_heartbeat = datetime.now()
                            logger.debug("Heartbeat inviato con successo")
                        else:
                            logger.warning(f"Errore nell'invio del heartbeat: {response.status}")
        except Exception as e:
            logger.error(f"Errore nell'invio del heartbeat: {e}")
    
    def _save_status(self):
        """Salva lo stato nel file di status"""
        try:
            with open("logs/health_status.json", "w") as f:
                json.dump(self.status, f, indent=2)
        except Exception as e:
            logger.error(f"Errore nel salvataggio dello stato: {e}")
    
    def update_heartbeat(self):
        """Aggiorna il timestamp dell'ultimo heartbeat"""
        self.last_heartbeat = datetime.now()
        self.status["online"] = True
    
    def get_status(self) -> Dict[str, Any]:
        """Restituisce lo stato attuale del sistema"""
        # Aggiorna lo stato prima di restituirlo
        self._update_stats()
        return self.status
    
    def log_error(self, error: str, severity: str = "error"):
        """Registra un errore nel sistema di monitoraggio"""
        logger.error(error)
        self.status["last_errors"].append({
            "timestamp": datetime.now().isoformat(),
            "error": error,
            "severity": severity
        })
        
        # Mantieni solo gli ultimi 10 errori
        self.status["last_errors"] = self.status["last_errors"][-10:]
        
        # Salva lo stato aggiornato
        self._save_status()

# Funzione per creare un'istanza del monitor di salute
def create_health_monitor(config: Dict[str, Any]) -> HealthMonitor:
    """
    Crea un'istanza del monitor di salute
    
    Args:
        config: Configurazione del monitor
        
    Returns:
        HealthMonitor: Istanza del monitor di salute
    """
    return HealthMonitor(config) 