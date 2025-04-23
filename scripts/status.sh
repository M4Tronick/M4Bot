#!/bin/bash
# Script per controllare lo stato dei servizi M4Bot

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzioni di utilità
print_message() {
    echo -e "${BLUE}[M4Bot]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERRORE]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESSO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[AVVISO]${NC} $1"
}

# Verifica che il sistema sia Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    print_error "Questo script è progettato per essere eseguito su Linux."
    exit 1
fi

print_message "Controllo dello stato dei servizi M4Bot..."

# Verifica se systemctl è disponibile
if ! command -v systemctl &> /dev/null; then
    print_warning "systemctl non è disponibile su questo sistema. Impossibile verificare lo stato dei servizi."
    exit 1
fi

# Funzione per controllare un servizio
check_service() {
    local service_name="$1"
    local display_name="$2"
    
    if systemctl is-active --quiet "$service_name"; then
        print_success "$display_name: ATTIVO"
        return 0
    else
        print_error "$display_name: NON ATTIVO"
        return 1
    fi
}

# Controlla PostgreSQL
check_service "postgresql" "PostgreSQL"

# Controlla Redis
check_service "redis-server" "Redis"

# Controlla Nginx
check_service "nginx" "Nginx"

# Controlla il servizio web M4Bot
check_service "m4bot-web.service" "M4Bot Web"

# Controlla il servizio bot M4Bot
check_service "m4bot-bot.service" "M4Bot Bot"

# Controlla il servizio di monitoraggio M4Bot
check_service "m4bot-monitor.service" "M4Bot Monitor"

# Controlla lo spazio su disco
print_message "Spazio su disco:"
if command -v df &> /dev/null; then
    df -h / | grep -v "Filesystem"
    
    # Controlla se lo spazio su disco è critico - in modo più robusto
    if df -h / &> /dev/null; then
        # Ottiene la percentuale di utilizzo rimuovendo il simbolo %
        DISK_INFO=$(df -h / | grep -v "Filesystem")
        if [ -n "$DISK_INFO" ]; then
            # Estraggo la percentuale di utilizzo (quinta colonna) e rimuovo il simbolo %
            DISK_USAGE=$(echo "$DISK_INFO" | awk '{print $5}' | tr -d '%')
            if [[ "$DISK_USAGE" =~ ^[0-9]+$ ]]; then
                if [ "$DISK_USAGE" -gt 90 ]; then
                    print_error "Spazio su disco critico! Utilizzo: ${DISK_USAGE}%"
                elif [ "$DISK_USAGE" -gt 75 ]; then
                    print_warning "Spazio su disco alto! Utilizzo: ${DISK_USAGE}%"
                fi
            else
                print_warning "Impossibile interpretare la percentuale di utilizzo del disco"
            fi
        fi
    fi
else
    print_warning "Comando df non disponibile"
fi

# Controlla l'utilizzo delle risorse
echo ""
print_message "Utilizzo delle risorse:"
echo "- CPU e Memoria per i processi di M4Bot:"
if command -v ps &> /dev/null; then
    ps aux | grep -E "m4bot.py|app.py" | grep -v grep
else
    print_warning "Comando ps non disponibile"
fi

# Controlla l'utilizzo della memoria
if command -v free &> /dev/null; then
    echo ""
    print_message "Utilizzo memoria:"
    free -m | head -n 2
else
    print_warning "Comando free non disponibile"
fi

# Controlla i log recenti
echo ""
print_message "Ultimi log del bot:"
if command -v journalctl &> /dev/null; then
    journalctl -u m4bot-bot.service -n 5 --no-pager
else
    print_warning "journalctl non disponibile, impossibile visualizzare i log"
fi

echo ""
print_message "Ultimi log del web:"
if command -v journalctl &> /dev/null; then
    journalctl -u m4bot-web.service -n 5 --no-pager
else
    print_warning "journalctl non disponibile, impossibile visualizzare i log"
fi

# Verifica connessione database
echo ""
print_message "Controllo connessione database:"
if command -v pg_isready &> /dev/null; then
    if pg_isready -q; then
        print_success "Connessione al database PostgreSQL: OK"
    else
        print_error "Connessione al database PostgreSQL: FALLITA"
    fi
else
    print_warning "pg_isready non disponibile, impossibile verificare lo stato del database"
fi

# Verifica connessione Redis
echo ""
print_message "Controllo connessione Redis:"
if command -v redis-cli &> /dev/null; then
    if redis-cli ping 2>/dev/null | grep -q "PONG"; then
        print_success "Connessione a Redis: OK"
    else
        print_error "Connessione a Redis: FALLITA"
    fi
else
    print_warning "redis-cli non disponibile, impossibile verificare lo stato di Redis"
fi

# Riepilogo
echo ""
active_services=0
total_services=6  # Postgresql, Redis, Nginx, Web, Bot, Monitor

check_service "postgresql" > /dev/null && ((active_services++))
check_service "redis-server" > /dev/null && ((active_services++))
check_service "nginx" > /dev/null && ((active_services++))
check_service "m4bot-web.service" > /dev/null && ((active_services++))
check_service "m4bot-bot.service" > /dev/null && ((active_services++))
check_service "m4bot-monitor.service" > /dev/null && ((active_services++))

if [ $active_services -eq $total_services ]; then
    print_success "Tutti i servizi sono attivi ($active_services/$total_services)"
else
    print_error "Alcuni servizi non sono attivi ($active_services/$total_services)"
    print_message "Per avviare tutti i servizi, esegui: sudo ./scripts/start.sh"
fi