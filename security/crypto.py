#!/usr/bin/env python3
"""
M4Bot - Sistema di Crittografia End-to-End

Questo modulo implementa funzionalità di crittografia avanzate per proteggere
i dati sensibili nell'applicazione, inclusi:
- Crittografia simmetrica AES per dati in database
- Crittografia di campi sensibili
- Derivazione sicura delle chiavi
- Rotazione automatica delle chiavi
- Hashing sicuro per password e token
"""

import os
import base64
import json
import logging
import hmac
import hashlib
import secrets
import time
from typing import Dict, Any, Optional, Tuple, List, Union
from datetime import datetime, timedelta
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa, padding as asymmetric_padding
from cryptography.hazmat.primitives.serialization import (
    load_pem_private_key, load_pem_public_key,
    Encoding, PrivateFormat, PublicFormat, NoEncryption
)
from cryptography.hazmat.backends import default_backend

# Inizializzazione logger
logger = logging.getLogger('m4bot.security.crypto')

# Configurazione
DEFAULT_KEY_ROTATION_DAYS = 30
DEFAULT_KEY_STRENGTH = 256  # AES-256
PASSWORD_HASH_ITERATIONS = 600_000  # Alto numero di iterazioni per sicurezza
SALT_SIZE_BYTES = 16
IV_SIZE_BYTES = 16

# Configurazione directory delle chiavi
KEY_DIR = Path("security/keys")
KEY_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class EncryptionConfig:
    """Configurazione per il sistema di crittografia."""
    symmetric_key_size: int = 32  # 256 bit
    rsa_key_size: int = 3072
    pbkdf2_iterations: int = 100000
    password_hash_algorithm: str = "argon2"
    hmac_algorithm: str = "sha256"

# Configurazione globale
config = EncryptionConfig()

# Variabili globali per il keystore
_key_store = {}  # Memorizza le chiavi in RAM (in produzione usare un vault)
_master_key = None  # Chiave principale per proteggere le altre
_key_creation_times = {}  # Timestamp di creazione delle chiavi

class CryptoError(Exception):
    """Eccezione base per gli errori di crittografia."""
    pass

class KeyNotFoundError(CryptoError):
    """Eccezione per chiave non trovata."""
    pass

class DecryptionError(CryptoError):
    """Eccezione per errore di decrittografia."""
    pass

class InvalidTokenError(CryptoError):
    """Eccezione per token invalido."""
    pass

# Funzioni di utility

def generate_key(length_bits: int = DEFAULT_KEY_STRENGTH) -> bytes:
    """
    Genera una chiave crittografica sicura con la lunghezza specificata
    
    Args:
        length_bits: Lunghezza della chiave in bit (default: 256)
        
    Returns:
        bytes: Chiave crittografica generata
    """
    bytes_length = length_bits // 8
    return secrets.token_bytes(bytes_length)

def derive_key_from_password(password: str, salt: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    """
    Deriva una chiave crittografica da una password usando PBKDF2
    
    Args:
        password: Password da cui derivare la chiave
        salt: Salt opzionale (se None, ne viene generato uno nuovo)
        
    Returns:
        Tuple[bytes, bytes]: (chiave_derivata, salt)
    """
    if salt is None:
        salt = os.urandom(SALT_SIZE_BYTES)
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,  # 256 bit
        salt=salt,
        iterations=PASSWORD_HASH_ITERATIONS,
    )
    
    key = kdf.derive(password.encode())
    return key, salt

def derive_key_from_master(key_id: str, master_key: bytes) -> bytes:
    """
    Deriva una chiave specifica dall'identificatore e dalla chiave master
    
    Args:
        key_id: Identificatore univoco della chiave
        master_key: Chiave master
        
    Returns:
        bytes: Chiave derivata
    """
    # Usiamo HMAC-SHA256 per derivare una chiave dall'ID e dalla chiave master
    h = hmac.new(master_key, key_id.encode(), hashlib.sha256)
    return h.digest()

def hash_password(password: str) -> str:
    """
    Calcola l'hash sicuro di una password
    
    Args:
        password: Password da hashare
        
    Returns:
        str: Hash della password in formato base64
    """
    salt = os.urandom(SALT_SIZE_BYTES)
    key, _ = derive_key_from_password(password, salt)
    
    # Combina salt e chiave in un unico valore
    result = salt + key
    
    # Codifica in base64 per archiviazione
    return base64.b64encode(result).decode('utf-8')

