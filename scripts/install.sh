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
    apt-get install -y python3 python3-pip python3-venv nginx postgresql certbot python3-certbot-nginx git supervisor || print_error "Impossibile installare le dipendenze" 1
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
    mkdir -p "$BOT_DIR" "$WEB_DIR" "$BOT_DIR/logs" || print_error "Impossibile creare le directory" 1
    
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
    
    # Crea directory per immagini e JS se non esistono
    mkdir -p "$WEB_DIR/static/js" "$WEB_DIR/static/images" "$WEB_DIR/static/css"
    
    # Imposta permessi
    chown -R m4bot:m4bot "$INSTALL_DIR" || print_error "Impossibile impostare i permessi" 1
    chmod +x "$BOT_DIR/m4bot.py" || print_warning "Impossibile impostare permessi di esecuzione"
    
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
        pip install aiohttp asyncpg websockets requests pyyaml python-dotenv cryptography bcrypt || print_warning "Impossibile installare alcune dipendenze del bot"
    fi
    
    # Installa dipendenze web
    pip install flask==2.3.3 flask-babel==2.0.0 quart==0.19.4 gunicorn python-dotenv jinja2 pyyaml || print_warning "Impossibile installare alcune dipendenze web"
    
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

    location /socket.io {
        proxy_pass http://127.0.0.1:5000/socket.io;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
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
    ENCRYPTION_KEY=$(openssl rand -hex 16)
    
    # Crea il file .env
    cat > "$SAVED_INSTALL_DIR/.env" << EOF
# Configurazione database
DB_USER=m4bot_user
DB_PASSWORD=$SAVED_DB_PASSWORD
DB_NAME=m4bot_db
DB_HOST=localhost

# Configurazione dominio
DOMAIN=$SAVED_DOMAIN
WEB_DOMAIN=$SAVED_DOMAIN
WEB_HOST=0.0.0.0
WEB_PORT=5000

# Chiavi e segreti
SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY
CLIENT_ID=01JR9DNAJYARH2466KBR8N2AW2
CLIENT_SECRET=4379baaef9eb1f1ba571372734cf9627a0f36680fd6f877895cb1d3f17065e4f
REDIRECT_URI=https://$SAVED_DOMAIN/auth/callback

# Configurazione log
LOG_LEVEL=INFO
LOG_FILE=$SAVED_BOT_DIR/logs/m4bot.log

# Altre configurazioni
DEFAULT_COMMAND_COOLDOWN=5
DEFAULT_USER_COOLDOWN=2
DEFAULT_GLOBAL_COOLDOWN=1
EOF
    
    # Imposta i permessi
    chown m4bot:m4bot "$SAVED_INSTALL_DIR/.env" || print_warning "Impossibile impostare i permessi per .env"
    chmod 600 "$SAVED_INSTALL_DIR/.env" || print_warning "Impossibile impostare i permessi per .env"
    
    print_success "File .env configurato"
}

# Funzione principale
main() {
    clear
    check_root
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
