#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import logging
import subprocess
import psutil
import json
import datetime
from pathlib import Path

# Configurazione logger
LOG_DIR = "/opt/m4bot/logs"
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "health_monitor.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("health_monitor")

# Configurazione
CONFIG = {
    "check_interval": 60,  # Secondi tra i controlli
    "cpu_threshold": 80.0,  # Soglia per avvisi CPU
    "memory_threshold": 85.0,  # Soglia per avvisi memoria
    "disk_threshold": 90.0,  # Soglia per avvisi disco
    "services": [
        "m4bot",
        "m4bot-web",
        "postgresql",
        "redis-server",
        "nginx"
    ]
}

# Directory di installazione e percorsi
INSTALL_DIR = "/opt/m4bot"
CONFIG_FILE = os.path.join(INSTALL_DIR, "config", "monitoring.json")
HISTORY_FILE = os.path.join(LOG_DIR, "health_history.json")

def load_config():
    """Carica la configurazione dal file JSON."""
    global CONFIG
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                file_config = json.load(f)
                CONFIG.update(file_config)
                logger.info(f"Configurazione caricata da {CONFIG_FILE}")
    except Exception as e:
        logger.error(f"Errore nel caricamento della configurazione: {e}")
        
    # Crea un file di configurazione predefinito se non esiste
    if not os.path.exists(CONFIG_FILE):
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, 'w') as f:
                json.dump(CONFIG, f, indent=4)
                logger.info(f"Configurazione predefinita creata in {CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Errore nella creazione del file di configurazione: {e}")

def save_history(data):
    """Salva i dati di monitoraggio nella cronologia."""
    try:
        # Carica la cronologia esistente
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, 'r') as f:
                history = json.load(f)
        
        # Limita la cronologia a 1000 voci
        history.append(data)
        if len(history) > 1000:
            history = history[-1000:]
        
        # Salva la cronologia aggiornata
        with open(HISTORY_FILE, 'w') as f:
            json.dump(history, f)
            
    except Exception as e:
        logger.error(f"Errore nel salvataggio della cronologia: {e}")

def check_system_health():
    """Esegue un controllo completo dello stato di salute del sistema."""
    timestamp = datetime.datetime.now().isoformat()
    issues = []
    
    # Controlla CPU
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        logger.info(f"Utilizzo CPU: {cpu_percent}%")
        
        if cpu_percent > CONFIG["cpu_threshold"]:
            msg = f"AVVISO: Utilizzo CPU alto ({cpu_percent}%)"
            logger.warning(msg)
            issues.append({"type": "cpu", "message": msg, "value": cpu_percent})
    except Exception as e:
        logger.error(f"Errore nel controllo CPU: {e}")
    
    # Controlla memoria
    try:
        memory = psutil.virtual_memory()
        logger.info(f"Utilizzo memoria: {memory.percent}%")
        
        if memory.percent > CONFIG["memory_threshold"]:
            msg = f"AVVISO: Utilizzo memoria alto ({memory.percent}%)"
            logger.warning(msg)
            issues.append({"type": "memory", "message": msg, "value": memory.percent})
    except Exception as e:
        logger.error(f"Errore nel controllo memoria: {e}")
    
    # Controlla disco
    try:
        disk = psutil.disk_usage('/')
        logger.info(f"Utilizzo disco: {disk.percent}%")
        
        if disk.percent > CONFIG["disk_threshold"]:
            msg = f"AVVISO: Utilizzo disco alto ({disk.percent}%)"
            logger.warning(msg)
            issues.append({"type": "disk", "message": msg, "value": disk.percent})
    except Exception as e:
        logger.error(f"Errore nel controllo disco: {e}")
    
    # Controlla servizi
    services_status = {}
    for service in CONFIG["services"]:
        try:
            result = subprocess.run(["systemctl", "is-active", service], 
                                   capture_output=True, text=True)
            status = result.stdout.strip()
            services_status[service] = status
            
            if status == "active":
                logger.info(f"Servizio {service}: ATTIVO")
            else:
                msg = f"AVVISO: Servizio {service} NON ATTIVO ({status})"
                logger.warning(msg)
                issues.append({"type": "service", "service": service, "message": msg, "status": status})
        except Exception as e:
            logger.error(f"Errore nel controllo del servizio {service}: {e}")
    
    # Controlla connessione database
    try:
        # Tenta di connettersi al database PostgreSQL
        import psycopg2
        conn = psycopg2.connect(
            host="localhost",
            port=5432,
            database="m4bot",
            user="m4bot",
            password="",  # Password vuota per sicurezza, si usa .pgpass o variabili d'ambiente
            connect_timeout=3
        )
        conn.close()
        logger.info("Connessione al database: OK")
    except Exception as e:
        msg = f"AVVISO: Problema di connessione al database: {str(e)}"
        logger.warning(msg)
        issues.append({"type": "database", "message": msg})
    
    # Salva i dati di questo controllo
    health_data = {
        "timestamp": timestamp,
        "cpu_percent": cpu_percent,
        "memory_percent": memory.percent,
        "disk_percent": disk.percent,
        "services": services_status,
        "issues": issues
    }
    
    save_history(health_data)
    
    return health_data, len(issues) == 0

