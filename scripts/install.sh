#!/bin/bash
# Script di installazione completa di M4Bot
# Questo script installa e configura tutti i componenti necessari per M4Bot

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

# Verifica privilegi root
check_root

print_message "====================================================="
print_message "      INSTALLAZIONE COMPLETA DI M4BOT v2.0           "
print_message "====================================================="
print_message "Questo script installerà e configurerà tutti i componenti di M4Bot:"
print_message "- Dipendenze di sistema"
print_message "- Database PostgreSQL"
print_message "- Server web Nginx"
print_message "- Certificato SSL (Let's Encrypt)"
print_message "- Servizi systemd"
print_message "- Applicazione web e bot"
print_message "- Script di gestione"

# Configurazione
M4BOT_DIR="/opt/m4bot"
WEB_DIR="$M4BOT_DIR/web"
BOT_DIR="$M4BOT_DIR/bot"
LOGS_DIR="$BOT_DIR/logs"
STATIC_DIR="$WEB_DIR/static"
TEMPLATES_DIR="$WEB_DIR/templates"
DB_NAME="m4bot_db"
DB_USER="m4bot_user"
DB_PASSWORD="$(openssl rand -hex 12)"  # Genera password casuale
DOMAIN="m4bot.it"
EMAIL="admin@m4bot.it"
ADMIN_USER="admin"
ADMIN_PASSWORD="admin123"
ADMIN_EMAIL="admin@m4bot.it"

# Chiedi conferma
read -p "Continuare con l'installazione? (s/n): " confirm
if [[ "$confirm" != "s" && "$confirm" != "S" ]]; then
    print_error "Installazione annullata" 0
        exit 0
fi

# Funzioni di installazione
update_system() {
print_message "Aggiornamento del sistema..."
    apt-get update
    apt-get upgrade -y
    print_success "Sistema aggiornato"
}

install_dependencies() {
    print_message "Installazione delle dipendenze di sistema..."
    apt-get install -y python3 python3-pip python3-venv python3-dev python3-bcrypt \
        postgresql postgresql-contrib nginx certbot python3-certbot-nginx \
        git wget curl build-essential libpq-dev net-tools sudo
    print_success "Dipendenze installate"
}

setup_directories() {
    print_message "Creazione delle directory di M4Bot..."
    # Crea directory principale
    mkdir -p "$M4BOT_DIR"
    mkdir -p "$WEB_DIR"
    mkdir -p "$BOT_DIR"
    mkdir -p "$LOGS_DIR"
    mkdir -p "$STATIC_DIR"
    mkdir -p "$STATIC_DIR/img"
    mkdir -p "$STATIC_DIR/css"
    mkdir -p "$STATIC_DIR/js"
    mkdir -p "$TEMPLATES_DIR"
    print_success "Directory create"
}

# Crea utente di sistema
create_user() {
    print_message "Creazione dell'utente di sistema m4bot..."
    
if id "m4bot" &>/dev/null; then
        print_warning "Utente m4bot già esistente"
    else
        useradd -r -m -s /bin/bash m4bot
        print_success "Utente m4bot creato con successo"
    fi
    
    # Imposta i permessi
    chown -R m4bot:m4bot "$M4BOT_DIR"
    chmod -R 755 "$M4BOT_DIR"
    print_success "Permessi impostati"
}

