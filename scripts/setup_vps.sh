#!/bin/bash
# Script per la configurazione dell'ambiente Linux VPS per M4Bot
# Installa tutte le dipendenze necessarie e prepara il sistema

# Imposta i colori per i messaggi
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzione per i messaggi
print_message() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verifica che lo script sia eseguito come root
if [ "$EUID" -ne 0 ]; then
    print_error "Questo script deve essere eseguito come root (usa sudo)"
    exit 1
fi

# Verifica che il sistema sia Linux
if [ "$(uname)" != "Linux" ]; then
    print_error "Questo script è progettato per funzionare solo su Linux"
    exit 1
fi

# Determina la distribuzione Linux
DISTRO=""
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
else
    print_error "Impossibile determinare la distribuzione Linux"
    exit 1
fi

print_message "Sistema operativo rilevato: $DISTRO $VERSION_ID"

# Verifica se la distribuzione è supportata
case $DISTRO in
    "ubuntu"|"debian")
        print_success "Distribuzione supportata: $DISTRO"
        ;;
    *)
        print_warning "Distribuzione non supportata ufficialmente: $DISTRO. Tenterò comunque l'installazione con comandi compatibili con Debian/Ubuntu"
        DISTRO="ubuntu"  # Usa i comandi di ubuntu come fallback
        ;;
esac

# Percorso di installazione
M4BOT_DIR=${M4BOT_DIR:-"/opt/m4bot"}
print_message "Installazione in: $M4BOT_DIR"

# Crea il log directory
SETUP_LOG_DIR="$M4BOT_DIR/logs/setup"
mkdir -p "$SETUP_LOG_DIR"
SETUP_LOG="$SETUP_LOG_DIR/setup_$(date +%Y%m%d_%H%M%S).log"

# Funzione per aggiornare ed installare pacchetti
install_packages() {
    print_message "Aggiornamento del sistema..."
    
    if [ "$DISTRO" = "ubuntu" ] || [ "$DISTRO" = "debian" ]; then
        # Aggiorna i repository ed il sistema
        apt-get update -y >> "$SETUP_LOG" 2>&1
        apt-get upgrade -y >> "$SETUP_LOG" 2>&1
        
        print_message "Installazione dei pacchetti essenziali..."
        apt-get install -y \
            git \
            python3 python3-pip python3-venv \
            nginx \
            postgresql postgresql-contrib \
            redis-server \
            certbot python3-certbot-nginx \
            curl wget \
            build-essential \
            libpq-dev \
            net-tools \
            supervisor \
            ufw \
            unzip \
            sudo \
            >> "$SETUP_LOG" 2>&1
        
        if [ $? -ne 0 ]; then
            print_error "Errore durante l'installazione dei pacchetti. Controlla $SETUP_LOG per maggiori dettagli."
            exit 1
        fi
        
        print_success "Pacchetti essenziali installati"
    else
        print_error "Installazione dei pacchetti non implementata per questa distribuzione"
        exit 1
    fi
}

# Configura PostgreSQL
setup_postgresql() {
    print_message "Configurazione di PostgreSQL..."
    
    # Assicurati che PostgreSQL sia in esecuzione
    systemctl start postgresql
    systemctl enable postgresql
    
    # Crea l'utente e il database per M4Bot
    DB_USER="m4bot_user"
    DB_PASS="m4bot_password_$(openssl rand -hex 4)"
    DB_NAME="m4bot_db"
    
    # Verifica se l'utente esiste già
    su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'\"" | grep -q 1
    if [ $? -ne 0 ]; then
        # Crea l'utente
        su - postgres -c "createuser --createdb $DB_USER"
        su - postgres -c "psql -c \"ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';\""
        print_success "Utente PostgreSQL creato: $DB_USER"
    else
        print_warning "L'utente PostgreSQL $DB_USER esiste già"
    fi
    
    # Verifica se il database esiste già
    su - postgres -c "psql -lqt | cut -d \| -f 1 | grep -qw $DB_NAME"
    if [ $? -ne 0 ]; then
        # Crea il database
        su - postgres -c "createdb -O $DB_USER $DB_NAME"
        print_success "Database PostgreSQL creato: $DB_NAME"
    else
        print_warning "Il database PostgreSQL $DB_NAME esiste già"
    fi
    
    # Abilita l'estensione pgcrypto per le funzioni crittografiche
    su - postgres -c "psql -d $DB_NAME -c 'CREATE EXTENSION IF NOT EXISTS pgcrypto;'"
    
    # Salva le credenziali del database
    echo "DB_USER=$DB_USER" >> "$M4BOT_DIR/.env.temp"
    echo "DB_PASSWORD=$DB_PASS" >> "$M4BOT_DIR/.env.temp"
    echo "DB_NAME=$DB_NAME" >> "$M4BOT_DIR/.env.temp"
    echo "DB_HOST=localhost" >> "$M4BOT_DIR/.env.temp"
    echo "DATABASE_URL=postgresql://$DB_USER:$DB_PASS@localhost/$DB_NAME" >> "$M4BOT_DIR/.env.temp"
    
    print_success "PostgreSQL configurato correttamente"
}

