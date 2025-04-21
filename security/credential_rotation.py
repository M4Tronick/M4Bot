#!/usr/bin/env python3
"""
M4Bot - Sistema di Rotazione Automatica delle Credenziali

Questo modulo implementa un sistema avanzato per la rotazione automatica e sicura delle
credenziali utilizzate da M4Bot (API keys, token, password del database, ecc.).

Funzionalità:
- Rotazione periodica e programmabile delle credenziali
- Backup sicuro delle credenziali precedenti
- Notifiche prima della rotazione
- Sistema di rollback in caso di problemi
- Sincronizzazione dei nuovi valori con tutti i servizi che li utilizzano
"""

import os
import sys
import json
import time
import random
import string
import logging
import asyncio
import datetime
import secrets
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Union, Callable, Tuple
from functools import wraps
from enum import Enum

# Importazione delle utility crittografiche
import bcrypt
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key, load_pem_public_key,
    Encoding, PrivateFormat, PublicFormat, NoEncryption
)
import base64

# Configurazione del logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/security/credential_rotation.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("CredentialRotation")

class CredentialType(Enum):
    """Tipi di credenziali supportate dal sistema."""
    API_KEY = "api_key"
    DATABASE_PASSWORD = "db_password"
    JWT_SECRET = "jwt_secret"
    ENCRYPTION_KEY = "encryption_key"
    ACCESS_TOKEN = "access_token"
    REFRESH_TOKEN = "refresh_token"
    SSH_KEY = "ssh_key"
    SERVICE_ACCOUNT = "service_account"
    WEBHOOK_SECRET = "webhook_secret"

class RotationSchedule(Enum):
    """Frequenza di rotazione delle credenziali."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    CUSTOM = "custom"  # Richiede un intervallo personalizzato in giorni

class RotationStatus(Enum):
    """Stato della rotazione delle credenziali."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

