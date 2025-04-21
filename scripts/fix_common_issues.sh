#!/bin/bash
# Script per la risoluzione dei problemi comuni di M4Bot

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directory di installazione (modificare se necessario)
INSTALL_DIR="/opt/m4bot"
BOT_DIR="$INSTALL_DIR/bot"
WEB_DIR="$INSTALL_DIR/web"
LOG_DIR="$INSTALL_DIR/logs"

# Funzioni di utilità
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

# Controlla che lo script sia eseguito come root
if [ "$(id -u)" != "0" ]; then
    print_error "Questo script deve essere eseguito come root" 1
fi

# Se viene passato un parametro, usa quello come directory di installazione
if [ -n "$1" ]; then
    INSTALL_DIR="$1"
    BOT_DIR="$INSTALL_DIR/bot"
    WEB_DIR="$INSTALL_DIR/web"
    LOG_DIR="$INSTALL_DIR/logs"
fi

# Verifica che la directory esista
if [ ! -d "$INSTALL_DIR" ]; then
    print_error "Directory $INSTALL_DIR non trovata" 1
fi

print_message "Risoluzione dei problemi comuni di M4Bot in $INSTALL_DIR..."

# Problema 1: Permessi errati
print_message "Controllo dei permessi..."
find "$INSTALL_DIR" -type d -exec chmod 755 {} \;
find "$INSTALL_DIR" -type f -name "*.py" -exec chmod 644 {} \;
find "$INSTALL_DIR" -type f -name "*.sh" -exec chmod 755 {} \;
find "$INSTALL_DIR/scripts" -type f -name "*.sh" -exec chmod 755 {} \;
if [ -f "$BOT_DIR/m4bot.py" ]; then
    chmod 755 "$BOT_DIR/m4bot.py"
fi
if [ -f "$WEB_DIR/app.py" ]; then
    chmod 755 "$WEB_DIR/app.py"
fi
print_success "Permessi corretti"

# Problema 2: Servizi non attivi
print_message "Controllo dei servizi..."
if systemctl is-active --quiet m4bot-bot.service; then
    print_success "Il servizio m4bot-bot.service è attivo"
else
    print_warning "Il servizio m4bot-bot.service non è attivo, tentativo di avvio..."
    systemctl start m4bot-bot.service
fi

if systemctl is-active --quiet m4bot-web.service; then
    print_success "Il servizio m4bot-web.service è attivo"
else
    print_warning "Il servizio m4bot-web.service non è attivo, tentativo di avvio..."
    systemctl start m4bot-web.service
fi

if systemctl is-active --quiet postgresql; then
    print_success "Il servizio postgresql è attivo"
else
    print_warning "Il servizio postgresql non è attivo, tentativo di avvio..."
    systemctl start postgresql
fi

if systemctl is-active --quiet nginx; then
    print_success "Il servizio nginx è attivo"
else
    print_warning "Il servizio nginx non è attivo, tentativo di avvio..."
    systemctl start nginx
fi

if systemctl is-active --quiet redis-server; then
    print_success "Il servizio redis-server è attivo"
else
    print_warning "Il servizio redis-server non è attivo, tentativo di avvio..."
    systemctl start redis-server
fi

# Problema 3: File di log troppo grandi
print_message "Controllo dei file di log..."
find "$LOG_DIR" -type f -name "*.log" -size +100M -exec truncate -s 10M {} \;
print_success "File di log controllati"

# Problema 4: Porta occupata
print_message "Controllo delle porte..."

if ! netstat -tuln | grep -q ":5000 "; then
    print_warning "La porta 5000 non è in ascolto, tentativo di riavvio dei servizi..."
    systemctl restart m4bot-web.service
fi

if ! netstat -tuln | grep -q ":5001 "; then
    print_warning "La porta 5001 non è in ascolto, tentativo di riavvio dei servizi..."
    systemctl restart m4bot-bot.service
fi
print_success "Porte controllate"

