#!/bin/bash
# Script unificato per M4Bot
# Questo script combina installazione, avvio e configurazione in un unico file
# Autore: M4Tronick
# Versione: 1.0

### FUNZIONI COMUNI ###

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzione per stampare messaggi colorati
print_message() {
    echo -e "${BLUE}[M4BOT]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESSO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[ATTENZIONE]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERRORE]${NC} $1"
    if [ "$2" -eq 1 ]; then
        exit 1
    fi
}

# Verifica che l'utente sia root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "Questo script deve essere eseguito come root" 1
    fi
}

# Verifica che PostgreSQL sia in esecuzione
check_postgres() {
    if ! systemctl is-active --quiet postgresql; then
        print_error "PostgreSQL non Ã¨ in esecuzione. Avvialo con: systemctl start postgresql" 1
    fi
}

# Verifica lo stato dei servizi principali
check_services() {
    # Verifica PostgreSQL
    if ! systemctl is-active --quiet postgresql; then
        print_warning "PostgreSQL non Ã¨ in esecuzione. Avvio in corso..."
        systemctl start postgresql
        if [ $? -ne 0 ]; then
            print_error "Impossibile avviare PostgreSQL" 1
        else
            print_success "PostgreSQL avviato"
        fi
    fi

    # Verifica Nginx
    if ! systemctl is-active --quiet nginx; then
        print_warning "Nginx non Ã¨ in esecuzione. Avvio in corso..."
        systemctl start nginx
        if [ $? -ne 0 ]; then
            print_error "Impossibile avviare Nginx" 1
        else
            print_success "Nginx avviato"
        fi
    fi
}

# Funzione per eseguire una fase e controllare se ha avuto successo
execute_step() {
    local step_name="$1"
    local command="$2"

    print_message "[PASSO] $step_name..."

    eval "$command"

    if [ $? -eq 0 ]; then
        print_success "Completato: $step_name"
        return 0
    else
        print_error "Errore durante: $step_name" 0
        read -p "Vuoi riprovare questo passaggio? (s/n): " retry
        if [ "$retry" == "s" ]; then
            execute_step "$step_name" "$command"
        else
            return 1
        fi
    fi
}

### FUNZIONI DI INSTALLAZIONE ###

# Configura il database PostgreSQL
setup_postgres() {
    print_message "Configurazione del database PostgreSQL..."

    # Verifica che PostgreSQL sia in esecuzione
    if ! systemctl is-active --quiet postgresql; then
        print_message "Avvio PostgreSQL..."
        systemctl start postgresql
        sleep 2
    fi

    # Parametri del database
    DB_NAME=${1:-"m4bot_db"}
    DB_USER=${2:-"m4bot_user"}
    DB_PASSWORD=${3:-"m4bot_password"}

    # Creiamo l'utente e il database PostgreSQL
    print_message "Creazione dell'utente database $DB_USER..."
    su - postgres -c "psql -c \"CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';\""

    print_message "Creazione del database $DB_NAME..."
    su - postgres -c "psql -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER;\""

    print_message "Configurazione dei privilegi..."
    su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;\""

    print_success "Database configurato con successo!"
}

