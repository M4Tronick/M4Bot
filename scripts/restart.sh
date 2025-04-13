#!/bin/bash
# Script per riavviare M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

print_message "Riavvio di M4Bot..."

# Ferma i servizi
print_message "Arresto dei servizi in corso..."
systemctl stop m4bot-bot.service
if [ $? -eq 0 ]; then
    print_success "Bot arrestato con successo"
else
    print_warning "Impossibile arrestare il bot, potrebbe non essere in esecuzione"
fi

systemctl stop m4bot-web.service
if [ $? -eq 0 ]; then
    print_success "Web app arrestata con successo"
else
    print_warning "Impossibile arrestare la web app, potrebbe non essere in esecuzione"
fi

# Breve pausa
sleep 2

# Avvia i servizi
print_message "Avvio dei servizi in corso..."
systemctl start m4bot-bot.service
if [ $? -eq 0 ]; then
    print_success "Bot avviato con successo"
else
    print_error "Impossibile avviare il bot" 1
fi

systemctl start m4bot-web.service
if [ $? -eq 0 ]; then
    print_success "Web app avviata con successo"
else
    print_error "Impossibile avviare la web app" 1
fi

# Controlla i servizi
check_services

print_message "M4Bot è stato riavviato con successo"
print_message "M4Bot è ora disponibile all'indirizzo https://m4bot.it" 