# Problema 5: File temporanei
print_message "Pulizia dei file temporanei..."
find "$INSTALL_DIR" -name "*.pyc" -delete
find "$INSTALL_DIR" -name "__pycache__" -exec rm -rf {} +
if [ -d "$INSTALL_DIR/tmp" ]; then
    rm -rf "$INSTALL_DIR/tmp/*"
fi
print_success "File temporanei puliti"

# Problema 6: Ambiente virtuale
print_message "Controllo dell'ambiente virtuale..."
if [ ! -d "$INSTALL_DIR/venv" ]; then
    print_warning "Ambiente virtuale non trovato, creazione in corso..."
    python3 -m venv "$INSTALL_DIR/venv"
    print_message "Installazione delle dipendenze..."
    if [ -f "$INSTALL_DIR/requirements.txt" ]; then
        "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
    elif [ -f "$BOT_DIR/requirements.txt" ]; then
        "$INSTALL_DIR/venv/bin/pip" install -r "$BOT_DIR/requirements.txt"
    elif [ -f "$WEB_DIR/requirements.txt" ]; then
        "$INSTALL_DIR/venv/bin/pip" install -r "$WEB_DIR/requirements.txt"
    else
        print_warning "File requirements.txt non trovato, installazione pacchetti di base..."
        "$INSTALL_DIR/venv/bin/pip" install flask flask-babel flask-session flask-login psycopg2-binary redis requests
    fi
else
    print_success "Ambiente virtuale trovato"
fi

# Problema 7: Directory mancanti
print_message "Controllo delle directory necessarie..."
declare -a directories=(
    "$BOT_DIR"
    "$WEB_DIR"
    "$LOG_DIR"
    "$BOT_DIR/plugins"
    "$BOT_DIR/languages"
    "$WEB_DIR/templates"
    "$WEB_DIR/static"
    "$WEB_DIR/static/css"
    "$WEB_DIR/static/js"
    "$WEB_DIR/static/images"
)

for dir in "${directories[@]}"; do
    if [ ! -d "$dir" ]; then
        print_warning "Directory $dir non trovata, creazione in corso..."
        mkdir -p "$dir"
    fi
done
print_success "Directory controllate"

# Problema 8: Configurazione Nginx
print_message "Controllo della configurazione Nginx..."
if [ ! -f "/etc/nginx/sites-available/m4bot" ]; then
    print_warning "Configurazione Nginx non trovata, creazione in corso..."
    cat > "/etc/nginx/sites-available/m4bot" << EOF
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static/ {
        alias $WEB_DIR/static/;
    }
}
EOF
    if [ ! -L "/etc/nginx/sites-enabled/m4bot" ]; then
        ln -s "/etc/nginx/sites-available/m4bot" "/etc/nginx/sites-enabled/"
    fi
    systemctl reload nginx
fi
print_success "Configurazione Nginx controllata"

# Problema 9: Problemi di encoding
print_message "Correzione dei problemi di encoding..."
find "$INSTALL_DIR" -type f -name "*.py" -o -name "*.sh" | while read -r file; do
    if file "$file" | grep -q "ISO-8859"; then
        print_warning "Conversione encoding per $file..."
        iconv -f ISO-8859-1 -t UTF-8 -o "$file.tmp" "$file" && mv "$file.tmp" "$file"
    fi
done
print_success "Problemi di encoding corretti"

# Problema 10: Risoluzione problemi file .env
if [ -f "$INSTALL_DIR/.env" ]; then
    print_message "Controllo file .env..."
    # Verifica se DATABASE_URL è impostato correttamente
    if ! grep -q "DATABASE_URL" "$INSTALL_DIR/.env"; then
        print_warning "DATABASE_URL non trovato in .env, aggiunta in corso..."
        echo "DATABASE_URL=postgresql://m4bot_user:m4bot_password@localhost/m4bot_db" >> "$INSTALL_DIR/.env"
    fi
    # Verifica se SECRET_KEY è impostato correttamente
    if ! grep -q "SECRET_KEY" "$INSTALL_DIR/.env"; then
        print_warning "SECRET_KEY non trovato in .env, aggiunta in corso..."
        echo "SECRET_KEY=$(openssl rand -hex 32)" >> "$INSTALL_DIR/.env"
    fi
