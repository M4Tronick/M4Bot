#!/bin/bash
# Script di installazione avanzato per M4Bot
# Questo script installa e configura tutte le dipendenze necessarie per M4Bot
# Versione: 2.0

set -e

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
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

print_step() {
    echo -e "${CYAN}[PASSO]${NC} $1"
}

print_info() {
    echo -e "${PURPLE}[INFO]${NC} $1"
}

# Banner di benvenuto
show_banner() {
    clear
    echo -e "${BLUE}"
    echo "  __  __ _  _  ____   __  ____"
    echo " |  \/  | || || __ ) / / |___ \\"
    echo " | |\/| | || ||  _ \/ /    __) |"
    echo " | |  | |__   _| |_/ /    / __/"
    echo " |_|  |_|  |_||____/_/    |_____|"
    echo -e "${NC}"
    echo -e "${BLUE}Installazione di M4Bot - v2.0${NC}"
    echo -e "${CYAN}=======================================${NC}"
    echo ""
}

# Funzione per verificare i prerequisiti
check_prerequisites() {
    print_step "Verifica dei prerequisiti di sistema..."
    
    # Controllo se l'utente è root
    if [ "$(id -u)" != "0" ]; then
       print_error "Questo script deve essere eseguito come root"
       exit 1
    fi
    
    # Controllo della distribuzione Linux
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$NAME
        VER=$VERSION_ID
        print_info "Sistema operativo rilevato: $OS $VER"
        
        case $OS in
            *"Ubuntu"*|*"Debian"*)
                print_success "Sistema operativo supportato"
                ;;
            *"CentOS"*|*"RHEL"*|*"Fedora"*)
                print_warning "Sistema operativo parzialmente supportato. Potrebbero essere necessarie modifiche manuali."
                read -p "Continuare? (s/n): " choice
                if [ "$choice" != "s" ]; then
                    print_message "Installazione annullata"
                    exit 0
                fi
                ;;
            *)
                print_warning "Sistema operativo non testato. L'installazione potrebbe fallire."
                read -p "Continuare a tuo rischio? (s/n): " choice
                if [ "$choice" != "s" ]; then
                    print_message "Installazione annullata"
                    exit 0
                fi
                ;;
        esac
    else
        print_warning "Impossibile determinare il sistema operativo"
        read -p "Continuare comunque? (s/n): " choice
        if [ "$choice" != "s" ]; then
            print_message "Installazione annullata"
            exit 0
        fi
    fi
    
    # Verifica la connessione a internet
    print_info "Verifica della connessione a internet..."
    if ! ping -c 1 google.com &> /dev/null; then
        print_error "Nessuna connessione a internet. Assicurati di essere connesso."
        exit 1
    fi
    print_success "Connessione a internet verificata"
}

# Verifica se è una VPS Hetzner
check_hetzner() {
    print_step "Verifica dell'ambiente di installazione..."
    
    HETZNER_IP="78.47.146.95"
    MY_IP=$(hostname -I | awk '{print $1}')

    if [ "$MY_IP" != "$HETZNER_IP" ]; then
        print_warning "L'indirizzo IP ($MY_IP) non corrisponde all'IP Hetzner atteso ($HETZNER_IP)"
        print_info "Puoi continuare l'installazione se stai installando su un altro server."
        read -p "Vuoi continuare comunque? (s/n): " choice
        if [ "$choice" != "s" ]; then
            print_message "Installazione annullata"
            exit 0
        fi
    else
        print_success "Installazione su server Hetzner confermata"
    fi
}

# Genera una password casuale sicura
generate_secure_password() {
    # Genera una password casuale di 20 caratteri
    PASSWORD=$(tr -dc 'A-Za-z0-9!#$%&()*+,-./:;<=>?@[\]^_`{|}~' </dev/urandom | head -c 20)
    echo "$PASSWORD"
}

