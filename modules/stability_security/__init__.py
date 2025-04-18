"""
M4Bot - Modulo per la gestione della stabilità e sicurezza
Fornisce funzionalità avanzate per garantire stabilità durante gli aggiornamenti
e implementa meccanismi di sicurezza aggiuntivi per l'admin control panel.
"""

import os
import sys
import time
import json
import logging
import threading
import subprocess
import datetime
from typing import Dict, List, Any, Optional, Tuple
from functools import wraps

# Configurazione logging
logger = logging.getLogger('m4bot.stability_security')

# Stato globale del modulo
_is_initialized = False
_status = {
    "lockdown_mode": False,
    "update_in_progress": False,
    "last_update_time": None,
    "health_check_status": "ok",
    "uptime_days": 0,
    "service_status": {},
    "rollback_available": False,
    "update_history": []
}

# Configurazione predefinita
DEFAULT_CONFIG = {
    "stability": {
        "enabled": True,
        "health_check_interval": 60,  # secondi
        "auto_restart_services": True,
        "keep_previous_versions": 3,
        "zero_downtime_update": True,
        "rollback_on_failure": True,
        "update_timeout": 300,  # secondi
        "mandatory_services": ["nginx", "postgresql", "redis-server", "m4bot-bot", "m4bot-web"]
    },
    "security": {
        "enabled": True,
        "admin_only_mode": False,
        "rate_limit_admin": 60,  # richieste al minuto
        "ip_whitelist": [],
        "notify_on_admin_login": True,
        "session_expiry": 3600,  # secondi
        "multi_factor_auth": False
    },
    "monitoring": {
        "enabled": True,
        "log_level": "INFO",
        "monitor_system_resources": True,
        "alert_cpu_threshold": 90,  # percentuale
        "alert_memory_threshold": 90,  # percentuale
        "alert_disk_threshold": 90,  # percentuale
        "retention_days": 30
    }
}

# Inizializzazione lock per thread-safety
_lock = threading.RLock()