# Clona il repository
clone_repository() {
        print_message "Clonazione del repository M4Bot..."
    
    # Verifica se ci sono file esistenti
    if [ -f "$WEB_DIR/app.py" ] || [ -f "$BOT_DIR/m4bot.py" ]; then
        print_warning "File esistenti rilevati. Creazione backup..."
        BACKUP_DIR="/tmp/m4bot_backup_$(date +%s)"
        mkdir -p "$BACKUP_DIR"
        cp -r "$M4BOT_DIR" "$BACKUP_DIR"
        print_message "Backup creato in $BACKUP_DIR"
    fi
    
    # Clone temporaneo del repository
    TEMP_DIR="/tmp/m4bot_temp"
    rm -rf "$TEMP_DIR"
    git clone https://github.com/M4Tronick/M4Bot.git "$TEMP_DIR" || {
        print_warning "Impossibile clonare da GitHub, utilizzo del repository locale..."
        if [ -d "$(dirname "$0")/../" ]; then
            cp -r "$(dirname "$0")/../"* "$TEMP_DIR/"
        else
            print_error "Nessun repository disponibile. Impossibile continuare." 1
        fi
    }
    
    # Copia i file dal repository temporaneo
    if [ -d "$TEMP_DIR/web" ]; then
        cp -r "$TEMP_DIR/web/"* "$WEB_DIR/"
        print_success "File web copiati"
    fi
    
    if [ -d "$TEMP_DIR/bot" ]; then
        cp -r "$TEMP_DIR/bot/"* "$BOT_DIR/"
        print_success "File bot copiati"
    fi
    
    if [ -d "$TEMP_DIR/scripts" ]; then
        cp -r "$TEMP_DIR/scripts/"* "$(dirname "$0")/"
        chmod +x "$(dirname "$0")"/*.sh
        print_success "Script copiati"
    fi
    
    # Pulisci
    rm -rf "$TEMP_DIR"
}

# Configura ambiente virtuale Python
setup_virtualenv() {
    print_message "Configurazione dell'ambiente virtuale Python..."
        python3 -m venv "$M4BOT_DIR/venv"
    
    # Aggiorna pip
    "$M4BOT_DIR/venv/bin/pip" install --upgrade pip
    
    # Installa dipendenze base
    "$M4BOT_DIR/venv/bin/pip" install wheel setuptools
    "$M4BOT_DIR/venv/bin/pip" install flask flask-sqlalchemy flask-login psycopg2-binary \
        python-dotenv requests asyncio aiohttp bcrypt gunicorn websockets APScheduler
    
    # Installa dipendenze specifiche
    if [ -f "$WEB_DIR/requirements.txt" ]; then
        "$M4BOT_DIR/venv/bin/pip" install -r "$WEB_DIR/requirements.txt"
    fi
    
    if [ -f "$BOT_DIR/requirements.txt" ]; then
        "$M4BOT_DIR/venv/bin/pip" install -r "$BOT_DIR/requirements.txt"
    fi
    
    print_success "Ambiente virtuale configurato"
}

# Configura PostgreSQL
setup_database() {
    print_message "Configurazione del database PostgreSQL..."

    # Avvia PostgreSQL se non è in esecuzione
    if ! systemctl is-active --quiet postgresql; then
        systemctl start postgresql
    fi
    
    # Crea utente e database
    if sudo -u postgres psql -lqt | grep -q "$DB_NAME"; then
        print_warning "Database $DB_NAME già esistente, verrà ricreato..."
        sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;"
    fi
    
    sudo -u postgres psql -c "DROP ROLE IF EXISTS $DB_USER;"
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
    
    # Salva credenziali
    cat > "$M4BOT_DIR/.env" << EOF
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_NAME=$DB_NAME
DB_HOST=localhost
DOMAIN=$DOMAIN
SECRET_KEY=$(openssl rand -hex 24)
EOF
    
    # Proteggi il file .env
    chmod 600 "$M4BOT_DIR/.env"
    chown m4bot:m4bot "$M4BOT_DIR/.env"

print_success "Database configurato"
}

# Inizializza il database con tabelle e dati iniziali
initialize_database() {
    print_message "Inizializzazione del database con le tabelle..."
    
    # Crea le tabelle
    cat > /tmp/init_m4bot_tables.sql << EOF
-- Tabella utenti
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabella canali
CREATE TABLE IF NOT EXISTS channels (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    owner_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Tabella comandi
CREATE TABLE IF NOT EXISTS commands (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    name VARCHAR(255) NOT NULL,
    response TEXT,
    cooldown INTEGER DEFAULT 0,
    user_level VARCHAR(50) DEFAULT 'everyone',
    enabled BOOLEAN DEFAULT TRUE,
    is_advanced BOOLEAN DEFAULT FALSE,
    custom_code TEXT,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (channel_id, name)
);

-- Tabella messaggi chat
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    user_id VARCHAR(255),
    username VARCHAR(255),
    content TEXT,
    is_command BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabella punti canale
CREATE TABLE IF NOT EXISTS channel_points (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    user_id VARCHAR(255),
    points INTEGER DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (channel_id, user_id)
);

-- Tabella impostazioni canale
CREATE TABLE IF NOT EXISTS channel_settings (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id) UNIQUE,
    welcome_message TEXT,
    prefix VARCHAR(10) DEFAULT '!',
    chat_rules TEXT,
    auto_mod_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabella predizioni
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    title VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    options JSONB NOT NULL,
    winner_option INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ends_at TIMESTAMP WITH TIME ZONE
);

-- Tabella sessioni
CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    data JSONB,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Indici
CREATE INDEX IF NOT EXISTS idx_chat_messages_channel_id ON chat_messages(channel_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_commands_channel_id ON commands(channel_id);
CREATE INDEX IF NOT EXISTS idx_channel_points_channel_id ON channel_points(channel_id);
EOF
    
    # Esegui lo script SQL
    sudo -u postgres psql -d "$DB_NAME" -f /tmp/init_m4bot_tables.sql
rm -f /tmp/init_m4bot_tables.sql

    # Crea utente admin
    print_message "Creazione dell'utente amministratore..."
    
# Genera hash della password
    PASS_HASH=$(python3 -c "import bcrypt; print(bcrypt.hashpw('$ADMIN_PASSWORD'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'))")

# Inserisci l'utente admin
    sudo -u postgres psql -d "$DB_NAME" -c "INSERT INTO users (username, email, password_hash, is_admin) VALUES ('$ADMIN_USER', '$ADMIN_EMAIL', '$PASS_HASH', TRUE);"

print_success "Database inizializzato"
}

# Configura Nginx
setup_nginx() {
print_message "Configurazione di Nginx..."
    
    # Crea file di configurazione
    cat > /etc/nginx/sites-available/m4bot << EOF
server {
    listen 80;
    server_name $DOMAIN _;

    # Servi direttamente index.html se richiesto direttamente
    location = / {
        root $STATIC_DIR;
        try_files /index.html @proxy;
    }

    # Proxy tutte le altre richieste all'app Flask
    location @proxy {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
    }

    # Serve i file statici direttamente
    location /static/ {
        alias $STATIC_DIR/;
        access_log off;
        expires 30d;
    }
    
    # Configurazione per WebSocket
    location /ws {
        proxy_pass http://localhost:5001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF
    
# Abilita il sito
    ln -sf /etc/nginx/sites-available/m4bot /etc/nginx/sites-enabled/
    
    # Rimuovi default se esiste
    if [ -f /etc/nginx/sites-enabled/default ]; then
rm -f /etc/nginx/sites-enabled/default
    fi
    
    # Verifica configurazione
    nginx -t && systemctl reload nginx
    print_success "Nginx configurato"
}

# Configura Let's Encrypt
setup_ssl() {
    print_message "Configurazione SSL con Let's Encrypt..."
    
    read -p "Configurare SSL con Let's Encrypt? (s/n): " ssl_choice
    if [[ "$ssl_choice" == "s" || "$ssl_choice" == "S" ]]; then
        certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m $EMAIL || {
            print_warning "Impossibile configurare SSL ora. Potrai eseguire manualmente:"
            print_warning "certbot --nginx -d $DOMAIN -m $EMAIL"
        }
    else
        print_warning "Configurazione SSL saltata"
    fi
}

# Crea servizi systemd
setup_services() {
    print_message "Configurazione dei servizi systemd..."
    
    # Servizio per il bot
    cat > /etc/systemd/system/m4bot-bot.service << EOF
[Unit]
Description=M4Bot Bot Service
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$BOT_DIR
ExecStart=$M4BOT_DIR/venv/bin/python m4bot.py
Restart=on-failure
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=m4bot-bot
Environment="PATH=$M4BOT_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

[Install]
WantedBy=multi-user.target
EOF

    # Servizio per l'applicazione web
    cat > /etc/systemd/system/m4bot-web.service << EOF
[Unit]
Description=M4Bot Web Service
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$WEB_DIR
ExecStart=$M4BOT_DIR/venv/bin/gunicorn -w 3 -b 127.0.0.1:5000 app:app
Restart=on-failure
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=m4bot-web
Environment="PATH=$M4BOT_DIR/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

[Install]
WantedBy=multi-user.target
EOF

    # Ricarica systemd
    systemctl daemon-reload
    
    # Abilita i servizi
    systemctl enable m4bot-bot.service
    systemctl enable m4bot-web.service
    
    print_success "Servizi configurati"
}

# Crea script di gestione
create_management_scripts() {
    print_message "Creazione degli script di gestione..."
    
    # common.sh - Funzioni comuni
    cat > /usr/local/bin/common.sh << EOF
#!/bin/bash
# Script con funzioni comuni per M4Bot

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzioni di utilità
check_root() {
    if [ "\$(id -u)" != "0" ]; then
        echo -e "\${RED}Errore: Questo script deve essere eseguito come root\${NC}"
        exit 1
    fi
}

print_message() {
    echo -e "\${BLUE}[M4Bot]\${NC} \$1"
}

print_error() {
    echo -e "\${RED}[ERRORE]\${NC} \$1"
    if [ -n "\$2" ]; then
        exit \$2
    fi
}

print_success() {
    echo -e "\${GREEN}[SUCCESSO]\${NC} \$1"
}

print_warning() {
    echo -e "\${YELLOW}[AVVISO]\${NC} \$1"
}

check_postgres() {
    if ! systemctl is-active --quiet postgresql; then
        print_warning "PostgreSQL non è in esecuzione, tentativo di avvio..."
        systemctl start postgresql
        if [ \$? -eq 0 ]; then
            print_success "PostgreSQL avviato con successo"
        else
            print_error "Impossibile avviare PostgreSQL" 1
        fi
    else
        print_success "PostgreSQL è in esecuzione"
    fi
}

check_nginx() {
    if ! systemctl is-active --quiet nginx; then
        print_warning "Nginx non è in esecuzione, tentativo di avvio..."
        systemctl start nginx
        if [ \$? -eq 0 ]; then
            print_success "Nginx avviato con successo"
        else
            print_error "Impossibile avviare Nginx" 1
        fi
    else
        print_success "Nginx è in esecuzione"
    fi
}

check_services() {
    print_message "Controllo dei servizi..."
    
    # Controlla PostgreSQL
    check_postgres
    
    # Controlla Nginx
    check_nginx
    
    print_message "Stato dei servizi:"
    systemctl status m4bot-bot.service --no-pager | grep Active
    systemctl status m4bot-web.service --no-pager | grep Active
    systemctl status nginx --no-pager | grep Active
    systemctl status postgresql --no-pager | grep Active
}
EOF
    
    chmod +x /usr/local/bin/common.sh
    
    # m4bot-start
    cat > /usr/local/bin/m4bot-start << EOF
#!/bin/bash
# Script per avviare M4Bot

# Carica le funzioni comuni
source /usr/local/bin/common.sh

# Verifica che l'utente sia root
check_root

print_message "Avvio di M4Bot..."

# Verifica che la directory dei log esista
if [ ! -d "/opt/m4bot/bot/logs" ]; then
    print_warning "La directory dei log non esiste, creazione in corso..."
    mkdir -p /opt/m4bot/bot/logs
    chown -R m4bot:m4bot /opt/m4bot/bot/logs
    chmod -R 755 /opt/m4bot/bot/logs
    print_success "Directory dei log creata"
fi

# Verifica che i servizi di base siano in esecuzione
check_services

# Avvia i servizi di M4Bot
systemctl start m4bot-bot.service
systemctl start m4bot-web.service

print_message "Stato dei servizi:"
systemctl status m4bot-bot.service --no-pager | grep Active
systemctl status m4bot-web.service --no-pager | grep Active

print_message "M4Bot è ora disponibile all'indirizzo: http://$DOMAIN"
print_message "Per fermare M4Bot, esegui: m4bot-stop"
EOF
    
    chmod +x /usr/local/bin/m4bot-start
    
    # m4bot-stop
    cat > /usr/local/bin/m4bot-stop << EOF
#!/bin/bash
# Script per fermare M4Bot

# Carica le funzioni comuni
source /usr/local/bin/common.sh

# Verifica che l'utente sia root
check_root

print_message "Arresto di M4Bot..."

# Ferma i servizi
systemctl stop m4bot-bot.service
systemctl stop m4bot-web.service

print_message "Stato dei servizi:"
systemctl status m4bot-bot.service --no-pager | grep Active
systemctl status m4bot-web.service --no-pager | grep Active

print_success "M4Bot fermato con successo"
EOF
    
    chmod +x /usr/local/bin/m4bot-stop
    
    # m4bot-status
    cat > /usr/local/bin/m4bot-status << EOF
#!/bin/bash
# Script per controllare lo stato di M4Bot

# Carica le funzioni comuni
source /usr/local/bin/common.sh

# Verifica che l'utente sia root
check_root

print_message "Stato di M4Bot..."

# Controlla i servizi
print_message "Stato dei servizi:"
systemctl status m4bot-bot.service --no-pager
print_message "---------------------------"
systemctl status m4bot-web.service --no-pager
print_message "---------------------------"
systemctl status postgresql --no-pager | grep Active
print_message "---------------------------"
systemctl status nginx --no-pager | grep Active

# Controlla i log
print_message "Ultimi log del bot:"
journalctl -u m4bot-bot.service --no-pager -n 10

print_message "Ultimi log del web:"
journalctl -u m4bot-web.service --no-pager -n 10

# Informazioni di sistema
print_message "Informazioni di sistema:"
df -h / | grep -v "Filesystem"
print_message "CPU e Memoria:"
ps aux | grep -E 'm4bot|python' | grep -v grep
EOF
    
    chmod +x /usr/local/bin/m4bot-status
    
    # m4bot-restart
    cat > /usr/local/bin/m4bot-restart << EOF
#!/bin/bash
# Script per riavviare M4Bot

# Carica le funzioni comuni
source /usr/local/bin/common.sh

# Verifica che l'utente sia root
check_root

print_message "Riavvio di M4Bot..."

# Riavvia i servizi
systemctl restart m4bot-bot.service
systemctl restart m4bot-web.service

print_message "Stato dei servizi:"
systemctl status m4bot-bot.service --no-pager | grep Active
systemctl status m4bot-web.service --no-pager | grep Active

print_success "M4Bot riavviato con successo"
EOF
    
    chmod +x /usr/local/bin/m4bot-restart
    
    print_success "Script di gestione creati"
}

# Correggi file mancanti e problemi
fix_common_issues() {
    print_message "Correzione di problemi comuni..."
    
    # Crea directory necessarie per la web app
    mkdir -p "$STATIC_DIR/img"
    mkdir -p "$STATIC_DIR/css"
    mkdir -p "$STATIC_DIR/js"
    
    # Crea file CSS di base se non esiste
    if [ ! -f "$STATIC_DIR/css/style.css" ]; then
        cat > "$STATIC_DIR/css/style.css" << EOF
/* M4Bot CSS principale */
:root {
    --primary-color: #2a9d8f;
    --secondary-color: #e76f51;
    --dark-color: #264653;
    --light-color: #f4f1de;
    --success-color: #2a9d8f;
    --warning-color: #e9c46a;
    --danger-color: #e76f51;
}