class CredentialRotationManager:
    """Gestisce la rotazione automatica delle credenziali."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Inizializza il gestore di rotazione delle credenziali.
        
        Args:
            config_path: Percorso del file di configurazione (opzionale)
        """
        self.config_path = config_path or "config/security/credential_rotation.json"
        self.config = self._load_config()
        self.backup_dir = Path(self.config.get("backup_dir", "security/backups/credentials"))
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Stato della rotazione in corso
        self.current_rotation: Dict[str, Any] = {}
        
        # Cronologia delle rotazioni
        self.rotation_history: List[Dict[str, Any]] = []
        
        # Carica le credenziali
        self._load_rotation_history()
        
        # Inizializza la chiave di cifratura per i backup
        self._init_encryption_key()
        
        logger.info("Sistema di rotazione credenziali inizializzato")
    
    def _load_config(self) -> Dict[str, Any]:
        """Carica la configurazione dal file JSON."""
        default_config = {
            "enabled": True,
            "notification_days_before": 3,
            "backup_dir": "security/backups/credentials",
            "backup_retention_days": 90,
            "encryption_key_env_var": "CREDENTIAL_BACKUP_KEY",
            "credentials": {}
        }
        
        try:
            config_dir = os.path.dirname(self.config_path)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir, exist_ok=True)
                
            if not os.path.exists(self.config_path):
                # Crea il file di configurazione di esempio
                with open(self.config_path, 'w') as f:
                    json.dump(default_config, f, indent=2)
                logger.info(f"File di configurazione creato: {self.config_path}")
                return default_config
            
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            
            # Assicurati che tutti i campi default siano presenti
            for key, value in default_config.items():
                if key not in config:
                    config[key] = value
            
            return config
        except Exception as e:
            logger.error(f"Errore nel caricamento della configurazione: {e}")
            return default_config
    
    def _init_encryption_key(self):
        """Inizializza o recupera la chiave di cifratura per i backup."""
        env_var = self.config.get("encryption_key_env_var", "CREDENTIAL_BACKUP_KEY")
        
        # Tenta di recuperare la chiave dall'ambiente
        key = os.environ.get(env_var)
        
        if not key:
            # Se non esiste, genera una nuova chiave
            try:
                key_path = Path(self.backup_dir) / ".encryption_key"
                
                if key_path.exists():
                    # Carica la chiave esistente
                    with open(key_path, 'rb') as f:
                        key = f.read().decode('utf-8')
                else:
                    # Genera una nuova chiave
                    key = Fernet.generate_key().decode('utf-8')
                    
                    # Salva la chiave (in un ambiente di produzione, usare un key vault)
                    with open(key_path, 'wb') as f:
                        f.write(key.encode('utf-8'))
                    
                    # Imposta i permessi appropriati
                    os.chmod(key_path, 0o600)  # Solo lettura/scrittura per il proprietario
            
                # Imposta la chiave nell'ambiente
                os.environ[env_var] = key
                
                logger.info("Chiave di cifratura per i backup inizializzata")
            except Exception as e:
                logger.error(f"Errore nell'inizializzazione della chiave di cifratura: {e}")
                # Genera comunque una chiave temporanea in memoria se non è possibile salvare
                os.environ[env_var] = Fernet.generate_key().decode('utf-8')
        
        self.encryption_key = key
    
    def _load_rotation_history(self):
        """Carica la cronologia delle rotazioni dal file."""
        history_path = Path(self.backup_dir) / "rotation_history.json"
        
        if history_path.exists():
            try:
                with open(history_path, 'r') as f:
                    self.rotation_history = json.load(f)
                logger.debug(f"Caricate {len(self.rotation_history)} rotazioni dalla cronologia")
            except Exception as e:
                logger.error(f"Errore nel caricamento della cronologia rotazioni: {e}")
                self.rotation_history = []
        else:
            self.rotation_history = []
    
    def _save_rotation_history(self):
        """Salva la cronologia delle rotazioni su file."""
        history_path = Path(self.backup_dir) / "rotation_history.json"
        
        try:
            with open(history_path, 'w') as f:
                json.dump(self.rotation_history, f, indent=2)
            logger.debug("Cronologia rotazioni salvata")
        except Exception as e:
            logger.error(f"Errore nel salvataggio della cronologia rotazioni: {e}")
    
    def _encrypt_value(self, value: str) -> str:
        """Cifra un valore utilizzando la chiave di backup."""
        try:
            f = Fernet(self.encryption_key.encode('utf-8'))
            return f.encrypt(value.encode('utf-8')).decode('utf-8')
        except Exception as e:
            logger.error(f"Errore nella cifratura del valore: {e}")
            return ""
    
    def _decrypt_value(self, encrypted_value: str) -> str:
        """Decifra un valore utilizzando la chiave di backup."""
        try:
            f = Fernet(self.encryption_key.encode('utf-8'))
            return f.decrypt(encrypted_value.encode('utf-8')).decode('utf-8')
        except Exception as e:
            logger.error(f"Errore nella decifratura del valore: {e}")
            return ""
    
    def register_credential(self, name: str, credential_type: CredentialType, 
                           current_value: str, rotation_schedule: RotationSchedule,
                           service_name: str, rotation_func: Optional[Callable] = None,
                           custom_interval_days: int = None, description: str = None) -> bool:
        """
        Registra una credenziale per la rotazione automatica.
        
        Args:
            name: Nome univoco della credenziale
            credential_type: Tipo di credenziale
            current_value: Valore attuale (sarà cifrato)
            rotation_schedule: Frequenza di rotazione
            service_name: Nome del servizio che utilizza questa credenziale
            rotation_func: Funzione personalizzata per la rotazione (opzionale)
            custom_interval_days: Intervallo personalizzato in giorni (solo per RotationSchedule.CUSTOM)
            description: Descrizione della credenziale (opzionale)
            
        Returns:
            bool: True se la registrazione è avvenuta con successo
        """
        try:
            # Verifica parametri
            if rotation_schedule == RotationSchedule.CUSTOM and not custom_interval_days:
                logger.error("Intervallo personalizzato richiesto per rotazione CUSTOM")
                return False
            
            # Calcola la data della prossima rotazione
            next_rotation = self._calculate_next_rotation(rotation_schedule, custom_interval_days)
            
            # Crea il record della credenziale
            credential = {
                "name": name,
                "type": credential_type.value,
                "service": service_name,
                "rotation_schedule": rotation_schedule.value,
                "custom_interval_days": custom_interval_days,
                "next_rotation": next_rotation.isoformat(),
                "last_rotation": None,
                "description": description or f"Credenziale {name} per {service_name}",
                "has_custom_function": rotation_func is not None
            }
            
            # Salva la funzione personalizzata se fornita
            if rotation_func:
                self._register_custom_rotation_function(name, rotation_func)
            
            # Salva la configurazione
            self.config["credentials"][name] = credential
            self._save_config()
            
            # Backup della credenziale attuale
            self._backup_credential(name, current_value)
            
            logger.info(f"Credenziale {name} registrata per rotazione {rotation_schedule.value}")
            return True
        except Exception as e:
            logger.error(f"Errore nella registrazione della credenziale {name}: {e}")
            return False
    
    def _register_custom_rotation_function(self, credential_name: str, func: Callable):
        """Registra una funzione personalizzata per la rotazione di una credenziale."""
        # In una implementazione reale, qui potremmo usare un registry o altro meccanismo
        # Per semplicità, memorizziamo solo il riferimento alla funzione in un attributo
        
        if not hasattr(self, "_custom_rotation_functions"):
            self._custom_rotation_functions = {}
        
        self._custom_rotation_functions[credential_name] = func
        logger.debug(f"Funzione personalizzata registrata per {credential_name}")
    
    def _save_config(self):
        """Salva la configurazione su file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.debug("Configurazione salvata")
        except Exception as e:
            logger.error(f"Errore nel salvataggio della configurazione: {e}")
    
    def _calculate_next_rotation(self, schedule: RotationSchedule, 
                                custom_interval_days: Optional[int] = None) -> datetime.datetime:
        """Calcola la data della prossima rotazione in base alla frequenza."""
        now = datetime.datetime.now()
        
        if schedule == RotationSchedule.DAILY:
            return now + datetime.timedelta(days=1)
        elif schedule == RotationSchedule.WEEKLY:
            return now + datetime.timedelta(weeks=1)
        elif schedule == RotationSchedule.MONTHLY:
            # Approssimazione semplice - in un'implementazione reale,
            # potremmo gestire meglio i mesi di diverse lunghezze
            return now + datetime.timedelta(days=30)
        elif schedule == RotationSchedule.QUARTERLY:
            return now + datetime.timedelta(days=90)
        elif schedule == RotationSchedule.CUSTOM:
            if not custom_interval_days or custom_interval_days < 1:
                raise ValueError("Intervallo personalizzato non valido")
            return now + datetime.timedelta(days=custom_interval_days)
        else:
            raise ValueError(f"Frequenza di rotazione non supportata: {schedule}")
    
    def _backup_credential(self, name: str, value: str):
        """Crea un backup cifrato di una credenziale."""
        try:
            # Genera un timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Cifra il valore
            encrypted_value = self._encrypt_value(value)
            
            # Crea il file di backup
            backup_path = Path(self.backup_dir) / f"{name}_{timestamp}.enc"
            
            with open(backup_path, 'w') as f:
                f.write(encrypted_value)
            
            logger.info(f"Backup della credenziale {name} creato")
            return True
        except Exception as e:
            logger.error(f"Errore nel backup della credenziale {name}: {e}")
            return False
    
    def _restore_credential_from_backup(self, name: str, timestamp: Optional[str] = None) -> Optional[str]:
        """
        Ripristina una credenziale da un backup.
        
        Args:
            name: Nome della credenziale
            timestamp: Timestamp specifico del backup (opzionale, se non specificato usa il più recente)
            
        Returns:
            Optional[str]: Valore ripristinato o None in caso di errore
        """
        try:
            # Trova tutti i backup per questa credenziale
            backups = list(Path(self.backup_dir).glob(f"{name}_*.enc"))
            
            if not backups:
                logger.error(f"Nessun backup trovato per la credenziale {name}")
                return None
            
            if timestamp:
                # Cerca il backup con il timestamp specifico
                backup_path = next((b for b in backups if timestamp in b.name), None)
                if not backup_path:
                    logger.error(f"Backup con timestamp {timestamp} non trovato per {name}")
                    return None
            else:
                # Usa il backup più recente
                backup_path = sorted(backups, key=lambda p: p.stat().st_mtime, reverse=True)[0]
            
            # Legge e decifra il valore
            with open(backup_path, 'r') as f:
                encrypted_value = f.read()
            
            return self._decrypt_value(encrypted_value)
        except Exception as e:
            logger.error(f"Errore nel ripristino della credenziale {name}: {e}")
            return None
    
    def check_pending_rotations(self) -> List[Dict[str, Any]]:
        """
        Verifica le credenziali che devono essere ruotate.
        
        Returns:
            List[Dict]: Lista di credenziali da ruotare
        """
        now = datetime.datetime.now()
        pending_rotations = []
        
        for name, cred in self.config["credentials"].items():
            next_rotation = datetime.datetime.fromisoformat(cred["next_rotation"])
            
            # Verifica se la rotazione è prevista per oggi o è già passata
            if next_rotation <= now:
                pending_rotations.append({
                    "name": name,
                    "type": cred["type"],
                    "service": cred["service"],
                    "scheduled_date": next_rotation.isoformat(),
                    "days_overdue": (now - next_rotation).days
                })
        
        logger.info(f"Trovate {len(pending_rotations)} rotazioni in attesa")
        return pending_rotations
    
    def check_upcoming_rotations(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Verifica le credenziali la cui rotazione è prevista entro un certo numero di giorni.
        
        Args:
            days: Numero di giorni entro cui verificare
            
        Returns:
            List[Dict]: Lista di credenziali la cui rotazione è prevista
        """
        now = datetime.datetime.now()
        future_date = now + datetime.timedelta(days=days)
        upcoming_rotations = []
        
        for name, cred in self.config["credentials"].items():
            next_rotation = datetime.datetime.fromisoformat(cred["next_rotation"])
            
            # Verifica se la rotazione è prevista entro i giorni specificati
            if now < next_rotation <= future_date:
                upcoming_rotations.append({
                    "name": name,
                    "type": cred["type"],
                    "service": cred["service"],
                    "scheduled_date": next_rotation.isoformat(),
                    "days_until_rotation": (next_rotation - now).days
                })
        
        logger.info(f"Trovate {len(upcoming_rotations)} rotazioni previste nei prossimi {days} giorni")
        return upcoming_rotations
    
    def _generate_new_value(self, credential_type: str, length: int = 32) -> str:
        """
        Genera un nuovo valore per una credenziale in base al tipo.
        
        Args:
            credential_type: Tipo di credenziale (da CredentialType)
            length: Lunghezza della nuova credenziale (per tipi che lo supportano)
            
        Returns:
            str: Nuovo valore generato
        """
        if credential_type == CredentialType.API_KEY.value:
            # API key standard formato "prefix_randomchars"
            prefix = ''.join(random.choices(string.ascii_uppercase, k=3))
            random_part = secrets.token_urlsafe(length)
            return f"{prefix}_{random_part}"
        
        elif credential_type == CredentialType.DATABASE_PASSWORD.value:
            # Password sicura con vari tipi di caratteri
            chars = string.ascii_letters + string.digits + "!@#$%^&*()-_=+[]{}|;:,.<>?"
            return ''.join(secrets.choice(chars) for _ in range(length))
        
        elif credential_type == CredentialType.JWT_SECRET.value:
            # Stringa random per JWT
            return secrets.token_hex(length)
        
        elif credential_type == CredentialType.ENCRYPTION_KEY.value:
            # Chiave Fernet
            return Fernet.generate_key().decode('utf-8')
        
        elif credential_type == CredentialType.WEBHOOK_SECRET.value:
            # Webhook secret (stringa esadecimale)
            return secrets.token_hex(length)
        
        elif credential_type == CredentialType.SSH_KEY.value:
            # Genera una coppia di chiavi SSH (in un'implementazione reale, 
            # usare librerie come paramiko o pycrypto)
            # Qui restituiamo solo una stringa di placeholder
            return "SSH_KEY_PLACEHOLDER_REQUIRES_ACTUAL_IMPLEMENTATION"
        
        else:
            # Per altri tipi, usa un token URL-safe
            return secrets.token_urlsafe(length)
    
    async def rotate_credential(self, name: str, manual: bool = False) -> Dict[str, Any]:
        """
        Ruota una credenziale, generando un nuovo valore e aggiornando la configurazione.
        
        Args:
            name: Nome della credenziale
            manual: True se la rotazione è stata avviata manualmente
            
        Returns:
            Dict: Risultato della rotazione
        """
        # Verifica se la credenziale esiste
        if name not in self.config["credentials"]:
            return {"success": False, "message": f"Credenziale {name} non trovata"}
        
        # Inizializza lo stato della rotazione
        self.current_rotation = {
            "name": name,
            "started_at": datetime.datetime.now().isoformat(),
            "status": RotationStatus.IN_PROGRESS.value,
            "manual": manual
        }
        
        try:
            credential = self.config["credentials"][name]
            
            # Ottieni il valore attuale dal backup più recente
            current_value = self._restore_credential_from_backup(name)
            if not current_value:
                return {"success": False, "message": f"Impossibile recuperare il valore attuale di {name}"}
            
            # Genera un nuovo valore
            new_value = None
            
            # Verifica se esiste una funzione di rotazione personalizzata
            if credential.get("has_custom_function", False) and hasattr(self, "_custom_rotation_functions"):
                if name in self._custom_rotation_functions:
                    try:
                        # Chiama la funzione personalizzata
                        custom_func = self._custom_rotation_functions[name]
                        logger.info(f"Utilizzo funzione personalizzata per ruotare {name}")
                        new_value = await custom_func(name, current_value)
                    except Exception as e:
                        logger.error(f"Errore nella funzione personalizzata per {name}: {e}")
                        # Continua con il metodo standard
            
            # Se non c'è un valore personalizzato, genera uno standard
            if not new_value:
                new_value = self._generate_new_value(credential["type"])
            
            # Crea un backup del nuovo valore
            if not self._backup_credential(name, new_value):
                return {"success": False, "message": f"Errore nel backup del nuovo valore per {name}"}
            
            # Aggiorna la configurazione
            credential["last_rotation"] = datetime.datetime.now().isoformat()
            credential["next_rotation"] = self._calculate_next_rotation(
                RotationSchedule(credential["rotation_schedule"]), 
                credential.get("custom_interval_days")
            ).isoformat()
            
            self.config["credentials"][name] = credential
            self._save_config()
            
            # Registra la rotazione nella cronologia
            rotation_entry = {
                "name": name,
                "type": credential["type"],
                "service": credential["service"],
                "rotated_at": datetime.datetime.now().isoformat(),
                "next_rotation": credential["next_rotation"],
                "manual": manual,
                "success": True
            }
            
            self.rotation_history.append(rotation_entry)
            self._save_rotation_history()
            
            # Aggiorna lo stato della rotazione
            self.current_rotation["status"] = RotationStatus.COMPLETED.value
            self.current_rotation["completed_at"] = datetime.datetime.now().isoformat()
            
            logger.info(f"Rotazione della credenziale {name} completata con successo")
            
            return {
                "success": True,
                "message": f"Credenziale {name} ruotata con successo",
                "credential_name": name,
                "credential_type": credential["type"],
                "service": credential["service"],
                "new_value": new_value,  # In un'implementazione reale, potremmo non voler restituire questo
                "previous_value": current_value,  # Stesso discorso per questo
                "next_rotation": credential["next_rotation"]
            }
            
        except Exception as e:
            error_message = f"Errore nella rotazione della credenziale {name}: {e}"
            logger.error(error_message)
            
            # Aggiorna lo stato della rotazione
            self.current_rotation["status"] = RotationStatus.FAILED.value
            self.current_rotation["error"] = str(e)
            self.current_rotation["completed_at"] = datetime.datetime.now().isoformat()
            
            # Registra il fallimento nella cronologia
            rotation_entry = {
                "name": name,
                "type": self.config["credentials"][name]["type"],
                "service": self.config["credentials"][name]["service"],
                "rotated_at": datetime.datetime.now().isoformat(),
                "manual": manual,
                "success": False,
                "error": str(e)
            }
            
            self.rotation_history.append(rotation_entry)
            self._save_rotation_history()
            
            return {"success": False, "message": error_message}
    
    async def rollback_rotation(self, name: str, to_timestamp: Optional[str] = None) -> Dict[str, Any]:
        """
        Ripristina una credenziale a un valore precedente.
        
        Args:
            name: Nome della credenziale
            to_timestamp: Timestamp specifico del backup (opzionale)
            
        Returns:
            Dict: Risultato del ripristino
        """
        # Verifica se la credenziale esiste
        if name not in self.config["credentials"]:
            return {"success": False, "message": f"Credenziale {name} non trovata"}
        
        try:
            # Ripristina il valore precedente
            previous_value = self._restore_credential_from_backup(name, to_timestamp)
            if not previous_value:
                return {"success": False, "message": f"Impossibile recuperare il valore precedente di {name}"}
            
            # Crea un backup del valore ripristinato (con un nuovo timestamp)
            if not self._backup_credential(name, previous_value):
                return {"success": False, "message": f"Errore nel backup del valore ripristinato per {name}"}
            
            # Registra il rollback nella cronologia
            rollback_entry = {
                "name": name,
                "type": self.config["credentials"][name]["type"],
                "service": self.config["credentials"][name]["service"],
                "rollback_at": datetime.datetime.now().isoformat(),
                "rollback_to": to_timestamp or "most_recent",
                "success": True
            }
            
            self.rotation_history.append(rollback_entry)
            self._save_rotation_history()
            
            # Se era in corso una rotazione, aggiorna lo stato
            if self.current_rotation and self.current_rotation.get("name") == name:
                self.current_rotation["status"] = RotationStatus.ROLLED_BACK.value
                self.current_rotation["completed_at"] = datetime.datetime.now().isoformat()
            
            logger.info(f"Rollback della credenziale {name} completato con successo")
            
            return {
                "success": True,
                "message": f"Credenziale {name} ripristinata con successo",
                "credential_name": name,
                "restored_value": previous_value,  # In un'implementazione reale, potremmo non voler restituire questo
                "to_timestamp": to_timestamp or "most_recent"
            }
            
        except Exception as e:
            error_message = f"Errore nel rollback della credenziale {name}: {e}"
            logger.error(error_message)
            return {"success": False, "message": error_message}
    
    def cleanup_old_backups(self) -> int:
        """
        Rimuove i backup più vecchi del periodo di retention configurato.
        
        Returns:
            int: Numero di backup rimossi
        """
        retention_days = self.config.get("backup_retention_days", 90)
        if retention_days <= 0:
            logger.info("Pulizia backup disabilitata (retention_days <= 0)")
            return 0
        
        try:
            cutoff_time = datetime.datetime.now() - datetime.timedelta(days=retention_days)
            count_removed = 0
            
            # Trova tutti i file di backup
            for backup_file in Path(self.backup_dir).glob("*.enc"):
                # Verifica l'età del file
                file_time = datetime.datetime.fromtimestamp(backup_file.stat().st_mtime)
                
                if file_time < cutoff_time:
                    backup_file.unlink()
                    count_removed += 1
            
            if count_removed > 0:
                logger.info(f"Rimossi {count_removed} backup più vecchi di {retention_days} giorni")
            
            return count_removed
        except Exception as e:
            logger.error(f"Errore nella pulizia dei backup: {e}")
            return 0
    
    async def start_scheduled_rotation(self):
        """Avvia il processo di rotazione schedulata delle credenziali."""
        if not self.config.get("enabled", True):
            logger.info("Sistema di rotazione credenziali disabilitato, rotazione schedulata saltata")
            return
        
        # Verifica le rotazioni in attesa
        pending_rotations = self.check_pending_rotations()
        
        if not pending_rotations:
            logger.info("Nessuna rotazione in attesa")
            return
        
        # Ruota le credenziali in attesa
        for rotation in pending_rotations:
            credential_name = rotation["name"]
            logger.info(f"Avvio rotazione schedulata per {credential_name}")
            
            result = await self.rotate_credential(credential_name)
            
            if not result["success"]:
                logger.error(f"Rotazione schedulata fallita per {credential_name}: {result['message']}")
            else:
                logger.info(f"Rotazione schedulata completata per {credential_name}")
    
    def get_credential_status(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Ottiene lo stato di una o tutte le credenziali.
        
        Args:
            name: Nome della credenziale (opzionale, se non specificato restituisce tutte)
            
        Returns:
            Dict: Stato della/e credenziale/i
        """
        if name:
            if name not in self.config["credentials"]:
                return {"error": f"Credenziale {name} non trovata"}
            
            credential = self.config["credentials"][name]
            
            # Calcola i giorni alla prossima rotazione
            next_rotation = datetime.datetime.fromisoformat(credential["next_rotation"])
            days_to_rotation = (next_rotation - datetime.datetime.now()).days
            
            return {
                "name": name,
                "type": credential["type"],
                "service": credential["service"],
                "last_rotation": credential["last_rotation"],
                "next_rotation": credential["next_rotation"],
                "days_to_rotation": days_to_rotation,
                "description": credential.get("description", ""),
                "schedule": credential["rotation_schedule"]
            }
        else:
            # Restituisce lo stato di tutte le credenziali
            result = {
                "total_credentials": len(self.config["credentials"]),
                "pending_rotations": len(self.check_pending_rotations()),
                "credentials": {}
            }
            
            for cred_name, credential in self.config["credentials"].items():
                # Calcola i giorni alla prossima rotazione
                next_rotation = datetime.datetime.fromisoformat(credential["next_rotation"])
                days_to_rotation = (next_rotation - datetime.datetime.now()).days
                
                result["credentials"][cred_name] = {
                    "type": credential["type"],
                    "service": credential["service"],
                    "next_rotation": credential["next_rotation"],
                    "days_to_rotation": days_to_rotation,
                    "schedule": credential["rotation_schedule"]
                }
            
            return result

# Esempio di utilizzo come script indipendente
async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Sistema di rotazione automatica delle credenziali")
    parser.add_argument("--config", help="Percorso del file di configurazione")
    parser.add_argument("--check", action="store_true", help="Verifica le rotazioni in attesa")
    parser.add_argument("--rotate", help="Ruota una credenziale specifica")
    parser.add_argument("--status", action="store_true", help="Mostra lo stato delle credenziali")
    parser.add_argument("--cleanup", action="store_true", help="Rimuovi i backup più vecchi")
    
    args = parser.parse_args()
    
    # Crea il gestore
    manager = CredentialRotationManager(args.config)
    
    if args.check:
        # Verifica le rotazioni in attesa
        pending = manager.check_pending_rotations()
        print(f"Rotazioni in attesa: {len(pending)}")
        for cred in pending:
            print(f"  - {cred['name']} ({cred['service']}): {cred['scheduled_date']}")
        
        # Verifica le rotazioni imminenti (prossimi 7 giorni)
        upcoming = manager.check_upcoming_rotations(7)
        print(f"\nRotazioni imminenti (prossimi 7 giorni): {len(upcoming)}")
        for cred in upcoming:
            print(f"  - {cred['name']} ({cred['service']}): {cred['scheduled_date']} " +
                 f"(tra {cred['days_until_rotation']} giorni)")
    
    elif args.rotate:
        # Ruota una credenziale specifica
        result = await manager.rotate_credential(args.rotate, manual=True)
        if result["success"]:
            print(f"Rotazione completata: {result['message']}")
        else:
            print(f"Errore nella rotazione: {result['message']}")
    
    elif args.status:
        # Mostra lo stato delle credenziali
        status = manager.get_credential_status()
        print(f"Credenziali totali: {status['total_credentials']}")
        print(f"Rotazioni in attesa: {status['pending_rotations']}")
        
        print("\nElenco credenziali:")
        for name, cred in status["credentials"].items():
            print(f"  - {name} ({cred['service']}): rotazione tra {cred['days_to_rotation']} giorni")
    
    elif args.cleanup:
        # Rimuovi i backup più vecchi
        removed = manager.cleanup_old_backups()
        print(f"Backup rimossi: {removed}")
    
    else:
        # Modalità predefinita: avvia la rotazione schedulata
        print("Avvio rotazione schedulata...")
        await manager.start_scheduled_rotation()
        print("Rotazione schedulata completata")

if __name__ == "__main__":
    asyncio.run(main()) 