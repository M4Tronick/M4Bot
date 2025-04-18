#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Modulo di monitoraggio per M4Bot
Fornisce funzionalità per monitorare lo stato del sistema, dei servizi e inviare avvisi.
"""

import os
import sys
import time
import json
import logging
import threading
import subprocess
import datetime
import platform
from typing import Dict, List, Any, Optional, Union

# Importazione condizionale di psutil
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Configurazione del logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('m4bot.monitoring')

# Percorso configurazione
CONFIG_DIR = "/opt/m4bot/config" if os.path.exists("/opt/m4bot/config") else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config")
CONFIG_FILE = os.path.join(CONFIG_DIR, "monitoring", "config.json")
LOG_DIR = "/var/log/m4bot" if os.path.exists("/var/log/m4bot") else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
LOG_FILE = os.path.join(LOG_DIR, "monitoring.log")

# Stato globale del sistema
_system_state = {
    "last_update": None,
    "cpu": {
        "usage": 0.0,
        "temperature": None,
        "cores": None
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
    "network": {
        "sent": 0,
        "received": 0,
        "connections": 0
    },
    "uptime": 0,
    "services": [],
    "alerts": []
}

# Configurazione di default
DEFAULT_CONFIG = {
    "interval": 60,  # Intervallo di monitoraggio in secondi
    "cpu_threshold": 80.0,  # Soglia di utilizzo CPU per avvisi
    "memory_threshold": 85.0,  # Soglia di utilizzo memoria per avvisi
    "disk_threshold": 90.0,  # Soglia di utilizzo disco per avvisi
    "alert_channels": ["log", "web"],  # Canali per gli avvisi (log, web, email, telegram)
    "email_alerts": {
        "enabled": False,
        "smtp_server": "",
        "port": 587,
        "username": "",
        "password": "",
        "sender": "",
        "recipients": []
    },
    "telegram_alerts": {
        "enabled": False,
        "bot_token": "",
        "chat_ids": []
    },
    "services": [
        {
            "name": "m4bot-web",
            "type": "systemd",
            "critical": True,
            "restart_on_failure": True
        },
        {
            "name": "m4bot-bot",
            "type": "systemd",
            "critical": True,
            "restart_on_failure": True
        },
        {
            "name": "m4bot-monitoring",
            "type": "systemd",
            "critical": False,
            "restart_on_failure": True
        }
    ],
    "log_rotation": {
        "enabled": True,
        "max_size_mb": 10,
        "backup_count": 5
    },
    "notification_throttling": {
        "enabled": True,
        "min_interval_seconds": 300  # Intervallo minimo tra notifiche dello stesso tipo
    }
}

# Thread di monitoraggio
_monitoring_thread = None
_should_run = False
_config = None

class MonitoringManager:
    """Gestisce il monitoraggio del sistema e dei servizi."""
    
    def __init__(self, config=None):
        self.config = config or self._load_config()
        self.last_alert_times = {}  # Per throttling delle notifiche
        
        # Configura il file di log se necessario
        if not os.path.exists(LOG_DIR):
            try:
                os.makedirs(LOG_DIR, exist_ok=True)
            except Exception as e:
                logger.error(f"Impossibile creare la directory dei log: {str(e)}")
        
        # Aggiunge un handler di file se la directory log esiste
        if os.path.exists(LOG_DIR):
            try:
                from logging.handlers import RotatingFileHandler
                
                # Configura la rotazione dei log se abilitata
                if self.config.get("log_rotation", {}).get("enabled", True):
                    max_size = self.config.get("log_rotation", {}).get("max_size_mb", 10) * 1024 * 1024
                    backup_count = self.config.get("log_rotation", {}).get("backup_count", 5)
                    
                    file_handler = RotatingFileHandler(
                        LOG_FILE,
                        maxBytes=max_size,
                        backupCount=backup_count
                    )
                else:
                    file_handler = logging.FileHandler(LOG_FILE)
                
                file_handler.setFormatter(logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
                ))
                logger.addHandler(file_handler)
            except Exception as e:
                logger.error(f"Errore nella configurazione del file di log: {str(e)}")
        
        logger.info("Inizializzazione del modulo di monitoraggio completata")
    
    def _load_config(self):
        """Carica la configurazione dal file o utilizza i valori predefiniti."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config = json.load(f)
                logger.info(f"Configurazione caricata da {CONFIG_FILE}")
                return config
            else:
                logger.warning(f"File di configurazione {CONFIG_FILE} non trovato, uso dei valori predefiniti")
                
                # Crea la directory di configurazione se non esiste
                os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
                
                # Salva la configurazione predefinita
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(DEFAULT_CONFIG, f, indent=4)
                
                return DEFAULT_CONFIG
        except Exception as e:
            logger.error(f"Errore nel caricamento della configurazione: {str(e)}")
            return DEFAULT_CONFIG
    
    def update_system_state(self):
        """Aggiorna lo stato del sistema."""
        global _system_state
        
        # Aggiorna il timestamp
        _system_state["last_update"] = time.time()
        
        # Controlla la disponibilità di psutil
        if not PSUTIL_AVAILABLE:
            logger.warning("psutil non disponibile, impossibile raccogliere statistiche dettagliate")
            return
        
        try:
            # Statistiche CPU
            _system_state["cpu"]["usage"] = psutil.cpu_percent(interval=1)
            _system_state["cpu"]["cores"] = psutil.cpu_count()
            
            # Prova a ottenere la temperatura se disponibile
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if temps:
                    # Prendi la prima temperatura disponibile
                    for name, entries in temps.items():
                        if entries:
                            _system_state["cpu"]["temperature"] = entries[0].current
                            break
            
            # Statistiche memoria
            mem = psutil.virtual_memory()
            _system_state["memory"]["total"] = mem.total
            _system_state["memory"]["used"] = mem.used
            _system_state["memory"]["percent"] = mem.percent
            
            # Statistiche disco
            disk = psutil.disk_usage('/')
            _system_state["disk"]["total"] = disk.total
            _system_state["disk"]["used"] = disk.used
            _system_state["disk"]["percent"] = disk.percent
            
            # Statistiche rete
            net_io = psutil.net_io_counters()
            _system_state["network"]["sent"] = net_io.bytes_sent
            _system_state["network"]["received"] = net_io.bytes_recv
            _system_state["network"]["connections"] = len(psutil.net_connections())
            
            # Uptime
            _system_state["uptime"] = time.time() - psutil.boot_time()
            
            # Verifica se ci sono soglie superate e genera avvisi
            self._check_thresholds()
            
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento dello stato del sistema: {str(e)}")
    
    def update_services_state(self):
        """Aggiorna lo stato dei servizi configurati."""
        global _system_state
        
        services_list = []
        
        for service_config in self.config.get("services", []):
            service_name = service_config.get("name")
            service_type = service_config.get("type", "systemd")
            
            service_state = {
                "name": service_name,
                "type": service_type,
                "status": "unknown",
                "running": False,
                "critical": service_config.get("critical", False),
                "restart_on_failure": service_config.get("restart_on_failure", False),
                "last_restart": None
            }
            
            try:
                if service_type == "systemd":
                    # Controlla lo stato del servizio systemd
                    result = subprocess.run(
                        ["systemctl", "is-active", service_name],
                        capture_output=True, 
                        text=True, 
                        check=False
                    )
                    
                    status = result.stdout.strip()
                    service_state["status"] = status
                    service_state["running"] = (status == "active")
                    
                    # Ottieni informazioni aggiuntive
                    if service_state["running"]:
                        # Ottieni il tempo di avvio
                        result = subprocess.run(
                            ["systemctl", "show", service_name, "--property=ActiveEnterTimestamp"],
                            capture_output=True, 
                            text=True, 
                            check=False
                        )
                        if result.returncode == 0:
                            timestamp_line = result.stdout.strip()
                            if "=" in timestamp_line:
                                timestamp_str = timestamp_line.split("=", 1)[1]
                                # Formato: "Tue 2023-08-15 12:34:56 UTC"
                                try:
                                    service_state["started_at"] = timestamp_str
                                except Exception:
                                    pass
                    
                    # Se il servizio è critico e non è in esecuzione, genera un avviso
                    if service_config.get("critical", False) and not service_state["running"]:
                        self._add_alert(
                            "Servizio critico non attivo",
                            f"Il servizio {service_name} non è in esecuzione",
                            "critical"
                        )
                        
                        # Riavvia il servizio se configurato
                        if service_config.get("restart_on_failure", False):
                            self._restart_service(service_name)
                            service_state["last_restart"] = time.time()
                
                elif service_type == "process":
                    # Controlla se il processo è in esecuzione per nome
                    process_name = service_name
                    running = False
                    
                    for proc in psutil.process_iter(['pid', 'name']):
                        if process_name.lower() in proc.info['name'].lower():
                            running = True
                            break
                    
                    service_state["running"] = running
                    service_state["status"] = "running" if running else "stopped"
                    
                    # Se il processo è critico e non è in esecuzione, genera un avviso
                    if service_config.get("critical", False) and not running:
                        self._add_alert(
                            "Processo critico non attivo",
                            f"Il processo {process_name} non è in esecuzione",
                            "critical"
                        )
            except Exception as e:
                logger.error(f"Errore nel controllo del servizio {service_name}: {str(e)}")
                service_state["status"] = "error"
                service_state["error"] = str(e)
            
            services_list.append(service_state)
        
        # Aggiorna la lista dei servizi
        _system_state["services"] = services_list
    
    def _check_thresholds(self):
        """Controlla se le metriche del sistema superano le soglie configurate."""
        # Controlla CPU
        if _system_state["cpu"]["usage"] > self.config.get("cpu_threshold", 80.0):
            self._add_alert(
                "Utilizzo CPU elevato",
                f"L'utilizzo della CPU ha raggiunto il {_system_state['cpu']['usage']:.1f}%",
                "warning"
            )
        
        # Controlla memoria
        if _system_state["memory"]["percent"] > self.config.get("memory_threshold", 85.0):
            self._add_alert(
                "Utilizzo memoria elevato",
                f"L'utilizzo della memoria ha raggiunto il {_system_state['memory']['percent']:.1f}%",
                "warning"
            )
        
        # Controlla disco
        if _system_state["disk"]["percent"] > self.config.get("disk_threshold", 90.0):
            self._add_alert(
                "Spazio su disco basso",
                f"L'utilizzo del disco ha raggiunto il {_system_state['disk']['percent']:.1f}%",
                "warning"
            )
    
    def _add_alert(self, title, message, level="info"):
        """Aggiunge un nuovo avviso e lo invia attraverso i canali configurati."""
        global _system_state
        
        # Verifica il throttling delle notifiche
        if self.config.get("notification_throttling", {}).get("enabled", True):
            min_interval = self.config.get("notification_throttling", {}).get("min_interval_seconds", 300)
            
            # Crea una chiave per il tipo di avviso
            alert_key = f"{level}:{title}"
            
            # Controlla se un avviso simile è stato inviato recentemente
            current_time = time.time()
            if alert_key in self.last_alert_times:
                time_since_last = current_time - self.last_alert_times[alert_key]
                if time_since_last < min_interval:
                    logger.debug(f"Limitazione della notifica: {title} (inviata {time_since_last:.1f}s fa)")
                    return
            
            # Aggiorna il timestamp dell'ultimo avviso
            self.last_alert_times[alert_key] = current_time
        
        # Crea l'oggetto avviso
        alert = {
            "id": str(int(time.time() * 1000)),
            "title": title,
            "message": message,
            "level": level,
            "timestamp": time.time(),
            "timestamp_str": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "acknowledged": False
        }
        
        # Aggiungi l'avviso alla lista
        _system_state["alerts"].insert(0, alert)
        
        # Limita il numero di avvisi memorizzati
        max_alerts = 100
        if len(_system_state["alerts"]) > max_alerts:
            _system_state["alerts"] = _system_state["alerts"][:max_alerts]
        
        # Invia l'avviso attraverso i canali configurati
        channels = self.config.get("alert_channels", ["log"])
        
        # Log
        if "log" in channels:
            log_method = getattr(logger, level) if hasattr(logger, level) else logger.info
            log_method(f"AVVISO: {title} - {message}")
        
        # Email
        if "email" in channels and self.config.get("email_alerts", {}).get("enabled", False):
            self._send_email_alert(alert)
        
        # Telegram
        if "telegram" in channels and self.config.get("telegram_alerts", {}).get("enabled", False):
            self._send_telegram_alert(alert)
    
    def _send_email_alert(self, alert):
        """Invia un avviso via email."""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            email_config = self.config.get("email_alerts", {})
            
            if not email_config.get("smtp_server") or not email_config.get("recipients"):
                logger.warning("Configurazione email incompleta, impossibile inviare l'avviso")
                return
            
            # Crea il messaggio
            msg = MIMEMultipart()
            msg["From"] = email_config.get("sender", email_config.get("username", "m4bot@localhost"))
            msg["To"] = ", ".join(email_config.get("recipients", []))
            msg["Subject"] = f"M4Bot Avviso: {alert['title']}"
            
            # Corpo del messaggio
            body = f"""
            <html>
            <body>
                <h2>Avviso M4Bot</h2>
                <p><strong>Livello:</strong> {alert['level']}</p>
                <p><strong>Titolo:</strong> {alert['title']}</p>
                <p><strong>Messaggio:</strong> {alert['message']}</p>
                <p><strong>Data/Ora:</strong> {alert['timestamp_str']}</p>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(body, "html"))
            
            # Connessione al server SMTP
            server = smtplib.SMTP(email_config.get("smtp_server"), email_config.get("port", 587))
            server.starttls()
            
            # Login
            if email_config.get("username") and email_config.get("password"):
                server.login(email_config.get("username"), email_config.get("password"))
            
            # Invio
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Avviso inviato via email a {len(email_config.get('recipients', []))} destinatari")
        except Exception as e:
            logger.error(f"Errore nell'invio dell'avviso via email: {str(e)}")
    
    def _send_telegram_alert(self, alert):
        """Invia un avviso via Telegram."""
        try:
            import requests
            
            telegram_config = self.config.get("telegram_alerts", {})
            
            if not telegram_config.get("bot_token") or not telegram_config.get("chat_ids"):
                logger.warning("Configurazione Telegram incompleta, impossibile inviare l'avviso")
                return
            
            # Prepara il messaggio
            emoji_map = {
                "info": "ℹ️",
                "warning": "⚠️",
                "error": "❌",
                "critical": "🚨"
            }
            
            emoji = emoji_map.get(alert['level'], "🔔")
            
            message = f"{emoji} *M4Bot Avviso*\n\n"
            message += f"*Livello:* {alert['level']}\n"
            message += f"*Titolo:* {alert['title']}\n"
            message += f"*Messaggio:* {alert['message']}\n"
            message += f"*Data/Ora:* {alert['timestamp_str']}"
            
            # Invia a tutti i chat ID configurati
            bot_token = telegram_config.get("bot_token")
            
            for chat_id in telegram_config.get("chat_ids", []):
                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                
                data = {
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "Markdown"
                }
                
                response = requests.post(url, data=data)
                
                if response.status_code != 200:
                    logger.warning(f"Errore nell'invio dell'avviso Telegram: {response.text}")
            
            logger.info(f"Avviso inviato via Telegram a {len(telegram_config.get('chat_ids', []))} chat")
        except Exception as e:
            logger.error(f"Errore nell'invio dell'avviso via Telegram: {str(e)}")
    
    def _restart_service(self, service_name):
        """Riavvia un servizio systemd."""
        try:
            logger.info(f"Tentativo di riavvio del servizio {service_name}")
            
            result = subprocess.run(
                ["systemctl", "restart", service_name],
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                logger.info(f"Servizio {service_name} riavviato con successo")
                self._add_alert(
                    "Servizio riavviato",
                    f"Il servizio {service_name} è stato riavviato automaticamente",
                    "info"
                )
                return True
            else:
                logger.error(f"Errore nel riavvio del servizio {service_name}: {result.stderr}")
                self._add_alert(
                    "Errore nel riavvio del servizio",
                    f"Impossibile riavviare {service_name}: {result.stderr}",
                    "error"
                )
                return False
        except Exception as e:
            logger.error(f"Eccezione nel riavvio del servizio {service_name}: {str(e)}")
            return False
    
    def run_monitoring_cycle(self):
        """Esegue un ciclo completo di monitoraggio."""
        try:
            # Aggiorna lo stato del sistema
            self.update_system_state()
            
            # Aggiorna lo stato dei servizi
            self.update_services_state()
            
            logger.debug("Ciclo di monitoraggio completato")
        except Exception as e:
            logger.error(f"Errore nel ciclo di monitoraggio: {str(e)}")

def monitoring_thread_function():
    """Funzione per il thread di monitoraggio."""
    global _should_run, _config
    
    logger.info("Thread di monitoraggio avviato")
    
    manager = MonitoringManager(_config)
    
    while _should_run:
        try:
            # Esegui un ciclo di monitoraggio
            manager.run_monitoring_cycle()
            
            # Attendi l'intervallo configurato
            interval = _config.get("interval", 60)
            time.sleep(interval)
        except Exception as e:
            logger.error(f"Errore nel thread di monitoraggio: {str(e)}")
            time.sleep(10)  # In caso di errore, aspetta un po' prima di riprovare
    
    logger.info("Thread di monitoraggio terminato")

def start_monitoring(config=None):
    """Avvia il thread di monitoraggio."""
    global _monitoring_thread, _should_run, _config
    
    # Se il thread è già in esecuzione, non fare nulla
    if _monitoring_thread is not None and _monitoring_thread.is_alive():
        logger.warning("Il thread di monitoraggio è già in esecuzione")
        return False
    
    # Carica la configurazione
    _config = config or DEFAULT_CONFIG
    
    # Imposta il flag per l'esecuzione
    _should_run = True
    
    # Avvia il thread
    _monitoring_thread = threading.Thread(
        target=monitoring_thread_function,
        daemon=True
    )
    _monitoring_thread.start()
    
    logger.info("Monitoraggio avviato")
    return True

def stop_monitoring():
    """Ferma il thread di monitoraggio."""
    global _monitoring_thread, _should_run
    
    # Imposta il flag per fermare l'esecuzione
    _should_run = False
    
    # Attendi che il thread termini (con timeout)
    if _monitoring_thread is not None:
        _monitoring_thread.join(timeout=5.0)
        _monitoring_thread = None
    
    logger.info("Monitoraggio fermato")
    return True

def get_monitoring_data():
    """Restituisce i dati di monitoraggio attuali."""
    global _system_state
    
    # Converti timestamp in stringhe leggibili per la visualizzazione
    monitoring_data = {
        "system": {
            "cpu_usage": _system_state["cpu"]["usage"],
            "cpu_temperature": _system_state["cpu"]["temperature"],
            "cpu_cores": _system_state["cpu"]["cores"],
            "memory_total": _system_state["memory"]["total"],
            "memory_used": _system_state["memory"]["used"],
            "memory_percent": _system_state["memory"]["percent"],
            "disk_total": _system_state["disk"]["total"],
            "disk_used": _system_state["disk"]["used"],
            "disk_percent": _system_state["disk"]["percent"],
            "network_sent": _system_state["network"]["sent"],
            "network_received": _system_state["network"]["received"],
            "network_connections": _system_state["network"]["connections"],
            "uptime": _system_state["uptime"],
            "uptime_str": format_uptime(_system_state["uptime"]),
            "last_update": _system_state["last_update"],
            "last_update_str": format_timestamp(_system_state["last_update"]) if _system_state["last_update"] else None
        },
        "services": _system_state["services"],
        "alerts": _system_state["alerts"]
    }
    
    return monitoring_data

def get_system_info():
    """Restituisce informazioni dettagliate sul sistema."""
    system_info = {
        "os": {
            "name": platform.system(),
            "version": platform.version(),
            "release": platform.release(),
            "architecture": platform.machine()
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "compiler": platform.python_compiler()
        },
        "network": {
            "hostname": platform.node()
        }
    }
    
    # Aggiunge ulteriori dettagli se psutil è disponibile
    if PSUTIL_AVAILABLE:
        try:
            # Informazioni sull'avvio
            system_info["boot_time"] = psutil.boot_time()
            system_info["boot_time_str"] = datetime.datetime.fromtimestamp(
                psutil.boot_time()
            ).strftime("%Y-%m-%d %H:%M:%S")
            
            # Informazioni sulla CPU
            cpu_info = {
                "physical_cores": psutil.cpu_count(logical=False),
                "total_cores": psutil.cpu_count(logical=True),
                "max_frequency": psutil.cpu_freq().max if psutil.cpu_freq() else None,
                "min_frequency": psutil.cpu_freq().min if psutil.cpu_freq() else None,
                "current_frequency": psutil.cpu_freq().current if psutil.cpu_freq() else None
            }
            system_info["cpu"] = cpu_info
            
            # Informazioni sulla memoria
            memory_info = {
                "total": psutil.virtual_memory().total,
                "available": psutil.virtual_memory().available,
                "used": psutil.virtual_memory().used,
                "percent": psutil.virtual_memory().percent
            }
            system_info["memory"] = memory_info
            
            # Informazioni sulla swap
            swap_info = {
                "total": psutil.swap_memory().total,
                "used": psutil.swap_memory().used,
                "free": psutil.swap_memory().free,
                "percent": psutil.swap_memory().percent
            }
            system_info["swap"] = swap_info
            
            # Informazioni sui dischi
            disks = []
            for partition in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disk_info = {
                        "device": partition.device,
                        "mountpoint": partition.mountpoint,
                        "filesystem": partition.fstype,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent
                    }
                    disks.append(disk_info)
                except (PermissionError, OSError):
                    # Alcuni punti di montaggio potrebbero non essere accessibili
                    pass
            system_info["disks"] = disks
            
            # Informazioni sulle interfacce di rete
            network_info = {}
            if hasattr(psutil, "net_if_addrs"):
                for interface_name, interface_addresses in psutil.net_if_addrs().items():
                    addresses = []
                    for address in interface_addresses:
                        addr_info = {
                            "family": str(address.family),
                            "address": address.address,
                            "netmask": address.netmask,
                            "broadcast": address.broadcast
                        }
                        addresses.append(addr_info)
                    network_info[interface_name] = addresses
            system_info["network_interfaces"] = network_info
            
        except Exception as e:
            logger.error(f"Errore nel recupero delle informazioni di sistema: {str(e)}")
    
    return system_info

def get_services_status():
    """Restituisce lo stato attuale dei servizi monitorati."""
    global _system_state
    return _system_state["services"]

def get_alerts(limit=50, include_acknowledged=False):
    """Restituisce gli avvisi generati."""
    global _system_state
    
    if include_acknowledged:
        alerts = _system_state["alerts"][:limit]
    else:
        alerts = [alert for alert in _system_state["alerts"] if not alert.get("acknowledged", False)][:limit]
    
    return alerts

def acknowledge_alert(alert_id):
    """Segna un avviso come riconosciuto."""
    global _system_state
    
    for alert in _system_state["alerts"]:
        if alert.get("id") == alert_id:
            alert["acknowledged"] = True
            logger.info(f"Avviso {alert_id} segnato come riconosciuto")
            return True
    
    logger.warning(f"Avviso {alert_id} non trovato")
    return False

def restart_service(service_name):
    """Riavvia un servizio systemd."""
    try:
        result = subprocess.run(
            ["systemctl", "restart", service_name],
            capture_output=True,
            text=True,
            check=False
        )
        
        success = result.returncode == 0
        
        response = {
            "success": success,
            "service": service_name,
            "output": result.stdout if success else result.stderr
        }
        
        # Aggiorna lo stato dei servizi
        if _monitoring_thread and _monitoring_thread.is_alive():
            manager = MonitoringManager(_config)
            manager.update_services_state()
        
        # Registra l'evento
        if success:
            logger.info(f"Servizio {service_name} riavviato con successo")
        else:
            logger.error(f"Errore nel riavvio del servizio {service_name}: {result.stderr}")
        
        return response
    except Exception as e:
        logger.error(f"Eccezione nel riavvio del servizio {service_name}: {str(e)}")
        return {
            "success": False,
            "service": service_name,
            "error": str(e)
        }

def format_uptime(seconds):
    """Formatta i secondi in una stringa di uptime leggibile."""
    days, remainder = divmod(int(seconds), 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    if minutes > 0 or hours > 0 or days > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    
    return " ".join(parts)

def format_timestamp(timestamp):
    """Formatta un timestamp in una stringa leggibile."""
    if timestamp is None:
        return None
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

def format_bytes(bytes_value):
    """Formatta i byte in una stringa leggibile."""
    if bytes_value < 1024:
        return f"{bytes_value} B"
    elif bytes_value < 1024 * 1024:
        return f"{bytes_value / 1024:.2f} KB"
    elif bytes_value < 1024 * 1024 * 1024:
        return f"{bytes_value / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_value / (1024 * 1024 * 1024):.2f} GB"

# Funzione chiamata all'inizializzazione del modulo
def init_monitoring(app=None, config=None):
    """Inizializza il modulo di monitoraggio."""
    logger.info("Inizializzazione del modulo di monitoraggio")
    
    # Avvia il monitoraggio con la configurazione fornita
    if config:
        start_monitoring(config)
    else:
        # Carica la configurazione dal file
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    config_data = json.load(f)
                start_monitoring(config_data)
            else:
                # Crea la directory di configurazione se non esiste
                os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
                
                # Salva la configurazione predefinita
                with open(CONFIG_FILE, 'w') as f:
                    json.dump(DEFAULT_CONFIG, f, indent=4)
                
                start_monitoring(DEFAULT_CONFIG)
        except Exception as e:
            logger.error(f"Errore nel caricamento della configurazione: {str(e)}")
            start_monitoring(DEFAULT_CONFIG)
    
    # Se viene fornita l'app, configura gli endpoint del monitoraggio
    if app:
        logger.info("Configurazione degli endpoint di monitoraggio per l'app")
        # Qui puoi registrare route o middleware specifici
    
    return True

# Punto di ingresso se il modulo viene eseguito direttamente
if __name__ == "__main__":
    print("Modulo di monitoraggio M4Bot")
    print("Questo modulo è destinato a essere importato, non eseguito direttamente.")
    
    # Se eseguito direttamente, avvia il monitoraggio come test
    init_monitoring()
    
    # Mantieni il processo in esecuzione
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Interruzione del monitoraggio...")
        stop_monitoring()
        print("Monitoraggio fermato.") 