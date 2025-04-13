#!/bin/bash
# Script per fermare M4Bot

# Carica le funzioni comuni
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Verificare che lo script sia eseguito come root
check_root

print_message "Arresto di M4Bot..."

# Controlla se i servizi sono in esecuzione
if ! is_service_active "m4bot-bot.service" && ! is_service_active "m4bot-web.service"; then
    print_warning "I servizi M4Bot non sono in esecuzione"
    exit 0
fi

# Chiedi conferma prima di continuare
read -p "Sei sicuro di voler fermare M4Bot? (s/n): " confirm_stop
if [ "$confirm_stop" != "s" ]; then
    print_message "Operazione annullata"
    exit 0
fi

# Ferma i servizi
print_step "Arresto del servizio web..."
systemctl stop m4bot-web.service
if ! is_service_active "m4bot-web.service"; then
    print_success "Servizio web fermato con successo"
else
    print_error "Impossibile fermare il servizio web"
fi

print_step "Arresto del servizio bot..."
systemctl stop m4bot-bot.service
if ! is_service_active "m4bot-bot.service"; then
    print_success "Servizio bot fermato con successo"
else
    print_error "Impossibile fermare il servizio bot"
fi

# Verifica finale
if ! is_service_active "m4bot-bot.service" && ! is_service_active "m4bot-web.service"; then
    print_success "M4Bot è stato fermato completamente"
else
    print_warning "Alcuni servizi potrebbero essere ancora in esecuzione"
    systemctl status m4bot-bot.service --no-pager
    systemctl status m4bot-web.service --no-pager
fi

print_info "Puoi avviare M4Bot con: m4bot-start"
