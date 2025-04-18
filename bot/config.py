"""
Configurazione per M4Bot per Kick.com
"""
import os
import secrets
from dotenv import load_dotenv
import base64

# Carica le variabili d'ambiente dal file .env
# Cerca il file .env dalla directory principale
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# Configurazione dell'app
APP_NAME = "M4Bot"
VERSION = "1.0.0"

# Credenziali OAuth per Kick.com
CLIENT_ID = os.getenv("CLIENT_ID", "01JR9DNAJYARH2466KBR8N2AW2")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "4379baaef9eb1f1ba571372734cf9627a0f36680fd6f877895cb1d3f17065e4f")
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

# Chiave per la crittografia dei dati sensibili
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
if not ENCRYPTION_KEY:
    print("ATTENZIONE: Chiave di crittografia non impostata. Generando una chiave temporanea.")
    print("Per una maggiore sicurezza, imposta la variabile ENCRYPTION_KEY nel file .env")
    # Genera una chiave Fernet sicura (deve essere di 32 byte base64-encoded)
    ENCRYPTION_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    
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
