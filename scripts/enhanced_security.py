#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import base64
import logging
import json
import datetime
from typing import Dict, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Configurazione logger
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("enhanced_security")

class KeyVault:
    """Gestisce la creazione, lo storage e l'accesso sicuro alle chiavi crittografiche."""
    
    def __init__(self, vault_path: str = None):
        """
        Inizializza il vault delle chiavi.
        
        Args:
            vault_path: Percorso del file vault. Se None, usa la posizione predefinita
        """
        self.vault_path = vault_path or os.path.expanduser('~/.m4bot/security/keyvault.enc')
        self._master_key = None
        self._keys = {}
        self._initialized = False
        
        # Assicurati che la directory esista
        os.makedirs(os.path.dirname(self.vault_path), exist_ok=True)
    
    def initialize(self, master_password: str) -> bool:
        """
        Inizializza il vault con una password master.
        
        Args:
            master_password: Password principale per proteggere il vault
            
        Returns:
            bool: True se l'inizializzazione è riuscita
        """
        try:
            # Genera una chiave derivata dalla password
            self._master_key = self._derive_key(master_password)
            
            # Se il vault non esiste, creane uno nuovo
            if not os.path.exists(self.vault_path):
                self._keys = {
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat(),
                    "keys": {}
                }
                self._save_vault()
                logger.info("Nuovo vault delle chiavi creato")
            else:
                # Carica il vault esistente
                self._load_vault()
            
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Errore nell'inizializzazione del vault: {e}")
            return False
    
    def add_key(self, key_name: str, key_value: Optional[bytes] = None) -> Tuple[bool, bytes]:
        """
        Aggiunge una nuova chiave al vault o genera una nuova chiave Fernet.
        
        Args:
            key_name: Nome identificativo della chiave
            key_value: Valore della chiave (se None, ne genera una nuova)
            
        Returns:
            Tuple[bool, bytes]: (successo, valore della chiave)
        """
        if not self._initialized:
            return False, b""
        
        try:
            if key_value is None:
                key_value = Fernet.generate_key()
            
            # Salva la chiave nel vault
            self._keys["keys"][key_name] = {
                "value": base64.b64encode(key_value).decode('utf-8'),
                "created_at": datetime.now().isoformat(),
                "last_used": datetime.now().isoformat(),
                "type": "fernet"
            }
            
            self._keys["updated_at"] = datetime.now().isoformat()
            self._save_vault()
            
            logger.info(f"Chiave '{key_name}' aggiunta al vault")
            return True, key_value
        except Exception as e:
            logger.error(f"Errore nell'aggiunta della chiave '{key_name}': {e}")
            return False, b""
    
    def get_key(self, key_name: str) -> Optional[bytes]:
        """
        Recupera una chiave dal vault.
        
        Args:
            key_name: Nome della chiave da recuperare
            
        Returns:
            Optional[bytes]: Il valore della chiave o None se non trovata
        """
        if not self._initialized:
            return None
        
        try:
            if key_name not in self._keys["keys"]:
                logger.warning(f"Chiave '{key_name}' non trovata nel vault")
                return None
            
            # Aggiorna l'ultimo utilizzo
            self._keys["keys"][key_name]["last_used"] = datetime.now().isoformat()
            self._save_vault()
            
            # Decodifica e restituisci la chiave
            return base64.b64decode(self._keys["keys"][key_name]["value"])
        except Exception as e:
            logger.error(f"Errore nel recupero della chiave '{key_name}': {e}")
            return None
    
    def rotate_key(self, key_name: str) -> Tuple[bool, Optional[bytes]]:
        """
        Ruota una chiave esistente generandone una nuova.
        
        Args:
            key_name: Nome della chiave da ruotare
            
        Returns:
            Tuple[bool, Optional[bytes]]: (successo, nuova chiave)
        """
        if not self._initialized:
            return False, None
        
        if key_name not in self._keys["keys"]:
            logger.warning(f"Impossibile ruotare: chiave '{key_name}' non trovata")
            return False, None
        
        try:
            # Genera una nuova chiave
            new_key = Fernet.generate_key()
            
            # Salva la chiave precedente nella storia
            if "history" not in self._keys["keys"][key_name]:
                self._keys["keys"][key_name]["history"] = []
            
            self._keys["keys"][key_name]["history"].append({
                "value": self._keys["keys"][key_name]["value"],
                "rotated_at": datetime.now().isoformat()
            })
            
            # Limita la cronologia a 5 chiavi
            if len(self._keys["keys"][key_name]["history"]) > 5:
                self._keys["keys"][key_name]["history"] = self._keys["keys"][key_name]["history"][-5:]
            
            # Aggiorna la chiave corrente
            self._keys["keys"][key_name]["value"] = base64.b64encode(new_key).decode('utf-8')
            self._keys["keys"][key_name]["last_rotated"] = datetime.now().isoformat()
            self._keys["updated_at"] = datetime.now().isoformat()
            
            self._save_vault()
            logger.info(f"Chiave '{key_name}' ruotata con successo")
            
            return True, new_key
        except Exception as e:
            logger.error(f"Errore nella rotazione della chiave '{key_name}': {e}")
            return False, None
    
    def list_keys(self) -> Dict[str, Dict[str, Any]]:
        """
        Elenca tutte le chiavi nel vault (senza i valori).
        
        Returns:
            Dict: Metadati delle chiavi senza i valori effettivi
        """
        if not self._initialized:
            return {}
        
        result = {}
        for key_name, data in self._keys["keys"].items():
            result[key_name] = {
                "created_at": data.get("created_at"),
                "last_used": data.get("last_used"),
                "type": data.get("type"),
                "has_history": "history" in data and len(data["history"]) > 0,
                "last_rotated": data.get("last_rotated")
            }
        
        return result
    
    def _derive_key(self, password: str) -> bytes:
        """
        Deriva una chiave crittografica da una password.
        
        Args:
            password: Password da cui derivare la chiave
            
        Returns:
            bytes: Chiave derivata
        """
        # Usa un sale fisso per questo progetto
        # In un sistema di produzione, il sale dovrebbe essere generato per utente
        # e conservato in modo sicuro
        salt = b'm4bot_security_salt'
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        
        return base64.urlsafe_b64encode(kdf.derive(password.encode()))
    
    def _save_vault(self) -> bool:
        """
        Salva il vault delle chiavi in un file crittografato.
        
        Returns:
            bool: True se il salvataggio è riuscito
        """
        if not self._master_key:
            return False
        
        try:
            # Converti il dizionario in JSON e crittografa
            vault_data = json.dumps(self._keys).encode('utf-8')
            
            f = Fernet(self._master_key)
            encrypted_data = f.encrypt(vault_data)
            
            # Scrivi su file
            with open(self.vault_path, 'wb') as vault_file:
                vault_file.write(encrypted_data)
            
            return True
        except Exception as e:
            logger.error(f"Errore nel salvataggio del vault: {e}")
            return False
    
    def _load_vault(self) -> bool:
        """
        Carica il vault delle chiavi da un file crittografato.
        
        Returns:
            bool: True se il caricamento è riuscito
        """
        if not self._master_key or not os.path.exists(self.vault_path):
            return False
        
        try:
            # Leggi e decrittografa il file
            with open(self.vault_path, 'rb') as vault_file:
                encrypted_data = vault_file.read()
            
            f = Fernet(self._master_key)
            decrypted_data = f.decrypt(encrypted_data)
            
            # Converti da JSON a dizionario
            self._keys = json.loads(decrypted_data.decode('utf-8'))
            return True
        except Exception as e:
            logger.error(f"Errore nel caricamento del vault: {e}")
            return False

