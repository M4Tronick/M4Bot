"""
Configurazione per M4Bot per Kick.com
"""
import os
import secrets
from dotenv import load_dotenv
import base64
import sys
from pathlib import Path
import json
import logging
from typing import Dict, List, Any, Optional
from cryptography.fernet import Fernet

# Aggiungi la directory principale al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importa il modulo di crittografia
try:
    from security.crypto import CryptoManager, initialize_master_key
except ImportError:
    print("ATTENZIONE: Impossibile importare il modulo di crittografia.")
    print("Assicurati che la directory 'security' sia presente e contenga il file crypto.py")
    # Definisci una versione semplificata della classe CryptoManager per non interrompere l'esecuzione
    class CryptoManager:
        @staticmethod
        def encrypt(data, purpose='config'):
            return data
        @staticmethod
        def decrypt(data, purpose='config'):
            return data

# Carica le variabili d'ambiente dal file .env
# Cerca il file .env dalla directory principale
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Configurazione dell'app
APP_NAME = "M4Bot"
VERSION = "1.0.0"

# Inizializza il sistema di crittografia
try:
    # Chiave per la crittografia dei dati sensibili
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
    if not ENCRYPTION_KEY:
        print("ATTENZIONE: Chiave di crittografia non impostata. Generando una chiave temporanea.")
        print("Per una maggiore sicurezza, imposta la variabile ENCRYPTION_KEY nel file .env")
        # Genera una chiave Fernet sicura (deve essere di 32 byte base64-encoded)
        ENCRYPTION_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    
    # Inizializza il sistema di crittografia
    initialize_master_key(ENCRYPTION_KEY)
    CryptoManager.initialize(ENCRYPTION_KEY)
except Exception as e:
    print(f"ATTENZIONE: Impossibile inizializzare il sistema di crittografia: {e}")
    print("Le credenziali sensibili non saranno criptate!")

# Credenziali OAuth per Kick.com - criptate
_CLIENT_ID = os.getenv("CLIENT_ID", "01JR9DNAJYARH2466KBR8N2AW2")
_CLIENT_SECRET = os.getenv("CLIENT_SECRET", "4379baaef9eb1f1ba571372734cf9627a0f36680fd6f877895cb1d3f17065e4f")

# Utilizzo dei valori criptati
try:
    CLIENT_ID = CryptoManager.decrypt(_CLIENT_ID, 'config') if hasattr(CryptoManager, 'decrypt') else _CLIENT_ID
    CLIENT_SECRET = CryptoManager.decrypt(_CLIENT_SECRET, 'config') if hasattr(CryptoManager, 'decrypt') else _CLIENT_SECRET
except Exception:
    CLIENT_ID = _CLIENT_ID
    CLIENT_SECRET = _CLIENT_SECRET

REDIRECT_URI = os.getenv("REDIRECT_URI", "https://m4bot.it/auth/callback")
SCOPE = os.getenv("SCOPE", "user:read channel:read channel:write chat:write events:subscribe")

# Configurazione del server web
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "443"))
WEB_DOMAIN = os.getenv("WEB_DOMAIN", "localhost")
SSL_CERT = os.getenv("SSL_CERT", "")
SSL_KEY = os.getenv("SSL_KEY", "")

# Configurazione del database
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "m4bot_db")
DB_USER = os.getenv("DB_USER", "m4bot_user")
DB_PASS = os.getenv("DB_PASSWORD", "")  # Deve essere configurato tramite .env

# Configurazione della VPS
VPS_IP = os.getenv("VPS_IP", "")

# Cooldown predefiniti (in secondi)
DEFAULT_COMMAND_COOLDOWN = int(os.getenv("DEFAULT_COMMAND_COOLDOWN", "5"))
DEFAULT_USER_COOLDOWN = int(os.getenv("DEFAULT_USER_COOLDOWN", "2"))
DEFAULT_GLOBAL_COOLDOWN = int(os.getenv("DEFAULT_GLOBAL_COOLDOWN", "1"))

# Impostazioni di log
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/m4bot.log")

# Integrazione OBS
OBS_WEBSOCKET_URL = os.getenv("OBS_WEBSOCKET_URL", "ws://localhost:4455")
OBS_WEBSOCKET_PASSWORD = os.getenv("OBS_WEBSOCKET_PASSWORD", "")
    
# Chiave segreta per sessioni web e token
SECRET_KEY = os.getenv("SECRET_KEY", "")
if not SECRET_KEY:
    print("ATTENZIONE: Chiave segreta non impostata. Generando una chiave temporanea.")
    print("Per una maggiore sicurezza, imposta la variabile SECRET_KEY nel file .env")
    SECRET_KEY = secrets.token_hex(32)

