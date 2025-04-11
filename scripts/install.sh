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
apt-get install -y python3 python3-pip python3-venv postgresql nginx certbot python3-certbot-nginx git

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

# Clona o copia i file sorgente
print_message "Copiando i file sorgente..."

# È possibile usare git clone o copiare i file dalla directory corrente
# Per questo esempio, copiamo i file dalla directory corrente
# Assumendo che lo script sia nella directory principale del progetto
cp -r ../bot/* $BOT_DIR/
cp -r ../web/* $WEB_DIR/
cp -r ../database/* $DB_DIR/
cp -r ../scripts/* $SCRIPTS_DIR/

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
# Creiamo l'utente e il database PostgreSQL
su - postgres -c "psql -c \"CREATE USER m4bot_user WITH PASSWORD 'm4bot_password';\""
su - postgres -c "psql -c \"CREATE DATABASE m4bot_db OWNER m4bot_user;\""
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE m4bot_db TO m4bot_user;\""

print_success "Database configurato"

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

print_success "Installazione completata con successo!"
print_message "Per avviare M4Bot, esegui: m4bot-start"
print_message "Per fermare M4Bot, esegui: m4bot-stop"
print_message "Per controllare lo stato di M4Bot, esegui: m4bot-status"
