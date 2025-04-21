#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import yaml
import json
import logging
import tempfile
import shutil
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Union, List, Tuple
from datetime import datetime

# Configurazione logger
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("config_manager")

class ConfigManager:
    """Gestore avanzato delle configurazioni che supporta vari formati e validazione."""
    
    def __init__(self, 
                 base_dir: str = None, 
                 config_name: str = "config",
                 format: str = "yaml"):
        """
        Inizializza il gestore configurazioni.
        
        Args:
            base_dir: Directory di base per i file di configurazione
            config_name: Nome del file di configurazione (senza estensione)
            format: Formato del file (yaml, json, env)
        """
        self.format = format.lower()
        if self.format not in ['yaml', 'json', 'env']:
            raise ValueError(f"Formato '{format}' non supportato. Usa 'yaml', 'json' o 'env'")
        
        # Determina la directory di base
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path(os.path.expanduser('~/.m4bot/config'))
        
        # Crea la directory se non esiste
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # Configura il nome del file
        self.config_name = config_name
        self.config_path = self._get_config_path()
        
        # Valori predefiniti
        self.config = {}
        self.defaults = {}
        self.required_keys = []
        self.validators = {}
        self.last_validation_errors = []
    
    def _get_config_path(self) -> Path:
        """Restituisce il percorso completo del file di configurazione."""
        extension = {"yaml": "yml", "json": "json", "env": "env"}[self.format]
        return self.base_dir / f"{self.config_name}.{extension}"
    
    def set_defaults(self, defaults: Dict[str, Any]) -> None:
        """
        Imposta i valori predefiniti per la configurazione.
        
        Args:
            defaults: Dizionario con i valori predefiniti
        """
        self.defaults = defaults
    
    def set_required(self, required_keys: List[str]) -> None:
        """
        Imposta le chiavi obbligatorie per la configurazione.
        
        Args:
            required_keys: Lista di chiavi obbligatorie
        """
        self.required_keys = required_keys
    
    def add_validator(self, key: str, validator_func: callable) -> None:
        """
        Aggiunge una funzione di validazione per una chiave specifica.
        
        Args:
            key: Chiave da validare
            validator_func: Funzione che accetta il valore e restituisce (valido, messaggio)
        """
        self.validators[key] = validator_func
    
    def load(self) -> Dict[str, Any]:
        """
        Carica la configurazione dal file.
        
        Returns:
            Dict: La configurazione caricata o i valori predefiniti
        """
        # Verifica se il file esiste
        if not self.config_path.exists():
            logger.warning(f"File di configurazione {self.config_path} non trovato. "
                          f"Utilizzo dei valori predefiniti.")
            self.config = self.defaults.copy()
            self._save_defaults()
            return self.config
        
        try:
            # Carica in base al formato
            if self.format == 'yaml':
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f) or {}
            elif self.format == 'json':
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            elif self.format == 'env':
                self.config = {}
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        key, value = line.split('=', 1)
                        self.config[key.strip()] = value.strip()
            
            # Aggiungi valori predefiniti per chiavi mancanti
            for key, value in self.defaults.items():
                if key not in self.config:
                    self.config[key] = value
            
            logger.info(f"Configurazione caricata da {self.config_path}")
            return self.config
        
        except Exception as e:
            logger.error(f"Errore nel caricamento della configurazione: {e}")
            self.config = self.defaults.copy()
            return self.config
    
    def save(self, config: Dict[str, Any] = None) -> bool:
        """
        Salva la configurazione su file.
        
        Args:
            config: Configurazione da salvare. Se None, usa quella corrente
            
        Returns:
            bool: True se il salvataggio è riuscito
        """
        if config is not None:
            self.config = config
        
        try:
            # Crea un file temporaneo per la scrittura sicura
            with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as temp_file:
                if self.format == 'yaml':
                    yaml.dump(self.config, temp_file, default_flow_style=False)
                elif self.format == 'json':
                    json.dump(self.config, temp_file, indent=2)
                elif self.format == 'env':
                    for key, value in self.config.items():
                        temp_file.write(f"{key}={value}\n")
            
            # Sposta il file temporaneo nella posizione finale con operazione atomica
            shutil.move(temp_file.name, self.config_path)
            
            logger.info(f"Configurazione salvata in {self.config_path}")
            return True
        
        except Exception as e:
            logger.error(f"Errore nel salvataggio della configurazione: {e}")
            # Rimuovi il file temporaneo se esiste
            if 'temp_file' in locals():
                try:
                    os.unlink(temp_file.name)
                except:
                    pass
            return False
    
    def _save_defaults(self) -> bool:
        """
        Salva i valori predefiniti come nuova configurazione.
        
        Returns:
            bool: True se il salvataggio è riuscito
        """
        return self.save(self.defaults)
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Ottiene il valore di una chiave specifica.
        
        Args:
            key: Chiave da cercare
            default: Valore da restituire se la chiave non esiste
            
        Returns:
            Any: Il valore della chiave o il default
        """
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """
        Imposta il valore di una chiave specifica.
        
        Args:
            key: Chiave da impostare
            value: Valore da assegnare
        """
        self.config[key] = value
    
    def update(self, updates: Dict[str, Any]) -> None:
        """
        Aggiorna più valori contemporaneamente.
        
        Args:
            updates: Dizionario con le coppie chiave-valore da aggiornare
        """
        self.config.update(updates)
    
    def validate(self) -> Tuple[bool, List[str]]:
        """
        Valida la configurazione corrente.
        
        Returns:
            Tuple[bool, List[str]]: (valido, lista di errori)
        """
        errors = []
        
        # Verifica le chiavi obbligatorie
        for key in self.required_keys:
            if key not in self.config or self.config[key] is None:
                errors.append(f"Chiave obbligatoria '{key}' mancante")
        
        # Applica i validatori personalizzati
        for key, validator in self.validators.items():
            if key in self.config:
                valid, message = validator(self.config[key])
                if not valid:
                    errors.append(f"Validazione fallita per '{key}': {message}")
        
        self.last_validation_errors = errors
        return len(errors) == 0, errors
    
    def create_backup(self) -> Optional[str]:
        """
        Crea un backup della configurazione corrente.
        
        Returns:
            Optional[str]: Percorso del file di backup o None se fallisce
        """
        if not self.config_path.exists():
            return None
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = self.config_path.with_name(f"{self.config_name}_{timestamp}.bak")
            shutil.copy2(self.config_path, backup_path)
            logger.info(f"Backup della configurazione creato: {backup_path}")
            return str(backup_path)
        except Exception as e:
            logger.error(f"Errore nella creazione del backup: {e}")
            return None
    
    def restore_backup(self, backup_path: str) -> bool:
        """
        Ripristina un backup della configurazione.
        
        Args:
            backup_path: Percorso del file di backup
            
        Returns:
            bool: True se il ripristino è riuscito
        """
        try:
            # Crea un backup della configurazione corrente prima di sovrascriverla
            current_backup = self.create_backup()
            
            # Ripristina dal backup
            shutil.copy2(backup_path, self.config_path)
            self.load()  # Ricarica la configurazione
            
            logger.info(f"Configurazione ripristinata da {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Errore nel ripristino del backup: {e}")
            return False
    
    def merge_with_env(self, prefix: str = "M4BOT_") -> None:
        """
        Integra le variabili d'ambiente nella configurazione.
        
        Args:
            prefix: Prefisso per le variabili d'ambiente da considerare
        """
        for env_key, env_value in os.environ.items():
            if env_key.startswith(prefix):
                # Rimuovi il prefisso e converti in minuscolo
                config_key = env_key[len(prefix):].lower()
                
                # Gestisci i tipi di dati
                if env_value.lower() in ['true', 'yes', '1']:
                    self.config[config_key] = True
                elif env_value.lower() in ['false', 'no', '0']:
                    self.config[config_key] = False
                elif env_value.isdigit():
                    self.config[config_key] = int(env_value)
                elif env_value.replace('.', '', 1).isdigit():
                    self.config[config_key] = float(env_value)
                else:
                    self.config[config_key] = env_value

class DatabaseConfigValidator:
    """Validatore specializzato per le configurazioni del database."""
    
    @staticmethod
    def validate_postgresql_url(url: str) -> Tuple[bool, str]:
        """
        Verifica se l'URL di PostgreSQL è valido.
        
        Args:
            url: URL del database PostgreSQL
            
        Returns:
            Tuple[bool, str]: (valido, messaggio)
        """
        if not url.startswith("postgresql://"):
            return False, "L'URL deve iniziare con 'postgresql://'"
        
        # Verifica che sia presente utente, password, host e database
        parts = url.split('://', 1)[1]
        if '@' not in parts or '/' not in parts:
            return False, "Formato URL non valido. Deve contenere '@' e '/'"
        
        return True, "URL PostgreSQL valido"
    
    @staticmethod
    def validate_port(port: int) -> Tuple[bool, str]:
        """
        Verifica se la porta è valida.
        
        Args:
            port: Numero di porta
            
        Returns:
            Tuple[bool, str]: (valido, messaggio)
        """
        if not isinstance(port, int):
            return False, "La porta deve essere un numero intero"
        
        if port < 1 or port > 65535:
            return False, "La porta deve essere compresa tra 1 e 65535"
        
        return True, "Porta valida"

class EncryptionConfigValidator:
    """Validatore specializzato per le configurazioni di crittografia."""
    
    @staticmethod
    def validate_fernet_key(key: str) -> Tuple[bool, str]:
        """
        Verifica se la chiave Fernet è valida.
        
        Args:
            key: Chiave Fernet codificata in base64
            
        Returns:
            Tuple[bool, str]: (valido, messaggio)
        """
        try:
            if isinstance(key, str):
                key_bytes = key.encode('utf-8')
            else:
                key_bytes = key
                
            # Verifica la lunghezza
            if len(key_bytes) != 32:
                return False, "La chiave deve essere lunga 32 byte dopo la decodifica"
            
            # Verifica che sia una chiave base64 valida
            base64.urlsafe_b64decode(key_bytes + b'=' * (4 - len(key_bytes) % 4))
            
            return True, "Chiave Fernet valida"
        except Exception as e:
            return False, f"Chiave Fernet non valida: {str(e)}"

# Aggiunta del metodo validate command per CLI
def validate_command():
    """Funzione per validare la configurazione da riga di comando."""
    config_manager = ConfigManager()
    config = config_manager.load()
    valid, errors = config_manager.validate()
    
    if valid:
        print("Configurazione valida!")
        return 0
    else:
        print("Errori di configurazione trovati:")
        for error in errors:
            print(f" - {error}")
        return 1

# Modifica della parte principale per supportare il comando validate
if __name__ == "__main__":
    import base64
    
    # Gestisci il comando validate
    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        sys.exit(validate_command())
    
    # Esecuzione del test originale se non viene specificato il comando validate
    print("Test del gestore configurazioni avanzato...")
    
    # Crea una configurazione di esempio
    config_manager = ConfigManager(format="yaml")
    
    # Imposta i valori predefiniti
    config_manager.set_defaults({
        "app_name": "M4Bot",
        "version": "1.0.0",
        "debug": False,
        "log_level": "INFO",
        "database": {
            "url": "postgresql://user:password@localhost:5432/m4bot",
            "pool_size": 10,
            "timeout": 30
        },
        "web": {
            "host": "0.0.0.0",
            "port": 5000,
            "workers": 4
        },
        "security": {
            "encryption_key": "",
            "session_timeout": 30,  # minuti
            "max_failed_logins": 5
        }
    })
    
    # Imposta le chiavi obbligatorie
    config_manager.set_required([
        "app_name", 
        "database.url",
        "security.encryption_key"
    ])
    
    # Aggiungi validatori personalizzati
    config_manager.add_validator("database.url", DatabaseConfigValidator.validate_postgresql_url)
    config_manager.add_validator("web.port", DatabaseConfigValidator.validate_port)
    
    # Carica la configurazione
    config = config_manager.load()
    
    # Mostra la configurazione
    print("\nConfigurazione caricata:")
    print(json.dumps(config, indent=2))
    
    # Valida la configurazione
    valid, errors = config_manager.validate()
    
    if valid:
        print("\nLa configurazione è valida!")
    else:
        print("\nLa configurazione non è valida:")
        for error in errors:
            print(f" - {error}")
    
    # Esempio di aggiornamento della configurazione
    config_manager.update({
        "security": {
            "encryption_key": base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8'),
            "session_timeout": 60,
            "max_failed_logins": 3
        }
    })
    
    # Salva la configurazione
    if config_manager.save():
        print("\nConfigurazione salvata con successo!")
    else:
        print("\nErrore nel salvataggio della configurazione!")
    
    # Crea un backup
    backup_path = config_manager.create_backup()
    if backup_path:
        print(f"\nBackup creato: {backup_path}")
    
    print("\nTest completati.") 