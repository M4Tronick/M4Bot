#!/bin/bash
# Script unificato per M4Bot
# Questo script combina installazione, avvio e configurazione in un unico file
# Autore: M4Tronick
# Versione: 1.0

### FUNZIONI COMUNI ###

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzione per stampare messaggi colorati
print_message() {
    echo -e "${BLUE}[M4BOT]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESSO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[ATTENZIONE]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERRORE]${NC} $1"
    if [ "$2" -eq 1 ]; then
        exit 1
    fi
}

# Verifica che l'utente sia root
check_root() {
    if [ "$EUID" -ne 0 ]; then
        print_error "Questo script deve essere eseguito come root" 1
    fi
}

# Verifica che PostgreSQL sia in esecuzione
check_postgres() {
    if ! systemctl is-active --quiet postgresql; then
        print_error "PostgreSQL non è in esecuzione. Avvialo con: systemctl start postgresql" 1
    fi
}

# Verifica lo stato dei servizi principali
check_services() {
    # Verifica PostgreSQL
    if ! systemctl is-active --quiet postgresql; then
        print_warning "PostgreSQL non è in esecuzione. Avvio in corso..."
        systemctl start postgresql
        if [ $? -ne 0 ]; then
            print_error "Impossibile avviare PostgreSQL" 1
        else
            print_success "PostgreSQL avviato"
        fi
    fi

    # Verifica Nginx
    if ! systemctl is-active --quiet nginx; then
        print_warning "Nginx non è in esecuzione. Avvio in corso..."
        systemctl start nginx
        if [ $? -ne 0 ]; then
            print_error "Impossibile avviare Nginx" 1
        else
            print_success "Nginx avviato"
        fi
    fi
}

# Funzione per eseguire una fase e controllare se ha avuto successo
execute_step() {
    local step_name="$1"
    local command="$2"
    
    print_message "Esecuzione: $step_name"
    
    eval "$command"
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        print_success "$step_name completato con successo"
        return 0
    else
        print_error "$step_name fallito (codice errore: $exit_code)"
        read -p "Vuoi continuare comunque? [S/n] " answer
        if [[ $answer =~ ^[Nn] ]]; then
            exit 1
        fi
        return $exit_code
    fi
}

# Configurazione iniziale
INSTALL_DIR="/opt/m4bot"
LOGS_DIR="$INSTALL_DIR/logs"
BOT_DIR="$INSTALL_DIR/bot"
WEB_DIR="$INSTALL_DIR/web"
NGINX_CONF="/etc/nginx/sites-available/m4bot"
SERVICE_BOT="/etc/systemd/system/m4bot-bot.service"
SERVICE_WEB="/etc/systemd/system/m4bot-web.service"
INSTALL_NGINX=true
INSTALL_POSTGRESQL=true
INSTALL_REDIS=true
CONFIGURE_SSL=true
DOMAIN="m4bot.localhost"

# Funzione per mostrare un menu sì/no
yes_no_menu() {
    local prompt="$1"
    local default="$2"  # true o false
    
    if $default; then
        read -p "$prompt [S/n]: " response
        if [[ $response =~ ^[Nn] ]]; then
            return 1
        else
            return 0
        fi
    else
        read -p "$prompt [s/N]: " response
        if [[ $response =~ ^[Ss] ]]; then
            return 0
        else
            return 1
        fi
    fi
}

