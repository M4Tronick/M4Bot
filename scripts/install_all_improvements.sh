#!/bin/bash
# Script di installazione per tutte le migliorie di M4Bot
# Progettato per sistemi Linux (Ubuntu/Debian)

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
    print_error "Questo script deve essere eseguito come root" 1
fi

# Verifica che sia un sistema Linux
if [ "$(uname)" != "Linux" ]; then
    print_error "Questo script è progettato per sistemi Linux" 1
fi

# Directory di base
CURRENT_DIR=$(pwd)
INSTALL_DIR="/opt/m4bot"
SCRIPTS_DIR="${INSTALL_DIR}/scripts"
MODULES_DIR="${INSTALL_DIR}/modules"
SECURITY_DIR="${INSTALL_DIR}/security"
LOG_DIR="${INSTALL_DIR}/logs"

# Crea directory principali se non esistono
mkdir -p ${SCRIPTS_DIR}
mkdir -p ${MODULES_DIR}
mkdir -p ${SECURITY_DIR}
mkdir -p ${LOG_DIR}

# Aggiungi queste directory
mkdir -p ${INSTALL_DIR}/config
mkdir -p ${INSTALL_DIR}/config/app
mkdir -p ${INSTALL_DIR}/config/security
mkdir -p ${INSTALL_DIR}/backups/database
mkdir -p ${INSTALL_DIR}/backups/security

# Funzione di progresso
progress_bar() {
    local title="$1"
    local completed="$2"
    local width=50
    local percentage=$((completed * 100 / 100))
    local completed_width=$((completed * width / 100))
    
    # Pulisci riga e crea la barra di progresso
    printf "\r%-30s [" "$title"
    for ((i=0; i<width; i++)); do
        if [ "$i" -lt "$completed_width" ]; then
            printf "#"
        else
            printf " "
        fi
    done
    printf "] %3d%%" "$percentage"
    
    # Vai a capo se completato
    if [ "$completed" -eq 100 ]; then
        printf "\n"
    fi
}

# 1. Installazione dipendenze
install_dependencies() {
    print_message "Installazione delle dipendenze di sistema..."
    progress_bar "Installazione dipendenze" 0
    
    # Aggiorna i repository
    apt-get update
    
    # Installa i pacchetti essenziali
    apt-get install -y \
        python3 python3-pip python3-venv \
        postgresql postgresql-contrib \
        nginx certbot python3-certbot-nginx \
        redis-server ufw fail2ban \
        git curl wget vim \
        libpq-dev
    
    progress_bar "Installazione dipendenze" 50
    
    # Crea ambiente virtuale Python
    if [ ! -d "${INSTALL_DIR}/venv" ]; then
        python3 -m venv ${INSTALL_DIR}/venv
    fi
    
    # Installa le dipendenze Python
    source ${INSTALL_DIR}/venv/bin/activate
    pip install --upgrade pip
    pip install psycopg2-binary redis PyYAML cryptography
    pip install flask flask-babel quart requests
    
    # Aggiungi altre dipendenze specifiche
    pip install argon2-cffi python-dotenv pycryptodome
    
    progress_bar "Installazione dipendenze" 100
    print_success "Dipendenze installate con successo"
}

# 2. Installazione nuovi script
install_scripts() {
    print_message "Installazione degli script migliorati..."
    progress_bar "Installazione script" 0
    
    # Copia gli script dal direttorio corrente
    cp ${CURRENT_DIR}/scripts/enhanced_security.py ${SECURITY_DIR}/
    cp ${CURRENT_DIR}/scripts/improved_config_manager.py ${MODULES_DIR}/
    cp ${CURRENT_DIR}/scripts/database_manager.py ${SCRIPTS_DIR}/
    cp ${CURRENT_DIR}/scripts/server_hardening.sh ${SCRIPTS_DIR}/
    
    progress_bar "Installazione script" 40
    
    # Rendi eseguibili gli script bash
    chmod +x ${SCRIPTS_DIR}/server_hardening.sh
    
    # Crea link simbolici nei percorsi appropriati per i moduli Python
    ln -sf ${SECURITY_DIR}/enhanced_security.py ${INSTALL_DIR}/venv/lib/python*/site-packages/m4bot_security.py
    ln -sf ${MODULES_DIR}/improved_config_manager.py ${INSTALL_DIR}/venv/lib/python*/site-packages/m4bot_config.py
    
    progress_bar "Installazione script" 80
    
    # Crea script di avvio per i nuovi moduli
    cat << EOF > ${SCRIPTS_DIR}/run_security_check.sh
#!/bin/bash
# Script per eseguire i controlli di sicurezza migliorati

source ${INSTALL_DIR}/venv/bin/activate
python ${SECURITY_DIR}/enhanced_security.py
EOF
    
    chmod +x ${SCRIPTS_DIR}/run_security_check.sh
    
    progress_bar "Installazione script" 100
    print_success "Script installati con successo"
}