# Aggiorna ed effettua backup del database
setup_database() {
    print_step "Configurazione del database PostgreSQL..."
    
    # Verifica l'installazione di PostgreSQL
    if ! command -v psql &> /dev/null; then
        print_error "PostgreSQL non è installato. Installalo con: apt-get install postgresql"
        exit 1
    fi
    
    DB_USER="m4bot_user"
    DB_NAME="m4bot_db"
    DB_PASSWORD=$(generate_secure_password)
    
    # Salva la password in un file sicuro
    echo "DATABASE_USER=\"$DB_USER\"" > $INSTALL_DIR/db_credentials.conf
    echo "DATABASE_NAME=\"$DB_NAME\"" >> $INSTALL_DIR/db_credentials.conf
    echo "DATABASE_PASSWORD=\"$DB_PASSWORD\"" >> $INSTALL_DIR/db_credentials.conf
    chmod 600 $INSTALL_DIR/db_credentials.conf
    
    # Creiamo l'utente e il database PostgreSQL
    if su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'\"" | grep -q 1; then
        print_warning "L'utente $DB_USER esiste già nel database"
        read -p "Vuoi ricreare l'utente con una nuova password? (s/n): " recreate_user
        if [ "$recreate_user" = "s" ]; then
            su - postgres -c "psql -c \"ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';\""
            print_success "Password dell'utente $DB_USER aggiornata"
        fi
    else
        su - postgres -c "psql -c \"CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';\""
        print_success "Utente $DB_USER creato"
    fi
    
    if su - postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='$DB_NAME'\"" | grep -q 1; then
        print_warning "Il database $DB_NAME esiste già"
        print_info "Creazione di un backup prima di eventuali modifiche..."
        
        BACKUP_FILE="/tmp/m4bot_db_backup_$(date +%Y%m%d_%H%M%S).sql"
        su - postgres -c "pg_dump $DB_NAME > $BACKUP_FILE"
        print_success "Backup del database creato in $BACKUP_FILE"
        
        read -p "Vuoi eliminare e ricreare il database? (s/n): " recreate_db
        if [ "$recreate_db" = "s" ]; then
            su - postgres -c "psql -c \"DROP DATABASE $DB_NAME;\""
            su - postgres -c "psql -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER;\""
            print_success "Database $DB_NAME ricreato"
        fi
    else
        su - postgres -c "psql -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER;\""
        print_success "Database $DB_NAME creato"
    fi
    
    # Assicuriamoci che l'utente abbia i permessi corretti
    su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;\""
    print_success "Configurazione del database completata"
    
    # Aggiorna il file di configurazione con i dati del database
    sed -i "s/DB_USER = .*/DB_USER = \"$DB_USER\"/" $BOT_DIR/config.py
    sed -i "s/DB_PASSWORD = .*/DB_PASSWORD = \"$DB_PASSWORD\"/" $BOT_DIR/config.py
    sed -i "s/DB_NAME = .*/DB_NAME = \"$DB_NAME\"/" $BOT_DIR/config.py
    
    print_info "Le credenziali del database sono state salvate in $INSTALL_DIR/db_credentials.conf"
}

# Installa e configura il firewall
setup_firewall() {
    print_step "Configurazione del firewall..."
    
    if ! command -v ufw &> /dev/null; then
        print_info "UFW non installato. Installazione in corso..."
        apt-get install -y ufw
    fi
    
    # Configura il firewall
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow http
    ufw allow https
    
    # Apri la porta per il WebSocket se necessario
    ufw allow 8765/tcp
    
    # Abilita il firewall senza richiesta di conferma
    echo "y" | ufw enable
    
    print_success "Firewall configurato"
}

