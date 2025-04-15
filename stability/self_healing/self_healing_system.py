#!/usr/bin/env python3
"""
M4Bot - Sistema di Self-Healing

Questo modulo implementa un sistema di self-healing che rileva e corregge 
automaticamente problemi che potrebbero verificarsi nel sistema, garantendo
maggiore stabilità e uptime. Funzionalità principali:

- Rilevamento anomalie nei servizi
- Riavvio automatico di servizi in caso di problemi
- Gestione di problemi di memoria e risorse
- Interventi preventivi basati su segnali di degrado
- Ripristino stato coerente dopo crash
"""

import os
import sys
import json
import time
import signal
import shutil
import logging
import asyncio
import subprocess
import traceback
import re
from typing import Dict, List, Any, Optional, Tuple, Callable, Set
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path

# Configurazione logging
logger = logging.getLogger('m4bot.stability.self_healing')

# Percorso predefinito per i servizi
SERVICE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'services')

# Configurazione predefinita
DEFAULT_CONFIG = {
    'enabled': True,
    'recovery_threshold': 3,       # Tentativi di riavvio prima di segnalare
    'max_restarts_per_day': 10,    # Limite riavvii giornalieri per servizio
    'check_interval': 60,          # Secondi tra controlli
    'maintenance_mode': False,     # Modalità manutenzione (no interventi)
    'services': {
        'web': {
            'type': 'systemd',
            'unit': 'm4bot-web.service',
            'critical': True,      # Servizio critico
            'healthcheck_url': 'http://localhost:5000/health',
            'restore_command': 'systemctl restart m4bot-web.service',
            'dependencies': ['database']
        },
        'bot': {
            'type': 'systemd',
            'unit': 'm4bot-bot.service',
            'critical': True,
            'healthcheck_url': 'http://localhost:5001/health',
            'restore_command': 'systemctl restart m4bot-bot.service',
            'dependencies': ['database']
        },
        'database': {
            'type': 'systemd',
            'unit': 'postgresql.service',
            'critical': True,
            'restore_command': 'systemctl restart postgresql.service',
            'dependencies': []
        },
        'nginx': {
            'type': 'systemd',
            'unit': 'nginx.service',
            'critical': False,
            'restore_command': 'systemctl restart nginx.service',
            'dependencies': []
        }
    },
    'resources': {
        'check_disk_space': True,
        'min_free_disk_percent': 10,   # Minimo % disco libero
        'disk_cleanup_command': 'find /var/log/m4bot -name "*.log.*" -type f -mtime +7 -delete',
        'max_memory_percent': 90,      # Massimo utilizzo memoria
        'memory_action': 'restart_high_consumers'  # Azione quando memoria troppo alta
    },
    'recovery_scripts': {
        'db_repair': os.path.join(SERVICE_DIR, 'scripts', 'repair_db.sh'),
        'cache_clear': os.path.join(SERVICE_DIR, 'scripts', 'clear_cache.sh'),
        'emergency_mode': os.path.join(SERVICE_DIR, 'scripts', 'emergency_mode.sh')
    },
    'backup': {
        'enabled': True,
        'auto_restore': True,          # Ripristina da backup in caso di fallimento
        'max_restore_age_hours': 24,   # Età massima backup per ripristino
        'backup_dir': os.path.join(SERVICE_DIR, 'backups')
    }
}

class ServiceStatus:
    """Rappresenta lo stato di un servizio monitorato."""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        self.type = config.get('type', 'systemd')
        self.is_healthy = False
        self.last_check = 0.0
        self.consecutive_failures = 0
        self.last_restart = 0.0
        self.restart_attempts = 0
        self.restarts_today = 0
        self.first_failure = 0.0
        self.last_error = ""
        self.status_history: List[bool] = []  # Cronologia stato recente
        self.recovery_in_progress = False
    
    def __str__(self) -> str:
        return (f"Service({self.name}, healthy={self.is_healthy}, "
                f"failures={self.consecutive_failures}, restarts={self.restart_attempts})")
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte lo stato in dizionario."""
        return {
            'name': self.name,
            'type': self.type,
            'is_healthy': self.is_healthy,
            'last_check': self.last_check,
            'consecutive_failures': self.consecutive_failures,
            'last_restart': self.last_restart,
            'restart_attempts': self.restart_attempts,
            'restarts_today': self.restarts_today,
            'first_failure': self.first_failure,
            'last_error': self.last_error,
            'recovery_in_progress': self.recovery_in_progress
        }
    
    def reset_restart_count(self):
        """Azzera il contatore dei riavvii per un nuovo giorno."""
        self.restarts_today = 0
    
    def update_status(self, is_healthy: bool, error: str = ""):
        """Aggiorna lo stato del servizio."""
        self.last_check = time.time()
        
        if is_healthy:
            # Se era in errore, resetta i contatori
            if self.consecutive_failures > 0:
                logger.info(f"Servizio {self.name} è tornato in salute dopo {self.consecutive_failures} fallimenti")
            
            self.is_healthy = True
            self.consecutive_failures = 0
            self.last_error = ""
        else:
            # Prima volta che fallisce
            if self.consecutive_failures == 0:
                self.first_failure = time.time()
            
            self.is_healthy = False
            self.consecutive_failures += 1
            self.last_error = error
            
            logger.warning(f"Servizio {self.name} non in salute: {error} (fallimento #{self.consecutive_failures})")
        
        # Mantieni storico di stato per analisi
        self.status_history.append(is_healthy)
        if len(self.status_history) > 100:
            self.status_history = self.status_history[-100:]

class SystemHealth:
    """Monitora lo stato di salute complessivo del sistema."""
    
    def __init__(self):
        self.disk_usage = 0.0
        self.memory_usage = 0.0
        self.cpu_usage = 0.0
        self.last_check = 0.0
        self.system_load = [0.0, 0.0, 0.0]
        self.open_files = 0
        self.active_connections = 0
        self.errors: List[Dict[str, Any]] = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte lo stato in dizionario."""
        return {
            'disk_usage': self.disk_usage,
            'memory_usage': self.memory_usage,
            'cpu_usage': self.cpu_usage,
            'last_check': self.last_check,
            'system_load': self.system_load,
            'open_files': self.open_files,
            'active_connections': self.active_connections,
            'errors': self.errors
        }