# 3. Configurazione del database
setup_database() {
    print_message "Configurazione del database PostgreSQL..."
    progress_bar "Configurazione database" 0
    
    # Verifica se PostgreSQL è in esecuzione
    if ! systemctl is-active --quiet postgresql; then
        systemctl start postgresql
        systemctl enable postgresql
    fi
    
    progress_bar "Configurazione database" 30
    
    # Configura il database manager
    cat << EOF > ${INSTALL_DIR}/config/database.yaml
host: localhost
port: 5432
user: m4bot
password: $(openssl rand -hex 16)
database: m4bot
backup_dir: ${INSTALL_DIR}/backups/database
EOF
    
    progress_bar "Configurazione database" 60
    
    # Crea utente e database
    su - postgres -c "psql -c \"CREATE USER m4bot WITH ENCRYPTED PASSWORD '$(grep password ${INSTALL_DIR}/config/database.yaml | cut -d' ' -f2)';\""
    su - postgres -c "psql -c \"CREATE DATABASE m4bot OWNER m4bot;\""
    su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE m4bot TO m4bot;\""
    
    progress_bar "Configurazione database" 100
    print_success "Database configurato con successo"
}

# 4. Configurazione della sicurezza
setup_security() {
    print_message "Configurazione della sicurezza avanzata..."
    progress_bar "Configurazione sicurezza" 0
    
    # Crea directory di configurazione per la sicurezza
    mkdir -p ${INSTALL_DIR}/config/security
    
    # Genera una chiave di crittografia per il KeyVault
    ENCRYPTION_KEY=$(python3 -c "import base64; import os; print(base64.urlsafe_b64encode(os.urandom(32)).decode('utf-8'))")
    
    # Crea file di configurazione della sicurezza
    cat << EOF > ${INSTALL_DIR}/config/security/security.yaml
encryption:
  master_key_file: ${SECURITY_DIR}/master.key
  vault_path: ${SECURITY_DIR}/keyvault.enc

intrusion_detection:
  enabled: true
  check_interval: 300
  log_file: ${LOG_DIR}/ids.log
  notify_email: root@localhost

firewall:
  enabled: true
  allowed_ports:
    - 22
    - 80
    - 443
    - 5000
    - 5432
    - 6379

backup:
  enabled: true
  auto_backup: true
  interval: 86400
  keep_days: 30
  backup_dir: ${INSTALL_DIR}/backups/security
EOF
    
    progress_bar "Configurazione sicurezza" 50
    
    # Crea script cron per controlli di sicurezza periodici
    cat << EOF > /etc/cron.d/m4bot-security
# M4Bot Security Checks
0 */6 * * * root ${SCRIPTS_DIR}/run_security_check.sh > ${LOG_DIR}/security_check.log 2>&1
EOF
    
    # Imposta permessi corretti sui file di sicurezza
    chmod 600 ${INSTALL_DIR}/config/security/security.yaml
    chmod 600 /etc/cron.d/m4bot-security
    
    progress_bar "Configurazione sicurezza" 100
    print_success "Sicurezza configurata con successo"
}

# 5. Configurazione del gestore configurazioni
setup_config_manager() {
    print_message "Configurazione del gestore di configurazioni avanzato..."
    progress_bar "Config Manager" 0
    
    # Crea directory per le configurazioni
    mkdir -p ${INSTALL_DIR}/config/app
    
    # Crea configurazione di base
    cat << EOF > ${INSTALL_DIR}/config/app/config.yml
app_name: "M4Bot"
version: "1.1.0"
debug: false
log_level: "INFO"

database:
  url: "postgresql://m4bot:$(grep password ${INSTALL_DIR}/config/database.yaml | cut -d' ' -f2)@localhost:5432/m4bot"
  pool_size: 10
  timeout: 30

web:
  host: "0.0.0.0"
  port: 5000
  workers: 4
  ssl: true
  domain: "m4bot.example.com"

security:
  encryption_key: "${ENCRYPTION_KEY}"
  session_timeout: 30
  max_failed_logins: 5
  
logging:
  file: "${LOG_DIR}/app.log"
  level: "INFO"
  max_size_mb: 10
  backup_count: 5
EOF
    
    progress_bar "Config Manager" 50
    
    # Crea script di avvio per il gestore configurazioni
    cat << EOF > ${SCRIPTS_DIR}/validate_config.sh
#!/bin/bash
# Script per validare la configurazione

source ${INSTALL_DIR}/venv/bin/activate
python ${MODULES_DIR}/improved_config_manager.py validate
EOF
    
    chmod +x ${SCRIPTS_DIR}/validate_config.sh
    
    progress_bar "Config Manager" 100
    print_success "Gestore configurazioni configurato con successo"
}