# Inizializza il database con lo schema iniziale
init_database() {
    print_message "Inizializzazione del database..."

    # Parametri
    DB_NAME=${1:-"m4bot_db"}
    DB_USER=${2:-"m4bot_user"}
    DB_PASSWORD=${3:-"m4bot_password"}
    INSTALL_DIR=${4:-"/opt/m4bot"}

    # Schema di base per il database (versione semplificata)
    SCHEMA_SQL="
    -- Tabella utenti
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username VARCHAR(50) UNIQUE NOT NULL,
        password_hash VARCHAR(255) NOT NULL,
        email VARCHAR(255) UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        is_admin BOOLEAN DEFAULT FALSE
    );

    -- Tabella per i log degli eventi
    CREATE TABLE IF NOT EXISTS event_logs (
        id SERIAL PRIMARY KEY,
        event_type VARCHAR(50) NOT NULL,
        description TEXT,
        user_id INTEGER REFERENCES users(id),
        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        severity VARCHAR(20) DEFAULT 'info'
    );

    -- Tabella configurazioni
    CREATE TABLE IF NOT EXISTS config (
        key VARCHAR(100) PRIMARY KEY,
        value TEXT,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Inserimento utente admin iniziale
    INSERT INTO users (username, password_hash, email, is_admin)
    VALUES ('M4Tronick', '\$2b\$12\$K8etytZvB6HM5XnNgzyu8eSXqmZdWRFX5HGGHmYg0adXRjBCBu1Hm', 'admin@m4bot.it', TRUE)
    ON CONFLICT (username) DO NOTHING;

    -- Configurazioni iniziali
    INSERT INTO config (key, value, description)
    VALUES 
        ('dashboard_url', 'dashboard.m4bot.it', 'URL della dashboard utente'),
        ('control_url', 'control.m4bot.it', 'URL del pannello di controllo admin'),
        ('version', '1.0.0', 'Versione di M4Bot')
    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
    "

    # Crea una directory temporanea per lo schema
    mkdir -p "$INSTALL_DIR/tmp"
    echo "$SCHEMA_SQL" > "$INSTALL_DIR/tmp/schema.sql"

    # Esegui lo schema SQL
    export PGPASSWORD="$DB_PASSWORD"
    psql -h localhost -U "$DB_USER" -d "$DB_NAME" -f "$INSTALL_DIR/tmp/schema.sql"
    
    # Pulisci
    rm -f "$INSTALL_DIR/tmp/schema.sql"

    print_success "Database inizializzato con successo!"
}