body {
    font-family: 'Roboto', sans-serif;
    line-height: 1.6;
    color: #333;
    background-color: #f8f9fa;
    margin: 0;
    padding: 0;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 15px;
}

.navbar {
    background-color: var(--dark-color);
    padding: 1rem 0;
}

.navbar a {
    color: white;
    text-decoration: none;
}

.btn {
    display: inline-block;
    padding: 0.5rem 1rem;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    text-decoration: none;
    font-size: 1rem;
    transition: background 0.3s ease;
}

.btn-primary {
    background-color: var(--primary-color);
    color: white;
}

.btn-secondary {
    background-color: var(--secondary-color);
    color: white;
}

.card {
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}

.alert {
    padding: 0.75rem 1.25rem;
    margin-bottom: 1rem;
    border-radius: 4px;
}

.alert-success {
    background-color: #d4edda;
    color: #155724;
}

.alert-danger {
    background-color: #f8d7da;
    color: #721c24;
}

.form-group {
    margin-bottom: 1rem;
}

.form-control {
    display: block;
    width: 100%;
    padding: 0.5rem;
    font-size: 1rem;
    border: 1px solid #ced4da;
    border-radius: 4px;
}

footer {
    background-color: var(--dark-color);
    color: white;
    padding: 1.5rem 0;
    margin-top: 2rem;
}
EOF
    fi
    
    # Crea JavaScript di base se non esiste
    if [ ! -f "$STATIC_DIR/js/main.js" ]; then
        cat > "$STATIC_DIR/js/main.js" << EOF
