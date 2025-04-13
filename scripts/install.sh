#!/bin/bash
# Script di installazione per M4Bot
# Questo script installa e configura tutte le dipendenze necessarie per M4Bot

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzione per stampare messaggi
print_message() {
    echo -e "${BLUE}[M4Bot]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERRORE]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESSO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[ATTENZIONE]${NC} $1"
}

# Controllo se l'utente è root
if [ "$(id -u)" != "0" ]; then
   print_error "Questo script deve essere eseguito come root" 
   exit 1
fi

# Verifica se è una VPS Hetzner
HETZNER_IP="78.47.146.95"
MY_IP=$(hostname -I | awk '{print $1}')

if [ "$MY_IP" != "$HETZNER_IP" ]; then
    print_warning "L'indirizzo IP ($MY_IP) non corrisponde all'IP Hetzner atteso ($HETZNER_IP)"
    read -p "Vuoi continuare comunque? (s/n): " choice
    if [ "$choice" != "s" ]; then
        print_message "Installazione annullata"
        exit 0
    fi
fi

# Directory di installazione
INSTALL_DIR="/opt/m4bot"
WEB_DIR="${INSTALL_DIR}/web"
BOT_DIR="${INSTALL_DIR}/bot"
LOGS_DIR="${INSTALL_DIR}/logs"
DB_DIR="${INSTALL_DIR}/database"
SCRIPTS_DIR="${INSTALL_DIR}/scripts"

# Aggiorna il sistema
print_message "Aggiornamento del sistema..."
apt-get update && apt-get upgrade -y

# Installa le dipendenze di sistema
print_message "Installazione delle dipendenze di sistema..."
apt-get install -y python3 python3-pip python3-venv postgresql nginx certbot python3-certbot-nginx git python3-bcrypt

# Crea l'utente m4bot
print_message "Creazione dell'utente m4bot..."
if id "m4bot" &>/dev/null; then
    print_warning "L'utente m4bot esiste già"
else
    useradd -m -s /bin/bash m4bot
    print_success "Utente m4bot creato"
fi

# Crea le directory necessarie
print_message "Creazione delle directory di installazione..."
mkdir -p $INSTALL_DIR $WEB_DIR $BOT_DIR $LOGS_DIR $DB_DIR $SCRIPTS_DIR

# Crea il file di funzioni comuni
print_message "Creazione del file di funzioni comuni..."
cat > $SCRIPTS_DIR/common.sh << EOF
#!/bin/bash
# Script con funzioni comuni per la gestione di M4Bot

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

chmod +x $SCRIPTS_DIR/common.sh
print_success "File common.sh creato"

# Creiamo lo script setup_postgres.sh
print_message "Creazione dello script di configurazione PostgreSQL..."
cat > $SCRIPTS_DIR/setup_postgres.sh << EOF
#!/bin/bash
# Script per configurare il database PostgreSQL per M4Bot

# Carica le funzioni comuni
source "\$(dirname "\$0")/common.sh"

# Verifica che l'utente sia root
check_root

print_message "Configurazione del database PostgreSQL..."

# Verifica che PostgreSQL sia in esecuzione
check_postgres

# Parametri del database
DB_NAME="m4bot_db"
DB_USER="m4bot_user"
DB_PASSWORD="m4bot_password"

# Creiamo l'utente e il database PostgreSQL
print_message "Creazione dell'utente database \$DB_USER..."
su - postgres -c "psql -c \"CREATE USER \$DB_USER WITH PASSWORD '\$DB_PASSWORD';\"" || true

print_message "Creazione del database \$DB_NAME..."
su - postgres -c "psql -c \"CREATE DATABASE \$DB_NAME OWNER \$DB_USER;\"" || true

print_message "Configurazione dei privilegi..."
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE \$DB_NAME TO \$DB_USER;\"" || true

print_success "Database configurato con successo!"
print_message "Nome database: \$DB_NAME"
print_message "Utente database: \$DB_USER"
EOF

chmod +x $SCRIPTS_DIR/setup_postgres.sh
print_success "Script setup_postgres.sh creato"

# Clona o copia i file sorgente
print_message "Copiando i file sorgente..."

