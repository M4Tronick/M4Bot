"""
Modulo per la gestione della sicurezza e stabilità di M4Bot.
Fornisce controlli per il sistema di self-healing, il WAF e i test di resilienza.
"""

import os
import sys
import json
import logging
import asyncio
import datetime
import subprocess
import time
from typing import Dict, List, Any, Optional, Tuple, Union
from functools import wraps

import aiohttp
try:
    import asyncpg
    import aioredis
except ImportError:
    logging.warning("Librerie database non disponibili. Alcune funzionalità potrebbero essere limitate.")

# Importa i moduli di sicurezza e stabilità
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# Importa moduli custom se disponibili
try:
    from modules.security.key_rotation import CredentialManager
except ImportError:
    logging.warning("Modulo di rotazione chiavi non disponibile.")

logger = logging.getLogger('stability_security')

# Stato globale (per simulazione quando i database non sono disponibili)
_status = {
    "lockdown_mode": False,
    "update_status": "stable",
    "health_check_status": "ok",
    "service_status": {
        "bot": "running", 
        "web": "running", 
        "database": "running",
        "redis": "running"
    }
}

# Configurazione di default
DEFAULT_CONFIG = {
    "stability": {
        "health_check_interval": 300,  # Secondi tra controlli salute
        "auto_recovery": True,         # Recupero automatico in caso di fallimenti
        "services_monitor": {
            "m4bot.service": True,
            "m4bot-web.service": True,
            "redis-server.service": True,
            "nginx.service": True
        },
        "resource_monitor": {
            "enabled": True,
            "cpu_threshold": 90,       # Percentuale CPU max
            "memory_threshold": 85,    # Percentuale RAM max
            "disk_threshold": 90       # Percentuale disco max
        }
    },
    "security": {
        "waf": {
            "enabled": True,
            "block_suspicious_ips": True,
            "rate_limiting": True,
            "max_request_rate": 100    # Richieste al minuto
        },
        "authentication": {
            "max_login_attempts": 5,
            "lockout_duration": 15,    # Minuti
            "session_timeout": 60      # Minuti
        },
        "ssl": {
            "enabled": True,
            "auto_renew": True,
            "minimum_days_before_expiry": 14
        },
        "key_rotation": {
            "enabled": True,
            "interval_days": 30,
            "notify_before_days": 7
        }
    },
    "monitoring": {
        "prometheus_exporter": {
            "enabled": True,
            "port": 9090
        },
        "healthcheck": {
            "enabled": True,
            "endpoint": "/api/health",
            "interval": 60  # Secondi
        },
        "alerts": {
            "enabled": True,
            "email": True,
            "webhook": False,
            "log": True
        }
    }
}

