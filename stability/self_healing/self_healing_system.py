#!/usr/bin/env python3
"""
M4Bot - Sistema di Self-Healing

Questo modulo implementa un sistema di auto-riparazione che monitora e ripristina
automaticamente i servizi M4Bot in caso di problemi, garantendo alta disponibilità
e resilienza dell'intero sistema.

Funzionalità:
- Monitoraggio continuo dei servizi e componenti
- Rilevamento automatico di guasti e anomalie
- Ripristino dei servizi in caso di crash
- Gestione dei problemi di risorse (CPU, memoria, disco)
- Logging dettagliato degli interventi di riparazione
"""

import os
import sys
import json
import time
import logging
import asyncio
import subprocess
from typing import Dict, List, Any, Optional, Tuple, Callable, Set
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('m4bot.stability.self_healing')

class HealthStatus(Enum):
    """Stato di salute di un componente."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

class ServiceType(Enum):
    """Tipi di servizi supportati."""
    SYSTEMD = "systemd"
    PROCESS = "process"
    DOCKER = "docker"
    API = "api"
    CUSTOM = "custom"

@dataclass
class SystemHealth:
    """Rappresenta lo stato di salute complessivo del sistema."""
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    disk_usage: float = 0.0
    load_average: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check: float = field(default_factory=time.time)
    
    def update(self):
        """Aggiorna lo stato di salute del sistema."""
        try:
            import psutil
            
            # CPU
            self.cpu_usage = psutil.cpu_percent(interval=1)
            
            # Memoria
            memory = psutil.virtual_memory()
            self.memory_usage = memory.percent
            
            # Disco
            disk = psutil.disk_usage('/')
            self.disk_usage = disk.percent
            
            # Load average
            self.load_average = list(psutil.getloadavg())
            
            # Determina lo stato complessivo
            if (self.cpu_usage > 90 or self.memory_usage > 90 or self.disk_usage > 90):
                self.status = HealthStatus.UNHEALTHY
            elif (self.cpu_usage > 75 or self.memory_usage > 75 or self.disk_usage > 75):
                self.status = HealthStatus.DEGRADED
            else:
                self.status = HealthStatus.HEALTHY
                
            self.last_check = time.time()
            
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento dello stato del sistema: {e}")
            self.status = HealthStatus.UNKNOWN
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte lo stato di salute in dizionario."""
        return {
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "disk_usage": self.disk_usage,
            "load_average": self.load_average,
            "status": self.status.value,
            "last_check": self.last_check
        }

@dataclass
class ServiceStatus:
    """Rappresenta lo stato di un servizio."""
    name: str
    type: ServiceType
    is_healthy: bool = False
    last_check: float = field(default_factory=time.time)
    consecutive_failures: int = 0
    restart_count: int = 0
    last_restart: float = 0
    last_error: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte lo stato del servizio in dizionario."""
        return {
            "name": self.name,
            "type": self.type.value,
            "is_healthy": self.is_healthy,
            "last_check": self.last_check,
            "consecutive_failures": self.consecutive_failures,
            "restart_count": self.restart_count,
            "last_restart": self.last_restart,
            "last_error": self.last_error
        }

@dataclass
class RepairAction:
    """Rappresenta un'azione di riparazione."""
    service: str
    action_type: str
    timestamp: float = field(default_factory=time.time)
    details: str = ""
    success: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte l'azione in dizionario."""
        return {
            "service": self.service,
            "action_type": self.action_type,
            "timestamp": self.timestamp,
            "details": self.details,
            "success": self.success
        }

