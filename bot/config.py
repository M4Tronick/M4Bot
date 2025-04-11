"""
Configurazione per M4Bot per Kick.com
"""

# Configurazione dell'app
APP_NAME = "M4Bot"
VERSION = "1.0.0"

# Credenziali OAuth per Kick.com
CLIENT_ID = "01JR9DNAJYARH2466KBR8N2AW2"
CLIENT_SECRET = "4379baaef9eb1f1ba571372734cf9627a0f36680fd6f877895cb1d3f17065e4f"
REDIRECT_URI = "https://m4bot.it/auth/callback"
SCOPE = "user:read channel:read channel:write chat:write events:subscribe"

# Configurazione del server web
WEB_HOST = "0.0.0.0"
WEB_PORT = 443
WEB_DOMAIN = "m4bot.it"
SSL_CERT = "/etc/letsencrypt/live/m4bot.it/fullchain.pem"
SSL_KEY = "/etc/letsencrypt/live/m4bot.it/privkey.pem"

# Configurazione del database
DB_HOST = "localhost"
DB_NAME = "m4bot_db"
DB_USER = "m4bot_user"
DB_PASS = "m4bot_password"  # Da cambiare in produzione

# Configurazione della VPS
VPS_IP = "78.47.146.95"

# Cooldown predefiniti (in secondi)
DEFAULT_COMMAND_COOLDOWN = 5
DEFAULT_USER_COOLDOWN = 2
DEFAULT_GLOBAL_COOLDOWN = 1

# Impostazioni di log
LOG_LEVEL = "INFO"
LOG_FILE = "logs/m4bot.log"

# Integrazione OBS
OBS_WEBSOCKET_URL = "ws://localhost:4455"
OBS_WEBSOCKET_PASSWORD = ""  # Da configurare se necessario

# Chiave per la crittografia dei dati sensibili
ENCRYPTION_KEY = "change_this_to_a_secure_random_key_in_production"