# Configura Redis
setup_redis() {
    print_message "Configurazione di Redis..."
    
    # Assicurati che Redis sia in esecuzione
    systemctl start redis-server
    systemctl enable redis-server
    
    # Verifica la connessione a Redis
    if redis-cli ping | grep -q "PONG"; then
        print_success "Redis risponde correttamente"
    else
        print_error "Redis non risponde. Controlla la configurazione di Redis e riavvia il servizio."
        exit 1
    fi
    
    # Salva l'URL Redis
    echo "REDIS_URL=redis://localhost:6379/0" >> "$M4BOT_DIR/.env.temp"
    
    print_success "Redis configurato correttamente"
}

# Configura Nginx
setup_nginx() {
    print_message "Configurazione di Nginx..."
    
    # Assicurati che Nginx sia in esecuzione
    systemctl start nginx
    systemctl enable nginx
    
    # Crea una configurazione di base per M4Bot
    DOMAIN=${DOMAIN:-"localhost"}
    
    # Directory per i certificati
    mkdir -p "$M4BOT_DIR/ssl"
    
    # Crea la configurazione Nginx
    cat > /etc/nginx/sites-available/m4bot << EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    # Reindirizza a HTTPS se è stato configurato un dominio diverso da localhost
    $([ "$DOMAIN" != "localhost" ] && echo "return 301 https://\$host\$request_uri;" || echo "# HTTPS non configurato")

    # Configurazione per HTTP (da utilizzare solo in sviluppo o se HTTPS non è configurato)
    $([ "$DOMAIN" = "localhost" ] && cat << 'INNEREOF'
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static {
        alias $M4BOT_DIR/web/static;
        expires 1h;
    }

    location /uploads {
        alias $M4BOT_DIR/web/uploads;
        expires 1h;
    }

    location /api/socket {
        proxy_pass http://127.0.0.1:5001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
INNEREOF
    || echo "# HTTP non configurato (verrà utilizzato HTTPS)")
}

$([ "$DOMAIN" != "localhost" ] && cat << EOF
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN;

    # Certificati SSL/TLS
    ssl_certificate $M4BOT_DIR/ssl/cert.pem;
    ssl_certificate_key $M4BOT_DIR/ssl/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
    ssl_stapling on;
    ssl_stapling_verify on;
    resolver 8.8.8.8 8.8.4.4 valid=300s;
    resolver_timeout 5s;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-XSS-Protection "1; mode=block";

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static {
        alias $M4BOT_DIR/web/static;
        expires 1h;
    }

    location /uploads {
        alias $M4BOT_DIR/web/uploads;
        expires 1h;
    }

    location /api/socket {
        proxy_pass http://127.0.0.1:5001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    || echo "# Server HTTPS non configurato")
EOF
    
    # Crea il link simbolico per abilitare il sito
    ln -sf /etc/nginx/sites-available/m4bot /etc/nginx/sites-enabled/
    
    # Verifica la configurazione
    nginx -t >> "$SETUP_LOG" 2>&1
    if [ $? -ne 0 ]; then
        print_error "Errore nella configurazione Nginx. Controlla $SETUP_LOG per maggiori dettagli."
        exit 1
    fi
    
    # Riavvia Nginx
    systemctl restart nginx
    
    # Genera certificati self-signed per sviluppo (se non è localhost)
    if [ "$DOMAIN" != "localhost" ]; then
        print_message "Generazione certificati self-signed per sviluppo..."
        openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
            -keyout "$M4BOT_DIR/ssl/key.pem" \
            -out "$M4BOT_DIR/ssl/cert.pem" \
            -subj "/CN=$DOMAIN" \
            >> "$SETUP_LOG" 2>&1
        
        print_warning "Generati certificati self-signed. Per un ambiente di produzione, configura Let's Encrypt."
        echo "# Per configurare Let's Encrypt, esegui:"
        echo "certbot --nginx -d $DOMAIN"
    fi
    
    print_success "Nginx configurato correttamente"
}

# Crea l'utente m4bot e configura le permission
setup_user() {
    print_message "Configurazione dell'utente m4bot..."
    
    # Verifica se l'utente esiste già
    id -u m4bot > /dev/null 2>&1
    if [ $? -ne 0 ]; then
        # Crea l'utente m4bot
        useradd -m -s /bin/bash m4bot
        print_success "Utente m4bot creato"
    else
        print_warning "L'utente m4bot esiste già"
    fi
    
    # Assegna la password all'utente (generata casualmente)
    USER_PASS="M4Bot_$(openssl rand -hex 4)"
    echo "m4bot:$USER_PASS" | chpasswd
    
    # Crea la directory di installazione se non esiste
    mkdir -p "$M4BOT_DIR"
    
    # Imposta i permessi
    chown -R m4bot:m4bot "$M4BOT_DIR"
    
    # Aggiungi l'utente al gruppo sudo per alcune operazioni
    usermod -aG sudo m4bot
    
    # Crea il file con la password per riferimento futuro
    echo "Utente m4bot - Password: $USER_PASS" > "$SETUP_LOG_DIR/m4bot_credentials.txt"
    chmod 600 "$SETUP_LOG_DIR/m4bot_credentials.txt"
    
    print_success "Utente m4bot configurato"
}

# Configura il firewall
setup_firewall() {
    print_message "Configurazione del firewall (ufw)..."
    
    # Assicurati che ufw sia installato
    if ! command -v ufw > /dev/null; then
        apt-get install -y ufw >> "$SETUP_LOG" 2>&1
    fi
    
    # Configura il firewall
    ufw default deny incoming
    ufw default allow outgoing
    
    # Consenti SSH, HTTP e HTTPS
    ufw allow ssh
    ufw allow http
    ufw allow https
    
    # Consenti porte specifiche per M4Bot
    ufw allow 5000  # Web app
    ufw allow 5001  # WebSocket
    
    # Abilita il firewall
    echo "y" | ufw enable
    
    # Verifica lo stato
    ufw status >> "$SETUP_LOG" 2>&1
    
    print_success "Firewall configurato correttamente"
}

# Configura l'ambiente Python
setup_python_env() {
    print_message "Configurazione dell'ambiente Python virtuale..."
    
    # Crea l'ambiente virtuale
    python3 -m venv "$M4BOT_DIR/venv"
    
    # Attiva l'ambiente virtuale e installa le dipendenze di base
    source "$M4BOT_DIR/venv/bin/activate"
    
    # Aggiorna pip
    pip install --upgrade pip >> "$SETUP_LOG" 2>&1
    
    # Installa le dipendenze di base
    pip install \
        wheel \
        setuptools \
        cryptography \
        python-dotenv \
        flask \
        quart \
        gunicorn \
        aiohttp \
        asyncpg \
        websockets \
        requests \
        redis \
        jinja2 \
        pyyaml \
        bcrypt \
        psutil \
        python-telegram-bot \
        flask-babel \
        >> "$SETUP_LOG" 2>&1
    
    if [ $? -ne 0 ]; then
        print_error "Errore durante l'installazione delle dipendenze Python. Controlla $SETUP_LOG per maggiori dettagli."
        exit 1
    fi
    
    # Salva il file requirements.txt nel caso sia necessario reinstallarlo
    pip freeze > "$M4BOT_DIR/requirements_generated.txt"
    
    # Disattiva l'ambiente virtuale
    deactivate
    
    print_success "Ambiente Python configurato correttamente"
}

# Genera una chiave di crittografia Fernet
generate_encryption_key() {
    print_message "Generazione della chiave di crittografia..."
    
    # Attiva l'ambiente virtuale
    source "$M4BOT_DIR/venv/bin/activate"
    
    # Genera la chiave
    ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    
    # Salva la chiave nel file .env
    echo "ENCRYPTION_KEY=$ENCRYPTION_KEY" >> "$M4BOT_DIR/.env.temp"
    
    # Disattiva l'ambiente virtuale
    deactivate
    
    print_success "Chiave di crittografia generata"
}

# Genera una chiave segreta per Flask
generate_secret_key() {
    print_message "Generazione della chiave segreta per Flask..."
    
    # Genera la chiave
    SECRET_KEY=$(openssl rand -hex 32)
    
    # Salva la chiave nel file .env
    echo "SECRET_KEY=$SECRET_KEY" >> "$M4BOT_DIR/.env.temp"
    
    print_success "Chiave segreta generata"
}

# Crea i servizi systemd
setup_systemd_services() {
    print_message "Configurazione dei servizi systemd..."
    
    # Servizio per il bot
    cat > /etc/systemd/system/m4bot-bot.service << EOF
[Unit]
Description=M4Bot Bot Service
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$M4BOT_DIR
ExecStart=$M4BOT_DIR/venv/bin/python $M4BOT_DIR/bot/m4bot.py
Restart=on-failure
RestartSec=5
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF
    
    # Servizio per l'applicazione web
    cat > /etc/systemd/system/m4bot-web.service << EOF
[Unit]
Description=M4Bot Web Service
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$M4BOT_DIR/web
ExecStart=$M4BOT_DIR/venv/bin/gunicorn -k quart.workers.QuartWorker -w 4 -b 127.0.0.1:5000 app:app
Restart=on-failure
RestartSec=5
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF
    
    # Ricarica i servizi systemd
    systemctl daemon-reload
    
    # Abilita i servizi (ma non li avvia ancora)
    systemctl enable m4bot-bot.service
    systemctl enable m4bot-web.service
    
    print_success "Servizi systemd configurati correttamente"
}

# Finalizza la configurazione
finalize_setup() {
    print_message "Finalizzazione della configurazione..."
    
    # Crea il file .env finale
    mv "$M4BOT_DIR/.env.temp" "$M4BOT_DIR/.env"
    
    # Imposta i permessi corretti
    chmod 600 "$M4BOT_DIR/.env"
    chown m4bot:m4bot "$M4BOT_DIR/.env"
    
    # Crea i file di log
    mkdir -p "$M4BOT_DIR/logs/bot"
    mkdir -p "$M4BOT_DIR/logs/web"
    mkdir -p "$M4BOT_DIR/logs/security"
    mkdir -p "$M4BOT_DIR/logs/database"
    
    # Assegna i permessi ai log
    chown -R m4bot:m4bot "$M4BOT_DIR/logs"
    
    # Crea le directory per l'upload
    mkdir -p "$M4BOT_DIR/web/uploads"
    mkdir -p "$M4BOT_DIR/web/static"
    
    # Assegna i permessi
    chown -R m4bot:m4bot "$M4BOT_DIR/web"
    
    print_success "Configurazione finalizzata"
}

# Esegui tutte le funzioni di setup
main() {
    print_message "Avvio della configurazione del VPS per M4Bot..."
    
    # Crea la directory di installazione
    mkdir -p "$M4BOT_DIR"
    
    # Installa i pacchetti
    install_packages
    
    # Configurazione
    setup_user
    setup_postgresql
    setup_redis
    setup_nginx
    setup_firewall
    setup_python_env
    generate_encryption_key
    generate_secret_key
    setup_systemd_services
    finalize_setup
    
    print_success "====== SETUP COMPLETATO ======"
    print_message "M4Bot è stato configurato correttamente sul tuo VPS"
    print_message "Credenziali dell'utente: $SETUP_LOG_DIR/m4bot_credentials.txt"
    print_message "Configurazione database: vedere $M4BOT_DIR/.env"
    print_message "Per avviare i servizi, esegui:"
    echo "  sudo systemctl start m4bot-bot.service"
    echo "  sudo systemctl start m4bot-web.service"
    
    # Suggerimenti finali
    if [ "$DOMAIN" != "localhost" ]; then
        print_warning "Ricorda di configurare i certificati SSL con Let's Encrypt:"
        echo "  sudo certbot --nginx -d $DOMAIN"
    fi
}

# Esegui lo script principale
main

exit 0 