class SelfHealingSystem:
    """Sistema centrale di self-healing."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Inizializza il sistema di self-healing."""
        self.config = self._load_config(config_path)
        self.services: Dict[str, ServiceStatus] = {}
        self.system_health = SystemHealth()
        self.running = False
        self._check_task = None
        self.recovery_lock = asyncio.Lock()
        self.latest_diagnostics: Dict[str, Any] = {}
        
        # Inizializza stato servizi
        self._init_services()
    
    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Carica la configurazione dal file o usa i valori predefiniti."""
        config = DEFAULT_CONFIG.copy()
        
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    loaded_config = json.load(f)
                    # Aggiorna ricorsivamente la configurazione predefinita
                    self._update_dict_recursive(config, loaded_config)
                logger.info(f"Configurazione caricata da {config_path}")
            except Exception as e:
                logger.error(f"Errore nel caricamento della configurazione: {e}")
        
        return config
    
    def _update_dict_recursive(self, d: Dict, u: Dict) -> Dict:
        """Aggiorna ricorsivamente un dizionario con i valori di un altro."""
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self._update_dict_recursive(d[k], v)
            else:
                d[k] = v
        return d
    
    def _init_services(self):
        """Inizializza lo stato dei servizi."""
        for service_name, service_config in self.config['services'].items():
            self.services[service_name] = ServiceStatus(service_name, service_config)
            logger.debug(f"Servizio inizializzato: {service_name}")
    
    async def start(self):
        """Avvia il sistema di self-healing."""
        if not self.config.get('enabled', True):
            logger.info("Sistema self-healing disabilitato nella configurazione")
            return
        
        if self.running:
            logger.warning("Il sistema self-healing è già in esecuzione")
            return
        
        self.running = True
        self._check_task = asyncio.create_task(self._health_check_loop())
        logger.info("Sistema self-healing avviato")
    
    async def stop(self):
        """Arresta il sistema di self-healing."""
        if not self.running:
            return
        
        self.running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Sistema self-healing arrestato")
    
    async def _health_check_loop(self):
        """Loop principale che controlla la salute dei servizi."""
        check_interval = self.config.get('check_interval', 60)
        
        while self.running:
            try:
                # Controlla risorse di sistema
                await self._check_system_resources()
                
                # Controlla servizi
                for service_name, service in self.services.items():
                    # Salta servizi in recupero
                    if service.recovery_in_progress:
                        continue
                    
                    try:
                        is_healthy, error = await self._check_service(service_name)
                        service.update_status(is_healthy, error)
                        
                        # Valuta se è necessario intervenire
                        if (not is_healthy and 
                            service.consecutive_failures >= self.config.get('recovery_threshold', 3)):
                            
                            # Controllo se il servizio ha dipendenze non in salute
                            dependencies = self.config['services'][service_name].get('dependencies', [])
                            unhealthy_deps = [dep for dep in dependencies 
                                             if dep in self.services and not self.services[dep].is_healthy]
                            
                            if unhealthy_deps:
                                logger.warning(f"Non posso ripristinare {service_name} con dipendenze non in salute: {unhealthy_deps}")
                            else:
                                asyncio.create_task(self._recover_service(service_name))
                    except Exception as e:
                        logger.error(f"Errore nel controllo del servizio {service_name}: {e}")
                        logger.debug(traceback.format_exc())
                
                # Aggiorna diagnostica
                self._update_diagnostics()
                
                # Attendi prossimo ciclo
                await asyncio.sleep(check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Errore nel ciclo di controllo salute: {e}")
                logger.debug(traceback.format_exc())
                await asyncio.sleep(5)  # Breve pausa in caso di errore
    
    async def _check_service(self, service_name: str) -> Tuple[bool, str]:
        """Controlla lo stato di un servizio."""
        service_config = self.config['services'][service_name]
        service_type = service_config.get('type', 'systemd')
        
        if service_type == 'systemd':
            return await self._check_systemd_service(service_config)
        elif service_type == 'process':
            return await self._check_process_service(service_config)
        elif service_type == 'http':
            return await self._check_http_service(service_config)
        else:
            return False, f"Tipo di servizio sconosciuto: {service_type}"
    
    async def _check_systemd_service(self, service_config: Dict[str, Any]) -> Tuple[bool, str]:
        """Controlla lo stato di un servizio systemd."""
        unit = service_config['unit']
        
        try:
            # Controlla se il servizio è attivo
            proc = await asyncio.create_subprocess_exec(
                'systemctl', 'is-active', unit,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                return False, f"Servizio non attivo: {stderr.decode().strip() or 'stato sconosciuto'}"
            
            # Controlla URL di salute se specificato
            if 'healthcheck_url' in service_config:
                is_healthy, error = await self._check_http_endpoint(service_config['healthcheck_url'])
                if not is_healthy:
                    return False, f"Healthcheck fallito: {error}"
            
            return True, ""
        except Exception as e:
            return False, f"Errore nel controllo: {str(e)}"
    
    async def _check_process_service(self, service_config: Dict[str, Any]) -> Tuple[bool, str]:
        """Controlla lo stato di un servizio tramite ricerca processo."""
        process_name = service_config['process_name']
        
        try:
            # Cerca il processo
            proc = await asyncio.create_subprocess_exec(
                'pgrep', '-f', process_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                return False, f"Processo non trovato: {process_name}"
            
            # Controlla URL di salute se specificato
            if 'healthcheck_url' in service_config:
                is_healthy, error = await self._check_http_endpoint(service_config['healthcheck_url'])
                if not is_healthy:
                    return False, f"Healthcheck fallito: {error}"
            
            return True, ""
        except Exception as e:
            return False, f"Errore nel controllo: {str(e)}"
    
    async def _check_http_service(self, service_config: Dict[str, Any]) -> Tuple[bool, str]:
        """Controlla lo stato di un servizio HTTP."""
        healthcheck_url = service_config['healthcheck_url']
        return await self._check_http_endpoint(healthcheck_url)
    
    async def _check_http_endpoint(self, url: str) -> Tuple[bool, str]:
        """Controlla un endpoint HTTP."""
        import aiohttp
        
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return False, f"Stato HTTP non valido: {response.status}"
                    
                    # Opzionalmente valida il body
                    try:
                        data = await response.json()
                        if 'status' in data and data['status'] != 'ok':
                            return False, f"Stato servizio non ok: {data.get('status')}"
                    except:
                        # Non è JSON o non ha il formato atteso, ma lo consideriamo ok
                        # se lo stato HTTP è 200
                        pass
                    
                    return True, ""
        except aiohttp.ClientConnectorError:
            return False, "Connessione rifiutata"
        except aiohttp.ClientError as e:
            return False, f"Errore HTTP: {str(e)}"
        except Exception as e:
            return False, f"Errore generico: {str(e)}"
    
    async def _check_system_resources(self):
        """Controlla lo stato delle risorse di sistema."""
        try:
            import psutil
            
            self.system_health.last_check = time.time()
            
            # CPU
            self.system_health.cpu_usage = psutil.cpu_percent(interval=1)
            
            # Memoria
            mem = psutil.virtual_memory()
            self.system_health.memory_usage = mem.percent
            
            # Disco
            disk = psutil.disk_usage('/')
            self.system_health.disk_usage = disk.percent
            
            # Carico sistema
            self.system_health.system_load = os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
            
            # File aperti (solo Linux)
            if sys.platform.startswith('linux'):
                self.system_health.open_files = len(psutil.Process().open_files())
            
            # Controlla e gestisci problemi di risorse
            await self._handle_resource_issues()
        except Exception as e:
            logger.error(f"Errore nel controllo delle risorse di sistema: {e}")
            self.system_health.errors.append({
                'time': time.time(),
                'message': str(e),
                'type': 'system_resources'
            })
    
    async def _handle_resource_issues(self):
        """Gestisce problemi di risorse di sistema."""
        resource_config = self.config.get('resources', {})
        
        # Controlla spazio su disco
        if (resource_config.get('check_disk_space', True) and
            self.system_health.disk_usage > 100 - resource_config.get('min_free_disk_percent', 10)):
            
            logger.warning(f"Spazio su disco in esaurimento: {self.system_health.disk_usage:.1f}%")
            
            # Esegui comandi di pulizia
            if 'disk_cleanup_command' in resource_config:
                try:
                    proc = await asyncio.create_subprocess_shell(
                        resource_config['disk_cleanup_command'],
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await proc.communicate()
                    
                    if proc.returncode == 0:
                        logger.info("Pulizia disco completata con successo")
                    else:
                        logger.error(f"Errore nella pulizia disco: {stderr.decode()}")
                except Exception as e:
                    logger.error(f"Errore nell'esecuzione pulizia disco: {e}")
        
        # Controlla utilizzo memoria
        if (self.system_health.memory_usage > resource_config.get('max_memory_percent', 90)):
            logger.warning(f"Utilizzo memoria elevato: {self.system_health.memory_usage:.1f}%")
            
            # Azione in base alla configurazione
            memory_action = resource_config.get('memory_action', None)
            if memory_action == 'restart_high_consumers':
                await self._restart_high_memory_processes()
            elif memory_action == 'clear_cache':
                await self._clear_system_caches()
    
    async def _restart_high_memory_processes(self):
        """Riavvia i processi che consumano troppa memoria."""
        try:
            import psutil
            
            # Identifica processi con alto consumo di memoria relativi a M4Bot
            high_consumers = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent']):
                try:
                    if (proc.info['memory_percent'] > 5.0 and  # Sopra 5% di utilizzo memoria
                        any(s in proc.name().lower() for s in ['python', 'm4bot', 'gunicorn'])):
                        high_consumers.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Ordina per utilizzo memoria (decrescente)
            high_consumers.sort(key=lambda p: p.memory_percent(), reverse=True)
            
            # Riavvia i processi più pesanti (ma limitando a max 2 per evitare downtime eccessivo)
            for i, proc in enumerate(high_consumers[:2]):
                try:
                    proc_name = proc.name()
                    proc_pid = proc.pid
                    proc_mem = proc.memory_percent()
                    
                    logger.warning(f"Riavvio processo con alto consumo memoria: {proc_name} (PID {proc_pid}, {proc_mem:.1f}%)")
                    
                    # Trova servizio corrispondente
                    for service_name, service in self.services.items():
                        if (self.config['services'][service_name].get('type') == 'systemd' and
                            self._is_process_part_of_service(proc, self.config['services'][service_name]['unit'])):
                            
                            # Riavvia servizio invece del processo
                            logger.info(f"Riavvio servizio {service_name} per gestire alto consumo memoria")
                            await self._recover_service(service_name)
                            break
                    else:
                        # Termina processo se non è parte di un servizio noto
                        proc.terminate()
                        try:
                            await asyncio.sleep(2)
                            if proc.is_running():
                                proc.kill()
                        except psutil.NoSuchProcess:
                            pass
                        
                except Exception as e:
                    logger.error(f"Errore nel riavvio processo {proc.pid}: {e}")
        except Exception as e:
            logger.error(f"Errore nella gestione processi ad alto consumo: {e}")
    
    def _is_process_part_of_service(self, proc, service_unit):
        """Verifica se un processo fa parte di un servizio systemd."""
        try:
            # Controlla se il processo è parte del servizio
            proc_cmdline = " ".join(proc.cmdline())
            return service_unit in proc_cmdline or service_unit.split('.')[0] in proc_cmdline
        except:
            return False
    
    async def _clear_system_caches(self):
        """Svuota cache di sistema per liberare memoria."""
        if sys.platform.startswith('linux'):
            try:
                # Esegui sync per flush dei file buffer
                await asyncio.create_subprocess_exec('sync')
                
                # Drop pagecache
                proc = await asyncio.create_subprocess_exec(
                    'sudo', 'sh', '-c', 'echo 1 > /proc/sys/vm/drop_caches',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                _, stderr = await proc.communicate()
                
                if proc.returncode == 0:
                    logger.info("Cache di sistema liberate con successo")
                else:
                    logger.warning(f"Errore nel liberare cache di sistema: {stderr.decode()}")
            except Exception as e:
                logger.error(f"Errore nell'esecuzione clear cache: {e}")
    
    async def _recover_service(self, service_name: str):
        """Ripristina un servizio non in salute."""
        if not self.running:
            return
        
        if self.config.get('maintenance_mode', False):
            logger.info(f"Modalità manutenzione attiva, saltato ripristino servizio {service_name}")
            return
        
        service = self.services.get(service_name)
        if not service:
            logger.error(f"Servizio {service_name} non trovato")
            return
        
        # Previeni ripristini simultanei dello stesso servizio
        if service.recovery_in_progress:
            logger.debug(f"Ripristino già in corso per {service_name}")
            return
        
        # Controlla limite riavvii
        max_restarts = self.config.get('max_restarts_per_day', 10)
        if service.restarts_today >= max_restarts:
            logger.warning(f"Raggiunto limite di {max_restarts} riavvii giornalieri per {service_name}")
            return
        
        # Acquisizione lock per operazioni di ripristino
        async with self.recovery_lock:
            try:
                service.recovery_in_progress = True
                service.restart_attempts += 1
                service.restarts_today += 1
                service.last_restart = time.time()
                
                logger.info(f"Avvio ripristino servizio {service_name} (tentativo #{service.restart_attempts})")
                
                # Esecuzione comando di ripristino
                success = await self._execute_restore_command(service_name)
                
                if success:
                    logger.info(f"Ripristino servizio {service_name} completato")
                    
                    # Verifica se il ripristino ha funzionato
                    await asyncio.sleep(5)  # Attesa per servizio
                    is_healthy, error = await self._check_service(service_name)
                    
                    if is_healthy:
                        service.consecutive_failures = 0
                        service.is_healthy = True
                        service.last_error = ""
                    else:
                        logger.warning(f"Servizio {service_name} ancora non in salute dopo ripristino: {error}")
                        
                        # Tenta ripristino da backup se configurato e multiple failures
                        if (self.config.get('backup', {}).get('auto_restore', False) and 
                            service.restart_attempts >= 2):
                            await self._attempt_restore_from_backup(service_name)
                else:
                    logger.error(f"Fallito ripristino servizio {service_name}")
            finally:
                service.recovery_in_progress = False
    
    async def _execute_restore_command(self, service_name: str) -> bool:
        """Esegue il comando di ripristino per un servizio."""
        service_config = self.config['services'][service_name]
        restore_command = service_config.get('restore_command')
        
        if not restore_command:
            logger.warning(f"Nessun comando di ripristino specificato per {service_name}")
            return False
        
        try:
            proc = await asyncio.create_subprocess_shell(
                restore_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                logger.info(f"Eseguito comando ripristino per {service_name}: {restore_command}")
                return True
            else:
                error_msg = stderr.decode().strip() or "Errore sconosciuto"
                logger.error(f"Errore nell'esecuzione ripristino per {service_name}: {error_msg}")
                return False
        except Exception as e:
            logger.error(f"Eccezione nell'esecuzione ripristino per {service_name}: {e}")
            return False
    
    async def _attempt_restore_from_backup(self, service_name: str) -> bool:
        """Tenta di ripristinare un servizio da backup."""
        backup_config = self.config.get('backup', {})
        backup_dir = backup_config.get('backup_dir')
        
        if not backup_config.get('enabled', True) or not backup_dir:
            return False
        
        logger.info(f"Tentativo di ripristino da backup per {service_name}")
        
        # Cerca backup recente
        try:
            service_backup_dir = os.path.join(backup_dir, service_name)
            if not os.path.exists(service_backup_dir):
                logger.warning(f"Directory backup non trovata per {service_name}: {service_backup_dir}")
                return False
            
            # Trova backup più recente
            backups = []
            for item in os.listdir(service_backup_dir):
                backup_path = os.path.join(service_backup_dir, item)
                if os.path.isdir(backup_path) and item.startswith('backup_'):
                    try:
                        # Estrai timestamp dal nome
                        timestamp = float(item.split('_')[1])
                        backups.append((backup_path, timestamp))
                    except:
                        continue
            
            if not backups:
                logger.warning(f"Nessun backup trovato per {service_name}")
                return False
            
            # Ordina per più recente e filtra per età massima
            backups.sort(key=lambda x: x[1], reverse=True)
            max_age = backup_config.get('max_restore_age_hours', 24) * 3600
            valid_backups = [b for b in backups if time.time() - b[1] <= max_age]
            
            if not valid_backups:
                logger.warning(f"Nessun backup abbastanza recente per {service_name}")
                return False
            
            # Usa il backup più recente
            backup_path, backup_time = valid_backups[0]
            backup_age = time.time() - backup_time
            
            logger.info(f"Ripristino {service_name} da backup di {backup_age/3600:.1f} ore fa: {backup_path}")
            
            # Esegui script di ripristino specifico per servizio
            restore_script = os.path.join(service_backup_dir, 'restore.sh')
            if os.path.exists(restore_script):
                proc = await asyncio.create_subprocess_exec(
                    restore_script, backup_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                
                if proc.returncode == 0:
                    logger.info(f"Ripristino da backup completato per {service_name}")
                    return True
                else:
                    logger.error(f"Errore nel ripristino da backup per {service_name}: {stderr.decode()}")
            else:
                logger.warning(f"Script di ripristino non trovato per {service_name}: {restore_script}")
        except Exception as e:
            logger.error(f"Errore nel tentativo di ripristino da backup per {service_name}: {e}")
        
        return False
    
    def _update_diagnostics(self):
        """Aggiorna le informazioni diagnostiche."""
        now = time.time()
        
        # Crea un dizionario con le informazioni sul sistema e servizi
        diagnostics = {
            'timestamp': now,
            'system_health': self.system_health.to_dict(),
            'services': {name: service.to_dict() for name, service in self.services.items()},
            'config': {
                'enabled': self.config.get('enabled', True),
                'maintenance_mode': self.config.get('maintenance_mode', False),
                'recovery_threshold': self.config.get('recovery_threshold', 3),
                'check_interval': self.config.get('check_interval', 60)
            }
        }
        
        self.latest_diagnostics = diagnostics
    
    def get_diagnostics(self) -> Dict[str, Any]:
        """Restituisce le informazioni diagnostiche più recenti."""
        return self.latest_diagnostics
    
    def set_maintenance_mode(self, enabled: bool) -> None:
        """Imposta o disattiva la modalità manutenzione."""
        self.config['maintenance_mode'] = enabled
        logger.info(f"Modalità manutenzione {'attivata' if enabled else 'disattivata'}")
    
    def reset_daily_counters(self) -> None:
        """Azzera i contatori giornalieri per tutti i servizi."""
        for service in self.services.values():
            service.restarts_today = 0
        logger.info("Contatori giornalieri dei riavvii azzerati")

    async def analyze_service_trends(self) -> Dict[str, Dict[str, Any]]:
        """
        Analizza le tendenze dei servizi per identificare problemi potenziali
        prima che causino interruzioni complete.
        
        Returns:
            Dict[str, Dict[str, Any]]: Analisi delle tendenze per servizio
        """
        results = {}
        
        for service_name, service in self.services.items():
            # Salta se non c'è abbastanza storia
            if len(service.status_history) < 10:
                continue
                
            # Calcola tendenze della stabilità
            health_rate = sum(1 for status in service.status_history if status) / len(service.status_history)
            
            # Individua pattern di degradazione
            degrading = False
            
            # Verifica se ci sono serie di fallimenti intermittenti (sintomo di degradazione)
            failure_sequences = 0
            for i in range(1, len(service.status_history)):
                if service.status_history[i-1] and not service.status_history[i]:
                    failure_sequences += 1
            
            # Più di 2 sequenze di fallimento nelle ultime 100 verifiche indica instabilità
            unstable = failure_sequences > 2
            
            # Analisi tendenza: se era sano e ora fallisce sempre più spesso
            recent_slice = service.status_history[-10:]
            older_slice = service.status_history[-20:-10] if len(service.status_history) >= 20 else []
            
            if older_slice:
                recent_health_rate = sum(1 for status in recent_slice if status) / len(recent_slice)
                older_health_rate = sum(1 for status in older_slice if status) / len(older_slice)
                degrading = recent_health_rate < older_health_rate and recent_health_rate < 0.7
            
            results[service_name] = {
                'health_rate': health_rate,
                'unstable': unstable,
                'degrading': degrading,
                'critical': self.config['services'][service_name].get('critical', False),
                'needs_attention': unstable or degrading,
                'failure_sequences': failure_sequences
            }
            
            # Log di avviso per servizi in degradazione
            if degrading or unstable:
                criticality = "critico" if self.config['services'][service_name].get('critical', False) else "non critico"
                logger.warning(f"Rilevata tendenza alla degradazione nel servizio {service_name} ({criticality})")
                
        return results

    async def predictive_healing(self) -> Dict[str, Any]:
        """
        Esegue il recupero predittivo basato sull'analisi delle tendenze.
        Interviene preventivamente sui servizi che mostrano segni di degradazione
        prima che causino un'interruzione completa.
        
        Returns:
            Dict[str, Any]: Risultato degli interventi predittivi
        """
        if self.config.get('maintenance_mode', False):
            return {"status": "skipped", "reason": "maintenance_mode"}
        
        trends = await self.analyze_service_trends()
        results = {"interventions": []}
        
        for service_name, analysis in trends.items():
            if analysis.get('needs_attention'):
                service = self.services[service_name]
                
                # Intervieni solo se il servizio è attualmente sano ma mostra segni di instabilità
                if service.is_healthy and analysis.get('unstable'):
                    logger.info(f"Avvio recupero predittivo per servizio {service_name} con tendenze instabili")
                    
                    # Prima prova un'azione leggera come il riavvio soft
                    intervention = {}
                    
                    try:
                        intervention = {
                            "service": service_name,
                            "time": time.time(),
                            "reason": "unstable_pattern",
                            "action": "soft_restart"
                        }
                        
                        # Esegui riavvio soft se disponibile, altrimenti quello normale
                        soft_restart_cmd = self.config['services'][service_name].get('soft_restart_command')
                        
                        if soft_restart_cmd:
                            proc = await asyncio.create_subprocess_shell(
                                soft_restart_cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )
                            _, stderr = await proc.communicate()
                            
                            intervention["success"] = proc.returncode == 0
                            if not intervention["success"]:
                                intervention["error"] = stderr.decode().strip()
                        else:
                            # Usa il normale comando di ripristino
                            intervention["action"] = "normal_restart"
                            success = await self._execute_restore_command(service_name)
                            intervention["success"] = success
                        
                        # Aggiorna i contatori solo se il riavvio è avvenuto
                        if intervention["success"]:
                            service.restart_attempts += 1
                            service.restarts_today += 1
                            
                    except Exception as e:
                        intervention["success"] = False
                        intervention["error"] = str(e)
                    
                    results["interventions"].append(intervention)
                
                # Per i servizi critici in degradazione, attiva la modalità di recupero avanzato
                elif service.is_healthy and analysis.get('degrading') and analysis.get('critical'):
                    intervention = {
                        "service": service_name,
                        "time": time.time(),
                        "reason": "degrading_critical",
                        "action": "proactive_maintenance"
                    }
                    
                    try:
                        # Esegui azioni di manutenzione proattiva (ottimizzazione DB, puliza cache, etc.)
                        await self._perform_proactive_maintenance(service_name)
                        intervention["success"] = True
                    except Exception as e:
                        intervention["success"] = False
                        intervention["error"] = str(e)
                    
                    results["interventions"].append(intervention)
        
        results["status"] = "completed"
        results["total_interventions"] = len(results["interventions"])
        results["successful_interventions"] = sum(1 for i in results["interventions"] if i.get("success", False))
        
        return results

    async def _perform_proactive_maintenance(self, service_name: str) -> bool:
        """
        Esegue azioni di manutenzione proattiva su un servizio.
        
        Args:
            service_name: Nome del servizio
            
        Returns:
            bool: True se la manutenzione è completata con successo
        """
        service_config = self.config['services'][service_name]
        maintenance_script = service_config.get('maintenance_script')
        
        if not maintenance_script:
            logger.warning(f"Nessuno script di manutenzione configurato per {service_name}")
            return False
        
        if not os.path.exists(maintenance_script):
            logger.error(f"Script di manutenzione non trovato: {maintenance_script}")
            return False
        
        try:
            logger.info(f"Esecuzione manutenzione proattiva per {service_name}")
            
            proc = await asyncio.create_subprocess_exec(
                maintenance_script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                logger.info(f"Manutenzione proattiva completata per {service_name}")
                return True
            else:
                logger.error(f"Errore nella manutenzione proattiva per {service_name}: {stderr.decode()}")
                return False
        except Exception as e:
            logger.error(f"Eccezione nella manutenzione proattiva per {service_name}: {e}")
            return False

    async def analyze_error_patterns(self) -> Dict[str, Any]:
        """
        Analizza i pattern di errore nei servizi per identificare cause comuni.
        
        Returns:
            Dict[str, Any]: Analisi dei pattern di errore
        """
        error_patterns = {}
        
        for service_name, service in self.services.items():
            if not service.last_error:
                continue
                
            # Estrai pattern significativi dagli errori
            patterns = self._extract_error_patterns(service.last_error)
            
            if patterns:
                error_patterns[service_name] = {
                    "error": service.last_error,
                    "patterns": patterns,
                    "timestamp": service.last_check
                }
        
        # Cerca errori correlati tra servizi diversi
        correlated_errors = self._find_correlated_errors(error_patterns)
        
        return {
            "error_patterns": error_patterns,
            "correlated_errors": correlated_errors
        }

    def _extract_error_patterns(self, error_text: str) -> List[str]:
        """
        Estrae pattern significativi da un messaggio di errore.
        
        Args:
            error_text: Testo dell'errore
            
        Returns:
            List[str]: Pattern significativi estratti
        """
        patterns = []
        
        # Pattern comuni di errore
        common_patterns = [
            r"connection refused",
            r"timeout",
            r"out of memory",
            r"disk full",
            r"permission denied",
            r"configuration error",
            r"database error",
            r"not found",
            r"unavailable",
            r"failed to start"
        ]
        
        for pattern in common_patterns:
            if re.search(pattern, error_text, re.IGNORECASE):
                patterns.append(pattern)
        
        return patterns

    def _find_correlated_errors(self, error_patterns: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Trova errori correlati tra servizi diversi.
        
        Args:
            error_patterns: Pattern di errore per servizio
            
        Returns:
            List[Dict[str, Any]]: Gruppi di errori correlati
        """
        correlated_groups = []
        processed_services = set()
        
        for service_name, error_data in error_patterns.items():
            if service_name in processed_services:
                continue
                
            related_services = []
            patterns = error_data["patterns"]
            
            # Trova servizi con pattern simili
            for other_service, other_data in error_patterns.items():
                if other_service == service_name or other_service in processed_services:
                    continue
                    
                common_patterns = set(patterns) & set(other_data["patterns"])
                if common_patterns:
                    related_services.append({
                        "service": other_service,
                        "common_patterns": list(common_patterns)
                    })
            
            if related_services:
                group = {
                    "primary_service": service_name,
                    "patterns": patterns,
                    "related_services": related_services,
                    "timestamp": error_data["timestamp"]
                }
                correlated_groups.append(group)
                processed_services.add(service_name)
                processed_services.update(s["service"] for s in related_services)
        
        return correlated_groups
        
    async def handle_correlated_failures(self) -> Dict[str, Any]:
        """
        Gestisce i fallimenti correlati in modo intelligente,
        evitando cicli di riavvio inutili e identificando la causa principale.
        
        Returns:
            Dict[str, Any]: Risultato degli interventi
        """
        if self.config.get('maintenance_mode', False):
            return {"status": "skipped", "reason": "maintenance_mode"}
        
        # Analizza i pattern di errore
        error_analysis = await self.analyze_error_patterns()
        correlated_groups = error_analysis["correlated_errors"]
        
        if not correlated_groups:
            return {"status": "no_correlated_errors"}
        
        results = {"interventions": []}
        
        for group in correlated_groups:
            primary_service = group["primary_service"]
            patterns = group["patterns"]
            
            # Determina la strategia di recupero basata sui pattern
            recovery_strategy = self._determine_recovery_strategy(patterns)
            
            intervention = {
                "correlation_group": {
                    "primary_service": primary_service,
                    "related_services": [s["service"] for s in group["related_services"]]
                },
                "patterns": patterns,
                "recovery_strategy": recovery_strategy,
                "time": time.time(),
                "actions": []
            }
            
            try:
                if recovery_strategy == "fix_primary_only":
                    # Ripristina solo il servizio primario
                    action = {
                        "service": primary_service,
                        "action": "recover_primary"
                    }
                    
                    success = await self._recover_service(primary_service)
                    action["success"] = success is not None
                    intervention["actions"].append(action)
                    
                elif recovery_strategy == "restart_dependency_chain":
                    # Trova l'ordine di dipendenza e riavvia dall'inizio
                    dependency_chain = self._resolve_dependency_chain(primary_service)
                    
                    # Riavvia in ordine corretto
                    for service_name in dependency_chain:
                        action = {
                            "service": service_name,
                            "action": "restart_in_chain"
                        }
                        
                        success = await self._recover_service(service_name)
                        action["success"] = success is not None
                        intervention["actions"].append(action)
                        
                        # Aspetta che il servizio si stabilizzi
                        await asyncio.sleep(5)
                
                elif recovery_strategy == "execute_recovery_procedure":
                    # Esegui una procedura di recupero speciale
                    script_name = self._get_recovery_script_for_patterns(patterns)
                    
                    if script_name and script_name in self.config.get('recovery_scripts', {}):
                        script_path = self.config['recovery_scripts'][script_name]
                        
                        action = {
                            "action": "execute_recovery_script",
                            "script": script_name
                        }
                        
                        try:
                            proc = await asyncio.create_subprocess_exec(
                                script_path,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )
                            _, stderr = await proc.communicate()
                            
                            action["success"] = proc.returncode == 0
                            if not action["success"]:
                                action["error"] = stderr.decode().strip()
                        except Exception as e:
                            action["success"] = False
                            action["error"] = str(e)
                        
                        intervention["actions"].append(action)
            except Exception as e:
                intervention["error"] = str(e)
            
            results["interventions"].append(intervention)
        
        results["status"] = "completed"
        results["total_interventions"] = len(results["interventions"])
        
        return results

    def _determine_recovery_strategy(self, patterns: List[str]) -> str:
        """
        Determina la strategia di recupero in base ai pattern di errore.
        
        Args:
            patterns: Pattern di errore rilevati
            
        Returns:
            str: Strategia di recupero da adottare
        """
        # Pattern che indicano un problema di dipendenza
        dependency_patterns = ["connection refused", "not found", "unavailable"]
        
        # Pattern che richiedono procedure speciali
        special_procedure_patterns = ["out of memory", "disk full", "database error"]
        
        # Verifica se ci sono pattern che indicano un problema di dipendenza
        if any(p in dependency_patterns for p in patterns):
            return "restart_dependency_chain"
        
        # Verifica se ci sono pattern che richiedono procedure speciali
        if any(p in special_procedure_patterns for p in patterns):
            return "execute_recovery_procedure"
        
        # Strategia predefinita: ripristina solo il servizio primario
        return "fix_primary_only"

    def _get_recovery_script_for_patterns(self, patterns: List[str]) -> Optional[str]:
        """
        Determina lo script di recupero appropriato per i pattern di errore.
        
        Args:
            patterns: Pattern di errore rilevati
            
        Returns:
            Optional[str]: Nome dello script di recupero, o None se non trovato
        """
        pattern_to_script = {
            "out of memory": "memory_recovery",
            "disk full": "disk_cleanup",
            "database error": "db_repair",
            "connection refused": "network_repair"
        }
        
        for pattern, script in pattern_to_script.items():
            if pattern in patterns:
                return script
        
        return None

    def _resolve_dependency_chain(self, service_name: str) -> List[str]:
        """
        Risolve la catena di dipendenze per un servizio.
        
        Args:
            service_name: Nome del servizio
            
        Returns:
            List[str]: Catena di dipendenze in ordine di riavvio
        """
        # Implementazione di base: riavvia prima le dipendenze
        result = []
        visited = set()
        
        def visit(svc):
            if svc in visited:
                return
            
            visited.add(svc)
            
            # Aggiungi prima le dipendenze
            deps = self.config['services'].get(svc, {}).get('dependencies', [])
            for dep in deps:
                if dep in self.config['services']:
                    visit(dep)
            
            result.append(svc)
        
        visit(service_name)
        return result
        