def verify_password(password: str, password_hash: str) -> bool:
    """
    Verifica se una password corrisponde al suo hash
    
    Args:
        password: Password da verificare
        password_hash: Hash della password precedentemente calcolato
        
    Returns:
        bool: True se la password è corretta, False altrimenti
    """
    try:
        # Decodifica l'hash
        hash_bytes = base64.b64decode(password_hash)
        
        # Estrae il salt (primi 16 bytes)
        salt = hash_bytes[:SALT_SIZE_BYTES]
        stored_key = hash_bytes[SALT_SIZE_BYTES:]
        
        # Ricalcola la chiave con la password fornita e confronta
        derived_key, _ = derive_key_from_password(password, salt)
        
        # Confronto sicuro che usa tecniche di timing-attack resistance
        return hmac.compare_digest(derived_key, stored_key)
    except Exception as e:
        logger.error(f"Errore nella verifica della password: {e}")
        return False

def initialize_master_key(password: Optional[str] = None) -> bytes:
    """
    Inizializza la chiave master
    
    Args:
        password: Password opzionale per derivare la chiave master
                  Se None, genera una chiave casuale
                  
    Returns:
        bytes: Chiave master generata
    """
    global _master_key
    
    if password:
        # Deriva la chiave master dalla password
        key, _ = derive_key_from_password(password)
    else:
        # Genera una chiave master casuale
        key = generate_key()
    
    _master_key = key
    return key

def get_master_key() -> bytes:
    """
    Restituisce la chiave master, inizializzandola se necessario
    
    Returns:
        bytes: Chiave master
    """
    global _master_key
    
    if _master_key is None:
        # In un sistema reale, la chiave master verrebbe recuperata da un sistema sicuro
        # come un vault di chiavi o un HSM, o derivata da una chiave di avvio
        logger.warning("Inizializzazione automatica della chiave master - IN PRODUZIONE USARE UN VAULT")
        _master_key = initialize_master_key()
    
    return _master_key

# Gestione delle chiavi
def register_key(key_id: str, key: Optional[bytes] = None, rotation_days: int = DEFAULT_KEY_ROTATION_DAYS) -> bytes:
    """
    Registra una chiave nel keystore
    
    Args:
        key_id: Identificatore univoco della chiave
        key: Chiave da registrare (se None, viene generata)
        rotation_days: Giorni dopo i quali la chiave deve essere ruotata
        
    Returns:
        bytes: Chiave registrata
    """
    if key is None:
        key = generate_key()
    
    _key_store[key_id] = key
    _key_creation_times[key_id] = time.time()
    
    logger.info(f"Chiave '{key_id}' registrata con successo")
    return key

def get_key(key_id: str) -> bytes:
    """
    Recupera una chiave dal keystore
    
    Args:
        key_id: Identificatore della chiave
        
    Returns:
        bytes: Chiave recuperata
        
    Raises:
        KeyNotFoundError: Se la chiave non esiste
    """
    if key_id not in _key_store:
        # Prova a derivare la chiave dalla chiave master
        master_key = get_master_key()
        derived_key = derive_key_from_master(key_id, master_key)
        register_key(key_id, derived_key)
        
        # Registra nella console che stiamo usando una chiave derivata
        logger.info(f"Chiave '{key_id}' derivata dalla chiave master")
    
    return _key_store[key_id]

def rotate_key(key_id: str) -> bytes:
    """
    Ruota una chiave esistente generandone una nuova
    
    Args:
        key_id: Identificatore della chiave
        
    Returns:
        bytes: Nuova chiave
    """
    # Genera una nuova chiave
    new_key = generate_key()
    
    # Archivia la chiave precedente con un suffisso (per decrittografia legacy)
    if key_id in _key_store:
        old_key = _key_store[key_id]
        _key_store[f"{key_id}_old"] = old_key
    
    # Registra la nuova chiave
    _key_store[key_id] = new_key
    _key_creation_times[key_id] = time.time()
    
    logger.info(f"Chiave '{key_id}' ruotata con successo")
    return new_key