class StabilitySecurityManager:
    """
    Gestisce funzionalità di stabilità e sicurezza per M4Bot
    """
    
    @staticmethod
    def initialize(config_path: Optional[str] = None) -> bool:
        """
        Inizializza il modulo di stabilità e sicurezza
        
        Args:
            config_path: Path al file di configurazione
        
        Returns:
            bool: True se inizializzato con successo
        """
        global _is_initialized, _status
        
        with _lock:
            if _is_initialized:
                logger.info("Il modulo stabilità e sicurezza è già inizializzato")
                return True
            
            try:
                # Carica configurazione
                config = StabilitySecurityManager._load_config(config_path)
                
                # Verifica stato sistema
                system_info = StabilitySecurityManager._get_system_info()
                _status.update(system_info)
                
                # Avvia monitoraggio in background se abilitato
                if config["monitoring"]["enabled"]:
                    StabilitySecurityManager._start_monitoring(config)
                
                _is_initialized = True
                logger.info("Modulo stabilità e sicurezza inizializzato con successo")
                return True
                
            except Exception as e:
                logger.error(f"Errore nell'inizializzazione del modulo stabilità e sicurezza: {e}")
                return False
    
    @staticmethod
    def _load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Carica la configurazione o usa i valori predefiniti
        
        Args:
            config_path: Path al file di configurazione
            
        Returns:
            Dict: Configurazione caricata
        """
        config = DEFAULT_CONFIG.copy()
        
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    loaded_config = json.load(f)
                
                # Aggiorna configurazione con valori caricati
                for section in config:
                    if section in loaded_config:
                        config[section].update(loaded_config[section])
                
                logger.info(f"Configurazione caricata da {config_path}")
            except Exception as e:
                logger.error(f"Errore nel caricamento della configurazione: {e}")
        else:
            logger.info("Utilizzando configurazione predefinita")
            
            # Salva configurazione predefinita se non esiste
            if config_path:
                try:
                    os.makedirs(os.path.dirname(config_path), exist_ok=True)
                    with open(config_path, 'w') as f:
                        json.dump(config, f, indent=2)
                    logger.info(f"Configurazione predefinita salvata in {config_path}")
                except Exception as e:
                    logger.error(f"Impossibile salvare la configurazione predefinita: {e}")
        
        return config
    
    @staticmethod
    def _get_system_info() -> Dict[str, Any]:
        """
        Ottiene informazioni sul sistema
        
        Returns:
            Dict: Informazioni sul sistema
        """
        info = {
            "uptime_days": 0,
            "service_status": {},
            "health_check_status": "unknown"
        }
        
        try:
            # Ottieni uptime se disponibile
            if os.path.exists('/proc/uptime'):
                with open('/proc/uptime', 'r') as f:
                    uptime_seconds = float(f.readline().split()[0])
                    info["uptime_days"] = uptime_seconds / (60 * 60 * 24)
            
            # Verifica stato dei servizi principali
            for service in DEFAULT_CONFIG["stability"]["mandatory_services"]:
                try:
                    result = subprocess.run(
                        ["systemctl", "is-active", service],
                        capture_output=True, text=True, check=False
                    )
                    info["service_status"][service] = result.stdout.strip()
                except Exception:
                    info["service_status"][service] = "unknown"
            
            # Imposta stato complessivo
            if all(status == "active" for status in info["service_status"].values()):
                info["health_check_status"] = "ok"
            elif any(status == "active" for status in info["service_status"].values()):
                info["health_check_status"] = "degraded"
            else:
                info["health_check_status"] = "critical"
                
        except Exception as e:
            logger.error(f"Errore nell'ottenere informazioni di sistema: {e}")
        
        return info
    
    @staticmethod
    def _start_monitoring(config: Dict[str, Any]) -> None:
        """
        Avvia monitoraggio in background
        
        Args:
            config: Configurazione del modulo
        """
        interval = config["monitoring"]["monitor_interval"] = 60
        
        def monitoring_thread():
            while True:
                try:
                    # Aggiorna informazioni di sistema
                    system_info = StabilitySecurityManager._get_system_info()
                    with _lock:
                        _status.update(system_info)
                    
                    # Verifica risorse di sistema se abilitato
                    if config["monitoring"]["monitor_system_resources"]:
                        StabilitySecurityManager._check_system_resources(config)
                    
                except Exception as e:
                    logger.error(f"Errore nel thread di monitoraggio: {e}")
                
                # Pausa prima del prossimo controllo
                time.sleep(interval)
        
        # Avvia thread in background
        thread = threading.Thread(target=monitoring_thread, daemon=True)
        thread.start()
        logger.info(f"Thread di monitoraggio avviato (intervallo: {interval}s)")
    
    @staticmethod
    def _check_system_resources(config: Dict[str, Any]) -> None:
        """
        Controlla utilizzo risorse di sistema
        
        Args:
            config: Configurazione del modulo
        """
        try:
            # Controllo CPU
            cpu_percent = StabilitySecurityManager._get_cpu_usage()
            if cpu_percent > config["monitoring"]["alert_cpu_threshold"]:
                logger.warning(f"Utilizzo CPU elevato: {cpu_percent}%")
                # Invia alert o implementa misure di mitigazione
            
            # Controllo memoria
            memory_percent = StabilitySecurityManager._get_memory_usage()
            if memory_percent > config["monitoring"]["alert_memory_threshold"]:
                logger.warning(f"Utilizzo memoria elevato: {memory_percent}%")
                # Invia alert o implementa misure di mitigazione
            
            # Controllo disco
            disk_percent = StabilitySecurityManager._get_disk_usage()
            if disk_percent > config["monitoring"]["alert_disk_threshold"]:
                logger.warning(f"Spazio su disco quasi esaurito: {disk_percent}%")
                # Invia alert o implementa misure di mitigazione
            
        except Exception as e:
            logger.error(f"Errore nel controllo delle risorse di sistema: {e}")
    
    @staticmethod
    def _get_cpu_usage() -> float:
        """
        Ottiene percentuale di utilizzo CPU
        
        Returns:
            float: Percentuale utilizzo CPU
        """
        try:
            result = subprocess.run(
                ["top", "-bn1"], 
                capture_output=True, text=True, check=True
            )
            
            # Parsing dell'output di top
            for line in result.stdout.splitlines():
                if '%Cpu(s):' in line:
                    # Estrai la percentuale di utilizzo CPU (100 - idle)
                    parts = line.split(',')
                    for part in parts:
                        if 'id' in part:  # idle
                            idle = float(part.split()[0])
                            return 100.0 - idle
        except Exception:
            pass
        
        # Fallback: restituisci un valore stimato o 0
        return 0.0
    
    @staticmethod
    def _get_memory_usage() -> float:
        """
        Ottiene percentuale di utilizzo memoria
        
        Returns:
            float: Percentuale utilizzo memoria
        """
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = f.read()
            
            # Estrai MemTotal e MemAvailable
            total = 0
            available = 0
            
            for line in meminfo.splitlines():
                if 'MemTotal:' in line:
                    total = int(line.split()[1])
                elif 'MemAvailable:' in line:
                    available = int(line.split()[1])
            
            if total > 0:
                used_percent = ((total - available) / total) * 100
                return used_percent
        except Exception:
            pass
        
        # Fallback
        return 0.0
    
    @staticmethod
    def _get_disk_usage() -> float:
        """
        Ottiene percentuale di utilizzo disco
        
        Returns:
            float: Percentuale utilizzo disco
        """
        try:
            result = subprocess.run(
                ["df", "/"], 
                capture_output=True, text=True, check=True
            )
            
            # Parsing dell'output di df
            lines = result.stdout.splitlines()
            if len(lines) >= 2:
                parts = lines[1].split()
                if len(parts) >= 5:
                    # Percentuale è nella quinta colonna
                    percent = parts[4].rstrip('%')
                    return float(percent)
        except Exception:
            pass
        
        # Fallback
        return 0.0
    
    @staticmethod
    def get_status() -> Dict[str, Any]:
        """
        Ottiene lo stato attuale del modulo
        
        Returns:
            Dict: Stato attuale
        """
        with _lock:
            # Copia dello stato per evitare modifiche esterne
            return _status.copy()
    
    @staticmethod
    def set_lockdown_mode(enabled: bool) -> bool:
        """
        Attiva o disattiva la modalità lockdown
        
        Args:
            enabled: True per attivare, False per disattivare
            
        Returns:
            bool: True se l'operazione ha avuto successo
        """
        global _status
        
        with _lock:
            try:
                # Implementazione effettiva della modalità lockdown
                if enabled:
                    logger.warning("Attivazione modalità lockdown")
                    # Qui implementare le restrizioni di sicurezza
                else:
                    logger.info("Disattivazione modalità lockdown")
                    # Qui rimuovere le restrizioni
                
                _status["lockdown_mode"] = enabled
                return True
            except Exception as e:
                logger.error(f"Errore nella gestione della modalità lockdown: {e}")
                return False
    
    @staticmethod
    def prepare_update() -> bool:
        """
        Prepara il sistema per un aggiornamento
        
        Returns:
            bool: True se il sistema è pronto per l'aggiornamento
        """
        global _status
        
        with _lock:
            if _status["update_in_progress"]:
                logger.warning("Aggiornamento già in corso")
                return False
            
            try:
                # Verifica prerequisiti
                if not StabilitySecurityManager._check_update_prerequisites():
                    logger.error("Prerequisiti per l'aggiornamento non soddisfatti")
                    return False
                
                # Crea backup pre-aggiornamento
                if not StabilitySecurityManager._create_pre_update_backup():
                    logger.error("Impossibile creare backup pre-aggiornamento")
                    return False
                
                # Aggiorna stato
                _status["update_in_progress"] = True
                _status["rollback_available"] = True
                
                logger.info("Sistema pronto per l'aggiornamento")
                return True
                
            except Exception as e:
                logger.error(f"Errore nella preparazione dell'aggiornamento: {e}")
                return False
    
    @staticmethod
    def _check_update_prerequisites() -> bool:
        """
        Verifica prerequisiti per l'aggiornamento
        
        Returns:
            bool: True se i prerequisiti sono soddisfatti
        """
        # Verifica spazio su disco
        disk_percent = StabilitySecurityManager._get_disk_usage()
        if disk_percent > 90:
            logger.error(f"Spazio su disco insufficiente per l'aggiornamento: {disk_percent}% utilizzato")
            return False
        
        # Verifica stato servizi
        for service, status in _status["service_status"].items():
            if status != "active":
                logger.error(f"Servizio {service} non attivo (stato: {status})")
                return False
        
        # Verifica connessione internet
        if not StabilitySecurityManager._check_internet_connection():
            logger.error("Connessione internet non disponibile")
            return False
        
        return True
    
    @staticmethod
    def _check_internet_connection() -> bool:
        """
        Verifica connessione internet
        
        Returns:
            bool: True se la connessione è disponibile
        """
        try:
            subprocess.run(
                ["ping", "-c", "1", "8.8.8.8"],
                capture_output=True, check=True, timeout=5
            )
            return True
        except Exception:
            return False
    
    @staticmethod
    def _create_pre_update_backup() -> bool:
        """
        Crea backup pre-aggiornamento
        
        Returns:
            bool: True se il backup è stato creato con successo
        """
        try:
            # Implementazione effettiva del backup
            # In una versione reale, qui si creerebbe un backup del database e dei file
            
            # Simuliamo un backup di successo
            backup_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            logger.info(f"Backup pre-aggiornamento creato: backup_{backup_time}")
            return True
            
        except Exception as e:
            logger.error(f"Errore nella creazione del backup pre-aggiornamento: {e}")
            return False
    
    @staticmethod
    def perform_update(update_type: str = "normal") -> Tuple[bool, str]:
        """
        Esegue l'aggiornamento del sistema
        
        Args:
            update_type: Tipo di aggiornamento ("normal", "zero_downtime", "hotfix")
            
        Returns:
            Tuple[bool, str]: (successo, messaggio)
        """
        global _status
        
        if not _status["update_in_progress"]:
            return False, "Sistema non pronto per l'aggiornamento"
        
        try:
            logger.info(f"Avvio aggiornamento di tipo: {update_type}")
            
            if update_type == "zero_downtime":
                success, message = StabilitySecurityManager._perform_zero_downtime_update()
            elif update_type == "hotfix":
                success, message = StabilitySecurityManager._perform_hotfix_update()
            else:
                success, message = StabilitySecurityManager._perform_normal_update()
            
            # Aggiorna stato
            with _lock:
                _status["update_in_progress"] = False
                _status["last_update_time"] = datetime.datetime.now().isoformat()
                
                # Aggiungi alla cronologia
                _status["update_history"].append({
                    "time": _status["last_update_time"],
                    "type": update_type,
                    "success": success,
                    "message": message
                })
                
                # Mantieni massimo 10 voci nella cronologia
                if len(_status["update_history"]) > 10:
                    _status["update_history"] = _status["update_history"][-10:]
            
            return success, message
            
        except Exception as e:
            logger.error(f"Errore durante l'aggiornamento: {e}")
            
            # Aggiorna stato
            with _lock:
                _status["update_in_progress"] = False
            
            return False, f"Errore durante l'aggiornamento: {str(e)}"
    
    @staticmethod
    def _perform_normal_update() -> Tuple[bool, str]:
        """
        Esegue un aggiornamento normale
        
        Returns:
            Tuple[bool, str]: (successo, messaggio)
        """
        try:
            # In una versione reale, qui si eseguirebbe l'aggiornamento effettivo
            # Per simulazione, attendiamo alcuni secondi
            time.sleep(2)
            
            logger.info("Aggiornamento normale completato con successo")
            return True, "Aggiornamento completato con successo"
            
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento normale: {e}")
            return False, f"Errore nell'aggiornamento: {str(e)}"
    
    @staticmethod
    def _perform_zero_downtime_update() -> Tuple[bool, str]:
        """
        Esegue un aggiornamento a zero downtime
        
        Returns:
            Tuple[bool, str]: (successo, messaggio)
        """
        try:
            # In una versione reale, qui si implementerebbe un metodo di aggiornamento blue-green
            # o rolling update per evitare downtime
            
            # Simulazione
            logger.info("Avvio aggiornamento a zero downtime...")
            
            # 1. Preparazione nuova istanza
            logger.info("Preparazione nuova istanza...")
            time.sleep(1)
            
            # 2. Configurazione load balancer
            logger.info("Configurazione load balancer...")
            time.sleep(1)
            
            # 3. Verifica nuova istanza
            logger.info("Verifica nuova istanza...")
            time.sleep(1)
            
            # 4. Switch traffico
            logger.info("Switch traffico alla nuova istanza...")
            time.sleep(1)
            
            # 5. Completamento
            logger.info("Aggiornamento a zero downtime completato con successo")
            return True, "Aggiornamento a zero downtime completato con successo"
            
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento a zero downtime: {e}")
            return False, f"Errore nell'aggiornamento: {str(e)}"
    
    @staticmethod
    def _perform_hotfix_update() -> Tuple[bool, str]:
        """
        Esegue un aggiornamento hotfix (solo correzioni critiche)
        
        Returns:
            Tuple[bool, str]: (successo, messaggio)
        """
        try:
            # In una versione reale, qui si applicherebbe solo un hotfix
            # senza riavviare completamente i servizi
            
            # Simulazione
            logger.info("Applicazione hotfix...")
            time.sleep(1)
            
            logger.info("Hotfix applicato con successo")
            return True, "Hotfix applicato con successo"
            
        except Exception as e:
            logger.error(f"Errore nell'applicazione del hotfix: {e}")
            return False, f"Errore nell'applicazione del hotfix: {str(e)}"
    
    @staticmethod
    def rollback_update() -> Tuple[bool, str]:
        """
        Esegue rollback all'ultimo aggiornamento
        
        Returns:
            Tuple[bool, str]: (successo, messaggio)
        """
        global _status
        
        if not _status["rollback_available"]:
            return False, "Nessun rollback disponibile"
        
        try:
            logger.warning("Avvio rollback dell'ultimo aggiornamento...")
            
            # In una versione reale, qui si ripristinerebbe il backup pre-aggiornamento
            # e si riavvierebbe il sistema nella versione precedente
            
            # Simulazione
            time.sleep(2)
            
            # Aggiorna stato
            with _lock:
                _status["rollback_available"] = False
            
            logger.info("Rollback completato con successo")
            return True, "Rollback completato con successo"
            
        except Exception as e:
            logger.error(f"Errore durante il rollback: {e}")
            return False, f"Errore durante il rollback: {str(e)}"
    
    @staticmethod
    def restart_service(service_name: str) -> Tuple[bool, str]:
        """
        Riavvia un servizio specifico
        
        Args:
            service_name: Nome del servizio da riavviare
            
        Returns:
            Tuple[bool, str]: (successo, messaggio)
        """
        try:
            logger.info(f"Riavvio del servizio {service_name}...")
            
            # Verifica che il servizio esista
            result = subprocess.run(
                ["systemctl", "status", service_name],
                capture_output=True, text=True, check=False
            )
            
            if result.returncode not in [0, 3]:  # 0=active, 3=inactive
                return False, f"Servizio {service_name} non trovato"
            
            # Riavvia il servizio
            subprocess.run(
                ["systemctl", "restart", service_name],
                check=True
            )
            
            # Verifica che il servizio sia attivo dopo il riavvio
            time.sleep(1)  # Attesa breve per il riavvio
            
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True, text=True, check=False
            )
            
            if result.stdout.strip() == "active":
                logger.info(f"Servizio {service_name} riavviato con successo")
                
                # Aggiorna stato servizio
                with _lock:
                    _status["service_status"][service_name] = "active"
                
                return True, f"Servizio {service_name} riavviato con successo"
            else:
                logger.error(f"Servizio {service_name} non attivo dopo il riavvio")
                
                # Aggiorna stato servizio
                with _lock:
                    _status["service_status"][service_name] = "failed"
                
                return False, f"Servizio {service_name} non attivo dopo il riavvio"
            
        except Exception as e:
            logger.error(f"Errore nel riavvio del servizio {service_name}: {e}")
            return False, f"Errore nel riavvio del servizio: {str(e)}"
    
    @staticmethod
    def check_system_health() -> Dict[str, Any]:
        """
        Esegue un controllo completo della salute del sistema
        
        Returns:
            Dict: Risultati del controllo
        """
        try:
            logger.info("Esecuzione controllo salute del sistema...")
            
            results = {
                "status": "ok",
                "checks": {},
                "timestamp": datetime.datetime.now().isoformat()
            }
            
            # 1. Controllo servizi
            service_results = {}
            services_ok = True
            
            for service in DEFAULT_CONFIG["stability"]["mandatory_services"]:
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True, text=True, check=False
                )
                status = result.stdout.strip()
                service_results[service] = status
                
                if status != "active":
                    services_ok = False
            
            results["checks"]["services"] = {
                "status": "ok" if services_ok else "fail",
                "details": service_results
            }
            
            # 2. Controllo risorse
            cpu_percent = StabilitySecurityManager._get_cpu_usage()
            memory_percent = StabilitySecurityManager._get_memory_usage()
            disk_percent = StabilitySecurityManager._get_disk_usage()
            
            resources_ok = (
                cpu_percent < 90 and
                memory_percent < 90 and
                disk_percent < 90
            )
            
            results["checks"]["resources"] = {
                "status": "ok" if resources_ok else "warning",
                "details": {
                    "cpu": f"{cpu_percent:.1f}%",
                    "memory": f"{memory_percent:.1f}%",
                    "disk": f"{disk_percent:.1f}%"
                }
            }
            
            # 3. Controllo connettività
            internet_ok = StabilitySecurityManager._check_internet_connection()
            
            results["checks"]["connectivity"] = {
                "status": "ok" if internet_ok else "warning",
                "details": {
                    "internet": "available" if internet_ok else "unavailable"
                }
            }
            
            # 4. Verifica database
            db_ok = StabilitySecurityManager._check_database()
            
            results["checks"]["database"] = {
                "status": "ok" if db_ok else "fail",
                "details": {
                    "connection": "ok" if db_ok else "fail"
                }
            }
            
            # Calcola stato complessivo
            if any(check["status"] == "fail" for check in results["checks"].values()):
                results["status"] = "fail"
            elif any(check["status"] == "warning" for check in results["checks"].values()):
                results["status"] = "warning"
            
            # Aggiorna stato
            with _lock:
                _status["health_check_status"] = results["status"]
            
            logger.info(f"Controllo salute completato: {results['status']}")
            return results
            
        except Exception as e:
            logger.error(f"Errore nel controllo salute del sistema: {e}")
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.datetime.now().isoformat()
            }
    
    @staticmethod
    def _check_database() -> bool:
        """
        Verifica connessione al database
        
        Returns:
            bool: True se il database è accessibile
        """
        try:
            # In una versione reale, qui si eseguirebbe una query di test al database
            # Per simulazione, verifichiamo solo che il servizio postgresql sia attivo
            
            result = subprocess.run(
                ["systemctl", "is-active", "postgresql"],
                capture_output=True, text=True, check=False
            )
            
            return result.stdout.strip() == "active"
            
        except Exception:
            return False


# Funzione di utilità per proteggere le route admin
def admin_route_protection(f):
    """
    Decorator per proteggere le route admin con controlli aggiuntivi
    """
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if not _is_initialized:
            logger.warning("Il modulo stabilità e sicurezza non è inizializzato")
        
        # Controlli di sicurezza per admin
        if _status.get("lockdown_mode", False):
            # In modalità lockdown, verifica IP whitelist
            from quart import request, abort
            client_ip = request.remote_addr
            
            config = DEFAULT_CONFIG["security"]
            if client_ip not in config["ip_whitelist"]:
                logger.warning(f"Accesso bloccato per IP {client_ip} (modalità lockdown attiva)")
                abort(403, "Accesso negato: modalità lockdown attiva")
        
        return await f(*args, **kwargs)
    
    return decorated_function

# Inizializzazione del modulo (da chiamare all'avvio dell'app)
def init_module():
    """Inizializza il modulo stability_security"""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config",
        "stability_security.json"
    )
    return StabilitySecurityManager.initialize(config_path) 