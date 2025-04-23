#!/bin/bash
# Script unificato di installazione e gestione per M4Bot
# Questo script integra tutte le funzionalità separate in un unico file

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Verifica che il sistema sia Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    echo -e "${RED}Errore: Questo script è progettato per essere eseguito su Linux.${NC}"
    exit 1
fi

# Directory e configurazioni
INSTALL_DIR="/opt/m4bot"
DB_NAME="m4bot_db"
DB_USER="m4bot_user"
DB_PASS=$(openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 16)
WEB_PORT="5000"
BOT_PORT="5001"
SCRIPT_VERSION="3.1.0"
LOG_DIR="$INSTALL_DIR/logs"
BACKUP_DIR="$INSTALL_DIR/backups"
DOMAIN="m4bot.it"
ADMIN_EMAIL=""
USE_SSL=true
SETUP_USER=true

# Funzioni di utilità comuni
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

show_progress() {
    local message="$1"
    local duration=${2:-2}
    local chars="⣾⣽⣻⢿⡿⣟⣯⣷"
    local delay=0.1
    local end_time=$((SECONDS + duration))

    tput sc
    while ((SECONDS < end_time)); do
        for (( i=0; i<${#chars}; i++ )); do
            tput rc
            echo -en "${BLUE}[${chars:$i:1}]${NC} $message"
            sleep $delay
        done
    done
    tput rc
    echo -e "${BLUE}[✓]${NC} $message"
}

prompt_user() {
    local message="$1"
    local default_value="$2"
    local result

    read -p "$message [$default_value]: " result
    result=${result:-$default_value}
    echo "$result"
}

prompt_yes_no() {
    local message="$1"
    local default_value="${2:-S}"
    local result

    if [[ "$default_value" == "S" || "$default_value" == "s" ]]; then
    read -p "$message [S/n]: " result
        result=${result:-"S"}
    else
        read -p "$message [s/N]: " result
        result=${result:-"N"}
    fi
    
    if [[ "$result" == "S" || "$result" == "s" ]]; then
        return 0
    else
        return 1
    fi
}

generate_random_password() {
    openssl rand -base64 16 | tr -dc 'a-zA-Z0-9' | head -c 16
}

generate_encryption_key() {
    openssl rand -base64 32
}

generate_secret_key() {
    openssl rand -hex 32
}

# Banner all'avvio
show_banner() {
    clear
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════════════╗"
    echo "║                                               ║"
    echo "║           M4Bot - Installazione               ║"
    echo "║           Versione: $SCRIPT_VERSION                   ║"
    echo "║                                               ║"
    echo "╚═══════════════════════════════════════════════╝"
    echo -e "${NC}"
    echo
}

# Funzione per raccogliere le informazioni di configurazione
gather_config_info() {
    print_message "Raccolta informazioni di configurazione..."
    
    INSTALL_DIR=$(prompt_user "Directory di installazione" "$INSTALL_DIR")
    DB_NAME=$(prompt_user "Nome del database" "$DB_NAME")
    DB_USER=$(prompt_user "Utente database" "$DB_USER")
    DB_PASS=$(prompt_user "Password database (lascia vuoto per generare)" "")
    if [ -z "$DB_PASS" ]; then
        DB_PASS=$(generate_random_password)
        print_message "Password database generata: $DB_PASS"
    fi
    
    WEB_PORT=$(prompt_user "Porta per l'interfaccia web" "$WEB_PORT")
    BOT_PORT=$(prompt_user "Porta per l'API del bot" "$BOT_PORT")
    DOMAIN=$(prompt_user "Dominio per il bot (senza http/https)" "$DOMAIN")
    
    if prompt_yes_no "Configurare SSL con Let's Encrypt?"; then
        USE_SSL=true
        ADMIN_EMAIL=$(prompt_user "Email per certificati Let's Encrypt" "$ADMIN_EMAIL")
    else
        USE_SSL=false
    fi
    
    if prompt_yes_no "Creare un utente dedicato per M4Bot?"; then
        SETUP_USER=true
    else
        SETUP_USER=false
    fi
    
    # Salva le configurazioni per riferimento
    echo "INSTALL_DIR=$INSTALL_DIR" > /tmp/m4bot_config.tmp
    echo "DB_NAME=$DB_NAME" >> /tmp/m4bot_config.tmp
    echo "DB_USER=$DB_USER" >> /tmp/m4bot_config.tmp
    echo "DB_PASS=$DB_PASS" >> /tmp/m4bot_config.tmp
    echo "WEB_PORT=$WEB_PORT" >> /tmp/m4bot_config.tmp
    echo "BOT_PORT=$BOT_PORT" >> /tmp/m4bot_config.tmp
    echo "DOMAIN=$DOMAIN" >> /tmp/m4bot_config.tmp
    echo "USE_SSL=$USE_SSL" >> /tmp/m4bot_config.tmp
    echo "ADMIN_EMAIL=$ADMIN_EMAIL" >> /tmp/m4bot_config.tmp
    echo "SETUP_USER=$SETUP_USER" >> /tmp/m4bot_config.tmp
    
    print_success "Informazioni di configurazione raccolte con successo"
}

# Funzione per verificare i prerequisiti
check_prerequisites() {
    print_message "Verifica dei prerequisiti..."
    
    # Verifica che sia Linux
    if [[ "$OSTYPE" != "linux-gnu"* ]]; then
        print_error "Questo script è progettato per essere eseguito su Linux." 1
    fi

    # Verifica che sia eseguito come root
    check_root

    # Verifica che i comandi necessari siano installati
    local cmds=("apt-get" "curl" "wget" "openssl")
    local missing_cmds=()

    for cmd in "${cmds[@]}"; do
        if ! command -v "$cmd" &>/dev/null; then
            missing_cmds+=("$cmd")
        fi
    done

    if [ ${#missing_cmds[@]} -gt 0 ]; then
        print_warning "I seguenti comandi necessari non sono installati: ${missing_cmds[*]}"
        print_message "Installazione dei comandi mancanti..."
        apt-get update || print_error "Impossibile aggiornare i pacchetti" 1
        apt-get install -y curl wget openssl || print_error "Impossibile installare i pacchetti richiesti" 1
    fi
    
    print_success "Prerequisiti verificati con successo"
}

# Funzione per controllare i servizi
check_services() {
    print_message "Controllo dei servizi..."
    
    # Controlla PostgreSQL
    if ! systemctl is-active --quiet postgresql; then
        print_warning "PostgreSQL non è in esecuzione, tentativo di avvio..."
        systemctl start postgresql
        if [ $? -eq 0 ]; then
            print_success "PostgreSQL avviato con successo"
        else
            print_error "Impossibile avviare PostgreSQL" 1
        fi
    else
        print_success "PostgreSQL è in esecuzione"
    fi
    
    # Controlla Nginx
    if ! systemctl is-active --quiet nginx; then
        print_warning "Nginx non è in esecuzione, tentativo di avvio..."
        systemctl start nginx
        if [ $? -eq 0 ]; then
            print_success "Nginx avviato con successo"
        else
            print_error "Impossibile avviare Nginx" 1
        fi
    else
        print_success "Nginx è in esecuzione"
    fi
    
    # Controlla Redis
    if ! systemctl is-active --quiet redis-server; then
        print_warning "Redis non è in esecuzione, tentativo di avvio..."
        systemctl start redis-server
        if [ $? -eq 0 ]; then
            print_success "Redis avviato con successo"
        else
            print_error "Impossibile avviare Redis" 1
        fi
    else
        print_success "Redis è in esecuzione"
    fi
    
    # Controlla i servizi M4Bot
    print_message "Stato dei servizi M4Bot:"
    systemctl status postgresql --no-pager | grep Active
    systemctl status nginx --no-pager | grep Active
    systemctl status redis-server --no-pager | grep Active
    
    systemctl status m4bot-bot.service --no-pager | grep Active 2>/dev/null || echo "m4bot-bot.service non installato"
    systemctl status m4bot-web.service --no-pager | grep Active 2>/dev/null || echo "m4bot-web.service non installato"
    systemctl status m4bot-monitor.service --no-pager | grep Active 2>/dev/null || echo "m4bot-monitor.service non installato"
}

# Funzione per installare le dipendenze di sistema
install_dependencies() {
    print_message "Installazione delle dipendenze di sistema..."
    apt-get update || print_error "Impossibile aggiornare i pacchetti" 1
    
    # Installa pacchetti essenziali
    apt-get install -y python3 python3-pip python3-venv python3-dev \
        postgresql postgresql-contrib \
        nginx certbot python3-certbot-nginx \
        git python3-bcrypt redis-server \
        dos2unix unzip curl wget \
        build-essential libpq-dev \
        libssl-dev libffi-dev \
        supervisor || print_error "Impossibile installare i pacchetti richiesti" 1
    
    # Abilita i servizi
    systemctl enable postgresql
    systemctl enable nginx
    systemctl enable redis-server
    systemctl enable supervisor
    
    # Avvia i servizi
    systemctl start postgresql
    systemctl start nginx
    systemctl start redis-server
    systemctl start supervisor
    
    # Crea le directory per la configurazione del monitoraggio integrato
    print_message "Configurazione del sistema di monitoraggio integrato..."
    
    mkdir -p "$INSTALL_DIR/config/schemas"
    
    # Crea il file di configurazione del monitoraggio
    cat > "$INSTALL_DIR/config/monitoring.json" << EOF
{
  "system_metrics_interval": 60,
  "app_metrics_interval": 30,
  "service_check_interval": 120,
  "config_check_interval": 300,
  "data_dir": "$INSTALL_DIR/monitoring_data",
  "log_level": "INFO",
  "enable_prometheus": true,
  "prometheus_port": 9090,
  "enable_export": true,
  "export_interval": 300,
  "history_days": 7,
  "thresholds": {
    "cpu_warning": 75,
    "cpu_critical": 90,
    "memory_warning": 80,
    "memory_critical": 95,
    "disk_warning": 85,
    "disk_critical": 95
  },
  "services": {
    "web": {
      "type": "systemd",
      "unit": "m4bot-web.service",
      "check_url": "http://localhost:$WEB_PORT/health",
      "expected_status": 200
    },
    "bot": {
      "type": "systemd",
      "unit": "m4bot-bot.service"
    },
    "database": {
      "type": "systemd",
      "unit": "postgresql.service"
    },
    "redis": {
      "type": "systemd",
      "unit": "redis.service"
    },
    "nginx": {
      "type": "systemd",
      "unit": "nginx.service"
    }
  },
  "config_directories": ["$INSTALL_DIR/config"],
  "alerts": {
    "email": {
      "enabled": false,
      "smtp_server": "smtp.example.com",
      "smtp_port": 587,
      "username": "alerts@example.com",
      "password": "",
      "sender": "alerts@example.com",
      "recipients": ["admin@example.com"]
    },
    "telegram": {
      "enabled": false,
      "bot_token": "",
      "chat_id": ""
    },
    "discord": {
      "enabled": false,
      "webhook_url": ""
    }
  }
}
EOF

    # Crea uno schema di esempio per il validatore di configurazioni
    cat > "$INSTALL_DIR/config/schemas/monitoring.json" << EOF
{
  "type": "object",
  "required": ["system_metrics_interval", "thresholds"],
  "properties": {
    "system_metrics_interval": {
      "type": "integer",
      "minimum": 10,
      "maximum": 3600
    },
    "app_metrics_interval": {
      "type": "integer",
      "minimum": 10,
      "maximum": 3600
    },
    "service_check_interval": {
      "type": "integer",
      "minimum": 10,
      "maximum": 3600
    },
    "thresholds": {
      "type": "object",
      "properties": {
        "cpu_warning": {
          "type": "integer",
          "minimum": 50,
          "maximum": 95
        },
        "cpu_critical": {
          "type": "integer",
          "minimum": 80,
          "maximum": 100
        }
      }
    }
  }
}
EOF

    # Crea directory per dati di monitoraggio
    mkdir -p "$INSTALL_DIR/monitoring_data"
    mkdir -p "$INSTALL_DIR/logs/monitoring"
    
    # Imposta permessi
    if [ "$SETUP_USER" = "true" ]; then
        chown -R m4bot:m4bot "$INSTALL_DIR/config"
        chown -R m4bot:m4bot "$INSTALL_DIR/monitoring_data"
        chown -R m4bot:m4bot "$INSTALL_DIR/logs/monitoring"
    fi
    
    chmod 755 "$INSTALL_DIR/config"
    chmod 755 "$INSTALL_DIR/monitoring_data"
    chmod 755 "$INSTALL_DIR/logs/monitoring"
    
    print_success "Sistema di monitoraggio integrato configurato con successo"
    print_success "Dipendenze installate con successo"
}

# Funzione per configurare l'utente
setup_user() {
    if [ "$SETUP_USER" != "true" ]; then
        print_message "Creazione utente dedicato saltata su richiesta"
        return 0
    fi
    
    print_message "Configurazione dell'utente dedicato..."
    
    # Crea l'utente m4bot se non esiste
    if ! id -u m4bot &>/dev/null; then
        useradd -m -s /bin/bash m4bot || print_error "Impossibile creare l'utente m4bot" 1
        
        # Genera una password casuale
        local user_password=$(generate_random_password)
        echo "m4bot:$user_password" | chpasswd
        
        print_message "Utente m4bot creato con password: $user_password"
        echo "USER_PASSWORD=$user_password" >> /tmp/m4bot_config.tmp
    else
        print_warning "L'utente m4bot già esiste"
    fi
    
    print_success "Utente configurato con successo"
}

# Funzione per configurare PostgreSQL
setup_postgres() {
    print_message "Configurazione di PostgreSQL..."
    
    # Verifica se PostgreSQL è in esecuzione
    if ! systemctl is-active --quiet postgresql; then
        print_warning "PostgreSQL non è in esecuzione, tentativo di avvio..."
        systemctl start postgresql
        if [ $? -ne 0 ]; then
            print_error "Impossibile avviare PostgreSQL" 1
        fi
    fi
    
    # Crea l'utente del database se non esiste
    if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
        print_message "Creazione dell'utente $DB_USER per PostgreSQL..."
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';" || print_error "Impossibile creare l'utente del database" 1
    else
        print_warning "L'utente $DB_USER già esiste"
    fi
    
    # Crea il database se non esiste
    if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
        print_message "Creazione del database $DB_NAME..."
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;" || print_error "Impossibile creare il database" 1
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" || print_error "Impossibile assegnare i privilegi" 1
    else
        print_warning "Il database $DB_NAME già esiste"
    fi
    
    # Configura l'autenticazione
    PG_VERSION=$(sudo -u postgres psql -c "SHOW server_version;" | head -n 3 | tail -n 1 | awk '{print $1}' | cut -d. -f1)
        PG_HBA=$(find /etc/postgresql -name "pg_hba.conf" | head -n 1)
    
    if [ -f "$PG_HBA" ]; then
        print_message "Configurazione dell'autenticazione PostgreSQL in $PG_HBA..."
        if ! grep -q "$DB_USER" "$PG_HBA"; then
            echo "local   $DB_NAME    $DB_USER    md5" >> "$PG_HBA"
        fi
        systemctl restart postgresql
    fi
    
    print_success "PostgreSQL configurato con successo"
}

# Funzione per inizializzare il database
init_database() {
    print_message "Inizializzazione del database..."
    
    # Verifica se il database esiste
    if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
        print_error "Il database $DB_NAME non esiste. Eseguire prima setup_postgres." 1
    fi
    
    # Creazione schema di base
    cat > /tmp/m4bot_schema.sql << EOF
-- Schema base per M4Bot
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    kick_id VARCHAR(255) UNIQUE,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255),
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS channels (
    id SERIAL PRIMARY KEY,
    kick_channel_id VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    owner_id INTEGER REFERENCES users(id),
    access_token TEXT,
    refresh_token TEXT,
    token_expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    key VARCHAR(255) NOT NULL,
    value TEXT,
    UNIQUE(channel_id, key)
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(channel_id, name)
);

CREATE TABLE IF NOT EXISTS channel_points (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    user_id INTEGER REFERENCES users(id),
    points INTEGER DEFAULT 0,
    watch_time INTEGER DEFAULT 0,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(channel_id, user_id)
);

CREATE TABLE IF NOT EXISTS event_logs (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    event_type VARCHAR(255) NOT NULL,
    user_id INTEGER REFERENCES users(id),
    data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_roles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    channel_id INTEGER REFERENCES channels(id),
    role VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, channel_id)
);

-- Inserisci impostazioni predefinite
INSERT INTO settings (key, value, channel_id) 
VALUES ('bot_name', 'M4Bot', NULL) 
ON CONFLICT DO NOTHING;

INSERT INTO settings (key, value, channel_id) 
VALUES ('web_url', 'https://$DOMAIN', NULL) 
ON CONFLICT DO NOTHING;
EOF

    # Esegui lo schema
    print_message "Creazione delle tabelle di base..."
    PGPASSWORD="$DB_PASS" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -f /tmp/m4bot_schema.sql || print_error "Impossibile creare lo schema del database" 1
    
    # Rimuovi il file temporaneo
    rm /tmp/m4bot_schema.sql
    
    print_success "Database inizializzato con successo"
}

# Funzione per preparare le directory
prepare_directories() {
    print_message "Preparazione delle directory di installazione..."
    
    # Crea la directory di installazione
    if [ ! -d "$INSTALL_DIR" ]; then
        mkdir -p "$INSTALL_DIR" || print_error "Impossibile creare la directory di installazione" 1
    fi
    
    # Crea le sottodirectory necessarie
    mkdir -p "$INSTALL_DIR/logs"
    mkdir -p "$INSTALL_DIR/backups"
    mkdir -p "$INSTALL_DIR/web/static"
    mkdir -p "$INSTALL_DIR/web/templates"
    mkdir -p "$INSTALL_DIR/web/media"
    mkdir -p "$INSTALL_DIR/security"
    mkdir -p "$INSTALL_DIR/bot"
    mkdir -p "$INSTALL_DIR/scripts"
    mkdir -p "$INSTALL_DIR/config"
    
    # Configura i permessi
    if [ "$SETUP_USER" = "true" ]; then
        chown -R m4bot:m4bot "$INSTALL_DIR"
        chmod -R 755 "$INSTALL_DIR"
    else
        chmod -R 755 "$INSTALL_DIR"
    fi
    
    print_success "Directory preparate con successo"
}

# Funzione per copiare i file del progetto
copy_project_files() {
    print_message "Copia dei file del progetto..."
    
    # Determina la directory corrente (quella da cui viene eseguito lo script)
    local CURRENT_DIR=$(pwd)
    
    # Verifica se stiamo già nella directory del progetto
    if [ -d "$CURRENT_DIR/bot" ] && [ -d "$CURRENT_DIR/web" ]; then
        print_message "Copia dei file dalla directory corrente..."
        
        # Copia i file principali
        cp -r "$CURRENT_DIR/bot"/* "$INSTALL_DIR/bot/" || print_error "Impossibile copiare i file del bot" 1
        cp -r "$CURRENT_DIR/web"/* "$INSTALL_DIR/web/" 2>/dev/null || print_warning "Impossibile copiare alcuni file web"
        cp -r "$CURRENT_DIR/security"/* "$INSTALL_DIR/security/" 2>/dev/null || print_warning "Impossibile copiare alcuni file di sicurezza"
        cp -r "$CURRENT_DIR/scripts"/* "$INSTALL_DIR/scripts/" 2>/dev/null || print_warning "Impossibile copiare alcuni script"
        
        # Copia README e altri file utili
        cp "$CURRENT_DIR/README.md" "$INSTALL_DIR/" 2>/dev/null || print_warning "README.md non trovato"
        cp "$CURRENT_DIR/requirements.txt" "$INSTALL_DIR/" 2>/dev/null || print_warning "requirements.txt non trovato"
    else
        print_error "Questa non sembra essere la directory del progetto M4Bot. Eseguire lo script dalla directory principale del progetto." 1
    fi
    
    print_success "File del progetto copiati con successo"
}

# Funzione per correggere i permessi dei file
fix_permissions() {
    print_message "Correzione dei permessi dei file..."
    
    # Imposta permessi eseguibili per gli script
    find "$INSTALL_DIR" -name "*.sh" -exec chmod +x {} \;
    find "$INSTALL_DIR" -name "*.py" -exec chmod +x {} \;
    
    # Imposta permessi corretti per le directory
    chmod -R 755 "$INSTALL_DIR/scripts"
    chmod -R 750 "$INSTALL_DIR/security"
    chmod -R 755 "$INSTALL_DIR/web/static"
    chmod -R 755 "$INSTALL_DIR/web/media"
    
    # Imposta proprietario corretto
    if [ "$SETUP_USER" = "true" ]; then
        chown -R m4bot:m4bot "$INSTALL_DIR"
    fi
    
    print_success "Permessi dei file corretti con successo"
}

# Funzione per correggere i file (fine riga, encoding, ecc.)
fix_files() {
    print_message "Correzione dei file del progetto..."
    
    # Installa dos2unix se non è già installato
    if ! command -v dos2unix &>/dev/null; then
        apt-get install -y dos2unix || print_error "Impossibile installare dos2unix" 1
    fi
    
    # Correggi i fine riga di tutti i file di testo
    find "$INSTALL_DIR" -type f -name "*.py" -o -name "*.sh" -o -name "*.conf" -o -name "*.txt" -o -name "*.md" | while read file; do
        dos2unix "$file" 2>/dev/null
    done
    
    # Correggi i file Python che potrebbero avere problemi
    find "$INSTALL_DIR" -name "*.py" | while read file; do
        # Rimuovi gli spazi bianchi alla fine delle righe
        sed -i 's/[ \t]*$//' "$file"
        
        # Aggiungi la riga shebang se manca
        if ! grep -q "^#!" "$file"; then
            sed -i '1i#!/usr/bin/env python3' "$file"
        fi
    done
    
    # Correggi i file di shell che potrebbero avere problemi
    find "$INSTALL_DIR" -name "*.sh" | while read file; do
        # Rimuovi gli spazi bianchi alla fine delle righe
        sed -i 's/[ \t]*$//' "$file"
        
        # Aggiungi la riga shebang se manca
        if ! grep -q "^#!" "$file"; then
            sed -i '1i#!/bin/bash' "$file"
        fi
    done
    
    print_success "File del progetto corretti con successo"
}

# Funzione per creare l'ambiente virtuale e installare le dipendenze Python
setup_python_env() {
    print_message "Configurazione dell'ambiente Python..."
    
    # Verifica se python3-venv è installato
    if ! command -v python3 -m venv &>/dev/null; then
        apt-get install -y python3-venv || print_error "Impossibile installare python3-venv" 1
    fi
    
    # Crea l'ambiente virtuale
    python3 -m venv "$INSTALL_DIR/venv" || print_error "Impossibile creare l'ambiente virtuale" 1
    
    # Aggiorna pip e setuptools
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip setuptools wheel || print_error "Impossibile aggiornare pip e setuptools" 1
    
    # Installa le dipendenze
    if [ -f "$INSTALL_DIR/requirements.txt" ]; then
        print_message "Installazione delle dipendenze da requirements.txt..."
        "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" || print_error "Impossibile installare le dipendenze" 1
    else
        print_warning "File requirements.txt non trovato. Installazione delle dipendenze di base..."
        
        # Installa le dipendenze minime
        "$INSTALL_DIR/venv/bin/pip" install quart quart-cors aiohttp asyncpg bcrypt cryptography \
            httpx isort black redis pyjwt passlib argon2-cffi python-dotenv ujson uvicorn \
            flask flask-babel || print_error "Impossibile installare le dipendenze di base" 1
    fi
    
    print_success "Ambiente Python configurato con successo"
}

# Funzione per creare il file .env
create_env_file() {
    print_message "Creazione del file .env..."
    
    # Genera chiavi sicure
    local ENCRYPTION_KEY=$(generate_encryption_key)
    local SECRET_KEY=$(generate_secret_key)
    
    # Crea il file .env
    cat > "$INSTALL_DIR/.env" << EOF
# Configurazione di M4Bot
# Generato automaticamente dallo script di installazione

# Credenziali OAuth per Kick.com
CLIENT_ID=01JR9DNAJYARH2466KBR8N2AW2
CLIENT_SECRET=4379baaef9eb1f1ba571372734cf9627a0f36680fd6f877895cb1d3f17065e4f
REDIRECT_URI=https://$DOMAIN/auth/callback
SCOPE=user:read channel:read channel:write chat:write events:subscribe

# Configurazione del server web
WEB_HOST=0.0.0.0
WEB_PORT=$WEB_PORT
WEB_DOMAIN=$DOMAIN
EOF

    # Aggiungi configurazione SSL se abilitata
    if [ "$USE_SSL" = "true" ]; then
        cat >> "$INSTALL_DIR/.env" << EOF
SSL_CERT=/etc/letsencrypt/live/$DOMAIN/fullchain.pem
SSL_KEY=/etc/letsencrypt/live/$DOMAIN/privkey.pem
EOF
    fi

    # Continua con il resto della configurazione
    cat >> "$INSTALL_DIR/.env" << EOF

# Configurazione del database
DB_HOST=localhost
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASS

# Configurazione della VPS
VPS_IP=$(hostname -I | awk '{print $1}')

# Impostazioni di log
LOG_LEVEL=INFO
LOG_FILE=logs/m4bot.log

# Integrazione OBS
OBS_WEBSOCKET_URL=ws://localhost:4455
OBS_WEBSOCKET_PASSWORD=

# Chiave per la crittografia dei dati sensibili
ENCRYPTION_KEY=$ENCRYPTION_KEY

# Chiave segreta per sessioni web e token
SECRET_KEY=$SECRET_KEY

# Configurazione della sicurezza
ALLOW_REGISTRATION=true
MAX_LOGIN_ATTEMPTS=5
LOGIN_TIMEOUT=300
SESSION_LIFETIME=604800
REQUIRE_HTTPS=true
CORS_ALLOWED_ORIGINS=*
EOF

    # Imposta permessi corretti
    chmod 640 "$INSTALL_DIR/.env"
    
    if [ "$SETUP_USER" = "true" ]; then
        chown m4bot:m4bot "$INSTALL_DIR/.env"
    fi
    
    print_success "File .env creato con successo"
}

# Funzione per configurare Nginx
setup_nginx() {
    print_message "Configurazione di Nginx..."
    
    # Verifica se Nginx è installato
    if ! command -v nginx &>/dev/null; then
        print_error "Nginx non è installato. Installarlo prima di continuare." 1
    fi
    
    # Crea il file di configurazione
    cat > /etc/nginx/sites-available/m4bot << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$WEB_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:$BOT_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static/ {
        alias $INSTALL_DIR/web/static/;
    }

    location /media/ {
        alias $INSTALL_DIR/web/media/;
    }
}
EOF

    # Abilita il sito
    if [ ! -L /etc/nginx/sites-enabled/m4bot ]; then
        ln -s /etc/nginx/sites-available/m4bot /etc/nginx/sites-enabled/ || print_error "Impossibile abilitare il sito Nginx" 1
    fi
    
    # Rimuovi il sito predefinito
    if [ -L /etc/nginx/sites-enabled/default ]; then
        rm /etc/nginx/sites-enabled/default
    fi
    
    # Testa la configurazione e riavvia
    nginx -t || print_error "Configurazione Nginx non valida" 1
    systemctl restart nginx || print_error "Impossibile riavviare Nginx" 1
    
    print_success "Nginx configurato con successo"
}

# Funzione per configurare SSL con Let's Encrypt
setup_ssl() {
    if [ "$USE_SSL" != "true" ]; then
        print_message "Configurazione SSL saltata su richiesta"
        return 0
    fi
    
    print_message "Configurazione SSL con Let's Encrypt..."
    
    # Verifica se certbot è installato
    if ! command -v certbot &>/dev/null; then
        print_warning "Certbot non è installato, installazione in corso..."
        apt-get update
        apt-get install -y certbot python3-certbot-nginx || print_error "Impossibile installare certbot" 1
    fi
    
    # Configura il certificato
    if [ -n "$ADMIN_EMAIL" ]; then
        certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos --email "$ADMIN_EMAIL" || print_error "Impossibile configurare SSL" 1
    else
        certbot --nginx -d "$DOMAIN" -d "www.$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email || print_error "Impossibile configurare SSL" 1
    fi
    
    # Verifica se il certificato è stato creato correttamente
    if [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
        print_success "Certificato SSL generato con successo"
        
        # Configura il rinnovo automatico
        systemctl enable certbot.timer
        systemctl start certbot.timer
        
        print_success "Rinnovo automatico del certificato configurato"
    else
        print_warning "Impossibile verificare la presenza del certificato SSL, potrebbe essere necessario eseguire la configurazione manualmente"
    fi
}

# Funzione per configurare i servizi systemd
setup_services() {
    print_message "Configurazione dei servizi systemd..."
    
    # Crea il servizio per il bot
    cat > /etc/systemd/system/m4bot-bot.service << EOF
[Unit]
Description=M4Bot Service
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/bot/m4bot.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
Environment=M4BOT_DIR=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

    # Crea il servizio per il web
    cat > /etc/systemd/system/m4bot-web.service << EOF
[Unit]
Description=M4Bot Web Interface
After=network.target postgresql.service redis-server.service m4bot-bot.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$INSTALL_DIR/web
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/web/app.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
Environment=M4BOT_DIR=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

    # Crea il servizio per il sistema di monitoraggio integrato
    cat > /etc/systemd/system/m4bot-monitor.service << EOF
[Unit]
Description=M4Bot Integrated Monitoring System
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/stability/monitoring/integrated_monitor.py --config $INSTALL_DIR/config/monitoring.json
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
Environment=M4BOT_DIR=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

    # Ricarica systemd
    systemctl daemon-reload || print_error "Impossibile ricaricare systemd" 1
    
    # Abilita i servizi
    systemctl enable m4bot-bot.service || print_error "Impossibile abilitare il servizio bot" 1
    systemctl enable m4bot-web.service || print_error "Impossibile abilitare il servizio web" 1
    systemctl enable m4bot-monitor.service || print_error "Impossibile abilitare il servizio monitor" 1
    
    print_success "Servizi systemd configurati con successo"
}

# Funzione per avviare i servizi
start_services() {
    print_message "Avvio dei servizi M4Bot..."
    
    # Verifica che la directory dei log esista
    if [ ! -d "$LOG_DIR" ]; then
        print_warning "La directory dei log non esiste, creazione in corso..."
        mkdir -p "$LOG_DIR"
        if [ "$SETUP_USER" = "true" ]; then
            chown m4bot:m4bot "$LOG_DIR"
        fi
        chmod 755 "$LOG_DIR"
        print_success "Directory dei log creata"
    fi
    
    # Verifica che PostgreSQL e Nginx siano in esecuzione
    check_services
    
    # Avvia i servizi
    if systemctl is-active --quiet m4bot-bot.service; then
        print_warning "Il servizio bot è già in esecuzione"
    else
        systemctl start m4bot-bot.service
        if [ $? -eq 0 ]; then
            print_success "Bot avviato con successo"
        else
            print_error "Impossibile avviare il bot" 1
        fi
    fi
    
    if systemctl is-active --quiet m4bot-web.service; then
        print_warning "Il servizio web è già in esecuzione"
    else
        systemctl start m4bot-web.service
        if [ $? -eq 0 ]; then
            print_success "Web app avviata con successo"
        else
            print_error "Impossibile avviare la web app" 1
        fi
    fi
    
    if systemctl is-active --quiet m4bot-monitor.service; then
        print_warning "Il servizio di monitoraggio è già in esecuzione"
    else
        systemctl start m4bot-monitor.service
        if [ $? -eq 0 ]; then
            print_success "Sistema di monitoraggio avviato con successo"
        else
            print_error "Impossibile avviare il sistema di monitoraggio" 1
        fi
    fi
    
    print_message "Stato dei servizi:"
    systemctl status m4bot-bot.service --no-pager | grep Active
    systemctl status m4bot-web.service --no-pager | grep Active
    systemctl status m4bot-monitor.service --no-pager | grep Active
    systemctl status nginx --no-pager | grep Active
    systemctl status postgresql --no-pager | grep Active
    
    print_message "M4Bot è ora disponibile all'indirizzo" 
    if [ "$USE_SSL" = "true" ]; then
        echo -e "${GREEN}https://$DOMAIN${NC}"
    else
        echo -e "${GREEN}http://$DOMAIN${NC}"
    fi
}

# Funzione per riassumere le informazioni di installazione
show_installation_summary() {
    print_message "Riepilogo dell'installazione M4Bot"
    echo
    echo -e "${CYAN}=== INFORMAZIONI GENERALI ===${NC}"
    echo -e "Directory di installazione: ${GREEN}$INSTALL_DIR${NC}"
    echo -e "Dominio: ${GREEN}$DOMAIN${NC}"
    echo -e "Protocollo: ${GREEN}$([ "$USE_SSL" = "true" ] && echo "HTTPS (SSL)" || echo "HTTP")${NC}"
    echo
    echo -e "${CYAN}=== INFORMAZIONI DATABASE ===${NC}"
    echo -e "Nome database: ${GREEN}$DB_NAME${NC}"
    echo -e "Utente database: ${GREEN}$DB_USER${NC}"
    echo -e "Password database: ${GREEN}$DB_PASS${NC}"
    echo
    echo -e "${CYAN}=== PORTE ===${NC}"
    echo -e "Porta web: ${GREEN}$WEB_PORT${NC}"
    echo -e "Porta API: ${GREEN}$BOT_PORT${NC}"
    echo -e "Porta Prometheus (monitoraggio): ${GREEN}9090${NC}"
    echo
    echo -e "${CYAN}=== SERVIZI ===${NC}"
    echo -e "Web: ${GREEN}m4bot-web.service${NC}"
    echo -e "Bot: ${GREEN}m4bot-bot.service${NC}"
    echo -e "Monitoraggio integrato: ${GREEN}m4bot-monitor.service${NC}"
    echo
    echo -e "${CYAN}=== FILE DI CONFIGURAZIONE ===${NC}"
    echo -e "File .env: ${GREEN}$INSTALL_DIR/.env${NC}"
    echo -e "Configurazione monitoraggio: ${GREEN}$INSTALL_DIR/config/monitoring.json${NC}"
    echo
    echo -e "${CYAN}=== URLs IMPORTANTI ===${NC}"
    if [ "$USE_SSL" = "true" ]; then
        echo -e "Interfaccia web: ${GREEN}https://$DOMAIN${NC}"
        echo -e "API bot: ${GREEN}https://$DOMAIN/api${NC}"
        echo -e "Metriche Prometheus: ${GREEN}https://$DOMAIN:9090/metrics${NC}"
    else
        echo -e "Interfaccia web: ${GREEN}http://$DOMAIN${NC}"
        echo -e "API bot: ${GREEN}http://$DOMAIN/api${NC}"
        echo -e "Metriche Prometheus: ${GREEN}http://$DOMAIN:9090/metrics${NC}"
    fi
    echo
    echo -e "${YELLOW}IMPORTANTE: Salva queste informazioni in un luogo sicuro!${NC}"
    echo
    
    # Salva le informazioni in un file
    cat > "$INSTALL_DIR/installation_info.txt" << EOF
=== INFORMAZIONI DI INSTALLAZIONE M4BOT ===
Data installazione: $(date)

=== INFORMAZIONI GENERALI ===
Directory di installazione: $INSTALL_DIR
Dominio: $DOMAIN
Protocollo: $([ "$USE_SSL" = "true" ] && echo "HTTPS (SSL)" || echo "HTTP")

=== INFORMAZIONI DATABASE ===
Nome database: $DB_NAME
Utente database: $DB_USER
Password database: $DB_PASS

=== PORTE ===
Porta web: $WEB_PORT
Porta API: $BOT_PORT
Porta Prometheus (monitoraggio): 9090

=== SERVIZI ===
Web: m4bot-web.service
Bot: m4bot-bot.service
Monitoraggio integrato: m4bot-monitor.service

=== FILE DI CONFIGURAZIONE ===
File .env: $INSTALL_DIR/.env
Configurazione monitoraggio: $INSTALL_DIR/config/monitoring.json

=== URLs IMPORTANTI ===
Interfaccia web: $([ "$USE_SSL" = "true" ] && echo "https://$DOMAIN" || echo "http://$DOMAIN")
API bot: $([ "$USE_SSL" = "true" ] && echo "https://$DOMAIN/api" || echo "http://$DOMAIN/api")
Metriche Prometheus: $([ "$USE_SSL" = "true" ] && echo "https://$DOMAIN:9090/metrics" || echo "http://$DOMAIN:9090/metrics")

IMPORTANTE: Salva queste informazioni in un luogo sicuro!
EOF

    # Imposta permessi corretti sul file di informazioni
    chmod 600 "$INSTALL_DIR/installation_info.txt"
    if [ "$SETUP_USER" = "true" ]; then
        chown m4bot:m4bot "$INSTALL_DIR/installation_info.txt"
    fi
}

# Funzione per la pulizia finale
cleanup() {
    print_message "Pulizia finale..."
    
    # Rimuovi file temporanei
    if [ -f "/tmp/m4bot_config.tmp" ]; then
        rm /tmp/m4bot_config.tmp
    fi
    
    # Rimuovi file di cache Python
    find "$INSTALL_DIR" -type d -name "__pycache__" -exec rm -rf {} +
    find "$INSTALL_DIR" -type f -name "*.pyc" -delete
    find "$INSTALL_DIR" -type f -name "*.pyo" -delete
    
    print_success "Pulizia completata"
}

# Funzione principale di installazione
install_m4bot() {
    show_banner
    
    # Verifica prerequisiti
    check_prerequisites
    
    # Raccoglie informazioni di configurazione
    gather_config_info
    
    # Installa dipendenze
    install_dependencies
    
    # Configura utente
    setup_user
    
    # Prepara directory
    prepare_directories
    
    # Copia file del progetto
    copy_project_files
    
    # Correggi permessi
    fix_permissions
    
    # Correggi file
    fix_files
    
    # Configura ambiente Python
    setup_python_env
    
    # Crea file .env
    create_env_file
    
    # Configura PostgreSQL
    setup_postgres
    
    # Inizializza database
    init_database
    
    # Configura Nginx
    setup_nginx
    
    # Configura SSL
    setup_ssl
    
    # Configura servizi
    setup_services
    
    # Avvia servizi
    start_services
    
    # Pulizia finale
    cleanup
    
    # Mostra riepilogo installazione
    show_installation_summary
    
    print_success "Installazione di M4Bot completata con successo!"
}

# Funzione per fermare i servizi
stop_services() {
    print_message "Arresto dei servizi M4Bot..."
    
    if systemctl is-active --quiet m4bot-web.service; then
        systemctl stop m4bot-web.service
        if [ $? -eq 0 ]; then
            print_success "Web app fermata con successo"
        else
            print_error "Impossibile fermare la web app" 1
        fi
    else
        print_warning "Il servizio web non è in esecuzione"
    fi
    
    if systemctl is-active --quiet m4bot-bot.service; then
        systemctl stop m4bot-bot.service
        if [ $? -eq 0 ]; then
            print_success "Bot fermato con successo"
        else
            print_error "Impossibile fermare il bot" 1
        fi
    else
        print_warning "Il servizio bot non è in esecuzione"
    fi
    
    print_message "Tutti i servizi M4Bot sono stati arrestati"
}

# Funzione per riavviare i servizi
restart_services() {
    print_message "Riavvio dei servizi M4Bot..."
    
    stop_services
    sleep 2
    start_services
    
    print_message "Tutti i servizi M4Bot sono stati riavviati"
}

# Gestione degli argomenti
    if [ $# -eq 0 ]; then
    install_m4bot
elif [ "$1" = "start" ]; then
    start_services
elif [ "$1" = "stop" ]; then
    stop_services
elif [ "$1" = "restart" ]; then
    restart_services
elif [ "$1" = "status" ]; then
    check_services
elif [ "$1" = "help" ]; then
                echo "Utilizzo: $0 [comando]"
    echo
                echo "Comandi disponibili:"
    echo "  (nessuno)   Esegue l'installazione completa"
    echo "  start       Avvia i servizi"
    echo "  stop        Ferma i servizi"
    echo "  restart     Riavvia i servizi"
    echo "  status      Mostra lo stato dei servizi"
else
    echo "Comando non riconosciuto: $1"
    echo "Utilizzo: $0 [comando]"
    echo "Eseguire $0 help per maggiori informazioni"
                exit 1
    fi