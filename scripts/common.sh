#!/bin/bash
# Funzioni e variabili comuni per gli script di M4Bot

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Directory di installazione
INSTALL_DIR="/opt/m4bot"
WEB_DIR="${INSTALL_DIR}/web"
BOT_DIR="${INSTALL_DIR}/bot"
LOGS_DIR="${INSTALL_DIR}/logs"
DB_DIR="${INSTALL_DIR}/database"
SCRIPTS_DIR="${INSTALL_DIR}/scripts"
VENV_DIR="${INSTALL_DIR}/venv"

# Funzioni di log e output
print_message() {
    echo -e "${BLUE}[M4Bot]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERRORE]${NC} $1" >&2
}

print_success() {
    echo -e "${GREEN}[SUCCESSO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[ATTENZIONE]${NC} $1"
}

print_step() {
    echo -e "${CYAN}[PASSO]${NC} $1"
}

print_info() {
    echo -e "${PURPLE}[INFO]${NC} $1"
}

# Funzione per verificare se un servizio è attivo
is_service_active() {
    systemctl is-active --quiet "$1"
    return $?
}

# Funzione per verificare lo stato dei servizi
check_service_status() {
    service_name="$1"
    if is_service_active "$service_name"; then
        print_success "Il servizio $service_name è attivo"
        return 0
    else
        print_error "Il servizio $service_name non è attivo"
        return 1
    fi
}

# Funzione per attivare l'ambiente virtuale
activate_venv() {
    if [ -f "$VENV_DIR/bin/activate" ]; then
        source "$VENV_DIR/bin/activate"
        print_info "Ambiente virtuale attivato"
    else
        print_error "Ambiente virtuale non trovato in $VENV_DIR"
        return 1
    fi
}

# Funzione per verificare che lo script sia eseguito come root
check_root() {
    if [ "$(id -u)" != "0" ]; then
        print_error "Questo script deve essere eseguito come root"
        exit 1
    fi
}

# Funzione per verificare se PostgreSQL è in esecuzione
check_postgres() {
    if ! systemctl is-active --quiet postgresql; then
        print_error "PostgreSQL non è in esecuzione"
        print_info "Avvio di PostgreSQL..."
        systemctl start postgresql
        if ! systemctl is-active --quiet postgresql; then
            print_error "Impossibile avviare PostgreSQL"
            return 1
        fi
    fi
    print_success "PostgreSQL è in esecuzione"
    return 0
}

# Funzione per visualizzare l'utilizzo di sistema
show_system_info() {
    print_step "Informazioni di sistema:"
    echo -e "${CYAN}CPU:${NC} $(grep 'model name' /proc/cpuinfo | head -1 | cut -d':' -f2 | xargs)"
    echo -e "${CYAN}Memoria:${NC} $(free -h | grep Mem | awk '{print $3 " usati di " $2}')"
    echo -e "${CYAN}Disco:${NC} $(df -h / | tail -1 | awk '{print $3 " usati di " $2 " (" $5 ")"}')"
    echo -e "${CYAN}Uptime:${NC} $(uptime -p)"
    
    # Mostra i processi M4Bot
    if pgrep -f "m4bot.py" > /dev/null; then
        echo -e "${CYAN}Processi M4Bot:${NC}"
        ps aux | grep -v grep | grep -E "m4bot\.py|app\.py" | awk '{print $2 "\t" $11 " " $12}'
    fi
}

# Funzione per il backup dei dati
backup_data() {
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_DIR="$INSTALL_DIR/backup"
    BACKUP_FILE="$BACKUP_DIR/m4bot_backup_$TIMESTAMP.tar.gz"
    
    mkdir -p "$BACKUP_DIR"
    
    print_step "Creazione backup in $BACKUP_FILE"
    tar -czf "$BACKUP_FILE" -C "$INSTALL_DIR" web bot database
    
    if [ $? -eq 0 ]; then
        print_success "Backup completato con successo"
        print_info "Dimensione: $(du -h "$BACKUP_FILE" | cut -f1)"
    else
        print_error "Errore durante il backup"
        return 1
    fi
}

# Funzione per riavviare i servizi
restart_services() {
    print_step "Riavvio dei servizi M4Bot"
    systemctl restart m4bot-bot.service
    systemctl restart m4bot-web.service
    
    # Verifica che i servizi siano stati riavviati correttamente
    if is_service_active "m4bot-bot.service" && is_service_active "m4bot-web.service"; then
        print_success "Servizi riavviati con successo"
        return 0
    else
        print_error "Errore durante il riavvio dei servizi"
        return 1
    fi
}

# Funzione per controllare gli aggiornamenti del repository
check_updates() {
    if [ ! -d "$INSTALL_DIR/.git" ]; then
        print_warning "Il repository git non è stato trovato"
        return 1
    fi
    
    cd "$INSTALL_DIR"
    git fetch
    
    LOCAL=$(git rev-parse @)
    REMOTE=$(git rev-parse @{u})
    
    if [ "$LOCAL" != "$REMOTE" ]; then
        print_info "Sono disponibili aggiornamenti"
        git log --oneline $LOCAL..$REMOTE
        return 0
    else
        print_success "Il sistema è aggiornato"
        return 1
    fi
} 