def check_key_rotation() -> List[str]:
    """
    Controlla quali chiavi devono essere ruotate a causa della scadenza
    
    Returns:
        List[str]: Lista di ID delle chiavi che necessitano rotazione
    """
    now = time.time()
    keys_to_rotate = []
    
    for key_id, creation_time in _key_creation_times.items():
        # Salta le chiavi di backup (con suffisso _old)
        if key_id.endswith("_old"):
            continue
            
        age_days = (now - creation_time) / (60 * 60 * 24)
        if age_days > DEFAULT_KEY_ROTATION_DAYS:
            keys_to_rotate.append(key_id)
    
    return keys_to_rotate

def rotate_expired_keys() -> Dict[str, bytes]:
    """
    Ruota automaticamente tutte le chiavi scadute
    
    Returns:
        Dict[str, bytes]: Dizionario delle chiavi ruotate {key_id: new_key}
    """
    keys_to_rotate = check_key_rotation()
    rotated_keys = {}
    
    for key_id in keys_to_rotate:
        new_key = rotate_key(key_id)
        rotated_keys[key_id] = new_key
    
    if rotated_keys:
        logger.info(f"Ruotate {len(rotated_keys)} chiavi scadute")
    
    return rotated_keys

# Funzioni di crittografia

def encrypt_data(data: bytes, key_id: str, add_timestamp: bool = True) -> bytes:
    """
    Cripta dati con la chiave specificata
    
    Args:
        data: Dati da criptare
        key_id: ID della chiave da usare
        add_timestamp: Se aggiungere un timestamp per prevenire attacchi replay
        
    Returns:
        bytes: Dati criptati
    """
    try:
        key = get_key(key_id)
        
        # Genera IV casuale
        iv = os.urandom(IV_SIZE_BYTES)
        
        # Aggiungi padding ai dati
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        
        # Aggiungi timestamp se richiesto
        if add_timestamp:
            timestamp = int(time.time()).to_bytes(8, byteorder='big')
            padded_data = padder.update(timestamp + data) + padder.finalize()
        else:
            padded_data = padder.update(data) + padder.finalize()
        
        # Inizializza cipher AES-CBC
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        
        # Cripta i dati
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
        
        # Calcola HMAC per garantire l'integrità
        mac = hmac.new(key, iv + encrypted_data, hashlib.sha256).digest()
        
        # Combina IV, dati criptati e MAC
        result = iv + encrypted_data + mac
        
        return result
    
    except KeyNotFoundError:
        raise
    except Exception as e:
        logger.error(f"Errore nella crittografia dei dati: {e}")
        raise CryptoError(f"Errore di crittografia: {str(e)}")

def decrypt_data(encrypted_data: bytes, key_id: str, verify_timestamp: bool = True) -> bytes:
    """
    Decripta dati con la chiave specificata
    
    Args:
        encrypted_data: Dati criptati
        key_id: ID della chiave da usare
        verify_timestamp: Se verificare il timestamp per prevenire replay
        
    Returns:
        bytes: Dati decriptati
        
    Raises:
        DecryptionError: Se la decrittografia fallisce
    """
    try:
        key = get_key(key_id)
        
        # Estrai IV, dati criptati e MAC
        iv = encrypted_data[:IV_SIZE_BYTES]
        mac_start = len(encrypted_data) - 32  # SHA-256 produce 32 bytes
        
        encrypted_content = encrypted_data[IV_SIZE_BYTES:mac_start]
        mac = encrypted_data[mac_start:]
        
        # Verifica l'integrità con HMAC
        expected_mac = hmac.new(key, iv + encrypted_content, hashlib.sha256).digest()
        if not hmac.compare_digest(mac, expected_mac):
            # Prova con la chiave precedente se disponibile
            legacy_key_id = f"{key_id}_old"
            if legacy_key_id in _key_store:
                logger.info(f"Tentativo di decrittografia con chiave legacy '{legacy_key_id}'")
                legacy_key = _key_store[legacy_key_id]
                legacy_mac = hmac.new(legacy_key, iv + encrypted_content, hashlib.sha256).digest()
                
                if hmac.compare_digest(mac, legacy_mac):
                    key = legacy_key
                else:
                    raise DecryptionError("Integrità dei dati compromessa (HMAC non valido)")
            else:
                raise DecryptionError("Integrità dei dati compromessa (HMAC non valido)")
        
        # Inizializza cipher AES-CBC per decrittografia
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        
        # Decripta i dati
        padded_data = decryptor.update(encrypted_content) + decryptor.finalize()
        
        # Rimuovi padding
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        data = unpadder.update(padded_data) + unpadder.finalize()
        
        # Verifica timestamp se richiesto
        if verify_timestamp and len(data) >= 8:
            timestamp_bytes = data[:8]
            actual_data = data[8:]
            
            timestamp = int.from_bytes(timestamp_bytes, byteorder='big')
            current_time = int(time.time())
            
            # Controlla se il timestamp è nel futuro o troppo vecchio (più di 24 ore)
            if timestamp > current_time + 60:  # 1 minuto di tolleranza per la sincronizzazione dell'orologio
                raise DecryptionError("Timestamp futuro rilevato - possibile attacco replay")
            
            if current_time - timestamp > 86400:  # 24 ore
                logger.warning("Decrittografia di dati con timestamp vecchio (>24h)")
            
            return actual_data
        else:
            # Se non verifichiamo il timestamp o non è incluso
            return data if not verify_timestamp else data[8:]
    
    except KeyNotFoundError:
        raise
    except DecryptionError:
        raise
    except Exception as e:
        logger.error(f"Errore nella decrittografia dei dati: {e}")
        raise DecryptionError(f"Errore di decrittografia: {str(e)}")

