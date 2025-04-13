#!/bin/bash
# Script per avviare M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

print_message "Avvio di M4Bot..."

# Verifica che la directory dei log esista
if [ ! -d "/opt/m4bot/bot/logs" ]; then
    print_warning "La directory dei log non esiste, creazione in corso..."
    mkdir -p /opt/m4bot/bot/logs
    chown -R m4bot:m4bot /opt/m4bot/bot/logs 2>/dev/null || true
    chmod -R 755 /opt/m4bot/bot/logs
    print_success "Directory dei log creata"
fi

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