# Funzione per l'installazione completa
install_m4bot() {
    print_message "Avvio installazione completa di M4Bot"
    check_root
    
    # Verifica spazio disco
    DISK_SPACE=$(df -m / | awk 'NR==2 {print $4}')
    if [ "$DISK_SPACE" -lt 1000 ]; then
        print_warning "Spazio disco limitato: ${DISK_SPACE}MB. Si raccomandano almeno 1GB"
        yes_no_menu "Vuoi continuare comunque?" true || exit 1
    fi
    
    # Aggiorna repository
    execute_step "Aggiornamento repository" "apt-get update"
    
    # Installa dipendenze
    execute_step "Installazione dipendenze" "apt-get install -y python3 python3-pip python3-venv git curl wget"
    
    # Installa PostgreSQL
    if $INSTALL_POSTGRESQL; then
        execute_step "Installazione PostgreSQL" "apt-get install -y postgresql postgresql-contrib"
        systemctl enable postgresql
        systemctl start postgresql
    fi
    
    # Installa Nginx
    if $INSTALL_NGINX; then
        execute_step "Installazione Nginx" "apt-get install -y nginx"
        systemctl enable nginx
        systemctl start nginx
    fi
    
    # Installa Redis
    if $INSTALL_REDIS; then
        execute_step "Installazione Redis" "apt-get install -y redis-server"
        systemctl enable redis-server
        systemctl start redis-server
    fi
    
    # Crea utente m4bot
    if ! id -u m4bot &>/dev/null; then
        execute_step "Creazione utente m4bot" "useradd -m -s /bin/bash m4bot"
    fi
    
    # Crea directory
    execute_step "Creazione directory di installazione" "mkdir -p $INSTALL_DIR $LOGS_DIR $BOT_DIR $WEB_DIR"
    
    # Clona repository (esempio)
    # execute_step "Clonazione repository" "git clone https://github.com/yourusername/m4bot.git /tmp/m4bot && cp -r /tmp/m4bot/* $INSTALL_DIR/ && rm -rf /tmp/m4bot"
    
    # Crea ambiente virtuale
    execute_step "Creazione ambiente virtuale Python" "python3 -m venv $INSTALL_DIR/venv"
    
    # Installa dipendenze Python
    execute_step "Installazione dipendenze Python" "$INSTALL_DIR/venv/bin/pip install flask flask-babel psycopg2-binary redis requests python-dotenv"
    
    # Configurazione Nginx
    if $INSTALL_NGINX; then
        cat > "$NGINX_CONF" << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /api {
        proxy_pass http://localhost:5001;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static {
        alias $WEB_DIR/static;
    }
}
EOF
        
        # Verifica la configurazione di Nginx
        if ! nginx -t; then
            print_error "La configurazione di Nginx non è valida" 1
        fi
        
        # Abilita il sito
        if [ ! -L "/etc/nginx/sites-enabled/m4bot" ]; then
            ln -sf "$NGINX_CONF" "/etc/nginx/sites-enabled/"
        fi
        
        systemctl reload nginx
    fi
    
    # Configura SSL con Let's Encrypt
    if $CONFIGURE_SSL && [ "$DOMAIN" != "localhost" ] && [ "$DOMAIN" != "m4bot.localhost" ]; then
        # Installa certbot se non è installato
        if ! command -v certbot &>/dev/null; then
            execute_step "Installazione Certbot" "apt-get install -y certbot python3-certbot-nginx"
        fi
        
        # Ottieni certificato
        execute_step "Configurazione SSL" "certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN --redirect"
    fi
    
    # Configura servizi systemd
    cat > "$SERVICE_BOT" << EOF
[Unit]
Description=M4Bot Bot Service
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$BOT_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $BOT_DIR/m4bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    cat > "$SERVICE_WEB" << EOF
[Unit]
Description=M4Bot Web Service
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$WEB_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $WEB_DIR/app.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    # Ricarica systemd
    systemctl daemon-reload
    
    # Abilita servizi
    systemctl enable m4bot-bot.service
    systemctl enable m4bot-web.service
    
    # Imposta proprietario
    chown -R m4bot:m4bot "$INSTALL_DIR"
    
    # Avvia servizi
    systemctl start m4bot-bot.service
    systemctl start m4bot-web.service
    
    print_success "Installazione di M4Bot completata con successo!"
    print_message "Visita http://$DOMAIN per accedere all'interfaccia web"
}

