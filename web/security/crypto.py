"""
Sistema di crittografia per i dati sensibili di M4Bot

Questo modulo fornisce funzionalità per la crittografia e decrittografia dei dati sensibili
utilizzando algoritmi moderni e sicuri. Include anche gestione delle chiavi e funzioni di utilità.
"""

import os
import base64
import json
import logging
import secrets
import hashlib
import time
from typing import Dict, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key, load_pem_public_key,
    Encoding, PrivateFormat, PublicFormat, NoEncryption
)

# Configurazione logger
logger = logging.getLogger('m4bot.security.crypto')

# Constants
KEY_ROTATION_DAYS = 30  # Rotazione chiavi ogni 30 giorni
SALT_SIZE = 16  # Dimensione del salt in bytes
IV_SIZE = 16  # Dimensione IV in bytes
RSA_KEY_SIZE = 2048  # Dimensione chiavi RSA in bits

class CryptoManager:
    """Gestisce la crittografia e le chiavi per M4Bot."""
    
    def __init__(self, key_path: str = None, master_password: str = None):
        """
        Inizializza il gestore di crittografia.
        
        Args:
            key_path: Percorso dove salvare/caricare le chiavi
            master_password: Password master per proteggere le chiavi
        """
        self.key_path = key_path or os.path.expanduser('~/.m4bot/keys')
        self.master_password = master_password
        
        # Chiavi
        self.symmetric_key = None  # Chiave Fernet per crittografia simmetrica
        self.rsa_private_key = None  # Chiave privata RSA per crittografia asimmetrica
        self.rsa_public_key = None  # Chiave pubblica RSA
        
        # Metadati chiavi
        self.key_metadata = {
            'symmetric_created': None,
            'symmetric_rotated': None,
            'rsa_created': None,
            'key_version': 1
        }
        
        # Assicurati che la directory esista
        os.makedirs(self.key_path, exist_ok=True)
        
        # Inizializza
        self._load_or_generate_keys()
    
    def _derive_key_from_password(self, password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
        """
        Deriva una chiave di crittografia dalla password.
        
        Args:
            password: Password da cui derivare la chiave
            salt: Salt opzionale (generato se non fornito)
        
        Returns:
            Tuple[bytes, bytes]: (chiave derivata, salt)
        """
        if salt is None:
            salt = os.urandom(SALT_SIZE)
        
        # Usa PBKDF2 per derivare una chiave sicura
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # 32 bytes = chiave a 256 bit
            salt=salt,
            iterations=100000,  # Numero elevato di iterazioni per sicurezza
        )
        
        key = kdf.derive(password.encode())
        return key, salt
    
    def _load_or_generate_keys(self):
        """Carica le chiavi esistenti o genera nuove chiavi se necessario."""
        symmetric_key_file = os.path.join(self.key_path, 'symmetric.key')
        rsa_private_key_file = os.path.join(self.key_path, 'rsa_private.pem')
        rsa_public_key_file = os.path.join(self.key_path, 'rsa_public.pem')
        metadata_file = os.path.join(self.key_path, 'key_metadata.json')
        
        # Carica metadati se esistono
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, 'r') as f:
                    self.key_metadata = json.load(f)
            except Exception as e:
                logger.warning(f"Impossibile caricare i metadati delle chiavi: {e}")
                self.key_metadata = {
                    'symmetric_created': datetime.now().isoformat(),
                    'symmetric_rotated': None,
                    'rsa_created': datetime.now().isoformat(),
                    'key_version': 1
                }
        
        # Carica o genera chiave simmetrica
        if os.path.exists(symmetric_key_file):
            try:
                with open(symmetric_key_file, 'rb') as f:
                    key_data = f.read()
                
                # Se la chiave è protetta con password
                if self.master_password:
                    # I primi 16 bytes sono il salt
                    salt = key_data[:SALT_SIZE]
                    encrypted_key = key_data[SALT_SIZE:]
                    
                    # Deriva chiave dalla password
                    derived_key, _ = self._derive_key_from_password(self.master_password, salt)
                    
                    # Usa Fernet per decriptare la chiave
                    fernet = Fernet(base64.urlsafe_b64encode(derived_key))
                    self.symmetric_key = fernet.decrypt(encrypted_key)
                else:
                    self.symmetric_key = key_data
                
                # Verifica se è tempo di ruotare la chiave
                if self._should_rotate_symmetric_key():
                    logger.info("Rotazione pianificata della chiave simmetrica")
                    self._rotate_symmetric_key()
            except Exception as e:
                logger.error(f"Errore nel caricare la chiave simmetrica: {e}")
                self._generate_symmetric_key()
        else:
            self._generate_symmetric_key()
        
        # Carica o genera coppia di chiavi RSA
        if os.path.exists(rsa_private_key_file) and os.path.exists(rsa_public_key_file):
            try:
                with open(rsa_private_key_file, 'rb') as f:
                    private_key_data = f.read()
                
                with open(rsa_public_key_file, 'rb') as f:
                    public_key_data = f.read()
                
                # Se le chiavi sono protette con password
                if self.master_password:
                    self.rsa_private_key = load_pem_private_key(
                        private_key_data,
                        password=self.master_password.encode()
                    )
                else:
                    self.rsa_private_key = load_pem_private_key(
                        private_key_data,
                        password=None
                    )
                
                self.rsa_public_key = load_pem_public_key(public_key_data)
            except Exception as e:
                logger.error(f"Errore nel caricare le chiavi RSA: {e}")
                self._generate_rsa_keys()
        else:
            self._generate_rsa_keys()
        
        # Salva i metadati aggiornati
        self._save_metadata()
    
    def _generate_symmetric_key(self):
        """Genera una nuova chiave simmetrica Fernet."""
        logger.info("Generazione di una nuova chiave simmetrica")
        
        # Genera una chiave Fernet
        self.symmetric_key = Fernet.generate_key()
        
        # Aggiorna i metadati
        self.key_metadata['symmetric_created'] = datetime.now().isoformat()
        self.key_metadata['symmetric_rotated'] = None
        self.key_metadata['key_version'] += 1
        
        # Salva la chiave
        self._save_symmetric_key()
    
    def _save_symmetric_key(self):
        """Salva la chiave simmetrica in modo sicuro."""
        symmetric_key_file = os.path.join(self.key_path, 'symmetric.key')
        
        try:
            # Se abbiamo una password, crittografa la chiave prima di salvarla
            if self.master_password:
                # Deriva una chiave dalla password
                derived_key, salt = self._derive_key_from_password(self.master_password)
                
                # Usa Fernet per criptare la chiave
                fernet = Fernet(base64.urlsafe_b64encode(derived_key))
                encrypted_key = fernet.encrypt(self.symmetric_key)
                
                # Salva salt + chiave criptata
                with open(symmetric_key_file, 'wb') as f:
                    f.write(salt + encrypted_key)
            else:
                # Salva la chiave in chiaro
                with open(symmetric_key_file, 'wb') as f:
                    f.write(self.symmetric_key)
            
            # Imposta permessi restrittivi
            os.chmod(symmetric_key_file, 0o600)
            
            logger.info("Chiave simmetrica salvata con successo")
        except Exception as e:
            logger.error(f"Errore nel salvataggio della chiave simmetrica: {e}")
    
    def _generate_rsa_keys(self):
        """Genera una nuova coppia di chiavi RSA."""
        logger.info("Generazione di una nuova coppia di chiavi RSA")
        
        # Genera chiavi RSA
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=RSA_KEY_SIZE
        )
        public_key = private_key.public_key()
        
        self.rsa_private_key = private_key
        self.rsa_public_key = public_key
        
        # Aggiorna metadati
        self.key_metadata['rsa_created'] = datetime.now().isoformat()
        
        # Salva le chiavi
        self._save_rsa_keys()
    
    def _save_rsa_keys(self):
        """Salva le chiavi RSA in formato PEM."""
        private_key_file = os.path.join(self.key_path, 'rsa_private.pem')
        public_key_file = os.path.join(self.key_path, 'rsa_public.pem')
        
        try:
            # Serializza la chiave privata
            if self.master_password:
                # Con protezione password
                private_pem = self.rsa_private_key.private_bytes(
                    encoding=Encoding.PEM,
                    format=PrivateFormat.PKCS8,
                    encryption_algorithm=NoEncryption()
                )
            else:
                # Senza protezione password
                private_pem = self.rsa_private_key.private_bytes(
                    encoding=Encoding.PEM,
                    format=PrivateFormat.PKCS8,
                    encryption_algorithm=NoEncryption()
                )
            
            # Serializza la chiave pubblica
            public_pem = self.rsa_public_key.public_bytes(
                encoding=Encoding.PEM,
                format=PublicFormat.SubjectPublicKeyInfo
            )
            
            # Salva le chiavi
            with open(private_key_file, 'wb') as f:
                f.write(private_pem)
            
            with open(public_key_file, 'wb') as f:
                f.write(public_pem)
            
            # Imposta permessi restrittivi sulla chiave privata
            os.chmod(private_key_file, 0o600)
            
            logger.info("Chiavi RSA salvate con successo")
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle chiavi RSA: {e}")
    
    def _save_metadata(self):
        """Salva i metadati delle chiavi."""
        metadata_file = os.path.join(self.key_path, 'key_metadata.json')
        
        try:
            with open(metadata_file, 'w') as f:
                json.dump(self.key_metadata, f, indent=2)
            
            # Imposta permessi restrittivi
            os.chmod(metadata_file, 0o600)
        except Exception as e:
            logger.error(f"Errore nel salvataggio dei metadati delle chiavi: {e}")
    
    def _should_rotate_symmetric_key(self) -> bool:
        """Verifica se è tempo di ruotare la chiave simmetrica."""
        if 'symmetric_created' not in self.key_metadata:
            return False
        
        created_str = self.key_metadata['symmetric_created']
        try:
            created = datetime.fromisoformat(created_str)
            now = datetime.now()
            
            # Calcola l'età della chiave in giorni
            age_days = (now - created).days
            
            return age_days >= KEY_ROTATION_DAYS
        except Exception as e:
            logger.error(f"Errore nel calcolo dell'età della chiave: {e}")
            return False
    
    def _rotate_symmetric_key(self):
        """Ruota la chiave simmetrica mantenendo compatibilità con i dati esistenti."""
        logger.info("Rotazione della chiave simmetrica")
        
        # Archivia la vecchia chiave
        old_key = self.symmetric_key
        old_version = self.key_metadata['key_version']
        
        # Genera una nuova chiave
        self._generate_symmetric_key()
        
        # Archivia la vecchia chiave
        archived_key_file = os.path.join(
            self.key_path, 
            f'symmetric.key.v{old_version}'
        )
        
        try:
            with open(archived_key_file, 'wb') as f:
                f.write(old_key)
            
            # Imposta permessi restrittivi
            os.chmod(archived_key_file, 0o600)
            
            # Aggiorna metadati
            self.key_metadata['symmetric_rotated'] = datetime.now().isoformat()
            self._save_metadata()
            
            logger.info(f"Chiave simmetrica precedente archiviata come v{old_version}")
        except Exception as e:
            logger.error(f"Errore nell'archiviazione della chiave precedente: {e}")
    
    def encrypt_symmetric(self, data: Union[str, bytes, Dict]) -> str:
        """
        Crittografa dati usando la chiave simmetrica.
        
        Args:
            data: Dati da crittografare (stringa, bytes o dizionario)
            
        Returns:
            str: Dati crittografati in formato base64
        """
        try:
            # Converti i dati nel formato appropriato
            if isinstance(data, dict):
                plain_data = json.dumps(data).encode()
            elif isinstance(data, str):
                plain_data = data.encode()
            else:
                plain_data = data
            
            # Crittografa con Fernet
            f = Fernet(self.symmetric_key)
            encrypted_data = f.encrypt(plain_data)
            
            # Aggiungi metadati (versione chiave)
            metadata = {
                'v': self.key_metadata['key_version'],
                't': int(time.time())
            }
            metadata_json = json.dumps(metadata).encode()
            metadata_b64 = base64.urlsafe_b64encode(metadata_json).decode()
            
            # Formato: metadata_b64:encrypted_data_b64
            result = f"{metadata_b64}:{base64.urlsafe_b64encode(encrypted_data).decode()}"
            return result
        except Exception as e:
            logger.error(f"Errore nella crittografia simmetrica: {e}")
            raise
    
    def decrypt_symmetric(self, encrypted_data: str) -> Union[str, bytes, Dict]:
        """
        Decripta dati usando la chiave simmetrica.
        
        Args:
            encrypted_data: Dati crittografati (formato metadata_b64:encrypted_data_b64)
            
        Returns:
            Union[str, bytes, Dict]: Dati decriptati
        """
        try:
            # Estrai metadati e dati
            parts = encrypted_data.split(':', 1)
            
            if len(parts) != 2:
                raise ValueError("Formato dati crittografati non valido")
            
            metadata_b64, data_b64 = parts
            
            # Decodifica metadati
            metadata_json = base64.urlsafe_b64decode(metadata_b64.encode())
            metadata = json.loads(metadata_json)
            
            key_version = metadata.get('v', self.key_metadata['key_version'])
            
            # Decodifica dati
            encrypted_binary = base64.urlsafe_b64decode(data_b64.encode())
            
            # Seleziona chiave corretta in base alla versione
            if key_version == self.key_metadata['key_version']:
                key = self.symmetric_key
            else:
                # Carica chiave archiviata
                archived_key_file = os.path.join(
                    self.key_path, 
                    f'symmetric.key.v{key_version}'
                )
                
                if not os.path.exists(archived_key_file):
                    raise ValueError(f"Chiave versione {key_version} non trovata")
                
                with open(archived_key_file, 'rb') as f:
                    key = f.read()
            
            # Decripta
            f = Fernet(key)
            decrypted_data = f.decrypt(encrypted_binary)
            
            # Prova a interpretare come JSON
            try:
                result = json.loads(decrypted_data)
            except:
                # Altrimenti restituisci come stringa o bytes
                try:
                    result = decrypted_data.decode()
                except:
                    result = decrypted_data
            
            return result
        except InvalidToken:
            logger.error("Token di crittografia non valido o corrotto")
            raise
        except Exception as e:
            logger.error(f"Errore nella decrittografia simmetrica: {e}")
            raise
    
    def encrypt_asymmetric(self, data: Union[str, bytes, Dict]) -> str:
        """
        Crittografa dati usando la chiave pubblica RSA.
        
        Args:
            data: Dati da crittografare
            
        Returns:
            str: Dati crittografati in formato base64
        """
        try:
            # Converti i dati nel formato appropriato
            if isinstance(data, dict):
                plain_data = json.dumps(data).encode()
            elif isinstance(data, str):
                plain_data = data.encode()
            else:
                plain_data = data
            
            # Per dati di grandi dimensioni, utilizziamo una crittografia ibrida
            # 1. Genera una chiave simmetrica casuale
            sym_key = Fernet.generate_key()
            f = Fernet(sym_key)
            
            # 2. Crittografa i dati con la chiave simmetrica
            encrypted_data = f.encrypt(plain_data)
            
            # 3. Crittografa la chiave simmetrica con RSA
            encrypted_key = self.rsa_public_key.encrypt(
                sym_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # 4. Combina chiave criptata e dati criptati
            result = {
                'key': base64.b64encode(encrypted_key).decode(),
                'data': base64.b64encode(encrypted_data).decode(),
                'version': 1  # Per future compatibilità
            }
            
            return json.dumps(result)
        except Exception as e:
            logger.error(f"Errore nella crittografia asimmetrica: {e}")
            raise
    
    def decrypt_asymmetric(self, encrypted_data: str) -> Union[str, bytes, Dict]:
        """
        Decripta dati usando la chiave privata RSA.
        
        Args:
            encrypted_data: Dati crittografati (formato JSON con chiave e dati)
            
        Returns:
            Union[str, bytes, Dict]: Dati decriptati
        """
        try:
            # Parsing dei dati
            data = json.loads(encrypted_data)
            
            encrypted_key = base64.b64decode(data['key'])
            encrypted_data = base64.b64decode(data['data'])
            
            # 1. Decripta la chiave simmetrica con RSA
            sym_key = self.rsa_private_key.decrypt(
                encrypted_key,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=hashes.SHA256()),
                    algorithm=hashes.SHA256(),
                    label=None
                )
            )
            
            # 2. Decripta i dati con la chiave simmetrica
            f = Fernet(sym_key)
            decrypted_data = f.decrypt(encrypted_data)
            
            # 3. Interpreta il risultato
            try:
                result = json.loads(decrypted_data)
            except:
                try:
                    result = decrypted_data.decode()
                except:
                    result = decrypted_data
            
            return result
        except Exception as e:
            logger.error(f"Errore nella decrittografia asimmetrica: {e}")
            raise

