#!/bin/bash
# Script per avviare M4Bot

# Carica le funzioni comuni
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# Verificare che lo script sia eseguito come root
check_root

print_message "Avvio di M4Bot..."

# Verifica che PostgreSQL sia in esecuzione
check_postgres || {
    print_error "Impossibile continuare senza PostgreSQL"
    exit 1
}

# Controlla lo stato attuale dei servizi
if is_service_active "m4bot-bot.service" && is_service_active "m4bot-web.service"; then
    print_warning "I servizi M4Bot sono già in esecuzione"
    read -p "Vuoi riavviarli? (s/n): " restart_choice
    if [ "$restart_choice" = "s" ]; then
        restart_services
        exit $?
    else
        print_message "Operazione annullata"
        exit 0
    fi
fi

# Avvio dei servizi
print_step "Avvio del servizio bot..."
systemctl start m4bot-bot.service
check_service_status "m4bot-bot.service" || {
    print_error "Errore durante l'avvio del servizio bot"
    exit 1
}

print_step "Avvio del servizio web..."
systemctl start m4bot-web.service
check_service_status "m4bot-web.service" || {
    print_error "Errore durante l'avvio del servizio web"
    systemctl stop m4bot-bot.service
    print_warning "Il servizio bot è stato fermato per coerenza"
    exit 1
}

print_success "M4Bot avviato con successo!"

# Mostra informazioni utili
print_info "Puoi controllare lo stato con: m4bot-status"
print_info "Puoi fermare i servizi con: m4bot-stop"

# Mostra i log (ultime 5 righe)
print_step "Ultime righe dai log:"
echo -e "${CYAN}=== Log del bot ===${NC}"
tail -n 5 "$LOGS_DIR/bot.log" 2>/dev/null || echo "Nessun log disponibile"
echo
echo -e "${CYAN}=== Log dell'applicazione web ===${NC}"
tail -n 5 "$LOGS_DIR/web.log" 2>/dev/null || echo "Nessun log disponibile"