class EnhancedEncryption:
    """Implementa funzionalità avanzate di crittografia con gestione sicura delle chiavi."""
    
    def __init__(self, vault: KeyVault = None, default_key_name: str = "default_encryption_key"):
        """
        Inizializza il sistema di crittografia.
        
        Args:
            vault: KeyVault da utilizzare. Se None, ne crea uno nuovo
            default_key_name: Nome della chiave predefinita da utilizzare
        """
        self.vault = vault or KeyVault()
        self.default_key_name = default_key_name
        self._initialized = False
    
    def initialize(self, master_password: str) -> bool:
        """
        Inizializza il sistema con la password master.
        
        Args:
            master_password: Password principale
            
        Returns:
            bool: True se l'inizializzazione è riuscita
        """
        try:
            # Inizializza il vault
            if not self.vault.initialize(master_password):
                return False
            
            # Verifica se la chiave predefinita esiste, altrimenti creala
            if not self.vault.get_key(self.default_key_name):
                success, _ = self.vault.add_key(self.default_key_name)
                if not success:
                    return False
            
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Errore nell'inizializzazione del sistema di crittografia: {e}")
            return False
    
    def encrypt(self, data: Union[str, bytes], key_name: str = None) -> Tuple[bool, bytes]:
        """
        Crittografa i dati.
        
        Args:
            data: Dati da crittografare
            key_name: Nome della chiave da usare (se None, usa quella predefinita)
            
        Returns:
            Tuple[bool, bytes]: (successo, dati crittografati)
        """
        if not self._initialized:
            return False, b""
        
        key_name = key_name or self.default_key_name
        key = self.vault.get_key(key_name)
        
        if not key:
            return False, b""
        
        try:
            f = Fernet(key)
            if isinstance(data, str):
                encrypted = f.encrypt(data.encode('utf-8'))
            else:
                encrypted = f.encrypt(data)
            
            return True, encrypted
        except Exception as e:
            logger.error(f"Errore nella crittografia: {e}")
            return False, b""
    
    def decrypt(self, encrypted_data: bytes, key_name: str = None) -> Tuple[bool, bytes]:
        """
        Decrittografa i dati.
        
        Args:
            encrypted_data: Dati crittografati
            key_name: Nome della chiave da usare (se None, usa quella predefinita)
            
        Returns:
            Tuple[bool, bytes]: (successo, dati decrittografati)
        """
        if not self._initialized:
            return False, b""
        
        key_name = key_name or self.default_key_name
        key = self.vault.get_key(key_name)
        
        if not key:
            return False, b""
        
        try:
            f = Fernet(key)
            decrypted = f.decrypt(encrypted_data)
            return True, decrypted
        except Exception as e:
            logger.error(f"Errore nella decrittografia: {e}")
            return False, b""
    
    def rotate_keys(self, key_names: Optional[list] = None) -> bool:
        """
        Ruota le chiavi specificate.
        
        Args:
            key_names: Lista di nomi di chiavi da ruotare. Se None, ruota solo quella predefinita
            
        Returns:
            bool: True se tutte le rotazioni sono riuscite
        """
        if not self._initialized:
            return False
        
        key_names = key_names or [self.default_key_name]
        success = True
        
        for key_name in key_names:
            result, _ = self.vault.rotate_key(key_name)
            if not result:
                success = False
        
        return success

