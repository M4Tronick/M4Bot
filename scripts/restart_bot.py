#!/usr/bin/env python
"""
Script per riavviare il bot M4Bot in caso di problemi o disconnessioni.
Questo script viene eseguito come processo separato per garantire che possa
funzionare anche se il processo principale del bot è bloccato.
"""

import os
import sys
import time
import signal
import logging
import subprocess
import json
import socket
import requests
from datetime import datetime, timedelta

# Configura logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/restart.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("restart_bot")

# Determina il percorso del progetto
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Percorso del file principale del bot
BOT_SCRIPT = os.path.join(PROJECT_ROOT, "bot", "main.py")

# File di configurazione
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config.json")

# File di PID per tenere traccia del processo del bot
PID_FILE = os.path.join(PROJECT_ROOT, "bot.pid")

# File di lock per evitare riavvii multipli simultanei
LOCK_FILE = os.path.join(PROJECT_ROOT, "restart.lock")

# Carica configurazione se esiste
config = {
    "max_restart_attempts": 3,
    "restart_cooldown": 60,  # secondi
    "heartbeat_timeout": 30,  # secondi
    "api_key": "",
    "api_url": "http://localhost:8000"
}

try:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            loaded_config = json.load(f)
            config.update(loaded_config.get("restart", {}))
except Exception as e:
    logger.error(f"Errore nel caricamento della configurazione: {e}")

def is_process_running(pid):
    """Verifica se un processo è in esecuzione tramite il suo PID."""
    try:
        # Verifica il processo in modo diverso a seconda della piattaforma
        if sys.platform == "win32":
            # Su Windows, prova ad aprire il processo (genera eccezione se non esiste)
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(1, False, pid)
            if handle == 0:
                return False
            kernel32.CloseHandle(handle)
            return True
        else:
            # Su Linux/Unix, invia segnale 0 (non fa nulla, ma verifica esistenza)
            os.kill(pid, 0)
            return True
    except (OSError, ImportError, ValueError):
        return False

def get_bot_pid():
    """Restituisce il PID del bot salvato nel file PID."""
    try:
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                return int(f.read().strip())
    except (ValueError, OSError) as e:
        logger.error(f"Errore nella lettura del PID: {e}")
    return None

def kill_bot(pid):
    """Termina il processo del bot."""
    logger.info(f"Tentativo di terminare il processo bot con PID {pid}")
    try:
        if sys.platform == "win32":
            # Windows
            subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False)
        else:
            # Linux/Unix
            os.kill(pid, signal.SIGTERM)
            # Attendi che il processo termini
            time.sleep(5)
            # Se ancora in esecuzione, forza la chiusura
            if is_process_running(pid):
                os.kill(pid, signal.SIGKILL)
        
        # Attendi che il processo termini
        timeout = 10
        while timeout > 0 and is_process_running(pid):
            time.sleep(1)
            timeout -= 1
        
        # Verifica se il processo è stato realmente terminato
        if is_process_running(pid):
            logger.error(f"Impossibile terminare il processo {pid}")
            return False
        
        logger.info(f"Processo {pid} terminato con successo")
        return True
    except Exception as e:
        logger.error(f"Errore durante la terminazione del processo: {e}")
        return False

