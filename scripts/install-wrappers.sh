#!/bin/bash
# Script per installare i wrapper di M4Bot nel sistema

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica privilegi root
check_root

print_message "Installazione dei wrapper di M4Bot..."

# Copia il file common.sh in /usr/local/bin/
print_message "Copiando common.sh in /usr/local/bin/..."
cp "$(dirname "$0")/common.sh" /usr/local/bin/
chmod +x /usr/local/bin/common.sh
print_success "File common.sh copiato con successo"

# Crea la directory per i log se non esiste
print_message "Controllo e creazione della directory per i log..."
mkdir -p /opt/m4bot/bot/logs
if [ -d "/opt/m4bot/bot" ]; then
    chown -R m4bot:m4bot /opt/m4bot/bot/logs 2>/dev/null || true
    chmod -R 755 /opt/m4bot/bot/logs
    print_success "Directory dei log creata/verificata"
else
    print_warning "La directory /opt/m4bot/bot non esiste. Assicurati che sia creata durante l'installazione."
fi

# Installa i wrapper
install_wrappers

print_success "Installazione completata"
print_message "Ora puoi utilizzare i seguenti comandi:"
print_message "- m4bot-start:   Avvia il bot e i servizi correlati"
print_message "- m4bot-stop:    Ferma il bot e i servizi correlati"
print_message "- m4bot-status:  Mostra lo stato del bot e dei servizi"
print_message "- m4bot-restart: Riavvia il bot e i servizi correlati" 