#!/bin/bash
# Script per fermare i servizi di M4Bot

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directory installazione
INSTALL_DIR=${INSTALL_DIR:-"/opt/m4bot"}

# Carica configurazioni se esiste
CONFIG_FILE="$INSTALL_DIR/.env"
if [ -f "$CONFIG_FILE" ]; then
    source "$CONFIG_FILE"
fi

# Funzioni di utilità
print_message() {
    echo -e "${BLUE}[M4Bot]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERRORE]${NC} $1"
    if [ -n "$2" ]; then
        exit $2
    fi
}

print_success() {
    echo -e "${GREEN}[SUCCESSO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[AVVISO]${NC} $1"
}

# Verifica che il sistema sia Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    print_error "Questo script è progettato per essere eseguito su Linux." 1
fi

# Verifica che sia eseguito come root
if [ "$(id -u)" != "0" ]; then
    print_error "Questo script deve essere eseguito come root (usa sudo)" 1
fi

# Verifica se systemctl è disponibile
if ! command -v systemctl &> /dev/null; then
    print_error "systemctl non è disponibile su questo sistema. Impossibile gestire i servizi." 1
fi

print_message "Arresto dei servizi di M4Bot..."

# Funzione per arrestare un servizio
stop_service() {
    local service_name="$1"
    local display_name="$2"
    
    print_message "Arresto di $display_name..."
    
    # Verifica se il servizio esiste
    if ! systemctl list-unit-files | grep -q "$service_name"; then
        print_warning "Il servizio $display_name non esiste nel sistema"
        return 0
    fi
    
    if ! systemctl is-active --quiet "$service_name"; then
        print_warning "$display_name non è in esecuzione"
        return 0
    fi
    
    systemctl stop "$service_name"
    
    if [ $? -eq 0 ]; then
        # Verifica che il servizio sia effettivamente fermato
        if ! systemctl is-active --quiet "$service_name"; then
            print_success "$display_name arrestato con successo"
            return 0
        else
            print_error "Impossibile arrestare $display_name" 0
            return 1
        fi
    else
        print_error "Errore durante l'arresto di $display_name" 0
        return 1
    fi
}

# Arresto dei servizi in ordine inverso
# Prima i servizi M4Bot, poi i servizi di sistema

# Arresto del servizio di monitoraggio
stop_service "m4bot-monitor.service" "M4Bot Monitor"
monitor_status=$?

# Arresto del servizio web
stop_service "m4bot-web.service" "M4Bot Web"
web_status=$?

# Arresto del servizio bot
stop_service "m4bot-bot.service" "M4Bot Bot"
bot_status=$?

# Riepilogo dell'arresto
if [ $monitor_status -eq 0 ] && [ $web_status -eq 0 ] && [ $bot_status -eq 0 ]; then
    print_success "Tutti i servizi di M4Bot sono stati arrestati con successo"
    print_message "Per avviare i servizi di M4Bot, esegui: sudo ./scripts/start.sh"
else
    print_error "Alcuni servizi di M4Bot non sono stati arrestati correttamente"
    print_message "Esegui './scripts/status.sh' per verificare lo stato dei servizi"
fi

exit 0