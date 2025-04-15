#!/bin/bash
# Script di installazione M4Bot v2.0

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzioni di utilità
check_root() {
    if [ "$(id -u)" != "0" ]; then
        echo -e "${RED}Errore: Questo script deve essere eseguito come root${NC}"
        exit 1
    fi
}

print_message() {
    echo -e "${BLUE}[M4Bot]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERRORE]${NC} $1"
    if [ -n "$2" ]; then
        exit $2
    fi
}

print_success() {
    echo -e "${GREEN}[SUCCESSO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[AVVISO]${NC} $1"
}

# Rende eseguibili tutti gli script nella cartella scripts
setup_script_permissions() {
    print_message "Impostazione dei permessi di esecuzione per gli script..."
    
    # Verifica se la directory scripts esiste
    if [ -d "scripts" ]; then
        chmod +x scripts/*.sh || print_warning "Impossibile impostare i permessi di esecuzione per alcuni script"
        print_success "Permessi di esecuzione impostati per gli script"
    else
        print_warning "Directory scripts non trovata, impossibile impostare i permessi"
    fi
}

# Funzione per confermare l'installazione
confirm_installation() {
    print_message "====================================================="
    print_message "      INSTALLAZIONE COMPLETA DI M4BOT v2.0"
    print_message "====================================================="
    print_message "Questo script installerà e configurerà tutti i componenti di M4Bot:"
    print_message "- Dipendenze di sistema"
    print_message "- Database PostgreSQL"
    print_message "- Server web Nginx"
    print_message "- Certificato SSL (Let's Encrypt)"
    print_message "- Servizi systemd"
    print_message "- Applicazione web e bot"
    print_message "- Script di gestione"
    
    read -p "Continuare con l'installazione? (s/n): " confirm
    if [[ $confirm != "s" && $confirm != "S" ]]; then
        print_message "Installazione annullata."
        exit 0
    fi
}

# Funzione per aggiornare il sistema
update_system() {
    print_message "Aggiornamento del sistema..."
    apt-get update || print_error "Impossibile aggiornare il sistema" 1
    print_success "Sistema aggiornato"
}

# Funzione per installare dipendenze
install_dependencies() {
    print_message "Installazione delle dipendenze..."
    apt-get install -y python3 python3-pip python3-venv nginx postgresql certbot python3-certbot-nginx git supervisor redis-server || print_error "Impossibile installare le dipendenze" 1
    print_success "Dipendenze installate"
}

# Funzione per creare l'utente di sistema m4bot
create_system_user() {
    print_message "Creazione dell'utente di sistema 'm4bot'..."
    if id -u m4bot >/dev/null 2>&1; then
        print_warning "L'utente 'm4bot' esiste già"
    else
        useradd -m -s /bin/bash m4bot || print_error "Impossibile creare l'utente 'm4bot'" 1
        print_success "Utente 'm4bot' creato"
    fi
}

# Funzione per configurare PostgreSQL
setup_database() {
    print_message "Configurazione del database PostgreSQL..."

    # Avvia PostgreSQL se non è in esecuzione
    if ! systemctl is-active --quiet postgresql; then
        systemctl start postgresql || print_error "Impossibile avviare PostgreSQL" 1
    fi
    
    # Genera una password sicura per il database
    DB_PASSWORD=$(openssl rand -hex 12)
    
    # Crea l'utente e il database
    sudo -u postgres psql -c "SELECT 1 FROM pg_roles WHERE rolname='m4bot_user'" | grep -q 1 || {
        sudo -u postgres psql -c "CREATE USER m4bot_user WITH PASSWORD '$DB_PASSWORD';" || print_error "Impossibile creare l'utente del database" 1
        print_success "Utente del database creato"
    }
    
    sudo -u postgres psql -c "SELECT 1 FROM pg_database WHERE datname='m4bot_db'" | grep -q 1 || {
        sudo -u postgres psql -c "CREATE DATABASE m4bot_db OWNER m4bot_user;" || print_error "Impossibile creare il database" 1
        print_success "Database creato"
    }
    
    # Salva la password del database per un uso successivo
    SAVED_DB_PASSWORD=$DB_PASSWORD
    print_success "Database PostgreSQL configurato"
}

# Funzione per inizializzare il database
initialize_database() {
    print_message "Inizializzazione del database..."
    
    # Crea le tabelle nel database
    sudo -u postgres psql -d m4bot_db -c "
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(255) NOT NULL UNIQUE,
        email VARCHAR(255) NOT NULL UNIQUE,
        password_hash VARCHAR(255) NOT NULL,
        is_admin BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    
    CREATE TABLE IF NOT EXISTS channels (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL UNIQUE,
        user_id INTEGER REFERENCES users(id),
        kick_id VARCHAR(255),
        access_token TEXT,
        refresh_token TEXT,
        token_expires_at TIMESTAMP,
        bot_enabled BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    
    CREATE TABLE IF NOT EXISTS commands (
        id SERIAL PRIMARY KEY,
        channel_id INTEGER REFERENCES channels(id),
        name VARCHAR(255) NOT NULL,
        response TEXT NOT NULL,
        cooldown INTEGER DEFAULT 5,
        user_level VARCHAR(50) DEFAULT 'everyone',
        enabled BOOLEAN DEFAULT TRUE,
        usage_count INTEGER DEFAULT 0,
        last_used TIMESTAMP,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    
    CREATE TABLE IF NOT EXISTS chat_messages (
        id SERIAL PRIMARY KEY,
        channel_id INTEGER REFERENCES channels(id),
        user_id VARCHAR(255),
        username VARCHAR(255),
        content TEXT,
        is_command BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP NOT NULL DEFAULT NOW()
    );
    
    CREATE TABLE IF NOT EXISTS user_points (
        id SERIAL PRIMARY KEY,
        channel_id INTEGER REFERENCES channels(id),
        user_id VARCHAR(255),
        username VARCHAR(255),
        points INTEGER DEFAULT 0,
        watch_time INTEGER DEFAULT 0,
        last_updated TIMESTAMP NOT NULL DEFAULT NOW()
    );
    " || print_error "Impossibile inizializzare il database" 1
    
    # Crea un admin di default
    ADMIN_PASSWORD_HASH=$(python3 -c "import hashlib; print(hashlib.sha256('admin123'.encode()).hexdigest())")
    sudo -u postgres psql -d m4bot_db -c "
    INSERT INTO users (username, email, password_hash, is_admin) 
    VALUES ('admin', 'admin@m4bot.it', '$ADMIN_PASSWORD_HASH', TRUE)
    ON CONFLICT (username) DO NOTHING;
    " || print_error "Impossibile creare l'utente admin" 1
    
    print_success "Database inizializzato con successo"
}

# Funzione per configurare i repository
setup_repository() {
    print_message "Configurazione dei repository..."
    
    # Directory di installazione
    INSTALL_DIR="/opt/m4bot"
    BOT_DIR="$INSTALL_DIR/bot"
    WEB_DIR="$INSTALL_DIR/web"
    
    # Crea le directory necessarie
    mkdir -p "$BOT_DIR" "$WEB_DIR" || print_error "Impossibile creare le directory" 1
    
    # Crea tutte le directory per i log
    mkdir -p "$BOT_DIR/logs/channels" "$BOT_DIR/logs/webhooks" "$BOT_DIR/logs/security" "$BOT_DIR/logs/errors" "$BOT_DIR/logs/connections" || print_warning "Impossibile creare alcune directory di log"
    
    # Directory aggiuntive necessarie
    mkdir -p "$BOT_DIR/languages" "$BOT_DIR/data" "$BOT_DIR/cache" "$BOT_DIR/modules" || print_warning "Impossibile creare alcune directory del bot"
    mkdir -p "$WEB_DIR/static/css" "$WEB_DIR/static/js" "$WEB_DIR/static/images" "$WEB_DIR/static/fonts" || print_warning "Impossibile creare alcune directory web statiche"
    mkdir -p "$WEB_DIR/templates" "$WEB_DIR/uploads" "$WEB_DIR/translations" "$WEB_DIR/logs" || print_warning "Impossibile creare alcune directory web"
    
    # Copia i file dal repository locale se esiste
    if [ -d "$HOME/M4Bot" ]; then
        print_message "Repository locale trovato, copiando i file..."
        cp -r "$HOME/M4Bot/bot/"* "$BOT_DIR/" || print_error "Impossibile copiare i file del bot" 1
        cp -r "$HOME/M4Bot/web/"* "$WEB_DIR/" || print_error "Impossibile copiare i file web" 1
    else
        print_message "Clonazione del repository da GitHub..."
        cd /tmp
        git clone https://github.com/username/M4Bot.git || print_error "Impossibile clonare il repository" 1
        cp -r M4Bot/bot/* "$BOT_DIR/" || print_error "Impossibile copiare i file del bot" 1
        cp -r M4Bot/web/* "$WEB_DIR/" || print_error "Impossibile copiare i file web" 1
        rm -rf M4Bot
    fi
    
    # Imposta permessi
    chown -R m4bot:m4bot "$INSTALL_DIR" || print_error "Impossibile impostare i permessi" 1
    chmod +x "$BOT_DIR/m4bot.py" || print_warning "Impossibile impostare permessi di esecuzione"
    chmod +x "$WEB_DIR/app.py" || print_warning "Impossibile impostare permessi di esecuzione"
    
    print_success "Repository configurato"
    
    # Salva i percorsi per un uso successivo
    SAVED_INSTALL_DIR=$INSTALL_DIR
    SAVED_BOT_DIR=$BOT_DIR
    SAVED_WEB_DIR=$WEB_DIR
}

# Funzione per configurare l'ambiente Python
setup_python_env() {
    print_message "Configurazione dell'ambiente Python..."
    
    # Crea l'ambiente virtuale
    python3 -m venv "$SAVED_INSTALL_DIR/venv" || print_error "Impossibile creare l'ambiente virtuale" 1
    
    # Attiva l'ambiente virtuale e installa le dipendenze
    source "$SAVED_INSTALL_DIR/venv/bin/activate"
    
    # Aggiorna pip
    pip install --upgrade pip || print_warning "Impossibile aggiornare pip"
    
    # Installa dipendenze del bot
    if [ -f "$SAVED_BOT_DIR/requirements.txt" ]; then
        pip install -r "$SAVED_BOT_DIR/requirements.txt" || print_warning "Impossibile installare alcune dipendenze del bot"
    else
        # Installa dipendenze minime
        pip install aiohttp asyncpg websockets requests pyyaml python-dotenv cryptography bcrypt redis || print_warning "Impossibile installare alcune dipendenze del bot"
    fi
    
    # Installa dipendenze web
    pip install flask==2.3.3 flask-babel==2.0.0 quart==0.19.4 quart-cors==0.6.0 gunicorn python-dotenv jinja2 pyyaml redis || print_warning "Impossibile installare alcune dipendenze web"
    
    # Crea il file babel_compat.py per gestire le differenze tra versioni di flask-babel
    cat > "$SAVED_WEB_DIR/babel_compat.py" << 'EOF'
# Compatibilità per diverse versioni di flask-babel
try:
    from flask_babel import Babel
    
    # Aggiungi retrocompatibilità se necessario
    if hasattr(Babel, 'select_locale') and not hasattr(Babel, 'localeselector'):
        Babel.localeselector = Babel.select_locale
    elif hasattr(Babel, 'localeselector') and not hasattr(Babel, 'select_locale'):
        Babel.select_locale = Babel.localeselector
except ImportError:
    # Stub class in caso di mancata importazione
    class Babel:
        def __init__(self, app=None):
            self.app = app
            
        def init_app(self, app):
            self.app = app
            
        def localeselector(self, f):
            return f
            
        select_locale = localeselector
EOF
    
    # Aggiungi l'importazione del modulo di compatibilità all'inizio di app.py
    sed -i '1i from babel_compat import *' "$SAVED_WEB_DIR/app.py" || print_warning "Impossibile modificare app.py"
    
    # Aggiungi l'importazione dotenv a entrambi gli script
    sed -i "1i import os\\nfrom dotenv import load_dotenv\\n\\n# Carica variabili d'ambiente\\nload_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), \".env\"))\\n\\n" "$SAVED_WEB_DIR/app.py"
    sed -i "1i import os\\nfrom dotenv import load_dotenv\\n\\n# Carica variabili d'ambiente\\nload_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), \".env\"))\\n\\n" "$SAVED_BOT_DIR/m4bot.py"
    
    deactivate
    print_success "Ambiente Python configurato"
}

# Funzione per configurare Nginx
setup_nginx() {
    print_message "Configurazione di Nginx..."
    
    # Ottieni il dominio dall'utente
    read -p "Inserisci il dominio per M4Bot (es. m4bot.it): " DOMAIN
    if [ -z "$DOMAIN" ]; then
        DOMAIN="m4bot.it"
        print_warning "Nessun dominio inserito, utilizzo il dominio predefinito: $DOMAIN"
    fi
    
    # Crea il file di configurazione Nginx
    cat > /etc/nginx/sites-available/m4bot << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static/ {
        alias $SAVED_WEB_DIR/static/;
        expires 30d;
    }

    # WebSocket per notifiche
    location /ws/notifications {
        proxy_pass http://127.0.0.1:5000/ws/notifications;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400;
    }

    # WebSocket per metriche
    location /ws/metrics {
        proxy_pass http://127.0.0.1:5000/ws/metrics;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400;
    }

    # Legacy WebSocket
    location /socket.io {
        proxy_pass http://127.0.0.1:5000/socket.io;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400;
    }
}
EOF
    
    # Attiva il sito
    ln -sf /etc/nginx/sites-available/m4bot /etc/nginx/sites-enabled/ || print_error "Impossibile attivare il sito Nginx" 1
    
    # Testa la configurazione
    nginx -t || print_error "Configurazione Nginx non valida" 1
    
    # Riavvia Nginx
    systemctl restart nginx || print_error "Impossibile riavviare Nginx" 1
    
    print_success "Nginx configurato"
    
    # Salva il dominio per un uso successivo
    SAVED_DOMAIN=$DOMAIN
}

# Funzione per configurare SSL con Let's Encrypt
setup_ssl() {
    print_message "Configurazione SSL con Let's Encrypt..."
    
    # Chiedi all'utente se vuole configurare SSL
    read -p "Configurare SSL con Let's Encrypt? (s/n, richiede un dominio valido): " configure_ssl
    if [[ $configure_ssl != "s" && $configure_ssl != "S" ]]; then
        print_warning "Configurazione SSL saltata"
        return
    fi
    
    # Ottieni l'email per il certificato
    read -p "Inserisci un indirizzo email per le notifiche di Let's Encrypt: " EMAIL
    if [ -z "$EMAIL" ]; then
        EMAIL="admin@m4bot.it"
        print_warning "Nessun email inserito, utilizzo l'email predefinita: $EMAIL"
    fi
    
    # Configura SSL
    certbot --nginx -d $SAVED_DOMAIN -d www.$SAVED_DOMAIN --non-interactive --agree-tos --email $EMAIL || print_error "Impossibile configurare SSL" 1
    
    print_success "SSL configurato"
}

# Funzione per configurare i servizi systemd
setup_systemd_services() {
    print_message "Configurazione dei servizi systemd..."
    
    # Crea il servizio del bot
    cat > /etc/systemd/system/m4bot-bot.service << EOF
[Unit]
Description=M4Bot Bot Service
After=network.target postgresql.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$SAVED_BOT_DIR
ExecStart=$SAVED_INSTALL_DIR/venv/bin/python m4bot.py
Restart=on-failure
RestartSec=10
Environment="PYTHONUNBUFFERED=1"
Environment="PYTHONIOENCODING=utf-8"

[Install]
WantedBy=multi-user.target
EOF

    # Crea il servizio web
    cat > /etc/systemd/system/m4bot-web.service << EOF
[Unit]
Description=M4Bot Web Service
After=network.target postgresql.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$SAVED_WEB_DIR
ExecStart=$SAVED_INSTALL_DIR/venv/bin/python app.py
Restart=on-failure
RestartSec=10
Environment="PYTHONUNBUFFERED=1"
Environment="PYTHONIOENCODING=utf-8"

[Install]
WantedBy=multi-user.target
EOF

    # Ricarica systemd e abilita i servizi
    systemctl daemon-reload || print_error "Impossibile ricaricare systemd" 1
    systemctl enable m4bot-bot.service || print_warning "Impossibile abilitare il servizio del bot"
    systemctl enable m4bot-web.service || print_warning "Impossibile abilitare il servizio web"
    
    print_success "Servizi systemd configurati"
}

# Funzione per configurare gli script di gestione
setup_management_scripts() {
    print_message "Configurazione degli script di gestione..."
    
    # Copia gli script di gestione
    if [ -d "$HOME/M4Bot/scripts" ]; then
        mkdir -p /usr/local/bin
        cp "$HOME/M4Bot/scripts/common.sh" /usr/local/bin/ || print_warning "Impossibile copiare common.sh"
        
        for script in start stop restart status; do
            # Crea uno script wrapper per il file .sh
            cat > "/usr/local/bin/m4bot-$script" << EOF
#!/bin/bash
# Script wrapper per m4bot-$script

# Verifica che esista lo script common.sh
if [ ! -f "/usr/local/bin/common.sh" ]; then
    echo "Errore: File common.sh non trovato in /usr/local/bin/"
    echo "Reinstallare gli script wrapper"
    exit 1
fi

# Carica le funzioni comuni
source "/usr/local/bin/common.sh"

# Esegui lo script
/bin/bash "$HOME/M4Bot/scripts/$script.sh" \$@
EOF
            chmod +x "/usr/local/bin/m4bot-$script" || print_warning "Impossibile impostare permessi di esecuzione per m4bot-$script"
        done
    else
        print_warning "Directory scripts non trovata, impossibile configurare gli script di gestione"
    fi
    
    print_success "Script di gestione configurati"
}

# Funzione per configurare il file .env
setup_env_file() {
    print_message "Configurazione del file .env..."
    
    # Genera chiavi segrete
    SECRET_KEY=$(openssl rand -hex 24)
    ENCRYPTION_KEY=$(openssl rand -base64 32)
    
    # Crea il file .env
    cat > "$SAVED_INSTALL_DIR/.env" << EOF
# Configurazione database
DB_USER=m4bot_user
DB_PASSWORD=$SAVED_DB_PASSWORD
DB_NAME=m4bot_db
DB_HOST=localhost

# Configurazione Redis per caching avanzato e WebSocket
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Configurazione dominio e web server
DOMAIN=$SAVED_DOMAIN
WEB_DOMAIN=$SAVED_DOMAIN
WEB_HOST=0.0.0.0
WEB_PORT=5000
DASHBOARD_DOMAIN=dashboard.$SAVED_DOMAIN
CONTROL_DOMAIN=control.$SAVED_DOMAIN

# Configurazione SSL
SSL_CERT=/etc/letsencrypt/live/$SAVED_DOMAIN/fullchain.pem
SSL_KEY=/etc/letsencrypt/live/$SAVED_DOMAIN/privkey.pem

# Chiavi e segreti
SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY

# Credenziali OAuth per Kick.com
CLIENT_ID=01JR9DNAJYARH2466KBR8N2AW2
CLIENT_SECRET=4379baaef9eb1f1ba571372734cf9627a0f36680fd6f877895cb1d3f17065e4f
REDIRECT_URI=https://$SAVED_DOMAIN/auth/callback
SCOPE=user:read channel:read channel:write chat:write events:subscribe

# Configurazione log
LOG_LEVEL=INFO
LOG_FILE=$SAVED_BOT_DIR/logs/m4bot.log

# Configurazioni webhook e sicurezza
WEBHOOK_MAX_RETRIES=3
WEBHOOK_RETRY_DELAY=5
WEBHOOK_TIMEOUT=10
WEBHOOK_IP_WHITELIST=
WEBHOOK_IP_BLACKLIST=
WEBHOOK_RATE_LIMIT_ENABLED=true
WEBHOOK_RATE_LIMIT_MAX_REQUESTS=100
WEBHOOK_RATE_LIMIT_TIME_WINDOW=60
WEBHOOK_RATE_LIMIT_BLOCK_DURATION=300
WEBHOOK_ANTI_REPLAY=true
WEBHOOK_CHECK_TIMESTAMP=true
WEBHOOK_VERIFY_SIGNATURE=true

# Configurazione WebSocket
WS_ENABLED=true
WS_HOST=0.0.0.0
WS_PORT=8765
WS_PATH=/ws
WS_AUTH_REQUIRED=true

# Directory per dati
DATA_DIR=$SAVED_INSTALL_DIR/data
TEMPLATES_DIR=$SAVED_INSTALL_DIR/data/templates
WORKFLOWS_DIR=$SAVED_INSTALL_DIR/data/workflows
NOTIFICATIONS_DIR=$SAVED_INSTALL_DIR/data/notifications
USER_CONFIGS_DIR=$SAVED_INSTALL_DIR/data/user_configs
VARIABLES_DIR=$SAVED_INSTALL_DIR/data/variables

# Configurazione VPS
VPS_IP=

# Configurazione OBS
OBS_WEBSOCKET_URL=ws://localhost:4455
OBS_WEBSOCKET_PASSWORD=

# Impostazioni sicurezza
ALLOW_REGISTRATION=true
MAX_LOGIN_ATTEMPTS=5
LOGIN_TIMEOUT=300
SESSION_LIFETIME=604800
REQUIRE_HTTPS=true
CORS_ALLOWED_ORIGINS=*

# Cooldown predefiniti (in secondi)
DEFAULT_COMMAND_COOLDOWN=5
DEFAULT_USER_COOLDOWN=2
DEFAULT_GLOBAL_COOLDOWN=1

# Configurazione manutenzione
MAINTENANCE_MODE=false
AUTO_BACKUP=true
BACKUP_RETENTION_DAYS=7

# Configurazione monitoraggio
MONITOR_CHECK_INTERVAL=300

# Configurazioni WhatsApp
WHATSAPP_API_VERSION=v16.0
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_TOKEN=
WHATSAPP_VERIFY_TOKEN=

# Configurazioni Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_URL=

# Configurazioni YouTube
YOUTUBE_API_KEY=
YOUTUBE_CHANNEL_ID=
YOUTUBE_METRICS_UPDATE_INTERVAL=60
EOF
    
    # Imposta i permessi
    chown m4bot:m4bot "$SAVED_INSTALL_DIR/.env" || print_warning "Impossibile impostare i permessi per .env"
    chmod 600 "$SAVED_INSTALL_DIR/.env" || print_warning "Impossibile impostare i permessi per .env"
    
    print_success "File .env configurato"
    
    # Crea le directory necessarie per i dati
    mkdir -p "$SAVED_INSTALL_DIR/data/templates" \
             "$SAVED_INSTALL_DIR/data/workflows" \
             "$SAVED_INSTALL_DIR/data/notifications" \
             "$SAVED_INSTALL_DIR/data/user_configs" \
             "$SAVED_INSTALL_DIR/data/variables" || print_warning "Impossibile creare alcune directory per i dati"
             
    chown -R m4bot:m4bot "$SAVED_INSTALL_DIR/data" || print_warning "Impossibile impostare i permessi per le directory dei dati"
}

# Funzione per verificare l'installazione
verify_installation() {
    print_message "====================================================="
    print_message "VERIFICA DELL'INSTALLAZIONE"
    print_message "====================================================="
    
    # Lista per tracciare i problemi trovati
    PROBLEMS=()
    
    # Verifica servizi
    print_message "Verifica dei servizi..."
    
    # Controlla Nginx
    if ! systemctl is-active --quiet nginx; then
        print_warning "Nginx non è in esecuzione"
        PROBLEMS+=("nginx_not_running")
    else
        print_success "Nginx in esecuzione"
    fi
    
    # Controlla PostgreSQL
    if ! systemctl is-active --quiet postgresql; then
        print_warning "PostgreSQL non è in esecuzione"
        PROBLEMS+=("postgresql_not_running")
    else
        print_success "PostgreSQL in esecuzione"
    fi
    
    # Controlla servizi M4Bot
    if ! systemctl is-active --quiet m4bot-bot.service; then
        print_warning "Servizio M4Bot bot non è in esecuzione"
        PROBLEMS+=("m4bot_bot_not_running")
    else
        print_success "Servizio M4Bot bot in esecuzione"
    fi
    
    if ! systemctl is-active --quiet m4bot-web.service; then
        print_warning "Servizio M4Bot web non è in esecuzione"
        PROBLEMS+=("m4bot_web_not_running")
    else
        print_success "Servizio M4Bot web in esecuzione"
    fi
    
    # Verifica directory
    print_message "Verifica delle directory..."
    
    # Controlla directory principali
    M4BOT_DIR="/opt/m4bot"
    BOT_DIR="$M4BOT_DIR/bot"
    WEB_DIR="$M4BOT_DIR/web"
    
    if [ ! -d "$M4BOT_DIR" ]; then
        print_warning "Directory principale $M4BOT_DIR non esiste"
        PROBLEMS+=("main_dir_missing")
    fi
    
    if [ ! -d "$BOT_DIR" ]; then
        print_warning "Directory del bot $BOT_DIR non esiste"
        PROBLEMS+=("bot_dir_missing")
    fi
    
    if [ ! -d "$WEB_DIR" ]; then
        print_warning "Directory web $WEB_DIR non esiste"
        PROBLEMS+=("web_dir_missing")
    fi
    
    # Controlla directory di log
    if [ ! -d "$BOT_DIR/logs" ]; then
        print_warning "Directory dei log del bot non esiste"
        PROBLEMS+=("bot_logs_missing")
    fi
    
    # Verifica file di configurazione
    print_message "Verifica dei file di configurazione..."
    
    # Controlla file .env
    if [ ! -f "$M4BOT_DIR/.env" ]; then
        print_warning "File .env non esiste"
        PROBLEMS+=("env_file_missing")
    fi
    
    # Controlla configurazione Nginx
    if [ ! -f "/etc/nginx/sites-available/m4bot" ]; then
        print_warning "File di configurazione Nginx non esiste"
        PROBLEMS+=("nginx_conf_missing")
    fi
    
    # Controlla se ci sono problemi da risolvere
    if [ ${#PROBLEMS[@]} -gt 0 ]; then
        print_message "Sono stati rilevati ${#PROBLEMS[@]} problemi."
        read -p "Vuoi tentare di risolverli automaticamente? (s/n): " fix_confirm
        if [[ $fix_confirm == "s" || $fix_confirm == "S" ]]; then
            autofix_problems
        else
            print_message "Puoi risolvere i problemi manualmente o eseguire lo script fix_common_issues.sh"
        fi
    else
        print_success "Verifica completata: nessun problema rilevato!"
    fi
}

# Funzione per risolvere automaticamente i problemi
autofix_problems() {
    print_message "====================================================="
    print_message "RISOLUZIONE AUTOMATICA DEI PROBLEMI"
    print_message "====================================================="
    
    for problem in "${PROBLEMS[@]}"; do
        case $problem in
            nginx_not_running)
                print_message "Tentativo di avvio di Nginx..."
                systemctl start nginx
                if systemctl is-active --quiet nginx; then
                    print_success "Nginx avviato con successo"
                else
                    print_error "Impossibile avviare Nginx" 0
                fi
                ;;
                
            postgresql_not_running)
                print_message "Tentativo di avvio di PostgreSQL..."
                systemctl start postgresql
                if systemctl is-active --quiet postgresql; then
                    print_success "PostgreSQL avviato con successo"
                else
                    print_error "Impossibile avviare PostgreSQL" 0
                fi
                ;;
                
            m4bot_bot_not_running)
                print_message "Tentativo di avvio del servizio M4Bot bot..."
                systemctl start m4bot-bot.service
                if systemctl is-active --quiet m4bot-bot.service; then
                    print_success "Servizio M4Bot bot avviato con successo"
                else
                    print_error "Impossibile avviare il servizio M4Bot bot" 0
                fi
                ;;
                
            m4bot_web_not_running)
                print_message "Tentativo di avvio del servizio M4Bot web..."
                systemctl start m4bot-web.service
                if systemctl is-active --quiet m4bot-web.service; then
                    print_success "Servizio M4Bot web avviato con successo"
                else
                    print_error "Impossibile avviare il servizio M4Bot web" 0
                fi
                ;;
                
            main_dir_missing|bot_dir_missing|web_dir_missing)
                print_message "Creazione delle directory mancanti..."
                mkdir -p "$M4BOT_DIR/bot/logs" "$M4BOT_DIR/web" || print_error "Impossibile creare le directory" 0
                
                # Verifica se sono stati create correttamente
                if [ -d "$M4BOT_DIR/bot/logs" ] && [ -d "$M4BOT_DIR/web" ]; then
                    print_success "Directory create con successo"
                    
                    # Imposta i permessi corretti
                    chown -R m4bot:m4bot "$M4BOT_DIR" || print_warning "Impossibile impostare i permessi"
                fi
                ;;
                
            bot_logs_missing)
                print_message "Creazione della directory dei log del bot..."
                mkdir -p "$BOT_DIR/logs" || print_error "Impossibile creare la directory dei log" 0
                
                if [ -d "$BOT_DIR/logs" ]; then
                    chown -R m4bot:m4bot "$BOT_DIR/logs" || print_warning "Impossibile impostare i permessi"
                    print_success "Directory dei log creata con successo"
                fi
                ;;
                
            env_file_missing)
                print_message "Ricreazione del file .env..."
                if [ -n "$SAVED_INSTALL_DIR" ] && [ -n "$SAVED_DB_PASSWORD" ] && [ -n "$SAVED_DOMAIN" ] && [ -n "$SAVED_BOT_DIR" ]; then
                    # Genera chiavi segrete
                    SECRET_KEY=$(openssl rand -hex 24)
                    ENCRYPTION_KEY=$(openssl rand -base64 32)
                    
                    # Crea il file .env
                    cat > "$SAVED_INSTALL_DIR/.env" << EOF
# Configurazione database
DB_USER=m4bot_user
DB_PASSWORD=$SAVED_DB_PASSWORD
DB_NAME=m4bot_db
DB_HOST=localhost

# Configurazione Redis per caching avanzato e WebSocket
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# Configurazione dominio e web server
DOMAIN=$SAVED_DOMAIN
WEB_DOMAIN=$SAVED_DOMAIN
WEB_HOST=0.0.0.0
WEB_PORT=5000
DASHBOARD_DOMAIN=dashboard.$SAVED_DOMAIN
CONTROL_DOMAIN=control.$SAVED_DOMAIN

# Configurazione SSL
SSL_CERT=/etc/letsencrypt/live/$SAVED_DOMAIN/fullchain.pem
SSL_KEY=/etc/letsencrypt/live/$SAVED_DOMAIN/privkey.pem

# Chiavi e segreti
SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY

# Credenziali OAuth per Kick.com
CLIENT_ID=01JR9DNAJYARH2466KBR8N2AW2
CLIENT_SECRET=4379baaef9eb1f1ba571372734cf9627a0f36680fd6f877895cb1d3f17065e4f
REDIRECT_URI=https://$SAVED_DOMAIN/auth/callback
SCOPE=user:read channel:read channel:write chat:write events:subscribe

# Configurazione log
LOG_LEVEL=INFO
LOG_FILE=$SAVED_BOT_DIR/logs/m4bot.log

# Configurazioni webhook e sicurezza
WEBHOOK_MAX_RETRIES=3
WEBHOOK_RETRY_DELAY=5
WEBHOOK_TIMEOUT=10
WEBHOOK_IP_WHITELIST=
WEBHOOK_IP_BLACKLIST=
WEBHOOK_RATE_LIMIT_ENABLED=true
WEBHOOK_RATE_LIMIT_MAX_REQUESTS=100
WEBHOOK_RATE_LIMIT_TIME_WINDOW=60
WEBHOOK_RATE_LIMIT_BLOCK_DURATION=300
WEBHOOK_ANTI_REPLAY=true
WEBHOOK_CHECK_TIMESTAMP=true
WEBHOOK_VERIFY_SIGNATURE=true

# Configurazione WebSocket
WS_ENABLED=true
WS_HOST=0.0.0.0
WS_PORT=8765
WS_PATH=/ws
WS_AUTH_REQUIRED=true

# Directory per dati
DATA_DIR=$SAVED_INSTALL_DIR/data
TEMPLATES_DIR=$SAVED_INSTALL_DIR/data/templates
WORKFLOWS_DIR=$SAVED_INSTALL_DIR/data/workflows
NOTIFICATIONS_DIR=$SAVED_INSTALL_DIR/data/notifications
USER_CONFIGS_DIR=$SAVED_INSTALL_DIR/data/user_configs
VARIABLES_DIR=$SAVED_INSTALL_DIR/data/variables

# Configurazione VPS
VPS_IP=

# Configurazione OBS
OBS_WEBSOCKET_URL=ws://localhost:4455
OBS_WEBSOCKET_PASSWORD=

# Impostazioni sicurezza
ALLOW_REGISTRATION=true
MAX_LOGIN_ATTEMPTS=5
LOGIN_TIMEOUT=300
SESSION_LIFETIME=604800
REQUIRE_HTTPS=true
CORS_ALLOWED_ORIGINS=*

# Cooldown predefiniti (in secondi)
DEFAULT_COMMAND_COOLDOWN=5
DEFAULT_USER_COOLDOWN=2
DEFAULT_GLOBAL_COOLDOWN=1

# Configurazione manutenzione
MAINTENANCE_MODE=false
AUTO_BACKUP=true
BACKUP_RETENTION_DAYS=7

# Configurazione monitoraggio
MONITOR_CHECK_INTERVAL=300

# Configurazioni WhatsApp
WHATSAPP_API_VERSION=v16.0
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_TOKEN=
WHATSAPP_VERIFY_TOKEN=

# Configurazioni Telegram
TELEGRAM_BOT_TOKEN=
TELEGRAM_WEBHOOK_URL=

# Configurazioni YouTube
YOUTUBE_API_KEY=
YOUTUBE_CHANNEL_ID=
YOUTUBE_METRICS_UPDATE_INTERVAL=60
EOF
                    chown m4bot:m4bot "$SAVED_INSTALL_DIR/.env" || print_warning "Impossibile impostare i permessi per .env"
                    chmod 600 "$SAVED_INSTALL_DIR/.env" || print_warning "Impossibile impostare i permessi per .env"
                    
                    print_success "File .env ricreato con successo"
                else
                    print_error "Variabili necessarie non disponibili, impossibile ricreare il file .env" 0
                fi
                ;;
                
            nginx_conf_missing)
                print_message "Ricreazione del file di configurazione Nginx..."
                if [ -n "$SAVED_DOMAIN" ] && [ -n "$SAVED_WEB_DIR" ]; then
                    # Crea il file di configurazione Nginx
                    cat > /etc/nginx/sites-available/m4bot << EOF
server {
    listen 80;
    server_name $SAVED_DOMAIN www.$SAVED_DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static/ {
        alias $SAVED_WEB_DIR/static/;
        expires 30d;
    }

    # WebSocket per notifiche
    location /ws/notifications {
        proxy_pass http://127.0.0.1:5000/ws/notifications;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400;
    }

    # WebSocket per metriche
    location /ws/metrics {
        proxy_pass http://127.0.0.1:5000/ws/metrics;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400;
    }

    # Legacy WebSocket
    location /socket.io {
        proxy_pass http://127.0.0.1:5000/socket.io;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400;
    }
}
EOF

                    # Attiva il sito
                    ln -sf /etc/nginx/sites-available/m4bot /etc/nginx/sites-enabled/ || print_warning "Impossibile attivare il sito Nginx"
                    
                    # Testa la configurazione
                    nginx -t
                    if [ $? -eq 0 ]; then
                        # Riavvia Nginx
                        systemctl restart nginx || print_warning "Impossibile riavviare Nginx"
                        print_success "Configurazione Nginx ricreata con successo"
                    else
                        print_error "Configurazione Nginx non valida" 0
                    fi
                else
                    print_error "Variabili necessarie non disponibili, impossibile ricreare la configurazione Nginx" 0
                fi
                ;;
        esac
    done
    
    print_message "Risoluzione dei problemi completata."
    
    # Verifica se tutti i servizi sono in esecuzione dopo i fix
    if systemctl is-active --quiet nginx && \
       systemctl is-active --quiet postgresql && \
       systemctl is-active --quiet m4bot-bot.service && \
       systemctl is-active --quiet m4bot-web.service; then
        print_success "Tutti i servizi sono ora in esecuzione!"
    else
        print_warning "Alcuni servizi non sono ancora attivi. Potrebbe essere necessario un intervento manuale."
    fi
}

# Funzione per configurare i sottodomini (opzionale)
setup_subdomains() {
    print_message "====================================================="
    print_message "CONFIGURAZIONE DEI SOTTODOMINI"
    print_message "====================================================="
    
    read -p "Vuoi configurare i sottodomini (dashboard.$SAVED_DOMAIN e control.$SAVED_DOMAIN)? (s/n): " setup_confirm
    if [[ $setup_confirm != "s" && $setup_confirm != "S" ]]; then
        print_message "Configurazione dei sottodomini saltata."
        return
    fi
    
    # Verifica se lo script setup_subdomains.sh esiste
    if [ -f "$HOME/M4Bot/scripts/setup_subdomains.sh" ]; then
        print_message "Esecuzione dello script di configurazione dei sottodomini..."
        chmod +x "$HOME/M4Bot/scripts/setup_subdomains.sh"
        bash "$HOME/M4Bot/scripts/setup_subdomains.sh" || print_warning "Errore nell'esecuzione dello script di configurazione dei sottodomini"
    else
        print_warning "Script di configurazione dei sottodomini non trovato"
        
        # Verifica se esistono gli script separati
        if [ -f "$HOME/M4Bot/scripts/add_subdomains.sh" ] && \
           [ -f "$HOME/M4Bot/scripts/update_env.sh" ] && \
           [ -f "$HOME/M4Bot/scripts/update_webapp.sh" ]; then
            
            print_message "Trovati script separati per la configurazione dei sottodomini"
            read -p "Vuoi eseguire questi script individualmente? (s/n): " run_individual
            
            if [[ $run_individual == "s" || $run_individual == "S" ]]; then
                chmod +x "$HOME/M4Bot/scripts/add_subdomains.sh" \
                        "$HOME/M4Bot/scripts/update_env.sh" \
                        "$HOME/M4Bot/scripts/update_webapp.sh"
                
                bash "$HOME/M4Bot/scripts/add_subdomains.sh" && \
                bash "$HOME/M4Bot/scripts/update_env.sh" && \
                bash "$HOME/M4Bot/scripts/update_webapp.sh" || \
                print_warning "Errore nell'esecuzione degli script individuali"
            fi
        else
            print_warning "Script per la configurazione dei sottodomini non trovati"
        fi
    fi
}

# Funzione per la diagnostica avanzata e risoluzione automatica di problemi complessi
advanced_diagnostics() {
    print_message "Esecuzione diagnostica avanzata e risoluzione problemi"
    
    # Controllo conflitti di porte
    print_message "Controllo conflitti di porte..."
    PORT_LIST=(80 443 8000 5432)
    for PORT in "${PORT_LIST[@]}"; do
        if netstat -tuln | grep -q ":$PORT "; then
            PROCESS=$(lsof -i:$PORT -t)
            if [[ $PORT == 80 ]] || [[ $PORT == 443 ]]; then
                if ! systemctl status nginx | grep -q "active (running)"; then
                    print_warning "Porta $PORT in uso dal processo $PROCESS. Tentativo di risoluzione..."
                    kill -15 $PROCESS 2>/dev/null || kill -9 $PROCESS 2>/dev/null
                    sleep 2
                fi
            elif [[ $PORT == 5432 ]]; then
                if ! systemctl status postgresql | grep -q "active (running)"; then
                    print_warning "Porta PostgreSQL $PORT in uso da un processo inatteso. Tentativo di risoluzione..."
                    kill -15 $PROCESS 2>/dev/null || kill -9 $PROCESS 2>/dev/null
                    sleep 2
                    systemctl start postgresql
                fi
            else
                print_warning "Porta $PORT in uso dal processo $PROCESS. Tentativo di risoluzione..."
                kill -15 $PROCESS 2>/dev/null || kill -9 $PROCESS 2>/dev/null
                sleep 2
            fi
        fi
    done
    
    # Controllo accesso PostgreSQL
    print_message "Verifica accesso PostgreSQL..."
    if ! su - postgres -c "psql -c '\l'" >/dev/null 2>&1; then
        print_warning "Problemi di accesso a PostgreSQL. Tentativo di riparazione..."
        systemctl restart postgresql
        sleep 5
        
        # Verifica permessi file di configurazione PostgreSQL
        chown -R postgres:postgres /var/lib/postgresql
        chmod 700 /var/lib/postgresql/*/main/
        
        # Controllo se è necessario ricostruire il cluster PostgreSQL
        if ! su - postgres -c "psql -c '\l'" >/dev/null 2>&1; then
            print_warning "Tentativo di ricostruzione del cluster PostgreSQL..."
            pg_dropcluster --stop $(pg_lsclusters | grep 5432 | awk '{print $1}') main
            pg_createcluster $(pg_lsclusters | grep 5432 | awk '{print $1}') main
            systemctl restart postgresql
            
            # Ricrea l'utente e il database
            setup_database
            initialize_database
        fi
    fi
    
    # Controllo permessi file
    print_message "Verifica permessi file critici..."
    find /opt/m4bot -type f -exec chmod 644 {} \;
    find /opt/m4bot -type d -exec chmod 755 {} \;
    find /opt/m4bot/scripts -type f -name "*.sh" -exec chmod +x {} \;
    chown -R m4bot:m4bot /opt/m4bot
    
    # Controllo validità certificati SSL
    print_message "Verifica certificati SSL..."
    if [[ -f "/etc/letsencrypt/live/$SAVED_DOMAIN/fullchain.pem" ]]; then
        CERT_EXPIRY=$(openssl x509 -enddate -noout -in "/etc/letsencrypt/live/$SAVED_DOMAIN/fullchain.pem" | cut -d= -f2)
        EXPIRY_DATE=$(date -d "$CERT_EXPIRY" +%s)
        CURRENT_DATE=$(date +%s)
        DAYS_LEFT=$(( ($EXPIRY_DATE - $CURRENT_DATE) / 86400 ))
        
        if [[ $DAYS_LEFT -lt 15 ]]; then
            print_warning "Il certificato SSL scadrà tra $DAYS_LEFT giorni. Tentativo di rinnovo..."
            certbot renew --quiet
        fi
    else
        print_warning "Certificati SSL non trovati. Tentativo di crearli nuovamente..."
        setup_ssl
    fi
    
    # Controllo errori configurazione Nginx
    print_message "Verifica configurazione Nginx..."
    if ! nginx -t >/dev/null 2>&1; then
        print_warning "Errori nella configurazione Nginx. Tentativo di riparazione..."
        # Backup della configurazione corrente
        cp /etc/nginx/sites-available/m4bot.conf /etc/nginx/sites-available/m4bot.conf.bak
        
        # Ricrea la configurazione
        setup_nginx
        
        # Riavvia Nginx se la configurazione è valida
        if nginx -t >/dev/null 2>&1; then
            systemctl restart nginx
        else
            print_error "Non è stato possibile riparare la configurazione Nginx. È necessario un intervento manuale."
        fi
    fi
    
    # Controllo dipendenze Python
    print_message "Verifica dipendenze Python..."
    source /opt/m4bot/venv/bin/activate
    if ! pip check >/dev/null 2>&1; then
        print_warning "Problemi con le dipendenze Python. Tentativo di reinstallazione..."
        pip install --upgrade pip
        pip install -r /opt/m4bot/requirements.txt
    fi
    deactivate
    
    # Controllo connettività rete
    print_message "Verifica connettività di rete..."
    if ! ping -c 1 google.com >/dev/null 2>&1; then
        print_warning "Problemi di connettività Internet. Verifica la configurazione di rete."
    fi
    
    # Controllo spazio disco
    print_message "Verifica spazio disco disponibile..."
    DISK_SPACE=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [[ $DISK_SPACE -gt 90 ]]; then
        print_warning "Spazio disco quasi esaurito ($DISK_SPACE%). Pulizia cache..."
        apt-get clean
        apt-get autoremove -y
        find /var/log -type f -name "*.gz" -delete
        find /var/log -type f -name "*.log.*" -delete
    fi
    
    # Controllo stato servizi
    print_message "Verifica stato servizi sistemici..."
    for SERVICE in nginx postgresql redis-server; do
        if ! systemctl is-active --quiet $SERVICE; then
            print_warning "Il servizio $SERVICE non è attivo. Tentativo di avvio..."
            systemctl restart $SERVICE
        fi
    done
    
    print_message "Diagnostica avanzata completata."
}

