#!/bin/bash
# Script per aggiungere sottodomini alla configurazione di M4Bot

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzioni di utilità
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

# Verifica i prerequisiti
check_prerequisites() {
    print_message "Verificando i prerequisiti..."
    
    # Verifica se Nginx è installato
    if ! command -v nginx &> /dev/null; then
        print_error "Nginx non è installato" 1
    fi
    
    # Verifica se Certbot è installato
    if ! command -v certbot &> /dev/null; then
        print_error "Certbot non è installato" 1
    fi
    
    # Verifica se il file di configurazione di M4Bot esiste
    if [ ! -f "/etc/nginx/sites-available/m4bot" ]; then
        print_error "File di configurazione Nginx per M4Bot non trovato" 1
    fi
    
    print_success "Prerequisiti verificati"
}

# Funzione principale
main() {
    check_root
    check_prerequisites
    
    print_message "====================================================="
    print_message "AGGIUNTA SOTTODOMINI PER M4BOT"
    print_message "====================================================="
    
    # Ottieni il dominio principale
    read -p "Inserisci il dominio principale (es. m4bot.it): " MAIN_DOMAIN
    if [ -z "$MAIN_DOMAIN" ]; then
        print_error "Il dominio principale è obbligatorio" 1
    fi
    
    # Email per Let's Encrypt
    read -p "Inserisci un indirizzo email per le notifiche di Let's Encrypt: " EMAIL
    if [ -z "$EMAIL" ]; then
        EMAIL="admin@$MAIN_DOMAIN"
        print_warning "Nessun email inserito, utilizzo l'email predefinita: $EMAIL"
    fi
    
    # Prepara i sottodomini
    DASHBOARD_DOMAIN="dashboard.$MAIN_DOMAIN"
    CONTROL_DOMAIN="control.$MAIN_DOMAIN"
    
    print_message "Aggiunta dei sottodomini: $DASHBOARD_DOMAIN e $CONTROL_DOMAIN"
    
    # Backup della configurazione Nginx originale
    cp /etc/nginx/sites-available/m4bot /etc/nginx/sites-available/m4bot.backup
    print_message "Backup creato: /etc/nginx/sites-available/m4bot.backup"
    
    # Modifica configurazione Nginx per includere i sottodomini
    sed -i "s/server_name $MAIN_DOMAIN www.$MAIN_DOMAIN;/server_name $MAIN_DOMAIN www.$MAIN_DOMAIN $DASHBOARD_DOMAIN $CONTROL_DOMAIN;/" /etc/nginx/sites-available/m4bot
    
    # Testa la configurazione Nginx
    nginx -t
    if [ $? -ne 0 ]; then
        print_error "Configurazione Nginx non valida, ripristino dal backup" 0
        cp /etc/nginx/sites-available/m4bot.backup /etc/nginx/sites-available/m4bot
        nginx -t || print_error "Impossibile ripristinare la configurazione" 1
        exit 1
    fi
    
    # Riavvia Nginx
    systemctl restart nginx
    if [ $? -ne 0 ]; then
        print_error "Impossibile riavviare Nginx, ripristino dal backup" 0
        cp /etc/nginx/sites-available/m4bot.backup /etc/nginx/sites-available/m4bot
        nginx -t && systemctl restart nginx || print_error "Impossibile ripristinare la configurazione" 1
        exit 1
    fi
    
    print_success "Configurazione Nginx aggiornata"
    
    # Aggiorna il certificato SSL per includere i sottodomini
    print_message "Aggiornamento del certificato SSL..."
    
    certbot --nginx -d $MAIN_DOMAIN -d www.$MAIN_DOMAIN -d $DASHBOARD_DOMAIN -d $CONTROL_DOMAIN --non-interactive --agree-tos --email $EMAIL
    
    if [ $? -ne 0 ]; then
        print_error "Impossibile aggiornare il certificato SSL" 0
        print_message "Puoi provare ad aggiornarlo manualmente con il comando:"
        print_message "certbot --nginx -d $MAIN_DOMAIN -d www.$MAIN_DOMAIN -d $DASHBOARD_DOMAIN -d $CONTROL_DOMAIN"
    else
        print_success "Certificato SSL aggiornato per includere i sottodomini"
    fi
    
    print_message "====================================================="
    print_message "SOTTODOMINI AGGIUNTI CON SUCCESSO"
    print_message "====================================================="
    print_message "Dominio principale: $MAIN_DOMAIN"
    print_message "Dashboard: $DASHBOARD_DOMAIN"
    print_message "Control Panel: $CONTROL_DOMAIN"
    print_message "====================================================="
    print_message "Ora puoi accedere ai sottodomini tramite HTTPS:"
    print_message "https://$DASHBOARD_DOMAIN"
    print_message "https://$CONTROL_DOMAIN"
    print_message "====================================================="
}

# Esecuzione dello script
main 