# Funzioni di utilità

def hash_password(password: str) -> str:
    """
    Crea un hash sicuro della password per l'archiviazione.
    
    Args:
        password: Password da hashare
        
    Returns:
        str: Hash della password in formato sicuro (bcrypt)
    """
    # Import bcrypt solo quando necessario
    import bcrypt
    
    # Genera un salt casuale
    salt = bcrypt.gensalt()
    
    # Crea l'hash
    password_hash = bcrypt.hashpw(password.encode(), salt)
    
    return password_hash.decode()

def verify_password(password: str, password_hash: str) -> bool:
    """
    Verifica che una password corrisponda all'hash archiviato.
    
    Args:
        password: Password da verificare
        password_hash: Hash archiviato della password
        
    Returns:
        bool: True se la password è corretta
    """
    import bcrypt
    
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except Exception as e:
        logger.warning(f"Errore nella verifica della password: {e}")
        return False

def generate_secure_token(length: int = 32) -> str:
    """
    Genera un token sicuro per uso in sessioni, API, ecc.
    
    Args:
        length: Lunghezza del token in bytes
        
    Returns:
        str: Token in formato base64url
    """
    token_bytes = secrets.token_bytes(length)
    return base64.urlsafe_b64encode(token_bytes).decode().rstrip('=')

def create_crypto_manager(key_path: str = None, master_password: str = None) -> CryptoManager:
    """
    Factory per creare un'istanza del gestore di crittografia.
    
    Args:
        key_path: Percorso per le chiavi
        master_password: Password master
        
    Returns:
        CryptoManager: Istanza del gestore
    """
    return CryptoManager(key_path, master_password)

# Singola istanza per uso in tutta l'app
_crypto_manager = None

def get_crypto_manager(key_path: str = None, master_password: str = None) -> CryptoManager:
    """
    Ottiene l'istanza singola del gestore di crittografia.
    
    Args:
        key_path: Percorso per le chiavi (solo per prima inizializzazione)
        master_password: Password master (solo per prima inizializzazione)
        
    Returns:
        CryptoManager: Istanza del gestore
    """
    global _crypto_manager
    
    if _crypto_manager is None:
        _crypto_manager = create_crypto_manager(key_path, master_password)
    
    return _crypto_manager 