// M4Bot JavaScript principale
document.addEventListener('DOMContentLoaded', function() {
    // Gestione flash messages
    const flashMessages = document.querySelectorAll('.alert');
    flashMessages.forEach(message => {
        setTimeout(() => {
            message.style.opacity = '0';
            setTimeout(() => {
                message.style.display = 'none';
            }, 500);
        }, 5000);
    });
    
    // Conferma per azioni di eliminazione
    const deleteButtons = document.querySelectorAll('.btn-delete');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            if (!confirm('Sei sicuro di voler eliminare questo elemento?')) {
                e.preventDefault();
            }
        });
    });
});
EOF
    fi
    
    # Crea icone di base
    if [ ! -f "$STATIC_DIR/img/favicon.ico" ]; then
        # Scarica icona predefinita
        curl -s -o "$STATIC_DIR/img/favicon.ico" "https://raw.githubusercontent.com/M4Tronick/M4Bot/main/web/static/img/favicon.ico" || {
            # Se il download fallisce, crea un file vuoto
            touch "$STATIC_DIR/img/favicon.ico"
        }
    fi
    
    # Correggi template base.html
    if [ -f "$TEMPLATES_DIR/base.html" ]; then
        # Rimuovi la sezione "Cosa dicono di noi" e il marchio registrato
        sed -i '/Cosa dicono di noi/,/<\/section>/d' "$TEMPLATES_DIR/base.html"
        sed -i 's/M4Bot®/M4Bot/g' "$TEMPLATES_DIR/base.html"
    else
        # Crea template base.html se non esiste
        cat > "$TEMPLATES_DIR/base.html" << EOF
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}M4Bot{% endblock %}</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="shortcut icon" href="{{ url_for('static', filename='img/favicon.ico') }}">
    {% block extra_css %}{% endblock %}
