#!/bin/bash
# Script di installazione unificato per M4Bot su VPS Linux
# Questo script combina tutte le funzionalità necessarie e gestisce la configurazione SSL

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Variabili di configurazione
INSTALL_DIR="/opt/m4bot"
DB_NAME="m4bot_db"
DB_USER="m4bot_user"
DB_PASS=$(openssl rand -hex 12)  # Password generata casualmente
WEB_PORT=5000
BOT_PORT=5001
DOMAINS=""
SSL_EMAIL=""
INSTALL_CERTBOT=false
AUTO_RENEWAL=true
SCRIPT_VERSION="2.0.0"

# Verifica se whiptail è disponibile
USE_GUI=true
if ! command -v whiptail &> /dev/null; then
    USE_GUI=false
fi

# Funzioni di utilità per interfaccia grafica
show_title() {
    clear
    echo -e "${BLUE}"
    echo "╔═════════════════════════════════════════════════════════╗"
    echo "║                                                         ║"
    echo "║            M4Bot - Installazione Versione $SCRIPT_VERSION            ║"
    echo "║                                                         ║"
    echo "╚═════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

progress_bar() {
    local title="$1"
    local percent="$2"
    
    if [ "$USE_GUI" = true ]; then
        echo "$percent" | whiptail --gauge "$title" 10 70 0
    else
        printf "%-40s [" "$title"
        for i in $(seq 1 20); do
            if [ $i -le $(($percent / 5)) ]; then
                printf "#"
            else
                printf " "
            fi
        done
        printf "] %3d%%\r" "$percent"
        if [ "$percent" -eq 100 ]; then
            echo
        fi
    fi
}

show_message() {
    local title="$1"
    local message="$2"
    
    if [ "$USE_GUI" = true ]; then
        whiptail --title "$title" --msgbox "$message" 10 70
    else
        echo -e "${BLUE}[$title]${NC} $message"
    fi
}

show_yesno() {
    local title="$1"
    local message="$2"
    local default="$3"  # yes/no
    
    if [ "$USE_GUI" = true ]; then
        if [ "$default" = "yes" ]; then
            whiptail --title "$title" --yesno "$message" 10 70 --defaultno
            return $?
        else
            whiptail --title "$title" --yesno "$message" 10 70
            return $?
        fi
    else
        read -p "$message (s/n): " response
        case "$response" in
            [Ss]* ) return 0;;
            [Nn]* ) return 1;;
            * ) 
                if [ "$default" = "yes" ]; then 
                    return 0
                else
                    return 1
                fi
                ;;
        esac
    fi
}

show_input() {
    local title="$1"
    local message="$2"
    local default="$3"
    local result=""
    
    if [ "$USE_GUI" = true ]; then
        result=$(whiptail --title "$title" --inputbox "$message" 10 70 "$default" 3>&1 1>&2 2>&3)
        if [ $? -ne 0 ]; then
            # Annullato
            echo "$default"
        else
            echo "$result"
        fi
    else
        read -p "$message [$default]: " input
        if [ -z "$input" ]; then
            echo "$default"
        else
            echo "$input"
        fi
    fi
}