def attempt_service_recovery(service):
    """Tenta di ripristinare un servizio non attivo."""
    try:
        logger.info(f"Tentativo di ripristino del servizio {service}...")
        result = subprocess.run(["systemctl", "restart", service], 
                               capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info(f"Servizio {service} riavviato con successo")
            return True
        else:
            logger.error(f"Errore nel riavvio del servizio {service}: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"Errore nel tentativo di ripristino del servizio {service}: {e}")
        return False

def generate_health_report():
    """Genera un report sullo stato di salute del sistema."""
    try:
        if not os.path.exists(HISTORY_FILE):
            logger.warning("Nessun dato storico disponibile per il report")
            return
        
        # Carica i dati storici
        with open(HISTORY_FILE, 'r') as f:
            history = json.load(f)
        
        if not history:
            logger.warning("Dati storici vuoti")
            return
        
        # Calcola statistiche
        cpu_values = [entry.get("cpu_percent", 0) for entry in history]
        memory_values = [entry.get("memory_percent", 0) for entry in history]
        disk_values = [entry.get("disk_percent", 0) for entry in history]
        
        avg_cpu = sum(cpu_values) / len(cpu_values) if cpu_values else 0
        avg_memory = sum(memory_values) / len(memory_values) if memory_values else 0
        avg_disk = sum(disk_values) / len(disk_values) if disk_values else 0
        
        max_cpu = max(cpu_values) if cpu_values else 0
        max_memory = max(memory_values) if memory_values else 0
        max_disk = max(disk_values) if disk_values else 0
        
        # Conta problemi per tipo
        issue_counts = {}
        for entry in history:
            for issue in entry.get("issues", []):
                issue_type = issue.get("type", "unknown")
                issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
        
        # Genera il report
        report = {
            "generated_at": datetime.datetime.now().isoformat(),
            "statistics": {
                "samples": len(history),
                "avg_cpu": avg_cpu,
                "avg_memory": avg_memory,
                "avg_disk": avg_disk,
                "max_cpu": max_cpu,
                "max_memory": max_memory,
                "max_disk": max_disk
            },
            "issues": issue_counts
        }
        
        # Salva il report
        report_file = os.path.join(LOG_DIR, f"health_report_{datetime.datetime.now().strftime('%Y%m%d')}.json")
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=4)
        
        logger.info(f"Report di salute generato: {report_file}")
        
    except Exception as e:
        logger.error(f"Errore nella generazione del report: {e}")

if __name__ == "__main__":
    logger.info("Avvio del monitoraggio di salute del sistema M4Bot...")
    
    # Carica la configurazione
    load_config()
    
    report_interval = 24 * 60 * 60  # Genera report ogni 24 ore
    last_report_time = time.time()
    
    try:
        while True:
            # Esegui il controllo di salute
            health_data, is_healthy = check_system_health()
            
            # Logica di ripristino automatico
            if not is_healthy:
                logger.warning("Problemi rilevati, tentativo di risoluzione automatica...")
                
                # Tenta di ripristinare i servizi inattivi
                for issue in health_data.get("issues", []):
                    if issue.get("type") == "service":
                        service_name = issue.get("service")
                        if service_name:
                            attempt_service_recovery(service_name)
            
            # Genera report periodico
            current_time = time.time()
            if current_time - last_report_time >= report_interval:
                generate_health_report()
                last_report_time = current_time
            
            # Attendi prima del prossimo controllo
            time.sleep(CONFIG["check_interval"])
            
    except KeyboardInterrupt:
        logger.info("Monitoraggio interrotto dall'utente")
    except Exception as e:
        logger.error(f"Errore critico nel monitoraggio: {e}")
        sys.exit(1) 