# Configurazione della sicurezza
SECURITY_SETTINGS = {
    "allow_registration": os.getenv("ALLOW_REGISTRATION", "true").lower() == "true",
    "max_login_attempts": int(os.getenv("MAX_LOGIN_ATTEMPTS", "5")),
    "login_timeout": int(os.getenv("LOGIN_TIMEOUT", "300")),  # 5 minuti
    "session_lifetime": int(os.getenv("SESSION_LIFETIME", "604800")),  # 7 giorni
    "require_https": os.getenv("REQUIRE_HTTPS", "true").lower() == "true",
    "cors_allowed_origins": os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")
}

# Configurazione API Kick
REDIRECT_URI = os.environ.get("REDIRECT_URI", "http://localhost:5000/auth/callback")
SCOPE = "channels:read chat:connect chat:read chat:write user:read"

# Configurazione database
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost/m4bot")

# Configurazione notifiche
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

# Configurazione email per notifiche
EMAIL_SENDER = os.environ.get("EMAIL_SENDER", "")
EMAIL_RECIPIENT = os.environ.get("EMAIL_RECIPIENT", "")
EMAIL_SMTP_SERVER = os.environ.get("EMAIL_SMTP_SERVER", "")
EMAIL_SMTP_PORT = int(os.environ.get("EMAIL_SMTP_PORT", "465"))
EMAIL_USERNAME = os.environ.get("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")

# Configurazione Redis
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

class ConfigValidator:
    """
    Classe per la validazione delle configurazioni necessarie
    Verifica che tutte le variabili d'ambiente richieste siano presenti e valide
    """
    
    def __init__(self):
        self.issues = []
        self.warnings = []
        self.is_valid = True
    
    def validate(self) -> bool:
        """
        Esegue la validazione completa della configurazione
        
        Returns:
            bool: True se la configurazione è valida, False altrimenti
        """
        # Verifica la configurazione di base
        self._validate_base_config()
        
        # Verifica la configurazione dell'API
        self._validate_api_config()
        
        # Verifica la configurazione del database
        self._validate_database_config()
        
        # Verifica la configurazione di crittografia
        self._validate_encryption_config()
        
        # Verifica la configurazione delle notifiche
        self._validate_notification_config()
        
        # Logga i risultati
        self._log_validation_results()
        
        return self.is_valid
    
    def _validate_base_config(self):
        """Verifica le configurazioni di base"""
        # Controlla le directory di log
        if not os.path.exists(os.path.dirname(LOG_FILE)):
            try:
                os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
                self.warnings.append(f"Directory dei log {os.path.dirname(LOG_FILE)} creata automaticamente")
            except Exception as e:
                self.issues.append(f"Impossibile creare la directory dei log {os.path.dirname(LOG_FILE)}: {e}")
                self.is_valid = False
        
        # Controlla il livello di log
        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if LOG_LEVEL not in valid_log_levels:
            self.warnings.append(f"Livello di log '{LOG_LEVEL}' non valido. Utilizzando 'INFO' come predefinito")
    
    def _validate_api_config(self):
        """Verifica le configurazioni dell'API"""
        if not CLIENT_ID:
            self.issues.append("CLIENT_ID non configurato")
            self.is_valid = False
        
        if not CLIENT_SECRET:
            self.issues.append("CLIENT_SECRET non configurato")
            self.is_valid = False
        
        if not REDIRECT_URI:
            self.warnings.append("REDIRECT_URI non configurato, utilizzando valore predefinito")
    
    def _validate_database_config(self):
        """Verifica le configurazioni del database"""
        if not DATABASE_URL:
            self.issues.append("DATABASE_URL non configurato")
            self.is_valid = False
        
        # Verifica che la stringa di connessione sia valida
        if DATABASE_URL:
            if not DATABASE_URL.startswith("postgresql://"):
                self.issues.append("DATABASE_URL deve essere una stringa di connessione PostgreSQL valida")
                self.is_valid = False
    
    def _validate_encryption_config(self):
        """Verifica la configurazione della crittografia"""
        if not ENCRYPTION_KEY:
            self.issues.append("ENCRYPTION_KEY non configurata")
            self.is_valid = False
            return
        
        # Verifica che la chiave sia una chiave Fernet valida
        try:
            if isinstance(ENCRYPTION_KEY, str):
                key = ENCRYPTION_KEY.encode('utf-8')
            else:
                key = ENCRYPTION_KEY
                
            # Verifica se la chiave è una chiave Fernet valida
            base64.urlsafe_b64decode(key + b'=' * (4 - len(key) % 4))
            Fernet(key)
        except Exception as e:
            self.issues.append(f"ENCRYPTION_KEY non è una chiave Fernet valida: {e}")
            self.is_valid = False
    
    def _validate_notification_config(self):
        """Verifica la configurazione delle notifiche"""
        # Verifica configurazione Telegram
        if TELEGRAM_BOT_TOKEN and not TELEGRAM_CHAT_ID:
            self.warnings.append("TELEGRAM_BOT_TOKEN configurato ma TELEGRAM_CHAT_ID mancante")
        
        if TELEGRAM_CHAT_ID and not TELEGRAM_BOT_TOKEN:
            self.warnings.append("TELEGRAM_CHAT_ID configurato ma TELEGRAM_BOT_TOKEN mancante")
        
        # Verifica configurazione email
        if EMAIL_SENDER or EMAIL_RECIPIENT or EMAIL_SMTP_SERVER:
            if not EMAIL_SENDER:
                self.warnings.append("EMAIL_SENDER non configurato")
            
            if not EMAIL_RECIPIENT:
                self.warnings.append("EMAIL_RECIPIENT non configurato")
            
            if not EMAIL_SMTP_SERVER:
                self.warnings.append("EMAIL_SMTP_SERVER non configurato")
            
            if not EMAIL_USERNAME or not EMAIL_PASSWORD:
                self.warnings.append("Credenziali email (USERNAME/PASSWORD) mancanti")
    
    def _log_validation_results(self):
        """Logga i risultati della validazione"""
        logger = logging.getLogger('ConfigValidator')
        
        if self.is_valid and not self.warnings:
            logger.info("Configurazione valida, nessun problema rilevato")
            return
        
        if not self.is_valid:
            logger.error("Configurazione NON valida. Problemi critici rilevati:")
            for issue in self.issues:
                logger.error(f"- {issue}")
        
        if self.warnings:
            logger.warning("Configurazione valida, ma con avvisi:")
            for warning in self.warnings:
                logger.warning(f"- {warning}")
    
    def get_issues(self) -> List[str]:
        """Restituisce la lista dei problemi rilevati"""
        return self.issues
    
    def get_warnings(self) -> List[str]:
        """Restituisce la lista degli avvisi"""
        return self.warnings
    
    @staticmethod
    def create_encryption_key() -> str:
        """
        Crea una nuova chiave di crittografia Fernet valida
        
        Returns:
            str: Chiave di crittografia in formato stringa
        """
        key = Fernet.generate_key()
        return key.decode('utf-8')