# Funzione per avviare M4Bot
start_m4bot() {
    print_message "Avvio di M4Bot..."
    check_root
    check_services
    
    # Verifica se i servizi sono già in esecuzione
    if systemctl is-active --quiet m4bot-bot.service; then
        print_warning "Il servizio bot è già in esecuzione"
    else
        systemctl start m4bot-bot.service
        if [ $? -eq 0 ]; then
            print_success "Bot avviato con successo"
        else
            print_error "Impossibile avviare il bot" 0
        fi
    fi
    
    if systemctl is-active --quiet m4bot-web.service; then
        print_warning "Il servizio web è già in esecuzione"
    else
        systemctl start m4bot-web.service
        if [ $? -eq 0 ]; then
            print_success "Web app avviata con successo"
        else
            print_error "Impossibile avviare la web app" 0
        fi
    fi
    
    print_message "Stato dei servizi:"
    systemctl status m4bot-bot.service --no-pager | grep Active
    systemctl status m4bot-web.service --no-pager | grep Active
    systemctl status nginx --no-pager | grep Active
    systemctl status postgresql --no-pager | grep Active
    
    print_message "M4Bot è ora disponibile all'indirizzo https://m4bot.it"
}

# Funzione per fermare M4Bot
stop_m4bot() {
    print_message "Arresto di M4Bot..."
    check_root
    
    # Ferma i servizi
    if systemctl is-active --quiet m4bot-bot.service; then
        systemctl stop m4bot-bot.service
        print_success "Bot fermato con successo"
    else
        print_warning "Il servizio bot non è in esecuzione"
    fi
    
    if systemctl is-active --quiet m4bot-web.service; then
        systemctl stop m4bot-web.service
        print_success "Web app fermata con successo"
    else
        print_warning "Il servizio web non è in esecuzione"
    fi
    
    print_message "Tutti i servizi M4Bot sono stati arrestati"
}

# Funzione per riavviare M4Bot
restart_m4bot() {
    print_message "Riavvio di M4Bot..."
    check_root
    
    # Riavvia i servizi
    systemctl restart m4bot-bot.service
    systemctl restart m4bot-web.service
    
    # Verifica che i servizi siano stati avviati correttamente
    if systemctl is-active --quiet m4bot-bot.service && systemctl is-active --quiet m4bot-web.service; then
        print_success "M4Bot è stato riavviato con successo"
    else
        print_error "Errore durante il riavvio di M4Bot" 0
        
        # Mostra lo stato dei servizi
        systemctl status m4bot-bot.service --no-pager
        systemctl status m4bot-web.service --no-pager
    fi
}

# Funzione per mostrare lo stato di M4Bot
status_m4bot() {
    print_message "Stato di M4Bot:"
    check_root
    
    echo "=== SERVIZI ==="
    systemctl status m4bot-bot.service --no-pager | grep -E "Active:|Loaded:"
    systemctl status m4bot-web.service --no-pager | grep -E "Active:|Loaded:"
    systemctl status nginx --no-pager | grep -E "Active:|Loaded:"
    systemctl status postgresql --no-pager | grep -E "Active:|Loaded:"
    
    echo "=== PORTE ==="
    netstat -tuln | grep -E ":5000|:5001|:80|:443"
    
    echo "=== LOG RECENTI ==="
    journalctl -u m4bot-bot.service -u m4bot-web.service --since "1 hour ago" | tail -n 10
    
    print_message "M4Bot è disponibile all'indirizzo https://m4bot.it"
}