class SelfHealingSystem:
    """Sistema di auto-riparazione per M4Bot."""
    
    _instance = None
    
    @classmethod
    def get_instance(cls):
        """Restituisce l'istanza singleton."""
        if cls._instance is None:
            cls._instance = SelfHealingSystem()
        return cls._instance
    
    def __init__(self, config_path: str = None):
        """
        Inizializza il sistema di self-healing.
        
        Args:
            config_path: Percorso del file di configurazione (opzionale)
        """
        if SelfHealingSystem._instance is not None:
            raise RuntimeError("Usa get_instance() per ottenere un'istanza di SelfHealingSystem")
        
        self.system_health = SystemHealth()
        self.services: Dict[str, ServiceStatus] = {}
        self.repair_history: List[RepairAction] = []
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        
        # Stato del sistema
        self.running = False
        self.monitoring_task = None
        
        # Intervalli di tempo (in secondi)
        self.system_check_interval = 60
        self.service_check_interval = 30
        self.cleanup_interval = 3600  # 1 ora
        
        # Soglie
        self.max_restarts = 5  # Numero massimo di riavvii in succession
        self.restart_window = 300  # Finestra di tempo per contare i riavvii (5 minuti)
        
        # Inizializza lo stato dei servizi dal config
        self._init_services()
        
        logger.info("Sistema di self-healing inizializzato")
    
    def _get_default_config_path(self) -> str:
        """Restituisce il percorso di default del file di configurazione."""
        # Cerca prima nella directory corrente
        if os.path.exists("m4bot_config.json"):
            return "m4bot_config.json"
            
        # Altrimenti usa un percorso relativo alla posizione del modulo
        module_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(module_dir, "..", "..", "M4Bot-Config", "self_healing.json")
    
    def _load_config(self) -> Dict[str, Any]:
        """Carica la configurazione dal file."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                logger.info(f"Configurazione caricata da {self.config_path}")
                return config
            else:
                logger.warning(f"File di configurazione {self.config_path} non trovato, uso configurazione predefinita")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"Errore nel caricamento della configurazione: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Restituisce una configurazione predefinita."""
        return {
            "services": {
                "web": {
                    "type": "systemd",
                    "unit": "m4bot-web.service",
                    "check_type": "systemd",
                    "max_restarts": 5
                },
                "bot": {
                    "type": "systemd",
                    "unit": "m4bot-bot.service",
                    "check_type": "systemd",
                    "max_restarts": 5
                },
                "database": {
                    "type": "systemd",
                    "unit": "postgresql.service",
                    "check_type": "systemd",
                    "max_restarts": 3
                },
                "nginx": {
                    "type": "systemd",
                    "unit": "nginx.service",
                    "check_type": "systemd",
                    "max_restarts": 3
                }
            },
            "system": {
                "check_interval": 60,
                "service_check_interval": 30,
                "cleanup_interval": 3600,
                "max_restarts": 5,
                "restart_window": 300
            }
        }
    
    def _init_services(self):
        """Inizializza lo stato dei servizi dal config."""
        for name, config in self.config.get('services', {}).items():
            service_type = ServiceType(config.get('type', 'systemd'))
            self.services[name] = ServiceStatus(
                name=name,
                type=service_type
            )
        
        logger.info(f"Inizializzati {len(self.services)} servizi")
    
    def save_config(self):
        """Salva la configurazione su file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"Configurazione salvata in {self.config_path}")
        except Exception as e:
            logger.error(f"Errore nel salvataggio della configurazione: {e}")
    
    async def start(self):
        """Avvia il sistema di self-healing."""
        if self.running:
            logger.warning("Il sistema di self-healing è già in esecuzione")
            return
        
        self.running = True
        logger.info("Avvio sistema di self-healing")
        
        # Imposta gli intervalli dalle configurazioni
        system_config = self.config.get('system', {})
        self.system_check_interval = system_config.get('check_interval', self.system_check_interval)
        self.service_check_interval = system_config.get('service_check_interval', self.service_check_interval)
        self.cleanup_interval = system_config.get('cleanup_interval', self.cleanup_interval)
        self.max_restarts = system_config.get('max_restarts', self.max_restarts)
        self.restart_window = system_config.get('restart_window', self.restart_window)
        
        # Avvia il task di monitoraggio
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
    
    async def stop(self):
        """Ferma il sistema di self-healing."""
        if not self.running:
            return
            
        self.running = False
        logger.info("Arresto sistema di self-healing")
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
            self.monitoring_task = None
    
    async def _monitoring_loop(self):
        """Loop principale di monitoraggio."""
        logger.info("Avvio loop di monitoraggio")
        
        last_system_check = 0
        last_cleanup = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                # Controlla lo stato del sistema periodicamente
                if current_time - last_system_check >= self.system_check_interval:
                    self.system_health.update()
                    last_system_check = current_time
                    
                    # Logging della salute del sistema
                    logger.info(f"Stato sistema: {self.system_health.status.value}, "
                               f"CPU: {self.system_health.cpu_usage:.1f}%, "
                               f"MEM: {self.system_health.memory_usage:.1f}%, "
                               f"DISK: {self.system_health.disk_usage:.1f}%")
                
                # Controlla tutti i servizi
                for name, service in self.services.items():
                    # Controlla se è il momento di verificare questo servizio
                    if current_time - service.last_check >= self.service_check_interval:
                        await self._check_service(name)
                
                # Cleanup periodico
                if current_time - last_cleanup >= self.cleanup_interval:
                    self._cleanup_history()
                    last_cleanup = current_time
                
                # Breve pausa per non consumare risorse
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                logger.info("Loop di monitoraggio cancellato")
                break
            except Exception as e:
                logger.error(f"Errore nel loop di monitoraggio: {e}")
                await asyncio.sleep(5)  # Attesa più lunga in caso di errore
    
    async def _check_service(self, service_name: str):
        """Controlla lo stato di un servizio e lo ripara se necessario."""
        if service_name not in self.services:
            logger.error(f"Servizio {service_name} non trovato")
            return
        
        service = self.services[service_name]
        service_config = self.config['services'].get(service_name, {})
        
        # Aggiorna il timestamp del controllo
        service.last_check = time.time()
        
        try:
            # Controlla lo stato del servizio in base al tipo
            is_healthy = False
            error_message = ""
            
            if service.type == ServiceType.SYSTEMD:
                is_healthy, error_message = await self._check_systemd_service(
                    service_config.get('unit', f"m4bot-{service_name}.service")
                )
                
            elif service.type == ServiceType.PROCESS:
                is_healthy, error_message = self._check_process_service(
                    service_config.get('process_name', service_name),
                    service_config.get('pid_file')
                )
                
            elif service.type == ServiceType.DOCKER:
                is_healthy, error_message = await self._check_docker_service(
                    service_config.get('container', service_name)
                )
                
            elif service.type == ServiceType.API:
                is_healthy, error_message = await self._check_api_service(
                    service_config.get('url'),
                    service_config.get('expected_status', 200)
                )
            
            # Aggiorna lo stato del servizio
            old_state = service.is_healthy
            service.is_healthy = is_healthy
            
            if not is_healthy:
                service.consecutive_failures += 1
                service.last_error = error_message
                logger.warning(f"Servizio {service_name} non funzionante: {error_message} "
                              f"({service.consecutive_failures} fallimenti consecutivi)")
                
                # Tenta la riparazione se necessario
                if service.consecutive_failures >= service_config.get('failure_threshold', 3):
                    await self._repair_service(service_name)
            else:
                if not old_state and is_healthy:
                    logger.info(f"Servizio {service_name} tornato operativo")
                
                service.consecutive_failures = 0
                service.last_error = ""
                
        except Exception as e:
            logger.error(f"Errore nel controllo del servizio {service_name}: {e}")
            service.last_error = str(e)
    
    async def _check_systemd_service(self, unit: str) -> Tuple[bool, str]:
        """Controlla lo stato di un servizio systemd."""
        try:
            proc = await asyncio.create_subprocess_exec(
                'systemctl', 'is-active', unit,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            is_active = proc.returncode == 0
            message = "active" if is_active else stderr.decode().strip() or "inactive"
            
            return is_active, message
            
        except Exception as e:
            return False, f"Errore systemd: {str(e)}"
    
    def _check_process_service(self, process_name: str, pid_file: Optional[str] = None) -> Tuple[bool, str]:
        """Controlla lo stato di un processo."""
        try:
            if pid_file and os.path.exists(pid_file):
                # Leggi il PID dal file
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                # Verifica se il processo esiste
                try:
                    os.kill(pid, 0)  # Signal 0 non fa nulla, ma verifica l'esistenza
                    return True, "running"
                except OSError:
                    return False, f"PID {pid} non trovato"
            
            # Altrimenti cerca per nome con 'ps'
            proc = subprocess.run(
                ['ps', '-ef'],
                capture_output=True,
                text=True
            )
            
            if proc.returncode == 0 and process_name in proc.stdout:
                return True, "running"
            else:
                return False, "process not found"
            
        except Exception as e:
            return False, f"Errore nel controllo processo: {str(e)}"
    
    async def _check_docker_service(self, container: str) -> Tuple[bool, str]:
        """Controlla lo stato di un container Docker."""
        try:
            proc = await asyncio.create_subprocess_exec(
                'docker', 'inspect', '--format={{.State.Running}}', container,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                is_running = stdout.decode().strip() == "true"
                return is_running, "running" if is_running else "not running"
            else:
                return False, stderr.decode().strip() or "container not found"
                
        except Exception as e:
            return False, f"Errore Docker: {str(e)}"
    
    async def _check_api_service(self, url: str, expected_status: int = 200) -> Tuple[bool, str]:
        """Controlla lo stato di un'API HTTP."""
        if not url:
            return False, "URL non specificato"
            
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == expected_status:
                        return True, f"HTTP {response.status}"
                    else:
                        return False, f"Stato HTTP non valido: {response.status}"
                    
        except aiohttp.ClientError as e:
            return False, f"Errore connessione: {str(e)}"
        except Exception as e:
            return False, f"Errore API: {str(e)}"
    
    async def _repair_service(self, service_name: str):
        """Tenta di riparare un servizio problematico."""
        if service_name not in self.services:
            logger.error(f"Tentativo di riparare servizio inesistente: {service_name}")
            return
            
        service = self.services[service_name]
        service_config = self.config['services'].get(service_name, {})
        
        # Verifica se abbiamo già riavviato troppo spesso
        recent_restarts = 0
        current_time = time.time()
        
        for action in self.repair_history:
            if (action.service == service_name and 
                action.action_type == "restart" and
                current_time - action.timestamp < self.restart_window):
                recent_restarts += 1
        
        service_max_restarts = service_config.get('max_restarts', self.max_restarts)
        
        if recent_restarts >= service_max_restarts:
            logger.warning(f"Troppi riavvii recenti per {service_name} ({recent_restarts}), salta riparazione")
            
            # Registra l'azione saltata
            self.repair_history.append(RepairAction(
                service=service_name,
                action_type="skip_restart",
                details=f"Troppi riavvii recenti: {recent_restarts} in {self.restart_window}s",
                success=False
            ))
            
            return
        
        # Tenta la riparazione in base al tipo
        action = RepairAction(
            service=service_name,
            action_type="restart"
        )
        
        try:
            if service.type == ServiceType.SYSTEMD:
                unit = service_config.get('unit', f"m4bot-{service_name}.service")
                
                logger.info(f"Tentativo di riavvio servizio systemd {unit}")
                proc = await asyncio.create_subprocess_exec(
                    'systemctl', 'restart', unit,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                
                if proc.returncode == 0:
                    action.success = True
                    action.details = "Riavvio systemd completato"
                else:
                    action.success = False
                    action.details = f"Errore riavvio systemd: {stderr.decode().strip()}"
                
            elif service.type == ServiceType.DOCKER:
                container = service_config.get('container', service_name)
                
                logger.info(f"Tentativo di riavvio container Docker {container}")
                proc = await asyncio.create_subprocess_exec(
                    'docker', 'restart', container,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                
                if proc.returncode == 0:
                    action.success = True
                    action.details = "Riavvio Docker completato"
                else:
                    action.success = False
                    action.details = f"Errore riavvio Docker: {stderr.decode().strip()}"
                
            elif service.type == ServiceType.PROCESS:
                # Per i processi generici, potremmo avere uno script di riavvio
                restart_script = service_config.get('restart_script')
                
                if restart_script:
                    logger.info(f"Esecuzione script di riavvio per {service_name}")
                    proc = await asyncio.create_subprocess_shell(
                        restart_script,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await proc.communicate()
                    
                    if proc.returncode == 0:
                        action.success = True
                        action.details = "Script di riavvio completato"
                    else:
                        action.success = False
                        action.details = f"Errore script riavvio: {stderr.decode().strip()}"
                else:
                    action.success = False
                    action.details = "Nessun metodo di riavvio configurato"
                    
            else:
                action.success = False
                action.details = f"Tipo di servizio {service.type.value} non supportato per il riavvio"
            
        except Exception as e:
            action.success = False
            action.details = f"Eccezione: {str(e)}"
            logger.error(f"Errore nel tentativo di riparazione di {service_name}: {e}")
        
        # Aggiorna lo stato e registra l'azione
        if action.success:
            logger.info(f"Riparazione di {service_name} completata con successo")
            service.restart_count += 1
            service.last_restart = current_time
            
            # Resettiamo consecutive_failures per dare tempo al servizio di riprendersi
            service.consecutive_failures = 0
        else:
            logger.error(f"Riparazione di {service_name} fallita: {action.details}")
        
        self.repair_history.append(action)
    
    def _cleanup_history(self):
        """Pulisce la cronologia delle azioni troppo vecchie."""
        if not self.repair_history:
            return
            
        # Mantieni solo le azioni degli ultimi 7 giorni
        cutoff_time = time.time() - (7 * 24 * 3600)
        self.repair_history = [action for action in self.repair_history 
                              if action.timestamp >= cutoff_time]
        
        logger.info(f"Cronologia riparazioni ridotta a {len(self.repair_history)} azioni")
    
    def get_service_status(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Restituisce lo stato di un servizio specifico."""
        if service_name in self.services:
            return self.services[service_name].to_dict()
        return None
    
    def get_all_service_status(self) -> Dict[str, Dict[str, Any]]:
        """Restituisce lo stato di tutti i servizi."""
        return {name: service.to_dict() for name, service in self.services.items()}
    
    def get_repair_history(self, service_name: Optional[str] = None, 
                          limit: int = 100) -> List[Dict[str, Any]]:
        """
        Restituisce la cronologia delle azioni di riparazione.
        
        Args:
            service_name: Filtra per un servizio specifico (opzionale)
            limit: Numero massimo di azioni da restituire
        """
        if service_name:
            history = [action.to_dict() for action in self.repair_history 
                      if action.service == service_name]
        else:
            history = [action.to_dict() for action in self.repair_history]
        
        # Ordina per timestamp decrescente e limita
        return sorted(history, key=lambda x: x['timestamp'], reverse=True)[:limit]
    
    def get_system_health(self) -> Dict[str, Any]:
        """Restituisce lo stato di salute del sistema."""
        return self.system_health.to_dict()
    
    def get_status_summary(self) -> Dict[str, Any]:
        """Restituisce un riepilogo dello stato del sistema."""
        healthy_count = sum(1 for service in self.services.values() if service.is_healthy)
        unhealthy_count = len(self.services) - healthy_count
        
        # Conta riavvii nelle ultime 24 ore
        restart_24h = 0
        cutoff_time = time.time() - (24 * 3600)
        
        for action in self.repair_history:
            if action.action_type == "restart" and action.timestamp >= cutoff_time:
                restart_24h += 1
        
        return {
            "system_health": self.system_health.status.value,
            "cpu_usage": self.system_health.cpu_usage,
            "memory_usage": self.system_health.memory_usage,
            "disk_usage": self.system_health.disk_usage,
            "total_services": len(self.services),
            "healthy_services": healthy_count,
            "unhealthy_services": unhealthy_count, 
            "restarts_24h": restart_24h,
            "timestamp": time.time()
        }


# Funzione utility per ottenere l'istanza singleton
def get_self_healing_system() -> SelfHealingSystem:
    """Restituisce l'istanza singleton del sistema di self-healing."""
    return SelfHealingSystem.get_instance()

# Avvio del sistema quando il modulo è eseguito direttamente
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="M4Bot Self-Healing System")
    parser.add_argument("--config", type=str, help="Percorso del file di configurazione")
    args = parser.parse_args()
    
    # Inizializza il sistema
    if args.config:
        system = SelfHealingSystem(config_path=args.config)
    else:
        system = get_self_healing_system()
    
    # Avvia il loop di monitoraggio
    asyncio.run(system.start())
    
    try:
        # Mantieni il programma in esecuzione
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        print("Interruzione da tastiera, arresto in corso...")
    finally:
        # Ferma il sistema prima di uscire
        asyncio.run(system.stop()) 