</head>
<body>
    <header>
        <nav class="navbar">
            <div class="container">
                <a href="{{ url_for('index') }}" class="navbar-brand">M4Bot</a>
                <div class="navbar-menu">
                    <a href="{{ url_for('index') }}">Home</a>
                    {% if current_user.is_authenticated %}
                        <a href="{{ url_for('dashboard') }}">Dashboard</a>
                        <a href="{{ url_for('logout') }}">Logout</a>
                    {% else %}
                        <a href="{{ url_for('login') }}">Login</a>
                        <a href="{{ url_for('register') }}">Registrati</a>
                    {% endif %}
                </div>
            </div>
        </nav>
    </header>
    
    <main class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        
        {% block content %}{% endblock %}
    </main>
    
    <footer>
        <div class="container">
            <p>&copy; 2025 M4Bot - Tutti i diritti riservati</p>
        </div>
    </footer>
    
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    {% block extra_js %}{% endblock %}
</body>
</html>
EOF
    fi
    
    # Crea index.html se non esiste
    if [ ! -f "$STATIC_DIR/index.html" ]; then
        print_message "Creazione della pagina index.html statica..."
        cat > "$STATIC_DIR/index.html" << EOF
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>M4Bot - Bot per Kick.com</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <link rel="shortcut icon" href="/static/img/favicon.ico">
    <meta name="description" content="M4Bot - Il bot completo e personalizzabile per la piattaforma di streaming Kick.com">
</head>
<body>
    <header>
        <nav class="navbar">
            <div class="container">
                <a href="/" class="navbar-brand">M4Bot</a>
                <div class="navbar-menu">
                    <a href="/" class="active">Home</a>
                    <a href="/features">Funzionalità</a>
                    <a href="/login">Accedi</a>
                    <a href="/register">Registrati</a>
                </div>
            </div>
        </nav>
    </header>
    
    <main class="container">
        <div class="hero">
            <h1>Benvenuto su M4Bot</h1>
            <p>Il bot completo e personalizzabile per la piattaforma di streaming Kick.com</p>
            <div class="hero-buttons">
                <a href="/register" class="btn btn-primary">Inizia ora</a>
                <a href="/features" class="btn btn-secondary">Scopri di più</a>
            </div>
        </div>
        
        <section class="features">
            <h2>Funzionalità principali</h2>
            <div class="card-grid">
                <div class="card">
                    <h3>Comandi personalizzati</h3>
                    <p>Crea e gestisci comandi con risposte dinamiche e cooldown personalizzabili.</p>
                </div>
                <div class="card">
                    <h3>Giochi in chat</h3>
                    <p>Intrattieni il tuo pubblico con giochi come dadi, trivia e altri mini-giochi interattivi.</p>
                </div>
                <div class="card">
                    <h3>Sistema di punti</h3>
                    <p>Premia gli spettatori con un sistema di punti personalizzabile integrato con la tua chat.</p>
                </div>
            </div>
        </section>
        
        <section class="cta">
            <h2>Porta la tua stream al livello successivo</h2>
            <p>Iscriviti oggi e scopri tutte le potenzialità di M4Bot per il tuo canale Kick.com</p>
            <a href="/register" class="btn btn-primary">Registrati gratuitamente</a>
        </section>
    </main>
    
    <footer>
        <div class="container">
            <div class="footer-content">
                <div class="footer-links">
                    <a href="/">Home</a>
                    <a href="/features">Funzionalità</a>
                    <a href="/login">Accedi</a>
                    <a href="/register">Registrati</a>
                </div>
                <p>&copy; 2025 M4Bot - Tutti i diritti riservati</p>
            </div>
        </div>
    </footer>
    
    <script src="/static/js/main.js"></script>
</body>
</html>
EOF
    fi
    
    # Crea anche il template index.html per Flask se necessario
    if [ ! -f "$TEMPLATES_DIR/index.html" ]; then
        print_message "Creazione del template index.html per Flask..."
        cat > "$TEMPLATES_DIR/index.html" << EOF
{% extends 'base.html' %}

{% block title %}M4Bot - Bot per Kick.com{% endblock %}

{% block content %}
<div class="hero">
    <h1>Benvenuto su M4Bot</h1>
    <p>Il bot completo e personalizzabile per la piattaforma di streaming Kick.com</p>
    <div class="hero-buttons">
        <a href="{{ url_for('register') }}" class="btn btn-primary">Inizia ora</a>
        <a href="{{ url_for('features') if 'features' in url_for_available else '#' }}" class="btn btn-secondary">Scopri di più</a>
    </div>
</div>