# Funzioni per oggetti e JSON

def encrypt_json(data: Dict[str, Any], key_id: str) -> str:
    """
    Cripta un oggetto JSON con la chiave specificata
    
    Args:
        data: Dati JSON da criptare
        key_id: ID della chiave da usare
        
    Returns:
        str: Dati JSON criptati in formato base64
    """
    json_data = json.dumps(data).encode('utf-8')
    encrypted = encrypt_data(json_data, key_id)
    return base64.b64encode(encrypted).decode('utf-8')

def decrypt_json(encrypted_data: str, key_id: str) -> Dict[str, Any]:
    """
    Decripta un oggetto JSON con la chiave specificata
    
    Args:
        encrypted_data: Dati JSON criptati in formato base64
        key_id: ID della chiave da usare
        
    Returns:
        Dict[str, Any]: Dati JSON decriptati
    """
    binary_data = base64.b64decode(encrypted_data)
    decrypted = decrypt_data(binary_data, key_id)
    return json.loads(decrypted.decode('utf-8'))

# Crittografia a livello di campo per database

def encrypt_field(value: Union[str, bytes], key_id: str = 'db_fields') -> str:
    """
    Cripta un singolo campo (stringa o bytes) per archiviazione in database
    
    Args:
        value: Valore da criptare
        key_id: ID della chiave da usare
        
    Returns:
        str: Campo criptato in formato base64
    """
    if isinstance(value, str):
        value = value.encode('utf-8')
    
    encrypted = encrypt_data(value, key_id, add_timestamp=False)
    return base64.b64encode(encrypted).decode('utf-8')

def decrypt_field(encrypted_value: str, key_id: str = 'db_fields') -> str:
    """
    Decripta un singolo campo dal database
    
    Args:
        encrypted_value: Campo criptato in formato base64
        key_id: ID della chiave da usare
        
    Returns:
        str: Campo decriptato
    """
    binary_data = base64.b64decode(encrypted_value)
    decrypted = decrypt_data(binary_data, key_id, verify_timestamp=False)
    return decrypted.decode('utf-8')

# Generazione token sicuri

def generate_token(data: Dict[str, Any], expiry_hours: int = 24, key_id: str = 'tokens') -> str:
    """
    Genera un token JWT-like sicuro con dati criptati
    
    Args:
        data: Dati da includere nel token
        expiry_hours: Validità del token in ore
        key_id: ID della chiave da usare
        
    Returns:
        str: Token sicuro
    """
    # Aggiungi timestamp di scadenza
    expiry = int(time.time() + expiry_hours * 3600)
    data['exp'] = expiry
    
    # Aggiungi un identificatore univoco per prevenire replay
    data['jti'] = secrets.token_hex(8)
    
    # Cripta il payload
    payload = json.dumps(data).encode('utf-8')
    encrypted = encrypt_data(payload, key_id)
    
    # Codifica in base64 per un token URL-safe
    token = base64.urlsafe_b64encode(encrypted).decode('utf-8')
    return token