# Main installation function
install_m4bot() {
    show_banner
    check_prerequisites
    check_hetzner
    
    # Directory di installazione
    INSTALL_DIR="/opt/m4bot"
    WEB_DIR="${INSTALL_DIR}/web"
    BOT_DIR="${INSTALL_DIR}/bot"
    LOGS_DIR="${INSTALL_DIR}/logs"
    DB_DIR="${INSTALL_DIR}/database"
    SCRIPTS_DIR="${INSTALL_DIR}/scripts"
    BACKUP_DIR="${INSTALL_DIR}/backup"

    # Crea una directory di backup per salvare configurazioni precedenti
    mkdir -p $BACKUP_DIR

    # Chiedi conferma prima di procedere
    echo
    print_info "L'installazione configurerà M4Bot nelle seguenti directory:"
    echo "- Directory principale: $INSTALL_DIR"
    echo "- Directory web: $WEB_DIR"
    echo "- Directory bot: $BOT_DIR"
    echo "- Directory logs: $LOGS_DIR"
    echo "- Directory database: $DB_DIR"
    echo "- Directory script: $SCRIPTS_DIR"
    echo
    read -p "Vuoi procedere con l'installazione? (s/n): " confirm_install
    if [ "$confirm_install" != "s" ]; then
        print_message "Installazione annullata"
        exit 0
    fi
    
    # Backup di un'installazione esistente se presente
    if [ -d "$INSTALL_DIR" ]; then
        print_warning "Rilevata installazione esistente di M4Bot"
        read -p "Vuoi effettuare un backup prima di continuare? (s/n): " backup_choice
        if [ "$backup_choice" = "s" ]; then
            TIMESTAMP=$(date +%Y%m%d_%H%M%S)
            BACKUP_NAME="m4bot_backup_$TIMESTAMP"
            print_info "Creazione backup in $BACKUP_DIR/$BACKUP_NAME"
            mkdir -p "$BACKUP_DIR/$BACKUP_NAME"
            
            # Copia solo le directory/file esistenti
            [ -d "$WEB_DIR" ] && cp -r "$WEB_DIR" "$BACKUP_DIR/$BACKUP_NAME/"
            [ -d "$BOT_DIR" ] && cp -r "$BOT_DIR" "$BACKUP_DIR/$BACKUP_NAME/"
            [ -d "$DB_DIR" ] && cp -r "$DB_DIR" "$BACKUP_DIR/$BACKUP_NAME/"
            
            print_success "Backup completato in $BACKUP_DIR/$BACKUP_NAME"
        fi
    fi

    # Aggiorna il sistema
    print_step "Aggiornamento del sistema..."
    apt-get update && apt-get upgrade -y

    # Installa le dipendenze di sistema
    print_step "Installazione delle dipendenze di sistema..."
    apt-get install -y python3 python3-pip python3-venv postgresql postgresql-contrib nginx \
                     certbot python3-certbot-nginx git curl wget ufw fail2ban htop

    # Crea l'utente m4bot
    print_step "Creazione dell'utente m4bot..."
    if id "m4bot" &>/dev/null; then
        print_warning "L'utente m4bot esiste già"
    else
        useradd -m -s /bin/bash m4bot
        print_success "Utente m4bot creato"
    fi

    # Crea le directory necessarie
    print_step "Creazione delle directory di installazione..."
    mkdir -p $INSTALL_DIR $WEB_DIR $BOT_DIR $LOGS_DIR $DB_DIR $SCRIPTS_DIR

    # Clona o copia i file sorgente
    print_step "Copiando i file sorgente..."
    # Determina se lo script è nella directory del progetto
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
    
    if [ -d "$PROJECT_ROOT/bot" ] && [ -d "$PROJECT_ROOT/web" ]; then
        print_info "Rilevata struttura di progetto valida, copio i file locali"
        cp -r "$PROJECT_ROOT/bot/"* $BOT_DIR/
        cp -r "$PROJECT_ROOT/web/"* $WEB_DIR/
        [ -d "$PROJECT_ROOT/database" ] && cp -r "$PROJECT_ROOT/database/"* $DB_DIR/
        cp -r "$PROJECT_ROOT/scripts/"* $SCRIPTS_DIR/
    else
        print_warning "Non trovo i file sorgente nella directory corrente"
        read -p "Vuoi clonare il repository da GitHub? (s/n): " clone_choice
        if [ "$clone_choice" = "s" ]; then
            GIT_REPO="https://github.com/username/m4bot.git"
            read -p "Inserisci l'URL del repository git [$GIT_REPO]: " input_repo
            GIT_REPO=${input_repo:-$GIT_REPO}
            
            print_info "Clonazione del repository da $GIT_REPO"
            git clone $GIT_REPO /tmp/m4bot
            
            cp -r /tmp/m4bot/bot/* $BOT_DIR/
            cp -r /tmp/m4bot/web/* $WEB_DIR/
            [ -d "/tmp/m4bot/database" ] && cp -r /tmp/m4bot/database/* $DB_DIR/
            cp -r /tmp/m4bot/scripts/* $SCRIPTS_DIR/
            
            rm -rf /tmp/m4bot
        else
            print_error "Non posso continuare senza i file sorgente"
            exit 1
        fi
    fi

    # Verifica i file copiati
    if [ ! -f "$BOT_DIR/m4bot.py" ] || [ ! -f "$WEB_DIR/app.py" ]; then
        print_error "File sorgente essenziali non trovati"
        exit 1
    fi
    
    print_success "File sorgente copiati con successo"

    # Crea un ambiente virtuale Python
    print_step "Creazione dell'ambiente virtuale Python..."
    python3 -m venv $INSTALL_DIR/venv
    source $INSTALL_DIR/venv/bin/activate

    # Installa le dipendenze Python
    print_step "Installazione delle dipendenze Python..."
    pip install --upgrade pip
    
    # Verifica se esiste un requirements.txt
    if [ -f "$BOT_DIR/requirements.txt" ]; then
        print_info "Installazione delle dipendenze da requirements.txt"
        pip install -r $BOT_DIR/requirements.txt
    else
        print_info "Installazione delle dipendenze predefinite"
        pip install aiohttp asyncpg websockets requests cryptography bcrypt quart quart-cors pillow python-dotenv redis
    fi
    
    # Configurazione del database
    setup_database

    # Configurazione di Nginx
    print_step "Configurazione di Nginx..."
    
    # Configurazione del server web
    cat > /etc/nginx/sites-available/m4bot.conf << EOF
server {
    listen 80;
    server_name m4bot.it www.m4bot.it;
    
    # Logging
    access_log /var/log/nginx/m4bot_access.log;
    error_log /var/log/nginx/m4bot_error.log;

    # Configurazione per WebSocket
    location /ws {
        proxy_pass http://127.0.0.1:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 86400;
    }
    
    # Configurazione per l'app web
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Configurazione per i file statici
    location /static {
        alias $WEB_DIR/static;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000";
    }
}
EOF

    # Abilita il sito
    ln -sf /etc/nginx/sites-available/m4bot.conf /etc/nginx/sites-enabled/
    
    # Rimuovi il default se esiste
    if [ -f /etc/nginx/sites-enabled/default ]; then
        rm -f /etc/nginx/sites-enabled/default
    fi

    # Verifica la configurazione di Nginx
    nginx -t || {
        print_error "Configurazione di Nginx non valida. Controlla il file /etc/nginx/sites-available/m4bot.conf"
        exit 1
    }
    
    # Riavvia Nginx
    systemctl restart nginx
    print_success "Nginx configurato correttamente"

    # Configurazione SSL con Certbot
    print_step "Configurazione SSL con Certbot..."
    read -p "Vuoi configurare SSL con Certbot? Assicurati che il dominio sia già configurato per questo server. (s/n): " ssl_choice
    if [ "$ssl_choice" = "s" ]; then
        read -p "Inserisci il dominio principale: " primary_domain
        read -p "Inserisci un indirizzo email per le notifiche di Let's Encrypt: " admin_email
        
        certbot --nginx -d $primary_domain -d www.$primary_domain --non-interactive --agree-tos --email $admin_email
        print_success "Certificato SSL configurato"
    else
        print_info "Configurazione SSL saltata. Puoi configurarla manualmente in seguito."
    fi

    # Crea il servizio systemd per il bot
    print_step "Creazione del servizio systemd per il bot..."
    cat > /etc/systemd/system/m4bot-bot.service << EOF
[Unit]
Description=M4Bot Bot Service
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=${BOT_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 m4bot.py
Restart=on-failure
RestartSec=10
StandardOutput=append:${LOGS_DIR}/bot.log
StandardError=append:${LOGS_DIR}/bot-error.log
Environment="PATH=${INSTALL_DIR}/venv/bin"
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

    # Crea il servizio systemd per l'applicazione web
    print_step "Creazione del servizio systemd per l'applicazione web..."
    cat > /etc/systemd/system/m4bot-web.service << EOF
[Unit]
Description=M4Bot Web Service
After=network.target postgresql.service
Wants=postgresql.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=${WEB_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python3 app.py
Restart=on-failure
RestartSec=10
StandardOutput=append:${LOGS_DIR}/web.log
StandardError=append:${LOGS_DIR}/web-error.log
Environment="PATH=${INSTALL_DIR}/venv/bin"
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

    # Ricarica systemd
    systemctl daemon-reload

    # Configurazione del firewall
    setup_firewall

    # Imposta i permessi corretti
    print_step "Impostazione dei permessi..."
    chown -R m4bot:m4bot $INSTALL_DIR
    chmod +x $BOT_DIR/m4bot.py
    chmod +x $WEB_DIR/app.py
    chmod +x $SCRIPTS_DIR/*.sh
    
    # Assicurati che le directory dei log siano scrivibili
    touch $LOGS_DIR/bot.log $LOGS_DIR/web.log $LOGS_DIR/bot-error.log $LOGS_DIR/web-error.log
    chown m4bot:m4bot $LOGS_DIR/*.log
    
    # Crea file di configurazione .env
    if [ ! -f "$BOT_DIR/.env" ]; then
        cat > $BOT_DIR/.env << EOF
# File di configurazione per M4Bot
# Generato automaticamente il $(date)

# Configurazione database
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_NAME=$DB_NAME
DB_HOST=localhost

# Configurazione applicazione
DEBUG=false
LOG_LEVEL=info
EOF
        chown m4bot:m4bot $BOT_DIR/.env
        chmod 600 $BOT_DIR/.env
    fi

    # Crea un link simbolico per i comandi di M4Bot
    print_step "Creazione dei comandi di M4Bot..."
    ln -sf $SCRIPTS_DIR/start.sh /usr/local/bin/m4bot-start
    ln -sf $SCRIPTS_DIR/stop.sh /usr/local/bin/m4bot-stop
    ln -sf $SCRIPTS_DIR/status.sh /usr/local/bin/m4bot-status
    chmod +x /usr/local/bin/m4bot-*
    
    # Crea uno script di aggiornamento
    cat > $SCRIPTS_DIR/update.sh << EOF
#!/bin/bash
# Script di aggiornamento per M4Bot

source ${SCRIPTS_DIR}/common.sh
cd $INSTALL_DIR

print_message "Aggiornamento di M4Bot in corso..."
print_message "Arresto dei servizi..."
systemctl stop m4bot-bot.service
systemctl stop m4bot-web.service

print_message "Aggiornamento del codice sorgente..."
# Inserire qui il comando per aggiornare il codice (git pull, etc.)

print_message "Attivazione dell'ambiente virtuale..."
source ${INSTALL_DIR}/venv/bin/activate

print_message "Aggiornamento delle dipendenze Python..."
pip install --upgrade pip
if [ -f "$BOT_DIR/requirements.txt" ]; then
    pip install -r $BOT_DIR/requirements.txt
fi

print_message "Riavvio dei servizi..."
systemctl start m4bot-bot.service
systemctl start m4bot-web.service

print_success "Aggiornamento completato con successo!"
EOF
    chmod +x $SCRIPTS_DIR/update.sh
    ln -sf $SCRIPTS_DIR/update.sh /usr/local/bin/m4bot-update

    # Crea un file di log rotazione
    cat > /etc/logrotate.d/m4bot << EOF
$LOGS_DIR/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 m4bot m4bot
    sharedscripts
    postrotate
        systemctl reload m4bot-bot.service >/dev/null 2>&1 || true
        systemctl reload m4bot-web.service >/dev/null 2>&1 || true
    endscript
}
EOF

    # Avvio automatico dei servizi
    print_step "Configurazione dell'avvio automatico dei servizi..."
    systemctl enable m4bot-bot.service
    systemctl enable m4bot-web.service

    # Chiedi se avviare i servizi
    read -p "Vuoi avviare i servizi M4Bot ora? (s/n): " start_choice
    if [ "$start_choice" = "s" ]; then
        print_message "Avvio dei servizi M4Bot..."
        systemctl start m4bot-bot.service
        systemctl start m4bot-web.service
        
        # Verifica lo stato dei servizi
        systemctl status m4bot-bot.service
        systemctl status m4bot-web.service
    fi

    # Fine dell'installazione
    print_success "Installazione di M4Bot completata con successo!"
    echo
    echo -e "${GREEN}===============================================${NC}"
    echo -e "${BLUE}Informazioni di installazione di M4Bot${NC}"
    echo -e "${GREEN}===============================================${NC}"
    echo -e "${CYAN}Directory principale:${NC} $INSTALL_DIR"
    echo -e "${CYAN}Utente del database:${NC} $DB_USER"
    echo -e "${CYAN}Nome del database:${NC} $DB_NAME"
    echo -e "${CYAN}File di credenziali:${NC} $INSTALL_DIR/db_credentials.conf"
    echo -e "${CYAN}Log del bot:${NC} $LOGS_DIR/bot.log"
    echo -e "${CYAN}Log dell'applicazione web:${NC} $LOGS_DIR/web.log"
    echo
    echo -e "${YELLOW}Comandi disponibili:${NC}"
    echo "m4bot-start   - Avvia tutti i servizi di M4Bot"
    echo "m4bot-stop    - Ferma tutti i servizi di M4Bot"
    echo "m4bot-status  - Visualizza lo stato di M4Bot"
    echo "m4bot-update  - Aggiorna M4Bot all'ultima versione"
    echo
    echo -e "${GREEN}===============================================${NC}"
}

# Esegui la funzione principale
install_m4bot
