#!/bin/bash
# Script per riavviare i servizi di M4Bot

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

print_message "Riavvio dei servizi di M4Bot..."

# Percorsi agli script di start e stop
SCRIPT_DIR="$(dirname "$0")"
STOP_SCRIPT="$SCRIPT_DIR/stop.sh"
START_SCRIPT="$SCRIPT_DIR/start.sh"

# Verifica che gli script esistano
if [ ! -f "$STOP_SCRIPT" ]; then
    print_error "Script di arresto non trovato: $STOP_SCRIPT" 1
fi

if [ ! -f "$START_SCRIPT" ]; then
    print_error "Script di avvio non trovato: $START_SCRIPT" 1
fi

# Assicurati che gli script siano eseguibili
chmod +x "$STOP_SCRIPT" 2>/dev/null
chmod +x "$START_SCRIPT" 2>/dev/null

# Funzione per riavviare un servizio
restart_service() {
    local service_name="$1"
    local display_name="$2"
    
    print_message "Riavvio di $display_name..."
    
    # Verifica se il servizio esiste
    if ! systemctl list-unit-files | grep -q "$service_name"; then
        print_warning "Il servizio $display_name non esiste nel sistema"
        return 2
    fi
    
    # Arresta il servizio
    systemctl stop "$service_name"
    sleep 1
    
    # Avvia il servizio
    systemctl start "$service_name"
    
    if [ $? -eq 0 ]; then
        systemctl is-active --quiet "$service_name"
        if [ $? -eq 0 ]; then
            print_success "$display_name riavviato con successo"
            return 0
        else
            print_error "Impossibile avviare $display_name dopo l'arresto" 0
            return 1
        fi
    else
        print_error "Errore durante l'avvio di $display_name dopo l'arresto" 0
        return 1
    fi
}

# Arresta i servizi
print_message "Arresto dei servizi in corso..."
$STOP_SCRIPT

# Breve pausa per assicurarsi che tutti i servizi si fermino
sleep 3

# Avvia i servizi
print_message "Avvio dei servizi in corso..."
$START_SCRIPT

print_message "Riavvio completato"

# Verifica che tutti i servizi siano in esecuzione
print_message "Verifica dello stato dei servizi..."
if systemctl is-active --quiet m4bot-bot.service && 
   systemctl is-active --quiet m4bot-web.service && 
   systemctl is-active --quiet m4bot-monitor.service; then
    print_success "Tutti i servizi di M4Bot sono in esecuzione"
    
    # Se è disponibile il dominio, mostra l'URL
    if [ -n "$DOMAIN" ]; then
        if [ "$USE_SSL" = "true" ]; then
            print_message "M4Bot è ora disponibile all'indirizzo https://$DOMAIN"
        else
            print_message "M4Bot è ora disponibile all'indirizzo http://$DOMAIN"
        fi
    else
        # Determina l'IP del server
        server_ip=$(hostname -I | awk '{print $1}')
        if [ -n "$server_ip" ]; then
            print_message "M4Bot è ora disponibile all'indirizzo http://$server_ip"
        fi
    fi
else
    print_error "Alcuni servizi di M4Bot non sono stati avviati correttamente"
    print_message "Esegui './scripts/status.sh' per verificare lo stato dei servizi"
fi

exit 0 