# Funzione per eseguire test funzionali completi
run_functional_tests() {
    print_message "Esecuzione test funzionali"
    
    # Test connessione database
    print_message "Test connessione database..."
    su - m4bot -c "cd /opt/m4bot && source venv/bin/activate && python -c 'from app.db import get_db; next(get_db())'" 2>/dev/null
    if [ $? -eq 0 ]; then
        print_success "✅ Connessione database OK"
    else
        print_error "❌ Errore connessione database"
        print_message "Tentativo di riparazione database..."
        initialize_database
    fi
    
    # Test connessione Redis
    print_message "Test connessione Redis..."
    if systemctl is-active --quiet redis-server; then
        su - m4bot -c "cd /opt/m4bot && source venv/bin/activate && python -c 'import redis.asyncio; r = redis.asyncio.Redis(host=\"localhost\", port=6379, db=0); r.ping()'" 2>/dev/null
        if [ $? -eq 0 ]; then
            print_success "✅ Connessione Redis OK"
        else
            print_warning "⚠️ Errore connessione Redis"
            print_message "Riavvio del servizio Redis..."
            systemctl restart redis-server
            sleep 3
        fi
    else
        print_warning "⚠️ Servizio Redis non attivo"
        print_message "Avvio del servizio Redis..."
        systemctl start redis-server
        sleep 3
    fi
    
    # Test endpoint API
    print_message "Test endpoint API..."
    systemctl is-active --quiet m4bot-web
    if [ $? -eq 0 ]; then
        # Attendere che il servizio sia completamente attivo
        sleep 5
        RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs || echo "000")
        if [[ "$RESPONSE" == "200" ]]; then
            print_success "✅ API accessibile (HTTP 200)"
        else
            print_warning "⚠️ API non accessibile (HTTP $RESPONSE)"
            print_message "Riavvio del servizio web..."
            systemctl restart m4bot-web
            sleep 5
        fi
    else
        print_warning "⚠️ Servizio web non attivo"
        print_message "Avvio del servizio web..."
        systemctl start m4bot-web
        sleep 5
    fi
    
    # Test nuove rotte API
    print_message "Test nuove rotte API..."
    ROUTE_TESTS=(
        "/api/metrics/live"
        "/api/templates/all"
        "/api/dashboard/widgets"
        "/api/workflows"
        "/api/notifications"
        "/api/variables"
    )
    
    for ROUTE in "${ROUTE_TESTS[@]}"; do
        RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5000$ROUTE || echo "000")
        if [[ "$RESPONSE" == "200" || "$RESPONSE" == "401" || "$RESPONSE" == "302" ]]; then
            # 200 = OK, 401 = Unauthorized (richiede login), 302 = Redirect (a login)
            print_success "✅ Rotta $ROUTE raggiungibile"
        else
            print_warning "⚠️ Rotta $ROUTE non raggiungibile (HTTP $RESPONSE)"
        fi
    done
    
    # Test WebSocket
    print_message "Test connessione WebSocket..."
    # Usa un comando curl con timeout breve per verificare se la connessione WebSocket funziona
    RESPONSE=$(curl -s -N -i --http1.1 -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dummy" --max-time 2 http://localhost:5000/ws/notifications | grep -c "101 Switching Protocols" || echo "0")
    if [ "$RESPONSE" -gt 0 ]; then
        print_success "✅ WebSocket raggiungibile"
    else
        print_warning "⚠️ WebSocket non funzionante o non raggiungibile"
    fi
    
    # Test servizio bot
    print_message "Test funzionalità bot..."
    systemctl is-active --quiet m4bot-bot
    if [ $? -eq 0 ]; then
        BOT_PID=$(systemctl show -p MainPID m4bot-bot | cut -d= -f2)
        if [[ "$BOT_PID" != "0" ]]; then
            print_success "✅ Servizio bot attivo (PID: $BOT_PID)"
        else
            print_warning "⚠️ Servizio bot registrato ma non in esecuzione"
            print_message "Riavvio del servizio bot..."
            systemctl restart m4bot-bot
            sleep 5
        fi
    else
        print_warning "⚠️ Servizio bot non attivo"
        print_message "Avvio del servizio bot..."
        systemctl start m4bot-bot
        sleep 5
    fi
    
    # Test configurazione Nginx
    print_message "Test configurazione Nginx..."
    if nginx -t >/dev/null 2>&1; then
        print_success "✅ Configurazione Nginx valida"
        
        # Test raggiungibilità sito tramite Nginx
        if [[ -n "$SAVED_DOMAIN" ]]; then
            print_message "Test accesso web tramite Nginx..."
            if curl -s -o /dev/null -w "%{http_code}" https://$SAVED_DOMAIN/login -k | grep -q "200\|301\|302"; then
                print_success "✅ Sito web raggiungibile tramite HTTPS"
            else
                print_warning "⚠️ Sito web non raggiungibile tramite HTTPS"
                
                # Test accesso HTTP per verificare se è il certificato SSL il problema
                if curl -s -o /dev/null -w "%{http_code}" http://$SAVED_DOMAIN/login | grep -q "200\|301\|302"; then
                    print_warning "⚠️ Sito raggiungibile via HTTP ma non HTTPS - Possibile problema SSL"
                    # Riparazione certificato SSL
                    setup_ssl
                else
                    print_warning "⚠️ Sito non raggiungibile via HTTP né HTTPS - Verifica configurazione DNS"
                    print_message "Assicurati che il dominio $SAVED_DOMAIN punti a questo server"
                fi
            fi
        fi
    else
        print_error "❌ Configurazione Nginx non valida"
        print_message "Riparazione configurazione Nginx..."
        setup_nginx
    fi
    
    print_message "Test funzionali completati."
}

