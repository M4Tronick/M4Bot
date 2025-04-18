#!/usr/bin/env python3
"""
M4Bot Prometheus Exporter
Esporta metriche di M4Bot per il monitoraggio con Prometheus

Questo modulo crea un endpoint HTTP che Prometheus può scrapare
per raccogliere metriche sullo stato e le prestazioni di M4Bot.
"""

import os
import sys
import time
import json
import logging
import psutil
import threading
import datetime
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional

# Utilizza il framework Prometheus client
try:
    from prometheus_client import start_http_server, Counter, Gauge, Histogram, Summary, Info
    from prometheus_client.core import CollectorRegistry
except ImportError:
    print("Errore: prometheus_client non installato.")
    print("Installalo con: pip install prometheus_client")
    sys.exit(1)

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/var/log/m4bot/prometheus_exporter.log")
    ]
)
logger = logging.getLogger("m4bot_prometheus")

# Constants
DEFAULT_PORT = 9090
DEFAULT_INTERVAL = 15  # secondi
M4BOT_DIR = os.environ.get("M4BOT_DIR", "/opt/m4bot")

# Crea directory per log se non esiste
os.makedirs("/var/log/m4bot", exist_ok=True)

class M4BotExporter:
    """Esportatore di metriche per M4Bot"""
    
    def __init__(self, port: int = DEFAULT_PORT, interval: int = DEFAULT_INTERVAL):
        """
        Inizializza l'esportatore
        
        Args:
            port: Porta su cui esporre le metriche
            interval: Intervallo di raccolta in secondi
        """
        self.port = port
        self.interval = interval
        self.registry = CollectorRegistry()
        
        # Inizializzazione metriche
        self._setup_metrics()
        
        # Configurazione state
        self.last_update = datetime.datetime.now()
        self.services_status = {}
        self.running = False
        
        logger.info(f"M4Bot Prometheus Exporter inizializzato (porta: {port}, intervallo: {interval}s)")
    
    def _setup_metrics(self):
        """Inizializza tutte le metriche Prometheus"""
        
        # Metriche di sistema
        self.system_cpu_usage = Gauge('m4bot_system_cpu_usage', 'Utilizzo CPU del sistema (%)', registry=self.registry)
        self.system_memory_usage = Gauge('m4bot_system_memory_usage', 'Utilizzo memoria del sistema (%)', registry=self.registry)
        self.system_disk_usage = Gauge('m4bot_system_disk_usage', 'Utilizzo disco del sistema (%)', registry=self.registry)
        self.system_uptime = Gauge('m4bot_system_uptime', 'Uptime del sistema in secondi', registry=self.registry)
        
        # Metriche dei servizi
        self.service_up = Gauge('m4bot_service_up', 'Stato del servizio (1=up, 0=down)', 
                               ['service'], registry=self.registry)
        self.service_restarts = Counter('m4bot_service_restarts_total', 'Numero totale di riavvii del servizio', 
                                      ['service'], registry=self.registry)
        
        # Metriche dell'applicazione
        self.app_requests_total = Counter('m4bot_app_requests_total', 'Numero totale di richieste ricevute', 
                                        ['endpoint'], registry=self.registry)
        self.app_request_duration = Histogram('m4bot_app_request_duration_seconds', 'Durata delle richieste in secondi', 
                                            ['endpoint'], registry=self.registry)
        self.app_errors_total = Counter('m4bot_app_errors_total', 'Numero totale di errori', 
                                      ['type'], registry=self.registry)
        
        # Metriche del database
        self.db_connections = Gauge('m4bot_db_connections', 'Numero corrente di connessioni al database', registry=self.registry)
        self.db_queries_total = Counter('m4bot_db_queries_total', 'Numero totale di query al database', registry=self.registry)
        self.db_query_duration = Summary('m4bot_db_query_duration_seconds', 'Durata delle query in secondi', registry=self.registry)
        
        # Metriche specifiche di M4Bot
        self.bot_users_total = Gauge('m4bot_users_total', 'Numero totale di utenti', registry=self.registry)
        self.bot_active_users = Gauge('m4bot_active_users', 'Numero di utenti attivi nelle ultime 24 ore', registry=self.registry)
        self.bot_commands_total = Counter('m4bot_commands_total', 'Numero totale di comandi eseguiti', 
                                        ['command'], registry=self.registry)
        self.bot_messages_processed = Counter('m4bot_messages_processed_total', 'Numero totale di messaggi elaborati', registry=self.registry)
        
        # Metriche per backup e aggiornamenti
        self.backup_last_success = Gauge('m4bot_backup_last_success_timestamp', 'Timestamp dell\'ultimo backup riuscito', registry=self.registry)
        self.backup_size = Gauge('m4bot_backup_size_bytes', 'Dimensione dell\'ultimo backup in bytes', registry=self.registry)
        self.update_last_check = Gauge('m4bot_update_last_check_timestamp', 'Timestamp dell\'ultimo controllo aggiornamenti', registry=self.registry)
        self.update_available = Gauge('m4bot_update_available', 'Se è disponibile un aggiornamento (1=sì, 0=no)', registry=self.registry)
        
        # Info generali
        self.m4bot_info = Info('m4bot_info', 'Informazioni sulla versione di M4Bot', registry=self.registry)
    
    def collect_system_metrics(self):
        """Raccoglie metriche di sistema"""
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            self.system_cpu_usage.set(cpu_percent)
            
            # Memoria
            memory = psutil.virtual_memory()
            self.system_memory_usage.set(memory.percent)
            
            # Disco
            disk = psutil.disk_usage('/')
            self.system_disk_usage.set(disk.percent)
            
            # Uptime
            boot_time = psutil.boot_time()
            uptime = time.time() - boot_time
            self.system_uptime.set(uptime)
            
            logger.debug("Metriche di sistema raccolte")
            
        except Exception as e:
            logger.error(f"Errore durante la raccolta delle metriche di sistema: {e}")
    
    def collect_service_metrics(self):
        """Raccoglie metriche sui servizi"""
        services = ["m4bot.service", "m4bot-web.service", "nginx", "redis-server", "postgresql"]
        
        try:
            for service in services:
                # Controlla se il servizio è in esecuzione
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True, 
                    text=True,
                    check=False
                )
                
                # Imposta lo stato (1 = attivo, 0 = inattivo)
                is_active = result.stdout.strip() == "active"
                
                # Se lo stato è cambiato da attivo a inattivo, potrebbe essere un riavvio
                if service in self.services_status and self.services_status[service] and not is_active:
                    self.service_restarts.labels(service=service).inc()
                
                # Salva lo stato corrente
                self.services_status[service] = is_active
                self.service_up.labels(service=service).set(1 if is_active else 0)
            
            logger.debug("Metriche dei servizi raccolte")
            
        except Exception as e:
            logger.error(f"Errore durante la raccolta delle metriche dei servizi: {e}")
    
    def collect_app_metrics(self):
        """Raccoglie metriche dell'applicazione dai log"""
        try:
            # Parsiamo i log degli accessi se disponibili
            log_file = os.path.join(M4BOT_DIR, "logs", "access.log")
            if os.path.exists(log_file):
                # Analisi del log per estrarre richieste ed errori
                # Questo è un esempio semplificato
                with open(log_file, 'r') as f:
                    log_lines = f.readlines()
                
                # Analizziamo le ultime 100 righe
                for line in log_lines[-100:]:
                    # Solo le righe più recenti dall'ultimo aggiornamento
                    try:
                        # Esempio di formato log: [2023-05-21 10:15:30] 200 GET /api/status 0.123s
                        parts = line.split()
                        if len(parts) >= 5:
                            timestamp_str = " ".join(parts[0:2]).strip("[]")
                            timestamp = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                            
                            if timestamp > self.last_update:
                                status_code = parts[2]
                                method = parts[3]
                                endpoint = parts[4]
                                duration = float(parts[5].strip("s"))
                                
                                # Incrementa contatori
                                self.app_requests_total.labels(endpoint=endpoint).inc()
                                self.app_request_duration.labels(endpoint=endpoint).observe(duration)
                                
                                # Registra errori
                                if status_code.startswith("5") or status_code.startswith("4"):
                                    self.app_errors_total.labels(type=f"HTTP_{status_code}").inc()
                    except Exception as e:
                        logger.debug(f"Errore durante il parsing della riga di log: {e}")
                        continue
            
            # Statistiche di utilizzo
            stats_file = os.path.join(M4BOT_DIR, "data", "usage_stats.json")
            if os.path.exists(stats_file):
                try:
                    with open(stats_file, 'r') as f:
                        stats = json.load(f)
                    
                    # Aggiorna le metriche con i dati dalle statistiche
                    if "users" in stats:
                        self.bot_users_total.set(stats.get("users", {}).get("total", 0))
                        self.bot_active_users.set(stats.get("users", {}).get("active_24h", 0))
                    
                    if "commands" in stats:
                        for cmd, count in stats.get("commands", {}).items():
                            # Reset e poi impostazione del valore corretto
                            self.bot_commands_total.labels(command=cmd)._value.set(count)
                    
                    if "messages" in stats:
                        self.bot_messages_processed._value.set(stats.get("messages", {}).get("total", 0))
                except Exception as e:
                    logger.error(f"Errore durante la lettura del file delle statistiche: {e}")
            
            logger.debug("Metriche dell'applicazione raccolte")
            
        except Exception as e:
            logger.error(f"Errore durante la raccolta delle metriche dell'applicazione: {e}")
    
    def collect_db_metrics(self):
        """Raccoglie metriche sul database"""
        try:
            # Controlla se possiamo connetterci a PostgreSQL o MySQL
            if self._check_postgres_available():
                # Raccoglie metriche PostgreSQL
                self._collect_postgres_metrics()
            elif self._check_mysql_available():
                # Raccoglie metriche MySQL
                self._collect_mysql_metrics()
            
            logger.debug("Metriche del database raccolte")
            
        except Exception as e:
            logger.error(f"Errore durante la raccolta delle metriche del database: {e}")
    
    def _check_postgres_available(self):
        """Verifica se PostgreSQL è disponibile"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "postgresql"],
                capture_output=True, text=True, check=False
            )
            return result.stdout.strip() == "active"
        except Exception:
            return False
    
    def _check_mysql_available(self):
        """Verifica se MySQL/MariaDB è disponibile"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "mysql"],
                capture_output=True, text=True, check=False
            )
            return result.stdout.strip() == "active"
        except Exception:
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", "mariadb"],
                    capture_output=True, text=True, check=False
                )
                return result.stdout.strip() == "active"
            except Exception:
                return False
    
    def _collect_postgres_metrics(self):
        """Raccoglie metriche PostgreSQL"""
        try:
            # Controlla se psycopg2 è disponibile
            try:
                import psycopg2
            except ImportError:
                logger.warning("psycopg2 non installato. Impossibile raccogliere metriche PostgreSQL dettagliate.")
                return
            
            # Lettura credenziali da file config
            config_file = os.path.join(M4BOT_DIR, "config", "db.json")
            if not os.path.exists(config_file):
                logger.warning("File di configurazione del database non trovato.")
                return
            
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            # Connessione a PostgreSQL
            conn = psycopg2.connect(
                host=config.get("host", "localhost"),
                port=config.get("port", 5432),
                database=config.get("database", "m4bot"),
                user=config.get("user", "m4bot"),
                password=config.get("password", "")
            )
            
            cursor = conn.cursor()
            
            # Numero di connessioni
            cursor.execute("SELECT count(*) FROM pg_stat_activity")
            connections = cursor.fetchone()[0]
            self.db_connections.set(connections)
            
            # Altre metriche potrebbero essere aggiunte qui
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Errore durante la raccolta delle metriche PostgreSQL: {e}")
    
    def _collect_mysql_metrics(self):
        """Raccoglie metriche MySQL/MariaDB"""
        try:
            # Controlla se MySQLdb è disponibile
            try:
                import MySQLdb
            except ImportError:
                logger.warning("MySQLdb non installato. Impossibile raccogliere metriche MySQL dettagliate.")
                return
            
            # Lettura credenziali da file config
            config_file = os.path.join(M4BOT_DIR, "config", "db.json")
            if not os.path.exists(config_file):
                logger.warning("File di configurazione del database non trovato.")
                return
            
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            # Connessione a MySQL
            conn = MySQLdb.connect(
                host=config.get("host", "localhost"),
                port=config.get("port", 3306),
                db=config.get("database", "m4bot"),
                user=config.get("user", "m4bot"),
                passwd=config.get("password", "")
            )
            
            cursor = conn.cursor()
            
            # Numero di connessioni
            cursor.execute("SHOW STATUS WHERE Variable_name = 'Threads_connected'")
            connections = int(cursor.fetchone()[1])
            self.db_connections.set(connections)
            
            # Altre metriche potrebbero essere aggiunte qui
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Errore durante la raccolta delle metriche MySQL: {e}")
    
    def collect_backup_metrics(self):
        """Raccoglie metriche sui backup"""
        try:
            backup_dir = os.path.join(M4BOT_DIR, "backups")
            if os.path.exists(backup_dir):
                # Trova l'ultimo backup
                backups = sorted(Path(backup_dir).glob("*"), key=os.path.getmtime, reverse=True)
                if backups:
                    last_backup = backups[0]
                    last_modified = os.path.getmtime(last_backup)
                    backup_size = 0
                    
                    # Calcola dimensione se è una directory
                    if os.path.isdir(last_backup):
                        for path, dirs, files in os.walk(last_backup):
                            for f in files:
                                fp = os.path.join(path, f)
                                backup_size += os.path.getsize(fp)
                    else:
                        backup_size = os.path.getsize(last_backup)
                    
                    self.backup_last_success.set(last_modified)
                    self.backup_size.set(backup_size)
            
            logger.debug("Metriche dei backup raccolte")
            
        except Exception as e:
            logger.error(f"Errore durante la raccolta delle metriche dei backup: {e}")
    
    def collect_update_metrics(self):
        """Raccoglie metriche sugli aggiornamenti"""
        try:
            # Verifica se ci sono aggiornamenti disponibili
            if os.path.isdir(os.path.join(M4BOT_DIR, ".git")):
                os.chdir(M4BOT_DIR)
                
                # Aggiorna il repository remoto
                subprocess.run(["git", "fetch", "origin"], check=False, capture_output=True)
                
                # Controlla se ci sono aggiornamenti
                result = subprocess.run(
                    ["git", "log", "HEAD..origin/master", "--oneline"],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                update_available = len(result.stdout.strip()) > 0
                self.update_available.set(1 if update_available else 0)
                self.update_last_check.set(time.time())
            
            logger.debug("Metriche degli aggiornamenti raccolte")
            
        except Exception as e:
            logger.error(f"Errore durante la raccolta delle metriche degli aggiornamenti: {e}")
    
    def collect_version_info(self):
        """Raccoglie informazioni sulla versione di M4Bot"""
        try:
            # Leggi il file version.json se esiste
            version_file = os.path.join(M4BOT_DIR, "version.json")
            if os.path.exists(version_file):
                with open(version_file, 'r') as f:
                    version_info = json.load(f)
                
                self.m4bot_info.info({
                    'version': version_info.get('version', 'sconosciuta'),
                    'build_date': version_info.get('build_date', ''),
                    'commit': version_info.get('commit', ''),
                    'branch': version_info.get('branch', 'master')
                })
            else:
                # Se il file non esiste, ottieni informazioni dal git
                if os.path.isdir(os.path.join(M4BOT_DIR, ".git")):
                    os.chdir(M4BOT_DIR)
                    
                    # Ottieni l'hash del commit corrente
                    commit = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        capture_output=True,
                        text=True,
                        check=False
                    ).stdout.strip()
                    
                    # Ottieni il branch corrente
                    branch = subprocess.run(
                        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True,
                        text=True,
                        check=False
                    ).stdout.strip()
                    
                    self.m4bot_info.info({
                        'version': 'git',
                        'commit': commit,
                        'branch': branch
                    })
            
            logger.debug("Informazioni sulla versione raccolte")
            
        except Exception as e:
            logger.error(f"Errore durante la raccolta delle informazioni sulla versione: {e}")
    
    def collect_metrics(self):
        """Raccoglie tutte le metriche disponibili"""
        self.collect_system_metrics()
        self.collect_service_metrics()
        self.collect_app_metrics()
        self.collect_db_metrics()
        self.collect_backup_metrics()
        self.collect_update_metrics()
        self.collect_version_info()
        
        # Aggiorna timestamp ultimo aggiornamento
        self.last_update = datetime.datetime.now()
    
    def start(self):
        """Avvia l'esportatore"""
        # Avvia il server HTTP per esporre le metriche
        try:
            start_http_server(self.port, registry=self.registry)
            logger.info(f"Server HTTP avviato sulla porta {self.port}")
        except Exception as e:
            logger.error(f"Impossibile avviare il server HTTP: {e}")
            return False
        
        # Impostazione thread raccolta metriche
        self.running = True
        
        # Raccoglie le metriche immediatamente
        self.collect_metrics()
        
        # Avvia thread per raccolta periodica
        threading.Thread(target=self._metrics_collection_thread, daemon=True).start()
        
        return True
    
    def _metrics_collection_thread(self):
        """Thread per la raccolta periodica delle metriche"""
        while self.running:
            time.sleep(self.interval)
            
            try:
                self.collect_metrics()
                logger.debug(f"Metriche raccolte - prossima raccolta tra {self.interval} secondi")
            except Exception as e:
                logger.error(f"Errore durante la raccolta delle metriche: {e}")
    
    def stop(self):
        """Ferma l'esportatore"""
        self.running = False
        logger.info("Esportatore fermato")


def main():
    """Funzione principale"""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='M4Bot Prometheus Exporter')
    parser.add_argument('-p', '--port', type=int, default=DEFAULT_PORT,
                        help=f'Porta su cui esporre le metriche (default: {DEFAULT_PORT})')
    parser.add_argument('-i', '--interval', type=int, default=DEFAULT_INTERVAL,
                        help=f'Intervallo di raccolta in secondi (default: {DEFAULT_INTERVAL})')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Abilita logging verboso')
    
    args = parser.parse_args()
    
    # Imposta livello di logging
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    print(f"M4Bot Prometheus Exporter v1.0")
    print(f"Porta: {args.port}")
    print(f"Intervallo: {args.interval}s")
    print("Avvio in corso...")
    
    # Crea e avvia l'esportatore
    exporter = M4BotExporter(port=args.port, interval=args.interval)
    if exporter.start():
        print(f"Esportatore avviato. Metriche disponibili su http://localhost:{args.port}")
        
        try:
            # Mantieni il processo in esecuzione
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Interruzione rilevata, arresto in corso...")
            exporter.stop()
    else:
        print("Impossibile avviare l'esportatore")
        sys.exit(1)


if __name__ == "__main__":
    main() 