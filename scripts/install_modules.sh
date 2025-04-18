#!/bin/bash

# Script di installazione dei moduli avanzati per M4Bot
# Installa i moduli di sicurezza e monitoraggio

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Directory principali
INSTALL_DIR="/opt/m4bot"
MODULES_DIR="${INSTALL_DIR}/modules"
CONFIG_DIR="${INSTALL_DIR}/config"
LOG_DIR="/var/log/m4bot"

# Funzioni di utilità
print_message() {
    echo -e "${BLUE}${BOLD}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}${BOLD}[ERRORE]${NC} $1"
}

print_success() {
    echo -e "${GREEN}${BOLD}[SUCCESSO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}${BOLD}[AVVISO]${NC} $1"
}

# Verifica dipendenze
check_dependencies() {
    print_message "Controllo dipendenze per i moduli avanzati..."
    
    local DEPS=("python3" "pip3" "psutil" "requests")
    local MISSING=()
    
    # Verifica Python e pip
    if ! command -v python3 &> /dev/null; then
        MISSING+=("python3")
    fi
    
    if ! command -v pip3 &> /dev/null; then
        MISSING+=("pip3")
    fi
    
    if [ ${#MISSING[@]} -gt 0 ]; then
        print_error "Dipendenze mancanti: ${MISSING[*]}"
        print_message "Installazione dipendenze in corso..."
        
        if [ -f /etc/debian_version ]; then
            # Debian/Ubuntu
            apt-get update
            apt-get install -y python3 python3-pip python3-dev
        elif [ -f /etc/redhat-release ]; then
            # RHEL/CentOS
            yum install -y python3 python3-pip python3-devel
        else
            print_error "Sistema operativo non supportato per l'installazione automatica."
            print_message "Installa manualmente: ${MISSING[*]}"
            exit 1
        fi
    fi
    
    # Verifica pacchetti Python
    print_message "Verifica pacchetti Python..."
    pip3 install --upgrade pip
    pip3 install psutil requests
    
    print_success "Tutte le dipendenze sono soddisfatte."
}

# Creazione directory
create_directories() {
    print_message "Creazione directory necessarie..."
    
    mkdir -p "${MODULES_DIR}/monitoring"
    mkdir -p "${MODULES_DIR}/stability_security"
    mkdir -p "${CONFIG_DIR}/monitoring"
    mkdir -p "${CONFIG_DIR}/security"
    mkdir -p "${LOG_DIR}"
    
    # Imposta permessi
    chmod 755 "${MODULES_DIR}" -R
    chmod 755 "${CONFIG_DIR}" -R
    chmod 775 "${LOG_DIR}"
    
    print_success "Directory create con successo."
}

# Configurazione del modulo di monitoraggio
configure_monitoring() {
    print_message "Configurazione del modulo di monitoraggio..."
    
    # Crea file di configurazione
    local CONFIG_FILE="${CONFIG_DIR}/monitoring/config.json"
    
    # Verifica se esiste già un file di configurazione
    if [ -f "$CONFIG_FILE" ]; then
        print_warning "File di configurazione esistente trovato. Creazione di un backup..."
        cp "$CONFIG_FILE" "${CONFIG_FILE}.bak.$(date +%Y%m%d%H%M%S)"
    fi
    
    # Crea il file di configurazione
    cat > "$CONFIG_FILE" << EOF
{
    "monitoring": {
        "interval": 60,
        "cpu_threshold": 85,
        "memory_threshold": 85,
        "disk_threshold": 90,
        "network_monitor": true,
        "process_monitor": true,
        "service_checks": [
            {"name": "web", "url": "http://localhost:5000/health", "expected": "healthy"},
            {"name": "bot", "port": 9000}
        ],
        "alert_channels": {
            "telegram": true,
            "email": true,
            "web_dashboard": true
        }
    }
}
EOF
    
    print_success "Modulo di monitoraggio configurato con successo."
}

# Configurazione del modulo di sicurezza
configure_security() {
    print_message "Configurazione del modulo di sicurezza e stabilità..."
    
    # Crea file di configurazione
    local CONFIG_FILE="${CONFIG_DIR}/security/config.json"
    
    # Verifica se esiste già un file di configurazione
    if [ -f "$CONFIG_FILE" ]; then
        print_warning "File di configurazione esistente trovato. Creazione di un backup..."
        cp "$CONFIG_FILE" "${CONFIG_FILE}.bak.$(date +%Y%m%d%H%M%S)"
    fi
    
    # Crea il file di configurazione
    cat > "$CONFIG_FILE" << EOF
{
    "security": {
        "lockdown_mode": false,
        "rate_limiting": {
            "enabled": true,
            "requests_per_minute": 60,
            "block_time_minutes": 15
        },
        "session": {
            "timeout_minutes": 30,
            "max_sessions_per_user": 3
        },
        "admin_protection": {
            "ip_whitelist": [],
            "two_factor_auth": true
        },
        "auto_block": {
            "enabled": true,
            "failed_login_threshold": 5,
            "suspicious_activity_threshold": 10
        }
    },
    "stability": {
        "health_check": {
            "interval_seconds": 120,
            "timeout_seconds": 5
        },
        "zero_downtime_update": {
            "enabled": true,
            "backup_before_update": true
        },
        "service_management": {
            "auto_restart": true,
            "max_restart_attempts": 3
        }
    }
}
EOF
    
    print_success "Modulo di sicurezza e stabilità configurato con successo."
}

# Configurazione del servizio systemd
setup_systemd_service() {
    print_message "Configurazione servizio systemd per moduli avanzati..."
    
    local SERVICE_FILE="/etc/systemd/system/m4bot-monitoring.service"
    
    # Crea il file di servizio
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=M4Bot Advanced Monitoring Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=m4bot
WorkingDirectory=${INSTALL_DIR}
ExecStart=/usr/bin/python3 -c "from modules.monitoring import init_monitoring; monitor = init_monitoring('${CONFIG_DIR}/monitoring/config.json')"
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal
SyslogIdentifier=m4bot-monitoring

[Install]
WantedBy=multi-user.target
EOF
    
    # Ricarica configurazione systemd
    systemctl daemon-reload
    
    # Abilita e avvia il servizio
    systemctl enable m4bot-monitoring.service
    systemctl start m4bot-monitoring.service
    
    # Verifica stato
    local SERVICE_STATUS=$(systemctl is-active m4bot-monitoring.service)
    if [ "$SERVICE_STATUS" = "active" ]; then
        print_success "Servizio m4bot-monitoring avviato con successo."
    else
        print_error "Impossibile avviare il servizio m4bot-monitoring."
        print_message "Controllare i log con: journalctl -u m4bot-monitoring.service"
    fi
}

# Aggiorna la configurazione web
update_web_config() {
    print_message "Aggiornamento configurazione web per integrare i moduli avanzati..."
    
    local WEB_CONFIG_FILE="${CONFIG_DIR}/web/config.json"
    
    # Verifica se esiste già un file di configurazione
    if [ -f "$WEB_CONFIG_FILE" ]; then
        print_warning "File di configurazione web esistente trovato. Creazione di un backup..."
        cp "$WEB_CONFIG_FILE" "${WEB_CONFIG_FILE}.bak.$(date +%Y%m%d%H%M%S)"
        
        # Aggiungi le nuove configurazioni al file esistente
        local TEMP_FILE=$(mktemp)
        jq '. += {"monitoring_enabled": true, "security_modules": true}' "$WEB_CONFIG_FILE" > "$TEMP_FILE"
        mv "$TEMP_FILE" "$WEB_CONFIG_FILE"
    else
        # Crea un nuovo file di configurazione
        cat > "$WEB_CONFIG_FILE" << EOF
{
    "monitoring_enabled": true,
    "security_modules": true,
    "admin_panel": {
        "show_security_tab": true,
        "show_monitoring_tab": true
    }
}
EOF
    fi
    
    print_success "Configurazione web aggiornata con successo."
}

# Funzione principale
main() {
    # Verifica se l'utente è root
    if [ "$EUID" -ne 0 ]; then
        print_error "Questo script deve essere eseguito come root."
        exit 1
    fi
    
    print_message "Inizio installazione moduli avanzati per M4Bot..."
    
    # Controllo prerequisiti
    check_dependencies
    
    # Creazione directory
    create_directories
    
    # Configurazione moduli
    configure_monitoring
    configure_security
    
    # Aggiornamento configurazione web
    update_web_config
    
    # Configurazione servizio systemd
    setup_systemd_service
    
    print_success "Installazione completata con successo!"
    print_message "I moduli avanzati sono ora installati e configurati."
    print_message "Puoi accedere alle funzionalità di monitoraggio e sicurezza dal pannello di controllo admin."
}

# Esecuzione
main "$@" 