#!/bin/bash
# Script di diagnostica avanzata per M4Bot
# Raccoglie informazioni complete sul sistema e stato dell'applicazione
# Versione: 1.0

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Variabili di configurazione
M4BOT_DIR="/opt/m4bot"
OUTPUT_DIR="/tmp/m4bot_diagnostics_$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$OUTPUT_DIR/diagnostics.log"
ARCHIVE_NAME="m4bot_diagnostics_$(date +%Y%m%d_%H%M%S).tar.gz"
COLLECT_LOGS=true
COLLECT_CONFIG=true
COLLECT_SYSTEM=true
COLLECT_DATABASE=true
LOG_LINES=1000 # Numero di righe da prelevare dai log
DB_ENABLED=true # Se abilitare il controllo del database
TIMEZONE=$(timedatectl | grep "Time zone" | awk '{print $3}')

# Crea la directory di output
mkdir -p "$OUTPUT_DIR"
touch "$LOG_FILE"

# Funzioni di utilità
log_message() {
    echo "[$(date +"%Y-%m-%d %H:%M:%S %Z")] $1" | tee -a "$LOG_FILE"
}

print_header() {
    echo -e "\n${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║ ${CYAN}$1${BLUE} ${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
    log_message "SEZIONE: $1"
}

print_section() {
    echo -e "\n${CYAN}▶ $1${NC}"
    log_message "SOTTOSEZIONE: $1"
}