# 6. Configurazione dei servizi systemd
setup_services() {
    print_message "Configurazione dei servizi systemd..."
    progress_bar "Configurazione servizi" 0
    
    # Servizio principale M4Bot
    cat << EOF > /etc/systemd/system/m4bot.service
[Unit]
Description=M4Bot Main Service
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
Type=simple
User=m4bot
Group=m4bot
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/bot/m4bot.py
Restart=on-failure
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=m4bot

[Install]
WantedBy=multi-user.target
EOF
    
    # Servizio web M4Bot
    cat << EOF > /etc/systemd/system/m4bot-web.service
[Unit]
Description=M4Bot Web Service
After=network.target postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
Type=simple
User=m4bot
Group=m4bot
WorkingDirectory=${INSTALL_DIR}/web
ExecStart=${INSTALL_DIR}/venv/bin/python ${INSTALL_DIR}/web/app.py
Restart=on-failure
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=m4bot-web

[Install]
WantedBy=multi-user.target
EOF

    # Servizio di monitoraggio M4Bot
    cat << EOF > /etc/systemd/system/m4bot-monitor.service
[Unit]
Description=M4Bot Health Monitoring Service
After=network.target

[Service]
Type=simple
User=m4bot
Group=m4bot
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/python ${SCRIPTS_DIR}/health_monitor.py
Restart=on-failure
RestartSec=10
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=m4bot-monitor

[Install]
WantedBy=multi-user.target
EOF
    
    progress_bar "Configurazione servizi" 50
    
    # Ricarica systemd
    systemctl daemon-reload
    
    # Crea utente m4bot se non esiste
    if ! id -u m4bot > /dev/null 2>&1; then
        useradd -r -m -s /bin/bash m4bot
    fi
    
    # Imposta proprietà delle directory
    chown -R m4bot:m4bot ${INSTALL_DIR}
    
    progress_bar "Configurazione servizi" 100
    print_success "Servizi systemd configurati con successo"
}