# Funzione per controllare gli aggiornamenti
check_updates() {
    check_root
    
    if [ -d "$INSTALL_DIR" ]; then
        print_message "Controllo aggiornamenti per M4Bot..."
        
        # Creazione file di versione se non esiste
        if [ ! -f "$INSTALL_DIR/version.txt" ]; then
            echo "1.0.0" > "$INSTALL_DIR/version.txt"
        fi
        
        LOCAL_VERSION=$(cat "$INSTALL_DIR/version.txt")
        LATEST_VERSION=$(curl -s "https://api.github.com/repos/yourusername/m4bot/releases/latest" | grep -Po '"tag_name": "\K.*?(?=")')
        
        if [ -z "$LATEST_VERSION" ]; then
            print_warning "Impossibile ottenere l'ultima versione"
            return
        fi
        
        print_message "Versione locale: $LOCAL_VERSION"
        print_message "Ultima versione: $LATEST_VERSION"
        
        if [ "$LOCAL_VERSION" != "$LATEST_VERSION" ]; then
            print_message "È disponibile una nuova versione!"
            yes_no_menu "Vuoi aggiornare ora?" true && update_m4bot
        else
            print_message "M4Bot è aggiornato all'ultima versione"
        fi
    else
        print_error "M4Bot non è installato in $INSTALL_DIR" 1
    fi
}

# Funzione per aggiornare M4Bot
update_m4bot() {
    check_root
    check_services
    
    print_message "Aggiornamento di M4Bot..."
    
    # Backup della directory attuale
    BACKUP_DIR="/opt/m4bot_backup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    cp -r "$INSTALL_DIR"/* "$BACKUP_DIR"
    
    # Scarica la nuova versione
    TMP_DIR="/tmp/m4bot_update"
    rm -rf "$TMP_DIR"
    mkdir -p "$TMP_DIR"
    
    # curl -s -L "https://github.com/yourusername/m4bot/archive/main.zip" -o "$TMP_DIR/m4bot.zip"
    # unzip -q "$TMP_DIR/m4bot.zip" -d "$TMP_DIR"
    # cp -r "$TMP_DIR/m4bot-main"/* "$INSTALL_DIR"
    
    # Aggiorna dipendenze
    "$INSTALL_DIR/venv/bin/pip" install --upgrade -r "$INSTALL_DIR/requirements.txt"
    
    # Aggiorna il file di versione
    # LATEST_VERSION=$(curl -s "https://api.github.com/repos/yourusername/m4bot/releases/latest" | grep -Po '"tag_name": "\K.*?(?=")')
    # echo "$LATEST_VERSION" > "$INSTALL_DIR/version.txt"
    
    # Imposta permessi corretti
    chown -R m4bot:m4bot "$INSTALL_DIR"
    
    # Riavvia i servizi
    systemctl restart m4bot-bot.service
    systemctl restart m4bot-web.service
    
    print_success "M4Bot aggiornato con successo!"
}

# Funzione principale che gestisce i parametri di input
main() {
    if [ $# -eq 0 ]; then
        # Nessun parametro, mostra il menu
        echo "M4Bot - Script Unificato"
        echo "------------------------"
        echo "Utilizzo: $0 [comando]"
        echo
        echo "Comandi disponibili:"
        echo "  install    - Installa M4Bot sul sistema"
        echo "  start      - Avvia i servizi M4Bot"
        echo "  stop       - Ferma i servizi M4Bot"
        echo "  restart    - Riavvia i servizi M4Bot"
        echo "  status     - Mostra lo stato dei servizi M4Bot"
        echo "  update     - Aggiorna M4Bot all'ultima versione"
        echo "  check      - Controlla se sono disponibili aggiornamenti"
        echo "  help       - Mostra questa guida"
        echo
        echo "Esempi:"
        echo "  $0 install  # Installa M4Bot sul sistema"
        echo "  $0 start    # Avvia i servizi M4Bot"
        exit 0
    fi
    
    # Gestisci il comando
    case "$1" in
        install)
            install_m4bot "${@:2}"
            ;;
        start)
            start_m4bot
            ;;
        stop)
            stop_m4bot
            ;;
        restart)
            restart_m4bot
            ;;
        status)
            status_m4bot
            ;;
        update)
            update_m4bot
            ;;
        check)
            check_updates
            ;;
        help)
            main
            ;;
        *)
            echo "Comando non riconosciuto: $1"
            echo "Usa '$0 help' per vedere i comandi disponibili"
            exit 1
            ;;
    esac
}

# Esegui la funzione principale con tutti i parametri passati allo script
main "$@" 