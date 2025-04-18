#!/bin/bash
# Script per configurare Nginx per M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

print_message "Configurazione di Nginx..."

# Parametri
DOMAIN=${1:-"m4bot.it"}
EMAIL=${2:-"info@m4bot.it"}
PORT=${3:-"8000"}

# Crea il file di configurazione
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

# Abilita il sito
ln -sf /etc/nginx/sites-available/m4bot.conf /etc/nginx/sites-enabled/

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

# Configurazione SSL se richiesto
if [ "$4" == "--ssl" ]; then
    print_message "Configurazione SSL con Certbot..."
    
    # Installa certbot se non Ã¨ installato
    if ! command -v certbot &> /dev/null; then
        print_message "Installazione di Certbot..."
        apt-get update
        apt-get install -y certbot python3-certbot-nginx
    fi
    
    # Ottieni il certificato SSL
    certbot --nginx -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos --email $EMAIL
    
    if [ $? -ne 0 ]; then
        print_error "Impossibile configurare SSL con Certbot" 0
    else
        print_success "SSL configurato correttamente per $DOMAIN"
    fi
fi

print_message "Puoi accedere a M4Bot all'indirizzo: http://$DOMAIN"
if [ "$4" == "--ssl" ]; then
    print_message "o in modo sicuro all'indirizzo: https://$DOMAIN"
fi 