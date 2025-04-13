#!/bin/bash
# Script di installazione completa di M4Bot
# Questo script gestisce l'installazione di tutti i componenti necessari

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica privilegi root
check_root

print_message "Inizializzazione dell'installazione di M4Bot..."
print_message "Questo script installerà e configurerà:"
print_message "- Dipendenze di sistema"
print_message "- Database PostgreSQL"
print_message "- Server web Nginx"
print_message "- Certificati SSL con Let's Encrypt"
print_message "- Servizi systemd per il bot e l'applicazione web"
print_message "- Script wrapper per la gestione da linea di comando"

# Configurazione
M4BOT_DIR="/opt/m4bot"
WEB_DIR="$M4BOT_DIR/web"
BOT_DIR="$M4BOT_DIR/bot"
LOGS_DIR="$BOT_DIR/logs"
DB_NAME="m4bot"
DB_USER="m4bot"
DB_PASSWORD="$(openssl rand -hex 12)"  # Genera password casuale
DOMAIN="m4bot.it"  # Modifica con il tuo dominio
EMAIL="admin@$DOMAIN"  # Modifica con la tua email

# Chiedi conferma all'utente
read -p "Continuare con l'installazione? (s/n): " confirm
if [[ "$confirm" != "s" && "$confirm" != "S" ]]; then
    print_error "Installazione annullata dall'utente" 1
fi

# 1. Installazione dipendenze di sistema
install_dependencies() {
    print_message "Installazione delle dipendenze di sistema..."
    apt-get update
    apt-get install -y python3-pip python3-venv postgresql nginx certbot python3-certbot-nginx git
    print_success "Dipendenze di sistema installate con successo"
}

# 2. Clonazione repository se necessario
clone_repository() {
    if [ ! -d "$M4BOT_DIR" ]; then
        print_message "Clonazione del repository M4Bot..."
        git clone https://github.com/yourusername/M4Bot.git "$M4BOT_DIR" || {
            print_warning "Repository non trovato, creazione manuale delle directory..."
            mkdir -p "$WEB_DIR" "$BOT_DIR" "$LOGS_DIR"
        }
    else
        print_warning "Directory $M4BOT_DIR già esistente, salto la clonazione"
        # Assicurati che le directory essenziali esistano
        mkdir -p "$WEB_DIR" "$BOT_DIR" "$LOGS_DIR"
    fi
    print_success "Directory M4Bot pronta"
}

# 3. Configurazione ambiente virtuale
setup_virtualenv() {
    print_message "Configurazione dell'ambiente virtuale Python..."
    if [ ! -d "$M4BOT_DIR/venv" ]; then
        python3 -m venv "$M4BOT_DIR/venv"
    else
        print_warning "Ambiente virtuale già esistente, lo utilizzeremo"
    fi
    
    "$M4BOT_DIR/venv/bin/pip" install --upgrade pip
    
    # Installa dipendenze bot
    if [ -f "$BOT_DIR/requirements.txt" ]; then
        "$M4BOT_DIR/venv/bin/pip" install -r "$BOT_DIR/requirements.txt"
    else
        print_warning "File requirements.txt non trovato per il bot, installazione dipendenze base..."
        "$M4BOT_DIR/venv/bin/pip" install python-dotenv requests asyncio aiohttp
    fi
    
    # Installa dipendenze web
    if [ -f "$WEB_DIR/requirements.txt" ]; then
        "$M4BOT_DIR/venv/bin/pip" install -r "$WEB_DIR/requirements.txt"
    else
        print_warning "File requirements.txt non trovato per il web, installazione dipendenze base..."
        "$M4BOT_DIR/venv/bin/pip" install flask flask-sqlalchemy flask-login psycopg2-binary
    fi
    
    print_success "Ambiente virtuale configurato con successo"
}

# 4. Configurazione PostgreSQL
setup_database() {
    print_message "Configurazione del database PostgreSQL..."

    # Avvia PostgreSQL se non è in esecuzione
    if ! systemctl is-active --quiet postgresql; then
        systemctl start postgresql
    fi
    
    # Configura utente e database
    if sudo -u postgres psql -lqt | grep -q "$DB_NAME"; then
        print_warning "Database $DB_NAME già esistente"
    else
        sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
        sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
        sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
        print_success "Database creato con successo"
    fi
    
    # Salva le credenziali del database in un file di configurazione
    cat > "$M4BOT_DIR/.env" << EOF
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_NAME=$DB_NAME
DB_HOST=localhost
EOF
    
    chmod 600 "$M4BOT_DIR/.env"
    print_success "Configurazione database completata"
}

