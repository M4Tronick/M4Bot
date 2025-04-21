#!/usr/bin/env python3
"""
Key Rotation - Sistema di rotazione automatica delle chiavi di crittografia
per M4Bot in ambiente Linux.

Questo script gestisce la rotazione sicura delle chiavi di crittografia,
mantenendo la possibilità di decifrare i dati vecchi e ricifrando
progressivamente i dati con la nuova chiave.
"""

import os
import sys
import json
import time
import logging
import argparse
import asyncio
import base64
import secrets
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

import asyncpg
import dotenv
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join("logs", "key_rotation.log")),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("KeyRotation")

class KeyRotationManager:
    """
    Gestisce la rotazione sicura delle chiavi di crittografia
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Inizializza il gestore della rotazione delle chiavi
        
        Args:
            config: Configurazione del manager
        """
        self.config = config
        self.db_pool = None
        self.connection_string = config.get("database_url", "")
        self.key_file = config.get("key_file", "security/encryption_keys.json")
        self.env_file = config.get("env_file", ".env")
        self.backup_dir = config.get("backup_dir", "security/backups")
        
        # Predefiniti per configurazione
        self.rotation_interval = config.get("rotation_interval", 90)  # giorni
        self.key_history_length = config.get("key_history_length", 5)  # numero di chiavi vecchie da mantenere
        
        # Chiavi di crittografia
        self.current_key = None
        self.old_keys = []
        self.keys_metadata = {
            "current_key": {
                "id": None,
                "created_at": None,
                "rotated_at": None,
            },
            "old_keys": []
        }
        
        # Crea directory per i backup
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Crea directory per le chiavi
        os.makedirs(os.path.dirname(self.key_file), exist_ok=True)
        
        logger.info("KeyRotationManager inizializzato")
    
    async def connect_to_database(self) -> bool:
        """
        Connette al database PostgreSQL
        
        Returns:
            bool: True se la connessione è riuscita, False altrimenti
        """
        try:
            # Connessione al database
            self.db_pool = await asyncpg.create_pool(
                dsn=self.connection_string,
                min_size=1,
                max_size=5
            )
            
            # Verifica la connessione
            async with self.db_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
                
            logger.info("Connessione al database stabilita")
            
            # Inizializza la tabella delle chiavi se non esiste
            await self._initialize_key_table()
            
            return True
        except Exception as e:
            logger.error(f"Errore nella connessione al database: {e}")
            return False
    
    async def _initialize_key_table(self):
        """Inizializza la tabella per le chiavi di crittografia"""
        try:
            async with self.db_pool.acquire() as conn:
                # Crea la tabella se non esiste
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS encryption_keys (
                        id SERIAL PRIMARY KEY,
                        key_id VARCHAR(36) UNIQUE NOT NULL,
                        key_value TEXT NOT NULL,
                        is_current BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        rotated_at TIMESTAMP WITH TIME ZONE
                    )
                ''')
                
                logger.info("Tabella delle chiavi di crittografia inizializzata")
        except Exception as e:
            logger.error(f"Errore nell'inizializzazione della tabella delle chiavi: {e}")
    
    async def load_keys(self) -> bool:
        """
        Carica le chiavi di crittografia da database o file
        
        Returns:
            bool: True se le chiavi sono state caricate con successo, False altrimenti
        """
        try:
            # Prova prima a caricare da database
            if self.db_pool:
                keys_loaded = await self._load_keys_from_database()
                if keys_loaded:
                    return True
            
            # Se non ci sono chiavi nel database, carica dal file
            keys_loaded = self._load_keys_from_file()
            if keys_loaded:
                return True
            
            # Se non ci sono chiavi né nel database né nel file, carica da .env
            keys_loaded = self._load_key_from_env()
            if keys_loaded:
                # Salva le chiavi per usi futuri
                await self._save_keys()
                return True
            
            # Se non ci sono chiavi da nessuna parte, genera una nuova chiave
            self._generate_new_key()
            await self._save_keys()
            
            logger.info("Nuova chiave di crittografia generata")
            return True
        except Exception as e:
            logger.error(f"Errore nel caricamento delle chiavi: {e}")
            return False
    
    async def _load_keys_from_database(self) -> bool:
        """
        Carica le chiavi di crittografia dal database
        
        Returns:
            bool: True se le chiavi sono state caricate con successo, False altrimenti
        """
        try:
            async with self.db_pool.acquire() as conn:
                # Carica la chiave corrente
                current_key_row = await conn.fetchrow('''
                    SELECT id, key_id, key_value, created_at, rotated_at
                    FROM encryption_keys
                    WHERE is_current = TRUE
                ''')
                
                if current_key_row:
                    self.current_key = current_key_row["key_value"]
                    self.keys_metadata["current_key"] = {
                        "id": current_key_row["key_id"],
                        "created_at": current_key_row["created_at"].isoformat() if current_key_row["created_at"] else None,
                        "rotated_at": current_key_row["rotated_at"].isoformat() if current_key_row["rotated_at"] else None,
                    }
                    
                    # Carica le chiavi vecchie
                    old_keys_rows = await conn.fetch('''
                        SELECT id, key_id, key_value, created_at, rotated_at
                        FROM encryption_keys
                        WHERE is_current = FALSE
                        ORDER BY created_at DESC
                        LIMIT $1
                    ''', self.key_history_length)
                    
                    self.old_keys = [row["key_value"] for row in old_keys_rows]
                    self.keys_metadata["old_keys"] = [
                        {
                            "id": row["key_id"],
                            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                            "rotated_at": row["rotated_at"].isoformat() if row["rotated_at"] else None,
                        }
                        for row in old_keys_rows
                    ]
                    
                    logger.info(f"Chiavi caricate dal database: {len(self.old_keys) + 1} chiavi")
                    return True
                    
                return False
        except Exception as e:
            logger.error(f"Errore nel caricamento delle chiavi dal database: {e}")
            return False
    
    def _load_keys_from_file(self) -> bool:
        """
        Carica le chiavi di crittografia da file
        
        Returns:
            bool: True se le chiavi sono state caricate con successo, False altrimenti
        """
        try:
            if os.path.exists(self.key_file):
                with open(self.key_file, "r") as f:
                    keys_data = json.load(f)
                
                self.current_key = keys_data.get("current_key")
                self.old_keys = keys_data.get("old_keys", [])
                self.keys_metadata = keys_data.get("metadata", {
                    "current_key": {
                        "id": None,
                        "created_at": None,
                        "rotated_at": None,
                    },
                    "old_keys": []
                })
                
                logger.info(f"Chiavi caricate dal file: {len(self.old_keys) + 1} chiavi")
                return bool(self.current_key)
                
            return False
        except Exception as e:
            logger.error(f"Errore nel caricamento delle chiavi dal file: {e}")
            return False
    
    def _load_key_from_env(self) -> bool:
        """
        Carica la chiave di crittografia da .env
        
        Returns:
            bool: True se la chiave è stata caricata con successo, False altrimenti
        """
        try:
            # Carica le variabili d'ambiente
            dotenv.load_dotenv(self.env_file)
            
            # Ottieni la chiave
            env_key = os.getenv("ENCRYPTION_KEY")
            if env_key:
                # Imposta come chiave corrente
                self.current_key = env_key
                
                # Crea i metadati
                self.keys_metadata["current_key"] = {
                    "id": self._generate_key_id(),
                    "created_at": datetime.now().isoformat(),
                    "rotated_at": None,
                }
                
                logger.info("Chiave caricata da .env")
                return True
                
            return False
        except Exception as e:
            logger.error(f"Errore nel caricamento della chiave da .env: {e}")
            return False
    
    def _generate_new_key(self):
        """Genera una nuova chiave di crittografia"""
        try:
            # Se c'è già una chiave corrente, spostala nelle chiavi vecchie
            if self.current_key:
                # Aggiorna i metadati della chiave corrente
                if "id" in self.keys_metadata["current_key"]:
                    self.keys_metadata["current_key"]["rotated_at"] = datetime.now().isoformat()
                    
                    # Sposta la chiave corrente nelle chiavi vecchie
                    self.old_keys.insert(0, self.current_key)
                    self.keys_metadata["old_keys"].insert(0, self.keys_metadata["current_key"])
                    
                    # Limita il numero di chiavi vecchie
                    if len(self.old_keys) > self.key_history_length:
                        self.old_keys = self.old_keys[:self.key_history_length]
                        self.keys_metadata["old_keys"] = self.keys_metadata["old_keys"][:self.key_history_length]
            
            # Genera una nuova chiave
            new_key = Fernet.generate_key().decode()
            
            # Imposta come chiave corrente
            self.current_key = new_key
            
            # Aggiorna i metadati
            self.keys_metadata["current_key"] = {
                "id": self._generate_key_id(),
                "created_at": datetime.now().isoformat(),
                "rotated_at": None,
            }
            
            logger.info("Nuova chiave di crittografia generata")
        except Exception as e:
            logger.error(f"Errore nella generazione della nuova chiave: {e}")
    
    def _generate_key_id(self) -> str:
        """
        Genera un ID univoco per la chiave
        
        Returns:
            str: ID univoco
        """
        return f"key_{int(time.time())}_{secrets.token_hex(4)}"
    
    async def _save_keys(self):
        """Salva le chiavi di crittografia su database e file"""
        try:
            # Salva su database se disponibile
            if self.db_pool:
                await self._save_keys_to_database()
            
            # Salva su file come backup
            self._save_keys_to_file()
            
            # Salva nella ENV
            self._update_env_file()
            
            logger.info("Chiavi salvate con successo")
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle chiavi: {e}")
    
    async def _save_keys_to_database(self):
        """Salva le chiavi di crittografia nel database"""
        try:
            async with self.db_pool.acquire() as conn:
                # Crea una transazione
                async with conn.transaction():
                    # Verifica se la chiave corrente esiste già
                    current_key_id = self.keys_metadata["current_key"]["id"]
                    existing_key = await conn.fetchval('''
                        SELECT id FROM encryption_keys WHERE key_id = $1
                    ''', current_key_id)
                    
                    if existing_key:
                        # Aggiorna la chiave esistente
                        await conn.execute('''
                            UPDATE encryption_keys
                            SET key_value = $1, is_current = TRUE
                            WHERE key_id = $2
                        ''', self.current_key, current_key_id)
                    else:
                        # Inserisci la nuova chiave
                        created_at = datetime.fromisoformat(self.keys_metadata["current_key"]["created_at"]) if self.keys_metadata["current_key"]["created_at"] else datetime.now()
                        
                        await conn.execute('''
                            INSERT INTO encryption_keys (key_id, key_value, is_current, created_at)
                            VALUES ($1, $2, TRUE, $3)
                        ''', current_key_id, self.current_key, created_at)
                    
                    # Imposta tutte le altre chiavi come non correnti
                    await conn.execute('''
                        UPDATE encryption_keys
                        SET is_current = FALSE
                        WHERE key_id != $1
                    ''', current_key_id)
                    
                    # Salva le chiavi vecchie se non esistono già
                    for i, old_key in enumerate(self.old_keys):
                        old_key_id = self.keys_metadata["old_keys"][i]["id"]
                        
                        # Verifica se la chiave vecchia esiste già
                        existing_old_key = await conn.fetchval('''
                            SELECT id FROM encryption_keys WHERE key_id = $1
                        ''', old_key_id)
                        
                        if not existing_old_key:
                            # Inserisci la chiave vecchia
                            created_at = datetime.fromisoformat(self.keys_metadata["old_keys"][i]["created_at"]) if self.keys_metadata["old_keys"][i]["created_at"] else None
                            rotated_at = datetime.fromisoformat(self.keys_metadata["old_keys"][i]["rotated_at"]) if self.keys_metadata["old_keys"][i]["rotated_at"] else None
                            
                            await conn.execute('''
                                INSERT INTO encryption_keys (key_id, key_value, is_current, created_at, rotated_at)
                                VALUES ($1, $2, FALSE, $3, $4)
                            ''', old_key_id, old_key, created_at, rotated_at)
            
            logger.info("Chiavi salvate nel database")
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle chiavi nel database: {e}")
    
    def _save_keys_to_file(self):
        """Salva le chiavi di crittografia su file"""
        try:
            # Prepara i dati da salvare
            keys_data = {
                "current_key": self.current_key,
                "old_keys": self.old_keys,
                "metadata": self.keys_metadata
            }
            
            # Salva su file
            with open(self.key_file, "w") as f:
                json.dump(keys_data, f, indent=2)
            
            # Imposta i permessi corretti (solo lettura per il proprietario)
            os.chmod(self.key_file, 0o600)
            
            logger.info("Chiavi salvate su file")
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle chiavi su file: {e}")
    
    def _update_env_file(self):
        """Aggiorna il file .env con la chiave corrente"""
        try:
            if not os.path.exists(self.env_file):
                # Crea il file .env se non esiste
                with open(self.env_file, "w") as f:
                    f.write(f"ENCRYPTION_KEY={self.current_key}\n")
            else:
                # Carica il file .env attuale
                with open(self.env_file, "r") as f:
                    lines = f.readlines()
                
                # Cerca la riga con ENCRYPTION_KEY
                key_line_index = None
                for i, line in enumerate(lines):
                    if line.startswith("ENCRYPTION_KEY="):
                        key_line_index = i
                        break
                
                # Aggiorna o aggiungi la chiave
                if key_line_index is not None:
                    lines[key_line_index] = f"ENCRYPTION_KEY={self.current_key}\n"
                else:
                    lines.append(f"ENCRYPTION_KEY={self.current_key}\n")
                
                # Salva il file .env
                with open(self.env_file, "w") as f:
                    f.writelines(lines)
            
            # Imposta i permessi corretti
            os.chmod(self.env_file, 0o600)
            
            logger.info("File .env aggiornato con la nuova chiave")
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento del file .env: {e}")
    
    def _backup_env_file(self):
        """Crea un backup del file .env"""
        try:
            if os.path.exists(self.env_file):
                # Nome del file di backup
                backup_file = os.path.join(
                    self.backup_dir, 
                    f"env_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.bak"
                )
                
                # Copia il file
                with open(self.env_file, "r") as src, open(backup_file, "w") as dst:
                    dst.write(src.read())
                
                # Imposta i permessi corretti
                os.chmod(backup_file, 0o600)
                
                logger.info(f"Backup del file .env creato: {backup_file}")
                return True
            
            return False
        except Exception as e:
            logger.error(f"Errore nella creazione del backup del file .env: {e}")
            return False
    
    async def check_and_rotate_if_needed(self) -> bool:
        """
        Verifica se è necessario ruotare la chiave e la ruota se necessario
        
        Returns:
            bool: True se la chiave è stata ruotata, False altrimenti
        """
        try:
            # Verifica se ci sono chiavi
            if not self.current_key:
                logger.warning("Nessuna chiave disponibile. Generazione nuova chiave...")
                self._generate_new_key()
                await self._save_keys()
                return True
            
            # Verifica quando è stata creata la chiave corrente
            if self.keys_metadata["current_key"]["created_at"]:
                created_at = datetime.fromisoformat(self.keys_metadata["current_key"]["created_at"])
                days_since_creation = (datetime.now() - created_at).days
                
                if days_since_creation >= self.rotation_interval:
                    logger.info(f"La chiave corrente ha {days_since_creation} giorni. Rotazione in corso...")
                    
                    # Crea backup prima della rotazione
                    self._backup_env_file()
                    
                    # Genera una nuova chiave
                    self._generate_new_key()
                    
                    # Salva le chiavi
                    await self._save_keys()
                    
                    logger.info("Rotazione della chiave completata con successo")
                    return True
                else:
                    logger.info(f"La chiave corrente ha {days_since_creation} giorni. "
                               f"Rotazione prevista tra {self.rotation_interval - days_since_creation} giorni.")
                    return False
            else:
                logger.warning("Data di creazione della chiave corrente non disponibile. Rotazione in corso...")
                
                # Crea backup prima della rotazione
                self._backup_env_file()
                
                # Genera una nuova chiave
                self._generate_new_key()
                
                # Salva le chiavi
                await self._save_keys()
                
                logger.info("Rotazione della chiave completata con successo")
                return True
        except Exception as e:
            logger.error(f"Errore nella rotazione della chiave: {e}")
            return False
    
    async def reencrypt_database_data(self) -> Dict[str, Any]:
        """
        Ricifrare i dati nel database con la nuova chiave
        
        Returns:
            Dict[str, Any]: Risultati della ricifratura
        """
        if not self.db_pool or not self.current_key:
            logger.error("Database non connesso o chiave non disponibile")
            return {"status": "error", "message": "Database non connesso o chiave non disponibile"}
        
        results = {
            "status": "success",
            "tables_processed": 0,
            "rows_processed": 0,
            "errors": []
        }
        
        try:
            async with self.db_pool.acquire() as conn:
                # 1. Elenca le tabelle con colonne criptate (si presume che abbiano il suffisso '_encrypted')
                tables = await conn.fetch('''
                    SELECT table_name, column_name 
                    FROM information_schema.columns 
                    WHERE column_name LIKE '%\_encrypted' ESCAPE '\\' 
                    AND table_schema = 'public'
                ''')
                
                if not tables:
                    logger.info("Nessuna colonna criptata trovata nel database")
                    return {"status": "success", "message": "Nessuna colonna criptata trovata"}
                
                # Raggruppa le colonne per tabella
                encrypted_columns_by_table = {}
                for row in tables:
                    table_name = row["table_name"]
                    column_name = row["column_name"]
                    
                    if table_name not in encrypted_columns_by_table:
                        encrypted_columns_by_table[table_name] = []
                    
                    encrypted_columns_by_table[table_name].append(column_name)
                
                # Crea istanze di Fernet per la decifratura e la cifratura
                current_fernet = Fernet(self.current_key.encode())
                old_fernets = [Fernet(key.encode()) for key in self.old_keys]
                
                # 2. Per ogni tabella, ricicla i dati crittografati
                for table_name, columns in encrypted_columns_by_table.items():
                    logger.info(f"Elaborazione tabella {table_name}, colonne: {columns}")
                    
                    try:
                        # Ottieni tutti i record
                        rows = await conn.fetch(f"SELECT id, {', '.join(columns)} FROM {table_name}")
                        
                        # Contatore per i record elaborati
                        processed_rows = 0
                        
                        # Elabora ciascun record
                        for row in rows:
                            row_id = row["id"]
                            
                            # Set di aggiornamento per la query
                            update_set = []
                            update_values = []
                            
                            for col_idx, column in enumerate(columns):
                                encrypted_value = row[column]
                                
                                # Salta se il valore è NULL
                                if encrypted_value is None:
                                    continue
                                
                                # Tenta di decifrare con la chiave corrente
                                try:
                                    # Se già cifrato con la chiave corrente, salta
                                    decrypted_value = current_fernet.decrypt(encrypted_value.encode())
                                    # È già cifrato con la chiave corrente, niente da fare
                                    continue
                                except Exception:
                                    # Non è cifrato con la chiave corrente, prova con le chiavi vecchie
                                    decrypted_value = None
                                    
                                    for old_fernet in old_fernets:
                                        try:
                                            decrypted_value = old_fernet.decrypt(encrypted_value.encode())
                                            break
                                        except Exception:
                                            continue
                                    
                                    # Se non è stato possibile decifrare, salta
                                    if decrypted_value is None:
                                        logger.warning(f"Impossibile decifrare il valore nella tabella {table_name}, "
                                                     f"colonna {column}, id {row_id}")
                                        continue
                                
                                # Cifra nuovamente con la chiave corrente
                                new_encrypted_value = current_fernet.encrypt(decrypted_value).decode()
                                
                                # Aggiungi alla query di aggiornamento
                                update_set.append(f"{column} = ${len(update_values) + 1}")
                                update_values.append(new_encrypted_value)
                            
                            # Se ci sono valori da aggiornare, esegui la query
                            if update_set:
                                update_query = f"UPDATE {table_name} SET {', '.join(update_set)} WHERE id = ${len(update_values) + 1}"
                                update_values.append(row_id)
                                
                                await conn.execute(update_query, *update_values)
                                processed_rows += 1
                        
                        # Aggiorna i risultati
                        results["tables_processed"] += 1
                        results["rows_processed"] += processed_rows
                        
                        logger.info(f"Elaborati {processed_rows} record nella tabella {table_name}")
                    except Exception as e:
                        error_msg = f"Errore nell'elaborazione della tabella {table_name}: {e}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)
                
                # Aggiorna lo stato finale
                if results["errors"]:
                    results["status"] = "partial" if results["tables_processed"] > 0 else "error"
                
                return results
        except Exception as e:
            logger.error(f"Errore nella ricifratura dei dati: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_encryption_fernet(self) -> Tuple[Fernet, List[Fernet]]:
        """
        Ottiene istanze Fernet per la cifratura/decifratura
        
        Returns:
            Tuple[Fernet, List[Fernet]]: Istanza Fernet per la chiave corrente e lista di istanze per le chiavi vecchie
        """
        try:
            current_fernet = Fernet(self.current_key.encode())
            old_fernets = [Fernet(key.encode()) for key in self.old_keys]
            
            return current_fernet, old_fernets
        except Exception as e:
            logger.error(f"Errore nella creazione delle istanze Fernet: {e}")
            raise ValueError("Impossibile creare istanze Fernet valide") from e
    
    def encrypt_data(self, data: str) -> str:
        """
        Cifra un dato con la chiave corrente
        
        Args:
            data: Dato da cifrare
            
        Returns:
            str: Dato cifrato
        """
        try:
            if not self.current_key:
                raise ValueError("Nessuna chiave di crittografia disponibile")
            
            fernet = Fernet(self.current_key.encode())
            return fernet.encrypt(data.encode()).decode()
        except Exception as e:
            logger.error(f"Errore nella cifratura dei dati: {e}")
            raise ValueError("Impossibile cifrare i dati") from e
    
    def decrypt_data(self, encrypted_data: str) -> str:
        """
        Decifra un dato provando prima con la chiave corrente e poi con le chiavi vecchie
        
        Args:
            encrypted_data: Dato cifrato
            
        Returns:
            str: Dato decifrato
        """
        try:
            if not self.current_key:
                raise ValueError("Nessuna chiave di crittografia disponibile")
            
            # Prova con la chiave corrente
            try:
                fernet = Fernet(self.current_key.encode())
                return fernet.decrypt(encrypted_data.encode()).decode()
            except Exception:
                # Prova con le chiavi vecchie
                for old_key in self.old_keys:
                    try:
                        fernet = Fernet(old_key.encode())
                        return fernet.decrypt(encrypted_data.encode()).decode()
                    except Exception:
                        continue
                
                # Se qui, non è stato possibile decifrare
                raise ValueError("Impossibile decifrare i dati con nessuna delle chiavi disponibili")
        except Exception as e:
            logger.error(f"Errore nella decifratura dei dati: {e}")
            raise ValueError("Impossibile decifrare i dati") from e

async def main():
    """Funzione principale"""
    parser = argparse.ArgumentParser(description="Key Rotation - Sistema di rotazione delle chiavi di crittografia")
    parser.add_argument("--force", action="store_true", help="Forza la rotazione anche se non è necessaria")
    parser.add_argument("--interval", type=int, default=90, help="Intervallo di rotazione in giorni")
    parser.add_argument("--history", type=int, default=5, help="Numero di chiavi vecchie da mantenere")
    parser.add_argument("--db-url", help="URL di connessione al database")
    parser.add_argument("--env-file", default=".env", help="File .env da aggiornare")
    parser.add_argument("--key-file", default="security/encryption_keys.json", help="File per il backup delle chiavi")
    parser.add_argument("--reencrypt", action="store_true", help="Ricifrare i dati nel database")
    
    args = parser.parse_args()
    
    # Carica le variabili d'ambiente
    dotenv.load_dotenv(args.env_file)
    
    # Configura il gestore delle chiavi
    config = {
        "database_url": args.db_url or os.getenv("DATABASE_URL"),
        "env_file": args.env_file,
        "key_file": args.key_file,
        "rotation_interval": args.interval,
        "key_history_length": args.history,
        "backup_dir": "security/backups"
    }
    
    # Crea il gestore
    key_manager = KeyRotationManager(config)
    
    # Connetti al database se fornito
    if config["database_url"]:
        if not await key_manager.connect_to_database():
            logger.error("Impossibile connettersi al database. Continuazione senza database.")
    else:
        logger.warning("URL del database non fornito. Continuazione senza database.")
    
    # Carica le chiavi
    if not await key_manager.load_keys():
        logger.error("Impossibile caricare le chiavi. Uscita.")
        return
    
    # Verifica se è necessario ruotare la chiave
    key_rotated = False
    if args.force:
        logger.info("Rotazione forzata della chiave...")
        key_rotated = await key_manager.check_and_rotate_if_needed() or True
    else:
        key_rotated = await key_manager.check_and_rotate_if_needed()
    
    # Ricicla i dati se richiesto e se la chiave è stata ruotata o se è forzato
    if args.reencrypt and (key_rotated or args.force) and config["database_url"]:
        logger.info("Ricifratura dei dati nel database...")
        results = await key_manager.reencrypt_database_data()
        
        if results["status"] == "success":
            logger.info(f"Ricifratura completata. Tabelle elaborate: {results['tables_processed']}, "
                      f"Record elaborati: {results['rows_processed']}")
        else:
            logger.warning(f"Ricifratura parziale o fallita. Stato: {results['status']}")
            if "errors" in results and results["errors"]:
                for error in results["errors"]:
                    logger.error(f"Errore durante la ricifratura: {error}")

if __name__ == "__main__":
    asyncio.run(main()) 