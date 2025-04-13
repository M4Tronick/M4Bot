#!/bin/bash
# Script per fermare M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

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
    print_warning "Il servizio bot non è in esecuzione"
fi

if systemctl is-active --quiet m4bot-web.service; then
    systemctl stop m4bot-web.service
    if [ $? -eq 0 ]; then
        print_success "Web app arrestata con successo"
    else
        print_error "Impossibile arrestare la web app" 1
    fi
else
    print_warning "Il servizio web non è in esecuzione"
fi

print_message "Tutti i servizi di M4Bot sono stati arrestati"
print_message "Per avviare M4Bot, esegui: m4bot-start"
