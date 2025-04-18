#!/usr/bin/env python3
"""
M4Bot - Modulo di Rotazione Automatica delle Chiavi di Sicurezza
Implementa la rotazione periodica e sicura delle credenziali critiche
"""

import os
import sys
import json
import time
import base64
import logging
import hashlib
import secrets
import datetime
import argparse
import subprocess
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename="/var/log/m4bot/key_rotation.log",
    filemode="a"
)

# Aggiungi handler per visualizzare anche su console
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
logging.getLogger('').addHandler(console)

logger = logging.getLogger("m4bot_key_rotation")

# Constants
M4BOT_DIR = os.environ.get("M4BOT_DIR", "/opt/m4bot")
CONFIG_DIR = os.path.join(M4BOT_DIR, "config")
KEY_HISTORY_FILE = os.path.join(CONFIG_DIR, ".key_history.json")
DEFAULT_ROTATION_DAYS = 30
ROTATION_HISTORY_SIZE = 5  # Numero di versioni precedenti da mantenere
CREDENTIAL_TYPES = ["token", "secret", "password", "api_key", "encryption_key"]

# Assicurati che la directory di log esista
os.makedirs("/var/log/m4bot", exist_ok=True)

class CredentialManager:
    """Gestore per la rotazione sicura delle credenziali"""
    
    def __init__(self, backup: bool = True, notify: bool = True):
        """
        Inizializza il gestore credenziali
        
        Args:
            backup: Se creare backup prima di modificare le credenziali
            notify: Se inviare notifiche dopo la rotazione
        """
        self.backup = backup
        self.notify = notify
        self.history = self._load_history()
        self.rotated_credentials = []
        
        # Mappa tra i tipi di credenziali e i pattern di file da cercare
        self.credential_file_patterns = {
            "token": ["config.json", "web/config.json", ".env", "web/.env"],
            "secret": ["config.json", "web/config.json", ".env", "web/.env"],
            "password": ["config/db.json", ".env", "web/.env"],
            "api_key": ["config.json", "web/config.json", ".env", "web/.env"],
            "encryption_key": ["config/security.json", ".env"]
        }
        
        logger.info("Credential Manager inizializzato")
    
    def _load_history(self) -> Dict[str, Any]:
        """
        Carica la cronologia delle rotazioni precedenti
        
        Returns:
            Dict: Cronologia delle rotazioni
        """
        if os.path.exists(KEY_HISTORY_FILE):
            try:
                with open(KEY_HISTORY_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Errore nel caricamento della cronologia: {e}")
                return {"last_rotation": None, "credentials": {}}
        else:
            return {"last_rotation": None, "credentials": {}}
    
    def _save_history(self) -> None:
        """Salva la cronologia delle rotazioni"""
        try:
            os.makedirs(os.path.dirname(KEY_HISTORY_FILE), exist_ok=True)
            
            # Imposta permessi restrittivi per il file
            with open(KEY_HISTORY_FILE, 'w') as f:
                json.dump(self.history, f, indent=2)
            
            # Imposta permessi 600 (solo lettura/scrittura per proprietario)
            os.chmod(KEY_HISTORY_FILE, 0o600)
            
            logger.debug("Cronologia rotazioni salvata")
        except Exception as e:
            logger.error(f"Errore nel salvataggio della cronologia: {e}")
    
    def _create_backup(self) -> str:
        """
        Crea un backup delle configurazioni prima della rotazione
        
        Returns:
            str: Path della directory di backup
        """
        try:
            backup_dir = os.path.join(M4BOT_DIR, "backups", f"keys_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}")
            os.makedirs(backup_dir, exist_ok=True)
            
            # Backup dei file di configurazione
            for pattern_list in self.credential_file_patterns.values():
                for pattern in pattern_list:
                    src_path = os.path.join(M4BOT_DIR, pattern)
                    if os.path.exists(src_path):
                        # Preserva la struttura delle directory
                        dst_dir = os.path.join(backup_dir, os.path.dirname(pattern))
                        os.makedirs(dst_dir, exist_ok=True)
                        
                        # Copia il file
                        dst_path = os.path.join(backup_dir, pattern)
                        with open(src_path, 'rb') as src, open(dst_path, 'wb') as dst:
                            dst.write(src.read())
                        
                        logger.debug(f"Backup creato per: {pattern}")
            
            logger.info(f"Backup creato in: {backup_dir}")
            return backup_dir
        except Exception as e:
            logger.error(f"Errore nella creazione del backup: {e}")
            return ""
    
    def _restart_services(self) -> bool:
        """
        Riavvia i servizi di M4Bot per applicare le nuove credenziali
        
        Returns:
            bool: True se riavvio completato con successo
        """
        try:
            # Lista dei servizi da riavviare
            services = ["m4bot.service", "m4bot-web.service"]
            
            for service in services:
                # Controlla se il servizio è attivo
                is_active_cmd = ["systemctl", "is-active", service]
                result = subprocess.run(is_active_cmd, capture_output=True, text=True)
                
                if result.stdout.strip() == "active":
                    logger.info(f"Riavvio del servizio: {service}")
                    
                    # Riavvia il servizio
                    restart_cmd = ["systemctl", "restart", service]
                    restart_result = subprocess.run(restart_cmd, capture_output=True, text=True)
                    
                    if restart_result.returncode != 0:
                        logger.error(f"Errore nel riavvio del servizio {service}: {restart_result.stderr}")
                        return False
                    
                    # Attendi un momento per il riavvio
                    time.sleep(2)
                    
                    # Verifica che il servizio sia ripartito
                    check_cmd = ["systemctl", "is-active", service]
                    check_result = subprocess.run(check_cmd, capture_output=True, text=True)
                    
                    if check_result.stdout.strip() != "active":
                        logger.error(f"Il servizio {service} non si è riavviato correttamente")
                        return False
                    
                    logger.info(f"Servizio {service} riavviato con successo")
                else:
                    logger.warning(f"Il servizio {service} non è attivo, non verrà riavviato")
            
            return True
        except Exception as e:
            logger.error(f"Errore nel riavvio dei servizi: {e}")
            return False
    
    def _send_notification(self, rotated_credentials: List[Dict[str, Any]]) -> None:
        """
        Invia una notifica sulle credenziali ruotate
        
        Args:
            rotated_credentials: Lista delle credenziali ruotate
        """
        if not self.notify:
            return
        
        try:
            # Log della notifica
            logger.info(f"Rotazione completata per {len(rotated_credentials)} credenziali")
            
            # Nella versione reale, qui si invierebbe anche una vera notifica
            # via email, webhook, o altro metodo configurato
            
            # Esempio di file notification log
            notification_log = os.path.join(M4BOT_DIR, "logs", "security_notifications.log")
            os.makedirs(os.path.dirname(notification_log), exist_ok=True)
            
            with open(notification_log, 'a') as f:
                f.write(f"[{datetime.datetime.now().isoformat()}] Rotazione chiavi completata\n")
                f.write(f"  - Credenziali ruotate: {len(rotated_credentials)}\n")
                for cred in rotated_credentials:
                    f.write(f"  - {cred['type']} in {cred['file']}\n")
                f.write("\n")
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica: {e}")
    
    def _generate_secure_credential(self, cred_type: str, length: int = 32) -> str:
        """
        Genera una nuova credenziale sicura
        
        Args:
            cred_type: Tipo di credenziale
            length: Lunghezza della credenziale
            
        Returns:
            str: Nuova credenziale
        """
        # Genera token con entropia adeguata in base al tipo
        if cred_type in ["token", "secret", "encryption_key"]:
            # Token complessi con mix di caratteri
            new_cred = secrets.token_urlsafe(length)
        elif cred_type == "password":
            # Password con caratteri speciali, numeri, maiuscole, minuscole
            chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()-_=+[]{}|;:,.<>?/"
            new_cred = ''.join(secrets.choice(chars) for _ in range(length))
        elif cred_type == "api_key":
            # API key in formato esadecimale
            new_cred = secrets.token_hex(length)
        else:
            # Formato generico per altri tipi
            new_cred = secrets.token_urlsafe(length)
        
        return new_cred
    
    def _update_json_file(self, file_path: str, cred_type: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Aggiorna una credenziale in un file JSON
        
        Args:
            file_path: Percorso del file JSON
            cred_type: Tipo di credenziale da cercare
            
        Returns:
            Tuple: (successo, dettagli)
        """
        try:
            # Leggi il file JSON
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            # Pattern di chiavi da cercare
            key_patterns = []
            if cred_type == "token":
                key_patterns = ["token", "auth_token", "bearer_token", "access_token", "jwt_token"]
            elif cred_type == "secret":
                key_patterns = ["secret", "secret_key", "jwt_secret", "app_secret", "client_secret"]
            elif cred_type == "password":
                key_patterns = ["password", "db_password", "admin_password", "user_password"]
            elif cred_type == "api_key":
                key_patterns = ["api_key", "apikey", "key", "client_key"]
            elif cred_type == "encryption_key":
                key_patterns = ["encryption_key", "crypto_key", "cipher_key"]
            
            updated = False
            old_value = None
            field_path = None
            
            # Funzione ricorsiva per trovare e aggiornare la credenziale
            def update_recursive(obj, path=""):
                nonlocal updated, old_value, field_path
                
                if isinstance(obj, dict):
                    for k, v in list(obj.items()):
                        current_path = f"{path}.{k}" if path else k
                        
                        # Se la chiave corrisponde a uno dei pattern
                        if any(pattern in k.lower() for pattern in key_patterns):
                            if isinstance(v, str) and len(v) >= 8:  # Solo valori stringa di lunghezza adeguata
                                old_value = v
                                new_value = self._generate_secure_credential(cred_type)
                                obj[k] = new_value
                                updated = True
                                field_path = current_path
                                
                                # Registra la credenziale ruotata
                                self.rotated_credentials.append({
                                    "type": cred_type,
                                    "file": file_path,
                                    "field": current_path
                                })
                                
                                # Salva nella cronologia
                                if cred_type not in self.history["credentials"]:
                                    self.history["credentials"][cred_type] = {}
                                
                                # Codifica hash dell'old value per riferimento futuro
                                old_hash = hashlib.sha256(old_value.encode()).hexdigest()
                                
                                if current_path not in self.history["credentials"][cred_type]:
                                    self.history["credentials"][cred_type][current_path] = []
                                
                                # Mantieni la cronologia limitata
                                history_entries = self.history["credentials"][cred_type][current_path]
                                history_entries.append({
                                    "date": datetime.datetime.now().isoformat(),
                                    "file": file_path,
                                    "hash": old_hash
                                })
                                
                                # Limita la dimensione della cronologia
                                if len(history_entries) > ROTATION_HISTORY_SIZE:
                                    self.history["credentials"][cred_type][current_path] = history_entries[-ROTATION_HISTORY_SIZE:]
                        
                        # Continua la ricerca ricorsiva
                        elif isinstance(v, (dict, list)):
                            update_recursive(v, current_path)
                
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        current_path = f"{path}[{i}]"
                        if isinstance(item, (dict, list)):
                            update_recursive(item, current_path)
            
            # Avvia l'aggiornamento ricorsivo
            update_recursive(data)
            
            # Se è stata trovata e aggiornata una credenziale
            if updated:
                # Scrivi il file JSON aggiornato
                with open(file_path, 'w') as f:
                    json.dump(data, f, indent=2)
                
                logger.info(f"Aggiornata credenziale {cred_type} in {file_path} ({field_path})")
                return True, {
                    "file": file_path,
                    "type": cred_type,
                    "field": field_path,
                    "old_hash": hashlib.sha256(old_value.encode()).hexdigest() if old_value else None
                }
            
            return False, None
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento del file JSON {file_path}: {e}")
            return False, None
    
    def _update_env_file(self, file_path: str, cred_type: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Aggiorna una credenziale in un file .env
        
        Args:
            file_path: Percorso del file .env
            cred_type: Tipo di credenziale da cercare
            
        Returns:
            Tuple: (successo, dettagli)
        """
        try:
            if not os.path.exists(file_path):
                return False, None
            
            # Leggi il file .env
            with open(file_path, 'r') as f:
                lines = f.readlines()
            
            # Pattern di variabili da cercare
            var_patterns = []
            if cred_type == "token":
                var_patterns = ["TOKEN", "AUTH_TOKEN", "BEARER_TOKEN", "ACCESS_TOKEN", "JWT_TOKEN"]
            elif cred_type == "secret":
                var_patterns = ["SECRET", "SECRET_KEY", "JWT_SECRET", "APP_SECRET", "CLIENT_SECRET"]
            elif cred_type == "password":
                var_patterns = ["PASSWORD", "DB_PASSWORD", "ADMIN_PASSWORD", "USER_PASSWORD"]
            elif cred_type == "api_key":
                var_patterns = ["API_KEY", "APIKEY", "KEY", "CLIENT_KEY"]
            elif cred_type == "encryption_key":
                var_patterns = ["ENCRYPTION_KEY", "CRYPTO_KEY", "CIPHER_KEY"]
            
            updated = False
            old_value = None
            var_name = None
            updated_lines = []
            
            for line in lines:
                line = line.strip()
                # Salta righe vuote o commenti
                if not line or line.startswith('#'):
                    updated_lines.append(line)
                    continue
                
                # Cerca variabili nel formato VAR=value
                if '=' in line:
                    var, value = line.split('=', 1)
                    var = var.strip()
                    value = value.strip()
                    
                    # Rimuovi virgolette se presenti
                    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    
                    # Se la variabile corrisponde a uno dei pattern e il valore è abbastanza lungo
                    if any(pattern in var.upper() for pattern in var_patterns) and len(value) >= 8:
                        old_value = value
                        new_value = self._generate_secure_credential(cred_type)
                        
                        # Determina se usare virgolette e quali
                        if (line.split('=', 1)[1].strip().startswith('"')):
                            updated_lines.append(f"{var}=\"{new_value}\"")
                        elif (line.split('=', 1)[1].strip().startswith("'")):
                            updated_lines.append(f"{var}='{new_value}'")
                        else:
                            updated_lines.append(f"{var}={new_value}")
                        
                        updated = True
                        var_name = var
                        
                        # Registra la credenziale ruotata
                        self.rotated_credentials.append({
                            "type": cred_type,
                            "file": file_path,
                            "field": var
                        })
                        
                        # Salva nella cronologia
                        if cred_type not in self.history["credentials"]:
                            self.history["credentials"][cred_type] = {}
                        
                        # Codifica hash dell'old value per riferimento futuro
                        old_hash = hashlib.sha256(old_value.encode()).hexdigest()
                        
                        if var not in self.history["credentials"][cred_type]:
                            self.history["credentials"][cred_type][var] = []
                        
                        # Mantieni la cronologia limitata
                        history_entries = self.history["credentials"][cred_type][var]
                        history_entries.append({
                            "date": datetime.datetime.now().isoformat(),
                            "file": file_path,
                            "hash": old_hash
                        })
                        
                        # Limita la dimensione della cronologia
                        if len(history_entries) > ROTATION_HISTORY_SIZE:
                            self.history["credentials"][cred_type][var] = history_entries[-ROTATION_HISTORY_SIZE:]
                    else:
                        updated_lines.append(line)
                else:
                    updated_lines.append(line)
            
            # Se è stata trovata e aggiornata una credenziale
            if updated:
                # Scrivi il file .env aggiornato
                with open(file_path, 'w') as f:
                    f.write('\n'.join(updated_lines) + '\n')
                
                logger.info(f"Aggiornata credenziale {cred_type} in {file_path} ({var_name})")
                return True, {
                    "file": file_path,
                    "type": cred_type,
                    "field": var_name,
                    "old_hash": hashlib.sha256(old_value.encode()).hexdigest() if old_value else None
                }
            
            return False, None
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento del file .env {file_path}: {e}")
            return False, None
    
    def update_credential(self, cred_type: str, file_pattern: str) -> None:
        """
        Aggiorna una specifica credenziale in un file
        
        Args:
            cred_type: Tipo di credenziale da aggiornare
            file_pattern: Pattern del file da aggiornare
        """
        file_path = os.path.join(M4BOT_DIR, file_pattern)
        
        if not os.path.exists(file_path):
            logger.warning(f"File non trovato: {file_path}")
            return
        
        logger.info(f"Tentativo di aggiornamento credenziale {cred_type} in {file_path}")
        
        # Determina il metodo di aggiornamento in base al tipo di file
        if file_path.endswith('.json'):
            success, details = self._update_json_file(file_path, cred_type)
        elif file_path.endswith('.env'):
            success, details = self._update_env_file(file_path, cred_type)
        else:
            logger.warning(f"Tipo di file non supportato: {file_path}")
            return
    
    def rotate_all_credentials(self) -> None:
        """Esegue la rotazione di tutte le credenziali configurate"""
        logger.info("Avvio rotazione di tutte le credenziali")
        
        # Crea backup se abilitato
        backup_path = ""
        if self.backup:
            backup_path = self._create_backup()
            if not backup_path:
                logger.error("Rotazione annullata: impossibile creare il backup")
                return
        
        # Resettare la lista delle credenziali ruotate
        self.rotated_credentials = []
        
        # Processa ogni tipo di credenziale
        for cred_type in CREDENTIAL_TYPES:
            for file_pattern in self.credential_file_patterns.get(cred_type, []):
                self.update_credential(cred_type, file_pattern)
        
        # Aggiorna data ultima rotazione
        self.history["last_rotation"] = datetime.datetime.now().isoformat()
        self._save_history()
        
        # Riavvia i servizi per applicare le nuove credenziali
        if self.rotated_credentials:
            if not self._restart_services():
                logger.error("Errore nel riavvio dei servizi dopo la rotazione")
            
            # Invia notifica
            self._send_notification(self.rotated_credentials)
            
            logger.info(f"Rotazione completata: {len(self.rotated_credentials)} credenziali aggiornate")
        else:
            logger.info("Nessuna credenziale da aggiornare")
    
    def should_rotate(self) -> bool:
        """
        Verifica se è necessario eseguire la rotazione delle credenziali
        in base all'ultima data di rotazione
        
        Returns:
            bool: True se è necessaria la rotazione
        """
        if not self.history["last_rotation"]:
            logger.info("Prima rotazione: nessuna rotazione precedente trovata")
            return True
        
        try:
            last_date = datetime.datetime.fromisoformat(self.history["last_rotation"])
            days_since = (datetime.datetime.now() - last_date).days
            
            if days_since >= DEFAULT_ROTATION_DAYS:
                logger.info(f"Rotazione necessaria: {days_since} giorni dall'ultima rotazione")
                return True
            else:
                logger.info(f"Rotazione non necessaria: {days_since} giorni dall'ultima rotazione (limite: {DEFAULT_ROTATION_DAYS})")
                return False
        except Exception as e:
            logger.error(f"Errore nel calcolo della data di rotazione: {e}")
            return True
    
    def check_credentials(self) -> Dict[str, Any]:
        """
        Verifica lo stato di tutte le credenziali
        
        Returns:
            Dict: Stato delle credenziali
        """
        result = {
            "status": "ok",
            "last_rotation": self.history["last_rotation"],
            "days_since_rotation": None,
            "credentials": {}
        }
        
        # Calcola giorni dall'ultima rotazione
        if self.history["last_rotation"]:
            try:
                last_date = datetime.datetime.fromisoformat(self.history["last_rotation"])
                days_since = (datetime.datetime.now() - last_date).days
                result["days_since_rotation"] = days_since
                
                if days_since >= DEFAULT_ROTATION_DAYS:
                    result["status"] = "rotation_needed"
            except Exception:
                pass
        else:
            result["status"] = "never_rotated"
        
        # Controlla ogni tipo di credenziale
        for cred_type in CREDENTIAL_TYPES:
            cred_status = {
                "files_checked": 0,
                "credentials_found": 0,
                "rotatable": True
            }
            
            for file_pattern in self.credential_file_patterns.get(cred_type, []):
                file_path = os.path.join(M4BOT_DIR, file_pattern)
                
                if os.path.exists(file_path):
                    cred_status["files_checked"] += 1
                    
                    # Verifica se ci sono credenziali nel file
                    if file_path.endswith('.json'):
                        try:
                            with open(file_path, 'r') as f:
                                data = json.load(f)
                            
                            # Cerca pattern di credenziali
                            key_patterns = []
                            if cred_type == "token":
                                key_patterns = ["token", "auth_token", "bearer_token", "access_token", "jwt_token"]
                            elif cred_type == "secret":
                                key_patterns = ["secret", "secret_key", "jwt_secret", "app_secret", "client_secret"]
                            elif cred_type == "password":
                                key_patterns = ["password", "db_password", "admin_password", "user_password"]
                            elif cred_type == "api_key":
                                key_patterns = ["api_key", "apikey", "key", "client_key"]
                            elif cred_type == "encryption_key":
                                key_patterns = ["encryption_key", "crypto_key", "cipher_key"]
                            
                            def search_recursive(obj, found=0):
                                if isinstance(obj, dict):
                                    for k, v in obj.items():
                                        if any(pattern in k.lower() for pattern in key_patterns):
                                            if isinstance(v, str) and len(v) >= 8:
                                                found += 1
                                        elif isinstance(v, (dict, list)):
                                            found += search_recursive(v)
                                elif isinstance(obj, list):
                                    for item in obj:
                                        if isinstance(item, (dict, list)):
                                            found += search_recursive(item)
                                return found
                            
                            cred_count = search_recursive(data)
                            cred_status["credentials_found"] += cred_count
                        except Exception as e:
                            logger.error(f"Errore nell'analisi del file JSON {file_path}: {e}")
                    
                    elif file_path.endswith('.env'):
                        try:
                            with open(file_path, 'r') as f:
                                lines = f.readlines()
                            
                            var_patterns = []
                            if cred_type == "token":
                                var_patterns = ["TOKEN", "AUTH_TOKEN", "BEARER_TOKEN", "ACCESS_TOKEN", "JWT_TOKEN"]
                            elif cred_type == "secret":
                                var_patterns = ["SECRET", "SECRET_KEY", "JWT_SECRET", "APP_SECRET", "CLIENT_SECRET"]
                            elif cred_type == "password":
                                var_patterns = ["PASSWORD", "DB_PASSWORD", "ADMIN_PASSWORD", "USER_PASSWORD"]
                            elif cred_type == "api_key":
                                var_patterns = ["API_KEY", "APIKEY", "KEY", "CLIENT_KEY"]
                            elif cred_type == "encryption_key":
                                var_patterns = ["ENCRYPTION_KEY", "CRYPTO_KEY", "CIPHER_KEY"]
                            
                            cred_count = 0
                            for line in lines:
                                line = line.strip()
                                if not line or line.startswith('#'):
                                    continue
                                
                                if '=' in line:
                                    var, value = line.split('=', 1)
                                    var = var.strip()
                                    value = value.strip()
                                    
                                    # Rimuovi virgolette se presenti
                                    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
                                        value = value[1:-1]
                                    
                                    if any(pattern in var.upper() for pattern in var_patterns) and len(value) >= 8:
                                        cred_count += 1
                            
                            cred_status["credentials_found"] += cred_count
                        except Exception as e:
                            logger.error(f"Errore nell'analisi del file .env {file_path}: {e}")
            
            # Aggiorna stato credenziale
            if cred_status["credentials_found"] == 0:
                cred_status["rotatable"] = False
            
            result["credentials"][cred_type] = cred_status
        
        return result


def rotate_credentials(force: bool = False, backup: bool = True, notify: bool = True, skip_services: bool = False) -> bool:
    """
    Esegue la rotazione delle credenziali
    
    Args:
        force: Se forzare la rotazione anche se non necessaria
        backup: Se creare backup prima della rotazione
        notify: Se inviare notifiche
        skip_services: Se saltare il riavvio dei servizi
        
    Returns:
        bool: True se la rotazione è avvenuta con successo
    """
    try:
        # Inizializza il gestore credenziali
        credential_manager = CredentialManager(backup=backup, notify=notify)
        
        # Verifica se è necessaria la rotazione
        if not force and not credential_manager.should_rotate():
            logger.info("Rotazione saltata: non necessaria al momento")
            return True
        
        # Esegui la rotazione
        credential_manager.rotate_all_credentials()
        
        return True
    except Exception as e:
        logger.error(f"Errore durante la rotazione delle credenziali: {e}")
        return False


def main():
    """Funzione principale"""
    parser = argparse.ArgumentParser(description='M4Bot - Rotazione Automatica delle Chiavi di Sicurezza')
    parser.add_argument('-f', '--force', action='store_true', help='Forza la rotazione anche se non necessaria')
    parser.add_argument('--no-backup', action='store_true', help='Non creare backup prima della rotazione')
    parser.add_argument('--no-notify', action='store_true', help='Non inviare notifiche')
    parser.add_argument('--skip-services', action='store_true', help='Non riavviare i servizi')
    parser.add_argument('-c', '--check', action='store_true', help='Controlla lo stato delle credenziali senza eseguire la rotazione')
    
    args = parser.parse_args()
    
    # Controlla directory M4Bot
    if not os.path.isdir(M4BOT_DIR):
        print(f"Errore: directory M4Bot non trovata: {M4BOT_DIR}")
        print("Imposta la variabile d'ambiente M4BOT_DIR o modifica lo script")
        return 1
    
    if args.check:
        # Modalità controllo: verifica lo stato delle credenziali
        credential_manager = CredentialManager(backup=False, notify=False)
        status = credential_manager.check_credentials()
        
        print("\nStato Credenziali M4Bot")
        print("=======================")
        print(f"Stato: {status['status']}")
        
        if status['last_rotation']:
            print(f"Ultima rotazione: {status['last_rotation']}")
            print(f"Giorni dall'ultima rotazione: {status['days_since_rotation']}")
        else:
            print("Ultima rotazione: Mai")
        
        print("\nCredenziali trovate:")
        for cred_type, details in status['credentials'].items():
            print(f"  - {cred_type}: {details['credentials_found']} credenziali in {details['files_checked']} file")
        
        if status['status'] == "rotation_needed":
            print("\nRisultato: È consigliata la rotazione delle credenziali")
        elif status['status'] == "never_rotated":
            print("\nRisultato: Le credenziali non sono mai state ruotate")
        else:
            print("\nRisultato: Le credenziali sono aggiornate")
        
        return 0
    else:
        # Modalità rotazione
        print("M4Bot - Rotazione Automatica delle Chiavi di Sicurezza")
        print("====================================================")
        print(f"Directory M4Bot: {M4BOT_DIR}")
        print(f"Forzare rotazione: {'Sì' if args.force else 'No'}")
        print(f"Creare backup: {'No' if args.no_backup else 'Sì'}")
        print(f"Inviare notifiche: {'No' if args.no_notify else 'Sì'}")
        print(f"Riavviare servizi: {'No' if args.skip_services else 'Sì'}")
        print("====================================================")
        
        success = rotate_credentials(
            force=args.force,
            backup=not args.no_backup,
            notify=not args.no_notify,
            skip_services=args.skip_services
        )
        
        if success:
            print("Rotazione completata con successo")
            return 0
        else:
            print("Errore durante la rotazione")
            return 1


if __name__ == "__main__":
    sys.exit(main()) 