def load_config() -> Dict[str, Any]:
    """
    Carica e verifica la configurazione complessiva
    
    Returns:
        Dict[str, Any]: Configurazione completa
    """
    # Verifica la validità delle configurazioni
    validator = ConfigValidator()
    is_valid = validator.validate()
    
    # Genera la configurazione completa
    config = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "encryption_key": ENCRYPTION_KEY,
        "database_url": DATABASE_URL,
        "log_level": LOG_LEVEL,
        "log_file": LOG_FILE,
        "notification": {
            "telegram_bot_token": TELEGRAM_BOT_TOKEN,
            "telegram_chat_id": TELEGRAM_CHAT_ID,
            "discord_webhook_url": DISCORD_WEBHOOK_URL,
            "email": {
                "sender": EMAIL_SENDER,
                "recipient": EMAIL_RECIPIENT,
                "smtp_server": EMAIL_SMTP_SERVER,
                "smtp_port": EMAIL_SMTP_PORT,
                "username": EMAIL_USERNAME,
                "password": EMAIL_PASSWORD
            }
        },
        "redis_url": REDIS_URL
    }
    
    if not is_valid:
        logger = logging.getLogger('Config')
        logger.critical("Configurazione non valida, l'applicazione potrebbe non funzionare correttamente")
    
    return config

# Genera ed esporta la configurazione completa
config = load_config()

# Esporta le variabili per retrocompatibilità con il codice esistente
__all__ = [
    'LOG_DIR', 'LOG_FILE', 'LOG_LEVEL',
    'CLIENT_ID', 'CLIENT_SECRET', 'REDIRECT_URI', 'SCOPE',
    'ENCRYPTION_KEY', 'DATABASE_URL',
    'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID', 'DISCORD_WEBHOOK_URL',
    'EMAIL_SENDER', 'EMAIL_RECIPIENT', 'EMAIL_SMTP_SERVER',
    'EMAIL_SMTP_PORT', 'EMAIL_USERNAME', 'EMAIL_PASSWORD',
    'REDIS_URL', 'ConfigValidator', 'load_config', 'config'
]