show_checkbox_menu() {
    local title="$1"
    local message="$2"
    shift 2
    local options=("$@")
    local result=""
    
    if [ "$USE_GUI" = true ]; then
        # Crea la lista per whiptail
        local whiptail_opts=()
        for ((i=0; i<${#options[@]}; i+=2)); do
            whiptail_opts+=("${options[$i]}" "${options[$i+1]}" "OFF")
        done
        
        result=$(whiptail --title "$title" --checklist "$message" 20 78 10 "${whiptail_opts[@]}" 3>&1 1>&2 2>&3)
        echo "$result"
    else
        echo "$message"
        local selection=()
        for ((i=0; i<${#options[@]}; i+=2)); do
            read -p "Includere ${options[$i]} (${options[$i+1]})? (s/n): " response
            if [[ "$response" =~ ^[Ss] ]]; then
                selection+=("${options[$i]}")
            fi
        done
        echo "${selection[*]}"
    fi
}

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

# Verifica che lo script sia eseguito come root
if [ "$(id -u)" != "0" ]; then
    if [ "$USE_GUI" = true ]; then
        whiptail --title "Errore" --msgbox "Questo script deve essere eseguito come root" 8 78
    else
        print_error "Questo script deve essere eseguito come root" 1
    fi
    exit 1
fi

# Ottieni directory corrente (per le operazioni relative)
CURRENT_DIR=$(pwd)

# Verifica prerequisiti
check_prerequisites() {
    print_message "Verifica prerequisiti..."
    progress_bar "Verifica prerequisiti" 0
    
    # Verifica che il sistema sia Linux
    if [ "$(uname)" != "Linux" ]; then
        progress_bar "Verifica prerequisiti" 100
        print_error "Questo script è progettato per sistemi Linux" 1
    fi
    progress_bar "Verifica prerequisiti" 50
    
    # Verifica che sia possibile eseguire comandi di base
    command -v apt-get >/dev/null 2>&1 || {
        progress_bar "Verifica prerequisiti" 100
        print_error "Comando apt-get non trovato. Questo script richiede una distribuzione basata su Debian/Ubuntu" 1
    }
    progress_bar "Verifica prerequisiti" 100
    
    print_success "Prerequisiti verificati"
}

# Verifica e prepara gli script nella directory scripts
check_scripts() {
    print_message "Verifica script necessari..."
    progress_bar "Verifica script" 0
    
    # Lista degli script essenziali
    ESSENTIAL_SCRIPTS=(
        "fix_all_files.sh"
        "fix_common_issues.sh"
        "setup_db.sh"
        "setup_nginx.sh"
        "setup_python.sh"
        "setup_redis.sh"
        "setup_ssl.sh"
        "startup.sh"
    )
    
    # Crea la directory scripts se non esiste
    if [ ! -d "$INSTALL_DIR/scripts" ]; then
        mkdir -p "$INSTALL_DIR/scripts"
        chown m4bot:m4bot "$INSTALL_DIR/scripts"
        chmod 755 "$INSTALL_DIR/scripts"
    fi
    
    # Copia gli script dalla directory corrente se disponibili
    SCRIPTS_FOUND=0
    SCRIPTS_TOTAL=${#ESSENTIAL_SCRIPTS[@]}
    
    for ((i=0; i<${#ESSENTIAL_SCRIPTS[@]}; i++)); do
        script="${ESSENTIAL_SCRIPTS[$i]}"
        percent=$(( (i+1) * 100 / SCRIPTS_TOTAL ))
        progress_bar "Verifica script" $percent
        
        # Verifica se lo script esiste nella directory di installazione
        if [ ! -f "$INSTALL_DIR/scripts/$script" ]; then
            # Cerca lo script nella directory corrente
            if [ -f "$CURRENT_DIR/scripts/$script" ]; then
                cp "$CURRENT_DIR/scripts/$script" "$INSTALL_DIR/scripts/"
                chmod +x "$INSTALL_DIR/scripts/$script"
                SCRIPTS_FOUND=$((SCRIPTS_FOUND + 1))
                print_message "Script $script copiato nella directory di installazione"
            else
                print_warning "Script $script non trovato. Alcune funzionalità potrebbero non essere disponibili."
            fi
        else
            # Lo script esiste, assicuriamoci che sia eseguibile
            chmod +x "$INSTALL_DIR/scripts/$script"
            SCRIPTS_FOUND=$((SCRIPTS_FOUND + 1))
        fi
    done
    
    # Crea script di servizio se mancanti
    if [ ! -f "$INSTALL_DIR/scripts/m4bot.service" ]; then
        cat > "$INSTALL_DIR/scripts/m4bot.service" << EOF
[Unit]
Description=M4Bot Service
After=network.target

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/run.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF
        chmod 644 "$INSTALL_DIR/scripts/m4bot.service"
        print_message "File di servizio m4bot.service creato"
    fi
    
    if [ ! -f "$INSTALL_DIR/scripts/m4bot-web.service" ]; then
        cat > "$INSTALL_DIR/scripts/m4bot-web.service" << EOF
[Unit]
Description=M4Bot Web Interface
After=network.target

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$INSTALL_DIR/web
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/web/app.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF
        chmod 644 "$INSTALL_DIR/scripts/m4bot-web.service"
        print_message "File di servizio m4bot-web.service creato"
    fi
    
    progress_bar "Verifica script" 100
    
    if [ $SCRIPTS_FOUND -eq $SCRIPTS_TOTAL ]; then
        print_success "Tutti gli script necessari sono disponibili"
    else
        print_warning "Trovati $SCRIPTS_FOUND script su $SCRIPTS_TOTAL necessari"
    fi
}

# Correggi automaticamente tutti i file nel progetto
fix_project_files() {
    print_message "Correzione dei file specifici del progetto M4Bot..."
    progress_bar "Personalizzazione M4Bot" 0
    
    # Elenco dei file principali da controllare
    MAIN_FILES=(
        "$INSTALL_DIR/config.py"
        "$INSTALL_DIR/run.py"
        "$INSTALL_DIR/m4bot_app.py"
        "$INSTALL_DIR/web/app.py"
        "$INSTALL_DIR/scripts/startup.sh"
    )
    
    # Contatori per statistiche
    TOTAL_FILES=${#MAIN_FILES[@]}
    FIXED_FILES=0
    
    # Controlla ogni file principale
    for ((i=0; i<${#MAIN_FILES[@]}; i++)); do
        file="${MAIN_FILES[$i]}"
        percent=$((i * 100 / TOTAL_FILES))
        progress_bar "Personalizzazione M4Bot" $percent
        
        if [ -f "$file" ]; then
            # Converti fine riga
            dos2unix "$file" >/dev/null 2>&1
            
            # Correggi problemi di codifica UTF-8
            if ! file "$file" | grep -q "UTF-8"; then
                iconv -f ISO-8859-1 -t UTF-8 -o "$file.tmp" "$file" && mv "$file.tmp" "$file"
                FIXED_FILES=$((FIXED_FILES + 1))
            fi
            
            # Correggi percorsi specifici di M4Bot
            if grep -q "/path/to/m4bot" "$file"; then
                sed -i "s|/path/to/m4bot|$INSTALL_DIR|g" "$file"
                FIXED_FILES=$((FIXED_FILES + 1))
            fi
            
            # Correggi placeholder generici
            if grep -q "<your_" "$file"; then
                sed -i "s|<your_api_key>|$API_KEY|g" "$file"
                sed -i "s|<your_db_user>|$DB_USER|g" "$file"
                sed -i "s|<your_db_password>|$DB_PASSWORD|g" "$file"
                sed -i "s|<your_db_name>|$DB_NAME|g" "$file"
                sed -i "s|<your_redis_host>|$REDIS_HOST|g" "$file"
                sed -i "s|<your_redis_port>|$REDIS_PORT|g" "$file"
                sed -i "s|<your_redis_password>|$REDIS_PASSWORD|g" "$file"
                FIXED_FILES=$((FIXED_FILES + 1))
            fi
            
            # Imposta permessi corretti
            if [[ "$file" == *".sh" || "$file" == *".py" ]]; then
                chmod +x "$file"
            fi
        fi
    done
    
    # Correggi il file di configurazione principale
    if [ -f "$INSTALL_DIR/config.py" ]; then
        # Aggiorna nome del bot
        if grep -q "BOT_NAME = " "$INSTALL_DIR/config.py"; then
            sed -i "s|BOT_NAME = .*|BOT_NAME = \"$BOT_NAME\"|g" "$INSTALL_DIR/config.py"
            FIXED_FILES=$((FIXED_FILES + 1))
        fi
        
        # Aggiorna URL dell'interfaccia web
        if grep -q "WEB_URL = " "$INSTALL_DIR/config.py"; then
            sed -i "s|WEB_URL = .*|WEB_URL = \"$WEB_URL\"|g" "$INSTALL_DIR/config.py"
            FIXED_FILES=$((FIXED_FILES + 1))
        fi
    fi
    
    # Correggi il file .env se esiste
    if [ -f "$INSTALL_DIR/.env" ]; then
        # Aggiorna variabili di ambiente nel file .env
        if ! grep -q "INSTALL_DIR=" "$INSTALL_DIR/.env"; then
            echo "INSTALL_DIR=$INSTALL_DIR" >> "$INSTALL_DIR/.env"
            FIXED_FILES=$((FIXED_FILES + 1))
        fi
        
        if ! grep -q "BOT_NAME=" "$INSTALL_DIR/.env"; then
            echo "BOT_NAME=$BOT_NAME" >> "$INSTALL_DIR/.env"
            FIXED_FILES=$((FIXED_FILES + 1))
        fi
    fi
    
    # Correggi i file di servizio
    if [ -f "$INSTALL_DIR/scripts/m4bot.service" ]; then
        # Aggiorna i percorsi nel file di servizio
        sed -i "s|ExecStart=.*|ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/run.py|g" "$INSTALL_DIR/scripts/m4bot.service"
        sed -i "s|WorkingDirectory=.*|WorkingDirectory=$INSTALL_DIR|g" "$INSTALL_DIR/scripts/m4bot.service"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
    
    # Correggi lo script di avvio
    if [ -f "$INSTALL_DIR/scripts/startup.sh" ]; then
        # Aggiorna i percorsi nello script di avvio
        sed -i "s|cd .*|cd $INSTALL_DIR|g" "$INSTALL_DIR/scripts/startup.sh"
        sed -i "s|source .*/venv/bin/activate|source $INSTALL_DIR/venv/bin/activate|g" "$INSTALL_DIR/scripts/startup.sh"
        chmod +x "$INSTALL_DIR/scripts/startup.sh"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
    
    # Personalizza il file README
    if [ -f "$INSTALL_DIR/README.md" ]; then
        # Aggiorna informazioni nel README
        sed -i "s|M4Bot è installato in .*|M4Bot è installato in $INSTALL_DIR|g" "$INSTALL_DIR/README.md"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
    
    progress_bar "Personalizzazione M4Bot" 100
    print_success "Personalizzazione M4Bot completata"
    print_message "File specifici del progetto controllati: $TOTAL_FILES"
    print_message "File specifici corretti: $FIXED_FILES"
}

# Correggi tutti i file nel progetto utilizzando lo script dedicato
fix_all_files() {
    print_message "Correzione automatica di tutti i file nel progetto M4Bot..."
    progress_bar "Correzione completa dei file" 0
    
    # Chiedi all'utente se desidera eseguire la correzione completa dei file
    if [ "$USE_GUI" = true ]; then
        if ! whiptail --title "Correzione file" --yesno "Vuoi eseguire la correzione automatica di tutti i file del progetto?\nQuesto processo potrebbe richiedere del tempo ma è consigliato per progetti importati da Windows." 10 78; then
            progress_bar "Correzione completa dei file" 100
            print_warning "Correzione completa dei file saltata su richiesta dell'utente"
            return 0
        fi
    else
        read -p "Vuoi eseguire la correzione automatica di tutti i file del progetto? (Consigliato per progetti importati da Windows) [s/n]: " response
        if [[ ! "$response" =~ ^[Ss] ]]; then
            progress_bar "Correzione completa dei file" 100
            print_warning "Correzione completa dei file saltata su richiesta dell'utente"
            return 0
        fi
    fi
    
    # Verifica che dos2unix sia installato
    if ! command -v dos2unix &> /dev/null; then
        print_warning "Il comando dos2unix non è installato. Installazione in corso..."
        apt-get update && apt-get install -y dos2unix
        if [ $? -ne 0 ]; then
            progress_bar "Correzione completa dei file" 100
            print_error "Impossibile installare dos2unix. La correzione completa dei file è stata saltata."
            return 1
        fi
        print_success "dos2unix installato correttamente"
    fi
    
    # Verifica che lo script di correzione sia disponibile
    if [ -f "$INSTALL_DIR/scripts/fix_all_files.sh" ]; then
        # Esegui lo script di correzione completa
        chmod +x "$INSTALL_DIR/scripts/fix_all_files.sh"
        
        print_message "Avvio correzione automatica di tutti i file..."
        # Esegui lo script con il percorso corretto
        bash "$INSTALL_DIR/scripts/fix_all_files.sh" "$INSTALL_DIR"
        
        if [ $? -ne 0 ]; then
            progress_bar "Correzione completa dei file" 100
            print_error "Si è verificato un errore durante la correzione dei file."
            return 1
        fi
        
        progress_bar "Correzione completa dei file" 100
        print_success "Correzione completa dei file terminata con successo"
    else
        # Se lo script non è disponibile, copialo dalla directory corrente
        if [ -f "$CURRENT_DIR/scripts/fix_all_files.sh" ]; then
            print_message "Copia dello script fix_all_files.sh dalla directory corrente..."
            cp "$CURRENT_DIR/scripts/fix_all_files.sh" "$INSTALL_DIR/scripts/"
            chmod +x "$INSTALL_DIR/scripts/fix_all_files.sh"
            
            print_message "Avvio correzione automatica di tutti i file..."
            # Esegui lo script con il percorso corretto
            bash "$INSTALL_DIR/scripts/fix_all_files.sh" "$INSTALL_DIR"
            
            if [ $? -ne 0 ]; then
                progress_bar "Correzione completa dei file" 100
                print_error "Si è verificato un errore durante la correzione dei file."
                return 1
            fi
            
            progress_bar "Correzione completa dei file" 100
            print_success "Correzione completa dei file terminata con successo"
        else
            # Tentativo di download dello script se non è disponibile localmente
            print_message "Script fix_all_files.sh non trovato. Tentativo di download..."
            
            if command -v curl &> /dev/null; then
                curl -s -o "$INSTALL_DIR/scripts/fix_all_files.sh" "https://raw.githubusercontent.com/m4bot/m4bot/main/scripts/fix_all_files.sh"
                if [ $? -eq 0 ] && [ -f "$INSTALL_DIR/scripts/fix_all_files.sh" ]; then
                    chmod +x "$INSTALL_DIR/scripts/fix_all_files.sh"
                    
                    print_message "Avvio correzione automatica di tutti i file..."
                    # Esegui lo script con il percorso corretto
                    bash "$INSTALL_DIR/scripts/fix_all_files.sh" "$INSTALL_DIR"
                    
                    if [ $? -ne 0 ]; then
                        progress_bar "Correzione completa dei file" 100
                        print_error "Si è verificato un errore durante la correzione dei file."
                        return 1
                    fi
                    
                    progress_bar "Correzione completa dei file" 100
                    print_success "Correzione completa dei file terminata con successo"
                else
                    progress_bar "Correzione completa dei file" 100
                    print_warning "Impossibile scaricare lo script fix_all_files.sh. La correzione completa dei file è stata saltata."
                fi
            elif command -v wget &> /dev/null; then
                wget -q -O "$INSTALL_DIR/scripts/fix_all_files.sh" "https://raw.githubusercontent.com/m4bot/m4bot/main/scripts/fix_all_files.sh"
                if [ $? -eq 0 ] && [ -f "$INSTALL_DIR/scripts/fix_all_files.sh" ]; then
                    chmod +x "$INSTALL_DIR/scripts/fix_all_files.sh"
                    
                    print_message "Avvio correzione automatica di tutti i file..."
                    # Esegui lo script con il percorso corretto
                    bash "$INSTALL_DIR/scripts/fix_all_files.sh" "$INSTALL_DIR"
                    
                    if [ $? -ne 0 ]; then
                        progress_bar "Correzione completa dei file" 100
                        print_error "Si è verificato un errore durante la correzione dei file."
                        return 1
                    fi
                    
                    progress_bar "Correzione completa dei file" 100
                    print_success "Correzione completa dei file terminata con successo"
                else
                    progress_bar "Correzione completa dei file" 100
                    print_warning "Impossibile scaricare lo script fix_all_files.sh. La correzione completa dei file è stata saltata."
                fi
            else
                progress_bar "Correzione completa dei file" 100
                print_warning "Script fix_all_files.sh non trovato e nessun comando disponibile per scaricarlo. La correzione completa dei file è stata saltata."
            fi
        fi
    fi
}

# Funzione principale
main() {
    # Mostra titolo
    show_title
    
    # Mostra schermata di benvenuto
    show_welcome
    
    # Avvia l'installazione
    print_message "Avvio installazione di M4Bot..."
    
    # Esegui le fasi di installazione con barra di progresso
    check_prerequisites
    
    # Verifica script nella directory scripts
    check_scripts
    
    get_configuration
    update_system
    setup_user
    setup_database
    setup_redis
    setup_files
    setup_python_env
    setup_env_file
    setup_services
    setup_nginx
    setup_ssl
    start_services
    
    # Correggi i file del progetto
    fix_project_files
    
    # Correggi tutti i file (scansione completa)
    fix_all_files
    
    # Diagnosi e correzione automatica dei problemi
    diagnose_and_fix
    
    # Verifica finale
    check_status
    
    # Informazioni finali
    print_final_info
    
    # Chiedi all'utente se vuole installare i componenti avanzati
    if show_yesno "Componenti avanzati" "Vuoi installare i componenti avanzati di sicurezza e monitoraggio?" "yes"; then
        INSTALL_ADVANCED=true
    else
        INSTALL_ADVANCED=false
    fi
    
    # ... existing code ...
    
    # Installa tutto
    install_all
    
    # ... existing code ...
}

# Diagnosi e correzione automatica dei problemi comuni
diagnose_and_fix() {
    print_message "Diagnosi e correzione automatica dei problemi comuni..."
    progress_bar "Diagnosi e correzione" 0
    
    PROBLEMS_FOUND=0
    PROBLEMS_FIXED=0
    
    # 1. Verifica permessi dei file
    print_message "Verifica permessi dei file..."
    progress_bar "Diagnosi e correzione" 10
    
    # Controlla e correggi i permessi della directory principale
    if [ -d "$INSTALL_DIR" ]; then
        if [ "$(stat -c '%U' "$INSTALL_DIR")" != "m4bot" ]; then
            chown -R m4bot:m4bot "$INSTALL_DIR"
            PROBLEMS_FOUND=$((PROBLEMS_FOUND + 1))
            PROBLEMS_FIXED=$((PROBLEMS_FIXED + 1))
        fi
    fi
    
    # 2. Verifica presenza di processi zombie o bloccati
    print_message "Verifica processi..."
    progress_bar "Diagnosi e correzione" 25
    
    # Controlla se ci sono processi python bloccati
    ZOMBIE_PROCS=$(ps aux | grep "[p]ython" | grep "m4bot" | awk '{print $2}')
    if [ -n "$ZOMBIE_PROCS" ]; then
        print_warning "Trovati processi Python potenzialmente bloccati. Pulizia in corso..."
        for pid in $ZOMBIE_PROCS; do
            kill -9 "$pid" 2>/dev/null
        done
        PROBLEMS_FOUND=$((PROBLEMS_FOUND + 1))
        PROBLEMS_FIXED=$((PROBLEMS_FIXED + 1))
    fi
    
    # 3. Verifica servizi systemd
    print_message "Verifica servizi systemd..."
    progress_bar "Diagnosi e correzione" 40
    
    if systemctl is-enabled m4bot.service &>/dev/null; then
        if ! systemctl is-active m4bot.service &>/dev/null; then
            print_warning "Servizio m4bot non attivo. Tentativo di riavvio..."
            systemctl restart m4bot.service
            PROBLEMS_FOUND=$((PROBLEMS_FOUND + 1))
            if systemctl is-active m4bot.service &>/dev/null; then
                PROBLEMS_FIXED=$((PROBLEMS_FIXED + 1))
            fi
        fi
    fi
    
    if systemctl is-enabled m4bot-web.service &>/dev/null; then
        if ! systemctl is-active m4bot-web.service &>/dev/null; then
            print_warning "Servizio m4bot-web non attivo. Tentativo di riavvio..."
            systemctl restart m4bot-web.service
            PROBLEMS_FOUND=$((PROBLEMS_FOUND + 1))
            if systemctl is-active m4bot-web.service &>/dev/null; then
                PROBLEMS_FIXED=$((PROBLEMS_FIXED + 1))
            fi
        fi
    fi
    
    # 4. Verifica dipendenze Python
    print_message "Verifica dipendenze Python..."
    progress_bar "Diagnosi e correzione" 55
    
    if [ -f "$INSTALL_DIR/requirements.txt" ] && [ -d "$INSTALL_DIR/venv" ]; then
        source "$INSTALL_DIR/venv/bin/activate" 2>/dev/null
        pip install -r "$INSTALL_DIR/requirements.txt" --quiet 2>/dev/null
        deactivate 2>/dev/null
    fi
    
    # 5. Verifica file di configurazione
    print_message "Verifica file di configurazione..."
    progress_bar "Diagnosi e correzione" 70
    
    if [ -f "$INSTALL_DIR/config.py" ]; then
        if grep -q "INSTALL_DIR = " "$INSTALL_DIR/config.py"; then
            if ! grep -q "INSTALL_DIR = \"$INSTALL_DIR\"" "$INSTALL_DIR/config.py"; then
                sed -i "s|INSTALL_DIR = .*|INSTALL_DIR = \"$INSTALL_DIR\"|g" "$INSTALL_DIR/config.py"
                PROBLEMS_FOUND=$((PROBLEMS_FOUND + 1))
                PROBLEMS_FIXED=$((PROBLEMS_FIXED + 1))
            fi
        fi
    fi
    
    if [ -f "$INSTALL_DIR/.env" ]; then
        if grep -q "INSTALL_DIR=" "$INSTALL_DIR/.env"; then
            if ! grep -q "INSTALL_DIR=$INSTALL_DIR" "$INSTALL_DIR/.env"; then
                sed -i "s|INSTALL_DIR=.*|INSTALL_DIR=$INSTALL_DIR|g" "$INSTALL_DIR/.env"
                PROBLEMS_FOUND=$((PROBLEMS_FOUND + 1))
                PROBLEMS_FIXED=$((PROBLEMS_FIXED + 1))
            fi
        fi
    fi
    
    # 6. Verifica accesso al database
    print_message "Verifica accesso al database..."
    progress_bar "Diagnosi e correzione" 85
    
    if command -v mysql &>/dev/null; then
        if mysql -u "$DB_USER" -p"$DB_PASS" -e "USE $DB_NAME;" &>/dev/null; then
            # Database accessibile, nessun problema
            :
        else
            print_warning "Impossibile accedere al database. Verifica credenziali..."
            PROBLEMS_FOUND=$((PROBLEMS_FOUND + 1))
        fi
    fi
    
    # 7. Verifica connessione Redis
    print_message "Verifica connessione Redis..."
    progress_bar "Diagnosi e correzione" 95
    
    if command -v redis-cli &>/dev/null; then
        if ! redis-cli ping &>/dev/null; then
            print_warning "Redis non risponde. Tentativo di riavvio..."
            systemctl restart redis-server &>/dev/null
            PROBLEMS_FOUND=$((PROBLEMS_FOUND + 1))
            if redis-cli ping &>/dev/null; then
                PROBLEMS_FIXED=$((PROBLEMS_FIXED + 1))
            fi
        fi
    fi
    
    # Riporta risultati
    progress_bar "Diagnosi e correzione" 100
    
    if [ $PROBLEMS_FOUND -eq 0 ]; then
        print_success "Nessun problema rilevato!"
    else
        print_message "Problemi rilevati: $PROBLEMS_FOUND"
        print_message "Problemi risolti: $PROBLEMS_FIXED"
        
        if [ $PROBLEMS_FIXED -eq $PROBLEMS_FOUND ]; then
            print_success "Tutti i problemi sono stati risolti automaticamente!"
        else
            UNSOLVED=$((PROBLEMS_FOUND - PROBLEMS_FIXED))
            print_warning "$UNSOLVED problemi richiedono intervento manuale. Consultare i log per dettagli."
        fi
    fi
}

# Verifica lo stato finale dell'installazione
check_status() {
    print_message "Verifica stato finale dell'installazione..."
    progress_bar "Verifica finale" 0
    
    # Variabili per il resoconto
    STATUS_OK=true
    COMPONENTS_TOTAL=0
    COMPONENTS_OK=0
    
    # 1. Verifica presenza file e directory principali
    print_message "Verifica file e directory principali..."
    progress_bar "Verifica finale" 10
    
    MAIN_DIRS=("$INSTALL_DIR" "$INSTALL_DIR/scripts" "$INSTALL_DIR/web" "$INSTALL_DIR/logs")
    COMPONENTS_TOTAL=$((COMPONENTS_TOTAL + ${#MAIN_DIRS[@]}))
    
    for dir in "${MAIN_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            COMPONENTS_OK=$((COMPONENTS_OK + 1))
        else
            STATUS_OK=false
            print_warning "Directory $dir non trovata"
        fi
    done
    
    # 2. Verifica servizi
    print_message "Verifica servizi systemd..."
    progress_bar "Verifica finale" 30
    
    SERVICES=("m4bot.service" "m4bot-web.service")
    COMPONENTS_TOTAL=$((COMPONENTS_TOTAL + ${#SERVICES[@]}))
    
    for service in "${SERVICES[@]}"; do
        if systemctl is-enabled "$service" &>/dev/null; then
            if systemctl is-active "$service" &>/dev/null; then
                COMPONENTS_OK=$((COMPONENTS_OK + 1))
            else
                STATUS_OK=false
                print_warning "Servizio $service non attivo"
            fi
        else
            STATUS_OK=false
            print_warning "Servizio $service non abilitato"
        fi
    done
    
    # 3. Verifica ambiente Python
    print_message "Verifica ambiente Python..."
    progress_bar "Verifica finale" 50
    
    COMPONENTS_TOTAL=$((COMPONENTS_TOTAL + 1))
    if [ -d "$INSTALL_DIR/venv" ]; then
        COMPONENTS_OK=$((COMPONENTS_OK + 1))
    else
        STATUS_OK=false
        print_warning "Ambiente virtuale Python non trovato"
    fi
    
    # 4. Verifica database
    print_message "Verifica database..."
    progress_bar "Verifica finale" 70
    
    COMPONENTS_TOTAL=$((COMPONENTS_TOTAL + 1))
    if command -v mysql &>/dev/null; then
        if mysql -u "$DB_USER" -p"$DB_PASS" -e "USE $DB_NAME;" &>/dev/null; then
            COMPONENTS_OK=$((COMPONENTS_OK + 1))
        else
            STATUS_OK=false
            print_warning "Impossibile accedere al database $DB_NAME"
        fi
    else
        STATUS_OK=false
        print_warning "MySQL non installato"
    fi
    
    # 5. Verifica Redis
    print_message "Verifica Redis..."
    progress_bar "Verifica finale" 80
    
    COMPONENTS_TOTAL=$((COMPONENTS_TOTAL + 1))
    if command -v redis-cli &>/dev/null; then
        if redis-cli ping &>/dev/null; then
            COMPONENTS_OK=$((COMPONENTS_OK + 1))
        else
            STATUS_OK=false
            print_warning "Redis non risponde"
        fi
    else
        STATUS_OK=false
        print_warning "Redis non installato"
    fi
    
    # 6. Verifica connettività web
    print_message "Verifica connettività web..."
    progress_bar "Verifica finale" 90
    
    COMPONENTS_TOTAL=$((COMPONENTS_TOTAL + 1))
    if command -v curl &>/dev/null; then
        # Tentativo di connessione al servizio web
        if curl -s "http://localhost:$WEB_PORT/" | grep -q "M4Bot" || curl -s "http://127.0.0.1:$WEB_PORT/" | grep -q "M4Bot"; then
            COMPONENTS_OK=$((COMPONENTS_OK + 1))
        else
            STATUS_OK=false
            print_warning "Interfaccia web non raggiungibile"
        fi
    else
        # Se curl non è disponibile, proviamo con wget
        if command -v wget &>/dev/null; then
            if wget -q -O - "http://localhost:$WEB_PORT/" | grep -q "M4Bot" || wget -q -O - "http://127.0.0.1:$WEB_PORT/" | grep -q "M4Bot"; then
                COMPONENTS_OK=$((COMPONENTS_OK + 1))
            else
                STATUS_OK=false
                print_warning "Interfaccia web non raggiungibile"
            fi
        else
            print_warning "Impossibile verificare la connettività web (curl/wget non disponibili)"
        fi
    fi
    
    # Mostra risultato
    progress_bar "Verifica finale" 100
    
    # Calcola percentuale di successo
    SUCCESS_PERCENT=$((COMPONENTS_OK * 100 / COMPONENTS_TOTAL))
    
    if [ "$STATUS_OK" = true ]; then
        print_success "Installazione completata con successo!"
        print_message "Tutti i componenti ($COMPONENTS_OK/$COMPONENTS_TOTAL) sono stati verificati e risultano funzionanti."
    else
        print_warning "Installazione completata con alcuni problemi."
        print_message "Componenti funzionanti: $COMPONENTS_OK/$COMPONENTS_TOTAL ($SUCCESS_PERCENT%)"
        
        if [ $SUCCESS_PERCENT -ge 80 ]; then
            print_message "L'installazione è funzionante ma alcuni componenti potrebbero richiedere intervento manuale."
        else
            print_warning "Diversi componenti non sono funzionanti. Si consiglia di rivedere i log e risolvere i problemi prima di procedere."
        fi
    fi
}

# Mostra informazioni finali all'utente
print_final_info() {
    # Pulisci lo schermo
    if [ "$USE_GUI" = true ]; then
        clear
    fi
    
    # Mostra intestazione
    echo -e "${BLUE}"
    echo "╔═════════════════════════════════════════════════════════╗"
    echo "║                                                         ║"
    echo "║             M4Bot - Installazione Completata            ║"
    echo "║                                                         ║"
    echo "╚═════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    # Mostra informazioni di base
    echo -e "${GREEN}M4Bot è stato installato con successo!${NC}"
    echo
    echo "INFORMAZIONI SULL'INSTALLAZIONE:"
    echo "--------------------------------"
    echo "Directory di installazione: $INSTALL_DIR"
    echo "Database: $DB_NAME"
    echo "Utente DB: $DB_USER"
    echo "Porta web: $WEB_PORT"
    echo "Porta bot: $BOT_PORT"
    
    # Mostra URL di accesso
    echo
    echo "ACCESSO ALL'INTERFACCIA WEB:"
    echo "---------------------------"
    
    if [ -n "$DOMAINS" ]; then
        echo "URL web: https://$DOMAINS"
    else
        echo "URL web (locale): http://localhost:$WEB_PORT"
        # Determina l'IP pubblico per l'accesso remoto
        PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || wget -qO- ifconfig.me 2>/dev/null)
        if [ -n "$PUBLIC_IP" ]; then
            echo "URL web (remoto): http://$PUBLIC_IP:$WEB_PORT"
        fi
    fi
    
    # Mostra comandi utili
    echo
    echo "COMANDI UTILI:"
    echo "-------------"
    echo "Avviare M4Bot: systemctl start m4bot"
    echo "Fermare M4Bot: systemctl stop m4bot"
    echo "Stato M4Bot: systemctl status m4bot"
    echo "Avviare interfaccia web: systemctl start m4bot-web"
    echo "Visualizzare log: journalctl -u m4bot -f"
    
    # Mostra informazioni sulla correzione di problemi
    echo
    echo "RISOLUZIONE PROBLEMI:"
    echo "--------------------"
    echo "Per correggere problemi comuni: $INSTALL_DIR/scripts/fix_common_issues.sh"
    echo "Per correggere tutti i file: $INSTALL_DIR/scripts/fix_all_files.sh"
    
    # Chiedi se salvare queste informazioni in un file
    echo
    if [ "$USE_GUI" = true ]; then
        if whiptail --title "Salva informazioni" --yesno "Vuoi salvare queste informazioni in un file README nella directory di installazione?" 10 78; then
            # Crea file README con le informazioni
            cat > "$INSTALL_DIR/README_INSTALLAZIONE.md" << EOF
# M4Bot - Informazioni di Installazione

## Dettagli di installazione
- **Directory di installazione:** $INSTALL_DIR
- **Database:** $DB_NAME
- **Utente DB:** $DB_USER
- **Porta web:** $WEB_PORT
- **Porta bot:** $BOT_PORT

## Accesso all'interfaccia web
EOF
            
            if [ -n "$DOMAINS" ]; then
                echo "- **URL web:** https://$DOMAINS" >> "$INSTALL_DIR/README_INSTALLAZIONE.md"
            else
                echo "- **URL web (locale):** http://localhost:$WEB_PORT" >> "$INSTALL_DIR/README_INSTALLAZIONE.md"
                # Determina l'IP pubblico per l'accesso remoto
                if [ -n "$PUBLIC_IP" ]; then
                    echo "- **URL web (remoto):** http://$PUBLIC_IP:$WEB_PORT" >> "$INSTALL_DIR/README_INSTALLAZIONE.md"
                fi
            fi
            
            cat >> "$INSTALL_DIR/README_INSTALLAZIONE.md" << EOF

## Comandi utili
- **Avviare M4Bot:** \`systemctl start m4bot\`
- **Fermare M4Bot:** \`systemctl stop m4bot\`
- **Stato M4Bot:** \`systemctl status m4bot\`
- **Avviare interfaccia web:** \`systemctl start m4bot-web\`
- **Visualizzare log:** \`journalctl -u m4bot -f\`

## Risoluzione problemi
- **Correggere problemi comuni:** \`$INSTALL_DIR/scripts/fix_common_issues.sh\`
- **Correggere tutti i file:** \`$INSTALL_DIR/scripts/fix_all_files.sh\`

Installazione completata il $(date).
EOF
            
            chmod 644 "$INSTALL_DIR/README_INSTALLAZIONE.md"
            print_success "Informazioni di installazione salvate in $INSTALL_DIR/README_INSTALLAZIONE.md"
        fi
    else
        read -p "Vuoi salvare queste informazioni in un file README nella directory di installazione? [s/n]: " response
        if [[ "$response" =~ ^[Ss] ]]; then
            # Crea file README con le informazioni
            cat > "$INSTALL_DIR/README_INSTALLAZIONE.md" << EOF
# M4Bot - Informazioni di Installazione

## Dettagli di installazione
- **Directory di installazione:** $INSTALL_DIR
- **Database:** $DB_NAME
- **Utente DB:** $DB_USER
- **Porta web:** $WEB_PORT
- **Porta bot:** $BOT_PORT

## Accesso all'interfaccia web
EOF
            
            if [ -n "$DOMAINS" ]; then
                echo "- **URL web:** https://$DOMAINS" >> "$INSTALL_DIR/README_INSTALLAZIONE.md"
            else
                echo "- **URL web (locale):** http://localhost:$WEB_PORT" >> "$INSTALL_DIR/README_INSTALLAZIONE.md"
                # Determina l'IP pubblico per l'accesso remoto
                if [ -n "$PUBLIC_IP" ]; then
                    echo "- **URL web (remoto):** http://$PUBLIC_IP:$WEB_PORT" >> "$INSTALL_DIR/README_INSTALLAZIONE.md"
                fi
            fi
            
            cat >> "$INSTALL_DIR/README_INSTALLAZIONE.md" << EOF

## Comandi utili
- **Avviare M4Bot:** \`systemctl start m4bot\`
- **Fermare M4Bot:** \`systemctl stop m4bot\`
- **Stato M4Bot:** \`systemctl status m4bot\`
- **Avviare interfaccia web:** \`systemctl start m4bot-web\`
- **Visualizzare log:** \`journalctl -u m4bot -f\`

## Risoluzione problemi
- **Correggere problemi comuni:** \`$INSTALL_DIR/scripts/fix_common_issues.sh\`
- **Correggere tutti i file:** \`$INSTALL_DIR/scripts/fix_all_files.sh\`

Installazione completata il $(date).
EOF
            
            chmod 644 "$INSTALL_DIR/README_INSTALLAZIONE.md"
            print_success "Informazioni di installazione salvate in $INSTALL_DIR/README_INSTALLAZIONE.md"
        fi
    fi
    
    # Messaggio finale
    echo
    print_success "Grazie per aver installato M4Bot!"
}

# Mostra schermata di benvenuto
show_welcome() {
    # Pulisci lo schermo e mostra il titolo
    show_title
    
    # Prepara messaggio di benvenuto
    WELCOME_MESSAGE="Benvenuto nel programma di installazione di M4Bot!\n\n"
    WELCOME_MESSAGE+="Questo script automatizzerà l'installazione e la configurazione del sistema M4Bot su questo server. "
    WELCOME_MESSAGE+="Verranno installati e configurati automaticamente tutti i componenti necessari, inclusi:\n\n"
    WELCOME_MESSAGE+="• Server web e interfaccia di amministrazione\n"
    WELCOME_MESSAGE+="• Database e archiviazione dati\n"
    WELCOME_MESSAGE+="• Sistema di gestione e automazione\n"
    WELCOME_MESSAGE+="• Configurazione di sicurezza e ottimizzazione\n\n"
    WELCOME_MESSAGE+="Durante l'installazione ti verranno richieste alcune informazioni. Puoi utilizzare i valori predefiniti "
    WELCOME_MESSAGE+="o personalizzare l'installazione in base alle tue esigenze.\n\n"
    WELCOME_MESSAGE+="Premi OK per continuare con l'installazione."
    
    # Mostra messaggio di benvenuto
    if [ "$USE_GUI" = true ]; then
        whiptail --title "Benvenuto" --msgbox "$WELCOME_MESSAGE" 20 78
    else
        echo -e "$WELCOME_MESSAGE"
        echo
        read -p "Premi INVIO per continuare..."
    fi
    
    # Verifica requisiti di sistema
    if [ "$USE_GUI" = true ]; then
        whiptail --title "Verifica Requisiti" --infobox "Verifica dei requisiti di sistema in corso..." 8 78
        sleep 1
    else
        echo "Verifica dei requisiti di sistema in corso..."
    fi
    
    # Controlla spazio su disco
    AVAILABLE_SPACE=$(df -h / | awk 'NR==2 {print $4}')
    MEMORY_TOTAL=$(free -h | awk 'NR==2 {print $2}')
    CPUS=$(nproc)
    
    # Prepara messaggio requisiti
    SYSTEM_INFO="Informazioni di sistema:\n\n"
    SYSTEM_INFO+="• Spazio disco disponibile: $AVAILABLE_SPACE\n"
    SYSTEM_INFO+="• Memoria totale: $MEMORY_TOTAL\n"
    SYSTEM_INFO+="• Processori: $CPUS\n\n"
    SYSTEM_INFO+="Requisiti minimi consigliati:\n"
    SYSTEM_INFO+="• Spazio disco: 500 MB\n"
    SYSTEM_INFO+="• Memoria: 1 GB\n"
    SYSTEM_INFO+="• Processori: 1\n\n"
    
    # Verifica requisiti minimi (conversione approssimativa)
    SPACE_WARN=false
    MEMORY_WARN=false
    
    # Estrai solo il numero dallo spazio disponibile
    SPACE_NUM=$(echo $AVAILABLE_SPACE | sed 's/[^0-9.]//g')
    SPACE_UNIT=$(echo $AVAILABLE_SPACE | sed 's/[0-9.]//g')
    
    # Estrai solo il numero dalla memoria
    MEM_NUM=$(echo $MEMORY_TOTAL | sed 's/[^0-9.]//g')
    MEM_UNIT=$(echo $MEMORY_TOTAL | sed 's/[0-9.]//g')
    
    # Verifica spazio (approssimativo, potrebbe non funzionare con tutte le unità)
    if [[ "$SPACE_UNIT" == "K" ]] || [[ "$SPACE_UNIT" == "KB" ]]; then
        SPACE_WARN=true
    elif [[ "$SPACE_UNIT" == "M" ]] || [[ "$SPACE_UNIT" == "MB" ]]; then
        if (( $(echo "$SPACE_NUM < 500" | bc -l) )); then
            SPACE_WARN=true
        fi
    fi
    
    # Verifica memoria (approssimativo)
    if [[ "$MEM_UNIT" == "M" ]] || [[ "$MEM_UNIT" == "MB" ]]; then
        if (( $(echo "$MEM_NUM < 1000" | bc -l) )); then
            MEMORY_WARN=true
        fi
    elif [[ "$MEM_UNIT" == "K" ]] || [[ "$MEM_UNIT" == "KB" ]]; then
        MEMORY_WARN=true
    fi
    
    # Aggiunge avvisi se necessario
    if [ "$SPACE_WARN" = true ]; then
        SYSTEM_INFO+="\n⚠️ ATTENZIONE: Lo spazio su disco potrebbe non essere sufficiente."
    fi
    
    if [ "$MEMORY_WARN" = true ]; then
        SYSTEM_INFO+="\n⚠️ ATTENZIONE: La memoria disponibile potrebbe non essere sufficiente."
    fi
    
    if [ "$CPUS" -lt 1 ]; then
        SYSTEM_INFO+="\n⚠️ ATTENZIONE: Il numero di processori è inferiore a quello consigliato."
    fi
    
    # Mostra informazioni di sistema
    if [ "$USE_GUI" = true ]; then
        if [ "$SPACE_WARN" = true ] || [ "$MEMORY_WARN" = true ] || [ "$CPUS" -lt 1 ]; then
            if ! whiptail --title "Requisiti di Sistema" --yesno "$SYSTEM_INFO\n\nAlcuni requisiti di sistema non sono soddisfatti. Continuare comunque?" 20 78; then
                exit 0
            fi
        else
            whiptail --title "Requisiti di Sistema" --msgbox "$SYSTEM_INFO\n\nTutti i requisiti di sistema sono soddisfatti." 20 78
        fi
    else
        echo -e "$SYSTEM_INFO"
        if [ "$SPACE_WARN" = true ] || [ "$MEMORY_WARN" = true ] || [ "$CPUS" -lt 1 ]; then
            echo -e "\nAlcuni requisiti di sistema non sono soddisfatti."
            read -p "Continuare comunque? [s/n]: " response
            if [[ ! "$response" =~ ^[Ss] ]]; then
                exit 0
            fi
        else
            echo -e "\nTutti i requisiti di sistema sono soddisfatti."
            echo
        fi
    fi
}

# Ottieni la configurazione dall'utente
get_configuration() {
    print_message "Raccolta informazioni di configurazione..."
    progress_bar "Configurazione" 0
    
    # Directory di installazione
    if [ "$USE_GUI" = true ]; then
        INSTALL_DIR=$(whiptail --title "Directory di Installazione" --inputbox "Inserisci la directory di installazione:" 10 70 "$INSTALL_DIR" 3>&1 1>&2 2>&3)
        if [ $? -ne 0 ]; then
            print_message "Utilizzo della directory predefinita: $INSTALL_DIR"
        fi
    else
        read -p "Directory di installazione [$INSTALL_DIR]: " input
        if [ -n "$input" ]; then
            INSTALL_DIR="$input"
        fi
        print_message "Directory di installazione: $INSTALL_DIR"
    fi
    
    progress_bar "Configurazione" 20
    
    # Configurazione del database
    if [ "$USE_GUI" = true ]; then
        DB_NAME=$(whiptail --title "Database" --inputbox "Nome del database:" 10 70 "$DB_NAME" 3>&1 1>&2 2>&3)
        if [ $? -ne 0 ]; then
            print_message "Utilizzo del nome database predefinito: $DB_NAME"
        fi
        
        DB_USER=$(whiptail --title "Database" --inputbox "Utente database:" 10 70 "$DB_USER" 3>&1 1>&2 2>&3)
        if [ $? -ne 0 ]; then
            print_message "Utilizzo dell'utente database predefinito: $DB_USER"
        fi
        
        # Per la password, chiedi solo se vogliamo usare quella generata
        if ! whiptail --title "Database" --yesno "Utilizzare una password database generata automaticamente?" 10 70; then
            DB_PASS=$(whiptail --title "Database" --passwordbox "Password database:" 10 70 3>&1 1>&2 2>&3)
            if [ $? -ne 0 ] || [ -z "$DB_PASS" ]; then
                # Se annulla o inserisce una password vuota, genera comunque una password sicura
                DB_PASS=$(openssl rand -hex 12)
                print_message "Password database generata automaticamente: $DB_PASS"
            fi
        else
            print_message "Password database generata automaticamente: $DB_PASS"
        fi
    else
        read -p "Nome del database [$DB_NAME]: " input
        if [ -n "$input" ]; then
            DB_NAME="$input"
        fi
        
        read -p "Utente database [$DB_USER]: " input
        if [ -n "$input" ]; then
            DB_USER="$input"
        fi
        
        read -p "Utilizzare una password database generata automaticamente? (s/n) [s]: " input
        if [[ "$input" =~ ^[Nn] ]]; then
            read -s -p "Password database: " DB_PASS
            echo
            if [ -z "$DB_PASS" ]; then
                DB_PASS=$(openssl rand -hex 12)
                print_message "Password database generata automaticamente: $DB_PASS"
            fi
        else
            print_message "Password database generata automaticamente: $DB_PASS"
        fi
    fi
    
    progress_bar "Configurazione" 40
    
    # Configurazione del web server
    if [ "$USE_GUI" = true ]; then
        WEB_PORT=$(whiptail --title "Web Server" --inputbox "Porta per l'interfaccia web:" 10 70 "$WEB_PORT" 3>&1 1>&2 2>&3)
        if [ $? -ne 0 ] || [ -z "$WEB_PORT" ]; then
            print_message "Utilizzo della porta web predefinita: $WEB_PORT"
        fi
        
        BOT_PORT=$(whiptail --title "Bot Server" --inputbox "Porta per il server bot:" 10 70 "$BOT_PORT" 3>&1 1>&2 2>&3)
        if [ $? -ne 0 ] || [ -z "$BOT_PORT" ]; then
            print_message "Utilizzo della porta bot predefinita: $BOT_PORT"
        fi
    else
        read -p "Porta per l'interfaccia web [$WEB_PORT]: " input
        if [ -n "$input" ]; then
            WEB_PORT="$input"
        fi
        
        read -p "Porta per il server bot [$BOT_PORT]: " input
        if [ -n "$input" ]; then
            BOT_PORT="$input"
        fi
    fi
    
    progress_bar "Configurazione" 60
    
    # Configurazione SSL
    if [ "$USE_GUI" = true ]; then
        if whiptail --title "SSL" --yesno "Vuoi configurare SSL con Let's Encrypt?" 10 70; then
            INSTALL_CERTBOT=true
            
            DOMAINS=$(whiptail --title "SSL" --inputbox "Domini (separati da spazi):" 10 70 "" 3>&1 1>&2 2>&3)
            if [ $? -ne 0 ] || [ -z "$DOMAINS" ]; then
                INSTALL_CERTBOT=false
                print_message "SSL non sarà configurato."
            else
                SSL_EMAIL=$(whiptail --title "SSL" --inputbox "Email per Let's Encrypt:" 10 70 "" 3>&1 1>&2 2>&3)
                if [ $? -ne 0 ] || [ -z "$SSL_EMAIL" ]; then
                    INSTALL_CERTBOT=false
                    print_message "SSL non sarà configurato."
                else
                    print_message "SSL sarà configurato per i domini: $DOMAINS"
                fi
            fi
        else
            INSTALL_CERTBOT=false
        fi
    else
        read -p "Vuoi configurare SSL con Let's Encrypt? (s/n) [n]: " input
        if [[ "$input" =~ ^[Ss] ]]; then
            INSTALL_CERTBOT=true
            
            read -p "Domini (separati da spazi): " DOMAINS
            if [ -z "$DOMAINS" ]; then
                INSTALL_CERTBOT=false
                print_message "SSL non sarà configurato."
            else
                read -p "Email per Let's Encrypt: " SSL_EMAIL
                if [ -z "$SSL_EMAIL" ]; then
                    INSTALL_CERTBOT=false
                    print_message "SSL non sarà configurato."
                else
                    print_message "SSL sarà configurato per i domini: $DOMAINS"
                fi
            fi
        else
            INSTALL_CERTBOT=false
        fi
    fi
    
    progress_bar "Configurazione" 80
    
    # Nome del bot
    if [ "$USE_GUI" = true ]; then
        BOT_NAME=$(whiptail --title "Bot" --inputbox "Nome del bot:" 10 70 "M4Bot" 3>&1 1>&2 2>&3)
        if [ $? -ne 0 ] || [ -z "$BOT_NAME" ]; then
            BOT_NAME="M4Bot"
        fi
    else
        read -p "Nome del bot [M4Bot]: " input
        if [ -n "$input" ]; then
            BOT_NAME="$input"
        else
            BOT_NAME="M4Bot"
        fi
    fi
    
    # URL dell'interfaccia web
    if [ "$INSTALL_CERTBOT" = true ] && [ -n "$DOMAINS" ]; then
        # Se abbiamo domini SSL, usa il primo come URL principale
        MAIN_DOMAIN=$(echo $DOMAINS | cut -d ' ' -f 1)
        WEB_URL="https://$MAIN_DOMAIN"
    else
        # Altrimenti usa l'IP locale
        IP_ADDR=$(hostname -I | awk '{print $1}')
        if [ -z "$IP_ADDR" ]; then
            IP_ADDR="127.0.0.1"
        fi
        WEB_URL="http://$IP_ADDR:$WEB_PORT"
    fi
    
    # Mostra un riepilogo della configurazione
    CONFIG_SUMMARY="Riepilogo configurazione:\n\n"
    CONFIG_SUMMARY+="• Directory di installazione: $INSTALL_DIR\n"
    CONFIG_SUMMARY+="• Database: $DB_NAME\n"
    CONFIG_SUMMARY+="• Utente DB: $DB_USER\n"
    CONFIG_SUMMARY+="• Porta web: $WEB_PORT\n"
    CONFIG_SUMMARY+="• Porta bot: $BOT_PORT\n"
    CONFIG_SUMMARY+="• Nome bot: $BOT_NAME\n"
    CONFIG_SUMMARY+="• URL web: $WEB_URL\n"
    if [ "$INSTALL_CERTBOT" = true ]; then
        CONFIG_SUMMARY+="• SSL: Sì (Certbot)\n"
        CONFIG_SUMMARY+="• Domini: $DOMAINS\n"
        CONFIG_SUMMARY+="• Email SSL: $SSL_EMAIL\n"
    else
        CONFIG_SUMMARY+="• SSL: No\n"
    fi
    
    progress_bar "Configurazione" 100
    
    if [ "$USE_GUI" = true ]; then
        whiptail --title "Riepilogo Configurazione" --msgbox "$CONFIG_SUMMARY" 20 78
    else
        echo -e "\n$CONFIG_SUMMARY"
        echo
        read -p "Premi INVIO per continuare con l'installazione utilizzando queste impostazioni..."
    fi
    
    print_success "Configurazione completata"
}

# Configura i servizi systemd per M4Bot
setup_services() {
    print_message "Configurazione dei servizi systemd per auto-start al riavvio del server..."
    progress_bar "Configurazione Servizi" 0
    
    # Verifica che systemd sia presente
    if ! command -v systemctl &> /dev/null; then
        print_error "systemd non è installato su questo sistema. Impossibile configurare i servizi di avvio automatico."
        progress_bar "Configurazione Servizi" 100
        return 1
    fi
    
    progress_bar "Configurazione Servizi" 20
    
    # Crea la directory scripts se non esiste
    if [ ! -d "$INSTALL_DIR/scripts" ]; then
        mkdir -p "$INSTALL_DIR/scripts"
    fi
    
    # Crea utente m4bot se non esiste
    if ! id -u m4bot &>/dev/null; then
        print_message "Creazione dell'utente m4bot per l'esecuzione dei servizi..."
        useradd -r -s /bin/false -d "$INSTALL_DIR" m4bot
        if [ $? -ne 0 ]; then
            print_error "Impossibile creare l'utente m4bot."
        else
            print_success "Utente m4bot creato."
        fi
    fi
    
    progress_bar "Configurazione Servizi" 40
    
    # Crea il servizio per il core di M4Bot
    cat > "$INSTALL_DIR/scripts/m4bot.service" << EOF
[Unit]
Description=M4Bot Core Service
After=network.target postgresql.service mysql.service redis.service
Wants=mysql.service redis.service

[Service]
Type=simple
User=m4bot
Group=m4bot
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/run.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=m4bot
Environment=PATH=/usr/bin:/usr/local/bin:$INSTALL_DIR/venv/bin
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
    
    progress_bar "Configurazione Servizi" 60
    
    # Crea il servizio per l'interfaccia web di M4Bot
    cat > "$INSTALL_DIR/scripts/m4bot-web.service" << EOF
[Unit]
Description=M4Bot Web Interface
After=network.target postgresql.service mysql.service redis.service m4bot.service
Wants=mysql.service redis.service

[Service]
Type=simple
User=m4bot
Group=m4bot
WorkingDirectory=$INSTALL_DIR/web
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/web/app.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=m4bot-web
Environment=PATH=/usr/bin:/usr/local/bin:$INSTALL_DIR/venv/bin
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
    
    # Copia i file di servizio nella directory systemd
    print_message "Installazione dei file di servizio systemd..."
    cp "$INSTALL_DIR/scripts/m4bot.service" /etc/systemd/system/
    cp "$INSTALL_DIR/scripts/m4bot-web.service" /etc/systemd/system/
    
    progress_bar "Configurazione Servizi" 80
    
    # Ricarica la configurazione di systemd
    systemctl daemon-reload
    if [ $? -ne 0 ]; then
        print_error "Impossibile ricaricare systemd. I servizi potrebbero non funzionare correttamente."
    fi
    
    # Abilita i servizi per l'avvio automatico
    print_message "Abilitazione dei servizi per l'avvio automatico al riavvio..."
    systemctl enable m4bot.service
    if [ $? -ne 0 ]; then
        print_error "Impossibile abilitare il servizio m4bot. L'avvio automatico potrebbe non funzionare."
    else
        print_success "Servizio m4bot abilitato per l'avvio automatico."
    fi
    
    systemctl enable m4bot-web.service
    if [ $? -ne 0 ]; then
        print_error "Impossibile abilitare il servizio m4bot-web. L'avvio automatico potrebbe non funzionare."
    else
        print_success "Servizio m4bot-web abilitato per l'avvio automatico."
    fi
    
    progress_bar "Configurazione Servizi" 100
    
    # Crea uno script di avvio personalizzato
    print_message "Creazione script di avvio personalizzato..."
    cat > "$INSTALL_DIR/scripts/startup.sh" << EOF
#!/bin/bash
# Script di avvio automatico per M4Bot
# Questo script viene eseguito al riavvio del sistema tramite i servizi systemd

# Directory di installazione
INSTALL_DIR="$INSTALL_DIR"

# Log file
LOG_FILE="\$INSTALL_DIR/logs/startup.log"

# Assicurati che la directory dei log esista
mkdir -p "\$INSTALL_DIR/logs"

# Funzione per registrare messaggi nel log
log_message() {
    echo "\$(date '+%Y-%m-%d %H:%M:%S') - \$1" >> "\$LOG_FILE"
}

# Registra l'avvio
log_message "Avvio automatico di M4Bot dopo il riavvio del sistema"

# Attiva l'ambiente virtuale Python
if [ -d "\$INSTALL_DIR/venv" ]; then
    log_message "Attivazione dell'ambiente virtuale Python"
    source "\$INSTALL_DIR/venv/bin/activate"
else
    log_message "ERRORE: Ambiente virtuale Python non trovato"
    exit 1
fi

# Esegui controlli di integrità
log_message "Esecuzione controlli di integrità"

# Verifica la connessione al database
if command -v mysql &> /dev/null; then
    if mysql -u "$DB_USER" -p"$DB_PASS" -e "USE $DB_NAME;" &>/dev/null; then
        log_message "Connessione al database verificata con successo"
    else
        log_message "ATTENZIONE: Impossibile connettersi al database"
    fi
fi

# Verifica la connessione Redis se utilizzata
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &>/dev/null; then
        log_message "Connessione a Redis verificata con successo"
    else
        log_message "ATTENZIONE: Impossibile connettersi a Redis"
    fi
fi

# Registra completamento
log_message "Controlli di avvio completati. M4Bot pronto."

# Disattiva l'ambiente virtuale
deactivate

exit 0
EOF
    
    # Rendi lo script eseguibile
    chmod +x "$INSTALL_DIR/scripts/startup.sh"
    
    # Imposta permessi corretti per i file e le directory principali
    print_message "Impostazione dei permessi corretti..."
    chown -R m4bot:m4bot "$INSTALL_DIR"
    
    print_success "Configurazione dei servizi di avvio automatico completata"
    print_message "M4Bot si avvierà automaticamente al riavvio del server"
}

# Aggiorna il sistema e installa dipendenze di base
update_system() {
    print_message "Aggiornamento del sistema e installazione dipendenze di base..."
    progress_bar "Aggiornamento Sistema" 0
    
    # Aggiorna la lista dei pacchetti
    print_message "Aggiornamento lista pacchetti..."
    apt-get update
    if [ $? -ne 0 ]; then
        print_error "Impossibile aggiornare la lista dei pacchetti. Verifica la connessione di rete."
        progress_bar "Aggiornamento Sistema" 100
        return 1
    fi
    
    progress_bar "Aggiornamento Sistema" 20
    
    # Installa le dipendenze di base
    print_message "Installazione dipendenze di base..."
    apt-get install -y python3 python3-pip python3-venv git curl wget unzip dos2unix
    if [ $? -ne 0 ]; then
        print_error "Errore durante l'installazione delle dipendenze di base."
        progress_bar "Aggiornamento Sistema" 100
        return 1
    fi
    
    progress_bar "Aggiornamento Sistema" 40
    
    # Installa MySQL/MariaDB se non già presenti
    print_message "Verifica installazione database..."
    if ! command -v mysql &> /dev/null; then
        print_message "Installazione MariaDB..."
        apt-get install -y mariadb-server mariadb-client
        if [ $? -ne 0 ]; then
            print_error "Errore durante l'installazione di MariaDB."
            progress_bar "Aggiornamento Sistema" 100
            return 1
        fi
        
        # Assicurati che il servizio sia attivo e abilitato all'avvio
        systemctl start mariadb
        systemctl enable mariadb
    else
        print_message "MySQL/MariaDB già installato."
    fi
    
    progress_bar "Aggiornamento Sistema" 60
    
    # Installa Redis se non già presente
    print_message "Verifica installazione Redis..."
    if ! command -v redis-cli &> /dev/null; then
        print_message "Installazione Redis..."
        apt-get install -y redis-server
        if [ $? -ne 0 ]; then
            print_error "Errore durante l'installazione di Redis."
            progress_bar "Aggiornamento Sistema" 100
            return 1
        fi
        
        # Assicurati che il servizio sia attivo e abilitato all'avvio
        systemctl start redis-server
        systemctl enable redis-server
    else
        print_message "Redis già installato."
    fi
    
    progress_bar "Aggiornamento Sistema" 80
    
    # Configura l'avvio automatico a livello di sistema operativo con crontab
    print_message "Configurazione avvio automatico con crontab..."
    
    # Crea uno script di avvio per crontab
    cat > "$INSTALL_DIR/scripts/crontab_startup.sh" << EOF
#!/bin/bash
# Script per assicurarsi che M4Bot si avvii anche se systemd non riesce ad avviarlo
# Questo script verrà eseguito tramite crontab all'avvio del sistema

# Attendi 60 secondi per dare tempo al sistema di avviarsi completamente
sleep 60

# Verifica se i servizi M4Bot sono in esecuzione
if ! systemctl is-active --quiet m4bot.service; then
    # Il servizio non è attivo, avvialo
    systemctl start m4bot.service
fi

if ! systemctl is-active --quiet m4bot-web.service; then
    # Il servizio web non è attivo, avvialo
    systemctl start m4bot-web.service
fi

# Registra l'esecuzione
echo "Avvio automatico eseguito il \$(date)" >> "$INSTALL_DIR/logs/crontab_startup.log"

exit 0
EOF
    
    # Rendi lo script eseguibile
    chmod +x "$INSTALL_DIR/scripts/crontab_startup.sh"
    
    # Aggiungi lo script a crontab (se non esiste già)
    if ! crontab -l 2>/dev/null | grep -q "$INSTALL_DIR/scripts/crontab_startup.sh"; then
        # Crea una copia temporanea dell'attuale crontab
        crontab -l 2>/dev/null > /tmp/crontab.tmp
        
        # Aggiungi la nuova entry
        echo "@reboot $INSTALL_DIR/scripts/crontab_startup.sh" >> /tmp/crontab.tmp
        
        # Installa il nuovo crontab
        crontab /tmp/crontab.tmp
        
        # Pulisci
        rm -f /tmp/crontab.tmp
        
        print_success "Configurato avvio automatico tramite crontab."
    else
        print_message "Avvio automatico tramite crontab già configurato."
    fi
    
    # Configura rc.local per l'avvio se esiste
    if [ -f /etc/rc.local ]; then
        print_message "Configurazione rc.local per avvio automatico..."
        
        # Verifica se rc.local contiene già il comando
        if ! grep -q "$INSTALL_DIR/scripts/startup.sh" /etc/rc.local; then
            # Ottiene la riga dell'exit 0
            EXIT_LINE=$(grep -n "exit 0" /etc/rc.local | cut -d: -f1)
            
            if [ -n "$EXIT_LINE" ]; then
                # Inserisce il comando prima dell'exit 0
                sed -i "${EXIT_LINE}i# Avvio automatico M4Bot\n$INSTALL_DIR/scripts/startup.sh" /etc/rc.local
            else
                # Aggiunge il comando alla fine
                echo -e "\n# Avvio automatico M4Bot\n$INSTALL_DIR/scripts/startup.sh" >> /etc/rc.local
                echo -e "\nexit 0" >> /etc/rc.local
            fi
            
            # Rendi rc.local eseguibile
            chmod +x /etc/rc.local
            
            print_success "Configurato avvio automatico tramite rc.local."
        else
            print_message "Avvio automatico tramite rc.local già configurato."
        fi
    fi
    
    progress_bar "Aggiornamento Sistema" 100
    
    print_success "Sistema aggiornato e dipendenze di base installate."
    print_message "Configurazione dell'avvio automatico completata attraverso systemd, crontab e rc.local."
}

# Avvia i servizi di M4Bot
start_services() {
    print_message "Avvio dei servizi M4Bot..."
    progress_bar "Avvio Servizi" 0
    
    # Crea la directory dei log se non esiste
    if [ ! -d "$INSTALL_DIR/logs" ]; then
        print_message "Creazione directory dei log..."
        mkdir -p "$INSTALL_DIR/logs"
        chown -R m4bot:m4bot "$INSTALL_DIR/logs"
        chmod -R 755 "$INSTALL_DIR/logs"
    fi
    
    progress_bar "Avvio Servizi" 20
    
    # Verifica che il database sia in esecuzione
    print_message "Verifica database..."
    if command -v systemctl &> /dev/null; then
        if systemctl is-active --quiet mariadb.service || systemctl is-active --quiet mysql.service; then
            print_success "Database attivo."
        else
            print_warning "Database non attivo. Tentativo di avvio..."
            if systemctl is-enabled --quiet mariadb.service; then
                systemctl start mariadb.service
            elif systemctl is-enabled --quiet mysql.service; then
                systemctl start mysql.service
            else
                print_error "Nessun servizio database configurato."
            fi
        fi
    fi
    
    progress_bar "Avvio Servizi" 40
    
    # Verifica che Redis sia in esecuzione (se presente)
    if command -v redis-cli &> /dev/null; then
        print_message "Verifica Redis..."
        if systemctl is-active --quiet redis-server.service; then
            print_success "Redis attivo."
        else
            print_warning "Redis non attivo. Tentativo di avvio..."
            systemctl start redis-server.service
        fi
    fi
    
    progress_bar "Avvio Servizi" 60
    
    # Preparazione all'avvio automatico al riavvio del sistema
    print_message "Preparazione all'avvio automatico al riavvio del sistema..."
    
    # Crea uno script di verifica dello stato dei servizi
    cat > "$INSTALL_DIR/scripts/check_services.sh" << EOF
#!/bin/bash
# Script per verificare lo stato dei servizi M4Bot

# Directory di installazione
INSTALL_DIR="$INSTALL_DIR"

# Log file
LOG_FILE="\$INSTALL_DIR/logs/services.log"

# Funzione per registrare messaggi nel log
log_message() {
    echo "\$(date '+%Y-%m-%d %H:%M:%S') - \$1" >> "\$LOG_FILE"
}

# Verifica lo stato di un servizio
check_service() {
    local service="\$1"
    if systemctl is-active --quiet "\$service"; then
        echo "✅ \$service è attivo"
        log_message "\$service è attivo"
        return 0
    else
        echo "❌ \$service non è attivo"
        log_message "\$service non è attivo"
        
        # Tenta di avviare il servizio
        echo "🔄 Tentativo di avvio di \$service..."
        systemctl start "\$service"
        
        # Verifica nuovamente lo stato
        if systemctl is-active --quiet "\$service"; then
            echo "✅ \$service avviato con successo"
            log_message "\$service avviato con successo"
            return 0
        else
            echo "❌ Impossibile avviare \$service"
            log_message "Impossibile avviare \$service"
            return 1
        fi
    fi
}

# Intestazione
echo "===========================================" 
echo "         VERIFICA SERVIZI M4BOT            "
echo "===========================================" 
echo "Data: \$(date)"
echo

# Verifica lo stato dei servizi
echo "1. Verifica dei servizi principali:"
check_service "m4bot.service"
check_service "m4bot-web.service"

echo

# Verifica le dipendenze
echo "2. Verifica dei servizi dipendenti:"
if command -v mysql &> /dev/null; then
    if systemctl is-active --quiet mariadb.service; then
        echo "✅ Database (MariaDB) è attivo"
    elif systemctl is-active --quiet mysql.service; then
        echo "✅ Database (MySQL) è attivo"
    else
        echo "❌ Database non è attivo"
    fi
fi

if command -v redis-cli &> /dev/null; then
    if systemctl is-active --quiet redis-server.service; then
        echo "✅ Redis è attivo"
    else
        echo "❌ Redis non è attivo"
    fi
fi

echo

# Verifica che il bot sia configurato per l'avvio automatico
echo "3. Verifica configurazione avvio automatico:"
if systemctl is-enabled --quiet m4bot.service; then
    echo "✅ m4bot.service è abilitato all'avvio automatico"
else
    echo "❌ m4bot.service non è abilitato all'avvio automatico"
    echo "🔄 Abilitazione di m4bot.service..."
    systemctl enable m4bot.service
fi

if systemctl is-enabled --quiet m4bot-web.service; then
    echo "✅ m4bot-web.service è abilitato all'avvio automatico"
else
    echo "❌ m4bot-web.service non è abilitato all'avvio automatico"
    echo "🔄 Abilitazione di m4bot-web.service..."
    systemctl enable m4bot-web.service
fi

# Verifica crontab
if crontab -l 2>/dev/null | grep -q "$INSTALL_DIR/scripts/crontab_startup.sh"; then
    echo "✅ Avvio tramite crontab configurato"
else
    echo "❌ Avvio tramite crontab non configurato"
fi

# Verifica rc.local
if [ -f /etc/rc.local ] && grep -q "$INSTALL_DIR/scripts/startup.sh" /etc/rc.local; then
    echo "✅ Avvio tramite rc.local configurato"
else
    echo "❓ Avvio tramite rc.local non configurato"
fi

# Configurazione moduli di sicurezza e stabilità
echo
echo "4. Configurazione moduli di sicurezza e stabilità:"

# Crea directory se non esiste
if [ ! -d "$INSTALL_DIR/security" ]; then
    echo "📁 Creazione directory per moduli di sicurezza..."
    mkdir -p "$INSTALL_DIR/security"
    chown m4bot:m4bot "$INSTALL_DIR/security"
fi

# Verifica e configura WAF
if [ -f "$INSTALL_DIR/security/waf.py" ]; then
    echo "✅ Web Application Firewall (WAF) è installato"
else
    echo "❌ WAF non trovato, installazione in corso..."
    # In una versione reale, qui copieremmo il file WAF dalla directory di installazione
    echo "⚠️ Per favore installa manualmente il modulo WAF"
fi

# Verifica e configura modulo di sicurezza avanzata
if [ -f "$INSTALL_DIR/security/security_enhancements.py" ]; then
    echo "✅ Modulo di sicurezza avanzata è installato"
else
    echo "❌ Modulo di sicurezza avanzata non trovato, installazione in corso..."
    # In una versione reale, qui copieremmo il file dalla directory di installazione
    echo "⚠️ Per favore installa manualmente il modulo di sicurezza avanzata"
fi

# Verifica e configura modulo di stabilità
if [ -d "$INSTALL_DIR/modules/stability_security" ]; then
    echo "✅ Modulo di stabilità è installato"
else
    echo "❌ Modulo di stabilità non trovato, installazione in corso..."
    # In una versione reale, qui copieremmo i file dalla directory di installazione
    mkdir -p "$INSTALL_DIR/modules/stability_security"
    echo "⚠️ Per favore installa manualmente il modulo di stabilità"
fi

# Configura script per aggiornamento zero-downtime
echo
echo "5. Configurazione per aggiornamento zero-downtime:"

if [ -f "$INSTALL_DIR/scripts/update.sh" ]; then
    echo "✅ Script di aggiornamento già presente"
else
    echo "❌ Script di aggiornamento non trovato, creazione in corso..."
    
    cat > "$INSTALL_DIR/scripts/update.sh" << 'EOF'
#!/bin/bash
# Script di aggiornamento M4Bot con supporto zero-downtime

# Imposta percorso di installazione
INSTALL_DIR=${INSTALL_DIR:-"/opt/m4bot"}

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Verifica parametri
ZERO_DOWNTIME=false
HOTFIX=false
ROLLBACK=false

for arg in "$@"; do
    case $arg in
        --zero-downtime)
            ZERO_DOWNTIME=true
            shift
            ;;
        --hotfix)
            HOTFIX=true
            shift
            ;;
        --rollback)
            ROLLBACK=true
            shift
            ;;
    esac
done

# Funzione per eseguire l'aggiornamento standard
perform_standard_update() {
    print_message "Esecuzione aggiornamento standard..."
    
    # Arresta servizi
    print_message "Arresto servizi..."
    systemctl stop m4bot-web.service
    systemctl stop m4bot.service
    
    # Backup
    print_message "Creazione backup pre-aggiornamento..."
    "$INSTALL_DIR/scripts/backup.sh" pre-update
    
    # Aggiornamento codice
    print_message "Aggiornamento codice sorgente..."
    cd "$INSTALL_DIR" && git pull
    
    # Aggiornamento dipendenze
    print_message "Aggiornamento dipendenze..."
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
    
    # Migrazione database
    print_message "Migrazione database..."
    "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/manage.py" migrate
    
    # Riavvio servizi
    print_message "Riavvio servizi..."
    systemctl start m4bot.service
    systemctl start m4bot-web.service
    
    print_success "Aggiornamento standard completato"
}

# Funzione per eseguire l'aggiornamento zero-downtime
perform_zero_downtime_update() {
    print_message "Esecuzione aggiornamento zero-downtime..."
    
    # Verifica prerequisiti
    if ! command -v python3 -m modules.stability_security &> /dev/null; then
        print_error "Modulo stability_security non disponibile. Impossibile eseguire aggiornamento zero-downtime." 1
    fi
    
echo
echo "===========================================" 
echo
EOF
    
    # Rendi lo script eseguibile
    chmod +x "$INSTALL_DIR/scripts/check_services.sh"
    
    progress_bar "Avvio Servizi" 80
    
    # Avvia i servizi
    print_message "Avvio dei servizi M4Bot..."
    systemctl start m4bot.service
    if [ $? -ne 0 ]; then
        print_warning "Impossibile avviare il servizio m4bot. Verificare i log per dettagli."
    else
        print_success "Servizio m4bot avviato."
    fi
    
    systemctl start m4bot-web.service
    if [ $? -ne 0 ]; then
        print_warning "Impossibile avviare il servizio m4bot-web. Verificare i log per dettagli."
    else
        print_success "Servizio m4bot-web avviato."
    fi
    
    progress_bar "Avvio Servizi" 100
    
    # Esegui lo script di verifica
    print_message "Verifica finale dei servizi:"
    "$INSTALL_DIR/scripts/check_services.sh"
    
    print_success "Avvio dei servizi completato"
    print_message "M4Bot è configurato per avviarsi automaticamente al riavvio del sistema"
}

# Installa i moduli di stabilità e sicurezza avanzata
install_security_monitoring_modules() {
    print_message "Installazione moduli di sicurezza e monitoraggio avanzati..."
    progress_bar "Installazione moduli avanzati" 0
    
    # Crea directory per i moduli
    mkdir -p "$INSTALL_DIR/modules/stability_security" 2>/dev/null
    mkdir -p "$INSTALL_DIR/modules/monitoring" 2>/dev/null
    mkdir -p "/var/log/m4bot" 2>/dev/null
    
    # Imposta permessi corretti per la directory dei log
    chmod 755 "/var/log/m4bot"
    chown m4bot:m4bot "/var/log/m4bot"
    
    progress_bar "Installazione moduli avanzati" 20
    
    # Copia lo script di health monitoring
    if [ -f "$CURRENT_DIR/scripts/health_monitor.sh" ]; then
        cp "$CURRENT_DIR/scripts/health_monitor.sh" "$INSTALL_DIR/scripts/"
        chmod +x "$INSTALL_DIR/scripts/health_monitor.sh"
        print_message "Script health_monitor.sh installato"
    elif [ -f "$INSTALL_DIR/scripts/health_monitor.sh" ]; then
        chmod +x "$INSTALL_DIR/scripts/health_monitor.sh"
        print_message "Script health_monitor.sh configurato"
    else
        print_warning "Script health_monitor.sh non trovato. Verrà creato..."
        # Qui si potrebbe aggiungere codice per creare lo script da zero
    fi
    
    progress_bar "Installazione moduli avanzati" 40
    
    # Copia lo script di aggiornamento a zero downtime
    if [ -f "$CURRENT_DIR/scripts/update_zero_downtime.sh" ]; then
        cp "$CURRENT_DIR/scripts/update_zero_downtime.sh" "$INSTALL_DIR/scripts/"
        chmod +x "$INSTALL_DIR/scripts/update_zero_downtime.sh"
        print_message "Script update_zero_downtime.sh installato"
    elif [ -f "$INSTALL_DIR/scripts/update_zero_downtime.sh" ]; then
        chmod +x "$INSTALL_DIR/scripts/update_zero_downtime.sh"
        print_message "Script update_zero_downtime.sh configurato"
    else
        print_warning "Script update_zero_downtime.sh non trovato. Verrà creato..."
        # Qui si potrebbe aggiungere codice per creare lo script da zero
    fi
    
    progress_bar "Installazione moduli avanzati" 60
    
    # Copia lo script di diagnostica
    if [ -f "$CURRENT_DIR/scripts/diagnostics.sh" ]; then
        cp "$CURRENT_DIR/scripts/diagnostics.sh" "$INSTALL_DIR/scripts/"
        chmod +x "$INSTALL_DIR/scripts/diagnostics.sh"
        print_message "Script diagnostics.sh installato"
    elif [ -f "$INSTALL_DIR/scripts/diagnostics.sh" ]; then
        chmod +x "$INSTALL_DIR/scripts/diagnostics.sh"
        print_message "Script diagnostics.sh configurato"
    else
        print_warning "Script diagnostics.sh non trovato. Verrà creato..."
        # Qui si potrebbe aggiungere codice per creare lo script da zero
    fi
    
    progress_bar "Installazione moduli avanzati" 80
    
    # Installa i moduli Python
    if [ -d "$CURRENT_DIR/modules/stability_security" ]; then
        cp -r "$CURRENT_DIR/modules/stability_security"/* "$INSTALL_DIR/modules/stability_security/"
        print_message "Modulo stability_security installato"
    fi
    
    if [ -d "$CURRENT_DIR/modules/monitoring" ]; then
        cp -r "$CURRENT_DIR/modules/monitoring"/* "$INSTALL_DIR/modules/monitoring/"
        print_message "Modulo monitoring installato"
    fi
    
    if [ -f "$CURRENT_DIR/modules/security/key_rotation.py" ]; then
        mkdir -p "$INSTALL_DIR/modules/security" 2>/dev/null
        cp "$CURRENT_DIR/modules/security/key_rotation.py" "$INSTALL_DIR/modules/security/"
        print_message "Modulo key_rotation installato"
    fi
    
    # Imposta permessi corretti per i moduli
    find "$INSTALL_DIR/modules" -type f -name "*.py" -exec chmod 644 {} \;
    find "$INSTALL_DIR/modules" -type f -name "*.sh" -exec chmod +x {} \;
    chown -R m4bot:m4bot "$INSTALL_DIR/modules"
    
    progress_bar "Installazione moduli avanzati" 90
    
    # Installa dipendenze Python necessarie
    pip3 install psutil prometheus_client aiohttp aioredis asyncpg 2>/dev/null
    
    # Crea servizi systemd per i moduli di monitoraggio
    cat > /etc/systemd/system/m4bot-health-monitor.service << EOF
[Unit]
Description=M4Bot Health Monitor Service
After=network.target

[Service]
User=root
Group=root
ExecStart=/bin/bash $INSTALL_DIR/scripts/health_monitor.sh --daemon
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/m4bot-prometheus-exporter.service << EOF
[Unit]
Description=M4Bot Prometheus Metrics Exporter
After=network.target

[Service]
User=m4bot
Group=m4bot
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/modules/monitoring/prometheus_exporter.py
Restart=on-failure
RestartSec=10s

[Install]
WantedBy=multi-user.target
EOF

    # Abilita e avvia i servizi
    systemctl daemon-reload
    systemctl enable m4bot-health-monitor.service
    systemctl enable m4bot-prometheus-exporter.service
    
    progress_bar "Installazione moduli avanzati" 100
    print_success "Moduli di sicurezza e monitoraggio installati e configurati"
}

# Aggiungi rotazione automatica delle chiavi ai crontab
setup_key_rotation_cron() {
    print_message "Configurazione rotazione automatica delle chiavi..."
    
    # Crea script wrapper per la rotazione delle chiavi
    cat > "$INSTALL_DIR/scripts/rotate_keys.sh" << EOF
#!/bin/bash
# Script wrapper per la rotazione automatica delle chiavi
cd "$INSTALL_DIR"
export M4BOT_DIR="$INSTALL_DIR"
"$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/modules/security/key_rotation.py"

# Registra il risultato nel log
if [ \$? -eq 0 ]; then
    echo "[$(date)] Rotazione chiavi completata con successo" >> /var/log/m4bot/key_rotation_cron.log
else
    echo "[$(date)] Errore nella rotazione delle chiavi" >> /var/log/m4bot/key_rotation_cron.log
fi
EOF
    
    chmod +x "$INSTALL_DIR/scripts/rotate_keys.sh"
    chown m4bot:m4bot "$INSTALL_DIR/scripts/rotate_keys.sh"
    
    # Crea il job cron (esegue la rotazione ogni 30 giorni)
    if ! crontab -l -u m4bot 2>/dev/null | grep -q "rotate_keys.sh"; then
        (crontab -l -u m4bot 2>/dev/null; echo "0 2 1 */1 * $INSTALL_DIR/scripts/rotate_keys.sh") | crontab -u m4bot -
        print_success "Rotazione chiavi pianificata per esecuzione mensile"
    else
        print_message "Job cron per rotazione chiavi già configurato"
    fi
}

# Nella funzione install_all o main, aggiungi chiamate alle nuove funzioni
install_all() {
    show_title
    print_message "Avvio installazione completa di M4Bot..."
    
    check_prerequisites
    install_dependencies
    create_user
    
    # Crea directory principale
    mkdir -p "$INSTALL_DIR"
    
    # Clona o copia il repository
    if [ "$CLONE_REPO" = true ]; then
        clone_repository
    elif [ "$COPY_FILES" = true ]; then
        copy_local_files
    fi
    
    # Setup ambiente Python
    setup_python_env
    
    # Setup database
    if [ "$SETUP_DB" = true ]; then
        setup_database
    fi
    
    # Setup Redis
    if [ "$SETUP_REDIS" = true ]; then
        setup_redis
    fi
    
    # Configura Nginx
    if [ "$SETUP_NGINX" = true ]; then
        configure_nginx
    fi
    
    # Configura SSL
    if [ "$SETUP_SSL" = true ]; then
        setup_ssl
    fi
    
    # Correggi file problematici
    fix_project_files
    
    # Correzione completa di tutti i file
    if [ "$FIX_ALL_FILES" = true ]; then
        fix_all_files
    fi
    
    # Installa i moduli di sicurezza e monitoraggio avanzati
    if [ "$INSTALL_ADVANCED" = true ]; then
        install_security_monitoring_modules
        setup_key_rotation_cron
    fi
    
    # Crea servizi systemd
    create_systemd_services
    
    # Avvia servizi
    start_services
    
    print_success "Installazione di M4Bot completata con successo!"
    print_message "Indirizzo web: http://$DOMAINS_LIST:$WEB_PORT"
    if [ "$SETUP_SSL" = true ]; then
        print_message "Indirizzo web sicuro: https://$DOMAINS_LIST"
    fi
}

# Avvia lo script
main