<section class="features">
    <h2>Funzionalità principali</h2>
    <div class="card-grid">
        <div class="card">
            <h3>Comandi personalizzati</h3>
            <p>Crea e gestisci comandi con risposte dinamiche e cooldown personalizzabili.</p>
        </div>
        <div class="card">
            <h3>Giochi in chat</h3>
            <p>Intrattieni il tuo pubblico con giochi come dadi, trivia e altri mini-giochi interattivi.</p>
        </div>
        <div class="card">
            <h3>Sistema di punti</h3>
            <p>Premia gli spettatori con un sistema di punti personalizzabile integrato con la tua chat.</p>
        </div>
    </div>
</section>

<section class="cta">
    <h2>Porta la tua stream al livello successivo</h2>
    <p>Iscriviti oggi e scopri tutte le potenzialità di M4Bot per il tuo canale Kick.com</p>
    <a href="{{ url_for('register') }}" class="btn btn-primary">Registrati gratuitamente</a>
</section>
{% endblock %}
EOF
    fi
    
    # Aggiungi CSS migliorato per la landing page
    cat >> "$STATIC_DIR/css/style.css" << EOF

/* Stili migliorati per la landing page */
.hero {
    padding: 4rem 0;
    text-align: center;
    background-color: #f8f9fa;
    margin-bottom: 2rem;
    border-radius: 8px;
    box-shadow: 0 2px 15px rgba(0,0,0,0.05);
}

.hero h1 {
    font-size: 2.8rem;
    margin-bottom: 1rem;
    color: var(--dark-color);
}

.hero p {
    font-size: 1.3rem;
    margin-bottom: 2rem;
    color: #555;
    max-width: 800px;
    margin-left: auto;
    margin-right: auto;
}

.hero-buttons {
    display: flex;
    justify-content: center;
    gap: 1rem;
    margin-top: 2rem;
}

.btn-secondary {
    background-color: #f8f9fa;
    color: var(--dark-color);
    border: 1px solid var(--dark-color);
}

.btn-secondary:hover {
    background-color: #e9ecef;
}

.card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 1.5rem;
    margin-top: 2rem;
}

.features {
    padding: 3rem 0;
}

.features h2 {
    text-align: center;
    margin-bottom: 2rem;
    color: var(--dark-color);
    font-size: 2.2rem;
}