# Configurare Nginx con dashboard e control panel
setup_nginx() {
    print_message "Configurazione di Nginx..."

    # Parametri
    DOMAIN=${1:-"m4bot.it"}
    DASHBOARD_DOMAIN="dashboard.$DOMAIN"
    CONTROL_DOMAIN="control.$DOMAIN"
    EMAIL=${2:-"admin@m4bot.it"}
    PORT=${3:-"8000"}

    # Crea il file di configurazione principale
    cat > /etc/nginx/sites-available/m4bot.conf << EOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

    # Crea il file di configurazione per la dashboard
    cat > /etc/nginx/sites-available/dashboard.conf << EOF
server {
    listen 80;
    server_name $DASHBOARD_DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$PORT/dashboard;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

    # Crea il file di configurazione per il pannello di controllo
    cat > /etc/nginx/sites-available/control.conf << EOF
server {
    listen 80;
    server_name $CONTROL_DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$PORT/control;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

    # Abilita i siti
    ln -sf /etc/nginx/sites-available/m4bot.conf /etc/nginx/sites-enabled/
    ln -sf /etc/nginx/sites-available/dashboard.conf /etc/nginx/sites-enabled/
    ln -sf /etc/nginx/sites-available/control.conf /etc/nginx/sites-enabled/

    # Rimuovi la configurazione di default
    if [ -f /etc/nginx/sites-enabled/default ]; then
        rm -f /etc/nginx/sites-enabled/default
    fi

    # Verifica la configurazione di Nginx
    nginx -t

    if [ $? -ne 0 ]; then
        print_error "La configurazione di Nginx non Ã¨ valida" 1
    fi

    # Riavvia Nginx
    systemctl restart nginx

    if [ $? -ne 0 ]; then
        print_error "Impossibile riavviare Nginx" 1
    fi

    print_success "Nginx configurato correttamente"

    # Configurazione SSL
    if [ "$4" == "--ssl" ]; then
        print_message "Configurazione SSL con Certbot..."

        # Installa certbot se non Ã¨ installato
        if ! command -v certbot &> /dev/null; then
            print_message "Installazione di Certbot..."
            apt-get update
            apt-get install -y certbot python3-certbot-nginx
        fi

        # Ottieni i certificati SSL per tutti i domini
        certbot --nginx -d $DOMAIN -d www.$DOMAIN -d $DASHBOARD_DOMAIN -d $CONTROL_DOMAIN --non-interactive --agree-tos --email $EMAIL

        if [ $? -ne 0 ]; then
            print_error "Impossibile configurare SSL con Certbot" 0
        else
            print_success "SSL configurato correttamente per tutti i domini"
        fi
    fi
}

# Configurazione dei servizi systemd
setup_services() {
    print_message "Configurazione dei servizi systemd..."

    # Parametri
    INSTALL_DIR=${1:-"/opt/m4bot"}
    BOT_DIR=${2:-"$INSTALL_DIR/bot"}
    WEB_DIR=${3:-"$INSTALL_DIR/web"}
    USER=${4:-"m4bot"}
    GROUP=${5:-"m4bot"}

    # Verifica che le directory esistano
    if [ ! -d "$INSTALL_DIR" ]; then
        print_message "Creazione della directory di installazione $INSTALL_DIR..."
        mkdir -p $INSTALL_DIR
    fi

    if [ ! -d "$BOT_DIR" ]; then
        print_message "Creazione della directory del bot $BOT_DIR..."
        mkdir -p $BOT_DIR
    fi

    if [ ! -d "$WEB_DIR" ]; then
        print_message "Creazione della directory web $WEB_DIR..."
        mkdir -p $WEB_DIR
    fi

    # Verifica che l'utente e il gruppo esistano
    if ! id -u $USER &>/dev/null; then
        print_message "Creazione dell'utente $USER..."
        useradd -m -s /bin/bash $USER
        print_success "Utente $USER creato"
    fi

    # Crea il servizio systemd per il bot
    print_message "Creazione del servizio systemd per il bot..."
    cat > /etc/systemd/system/m4bot-bot.service << EOF
[Unit]
Description=M4Bot Bot Service
After=network.target postgresql.service

[Service]
User=$USER
Group=$GROUP
WorkingDirectory=$BOT_DIR
ExecStart=/usr/bin/python3 $BOT_DIR/m4bot.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

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
User=$USER
Group=$GROUP
WorkingDirectory=$WEB_DIR
ExecStart=/usr/bin/python3 $WEB_DIR/app.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Ricarica systemd
    systemctl daemon-reload

    # Imposta i permessi corretti
    print_message "Impostazione dei permessi..."
    chown -R $USER:$GROUP $INSTALL_DIR

    if [ -f "$BOT_DIR/m4bot.py" ]; then
        chmod +x $BOT_DIR/m4bot.py
    fi

    if [ -f "$WEB_DIR/app.py" ]; then
        chmod +x $WEB_DIR/app.py
    fi

    # Avvio automatico dei servizi
    print_message "Configurazione dell'avvio automatico dei servizi..."
    systemctl enable m4bot-bot.service
    systemctl enable m4bot-web.service

    print_success "Servizi configurati correttamente"
}

# Configura la sicurezza del server
setup_security() {
    print_message "Configurazione delle impostazioni di sicurezza per M4Bot..."

    # Installa fail2ban per proteggere da tentativi di accesso non autorizzati
    print_message "Installazione di fail2ban..."
    apt-get install -y fail2ban || print_error "Impossibile installare fail2ban" 1

    # Configura fail2ban per Nginx
    cat > /etc/fail2ban/jail.d/nginx.conf << EOF
[nginx-http-auth]
enabled = true
port = http,https
filter = nginx-http-auth
logpath = /var/log/nginx/error.log
maxretry = 5
bantime = 3600
findtime = 600

[nginx-login]
enabled = true
port = http,https
filter = nginx-login
logpath = /var/log/nginx/access.log
maxretry = 5
bantime = 3600
findtime = 600
EOF

    # Configura il firewall UFW
    print_message "Configurazione del firewall UFW..."
    apt-get install -y ufw || print_warning "UFW giÃ  installato o impossibile installare"

    # Configura le regole UFW
    ufw default deny incoming
    ufw default allow outgoing
    ufw allow ssh
    ufw allow http
    ufw allow https
    ufw allow 5432/tcp comment 'PostgreSQL'

    # Abilita UFW in modo non interattivo
    print_message "Abilitazione di UFW..."
    echo "y" | ufw enable

    # Hardening della configurazione SSL di Nginx
    print_message "Hardening della configurazione SSL di Nginx..."
    cat > /etc/nginx/snippets/ssl-params.conf << EOF
ssl_protocols TLSv1.2 TLSv1.3;
ssl_prefer_server_ciphers on;
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
ssl_session_timeout 1d;
ssl_session_cache shared:SSL:10m;
ssl_session_tickets off;
ssl_stapling on;
ssl_stapling_verify on;
resolver 8.8.8.8 8.8.4.4 valid=300s;
resolver_timeout 5s;
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
add_header X-Frame-Options SAMEORIGIN;
add_header X-Content-Type-Options nosniff;
add_header X-XSS-Protection "1; mode=block";
EOF

    # Configurazione della protezione DDoS di base in Nginx
    print_message "Configurazione della protezione DDoS di base in Nginx..."
    cat > /etc/nginx/conf.d/rate-limit.conf << EOF
limit_req_zone \$binary_remote_addr zone=m4bot_limit:10m rate=10r/s;
EOF

    # Riavvio dei servizi di sicurezza
    print_message "Riavvio dei servizi di sicurezza..."
    systemctl restart fail2ban
    systemctl restart nginx

    print_success "Configurazione di sicurezza completata!"
}

### FUNZIONI DI GESTIONE ###

# Avvia i servizi di M4Bot
start_bot() {
    print_message "Avvio di M4Bot..."

    # Verifica che la directory dei log esista
    if [ ! -d "/opt/m4bot/bot/logs" ]; then
        print_warning "La directory dei log non esiste, creazione in corso..."
        mkdir -p /opt/m4bot/bot/logs
        chown -R m4bot:m4bot /opt/m4bot/bot/logs 2>/dev/null || true
        chmod -R 755 /opt/m4bot/bot/logs
        print_success "Directory dei log creata"
    fi

    # Verifica che PostgreSQL e Nginx siano in esecuzione
    check_services

    # Controllo se i servizi sono giÃ  in esecuzione
    if systemctl is-active --quiet m4bot-bot.service; then
        print_warning "Il servizio bot Ã¨ giÃ  in esecuzione"
    else
        systemctl start m4bot-bot.service
        if [ $? -eq 0 ]; then
            print_success "Bot avviato con successo"
        else
            print_error "Impossibile avviare il bot" 1
        fi
    fi

    if systemctl is-active --quiet m4bot-web.service; then
        print_warning "Il servizio web Ã¨ giÃ  in esecuzione"
    else
        systemctl start m4bot-web.service
        if [ $? -eq 0 ]; then
            print_success "Web app avviata con successo"
        else
            print_error "Impossibile avviare la web app" 1
        fi
    fi

    print_message "Stato dei servizi:"
    systemctl status m4bot-bot.service --no-pager | grep Active
    systemctl status m4bot-web.service --no-pager | grep Active
    systemctl status nginx --no-pager | grep Active
    systemctl status postgresql --no-pager | grep Active

    print_message "M4Bot Ã¨ ora disponibile all'indirizzo https://m4bot.it"
    print_message "Dashboard: https://dashboard.m4bot.it"
    print_message "Pannello di controllo: https://control.m4bot.it"
}

# Ferma i servizi di M4Bot
stop_bot() {
    print_message "Arresto di M4Bot..."

    # Arresto dei servizi
    if systemctl is-active --quiet m4bot-bot.service; then
        systemctl stop m4bot-bot.service
        if [ $? -eq 0 ]; then
            print_success "Bot arrestato con successo"
        else
            print_error "Impossibile arrestare il bot" 1
        fi
    else
        print_warning "Il servizio bot non Ã¨ in esecuzione"
    fi

    if systemctl is-active --quiet m4bot-web.service; then
        systemctl stop m4bot-web.service
        if [ $? -eq 0 ]; then
            print_success "Web app arrestata con successo"
        else
            print_error "Impossibile arrestare la web app" 1
        fi
    else
        print_warning "Il servizio web non Ã¨ in esecuzione"
    fi

    print_message "Tutti i servizi di M4Bot sono stati arrestati"
}

# Riavvia i servizi di M4Bot
restart_bot() {
    print_message "Riavvio di M4Bot..."

    # Ferma i servizi
    print_message "Arresto dei servizi in corso..."
    systemctl stop m4bot-bot.service
    if [ $? -eq 0 ]; then
        print_success "Bot arrestato con successo"
    else
        print_warning "Impossibile arrestare il bot, potrebbe non essere in esecuzione"
    fi

    systemctl stop m4bot-web.service
    if [ $? -eq 0 ]; then
        print_success "Web app arrestata con successo"
    else
        print_warning "Impossibile arrestare la web app, potrebbe non essere in esecuzione"
    fi

    # Breve pausa
    sleep 2

    # Avvia i servizi
    print_message "Avvio dei servizi in corso..."
    systemctl start m4bot-bot.service
    if [ $? -eq 0 ]; then
        print_success "Bot avviato con successo"
    else
        print_error "Impossibile avviare il bot" 1
    fi

    systemctl start m4bot-web.service
    if [ $? -eq 0 ]; then
        print_success "Web app avviata con successo"
    else
        print_error "Impossibile avviare la web app" 1
    fi

    # Controlla i servizi
    check_services

    print_message "M4Bot Ã¨ stato riavviato con successo"
}

# Controlla lo stato di M4Bot
status_bot() {
    print_message "Controllo dello stato di M4Bot..."

    # Controllo dello stato dei servizi
    print_message "Servizio Bot:"
    systemctl status m4bot-bot.service --no-pager

    echo ""
    print_message "Servizio Web:"
    systemctl status m4bot-web.service --no-pager

    echo ""
    print_message "Servizio Nginx:"
    systemctl status nginx --no-pager | grep Active

    echo ""
    print_message "Servizio PostgreSQL:"
    systemctl status postgresql --no-pager | grep Active

    # Verifica se i servizi sono attivi
    if systemctl is-active --quiet m4bot-bot.service && systemctl is-active --quiet m4bot-web.service && systemctl is-active --quiet nginx && systemctl is-active --quiet postgresql; then
        echo ""
        print_success "Tutti i servizi di M4Bot sono attivi e funzionanti"
        echo ""
        print_message "M4Bot Ã¨ disponibile all'indirizzo https://m4bot.it"
        print_message "Dashboard: https://dashboard.m4bot.it"
        print_message "Pannello di controllo: https://control.m4bot.it"
    else
        echo ""
        print_error "Uno o piÃ¹ servizi di M4Bot non sono attivi" 0
    fi

    # Controlla l'utilizzo delle risorse
    echo ""
    print_message "Utilizzo delle risorse:"
    echo "- CPU e Memoria per i processi di M4Bot:"
    ps aux | grep -E "m4bot.py|app.py" | grep -v grep

    echo ""
    print_message "Spazio su disco:"
    df -h | grep -E '(Filesystem|/$)'

    echo ""
    print_message "Ultimi log del bot:"
    journalctl -u m4bot-bot.service -n 10 --no-pager

    echo ""
    print_message "Ultimi log del web:"
    journalctl -u m4bot-web.service -n 10 --no-pager
} 