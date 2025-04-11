#!/bin/bash
# Script per avviare M4Bot

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

print_message "Avvio di M4Bot..."

# Controlla se l'utente è root
if [ "$(id -u)" != "0" ]; then
   print_error "Questo script deve essere eseguito come root" 
   exit 1
fi

# Controllo se i servizi sono già in esecuzione
if systemctl is-active --quiet m4bot-bot.service; then
    print_warning "Il servizio bot è già in esecuzione"
else
    systemctl start m4bot-bot.service
    if [ $? -eq 0 ]; then
        print_success "Bot avviato con successo"
    else
        print_error "Impossibile avviare il bot"
    fi
fi

if systemctl is-active --quiet m4bot-web.service; then
    print_warning "Il servizio web è già in esecuzione"
else
    systemctl start m4bot-web.service
    if [ $? -eq 0 ]; then
        print_success "Web app avviata con successo"
    else
        print_error "Impossibile avviare la web app"
    fi
fi

# Verifica che Nginx sia in esecuzione
if systemctl is-active --quiet nginx; then
    print_success "Nginx è in esecuzione"
else
    print_warning "Nginx non è in esecuzione, tentativo di avvio..."
    systemctl start nginx
    if [ $? -eq 0 ]; then
        print_success "Nginx avviato con successo"
    else
        print_error "Impossibile avviare Nginx"
    fi
fi

# Verifica che PostgreSQL sia in esecuzione
if systemctl is-active --quiet postgresql; then
    print_success "PostgreSQL è in esecuzione"
else
    print_warning "PostgreSQL non è in esecuzione, tentativo di avvio..."
    systemctl start postgresql
    if [ $? -eq 0 ]; then
        print_success "PostgreSQL avviato con successo"
    else
        print_error "Impossibile avviare PostgreSQL"
    fi
fi

print_message "Stato dei servizi:"
systemctl status m4bot-bot.service --no-pager | grep Active
systemctl status m4bot-web.service --no-pager | grep Active
systemctl status nginx --no-pager | grep Active
systemctl status postgresql --no-pager | grep Active

print_message "M4Bot è ora disponibile all'indirizzo https://m4bot.it"
print_message "Per fermare M4Bot, esegui: m4bot-stop"
