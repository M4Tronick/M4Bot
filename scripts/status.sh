#!/bin/bash
# Script per controllare lo stato di M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

print_message "Controllo dello stato di M4Bot..."

# Controllo dello stato dei servizi
print_message "Servizio Bot:"
systemctl status m4bot-bot.service --no-pager

echo ""
print_message "Servizio Web:"
systemctl status m4bot-web.service --no-pager

echo ""
print_message "Servizio Nginx:"
systemctl status nginx --no-pager | grep Active

echo ""
print_message "Servizio PostgreSQL:"
systemctl status postgresql --no-pager | grep Active

# Verifica se i servizi sono attivi
if systemctl is-active --quiet m4bot-bot.service && systemctl is-active --quiet m4bot-web.service && systemctl is-active --quiet nginx && systemctl is-active --quiet postgresql; then
    echo ""
    print_success "Tutti i servizi di M4Bot sono attivi e funzionanti"
    echo ""
    print_message "M4Bot è disponibile all'indirizzo https://m4bot.it"
else
    echo ""
    print_error "Uno o più servizi di M4Bot non sono attivi"
    echo ""
    print_message "Per avviare tutti i servizi, esegui: m4bot-start"
fi

# Controlla l'utilizzo delle risorse
echo ""
print_message "Utilizzo delle risorse:"
echo "- CPU e Memoria per i processi di M4Bot:"
ps aux | grep -E "m4bot.py|app.py" | grep -v grep

echo ""
print_message "Spazio su disco:"
df -h | grep -E '(Filesystem|/$)'

echo ""
print_message "Ultimi log del bot:"
journalctl -u m4bot-bot.service -n 10 --no-pager

echo ""
print_message "Ultimi log del web:"
journalctl -u m4bot-web.service -n 10 --no-pager