# 7. Configurazione di Nginx
setup_nginx() {
    print_message "Configurazione di Nginx come reverse proxy..."
    progress_bar "Configurazione Nginx" 0
    
    # Crea configurazione di Nginx
    cat << EOF > /etc/nginx/sites-available/m4bot
server {
    listen 80;
    server_name m4bot.example.com;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    location /static {
        alias ${INSTALL_DIR}/web/static;
        expires 30d;
    }
    
    location /api {
        proxy_pass http://127.0.0.1:5000/api;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
    
    # Security headers
    add_header X-Content-Type-Options nosniff;
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-XSS-Protection "1; mode=block";
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:;";
    add_header Referrer-Policy "strict-origin-when-cross-origin";
}
EOF
    
    progress_bar "Configurazione Nginx" 40
    
    # Attiva la configurazione
    if [ ! -e /etc/nginx/sites-enabled/m4bot ]; then
        ln -s /etc/nginx/sites-available/m4bot /etc/nginx/sites-enabled/
    fi
    
    # Verifica la configurazione di Nginx
    nginx -t
    
    progress_bar "Configurazione Nginx" 80
    
    # Riavvia Nginx se la configurazione è corretta
    if [ $? -eq 0 ]; then
        systemctl restart nginx
    else
        print_warning "La configurazione di Nginx ha errori. Controlla /etc/nginx/sites-available/m4bot"
    fi
    
    progress_bar "Configurazione Nginx" 100
    print_success "Nginx configurato con successo"
}

# 8. Hardening del server
run_hardening() {
    print_message "Esecuzione dell'hardening del server..."
    
    # Esegui lo script di hardening
    bash ${SCRIPTS_DIR}/server_hardening.sh
    
    print_success "Hardening del server completato"
}

# 9. Finalizzazione dell'installazione
finalize_installation() {
    print_message "Finalizzazione dell'installazione..."
    progress_bar "Finalizzazione" 0
    
    # Crea file README con istruzioni
    cat << EOF > ${INSTALL_DIR}/README_MIGLIORIE.md
# Migliorie installate per M4Bot

## Riepilogo delle migliorie

1. **Sicurezza Avanzata**
   - Sistema KeyVault per la gestione sicura delle chiavi crittografiche
   - Intrustion Detection System (IDS) integrato
   - Hardening del server completo
   - Firewall e WAF configurati

2. **Gestione Configurazioni**
   - Gestore configurazioni con supporto multi-formato (YAML, JSON, ENV)
   - Validazione automatica delle configurazioni
   - Backup e ripristino configurazioni

3. **Database Manager**
   - Utility per backup e ripristino automatico
   - Ottimizzazione automatica delle prestazioni
   - Monitoraggio dimensioni tabelle

4. **Servizi Systemd**
   - Configurazione ottimizzata dei servizi
   - Monitoraggio stato di salute
   - Riavvio automatico in caso di errori

## Come usare le nuove funzionalità

### Sicurezza Avanzata
\`\`\`bash
# Esegui un controllo di sicurezza manuale
${SCRIPTS_DIR}/run_security_check.sh

# Esegui l'hardening del server
${SCRIPTS_DIR}/server_hardening.sh
\`\`\`

### Gestione Database
\`\`\`bash
# Backup del database
${SCRIPTS_DIR}/database_manager.py backup

# Ottimizzazione del database
${SCRIPTS_DIR}/database_manager.py optimize
\`\`\`

### Gestione Configurazioni
\`\`\`bash
# Validazione configurazione
${SCRIPTS_DIR}/validate_config.sh
\`\`\`

## Manutenzione

I backup vengono creati automaticamente in:
- ${INSTALL_DIR}/backups/database
- ${INSTALL_DIR}/backups/security

I log si trovano in:
- ${LOG_DIR}

## Contatti

Per assistenza: support@m4bot.example.com
EOF
    
    progress_bar "Finalizzazione" 50
    
    # Imposta permessi corretti
    chmod -R 750 ${SCRIPTS_DIR}
    chmod -R 640 ${INSTALL_DIR}/config
    chmod -R 750 ${MODULES_DIR}
    chmod -R 750 ${SECURITY_DIR}
    chmod -R 770 ${LOG_DIR}
    
    progress_bar "Finalizzazione" 100
    print_success "Installazione finalizzata con successo"
}

# Funzione principale
main() {
    print_message "INIZIO INSTALLAZIONE MIGLIORIE M4BOT"
    echo "Questo script installerà tutte le migliorie per M4Bot in una configurazione Linux."
    echo ""
    
    # Chiedi all'utente se continuare
    read -p "Vuoi procedere con l'installazione? [s/n]: " response
    if [[ ! "$response" =~ ^[Ss] ]]; then
        print_message "Installazione annullata dall'utente"
        exit 0
    fi
    
    # Esegui tutti i passaggi di installazione
    install_dependencies
    install_scripts
    setup_database
    setup_security
    setup_config_manager
    setup_services
    setup_nginx
    
    # Chiedi se eseguire l'hardening
    read -p "Vuoi eseguire l'hardening del server? [s/n]: " response
    if [[ "$response" =~ ^[Ss] ]]; then
        run_hardening
    else
        print_warning "Hardening del server saltato. Puoi eseguirlo manualmente in seguito con ${SCRIPTS_DIR}/server_hardening.sh"
    fi
    
    finalize_installation
    
    print_message "INSTALLAZIONE COMPLETATA CON SUCCESSO"
    echo ""
    echo "Le migliorie sono state installate. Leggi ${INSTALL_DIR}/README_MIGLIORIE.md per ulteriori dettagli."
    echo ""
    echo "Ricordati di modificare le configurazioni di esempio in base alle tue esigenze:"
    echo "- ${INSTALL_DIR}/config/app/config.yml"
    echo "- ${INSTALL_DIR}/config/security/security.yaml"
    echo "- ${INSTALL_DIR}/config/database.yaml"
    echo ""
    echo "È necessario riavviare per applicare tutte le modifiche."
    read -p "Vuoi riavviare ora? [s/n]: " response
    if [[ "$response" =~ ^[Ss] ]]; then
        reboot
    else
        print_warning "Ricordati di riavviare il sistema per applicare tutte le modifiche"
    fi
}

# Esegui la funzione principale
main 