# Funzione principale
main() {
    clear
    check_root
    setup_script_permissions
    confirm_installation
    
    update_system
    install_dependencies
    create_system_user
    setup_database
    initialize_database
    setup_repository
    setup_python_env
    setup_nginx
    setup_ssl
    setup_systemd_services
    setup_management_scripts
    setup_env_file
    
    # Avvia i servizi
    print_message "Avvio dei servizi..."
    systemctl start m4bot-bot.service || print_warning "Impossibile avviare il servizio del bot"
    systemctl start m4bot-web.service || print_warning "Impossibile avviare il servizio web"
    
    # Configurazione dei sottodomini (opzionale)
    setup_subdomains
    
    # Diagnostica avanzata e risoluzione problemi complessi
    advanced_diagnostics
    
    # Test funzionali completi
    run_functional_tests
    
    # Verifica finale dell'installazione
    verify_installation
    
    # Mostra le credenziali di accesso
    print_message "====================================================="
    print_message "INSTALLAZIONE COMPLETATA!"
    print_message "====================================================="
    print_message "Credenziali di accesso:"
    print_message "URL: https://$SAVED_DOMAIN"
    print_message "Username: admin"
    print_message "Password: admin123"
    print_message ""
    print_message "IMPORTANTE: Cambia la password dell'amministratore dopo il primo accesso."
    print_message "====================================================="
    print_message "Per gestire M4Bot, usa i seguenti comandi:"
    print_message "m4bot-start  - Avvia i servizi"
    print_message "m4bot-stop   - Ferma i servizi"
    print_message "m4bot-status - Controlla lo stato dei servizi"
    print_message "====================================================="
}

# Esecuzione dello script
main
