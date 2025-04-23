#!/bin/bash
# Script per avviare i servizi di M4Bot

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

print_message "Avvio dei servizi di M4Bot..."

# Funzione per avviare servizio
start_service() {
    local service_name="$1"
    local display_name="$2"
    
    print_message "Avvio di $display_name..."
    
    # Verifica se il servizio esiste
    if ! systemctl list-unit-files | grep -q "$service_name"; then
        print_warning "Il servizio $display_name non esiste nel sistema"
        return 2
    fi
    
    if systemctl is-active --quiet "$service_name"; then
        print_warning "$display_name è già in esecuzione"
        return 0
    fi
    
    systemctl start "$service_name"
    
    if [ $? -eq 0 ]; then
        systemctl is-active --quiet "$service_name"
        if [ $? -eq 0 ]; then
            print_success "$display_name avviato con successo"
            return 0
        else
            print_error "Impossibile avviare $display_name" 0
            return 1
        fi
    else
        print_error "Errore durante l'avvio di $display_name" 0
        return 1
    fi
}

# Verifica se la directory dei log esiste
if [ ! -d "$INSTALL_DIR/logs" ]; then
    print_warning "La directory dei log non esiste, creazione in corso..."
    mkdir -p "$INSTALL_DIR/logs"
    if [ $? -eq 0 ]; then
        # Imposta permessi
        chown -R m4bot:m4bot "$INSTALL_DIR/logs" 2>/dev/null || true
        chmod 755 "$INSTALL_DIR/logs"
        print_success "Directory dei log creata"
    else
        print_error "Impossibile creare la directory dei log"
    fi
fi

# Avvia PostgreSQL
start_service "postgresql" "PostgreSQL"
pg_status=$?

# Avvia Redis
start_service "redis-server" "Redis"
redis_status=$?

# Avvia Nginx
start_service "nginx" "Nginx"
nginx_status=$?

# Attendi che i servizi di database siano pronti
if [ $pg_status -eq 0 ]; then
    if command -v pg_isready &> /dev/null; then
        print_message "Attesa che PostgreSQL sia pronto..."
        counter=0
        while ! pg_isready -q 2>/dev/null && [ $counter -lt 10 ]; do
            sleep 1
            ((counter++))
        done
        
        if pg_isready -q 2>/dev/null; then
            print_success "PostgreSQL è pronto"
        else
            print_warning "Timeout mentre si attendeva PostgreSQL"
        fi
    else
        print_warning "pg_isready non disponibile, impossibile verificare lo stato di PostgreSQL"
    fi
fi

# Verifica connessione Redis
if [ $redis_status -eq 0 ]; then
    if command -v redis-cli &> /dev/null; then
        print_message "Verifica connessione Redis..."
        counter=0
        redis_ready=false
        
        while [ $counter -lt 5 ] && [ "$redis_ready" = "false" ]; do
            if redis-cli ping 2>/dev/null | grep -q "PONG"; then
                redis_ready=true
                print_success "Redis è pronto"
            else
                sleep 1
                ((counter++))
            fi
        done
        
        if [ "$redis_ready" = "false" ]; then
            print_warning "Redis non risponde correttamente"
        fi
    else
        print_warning "redis-cli non disponibile, impossibile verificare lo stato di Redis"
    fi
fi

# Avvia i servizi M4Bot
if [ $pg_status -eq 0 ] && [ $redis_status -eq 0 ]; then
    # Avvia il bot
    start_service "m4bot-bot.service" "M4Bot Bot"
    bot_status=$?
    
    # Avvia il web
    start_service "m4bot-web.service" "M4Bot Web"
    web_status=$?
    
    # Avvia il monitor
    start_service "m4bot-monitor.service" "M4Bot Monitor"
    monitor_status=$?
else
    print_error "I servizi database o cache non sono attivi. M4Bot non può essere avviato."
    exit 1
fi

# Verifica tutti i servizi sono stati avviati correttamente
if [ $pg_status -eq 0 ] && [ $redis_status -eq 0 ] && [ $nginx_status -eq 0 ] && 
   [ $bot_status -eq 0 ] && [ $web_status -eq 0 ] && [ $monitor_status -eq 0 ]; then
    print_success "Tutti i servizi di M4Bot sono stati avviati con successo"
    
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