print_message() {
    echo -e "${BLUE}[M4Bot]${NC} $1"
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

run_command() {
    local cmd="$1"
    local output_file="$2"
    local description="$3"
    local silent="${4:-false}"
    
    if [ "$silent" = "false" ]; then
        print_message "Esecuzione: $description"
    fi
    
    # Esegui comando e scrivi output nel file
    echo "=== $description ($(date)) ===" > "$output_file"
    echo "$ $cmd" >> "$output_file"
    echo "---" >> "$output_file"
    
    # Esegui comando e salva output
    if ! eval "$cmd" >> "$output_file" 2>&1; then
        if [ "$silent" = "false" ]; then
            print_error "Errore nell'esecuzione del comando: $cmd"
        fi
        echo "[ERROR] Comando fallito con codice di uscita $?" >> "$output_file"
        return 1
    fi
    
    return 0
}

# Controlla requisiti
check_requirements() {
    print_message "Controllo requisiti per la diagnostica..."
    
    # Verifica che lo script sia eseguito come root
    if [ "$(id -u)" -ne 0 ]; then
        print_warning "Questo script non è eseguito come root. Alcune informazioni potrebbero non essere raccolte."
    fi
    
    # Verifica che il sistema sia Linux
    if [ "$(uname)" != "Linux" ]; then
        print_error "Questo script è progettato per sistemi Linux"
        exit 1
    fi
    
    # Verifica che la directory di M4Bot esista
    if [ ! -d "$M4BOT_DIR" ]; then
        print_error "Directory di M4Bot non trovata in $M4BOT_DIR"
        print_message "Imposta manualmente con: export M4BOT_DIR=/percorso/a/m4bot"
        exit 1
    fi
    
    # Verifica comandi necessari
    MISSING_COMMANDS=0
    for cmd in systemctl grep awk sed lsof ps netstat df free; do
        if ! command -v $cmd &> /dev/null; then
            print_warning "Comando $cmd non disponibile. Alcune informazioni potrebbero non essere raccolte."
            MISSING_COMMANDS=$((MISSING_COMMANDS + 1))
        fi
    done
    
    print_success "Controllo requisiti completato (comandi mancanti: $MISSING_COMMANDS)"
}

# Raccoglie informazioni sul sistema
collect_system_info() {
    print_header "INFORMAZIONI SISTEMA"
    
    mkdir -p "$OUTPUT_DIR/system"
    
    # Info OS
    print_section "Sistema Operativo"
    run_command "cat /etc/os-release" "$OUTPUT_DIR/system/os_release.txt" "Versione Sistema Operativo"
    run_command "uname -a" "$OUTPUT_DIR/system/uname.txt" "Informazioni Kernel"
    
    # CPU e memoria
    print_section "CPU e Memoria"
    run_command "cat /proc/cpuinfo" "$OUTPUT_DIR/system/cpu_info.txt" "Informazioni CPU"
    run_command "free -h" "$OUTPUT_DIR/system/memory.txt" "Utilizzo Memoria"
    run_command "vmstat 1 5" "$OUTPUT_DIR/system/vmstat.txt" "Statistiche Virtual Memory (5 campioni)"
    run_command "cat /proc/meminfo" "$OUTPUT_DIR/system/mem_info.txt" "Informazioni Memoria Dettagliate"
    
    # Disco
    print_section "Disco"
    run_command "df -h" "$OUTPUT_DIR/system/disk_usage.txt" "Utilizzo Disco"
    run_command "lsblk" "$OUTPUT_DIR/system/block_devices.txt" "Dispositivi a Blocchi"
    run_command "mount" "$OUTPUT_DIR/system/mount_points.txt" "Punti di Mount"
    
    # Rete
    print_section "Rete"
    run_command "ip addr" "$OUTPUT_DIR/system/ip_addresses.txt" "Indirizzi IP"
    run_command "ip route" "$OUTPUT_DIR/system/ip_routes.txt" "Route IP"
    run_command "netstat -tuln" "$OUTPUT_DIR/system/open_ports.txt" "Porte Aperte"
    run_command "cat /etc/hosts" "$OUTPUT_DIR/system/hosts.txt" "File Hosts"
    run_command "cat /etc/resolv.conf" "$OUTPUT_DIR/system/resolv_conf.txt" "Configurazione DNS"
    
    # Processi
    print_section "Processi"
    run_command "ps aux" "$OUTPUT_DIR/system/processes.txt" "Processi Attivi"
    run_command "ps aux | grep -i m4bot" "$OUTPUT_DIR/system/m4bot_processes.txt" "Processi M4Bot"
    run_command "ps aux --sort=-%cpu | head -10" "$OUTPUT_DIR/system/top_cpu_processes.txt" "Top 10 Processi per CPU"
    run_command "ps aux --sort=-%mem | head -10" "$OUTPUT_DIR/system/top_mem_processes.txt" "Top 10 Processi per Memoria"
    
    # Limiti e risorse
    print_section "Limiti e Risorse"
    run_command "ulimit -a" "$OUTPUT_DIR/system/ulimit.txt" "Limiti di Sistema"
    run_command "sysctl -a" "$OUTPUT_DIR/system/sysctl.txt" "Configurazioni Kernel"
    
    # Data e ora
    print_section "Data e Ora"
    run_command "date" "$OUTPUT_DIR/system/date.txt" "Data e Ora Sistema"
    run_command "timedatectl" "$OUTPUT_DIR/system/timedatectl.txt" "Configurazione Orologio"
    run_command "cat /etc/timezone 2>/dev/null || echo $TIMEZONE" "$OUTPUT_DIR/system/timezone.txt" "Fuso Orario"
    
    # Servizi systemd
    print_section "Servizi Systemd"
    run_command "systemctl list-units --type=service" "$OUTPUT_DIR/system/systemd_services.txt" "Elenco Servizi"
    run_command "systemctl status m4bot.service" "$OUTPUT_DIR/system/m4bot_service_status.txt" "Stato Servizio M4Bot"
    run_command "systemctl status m4bot-web.service" "$OUTPUT_DIR/system/m4bot_web_service_status.txt" "Stato Servizio Web M4Bot"
    
    # Utenti
    print_section "Utenti"
    run_command "cat /etc/passwd | grep -i m4bot" "$OUTPUT_DIR/system/m4bot_user.txt" "Utente M4Bot"
    run_command "id m4bot 2>/dev/null || echo 'Utente m4bot non trovato'" "$OUTPUT_DIR/system/m4bot_id.txt" "ID Utente M4Bot"
    
    # Socket e connessioni
    print_section "Socket e Connessioni"
    run_command "lsof -i" "$OUTPUT_DIR/system/open_files_network.txt" "File Aperti (Rete)"
    run_command "lsof -p \$(pgrep -f m4bot)" "$OUTPUT_DIR/system/m4bot_open_files.txt" "File Aperti da M4Bot"
    
    # Firewall
    print_section "Firewall"
    run_command "iptables -L -v -n" "$OUTPUT_DIR/system/iptables.txt" "Regole Firewall IPTables"
    
    # Log di sistema
    print_section "Log di Sistema"
    run_command "journalctl -u m4bot.service --no-pager -n $LOG_LINES" "$OUTPUT_DIR/system/journalctl_m4bot.txt" "Log Journal M4Bot"
    run_command "journalctl -u m4bot-web.service --no-pager -n $LOG_LINES" "$OUTPUT_DIR/system/journalctl_m4bot_web.txt" "Log Journal M4Bot Web"
    run_command "tail -n $LOG_LINES /var/log/syslog 2>/dev/null || echo 'Syslog non accessibile'" "$OUTPUT_DIR/system/syslog.txt" "Syslog"
    
    # Python
    print_section "Python"
    run_command "python3 --version" "$OUTPUT_DIR/system/python_version.txt" "Versione Python"
    run_command "pip3 list" "$OUTPUT_DIR/system/pip_packages.txt" "Pacchetti Pip Installati"
    run_command "$M4BOT_DIR/venv/bin/pip list 2>/dev/null || echo 'Virtualenv non accessibile'" "$OUTPUT_DIR/system/venv_packages.txt" "Pacchetti Virtualenv M4Bot"
    
    print_success "Raccolta informazioni sistema completata"
}

# Raccoglie informazioni sulla configurazione
collect_config_info() {
    print_header "CONFIGURAZIONE M4BOT"
    
    mkdir -p "$OUTPUT_DIR/config"
    
    print_section "File di Configurazione"
    
    # Copia file di configurazione principali (rimuovendo dati sensibili)
    CONFIG_FILES=(
        "config.json"
        "config.py"
        ".env"
        "web/config.json"
        "web/.env"
    )
    
    for config_file in "${CONFIG_FILES[@]}"; do
        if [ -f "$M4BOT_DIR/$config_file" ]; then
            # Crea una copia sanitizzata (senza password e token)
            cat "$M4BOT_DIR/$config_file" | \
                sed 's/\("password"\s*:\s*"\)[^"]*"/\1********"/g' | \
                sed 's/\("token"\s*:\s*"\)[^"]*"/\1********"/g' | \
                sed 's/\("secret"\s*:\s*"\)[^"]*"/\1********"/g' | \
                sed 's/\("api_key"\s*:\s*"\)[^"]*"/\1********"/g' | \
                sed 's/\(password\s*=\s*["'"'"']\)[^"'"'"']*["'"'"']/\1********/g' | \
                sed 's/\(TOKEN\s*=\s*["'"'"']\)[^"'"'"']*["'"'"']/\1********/g' | \
                sed 's/\(SECRET\s*=\s*["'"'"']\)[^"'"'"']*["'"'"']/\1********/g' | \
                sed 's/\(API_KEY\s*=\s*["'"'"']\)[^"'"'"']*["'"'"']/\1********/g' | \
                sed 's/PASSWORD=.*/PASSWORD=********/g' | \
                sed 's/TOKEN=.*/TOKEN=********/g' | \
                sed 's/SECRET_KEY=.*/SECRET_KEY=********/g' | \
                sed 's/API_KEY=.*/API_KEY=********/g' \
                > "$OUTPUT_DIR/config/$(basename "$config_file")"
                
            print_message "File di configurazione copiato e sanitizzato: $config_file"
        fi
    done
    
    # Verifica struttura directory
    print_section "Struttura Directory"
    run_command "find $M4BOT_DIR -type d | sort" "$OUTPUT_DIR/config/directory_structure.txt" "Struttura Directory M4Bot"
    run_command "ls -la $M4BOT_DIR" "$OUTPUT_DIR/config/main_dir_listing.txt" "Contenuto Directory Principale"
    run_command "ls -la $M4BOT_DIR/web" "$OUTPUT_DIR/config/web_dir_listing.txt" "Contenuto Directory Web"
    
    # Raccoglie informazioni sui file di configurazione Nginx
    print_section "Configurazione Web Server"
    run_command "find /etc/nginx -name '*.conf' | xargs cat 2>/dev/null | grep -i m4bot" "$OUTPUT_DIR/config/nginx_config.txt" "Configurazione Nginx per M4Bot"
    
    # Raccoglie info sui file di servizio
    print_section "File di Servizio"
    run_command "cat /etc/systemd/system/m4bot.service 2>/dev/null || echo 'File servizio non trovato'" "$OUTPUT_DIR/config/m4bot_service.txt" "File Servizio M4Bot" 
    run_command "cat /etc/systemd/system/m4bot-web.service 2>/dev/null || echo 'File servizio non trovato'" "$OUTPUT_DIR/config/m4bot_web_service.txt" "File Servizio M4Bot Web"
    
    # Verifica presenza SSL
    print_section "Configurazione SSL"
    run_command "find /etc/letsencrypt/live -name 'cert.pem' | xargs -I{} dirname {} 2>/dev/null || echo 'Nessun certificato trovato'" "$OUTPUT_DIR/config/ssl_certificates.txt" "Certificati SSL"
    run_command "find /etc/ssl -name '*.pem' | grep -i m4bot 2>/dev/null || echo 'Nessun certificato trovato'" "$OUTPUT_DIR/config/ssl_certificates_other.txt" "Altri Certificati SSL"
    
    print_success "Raccolta informazioni configurazione completata"
}

# Raccoglie log e stato dell'applicazione
collect_app_logs() {
    print_header "LOG E STATO M4BOT"
    
    mkdir -p "$OUTPUT_DIR/logs"
    
    print_section "Log Applicazione"
    
    # Directory dei log
    LOG_DIRS=(
        "$M4BOT_DIR/logs"
        "$M4BOT_DIR/web/logs"
        "/var/log/m4bot"
    )
    
    for log_dir in "${LOG_DIRS[@]}"; do
        if [ -d "$log_dir" ]; then
            print_message "Raccolta log dalla directory: $log_dir"
            
            # Raccoglie gli ultimi N righe dai file di log
            for log_file in $(find "$log_dir" -name "*.log" -type f); do
                # Crea nome file di output
                output_basename=$(basename "$log_file")
                output_file="$OUTPUT_DIR/logs/$output_basename"
                
                # Raccoglie le ultime N righe dal log
                if [ -f "$log_file" ]; then
                    tail -n $LOG_LINES "$log_file" > "$output_file"
                    print_message "Raccolte ultime $LOG_LINES righe da: $output_basename"
                fi
            done
        fi
    done
    
    # Raccoglie log di errore
    print_section "Log Errori"
    for log_dir in "${LOG_DIRS[@]}"; do
        if [ -d "$log_dir" ]; then
            for log_file in $(find "$log_dir" -name "*.log" -type f); do
                # Cerca errori e salva in file separato
                output_basename="errors_$(basename "$log_file")"
                output_file="$OUTPUT_DIR/logs/$output_basename"
                
                grep -i "error\|exception\|fatal\|crash\|fail" "$log_file" > "$output_file" 2>/dev/null
                
                # Conta errori trovati
                error_count=$(wc -l < "$output_file")
                if [ "$error_count" -gt 0 ]; then
                    print_warning "Trovati $error_count errori in: $(basename "$log_file")"
                else
                    rm "$output_file" # Rimuovi file se vuoto
                fi
            done
        fi
    done
    
    # Stato API
    print_section "Stato API"
    if command -v curl &>/dev/null; then
        run_command "curl -s http://localhost:5000/api/health 2>/dev/null || echo 'API non raggiungibile'" "$OUTPUT_DIR/logs/api_health.txt" "Stato API Health"
        run_command "curl -s http://localhost:5000/api/status 2>/dev/null || echo 'API non raggiungibile'" "$OUTPUT_DIR/logs/api_status.txt" "Stato API Status"
    else
        print_warning "curl non disponibile, impossibile controllare stato API"
    fi
    
    # Informazioni Git
    print_section "Stato Repository Git"
    if [ -d "$M4BOT_DIR/.git" ] && command -v git &>/dev/null; then
        cd "$M4BOT_DIR"
        run_command "git status" "$OUTPUT_DIR/logs/git_status.txt" "Stato Git"
        run_command "git log -n 10 --pretty=format:'%h - %s (%cr) <%an>'" "$OUTPUT_DIR/logs/git_log.txt" "Ultimi 10 Commit"
        run_command "git branch" "$OUTPUT_DIR/logs/git_branch.txt" "Branch Git"
        run_command "git config --local --list" "$OUTPUT_DIR/logs/git_config.txt" "Configurazione Git"
    else
        print_warning "Repository git non trovato"
    fi
    
    print_success "Raccolta log e stato applicazione completata"
}

# Raccoglie informazioni sul database
collect_database_info() {
    if [ "$DB_ENABLED" != true ]; then
        print_warning "Raccolta informazioni database disabilitata"
        return 0
    fi
    
    print_header "INFORMAZIONI DATABASE"
    
    mkdir -p "$OUTPUT_DIR/database"
    
    # Determina tipo di database
    DB_TYPE="unknown"
    if command -v mysql &>/dev/null; then
        run_command "systemctl status mysql mariadb 2>/dev/null" "$OUTPUT_DIR/database/mysql_status.txt" "Stato MySQL/MariaDB" true
        if grep -q "Active: active" "$OUTPUT_DIR/database/mysql_status.txt"; then
            DB_TYPE="mysql"
            print_section "MySQL/MariaDB"
        fi
    fi
    
    if command -v psql &>/dev/null; then
        run_command "systemctl status postgresql 2>/dev/null" "$OUTPUT_DIR/database/postgresql_status.txt" "Stato PostgreSQL" true
        if grep -q "Active: active" "$OUTPUT_DIR/database/postgresql_status.txt"; then
            DB_TYPE="postgresql"
            print_section "PostgreSQL"
        fi
    fi
    
    # Redis
    if command -v redis-cli &>/dev/null; then
        run_command "systemctl status redis-server 2>/dev/null" "$OUTPUT_DIR/database/redis_status.txt" "Stato Redis" true
        if grep -q "Active: active" "$OUTPUT_DIR/database/redis_status.txt"; then
            print_section "Redis"
            run_command "redis-cli info" "$OUTPUT_DIR/database/redis_info.txt" "Informazioni Redis"
            run_command "redis-cli dbsize" "$OUTPUT_DIR/database/redis_dbsize.txt" "Dimensione Redis"
            run_command "redis-cli config get *" "$OUTPUT_DIR/database/redis_config.txt" "Configurazione Redis"
        fi
    fi
    
    # Informazioni MySQL
    if [ "$DB_TYPE" = "mysql" ]; then
        print_message "Rilevato database MySQL/MariaDB"
        
        # Cerca config file
        CONFIG_FILE="$M4BOT_DIR/config/db.json"
        if [ -f "$CONFIG_FILE" ]; then
            # Estrai info database dal config (in modo sicuro)
            DB_NAME=$(grep -o '"database"[[:space:]]*:[[:space:]]*"[^"]*"' "$CONFIG_FILE" | sed 's/"database"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')
            DB_USER=$(grep -o '"user"[[:space:]]*:[[:space:]]*"[^"]*"' "$CONFIG_FILE" | sed 's/"user"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')
            
            if [ -n "$DB_NAME" ] && [ -n "$DB_USER" ]; then
                print_message "Raccolta informazioni per database: $DB_NAME (utente: $DB_USER)"
                
                # Prova a raccogliere info schema del database (senza richiedere password)
                run_command "mysql -u $DB_USER --database=$DB_NAME -e 'SHOW TABLES;' 2>/dev/null || echo 'Accesso negato'" "$OUTPUT_DIR/database/mysql_tables.txt" "Tabelle MySQL"
                
                # Informazioni generali
                run_command "mysql -e 'SHOW VARIABLES;' 2>/dev/null || echo 'Accesso negato'" "$OUTPUT_DIR/database/mysql_variables.txt" "Variabili MySQL"
                run_command "mysql -e 'SHOW STATUS;' 2>/dev/null || echo 'Accesso negato'" "$OUTPUT_DIR/database/mysql_status_vars.txt" "Stato MySQL"
                run_command "mysql -e 'SHOW PROCESSLIST;' 2>/dev/null || echo 'Accesso negato'" "$OUTPUT_DIR/database/mysql_processes.txt" "Processi MySQL"
            else
                print_warning "Impossibile estrarre info database dal file di configurazione"
            fi
        else
            print_warning "File di configurazione database non trovato: $CONFIG_FILE"
        fi
    fi
    
    # Informazioni PostgreSQL
    if [ "$DB_TYPE" = "postgresql" ]; then
        print_message "Rilevato database PostgreSQL"
        
        # Cerca config file
        CONFIG_FILE="$M4BOT_DIR/config/db.json"
        if [ -f "$CONFIG_FILE" ]; then
            # Estrai info database dal config (in modo sicuro)
            DB_NAME=$(grep -o '"database"[[:space:]]*:[[:space:]]*"[^"]*"' "$CONFIG_FILE" | sed 's/"database"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')
            DB_USER=$(grep -o '"user"[[:space:]]*:[[:space:]]*"[^"]*"' "$CONFIG_FILE" | sed 's/"user"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')
            
            if [ -n "$DB_NAME" ] && [ -n "$DB_USER" ]; then
                print_message "Raccolta informazioni per database: $DB_NAME (utente: $DB_USER)"
                
                # Prova con utente m4bot senza richiedere password
                run_command "PGPASSWORD='' psql -U $DB_USER -d $DB_NAME -c '\\dt' 2>/dev/null || echo 'Accesso negato'" "$OUTPUT_DIR/database/pg_tables.txt" "Tabelle PostgreSQL"
                
                # Informazioni generali
                run_command "PGPASSWORD='' psql -U $DB_USER -d $DB_NAME -c 'SELECT version();' 2>/dev/null || echo 'Accesso negato'" "$OUTPUT_DIR/database/pg_version.txt" "Versione PostgreSQL"
                run_command "PGPASSWORD='' psql -U $DB_USER -d $DB_NAME -c 'SELECT * FROM pg_stat_activity;' 2>/dev/null || echo 'Accesso negato'" "$OUTPUT_DIR/database/pg_activity.txt" "Attività PostgreSQL"
            else
                print_warning "Impossibile estrarre info database dal file di configurazione"
            fi
        else
            print_warning "File di configurazione database non trovato: $CONFIG_FILE"
        fi
    fi
    
    print_success "Raccolta informazioni database completata"
}

# Crea report diagnostico
create_report() {
    print_header "CREAZIONE REPORT DIAGNOSTICO"
    
    print_message "Generazione sommario..."
    
    # Crea file di sommario
    SUMMARY_FILE="$OUTPUT_DIR/summary.txt"
    
    {
        echo "======================================================"
        echo "  M4Bot - Report Diagnostico"
        echo "======================================================"
        echo ""
        echo "Data generazione: $(date)"
        echo "Host: $(hostname)"
        echo "Sistema operativo: $(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '"')"
        echo "Kernel: $(uname -r)"
        echo "Fuso orario: $TIMEZONE"
        echo ""
        echo "======================================================" 
        echo "  Dati Raccolti"
        echo "======================================================" 
        
        # Informazioni sistema
        if [ "$COLLECT_SYSTEM" = true ]; then
            echo "- Informazioni sistema: SÌ"
            echo "  * CPU: $(grep -c processor /proc/cpuinfo) core"
            echo "  * Memoria: $(free -h | awk '/^Mem/{print $2}')"
            echo "  * Spazio disco: $(df -h / | awk 'NR==2 {print $4}') disponibili"
        else
            echo "- Informazioni sistema: NO"
        fi
        
        # Configurazione
        if [ "$COLLECT_CONFIG" = true ]; then
            echo "- Configurazione: SÌ"
            echo "  * Directory di installazione: $M4BOT_DIR"
            echo "  * Servizi:"
            
            if systemctl is-active --quiet m4bot.service; then
                echo "    - m4bot.service: ATTIVO"
            else
                echo "    - m4bot.service: INATTIVO"
            fi
            
            if systemctl is-active --quiet m4bot-web.service; then
                echo "    - m4bot-web.service: ATTIVO"
            else
                echo "    - m4bot-web.service: INATTIVO"
            fi
        else
            echo "- Configurazione: NO"
        fi
        
        # Log
        if [ "$COLLECT_LOGS" = true ]; then
            echo "- Log: SÌ"
            LOG_COUNT=$(find "$OUTPUT_DIR/logs" -type f | wc -l)
            ERROR_LOG_COUNT=$(find "$OUTPUT_DIR/logs" -name "errors_*" | wc -l)
            echo "  * File log raccolti: $LOG_COUNT"
            echo "  * File con errori: $ERROR_LOG_COUNT"
        else
            echo "- Log: NO"
        fi
        
        # Database
        if [ "$COLLECT_DATABASE" = true ] && [ "$DB_ENABLED" = true ]; then
            echo "- Database: SÌ"
            echo "  * Tipo database: $DB_TYPE"
            
            if command -v redis-cli &>/dev/null && systemctl is-active --quiet redis-server; then
                echo "  * Redis: ATTIVO"
            else
                echo "  * Redis: INATTIVO"
            fi
        else
            echo "- Database: NO"
        fi
        
        echo ""
        echo "======================================================"
        echo "  Problemi Rilevati"
        echo "======================================================"
        
        # Controlla errori nei log
        ERROR_COUNT=0
        if [ -d "$OUTPUT_DIR/logs" ]; then
            for error_file in $(find "$OUTPUT_DIR/logs" -name "errors_*"); do
                file_errors=$(wc -l < "$error_file")
                ERROR_COUNT=$((ERROR_COUNT + file_errors))
            done
        fi
        
        if [ $ERROR_COUNT -gt 0 ]; then
            echo "- Trovati $ERROR_COUNT errori nei log"
        fi
        
        # Controlla servizi non attivi
        if ! systemctl is-active --quiet m4bot.service; then
            echo "- Servizio m4bot.service non attivo"
        fi
        
        if ! systemctl is-active --quiet m4bot-web.service; then
            echo "- Servizio m4bot-web.service non attivo"
        fi
        
        # Controllo risorse sistema
        DISK_USAGE=$(df -h / | awk 'NR==2 {gsub(/%/,""); print $5}')
        if [ "$DISK_USAGE" -gt 85 ]; then
            echo "- Spazio disco quasi esaurito: $DISK_USAGE%"
        fi
        
        MEM_USAGE=$(free | grep Mem | awk '{print int($3/$2 * 100.0)}')
        if [ "$MEM_USAGE" -gt 90 ]; then
            echo "- Utilizzo memoria molto alto: $MEM_USAGE%"
        fi
        
        echo ""
        echo "======================================================"
        echo "  Come utilizzare questo report"
        echo "======================================================"
        echo ""
        echo "1. Estrai il file $(basename "$ARCHIVE_PATH")"
        echo "2. Esamina il file summary.txt per una panoramica"
        echo "3. Controlla i file di log nella directory 'logs' per errori specifici"
        echo "4. Verifica lo stato del sistema nella directory 'system'"
        echo ""
        echo "Per supporto, invia questo report completo all'assistenza tecnica."
        
    } > "$SUMMARY_FILE"
    
    print_message "Compressione file diagnostici..."
    
    # Crea archivio compresso
    ARCHIVE_PATH="/tmp/$ARCHIVE_NAME"
    tar -czf "$ARCHIVE_PATH" -C "$(dirname "$OUTPUT_DIR")" "$(basename "$OUTPUT_DIR")"
    
    print_success "Report diagnostico creato: $ARCHIVE_PATH"
    print_message "Dimensione: $(du -h "$ARCHIVE_PATH" | cut -f1)"
}

# Funzione principale
main() {
    # Titolo iniziale
    echo -e "\n${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║ ${CYAN}M4Bot - Strumento Diagnostico Avanzato v1.0${BLUE}          ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
    echo
    print_message "Avvio diagnostica completa del sistema M4Bot..."
    
    # Controlla requisiti
    check_requirements
    
    # Raccoglie informazioni di sistema
    if [ "$COLLECT_SYSTEM" = true ]; then
        collect_system_info
    fi
    
    # Raccoglie informazioni configurazione
    if [ "$COLLECT_CONFIG" = true ]; then
        collect_config_info
    fi
    
    # Raccoglie log
    if [ "$COLLECT_LOGS" = true ]; then
        collect_app_logs
    fi
    
    # Raccoglie informazioni database
    if [ "$COLLECT_DATABASE" = true ]; then
        collect_database_info
    fi
    
    # Crea report
    create_report
    
    # Output finale
    echo -e "\n${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║ ${CYAN}Diagnostica Completata                               ${BLUE}║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
    echo
    print_message "File diagnostico: $ARCHIVE_PATH"
    print_message "Puoi inviare questo file all'assistenza tecnica per supporto."
}

# Analizza argomenti
while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-system)
            COLLECT_SYSTEM=false
            shift
            ;;
        --no-config)
            COLLECT_CONFIG=false
            shift
            ;;
        --no-logs)
            COLLECT_LOGS=false
            shift
            ;;
        --no-db)
            COLLECT_DATABASE=false
            shift
            ;;
        --db-enabled)
            DB_ENABLED=true
            shift
            ;;
        --log-lines)
            LOG_LINES="$2"
            shift 2
            ;;
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -h|--help)
            echo "Uso: $0 [opzioni]"
            echo
            echo "Opzioni:"
            echo "  --no-system       Non raccogliere informazioni di sistema"
            echo "  --no-config       Non raccogliere informazioni di configurazione"
            echo "  --no-logs         Non raccogliere log"
            echo "  --no-db           Non raccogliere informazioni database"
            echo "  --db-enabled      Abilita raccolta informazioni database"
            echo "  --log-lines N     Imposta numero di righe da prelevare dai log (default: 1000)"
            echo "  --output DIR      Imposta directory di output"
            echo "  -h, --help        Mostra questo messaggio di aiuto"
            exit 0
            ;;
        *)
            echo "Opzione non riconosciuta: $1"
            echo "Usa --help per la lista delle opzioni disponibili"
            exit 1
            ;;
    esac
done

# Esegui funzione principale
main 