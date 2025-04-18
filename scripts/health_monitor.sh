#!/bin/bash
# Script di monitoraggio avanzato per M4Bot
# Verifica regolarmente lo stato del sistema e avvia procedure di auto-riparazione
# Versione: 1.0

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variabili di configurazione
M4BOT_DIR="/opt/m4bot"
LOG_DIR="/var/log/m4bot"
LOG_FILE="$LOG_DIR/health_$(date +%Y%m%d).log"
CHECK_INTERVAL=300 # Intervallo tra i controlli (in secondi)
MAX_CPU_THRESHOLD=80 # Percentuale massima di CPU
MAX_MEM_THRESHOLD=80 # Percentuale massima di memoria
MAX_DISK_THRESHOLD=85 # Percentuale massima di spazio su disco
SERVICES=("m4bot.service" "m4bot-web.service" "nginx" "redis-server")
API_ENDPOINTS=("http://localhost:5000/api/health" "http://localhost:5000/api/status")
DB_CHECK_ENABLED=true
SMTP_NOTIFY_ENABLED=false
SMTP_SERVER=""
SMTP_PORT=587
SMTP_USER=""
SMTP_PASSWORD=""
NOTIFY_EMAIL=""

# Crea directory per log
mkdir -p "$LOG_DIR"
touch "$LOG_FILE"

# Funzioni di utility
log_message() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1" | tee -a "$LOG_FILE"
}

print_message() {
    echo -e "${BLUE}[M4Bot Health]${NC} $1"
    log_message "$1"
}

print_error() {
    echo -e "${RED}[ERRORE]${NC} $1"
    log_message "[ERROR] $1"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
    log_message "[OK] $1"
}

print_warning() {
    echo -e "${YELLOW}[AVVISO]${NC} $1"
    log_message "[WARNING] $1"
}

# Controlla requisiti
check_requirements() {
    # Verifica che lo script sia eseguito come root
    if [ "$(id -u)" -ne 0 ]; then
        print_error "Questo script deve essere eseguito come root" 
        exit 1
    fi
    
    # Verifica che il sistema sia Linux
    if [ "$(uname)" != "Linux" ]; then
        print_error "Questo script è progettato per sistemi Linux"
        exit 1
    fi
    
    # Verifica comandi necessari
    for cmd in systemctl curl grep awk bc; do
        if ! command -v $cmd &> /dev/null; then
            print_error "Comando $cmd non disponibile. Installalo e riprova."
            exit 1
        fi
    done
}

# Controlla lo stato dei servizi
check_services() {
    print_message "Controllo servizi..."
    local issues_found=0
    
    for service in "${SERVICES[@]}"; do
        if systemctl is-active --quiet "$service"; then
            print_success "Servizio $service attivo"
        else
            print_error "Servizio $service non attivo"
            issues_found=$((issues_found + 1))
            repair_service "$service"
        fi
    done
    
    return $issues_found
}

# Controlla gli endpoint API
check_api_endpoints() {
    print_message "Controllo endpoint API..."
    local issues_found=0
    
    for endpoint in "${API_ENDPOINTS[@]}"; do
        local http_code=$(curl -s -o /dev/null -w "%{http_code}" "$endpoint")
        if [ "$http_code" == "200" ]; then
            print_success "Endpoint $endpoint risponde correttamente (HTTP $http_code)"
        else
            print_error "Endpoint $endpoint non risponde correttamente (HTTP $http_code)"
            issues_found=$((issues_found + 1))
        fi
    done
    
    return $issues_found
}