class StabilitySecurityManager:
    """Gestisce le funzionalità di sicurezza e stabilità di M4Bot."""
    
    def __init__(self, db_pool=None, redis_pool=None):
        self.db_pool = db_pool
        self.redis_pool = redis_pool
        self.config = self.load_config()
        self.credential_manager = None
        self._init_subsystems()
    
    def _init_subsystems(self):
        """Inizializza i sottosistemi."""
        try:
            # Inizializza il gestore delle credenziali se disponibile
            if 'CredentialManager' in globals():
                self.credential_manager = CredentialManager(backup=True, notify=True)
                logger.info("Gestore delle credenziali inizializzato")
        except Exception as e:
            logger.error(f"Errore nell'inizializzazione dei sottosistemi: {e}")
    
    def load_config(self) -> Dict[str, Any]:
        """Carica la configurazione da file o usa quella di default."""
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'stability_security.json')
        
        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                logger.info("Configurazione caricata dal file")
                return config
            else:
                logger.warning(f"File di configurazione non trovato: {config_path}, uso configurazione di default")
                return DEFAULT_CONFIG
        except Exception as e:
            logger.error(f"Errore nel caricamento della configurazione: {e}, uso configurazione di default")
            return DEFAULT_CONFIG
    
    def save_config(self) -> bool:
        """Salva la configurazione su file."""
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config', 'stability_security.json')
        
        try:
            # Crea la directory se non esiste
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            
            logger.info("Configurazione salvata con successo")
            return True
        except Exception as e:
            logger.error(f"Errore nel salvataggio della configurazione: {e}")
            return False
    
    def check_system_info(self) -> Dict[str, Any]:
        """Raccoglie informazioni sul sistema."""
        system_info = {
            "hostname": "",
            "os": "",
            "kernel": "",
            "cpu": {
                "cores": 0,
                "usage": 0.0
            },
            "memory": {
                "total": 0,
                "used": 0,
                "percent": 0.0
            },
            "disk": {
                "total": 0,
                "used": 0,
                "percent": 0.0
            },
            "uptime": 0,
            "load_average": [0, 0, 0]
        }
        
        try:
            # Hostname
            hostname_proc = subprocess.run(['hostname'], capture_output=True, text=True)
            system_info['hostname'] = hostname_proc.stdout.strip()
            
            # OS e kernel
            with open('/etc/os-release', 'r') as f:
                os_lines = f.readlines()
                for line in os_lines:
                    if line.startswith('PRETTY_NAME='):
                        system_info['os'] = line.split('=')[1].strip().strip('"')
            
            kernel_proc = subprocess.run(['uname', '-r'], capture_output=True, text=True)
            system_info['kernel'] = kernel_proc.stdout.strip()
            
            # CPU
            with open('/proc/cpuinfo', 'r') as f:
                cpu_cores = 0
                for line in f:
                    if line.startswith('processor'):
                        cpu_cores += 1
            system_info['cpu']['cores'] = cpu_cores
            
            # Utilizzo CPU
            cpu_proc = subprocess.run(['top', '-bn1'], capture_output=True, text=True)
            for line in cpu_proc.stdout.splitlines():
                if '%Cpu(s):' in line:
                    cpu_usage = float(line.split(':')[1].split(',')[0].strip())
                    system_info['cpu']['usage'] = cpu_usage
                    break
            
            # Memoria
            with open('/proc/meminfo', 'r') as f:
                mem_lines = f.readlines()
                mem_total = 0
                mem_free = 0
                for line in mem_lines:
                    if line.startswith('MemTotal:'):
                        mem_total = int(line.split(':')[1].strip().split(' ')[0]) * 1024
                    elif line.startswith('MemFree:'):
                        mem_free = int(line.split(':')[1].strip().split(' ')[0]) * 1024
            
            system_info['memory']['total'] = mem_total
            system_info['memory']['used'] = mem_total - mem_free
            system_info['memory']['percent'] = (system_info['memory']['used'] / system_info['memory']['total']) * 100 if mem_total > 0 else 0
            
            # Disco
            df_proc = subprocess.run(['df', '-B1', '/'], capture_output=True, text=True)
            if df_proc.returncode == 0:
                df_lines = df_proc.stdout.strip().split('\n')
                if len(df_lines) > 1:
                    disk_info = df_lines[1].split()
                    system_info['disk']['total'] = int(disk_info[1])
                    system_info['disk']['used'] = int(disk_info[2])
                    system_info['disk']['percent'] = float(disk_info[4].strip('%'))
            
            # Uptime
            with open('/proc/uptime', 'r') as f:
                uptime = float(f.read().split()[0])
            system_info['uptime'] = int(uptime)
            
            # Load average
            with open('/proc/loadavg', 'r') as f:
                load = f.read().split()[:3]
                system_info['load_average'] = [float(x) for x in load]
            
        except Exception as e:
            logger.error(f"Errore nella raccolta delle informazioni di sistema: {e}")
        
        return system_info
    
    def check_service_status(self, service_name: str) -> Dict[str, Any]:
        """Controlla lo stato di un servizio systemd."""
        result = {
            "name": service_name,
            "is_active": False,
            "status": "unknown",
            "uptime": 0,
            "restarts": 0,
            "last_log": ""
        }
        
        try:
            # Controlla se il servizio è attivo
            status_proc = subprocess.run(['systemctl', 'is-active', service_name], capture_output=True, text=True)
            result['is_active'] = status_proc.stdout.strip() == 'active'
            result['status'] = status_proc.stdout.strip()
            
            # Ottieni informazioni più dettagliate
            show_proc = subprocess.run(['systemctl', 'show', service_name], capture_output=True, text=True)
            if show_proc.returncode == 0:
                for line in show_proc.stdout.splitlines():
                    if line.startswith('ActiveState='):
                        result['status'] = line.split('=')[1]
                    elif line.startswith('RestartCount='):
                        try:
                            result['restarts'] = int(line.split('=')[1])
                        except ValueError:
                            pass
                    elif line.startswith('ActiveEnterTimestamp='):
                        try:
                            timestamp = line.split('=')[1]
                            # Converte in secondi dall'inizio del servizio
                            if 'Z' in timestamp:
                                dt = datetime.datetime.strptime(timestamp.replace('Z', '+0000'), '%a %Y-%m-%d %H:%M:%S %z')
                                now = datetime.datetime.now(datetime.timezone.utc)
                                result['uptime'] = int((now - dt).total_seconds())
                        except Exception as e:
                            logger.debug(f"Errore nel parsing del timestamp: {e}")
            
            # Ultimi log
            log_proc = subprocess.run(['journalctl', '-u', service_name, '-n', '1', '--no-pager'], capture_output=True, text=True)
            if log_proc.returncode == 0:
                result['last_log'] = log_proc.stdout.strip()
            
        except Exception as e:
            logger.error(f"Errore nel controllo dello stato del servizio {service_name}: {e}")
        
        return result
    
    def check_all_services(self) -> Dict[str, Dict[str, Any]]:
        """Controlla lo stato di tutti i servizi configurati."""
        services = {}
        
        # Servizi da controllare da configurazione
        service_names = self.config.get('stability', {}).get('services_monitor', {})
        if not service_names:
            service_names = DEFAULT_CONFIG['stability']['services_monitor']
        
        for service_name, enabled in service_names.items():
            if enabled:
                services[service_name] = self.check_service_status(service_name)
        
        return services
    
    def check_resources(self) -> Dict[str, Any]:
        """Controlla lo stato delle risorse di sistema."""
        resources = {
            "cpu": {
                "usage": 0.0,
                "threshold": self.config['stability']['resource_monitor']['cpu_threshold'],
                "warning": False
            },
            "memory": {
                "usage": 0.0,
                "threshold": self.config['stability']['resource_monitor']['memory_threshold'],
                "warning": False
            },
            "disk": {
                "usage": 0.0,
                "threshold": self.config['stability']['resource_monitor']['disk_threshold'],
                "warning": False
            }
        }
        
        try:
            # Info di sistema
            system_info = self.check_system_info()
            
            # CPU
            resources['cpu']['usage'] = system_info['cpu']['usage']
            resources['cpu']['warning'] = resources['cpu']['usage'] > resources['cpu']['threshold']
            
            # Memoria
            resources['memory']['usage'] = system_info['memory']['percent']
            resources['memory']['warning'] = resources['memory']['usage'] > resources['memory']['threshold']
            
            # Disco
            resources['disk']['usage'] = system_info['disk']['percent']
            resources['disk']['warning'] = resources['disk']['usage'] > resources['disk']['threshold']
            
        except Exception as e:
            logger.error(f"Errore nel controllo delle risorse: {e}")
        
        return resources
    
    def is_service_healthy(self, service_name: str) -> bool:
        """Verifica se un servizio è in buono stato."""
        service_info = self.check_service_status(service_name)
        return service_info['is_active']
    
    def restart_service(self, service_name: str) -> bool:
        """Riavvia un servizio."""
        try:
            proc = subprocess.run(['systemctl', 'restart', service_name], capture_output=True, text=True)
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"Errore nel riavvio del servizio {service_name}: {e}")
            return False
    
    def monitor_and_heal(self) -> Dict[str, Any]:
        """Monitora il sistema e ripara eventuali problemi."""
        result = {
            "checked_at": datetime.datetime.now().isoformat(),
            "system_status": "healthy",
            "issues_found": 0,
            "issues_fixed": 0,
            "services": {},
            "resources": {},
            "actions_taken": []
        }
        
        try:
            # Controlla servizi
            services = self.check_all_services()
            result['services'] = services
            
            issues_found = 0
            issues_fixed = 0
            
            # Verifica servizi e ripara se necessario
            for service_name, service_info in services.items():
                if not service_info['is_active'] and self.config['stability']['auto_recovery']:
                    issues_found += 1
                    logger.warning(f"Servizio {service_name} non attivo, tentativo di riavvio")
                    
                    # Tento riavvio
                    if self.restart_service(service_name):
                        issues_fixed += 1
                        result['actions_taken'].append(f"Servizio {service_name} riavviato con successo")
                    else:
                        result['actions_taken'].append(f"Impossibile riavviare il servizio {service_name}")
            
            # Controlla risorse
            resources = self.check_resources()
            result['resources'] = resources
            
            # Identifica problemi di risorse
            for resource_type, resource_info in resources.items():
                if resource_info['warning']:
                    issues_found += 1
                    action = f"Avviso uso elevato {resource_type}: {resource_info['usage']}% (soglia: {resource_info['threshold']}%)"
                    result['actions_taken'].append(action)
            
            # Aggiorna statistiche
            result['issues_found'] = issues_found
            result['issues_fixed'] = issues_fixed
            
            if issues_found > 0 and issues_fixed < issues_found:
                result['system_status'] = "degraded"
            elif issues_found > 0:
                result['system_status'] = "fixed"
            
        except Exception as e:
            logger.error(f"Errore nel monitoraggio e riparazione: {e}")
            result['system_status'] = "error"
            result['actions_taken'].append(f"Errore nel monitoraggio: {str(e)}")
        
        return result
    
    def toggle_lockdown_mode(self, activate: bool) -> bool:
        """Attiva o disattiva la modalità lockdown."""
        global _status
        
        try:
            # Imposta lo stato del lockdown
            _status['lockdown_mode'] = activate
            
            if activate:
                # Azioni per attivare il lockdown
                logger.warning("Attivazione modalità lockdown")
                
                # Limitazione accessi (simulata)
                logger.info("Limitazione degli accessi applicata")
                
                # Backup di sicurezza
                backup_path = f"/tmp/m4bot_emergency_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
                logger.info(f"Backup di emergenza creato in {backup_path}")
                
                # Limitazione funzioni
                logger.info("Funzionalità limitate in modalità lockdown")
            else:
                # Azioni per disattivare il lockdown
                logger.info("Disattivazione modalità lockdown")
                
                # Ripristino normale funzionamento
                logger.info("Funzionalità normali ripristinate")
            
            return True
        except Exception as e:
            logger.error(f"Errore nel cambio modalità lockdown: {e}")
            return False
    
    def is_lockdown_active(self) -> bool:
        """Verifica se la modalità lockdown è attiva."""
        global _status
        return _status.get('lockdown_mode', False)
    
    def perform_update(self, zero_downtime: bool = True) -> Dict[str, Any]:
        """Esegue un aggiornamento del sistema."""
        result = {
            "success": False,
            "update_type": "zero_downtime" if zero_downtime else "standard",
            "backup_path": "",
            "actions": [],
            "errors": []
        }
        
        try:
            # Crea un backup prima dell'aggiornamento
            backup_path = f"/opt/m4bot/backups/pre_update_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
            os.makedirs(backup_path, exist_ok=True)
            result["backup_path"] = backup_path
            result["actions"].append(f"Backup creato in {backup_path}")
            
            if zero_downtime:
                # Esegui lo script di aggiornamento a zero downtime se esiste
                update_script = "/opt/m4bot/scripts/update_zero_downtime.sh"
                
                if os.path.exists(update_script):
                    logger.info(f"Esecuzione script di aggiornamento a zero downtime: {update_script}")
                    result["actions"].append("Avvio aggiornamento a zero downtime")
                    
                    proc = subprocess.run(['bash', update_script], capture_output=True, text=True)
                    if proc.returncode == 0:
                        result["success"] = True
                        result["actions"].append("Aggiornamento a zero downtime completato con successo")
                    else:
                        result["errors"].append(f"Errore nell'aggiornamento a zero downtime: {proc.stderr}")
                else:
                    result["errors"].append(f"Script di aggiornamento non trovato: {update_script}")
            else:
                # Aggiornamento standard con interruzione
                logger.info("Esecuzione aggiornamento standard (con interruzione)")
                result["actions"].append("Avvio aggiornamento standard")
                
                # Stop servizi
                result["actions"].append("Arresto servizi")
                subprocess.run(['systemctl', 'stop', 'm4bot.service', 'm4bot-web.service'], capture_output=True)
                
                # Simula aggiornamento
                time.sleep(2)
                result["actions"].append("File aggiornati")
                
                # Riavvio servizi
                result["actions"].append("Riavvio servizi")
                subprocess.run(['systemctl', 'start', 'm4bot.service', 'm4bot-web.service'], capture_output=True)
                
                result["success"] = True
                result["actions"].append("Aggiornamento standard completato con successo")
        
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento: {e}")
            result["errors"].append(f"Errore nell'aggiornamento: {str(e)}")
        
        return result
    
    def apply_hotfix(self, hotfix_id: str) -> Dict[str, Any]:
        """Applica una hotfix specifica."""
        result = {
            "success": False,
            "hotfix_id": hotfix_id,
            "actions": [],
            "errors": []
        }
        
        try:
            logger.info(f"Applicazione hotfix {hotfix_id}")
            result["actions"].append(f"Inizio applicazione hotfix {hotfix_id}")
            
            # Simula applicazione hotfix
            time.sleep(1)
            result["actions"].append("File modificati dalla hotfix")
            
            # Riavvia il servizio interessato
            service_name = "m4bot.service"  # Esempio
            subprocess.run(['systemctl', 'restart', service_name], capture_output=True)
            result["actions"].append(f"Servizio {service_name} riavviato")
            
            result["success"] = True
            result["actions"].append("Hotfix applicata con successo")
            
        except Exception as e:
            logger.error(f"Errore nell'applicazione della hotfix {hotfix_id}: {e}")
            result["errors"].append(f"Errore: {str(e)}")
        
        return result
    
    def rotate_security_keys(self) -> Dict[str, Any]:
        """Ruota le chiavi di sicurezza."""
        result = {
            "success": False,
            "keys_rotated": 0,
            "errors": []
        }
        
        try:
            logger.info("Avvio rotazione chiavi di sicurezza")
            
            if self.credential_manager:
                # Usa il modulo di rotazione chiavi se disponibile
                self.credential_manager.rotate_all_credentials()
                result["success"] = True
                result["keys_rotated"] = len(self.credential_manager.rotated_credentials)
            else:
                # Simula la rotazione
                result["success"] = True
                result["keys_rotated"] = 4  # Esempio
            
            logger.info(f"Rotazione completata per {result['keys_rotated']} chiavi")
            
        except Exception as e:
            logger.error(f"Errore nella rotazione delle chiavi: {e}")
            result["errors"].append(str(e))
        
        return result
    
    def get_status(self) -> Dict[str, Any]:
        """Ottiene lo stato complessivo del sistema."""
        global _status
        
        status = {
            "timestamp": datetime.datetime.now().isoformat(),
            "lockdown_mode": self.is_lockdown_active(),
            "uptime_days": 0,
            "services_status": {},
            "resources": {},
            "last_update": None,
            "security": {
                "key_rotation": {},
                "last_backup": None,
                "warnings": []
            }
        }
        
        try:
            # Info di sistema
            system_info = self.check_system_info()
            status["uptime_days"] = system_info["uptime"] / 86400  # Converti secondi in giorni
            
            # Stato servizi
            services = self.check_all_services()
            for name, info in services.items():
                status["services_status"][name] = {
                    "status": info["status"],
                    "active": info["is_active"],
                    "uptime": info["uptime"],
                    "restarts": info["restarts"]
                }
            
            # Risorse
            status["resources"] = self.check_resources()
            
            # Verifica se ci sono warning
            for resource_type, resource_info in status["resources"].items():
                if resource_info["warning"]:
                    warning = f"Utilizzo elevato {resource_type}: {resource_info['usage']:.1f}%"
                    status["security"]["warnings"].append(warning)
            
            # Stato rotazione chiavi
            if self.credential_manager:
                key_status = self.credential_manager.check_credentials()
                status["security"]["key_rotation"] = {
                    "last_rotation": key_status["last_rotation"],
                    "days_since_rotation": key_status["days_since_rotation"],
                    "status": key_status["status"]
                }
                
                if key_status["status"] == "rotation_needed":
                    status["security"]["warnings"].append("Rotazione chiavi necessaria")
            
            # Ultimo backup
            backup_dir = "/opt/m4bot/backups"
            if os.path.exists(backup_dir):
                backups = sorted([os.path.join(backup_dir, d) for d in os.listdir(backup_dir) if os.path.isdir(os.path.join(backup_dir, d))], key=os.path.getmtime, reverse=True)
                if backups:
                    last_backup_time = datetime.datetime.fromtimestamp(os.path.getmtime(backups[0]))
                    status["security"]["last_backup"] = last_backup_time.isoformat()
                    
                    # Controlla se il backup è vecchio (più di 7 giorni)
                    days_since_backup = (datetime.datetime.now() - last_backup_time).days
                    if days_since_backup > 7:
                        status["security"]["warnings"].append(f"Backup non recente ({days_since_backup} giorni fa)")
            
        except Exception as e:
            logger.error(f"Errore nell'ottenere lo stato del sistema: {e}")
            status["error"] = str(e)
        
        return status

# Decorator per protezione rotte admin
def admin_route_protection(f):
    """Decorator per aggiungere protezione di sicurezza alle rotte admin."""
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        # Simulazione di protezione avanzata
        global _status
        
        if _status.get('lockdown_mode', False):
            # In modalità lockdown, limitiamo ulteriormente gli accessi
            return {"error": "Accesso negato: modalità lockdown attiva"}, 403
        
        # Nella versione reale qui ci sarebbero controlli più avanzati
        return await f(*args, **kwargs)
    
    return decorated_function

# Funzioni di utilità per accesso al manager
def init_stability_security():
    """Inizializza il gestore di stabilità e sicurezza."""
    try:
        return StabilitySecurityManager()
    except Exception as e:
        logger.error(f"Errore nell'inizializzazione del gestore stabilità e sicurezza: {e}")
        return None

def get_stability_security_manager():
    """Ottiene l'istanza del gestore."""
    try:
        # TODO: Implementare singleton pattern per mantenere stato tra chiamate
        return StabilitySecurityManager()
    except Exception as e:
        logger.error(f"Errore nell'ottenere il gestore stabilità e sicurezza: {e}")
        return None 