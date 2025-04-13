#!/bin/bash
# Script con funzioni comuni per la gestione di M4Bot

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzioni di utilità
check_root() {
    if [ "$(id -u)" != "0" ]; then
        echo -e "${RED}Errore: Questo script deve essere eseguito come root${NC}"
        exit 1
    fi
}

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

check_postgres() {
    if ! systemctl is-active --quiet postgresql; then
        print_warning "PostgreSQL non è in esecuzione, tentativo di avvio..."
        systemctl start postgresql
        if [ $? -eq 0 ]; then
            print_success "PostgreSQL avviato con successo"
        else
            print_error "Impossibile avviare PostgreSQL" 1
        fi
    else
        print_success "PostgreSQL è in esecuzione"
    fi
}

check_nginx() {
    if ! systemctl is-active --quiet nginx; then
        print_warning "Nginx non è in esecuzione, tentativo di avvio..."
        systemctl start nginx
        if [ $? -eq 0 ]; then
            print_success "Nginx avviato con successo"
        else
            print_error "Impossibile avviare Nginx" 1
        fi
    else
        print_success "Nginx è in esecuzione"
    fi
}

check_services() {
    print_message "Controllo dei servizi..."
    
    # Controlla PostgreSQL
    check_postgres
    
    # Controlla Nginx
    check_nginx
    
    print_message "Stato dei servizi:"
    systemctl status m4bot-bot.service --no-pager | grep Active
    systemctl status m4bot-web.service --no-pager | grep Active
    systemctl status nginx --no-pager | grep Active
    systemctl status postgresql --no-pager | grep Active
}

# Funzione per creare uno script wrapper nel sistema
create_wrapper() {
    local script_name=$1
    local destination="/usr/local/bin/$script_name"
    
    cat > "$destination" << EOF
#!/bin/bash
# Script wrapper per $script_name

# Imposta il percorso degli script
SCRIPT_DIR="/root/M4Bot/scripts"

# Verifica che esista la directory degli script
if [ ! -d "\$SCRIPT_DIR" ]; then
    echo "Errore: Directory degli script non trovata: \$SCRIPT_DIR"
    exit 1
fi

# Verifica che esista lo script common.sh
if [ ! -f "\$SCRIPT_DIR/common.sh" ]; then
    echo "Errore: File common.sh non trovato in \$SCRIPT_DIR"
    exit 1
fi

# Esegui lo script corrispondente
\$SCRIPT_DIR/$script_name.sh \$@
EOF

    chmod +x "$destination"
    print_success "Script wrapper creato: $destination"
}

# Funzione per installare tutti gli script wrapper
install_wrappers() {
    print_message "Installazione degli script wrapper nel sistema..."
    
    create_wrapper "m4bot-start"
    create_wrapper "m4bot-stop"
    create_wrapper "m4bot-status"
    create_wrapper "m4bot-restart"
    
    print_success "Tutti gli script wrapper sono stati installati"
} 