# Controlla l'utilizzo delle risorse
check_resources() {
    print_message "Controllo risorse di sistema..."
    local issues_found=0
    
    # CPU
    local cpu_usage=$(mpstat 1 1 | awk '$12 ~ /[0-9.]+/ { print 100 - $12 }' | tail -1)
    if (( $(echo "$cpu_usage < $MAX_CPU_THRESHOLD" | bc -l) )); then
        print_success "Utilizzo CPU: ${cpu_usage}% (soglia: ${MAX_CPU_THRESHOLD}%)"
    else
        print_warning "Utilizzo CPU elevato: ${cpu_usage}% (soglia: ${MAX_CPU_THRESHOLD}%)"
        issues_found=$((issues_found + 1))
        check_high_cpu_processes
    fi
    
    # Memoria
    local mem_usage=$(free | grep Mem | awk '{print $3/$2 * 100.0}')
    if (( $(echo "$mem_usage < $MAX_MEM_THRESHOLD" | bc -l) )); then
        print_success "Utilizzo memoria: ${mem_usage}% (soglia: ${MAX_MEM_THRESHOLD}%)"
    else
        print_warning "Utilizzo memoria elevato: ${mem_usage}% (soglia: ${MAX_MEM_THRESHOLD}%)"
        issues_found=$((issues_found + 1))
        check_high_memory_processes
    fi
    
    # Disco
    local disk_usage=$(df -h / | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$disk_usage" -lt "$MAX_DISK_THRESHOLD" ]; then
        print_success "Utilizzo disco: ${disk_usage}% (soglia: ${MAX_DISK_THRESHOLD}%)"
    else
        print_warning "Utilizzo disco elevato: ${disk_usage}% (soglia: ${MAX_DISK_THRESHOLD}%)"
        issues_found=$((issues_found + 1))
        clean_disk_space
    fi
    
    return $issues_found
}

# Controlla database
check_database() {
    if [ "$DB_CHECK_ENABLED" != true ]; then
        return 0
    fi
    
    print_message "Controllo database..."
    local issues_found=0
    
    # Verifica connessione al database
    if command -v mysql &> /dev/null; then
        if mysql -e "SHOW DATABASES;" &> /dev/null; then
            print_success "Database MySQL/MariaDB raggiungibile"
        else
            print_error "Impossibile connettersi al database MySQL/MariaDB"
            issues_found=$((issues_found + 1))
            repair_database "mysql"
        fi
    fi
    
    # Verifica connessione a Redis
    if command -v redis-cli &> /dev/null; then
        if redis-cli ping &> /dev/null; then
            print_success "Redis raggiungibile"
        else
            print_error "Impossibile connettersi a Redis"
            issues_found=$((issues_found + 1))
            repair_database "redis"
        fi
    fi
    
    return $issues_found
}

# Controlla i log per errori recenti
check_logs() {
    print_message "Analisi dei log per errori recenti..."
    local issues_found=0
    
    # Controlla i log di M4Bot per errori
    if [ -d "$M4BOT_DIR/logs" ]; then
        local error_count=$(grep -i "error\|exception\|fatal" "$M4BOT_DIR/logs"/* 2>/dev/null | wc -l)
        if [ "$error_count" -gt 0 ]; then
            print_warning "Trovati $error_count errori nei log di M4Bot"
            # Mostra gli ultimi 5 errori
            print_message "Ultimi errori:"
            grep -i "error\|exception\|fatal" "$M4BOT_DIR/logs"/* 2>/dev/null | tail -5
            issues_found=$((issues_found + 1))
        else
            print_success "Nessun errore rilevante nei log di M4Bot"
        fi
    fi
    
    # Controlla i log di systemd
    local systemd_errors=$(journalctl -u m4bot -u m4bot-web -p err -n 10 --no-pager 2>/dev/null | wc -l)
    if [ "$systemd_errors" -gt 0 ]; then
        print_warning "Trovati errori nei log di systemd"
        issues_found=$((issues_found + 1))
    else
        print_success "Nessun errore recente nei log di systemd"
    fi
    
    return $issues_found
}

# Verifica stato di backup
check_backups() {
    print_message "Controllo stato backup..."
    local issues_found=0
    
    # Verifica la presenza di backup recenti
    local backup_dir="$M4BOT_DIR/backups"
    if [ ! -d "$backup_dir" ]; then
        print_warning "Directory backup non trovata"
        issues_found=$((issues_found + 1))
        # Crea la directory
        mkdir -p "$backup_dir"
    else
        # Controlla se esiste un backup delle ultime 24 ore
        local recent_backup=$(find "$backup_dir" -type d -mtime -1 | wc -l)
        if [ "$recent_backup" -eq 0 ]; then
            print_warning "Nessun backup recente trovato (ultime 24 ore)"
            issues_found=$((issues_found + 1))
            # Avvia backup automatico
            trigger_backup
        else
            print_success "Backup recenti trovati: $recent_backup"
        fi
    fi
    
    return $issues_found
}

# Controlla aggiornamenti disponibili
check_updates() {
    print_message "Controllo aggiornamenti disponibili..."
    
    # Se git è disponibile e directory è un repo git
    if command -v git &> /dev/null && [ -d "$M4BOT_DIR/.git" ]; then
        # Controlla per aggiornamenti
        cd "$M4BOT_DIR"
        git fetch origin &> /dev/null
        
        local updates=$(git log HEAD..origin/main --oneline | wc -l)
        if [ "$updates" -gt 0 ]; then
            print_warning "Ci sono $updates aggiornamenti disponibili"
            # Mostra gli ultimi 3 aggiornamenti
            print_message "Ultimi aggiornamenti:"
            git log HEAD..origin/main --oneline --max-count=3
        else
            print_success "Sistema aggiornato all'ultima versione"
        fi
    else
        print_message "Impossibile controllare aggiornamenti (directory non è un repository git)"
    fi
}

# Funzioni di riparazione automatica
repair_service() {
    local service=$1
    print_message "Tentativo di riparazione del servizio $service..."
    
    # Riavvia il servizio
    systemctl restart "$service"
    sleep 2
    
    # Verifica se il riavvio ha risolto il problema
    if systemctl is-active --quiet "$service"; then
        print_success "Servizio $service riparato con successo"
        send_notification "Servizio $service riparato automaticamente"
    else
        print_error "Impossibile riparare il servizio $service"
        send_notification "CRITICO: Impossibile riparare il servizio $service"
    fi
}

repair_database() {
    local db_type=$1
    print_message "Tentativo di riparazione database $db_type..."
    
    case "$db_type" in
        mysql)
            # Riavvia il servizio MySQL/MariaDB
            systemctl restart mysql.service 2>/dev/null || systemctl restart mariadb.service 2>/dev/null
            sleep 5
            if mysql -e "SHOW DATABASES;" &> /dev/null; then
                print_success "Database MySQL/MariaDB riparato con successo"
            else
                print_error "Impossibile riparare il database MySQL/MariaDB"
            fi
            ;;
        redis)
            # Riavvia Redis
            systemctl restart redis-server
            sleep 2
            if redis-cli ping &> /dev/null; then
                print_success "Redis riparato con successo"
            else
                print_error "Impossibile riparare Redis"
            fi
            ;;
    esac
}

check_high_cpu_processes() {
    print_message "Analisi processi CPU intensivi..."
    echo "Top 5 processi per utilizzo CPU:"
    ps aux --sort=-%cpu | head -6
}

check_high_memory_processes() {
    print_message "Analisi processi con alto consumo di memoria..."
    echo "Top 5 processi per utilizzo memoria:"
    ps aux --sort=-%mem | head -6
}

clean_disk_space() {
    print_message "Pulizia spazio disco..."
    
    # Pulisci la cache di APT
    if command -v apt-get &> /dev/null; then
        print_message "Pulizia cache APT..."
        apt-get clean -y &> /dev/null
    fi
    
    # Pulisci log vecchi
    print_message "Pulizia log vecchi..."
    find "$LOG_DIR" -type f -name "*.log" -mtime +30 -delete
    find /var/log -type f -name "*.gz" -mtime +30 -delete 2>/dev/null
    
    # Pulisci file temporanei
    print_message "Pulizia file temporanei..."
    find /tmp -type f -atime +10 -delete 2>/dev/null
    
    # Verifica spazio liberato
    print_success "Pulizia completata"
}

trigger_backup() {
    print_message "Avvio backup automatico..."
    
    # Se esiste uno script di backup, eseguilo
    if [ -f "$M4BOT_DIR/scripts/backup.sh" ]; then
        bash "$M4BOT_DIR/scripts/backup.sh" auto
        if [ $? -eq 0 ]; then
            print_success "Backup automatico completato con successo"
        else
            print_error "Backup automatico fallito"
        fi
    else
        print_error "Script di backup non trovato"
    fi
}

send_notification() {
    local message=$1
    
    # Log della notifica
    log_message "NOTIFICA: $message"
    
    # Se le notifiche email sono abilitate
    if [ "$SMTP_NOTIFY_ENABLED" = true ] && [ -n "$NOTIFY_EMAIL" ]; then
        if command -v mail &> /dev/null; then
            echo "$message" | mail -s "M4Bot Health Alert" "$NOTIFY_EMAIL"
        fi
    fi
    
    # Volendo qui si potrebbero aggiungere altri tipi di notifiche (webhook, Telegram, etc.)
}

run_health_check() {
    print_message "====================================================="
    print_message "AVVIO CONTROLLO SALUTE SISTEMA M4BOT"
    print_message "====================================================="
    
    local total_issues=0
    local issues=0
    
    # Esegui tutti i controlli
    check_services
    issues=$?
    total_issues=$((total_issues + issues))
    
    check_api_endpoints
    issues=$?
    total_issues=$((total_issues + issues))
    
    check_resources
    issues=$?
    total_issues=$((total_issues + issues))
    
    check_database
    issues=$?
    total_issues=$((total_issues + issues))
    
    check_logs
    issues=$?
    total_issues=$((total_issues + issues))
    
    check_backups
    issues=$?
    total_issues=$((total_issues + issues))
    
    check_updates
    
    # Riassunto
    print_message "====================================================="
    if [ $total_issues -eq 0 ]; then
        print_success "TUTTI I CONTROLLI COMPLETATI: Sistema in salute"
    else
        print_warning "CONTROLLI COMPLETATI: Trovati $total_issues problemi"
    fi
    print_message "====================================================="
}

# Modalità demone (monitor continuo)
daemon_mode() {
    while true; do
        run_health_check
        print_message "Prossimo controllo tra $CHECK_INTERVAL secondi..."
        sleep $CHECK_INTERVAL
    done
}

# Verifica argomenti
check_requirements

# Controlla se eseguire in modalità demone o singolo controllo
if [ "$1" = "--daemon" ] || [ "$1" = "-d" ]; then
    daemon_mode
else
    run_health_check
fi 