# Singleton del sistema di self-healing
_self_healing_system = None

def get_self_healing_system(config_path: Optional[str] = None) -> SelfHealingSystem:
    """Restituisce l'istanza singleton del sistema di self-healing."""
    global _self_healing_system
    if _self_healing_system is None:
        _self_healing_system = SelfHealingSystem(config_path)
    return _self_healing_system

async def start_self_healing(config_path: Optional[str] = None):
    """Avvia il sistema di self-healing."""
    system = get_self_healing_system(config_path)
    await system.start()
    
    # Avvia un task periodico per il self-healing predittivo
    async def predictive_healing_task():
        while system.running:
            try:
                await system.predictive_healing()
                await system.handle_correlated_failures()
                # Esegui ogni ora
                await asyncio.sleep(3600)
            except Exception as e:
                logger.error(f"Errore nel task di healing predittivo: {e}")
                await asyncio.sleep(300)  # Pausa più breve in caso di errore
    
    # Avvia il task
    asyncio.create_task(predictive_healing_task())
    
    return system

if __name__ == "__main__":
    # Avvia il sistema di self-healing come script standalone
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        config_path = sys.argv[1] if len(sys.argv) > 1 else None
        asyncio.run(start_self_healing(config_path))
    except KeyboardInterrupt:
        print("Sistema self-healing interrotto dall'utente") 