#!/bin/bash
# Script per configurare i servizi systemd per M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

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
print_message "Puoi avviare i servizi con: systemctl start m4bot-bot.service m4bot-web.service"
print_message "O utilizzando il comando: m4bot-start" 