else
    print_warning "File .env non trovato, creazione in corso..."
    cat > "$INSTALL_DIR/.env" << EOF
# Configurazione di M4Bot
DEBUG=False
SECRET_KEY=$(openssl rand -hex 32)
DATABASE_URL=postgresql://m4bot_user:m4bot_password@localhost/m4bot_db
REDIS_URL=redis://localhost:6379/0
EOF
fi
print_success "File .env controllato"

# Problema 11: Correzione unit file systemd
print_message "Controllo dei file di servizio systemd..."
if [ -f "/etc/systemd/system/m4bot-bot.service" ]; then
    if ! grep -q "ExecStart=" "/etc/systemd/system/m4bot-bot.service"; then
        print_warning "ExecStart non trovato in m4bot-bot.service, correzione in corso..."
        cat > "/etc/systemd/system/m4bot-bot.service" << EOF
[Unit]
Description=M4Bot Bot Service
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$BOT_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $BOT_DIR/m4bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl restart m4bot-bot.service
    fi
else
    print_warning "File m4bot-bot.service non trovato, creazione in corso..."
    cat > "/etc/systemd/system/m4bot-bot.service" << EOF
[Unit]
Description=M4Bot Bot Service
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$BOT_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $BOT_DIR/m4bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable m4bot-bot.service
    systemctl start m4bot-bot.service
fi

if [ -f "/etc/systemd/system/m4bot-web.service" ]; then
    if ! grep -q "ExecStart=" "/etc/systemd/system/m4bot-web.service"; then
        print_warning "ExecStart non trovato in m4bot-web.service, correzione in corso..."
        cat > "/etc/systemd/system/m4bot-web.service" << EOF
[Unit]
Description=M4Bot Web Service
After=network.target postgresql.service redis-server.service m4bot-bot.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$WEB_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $WEB_DIR/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
        systemctl daemon-reload
        systemctl restart m4bot-web.service
    fi
else
    print_warning "File m4bot-web.service non trovato, creazione in corso..."
    cat > "/etc/systemd/system/m4bot-web.service" << EOF
[Unit]
Description=M4Bot Web Service
After=network.target postgresql.service redis-server.service m4bot-bot.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$WEB_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $WEB_DIR/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable m4bot-web.service
    systemctl start m4bot-web.service
fi
print_success "File di servizio systemd controllati"

# Problema 12: Verifica e correzione dei permessi dei file di configurazione
print_message "Correzione dei permessi dei file di configurazione..."
if [ -f "$BOT_DIR/config.py" ]; then
    chmod 644 "$BOT_DIR/config.py"
    chown m4bot:m4bot "$BOT_DIR/config.py"
fi
if [ -f "$WEB_DIR/config.py" ]; then
    chmod 644 "$WEB_DIR/config.py"
    chown m4bot:m4bot "$WEB_DIR/config.py"
fi
if [ -f "$INSTALL_DIR/.env" ]; then
    chmod 600 "$INSTALL_DIR/.env"
    chown m4bot:m4bot "$INSTALL_DIR/.env"
fi
print_success "Permessi dei file di configurazione corretti"

# Problema 13: Imposta l'utente m4bot come proprietario
print_message "Impostazione dell'utente m4bot come proprietario..."
if ! id -u m4bot &>/dev/null; then
    print_warning "Utente m4bot non trovato, creazione in corso..."
    useradd -m -s /bin/bash m4bot
fi
chown -R m4bot:m4bot "$INSTALL_DIR"
print_success "Utente m4bot impostato come proprietario"

# Riavvia i servizi per applicare tutte le modifiche
print_message "Riavvio dei servizi..."
systemctl restart nginx
systemctl restart m4bot-bot.service
systemctl restart m4bot-web.service

print_success "Risoluzione dei problemi completata"
print_message "Tutti i problemi comuni sono stati corretti" 