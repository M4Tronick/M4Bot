#!/bin/bash
# Script per avviare M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

print_message "Avvio di M4Bot..."

# Verifica che PostgreSQL e Nginx siano in esecuzione
check_services

# Controllo se i servizi sono già in esecuzione
if systemctl is-active --quiet m4bot-bot.service; then
    print_warning "Il servizio bot è già in esecuzione"
else
    systemctl start m4bot-bot.service
    if [ $? -eq 0 ]; then
        print_success "Bot avviato con successo"
    else
        print_error "Impossibile avviare il bot" 1
    fi
fi

if systemctl is-active --quiet m4bot-web.service; then
    print_warning "Il servizio web è già in esecuzione"
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

print_message "M4Bot è ora disponibile all'indirizzo https://m4bot.it"
print_message "Per fermare M4Bot, esegui: m4bot-stop"
