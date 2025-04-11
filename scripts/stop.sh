#!/bin/bash
# Script per fermare M4Bot

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

print_message "Arresto di M4Bot..."

# Controlla se l'utente è root
if [ "$(id -u)" != "0" ]; then
   print_error "Questo script deve essere eseguito come root" 
   exit 1
fi

# Arresto dei servizi
if systemctl is-active --quiet m4bot-bot.service; then
    systemctl stop m4bot-bot.service
    if [ $? -eq 0 ]; then
        print_success "Bot arrestato con successo"
    else
        print_error "Impossibile arrestare il bot"
    fi
else
    print_warning "Il servizio bot non è in esecuzione"
fi

if systemctl is-active --quiet m4bot-web.service; then
    systemctl stop m4bot-web.service
    if [ $? -eq 0 ]; then
        print_success "Web app arrestata con successo"
    else
        print_error "Impossibile arrestare la web app"
    fi
else
    print_warning "Il servizio web non è in esecuzione"
fi

print_message "Tutti i servizi di M4Bot sono stati arrestati"
print_message "Per avviare M4Bot, esegui: m4bot-start"