# Funzioni di utilità
def create_secure_backup(data: bytes, filename: str, encryption: EnhancedEncryption) -> Tuple[bool, str]:
    """
    Crea un backup crittografato.
    
    Args:
        data: Dati da salvare
        filename: Nome base del file
        encryption: Sistema di crittografia da utilizzare
        
    Returns:
        Tuple[bool, str]: (successo, percorso del file di backup)
    """
    try:
        # Crittografa i dati
        success, encrypted_data = encryption.encrypt(data)
        if not success:
            return False, ""
        
        # Imposta percorso del backup
        backup_dir = os.path.expanduser('~/.m4bot/backups')
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"{filename}_{timestamp}.enc")
        
        # Salva il backup
        with open(backup_path, "wb") as f:
            f.write(encrypted_data)
        
        logger.info(f"Backup crittografato creato: {backup_path}")
        return True, backup_path
    except Exception as e:
        logger.error(f"Errore nella creazione del backup: {e}")
        return False, ""

def restore_secure_backup(backup_path: str, encryption: EnhancedEncryption) -> Tuple[bool, bytes]:
    """
    Ripristina un backup crittografato.
    
    Args:
        backup_path: Percorso del file di backup
        encryption: Sistema di crittografia da utilizzare
        
    Returns:
        Tuple[bool, bytes]: (successo, dati ripristinati)
    """
    try:
        # Leggi il file crittografato
        with open(backup_path, "rb") as f:
            encrypted_data = f.read()
        
        # Decrittografa i dati
        success, decrypted_data = encryption.decrypt(encrypted_data)
        if not success:
            return False, b""
        
        logger.info(f"Backup {backup_path} ripristinato con successo")
        return True, decrypted_data
    except Exception as e:
        logger.error(f"Errore nel ripristino del backup: {e}")
        return False, b""

# Esempio di utilizzo:
if __name__ == "__main__":
    print("Inizializzazione del sistema di sicurezza avanzato...")
    
    # Crea e inizializza il vault
    vault = KeyVault()
    vault.initialize("password_super_segreta")  # In un sistema reale, non hardcodare mai la password
    
    # Crea il sistema di crittografia
    encryption = EnhancedEncryption(vault)
    encryption.initialize("password_super_segreta")
    
    # Test di crittografia
    print("Test di crittografia...")
    success, encrypted = encryption.encrypt("Dati sensibili di test")
    if success:
        print("Crittografia riuscita!")
        
        # Test di decrittografia
        success, decrypted = encryption.decrypt(encrypted)
        if success:
            print(f"Decrittografia riuscita: {decrypted.decode('utf-8')}")
        else:
            print("Decrittografia fallita!")
    else:
        print("Crittografia fallita!")
    
    # Test di rotazione chiavi
    print("Rotazione delle chiavi...")
    if encryption.rotate_keys():
        print("Rotazione chiavi completata!")
    else:
        print("Rotazione chiavi fallita!")
    
    # Elenco delle chiavi
    print("Chiavi nel vault:")
    for key_name, metadata in vault.list_keys().items():
        print(f" - {key_name}: creata il {metadata['created_at']}, tipo {metadata['type']}")
    
    # Test backup
    print("Test di backup...")
    success, backup_path = create_secure_backup(b"Dati importanti di test", "test_backup", encryption)
    if success:
        print(f"Backup creato: {backup_path}")
        
        # Test di ripristino
        success, restored_data = restore_secure_backup(backup_path, encryption)
        if success:
            print(f"Backup ripristinato: {restored_data.decode('utf-8')}")
        else:
            print("Ripristino fallito!")
    else:
        print("Creazione backup fallita!")
    
    print("Test completati.") 