.card {
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.card:hover {
    transform: translateY(-5px);
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
}

.cta {
    background-color: var(--primary-color);
    color: white;
    padding: 3rem 0;
    text-align: center;
    border-radius: 8px;
    margin: 3rem 0;
}

.cta h2 {
    font-size: 2.2rem;
    margin-bottom: 1rem;
}

.cta p {
    font-size: 1.2rem;
    margin-bottom: 2rem;
    max-width: 800px;
    margin-left: auto;
    margin-right: auto;
}

.cta .btn-primary {
    background-color: white;
    color: var(--primary-color);
    font-size: 1.1rem;
    padding: 0.7rem 1.5rem;
}

.cta .btn-primary:hover {
    background-color: #f8f9fa;
}

.footer-content {
    display: flex;
    flex-direction: column;
    align-items: center;
}

.footer-links {
    display: flex;
    gap: 1rem;
    margin-bottom: 1rem;
}

.footer-links a {
    color: white;
    text-decoration: none;
}

.navbar a.active {
    font-weight: bold;
    text-decoration: underline;
}

@media (max-width: 768px) {
    .hero h1 {
        font-size: 2.2rem;
    }
    
    .hero p {
        font-size: 1.1rem;
    }
    
    .hero-buttons {
        flex-direction: column;
        align-items: center;
    }
    
    .card-grid {
        grid-template-columns: 1fr;
    }
}
EOF
    
    # Assicurati che la rotta '/' nell'app Flask rimandi a index.html o a una pagina di benvenuto
    if [ -f "$WEB_DIR/app.py" ]; then
        if ! grep -q "@app.route('/')" "$WEB_DIR/app.py"; then
            print_message "Aggiunta della rotta principale a app.py..."
            cat >> "$WEB_DIR/app.py" << EOF

@app.route('/')
def index():
    return render_template('index.html')
EOF
        fi
        
        # Crea anche il template index.html per Flask se necessario
        if [ ! -f "$TEMPLATES_DIR/index.html" ]; then
            print_message "Creazione del template index.html per Flask..."
            cat > "$TEMPLATES_DIR/index.html" << EOF
{% extends 'base.html' %}

{% block title %}M4Bot - Bot per Kick.com{% endblock %}

{% block content %}
<div class="hero">
    <h1>Benvenuto su M4Bot</h1>
    <p>Il bot completo e personalizzabile per la piattaforma di streaming Kick.com</p>
    <div class="hero-buttons">
        <a href="{{ url_for('register') }}" class="btn btn-primary">Inizia ora</a>
        <a href="{{ url_for('features') if 'features' in url_for_available else '#' }}" class="btn btn-secondary">Scopri di più</a>
    </div>
</div>

<section class="features">
    <h2>Funzionalità principali</h2>
    <div class="card-grid">
        <div class="card">
            <h3>Comandi personalizzati</h3>
            <p>Crea e gestisci comandi con risposte dinamiche e cooldown personalizzabili.</p>
        </div>
        <div class="card">
            <h3>Giochi in chat</h3>
            <p>Intrattieni il tuo pubblico con giochi come dadi, trivia e altri mini-giochi interattivi.</p>
        </div>
        <div class="card">
            <h3>Sistema di punti</h3>
            <p>Premia gli spettatori con un sistema di punti personalizzabile integrato con la tua chat.</p>
        </div>
    </div>
</section>

<section class="cta">
    <h2>Porta la tua stream al livello successivo</h2>
    <p>Iscriviti oggi e scopri tutte le potenzialità di M4Bot per il tuo canale Kick.com</p>
    <a href="{{ url_for('register') }}" class="btn btn-primary">Registrati gratuitamente</a>
</section>
{% endblock %}
EOF
        fi
    fi
    
    # Verifica app.py e correggi se necessario
    if [ -f "$WEB_DIR/app.py" ]; then
        # Assicurati che il file sia eseguibile
        chmod +x "$WEB_DIR/app.py"
        
        # Controlla se app.py contiene il caricamento di .env
        if ! grep -q "load_dotenv" "$WEB_DIR/app.py"; then
            print_message "Aggiunta del caricamento delle variabili d'ambiente in app.py..."
            
            # Inserisci l'import di dotenv all'inizio del file
            sed -i '1s/^/import os\nfrom dotenv import load_dotenv\n\n# Carica variabili d\'ambiente\nload_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))\n\n/' "$WEB_DIR/app.py"
        fi
        
        # Controlla se app.py contiene la configurazione del database e aggiungila se manca
        if ! grep -q "SQLALCHEMY_DATABASE_URI" "$WEB_DIR/app.py"; then
            print_message "Aggiunta della configurazione del database in app.py..."
            sed -i "/app = Flask/a \\
# Configurazione del database\\
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{os.getenv(\"DB_USER\")}:{os.getenv(\"DB_PASSWORD\")}@{os.getenv(\"DB_HOST\", \"localhost\")}/{os.getenv(\"DB_NAME\")}'\\
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False\\
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', '$(openssl rand -hex 24)')" "$WEB_DIR/app.py"
        fi
        
        # Aggiungi gestione errori se manca
        if ! grep -q "errorhandler" "$WEB_DIR/app.py"; then
            print_message "Aggiunta della gestione degli errori in app.py..."
            cat >> "$WEB_DIR/app.py" << EOF

# Gestione degli errori
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error='Pagina non trovata'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', error='Errore interno del server'), 500
EOF
        fi
    fi
    
    # Verifica m4bot.py e correggi se necessario
    if [ -f "$BOT_DIR/m4bot.py" ]; then
        # Assicurati che il file sia eseguibile
        chmod +x "$BOT_DIR/m4bot.py"
        
        # Controlla se m4bot.py contiene il caricamento di .env
        if ! grep -q "load_dotenv" "$BOT_DIR/m4bot.py"; then
            print_message "Aggiunta del caricamento delle variabili d'ambiente in m4bot.py..."
            
            # Inserisci l'import di dotenv all'inizio del file
            sed -i '1s/^/import os\nfrom dotenv import load_dotenv\n\n# Carica variabili d\'ambiente\nload_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))\n\n/' "$BOT_DIR/m4bot.py"
        fi
        
        # Controlla se il file di log è configurato correttamente
        if ! grep -q "logs/m4bot.log" "$BOT_DIR/m4bot.py"; then
            mkdir -p "$LOGS_DIR"
            sed -i "s|logs/m4bot.log|$LOGS_DIR/m4bot.log|g" "$BOT_DIR/m4bot.py"
        fi
    fi
    
    # Crea template error.html se non esiste
    if [ ! -f "$TEMPLATES_DIR/error.html" ]; then
        cat > "$TEMPLATES_DIR/error.html" << EOF
{% extends 'base.html' %}

{% block title %}Errore - M4Bot{% endblock %}

{% block content %}
<div class="card">
    <h1>Oops! Si è verificato un errore</h1>
    <p>{{ error }}</p>
    <a href="{{ url_for('index') }}" class="btn btn-primary">Torna alla Home</a>
</div>
{% endblock %}
EOF
    fi
    
    # Crea template features.html se non esiste
    if [ ! -f "$TEMPLATES_DIR/features.html" ]; then
        print_message "Creazione del template features.html..."
        cat > "$TEMPLATES_DIR/features.html" << EOF
{% extends 'base.html' %}

{% block title %}Funzionalità - M4Bot{% endblock %}

{% block content %}
<div class="page-header">
    <h1>Funzionalità di M4Bot</h1>
    <p>Scopri tutte le potenzialità del bot per il tuo canale Kick.com</p>
</div>

<section class="feature-section">
    <h2>Gestione Comandi</h2>
    <div class="feature-grid">
        <div class="feature-card">
            <h3>Comandi Personalizzati</h3>
            <p>Crea comandi personalizzati con risposte statiche o dinamiche che rispondano alle esigenze specifiche del tuo canale.</p>
        </div>
        <div class="feature-card">
            <h3>Timer Automatici</h3>
            <p>Imposta messaggi automatici che vengono inviati a intervalli regolari durante lo streaming.</p>
        </div>
        <div class="feature-card">
            <h3>Livelli di Permesso</h3>
            <p>Imposta diversi livelli di permesso per i comandi: tutti, abbonati, moderatori, solo streamer.</p>
        </div>
        <div class="feature-card">
            <h3>Cooldown Intelligenti</h3>
            <p>Configura i tempi di riutilizzo (cooldown) per ogni comando per evitare spam in chat.</p>
        </div>
    </div>
</section>

<section class="feature-section">
    <h2>Giochi e Interazione</h2>
    <div class="feature-grid">
        <div class="feature-card">
            <h3>Mini-giochi Interattivi</h3>
            <p>Dadi, trivia, indovinelli e altri giochi che coinvolgono gli spettatori durante lo streaming.</p>
        </div>
        <div class="feature-card">
            <h3>Sondaggi e Votazioni</h3>
            <p>Crea sondaggi interattivi per far votare il tuo pubblico su diverse opzioni.</p>
        </div>
        <div class="feature-card">
            <h3>Sistema di Punti</h3>
            <p>Gli spettatori accumulano punti per il tempo di visione, donazioni e partecipazione, che possono essere usati per premi.</p>
        </div>
        <div class="feature-card">
            <h3>Classifiche</h3>
            <p>Tieni traccia dei migliori spettatori per punti, messaggi, tempo di visione e altro.</p>
        </div>
    </div>
</section>

<section class="feature-section">
    <h2>Moderazione e Gestione</h2>
    <div class="feature-grid">
        <div class="feature-card">
            <h3>Filtro Parole</h3>
            <p>Filtra automaticamente parole e frasi indesiderate dalla chat del tuo canale.</p>
        </div>
        <div class="feature-card">
            <h3>Anti-Spam</h3>
            <p>Proteggi la tua chat da messaggi ripetuti e spam con la moderazione automatica.</p>
        </div>
        <div class="feature-card">
            <h3>Notifiche Integrate</h3>
            <p>Ricevi notifiche per eventi importanti sul canale direttamente sul tuo Discord.</p>
        </div>
        <div class="feature-card">
            <h3>Dashboard Web</h3>
            <p>Gestisci facilmente tutte le impostazioni del bot da un'interfaccia web intuitiva.</p>
        </div>
    </div>
</section>

<section class="cta">
    <h2>Pronto a migliorare il tuo canale?</h2>
    <p>Iscriviti ora e inizia a utilizzare M4Bot per portare la tua stream al livello successivo!</p>
    <a href="{{ url_for('register') }}" class="btn btn-primary">Registrati Gratuitamente</a>
</section>
{% endblock %}
EOF
    fi
    
    # Aggiungi CSS per features.html
    cat >> "$STATIC_DIR/css/style.css" << EOF

/* Stili per la pagina features */
.page-header {
    text-align: center;
    padding: 3rem 0;
    margin-bottom: 2rem;
    background-color: var(--dark-color);
    color: white;
    border-radius: 8px;
}

.page-header h1 {
    font-size: 2.5rem;
    margin-bottom: 1rem;
}

.page-header p {
    font-size: 1.2rem;
    max-width: 800px;
    margin: 0 auto;
}

.feature-section {
    margin-bottom: 4rem;
}

.feature-section h2 {
    font-size: 1.8rem;
    margin-bottom: 2rem;
    text-align: center;
    color: var(--dark-color);
}

.feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
}

.feature-card {
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.1);
    padding: 1.5rem;
    transition: transform 0.3s ease, box-shadow 0.3s ease;
}

.feature-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
}