def validate_token(token: str, key_id: str = 'tokens') -> Dict[str, Any]:
    """
    Verifica e decodifica un token sicuro
    
    Args:
        token: Token da validare
        key_id: ID della chiave usata per criptare
        
    Returns:
        Dict[str, Any]: Dati del token
        
    Raises:
        InvalidTokenError: Se il token è invalido o scaduto
    """
    try:
        # Decodifica il token
        encrypted = base64.urlsafe_b64decode(token)
        decrypted = decrypt_data(encrypted, key_id)
        data = json.loads(decrypted.decode('utf-8'))
        
        # Verifica scadenza
        current_time = int(time.time())
        if 'exp' in data and data['exp'] < current_time:
            raise InvalidTokenError("Token scaduto")
        
        return data
    
    except (json.JSONDecodeError, DecryptionError, KeyNotFoundError) as e:
        raise InvalidTokenError(f"Token invalido: {str(e)}")
    except Exception as e:
        logger.error(f"Errore nella validazione del token: {e}")
        raise InvalidTokenError(f"Errore nella validazione: {str(e)}")

# Funzioni di crittografia asimmetrica per comunicazioni sicure

def generate_rsa_keypair(key_size: int = 2048) -> Tuple[bytes, bytes]:
    """
    Genera una coppia di chiavi RSA per crittografia asimmetrica
    
    Args:
        key_size: Dimensione della chiave in bit
        
    Returns:
        Tuple[bytes, bytes]: (chiave_privata_pem, chiave_pubblica_pem)
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size
    )
    
    private_pem = private_key.private_bytes(
        encoding=Encoding.PEM,
        format=PrivateFormat.PKCS8,
        encryption_algorithm=NoEncryption()
    )
    
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=Encoding.PEM,
        format=PublicFormat.SubjectPublicKeyInfo
    )
    
    return private_pem, public_pem

def encrypt_with_public_key(data: bytes, public_key_pem: bytes) -> bytes:
    """
    Cripta dati con una chiave pubblica RSA
    
    Args:
        data: Dati da criptare
        public_key_pem: Chiave pubblica in formato PEM
        
    Returns:
        bytes: Dati criptati
    """
    public_key = load_pem_public_key(public_key_pem)
    
    # RSA può criptare solo piccole quantità di dati, quindi generiamo
    # una chiave simmetrica per i dati effettivi
    symmetric_key = generate_key()
    
    # Cripta la chiave simmetrica con RSA
    encrypted_key = public_key.encrypt(
        symmetric_key,
        asymmetric_padding.OAEP(
            mgf=asymmetric_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    # Cripta i dati con la chiave simmetrica
    iv = os.urandom(IV_SIZE_BYTES)
    cipher = Cipher(algorithms.AES(symmetric_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(data) + padder.finalize()
    
    encrypted_data = encryptor.update(padded_data) + encryptor.finalize()
    
    # Formato del risultato: len(encrypted_key)[2 bytes] + encrypted_key + iv + encrypted_data
    key_size = len(encrypted_key).to_bytes(2, byteorder='big')
    result = key_size + encrypted_key + iv + encrypted_data
    
    return result

def decrypt_with_private_key(encrypted_data: bytes, private_key_pem: bytes) -> bytes:
    """
    Decripta dati con una chiave privata RSA
    
    Args:
        encrypted_data: Dati criptati
        private_key_pem: Chiave privata in formato PEM
        
    Returns:
        bytes: Dati decriptati
    """
    private_key = load_pem_private_key(private_key_pem, password=None)
    
    # Estrai dimensione chiave criptata
    key_size = int.from_bytes(encrypted_data[:2], byteorder='big')
    
    # Estrai chiave criptata
    encrypted_key = encrypted_data[2:2+key_size]
    
    # Decripta la chiave simmetrica
    symmetric_key = private_key.decrypt(
        encrypted_key,
        asymmetric_padding.OAEP(
            mgf=asymmetric_padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None
        )
    )
    
    # Estrai IV e dati criptati
    iv = encrypted_data[2+key_size:2+key_size+IV_SIZE_BYTES]
    encrypted_content = encrypted_data[2+key_size+IV_SIZE_BYTES:]
    
    # Decripta i dati con la chiave simmetrica
    cipher = Cipher(algorithms.AES(symmetric_key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    
    padded_data = decryptor.update(encrypted_content) + decryptor.finalize()
    
    # Rimuovi padding
    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    data = unpadder.update(padded_data) + unpadder.finalize()
    
    return data

# Funzioni di utilità per operazioni comuni

def generate_secure_password(length: int = 16) -> str:
    """
    Genera una password sicura casuale
    
    Args:
        length: Lunghezza della password
        
    Returns:
        str: Password generata
    """
    # Utilizziamo secrets per una generazione più sicura
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*()-_=+"
    return ''.join(secrets.choice(chars) for _ in range(length))

def create_random_key_id() -> str:
    """
    Genera un ID casuale per una nuova chiave
    
    Returns:
        str: ID univoco per la chiave
    """
    timestamp = int(time.time())
    random_suffix = secrets.token_hex(4)
    return f"key_{timestamp}_{random_suffix}"

# Funzione principale di inizializzazione

def init_crypto_system(master_password: Optional[str] = None):
    """
    Inizializza il sistema di crittografia
    
    Args:
        master_password: Password principale per derivare la chiave master
    """
    # Inizializza la chiave master
    initialize_master_key(master_password)
    
    # Inizializza chiavi di default
    if 'db_fields' not in _key_store:
        register_key('db_fields')
    
    if 'tokens' not in _key_store:
        register_key('tokens')
    
    logger.info("Sistema di crittografia inizializzato")

# Classe di facade per un'API più pulita

class CryptoManager:
    """Classe manager per la gestione centralizzata della crittografia."""
    
    @staticmethod
    def initialize(master_password: Optional[str] = None):
        """Inizializza il sistema di crittografia."""
        init_crypto_system(master_password)
    
    @staticmethod
    def encrypt(data: Union[str, bytes], purpose: str = 'db_fields') -> str:
        """
        Cripta dati per uno scopo specifico
        
        Args:
            data: Dati da criptare
            purpose: Scopo/contesto della crittografia
            
        Returns:
            str: Dati criptati in formato base64
        """
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        encrypted = encrypt_data(data, purpose)
        return base64.b64encode(encrypted).decode('utf-8')
    
    @staticmethod
    def decrypt(encrypted_data: str, purpose: str = 'db_fields') -> str:
        """
        Decripta dati
        
        Args:
            encrypted_data: Dati criptati in formato base64
            purpose: Scopo/contesto della crittografia
            
        Returns:
            str: Dati decriptati
        """
        binary_data = base64.b64decode(encrypted_data)
        decrypted = decrypt_data(binary_data, purpose)
        return decrypted.decode('utf-8')
    
    @staticmethod
    def encrypt_json(data: Dict[str, Any], purpose: str = 'json') -> str:
        """Cripta un oggetto JSON."""
        return encrypt_json(data, purpose)
    
    @staticmethod
    def decrypt_json(encrypted_data: str, purpose: str = 'json') -> Dict[str, Any]:
        """Decripta un oggetto JSON."""
        return decrypt_json(encrypted_data, purpose)
    
    @staticmethod
    def generate_token(data: Dict[str, Any], expiry_hours: int = 24) -> str:
        """Genera un token sicuro."""
        return generate_token(data, expiry_hours)
    
    @staticmethod
    def validate_token(token: str) -> Dict[str, Any]:
        """Valida un token sicuro."""
        return validate_token(token)
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Calcola l'hash di una password."""
        return hash_password(password)
    
    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verifica una password contro il suo hash."""
        return verify_password(password, password_hash)
    
    @staticmethod
    def generate_rsa_keypair() -> Tuple[bytes, bytes]:
        """Genera una coppia di chiavi RSA."""
        return generate_rsa_keypair()
    
    @staticmethod
    def rotate_keys() -> None:
        """Ruota tutte le chiavi scadute."""
        rotate_expired_keys()
    
    @staticmethod
    def secure_random_string(length: int = 16) -> str:
        """Genera una stringa casuale sicura."""
        return generate_secure_password(length)

# Inizializzazione del modulo
if __name__ != "__main__":
    logger.info("Modulo di crittografia caricato")

# Inizializzazione del gestore di crittografia
crypto_manager = CryptoManager()

def get_crypto_manager() -> CryptoManager:
    """Restituisce l'istanza del gestore di crittografia."""
    return crypto_manager 