import os
import time
import json
import logging
import asyncio
import psutil
import aiohttp
import platform
import smtplib
from email.message import EmailMessage
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
                "websocket": True,
                "redis": True
            },
            "response_times": {
                "database": 0,
                "api": 0,
                "websocket": 0
            }
        }
        
        # Stato di notifica per evitare notifiche ripetute
        self.notification_state = {
            "database": True,
            "api": True,
            "websocket": True,
            "redis": True
        }
        
        # Contatori di errori
        self.error_counters = {
            "database": 0,
            "api": 0,
            "websocket": 0,
            "redis": 0
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
                
                # Verifica se ci sono problemi critici che richiedono notifiche
                await self._check_for_critical_issues()
                
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
            
            # Log solo se ci sono cambiamenti significativi
            if cpu_percent > 80 or mem_usage_mb > 500 or disk_percent > 90:
                logger.warning(f"Utilizzo risorse elevato: CPU={cpu_percent}%, MEM={mem_usage_mb:.2f}MB, DISK={disk_percent}%")
            else:
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
        
        # Controllo Redis
        await self._check_redis()
    
    async def _check_database(self):
        """Verifica la connessione al database"""
        try:
            # Ottenere la connessione dal pool
            db_pool = self.config.get("db_pool")
            if not db_pool:
                # Database non configurato
                logger.warning("Pool di database non configurato nel monitor")
                self.status["services"]["database"] = False
                return
            
            start_time = time.time()
            
            # Esegui una query semplice per verificare la connessione
            async with db_pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                
            # Calcola il tempo di risposta
            response_time = (time.time() - start_time) * 1000  # ms
            self.status["response_times"]["database"] = response_time
            
            if result == 1:
                self.status["services"]["database"] = True
                self.error_counters["database"] = 0
                
                if response_time > 500:  # più di 500ms è lento
                    logger.warning(f"Database risponde lentamente: {response_time:.2f}ms")
                else:
                    logger.debug(f"Database OK: {response_time:.2f}ms")
            else:
                self.status["services"]["database"] = False
                self.error_counters["database"] += 1
                logger.error("Errore nella verifica del database: risultato non valido")
                
        except Exception as e:
            self.status["services"]["database"] = False
            self.error_counters["database"] += 1
            logger.error(f"Errore di connessione al database: {e}")
            
    async def _check_api(self):
        """Verifica la connessione all'API"""
        try:
            if "api_url" in self.config:
                start_time = time.time()
                
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"{self.config['api_url']}/api/status", timeout=5) as response:
                        # Calcola il tempo di risposta
                        response_time = (time.time() - start_time) * 1000  # ms
                        self.status["response_times"]["api"] = response_time
                        
                        if response.status == 200:
                            self.status["services"]["api"] = True
                            self.error_counters["api"] = 0
                            
                            if response_time > 1000:  # più di 1000ms è lento
                                logger.warning(f"API risponde lentamente: {response_time:.2f}ms")
                            else:
                                logger.debug(f"API OK: {response_time:.2f}ms")
                        else:
                            self.status["services"]["api"] = False
                            self.error_counters["api"] += 1
                            logger.error(f"API non disponibile: status {response.status}")
            else:
                # Se l'API non è configurata, la consideriamo attiva
                self.status["services"]["api"] = True
                
        except aiohttp.ClientError as e:
            self.status["services"]["api"] = False
            self.error_counters["api"] += 1
            logger.error(f"Errore di connessione all'API: {e}")
        except asyncio.TimeoutError:
            self.status["services"]["api"] = False
            self.error_counters["api"] += 1
            logger.error("Timeout durante la connessione all'API")
        except Exception as e:
            self.status["services"]["api"] = False
            self.error_counters["api"] += 1
            logger.error(f"Errore generico durante la connessione all'API: {e}")
    
    async def _check_websocket(self):
        """Verifica la connessione WebSocket"""
        try:
            if "websocket_url" in self.config:
                start_time = time.time()
                
                # Utilizza websockets per verificare la connessione
                try:
                    async with websockets.connect(self.config["websocket_url"], timeout=5) as websocket:
                        await websocket.ping()
                        
                        # Calcola il tempo di risposta
                        response_time = (time.time() - start_time) * 1000  # ms
                        self.status["response_times"]["websocket"] = response_time
                        
                        self.status["services"]["websocket"] = True
                        self.error_counters["websocket"] = 0
                        
                        if response_time > 500:
                            logger.warning(f"WebSocket risponde lentamente: {response_time:.2f}ms")
                        else:
                            logger.debug(f"WebSocket OK: {response_time:.2f}ms")
                except (websockets.exceptions.WebSocketException, asyncio.TimeoutError) as e:
                    self.status["services"]["websocket"] = False
                    self.error_counters["websocket"] += 1
                    logger.error(f"Errore nella connessione WebSocket: {e}")
            else:
                # Se il WebSocket non è configurato, lo consideriamo attivo
                self.status["services"]["websocket"] = True
        except Exception as e:
            self.status["services"]["websocket"] = False
            self.error_counters["websocket"] += 1
            logger.error(f"Errore generico durante la verifica WebSocket: {e}")
    
    async def _check_redis(self):
        """Verifica la connessione a Redis"""
        try:
            redis_client = self.config.get("redis_client")
            if not redis_client:
                # Redis non configurato
                return
                
            # Verifica la connessione
            result = await redis_client.ping()
            if result:
                self.status["services"]["redis"] = True
                self.error_counters["redis"] = 0
                logger.debug("Redis OK")
            else:
                self.status["services"]["redis"] = False
                self.error_counters["redis"] += 1
                logger.error("Redis non risponde correttamente")
        except Exception as e:
            self.status["services"]["redis"] = False
            self.error_counters["redis"] += 1
            logger.error(f"Errore nella connessione a Redis: {e}")
    
    async def _check_for_critical_issues(self):
        """Verifica se ci sono problemi critici che richiedono notifiche"""
        critical_issues = []
        
        # Controllo servizi
        for service, status in self.status["services"].items():
            # Se il servizio è inattivo e lo stato delle notifiche è attivo
            if not status and self.notification_state[service]:
                critical_issues.append(f"Servizio {service} non disponibile")
                # Imposta lo stato della notifica a False per evitare notifiche ripetute
                self.notification_state[service] = False
            # Se il servizio è tornato attivo e lo stato delle notifiche è disattivato
            elif status and not self.notification_state[service]:
                # Ripristina lo stato della notifica
                self.notification_state[service] = True
                await self._send_notification(f"Servizio {service} ripristinato", "info")
        
        # Controllo utilizzo risorse
        if self.status["cpu_usage"] > 90:
            critical_issues.append(f"Utilizzo CPU critico: {self.status['cpu_usage']:.1f}%")
            
        if self.status["memory_usage"] > 1000:  # 1GB
            critical_issues.append(f"Utilizzo memoria critico: {self.status['memory_usage']:.1f}MB")
            
        if self.status["disk_usage"] > 95:
            critical_issues.append(f"Spazio su disco critico: {self.status['disk_usage']:.1f}%")
        
        # Se ci sono problemi critici, invia notifica
        if critical_issues:
            message = "PROBLEMI CRITICI RILEVATI:\n" + "\n".join(critical_issues)
            await self._send_notification(message, "critical")
    
    async def _send_notification(self, message: str, level: str = "info"):
        """Invia una notifica tramite i canali configurati"""
        try:
            # Registra nel log
            if level == "critical":
                logger.critical(message)
            elif level == "error":
                logger.error(message)
            else:
                logger.info(message)
            
            # Telegram
            if "telegram_bot_token" in self.config and "telegram_chat_id" in self.config:
                await self._send_telegram_notification(message, level)
            
            # Email
            if level == "critical" and "email_config" in self.config:
                await self._send_email_notification(message)
            
            # Discord (webhook)
            if "discord_webhook_url" in self.config:
                await self._send_discord_notification(message, level)
        except Exception as e:
            logger.error(f"Errore nell'invio delle notifiche: {e}")
    
    async def _send_telegram_notification(self, message: str, level: str):
        """Invia una notifica tramite Telegram"""
        try:
            # Formatta il messaggio
            if level == "critical":
                formatted_message = f"🔴 *CRITICO*: {message}"
            elif level == "error":
                formatted_message = f"🟠 *ERRORE*: {message}"
            elif level == "warning":
                formatted_message = f"🟡 *AVVISO*: {message}"
            else:
                formatted_message = f"🟢 *INFO*: {message}"
            
            # Invia il messaggio
            bot_token = self.config["telegram_bot_token"]
            chat_id = self.config["telegram_chat_id"]
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            
            async with aiohttp.ClientSession() as session:
                await session.post(url, data={
                    "chat_id": chat_id,
                    "text": formatted_message,
                    "parse_mode": "Markdown"
                })
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica Telegram: {e}")
    
    async def _send_email_notification(self, message: str):
        """Invia una notifica tramite email"""
        try:
            email_config = self.config["email_config"]
            
            msg = EmailMessage()
            msg.set_content(message)
            msg["Subject"] = f"M4Bot - AVVISO CRITICO - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            msg["From"] = email_config["sender"]
            msg["To"] = email_config["recipient"]
            
            # Invio asincrono dell'email
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_email, msg, email_config)
            
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica email: {e}")
    
    def _send_email(self, msg, email_config):
        """Funzione sincrona per l'invio dell'email"""
        try:
            with smtplib.SMTP_SSL(email_config["smtp_server"], email_config["smtp_port"]) as server:
                server.login(email_config["username"], email_config["password"])
                server.send_message(msg)
        except Exception as e:
            logger.error(f"Errore nell'invio dell'email: {e}")
    
    async def _send_discord_notification(self, message: str, level: str):
        """Invia una notifica tramite Discord webhook"""
        try:
            webhook_url = self.config["discord_webhook_url"]
            
            # Determina il colore dell'embed in base al livello
            if level == "critical":
                color = 16711680  # Rosso
                title = "⚠️ AVVISO CRITICO"
            elif level == "error":
                color = 16744192  # Arancione
                title = "⚠️ ERRORE"
            elif level == "warning":
                color = 16776960  # Giallo
                title = "⚠️ AVVISO"
            else:
                color = 65280  # Verde
                title = "ℹ️ INFORMAZIONE"
            
            # Crea l'embed per Discord
            embed = {
                "title": title,
                "description": message,
                "color": color,
                "timestamp": datetime.now().isoformat(),
                "footer": {
                    "text": f"M4Bot Health Monitor - {self.status['system_info']['hostname']}"
                }
            }
            
            # Invia il webhook
            async with aiohttp.ClientSession() as session:
                await session.post(webhook_url, json={"embeds": [embed]})
                
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica Discord: {e}")
    
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
    
    async def auto_restart_service(self, service_name: str) -> bool:
        """
        Tenta di riavviare automaticamente un servizio in errore
        
        Args:
            service_name: Nome del servizio da riavviare
            
        Returns:
            bool: True se il riavvio è riuscito, False altrimenti
        """
        try:
            if service_name == "redis":
                # Riavvio di Redis su Linux
                process = await asyncio.create_subprocess_shell(
                    "sudo systemctl restart redis-server",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    logger.info("Servizio Redis riavviato con successo")
                    return True
                else:
                    logger.error(f"Errore nel riavvio di Redis: {stderr.decode()}")
                    return False
                    
            elif service_name == "database":
                # Riavvio di PostgreSQL su Linux
                process = await asyncio.create_subprocess_shell(
                    "sudo systemctl restart postgresql",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    logger.info("Servizio Database riavviato con successo")
                    return True
                else:
                    logger.error(f"Errore nel riavvio del Database: {stderr.decode()}")
                    return False
                    
            else:
                logger.warning(f"Riavvio automatico non implementato per il servizio {service_name}")
                return False
        except Exception as e:
            logger.error(f"Errore durante il tentativo di riavvio del servizio {service_name}: {e}")
            return False
    
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