.feature-card h3 {
    font-size: 1.3rem;
    margin-bottom: 1rem;
    color: var(--primary-color);
}

.feature-card p {
    font-size: 1rem;
    color: #555;
    line-height: 1.6;
}

@media (max-width: 768px) {
    .feature-grid {
        grid-template-columns: 1fr;
    }
    
    .page-header h1 {
        font-size: 2rem;
    }
}
EOF

    # Aggiungi la rotta per features in app.py se non esiste
    if [ -f "$WEB_DIR/app.py" ]; then
        if ! grep -q "@app.route('/features')" "$WEB_DIR/app.py"; then
            print_message "Aggiunta della rotta per features in app.py..."
            cat >> "$WEB_DIR/app.py" << EOF

@app.route('/features')
def features():
    return render_template('features.html')
EOF
        fi
    fi

# Imposta i permessi corretti
    chown -R m4bot:m4bot "$M4BOT_DIR"
    chmod -R 755 "$M4BOT_DIR"
    
    print_success "Problemi comuni corretti"
}

# Esecuzione
update_system
install_dependencies
setup_directories
create_user
clone_repository
setup_virtualenv
setup_database
initialize_database
setup_nginx
setup_ssl
setup_services
create_management_scripts
fix_common_issues

# Avvio dei servizi
print_message "Avvio dei servizi M4Bot..."
systemctl start postgresql
systemctl start nginx
systemctl start m4bot-bot.service
systemctl start m4bot-web.service

# Verifica finale
print_message "Verifica dello stato dei servizi..."
systemctl status postgresql --no-pager | grep Active
systemctl status nginx --no-pager | grep Active
systemctl status m4bot-bot.service --no-pager | grep Active
systemctl status m4bot-web.service --no-pager | grep Active

# Riassunto finale
print_success "==============================================="
print_success "   INSTALLAZIONE DI M4BOT COMPLETATA!          "
print_success "==============================================="
print_message "M4Bot è ora disponibile all'indirizzo: http://$DOMAIN"
print_message ""
print_message "Credenziali database:"
print_message "  Database: $DB_NAME"
print_message "  Utente:   $DB_USER"
print_message "  Password: $DB_PASSWORD"
print_message ""
print_message "Credenziali di accesso all'applicazione web:"
print_message "  Username: $ADMIN_USER"
print_message "  Password: $ADMIN_PASSWORD"
print_message ""
print_message "Comandi disponibili:"
print_message "  m4bot-start:   Avvia i servizi di M4Bot"
print_message "  m4bot-stop:    Ferma i servizi di M4Bot"
print_message "  m4bot-status:  Verifica lo stato dei servizi"
print_message "  m4bot-restart: Riavvia i servizi di M4Bot"
print_message ""
print_message "Le credenziali sono state salvate nel file: $M4BOT_DIR/.env"