# 5. Configurazione Nginx
setup_nginx() {
    print_message "Configurazione del server web Nginx..."
    
    # Crea il file di configurazione di Nginx
    cat > /etc/nginx/sites-available/m4bot << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static {
        alias $WEB_DIR/static;
    }
}
EOF
    
    # Attiva il sito
    if [ ! -L /etc/nginx/sites-enabled/m4bot ]; then
        ln -s /etc/nginx/sites-available/m4bot /etc/nginx/sites-enabled/
    fi
    
    # Rimuovi il sito di default se esiste
    if [ -L /etc/nginx/sites-enabled/default ]; then
        rm /etc/nginx/sites-enabled/default
    fi
    
    # Controlla la configurazione
    nginx -t && systemctl reload nginx
    print_success "Configurazione Nginx completata"
}

# 6. Configurazione Let's Encrypt
setup_ssl() {
    print_message "Configurazione del certificato SSL con Let's Encrypt..."
    
    read -p "Vuoi configurare SSL con Let's Encrypt? (s/n): " confirm_ssl
    if [[ "$confirm_ssl" == "s" || "$confirm_ssl" == "S" ]]; then
        certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m $EMAIL || {
            print_warning "Impossibile ottenere il certificato SSL ora."
            print_warning "Puoi eseguire manualmente: certbot --nginx -d $DOMAIN"
        }
        print_success "Configurazione SSL completata"
    else
        print_warning "Configurazione SSL saltata"
    fi
}

# 7. Configurazione servizi systemd
setup_services() {
    print_message "Configurazione dei servizi systemd..."
    
    # Crea il servizio per il bot
    cat > /etc/systemd/system/m4bot-bot.service << EOF
[Unit]
Description=M4Bot Bot Service
After=network.target postgresql.service

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

    # Crea il servizio per l'applicazione web
    cat > /etc/systemd/system/m4bot-web.service << EOF
[Unit]
Description=M4Bot Web Service
After=network.target postgresql.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$WEB_DIR
ExecStart=$M4BOT_DIR/venv/bin/python app.py
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
    
    # Attiva i servizi per l'avvio automatico
    systemctl enable m4bot-bot.service
    systemctl enable m4bot-web.service
    
    print_success "Servizi systemd configurati con successo"
}

# 8. Crea utente di sistema dedicato
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
    
    print_success "Permessi impostati correttamente"
}

# 9. Installa gli script wrapper
install_wrappers_scripts() {
    print_message "Installazione degli script wrapper..."
    
    # Copia lo script common.sh in /usr/local/bin/
    cp "$(dirname "$0")/common.sh" /usr/local/bin/
    chmod +x /usr/local/bin/common.sh
    
    # Installa i wrapper
    source "$(dirname "$0")/install-wrappers.sh"
    
    print_success "Script wrapper installati con successo"
}

# 10. Creazione cartella logs se non esiste
ensure_logs_dir() {
    print_message "Creazione directory dei log..."
    mkdir -p "$LOGS_DIR"
    chown -R m4bot:m4bot "$LOGS_DIR"
    chmod -R 755 "$LOGS_DIR"
    print_success "Directory dei log creata/verificata"
}

# 11. Funzione per inizializzare il database con i dati iniziali
init_database() {
    print_message "Inizializzazione del database..."
    if [ -f "$(dirname "$0")/init_database.sh" ]; then
        source "$(dirname "$0")/init_database.sh"
    else
        print_warning "Script init_database.sh non trovato, saltando l'inizializzazione del database"
    fi
}

# 12. Esecuzione dei passi di installazione
install_dependencies
clone_repository
create_user
setup_virtualenv
setup_database
setup_nginx
setup_ssl
setup_services
ensure_logs_dir
init_database
install_wrappers_scripts

# 13. Avvio dei servizi
print_message "Avvio dei servizi M4Bot..."
systemctl start m4bot-bot.service
systemctl start m4bot-web.service

# 14. Verifica finale
print_message "Verifica dello stato dei servizi..."
check_services

print_success "==============================================="
print_success "Installazione di M4Bot completata con successo!"
print_success "==============================================="
print_message "Il bot è ora disponibile all'indirizzo: https://$DOMAIN"
print_message "Credenziali database:"
print_message "  Database: $DB_NAME"
print_message "  Utente:   $DB_USER"
print_message "  Password: $DB_PASSWORD"
print_message ""
print_message "Le credenziali sono state salvate nel file: $M4BOT_DIR/.env"
print_message ""
print_message "Comandi disponibili:"
print_message "  m4bot-start:   Avvia i servizi di M4Bot"
print_message "  m4bot-stop:    Ferma i servizi di M4Bot"
print_message "  m4bot-status:  Verifica lo stato dei servizi"
print_message "  m4bot-restart: Riavvia i servizi di M4Bot"
