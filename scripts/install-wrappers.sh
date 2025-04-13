#!/bin/bash
# Script per installare i wrapper di M4Bot nel sistema

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica privilegi root
check_root

print_message "Installazione dei wrapper di M4Bot..."

# Installa i wrapper
install_wrappers

print_success "Installazione completata"
print_message "Ora puoi utilizzare i seguenti comandi:"
print_message "- m4bot-start:   Avvia il bot e i servizi correlati"
print_message "- m4bot-stop:    Ferma il bot e i servizi correlati"
print_message "- m4bot-status:  Mostra lo stato del bot e dei servizi"
print_message "- m4bot-restart: Riavvia il bot e i servizi correlati" 