def start_bot():
    """Avvia il processo del bot."""
    logger.info("Avvio del bot...")
    try:
        # Crea comando in base al sistema operativo
        if sys.platform == "win32":
            command = ["python", BOT_SCRIPT]
            # Avvia il processo senza collegare stdin/stdout
            process = subprocess.Popen(
                command,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        else:
            command = ["python3", BOT_SCRIPT]
            # Avvia il processo in una nuova sessione
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
        
        # Salva il PID del nuovo processo
        with open(PID_FILE, 'w') as f:
            f.write(str(process.pid))
        
        logger.info(f"Bot avviato con PID {process.pid}")
        return True
    except Exception as e:
        logger.error(f"Errore durante l'avvio del bot: {e}")
        return False

def check_heartbeat():
    """
    Controlla l'ultimo heartbeat del bot per verificare che sia ancora in esecuzione.
    Restituisce True se il bot è attivo, False altrimenti.
    """
    try:
        # Verifica se possiamo contattare il server web
        response = requests.get(
            f"{config['api_url']}/api/status/bot",
            headers={"X-API-Key": config["api_key"]},
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get("online", False)
        
        logger.warning(f"Risposta dal server non valida: {response.status_code}")
        return False
    except Exception as e:
        logger.error(f"Errore nel controllo del heartbeat: {e}")
        return False

def acquire_lock():
    """
    Acquisisce un lock per evitare riavvii multipli simultanei.
    Restituisce True se il lock è stato acquisito, False altrimenti.
    """
    try:
        if os.path.exists(LOCK_FILE):
            # Verifica se il lock è vecchio (più di 10 minuti)
            lock_time = os.path.getmtime(LOCK_FILE)
            now = time.time()
            if (now - lock_time) < 600:  # 10 minuti
                logger.warning("Lock di riavvio già acquisito da un altro processo")
                return False
            
            # Lock vecchio, lo rimuoviamo
            logger.warning("Rimozione lock di riavvio scaduto")
            os.remove(LOCK_FILE)
        
        # Crea il file di lock
        with open(LOCK_FILE, 'w') as f:
            f.write(str(datetime.now()))
        
        logger.info("Lock di riavvio acquisito")
        return True
    except Exception as e:
        logger.error(f"Errore nell'acquisizione del lock: {e}")
        return False

def release_lock():
    """Rilascia il lock di riavvio."""
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
        logger.info("Lock di riavvio rilasciato")
    except Exception as e:
        logger.error(f"Errore nel rilascio del lock: {e}")

def notify_restart(success=True):
    """Notifica il riavvio al server web."""
    try:
        data = {
            "status": "success" if success else "failed",
            "timestamp": datetime.now().isoformat(),
            "details": {
                "hostname": socket.gethostname(),
                "script_version": "1.0.0",
                "pid": os.getpid()
            }
        }
        
        response = requests.post(
            f"{config['api_url']}/api/bot/restart-notification",
            headers={
                "X-API-Key": config["api_key"],
                "Content-Type": "application/json"
            },
            json=data,
            timeout=5
        )
        
        if response.status_code != 200:
            logger.warning(f"Errore nella notifica di riavvio: {response.status_code}")
    except Exception as e:
        logger.error(f"Errore nell'invio della notifica di riavvio: {e}")

def main():
    """Funzione principale per riavviare il bot."""
    logger.info("Script di riavvio avviato")
    
    # Acquisici il lock per evitare riavvii multipli
    if not acquire_lock():
        logger.error("Impossibile acquisire il lock, uscita")
        return 1
    
    try:
        restart_attempts = 0
        max_attempts = config["max_restart_attempts"]
        
        while restart_attempts < max_attempts:
            restart_attempts += 1
            logger.info(f"Tentativo di riavvio {restart_attempts}/{max_attempts}")
            
            # Ottieni il PID attuale del bot
            bot_pid = get_bot_pid()
            
            # Controlla se il bot è in esecuzione
            if bot_pid and is_process_running(bot_pid):
                logger.info(f"Bot trovato in esecuzione con PID {bot_pid}")
                
                # Verifica se il bot è attivo tramite heartbeat
                if check_heartbeat():
                    logger.info("Il bot è attivo, riavvio non necessario")
                    notify_restart(success=True)
                    return 0
                
                # Bot in esecuzione ma non risponde, terminalo
                logger.warning("Bot in esecuzione ma non risponde, tentativo di terminazione")
                kill_bot(bot_pid)
            else:
                logger.warning("Bot non in esecuzione o PID non valido")
            
            # Avvia il bot
            if start_bot():
                logger.info("Bot riavviato con successo")
                # Attendi un po' per permettere al bot di stabilizzarsi
                time.sleep(10)
                
                # Verifica che il bot sia attivo
                if check_heartbeat():
                    logger.info("Heartbeat del bot rilevato, riavvio completato con successo")
                    notify_restart(success=True)
                    return 0
                
                logger.warning("Bot avviato ma heartbeat non rilevato, potrebbe essere in fase di avvio")
                # Attendiamo un po' più a lungo
                time.sleep(20)
                
                if check_heartbeat():
                    logger.info("Heartbeat del bot rilevato dopo attesa, riavvio completato con successo")
                    notify_restart(success=True)
                    return 0
            
            logger.error(f"Tentativo di riavvio {restart_attempts} fallito")
            
            # Attendi prima del prossimo tentativo
            if restart_attempts < max_attempts:
                cooldown = config["restart_cooldown"]
                logger.info(f"Attesa {cooldown} secondi prima del prossimo tentativo...")
                time.sleep(cooldown)
        
        logger.critical(f"Tutti i {max_attempts} tentativi di riavvio sono falliti!")
        notify_restart(success=False)
        return 1
    
    finally:
        # Rilascia sempre il lock
        release_lock()

if __name__ == "__main__":
    try:
        # Crea directory per i log se non esiste
        os.makedirs(os.path.join(PROJECT_ROOT, "logs"), exist_ok=True)
        
        # Esegui la procedura di riavvio
        sys.exit(main())
    except Exception as e:
        logger.critical(f"Errore fatale durante il riavvio: {e}", exc_info=True)
        sys.exit(1) 