# È possibile usare git clone o copiare i file dalla directory corrente
# Per questo esempio, copiamo i file dalla directory corrente
# Assumendo che lo script sia nella directory principale del progetto

# Copia i file del bot se esistono
if [ -d "../bot" ]; then
    cp -r ../bot/* $BOT_DIR/ 2>/dev/null || print_warning "Nessun file trovato in ../bot/"
else
    print_warning "Directory ../bot/ non trovata"
fi

# Copia i file web se esistono
if [ -d "../web" ]; then
    cp -r ../web/* $WEB_DIR/ 2>/dev/null || print_warning "Nessun file trovato in ../web/"
else
    print_warning "Directory ../web/ non trovata"
fi

# Crea la struttura della directory del database
print_message "Creazione della struttura del database..."
mkdir -p $DB_DIR/migrations

# La directory database potrebbe non esistere, quindi controlliamo prima
if [ -d "../database" ]; then
    cp -r ../database/* $DB_DIR/ 2>/dev/null || print_warning "Nessun file trovato in ../database/"
else
    print_warning "Directory ../database/ non trovata, verrà creata una struttura vuota"
    
    # Crea un file README nel database
    cat > $DB_DIR/README.md << EOF
# Database M4Bot

Questa directory contiene i file di database e le migrazioni per M4Bot.
Creata automaticamente dallo script di installazione.
EOF
fi

# Copia gli script se esistono
if [ -d "../scripts" ]; then
    cp -r ../scripts/* $SCRIPTS_DIR/ 2>/dev/null || print_warning "Nessun file trovato in ../scripts/"
else
    cp -r ./* $SCRIPTS_DIR/ 2>/dev/null || print_warning "Impossibile copiare gli script"
fi

# Crea un ambiente virtuale Python
print_message "Creazione dell'ambiente virtuale Python..."
python3 -m venv $INSTALL_DIR/venv
source $INSTALL_DIR/venv/bin/activate

# Installa le dipendenze Python
print_message "Installazione delle dipendenze Python..."
pip install --upgrade pip
pip install aiohttp asyncpg websockets requests cryptography bcrypt quart quart-cors

# Configurazione del database PostgreSQL
print_message "Configurazione del database PostgreSQL..."
# Utilizziamo lo script dedicato per configurare PostgreSQL
$SCRIPTS_DIR/setup_postgres.sh

print_success "Database configurato"

# Inizializzazione del database
print_message "Inizializzazione del database e creazione delle tabelle..."
# Eseguiamo lo script di inizializzazione con valori predefiniti
DB_NAME="m4bot_db"
DB_USER="m4bot_user"
DB_PASSWORD="m4bot_password"
ADMIN_USER="admin"
ADMIN_EMAIL="admin@m4bot.it"
ADMIN_PASSWORD="admin123"

# Utilizziamo lo script init_database.sh ma senza richiesta di input
cat > $SCRIPTS_DIR/init_db_auto.sh << EOF
#!/bin/bash
source \$(dirname "\$0")/common.sh
check_root
print_message "Inizializzazione automatica del database M4Bot..."

# Parametri fissi
DB_NAME="$DB_NAME"
DB_USER="$DB_USER"
DB_PASSWORD="$DB_PASSWORD"
ADMIN_USER="$ADMIN_USER"
ADMIN_EMAIL="$ADMIN_EMAIL"
ADMIN_PASSWORD="$ADMIN_PASSWORD"

# Creazione tabelle
print_message "Creazione delle tabelle principali..."
cat > /tmp/init_m4bot_tables.sql << EOSQL
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
EOSQL

su - postgres -c "psql -d $DB_NAME -f /tmp/init_m4bot_tables.sql"
if [ \$? -ne 0 ]; then
    print_error "Errore nella creazione delle tabelle" 1
fi

# Pulizia
rm -f /tmp/init_m4bot_tables.sql

# Crea l'amministratore
print_message "Creazione dell'utente amministratore predefinito..."
# Genera hash della password
PASS_HASH=\$(python3 -c "import bcrypt; print(bcrypt.hashpw('$ADMIN_PASSWORD'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'))")

# Inserisci l'utente admin
su - postgres -c "psql -d $DB_NAME -c \"INSERT INTO users (username, email, password_hash, is_admin) VALUES ('$ADMIN_USER', '$ADMIN_EMAIL', '\$PASS_HASH', TRUE) ON CONFLICT (username) DO NOTHING;\""

print_success "Database inizializzato con successo!"
print_message "Utente admin: $ADMIN_USER"
print_message "Email admin: $ADMIN_EMAIL"
EOF

chmod +x $SCRIPTS_DIR/init_db_auto.sh
$SCRIPTS_DIR/init_db_auto.sh

print_success "Database inizializzato"

# Configurazione di Nginx
print_message "Configurazione di Nginx..."
cat > /etc/nginx/sites-available/m4bot.conf << EOF
server {
    listen 80;
    server_name m4bot.it www.m4bot.it;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

# Abilita il sito
ln -sf /etc/nginx/sites-available/m4bot.conf /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Riavvia Nginx
systemctl restart nginx

# Ottieni certificato SSL con Certbot
print_message "Configurazione SSL con Certbot..."
certbot --nginx -d m4bot.it -d www.m4bot.it --non-interactive --agree-tos --email info@m4bot.it

# Crea il servizio systemd per il bot
print_message "Creazione del servizio systemd per il bot..."
cat > /etc/systemd/system/m4bot-bot.service << EOF
[Unit]
Description=M4Bot Bot Service
After=network.target postgresql.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=${BOT_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python m4bot.py
Restart=on-failure
Environment="PATH=${INSTALL_DIR}/venv/bin"

[Install]
WantedBy=multi-user.target
EOF

# Crea il servizio systemd per l'applicazione web
print_message "Creazione del servizio systemd per l'applicazione web..."
cat > /etc/systemd/system/m4bot-web.service << EOF
[Unit]
Description=M4Bot Web Service
After=network.target postgresql.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=${WEB_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python app.py
Restart=on-failure
Environment="PATH=${INSTALL_DIR}/venv/bin"

[Install]
WantedBy=multi-user.target
EOF

# Ricarica systemd
systemctl daemon-reload

# Imposta i permessi corretti
print_message "Impostazione dei permessi..."
chown -R m4bot:m4bot $INSTALL_DIR
chmod +x $BOT_DIR/m4bot.py
chmod +x $WEB_DIR/app.py
chmod +x $SCRIPTS_DIR/*.sh

# Crea un link simbolico per i comandi di M4Bot
ln -sf $SCRIPTS_DIR/start.sh /usr/local/bin/m4bot-start
ln -sf $SCRIPTS_DIR/stop.sh /usr/local/bin/m4bot-stop
ln -sf $SCRIPTS_DIR/status.sh /usr/local/bin/m4bot-status

# Avvio automatico dei servizi
print_message "Configurazione dell'avvio automatico dei servizi..."
systemctl enable m4bot-bot.service
systemctl enable m4bot-web.service

# Avvio dei servizi
print_message "Avvio dei servizi M4Bot..."
systemctl start postgresql
systemctl start nginx
systemctl start m4bot-bot.service
systemctl start m4bot-web.service

# Verifica dello stato dei servizi
print_message "Verifica dello stato dei servizi..."
systemctl status postgresql --no-pager | grep Active
systemctl status nginx --no-pager | grep Active
systemctl status m4bot-bot.service --no-pager | grep Active
systemctl status m4bot-web.service --no-pager | grep Active

print_success "Installazione completata con successo!"
print_message "M4Bot è ora attivo e funzionante!"
print_message "Puoi accedere all'interfaccia web all'indirizzo: https://m4bot.it"
print_message "Credenziali di accesso:"
print_message "  Username: $ADMIN_USER"
print_message "  Password: $ADMIN_PASSWORD"
print_message ""
print_message "Per gestire M4Bot, usa i seguenti comandi:"
print_message "  - m4bot-start:   Avvia i servizi"
print_message "  - m4bot-stop:    Ferma i servizi"
print_message "  - m4bot-status:  Controlla lo stato dei servizi"
