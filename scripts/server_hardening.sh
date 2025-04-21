#!/bin/bash
# Script per l'hardening di sicurezza del server Linux

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

# Directory di base
INSTALL_DIR="/opt/m4bot"
LOG_DIR="${INSTALL_DIR}/logs"
BACKUP_DIR="${INSTALL_DIR}/backups/security"

# Crea directory per log e backup se non esistono
mkdir -p ${LOG_DIR}
mkdir -p ${BACKUP_DIR}

# Log delle operazioni
HARDENING_LOG="${LOG_DIR}/security_hardening.log"
touch ${HARDENING_LOG}

log_message() {
    local message="$1"
    local date=$(date "+%Y-%m-%d %H:%M:%S")
    echo "${date} - ${message}" >> ${HARDENING_LOG}
    echo "${message}"
}

log_message "Avvio processo di hardening del server..."

# Backup dei file di configurazione originali
backup_config() {
    local file="$1"
    local backup_dir="${BACKUP_DIR}/$(dirname $file)"
    
    if [ -f "$file" ]; then
        mkdir -p "$backup_dir"
        cp "$file" "${BACKUP_DIR}/${file}.bak-$(date +%Y%m%d%H%M%S)"
        log_message "Backup di $file creato"
    else
        log_message "File $file non trovato, impossibile creare backup"
    fi
}

# 1. Aggiornamento del sistema
update_system() {
    print_message "Aggiornamento del sistema..."
    log_message "Avvio aggiornamento del sistema"
    
    # Aggiorna repository e pacchetti
    if apt-get update && apt-get upgrade -y; then
        print_success "Sistema aggiornato"
        log_message "Sistema aggiornato con successo"
    else
        print_error "Errore nell'aggiornamento del sistema"
        log_message "Errore nell'aggiornamento del sistema"
    fi
}

# 2. Configurazione del firewall (UFW)
setup_firewall() {
    print_message "Configurazione del firewall (UFW)..."
    log_message "Avvio configurazione firewall"
    
    # Installa UFW se non è già presente
    if ! command -v ufw &> /dev/null; then
        apt-get install -y ufw
        log_message "UFW installato"
    fi
    
    # Configura le regole del firewall
    ufw default deny incoming
    ufw default allow outgoing
    
    # Permetti SSH e web
    ufw allow ssh
    ufw allow http
    ufw allow https
    
    # Permetti altri servizi necessari
    ufw allow 5000/tcp # Flask
    ufw allow 5432/tcp # PostgreSQL
    ufw allow 6379/tcp # Redis
    
    # Abilita il firewall
    ufw --force enable
    
    print_success "Firewall configurato e attivato"
    log_message "Firewall configurato"
}

# 3. Hardening SSH
harden_ssh() {
    print_message "Configurazione sicura di SSH..."
    log_message "Avvio configurazione SSH"
    
    SSH_CONFIG="/etc/ssh/sshd_config"
    backup_config ${SSH_CONFIG}
    
    # Modifica il file di configurazione SSH
    sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' ${SSH_CONFIG}
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' ${SSH_CONFIG}
    sed -i 's/#PubkeyAuthentication yes/PubkeyAuthentication yes/' ${SSH_CONFIG}
    
    # Cambia la porta SSH se richiesto
    read -p "Vuoi cambiare la porta SSH standard (22)? [s/n]: " change_port
    if [[ "$change_port" =~ ^[Ss] ]]; then
        read -p "Inserisci la nuova porta SSH (consigliato: 2222): " ssh_port
        if [[ "$ssh_port" =~ ^[0-9]+$ ]] && [ "$ssh_port" -gt 1024 ] && [ "$ssh_port" -lt 65535 ]; then
            sed -i "s/#Port 22/Port ${ssh_port}/" ${SSH_CONFIG}
            ufw delete allow ssh
            ufw allow ${ssh_port}/tcp
            log_message "Porta SSH cambiata in ${ssh_port}"
        else
            print_error "Porta non valida, mantengo la porta 22"
            log_message "Tentativo fallito di cambiare la porta SSH"
        fi
    fi
    
    # Riavvia il servizio SSH
    systemctl restart sshd
    
    print_success "Configurazione SSH completata"
    log_message "Configurazione SSH completata"
}

# 4. Hardening kernel e networking
harden_kernel() {
    print_message "Hardening kernel e networking..."
    log_message "Avvio hardening kernel"
    
    SYSCTL_CONFIG="/etc/sysctl.conf"
    backup_config ${SYSCTL_CONFIG}
    
    # Aggiungi parametri di sicurezza al kernel
    cat << EOF >> ${SYSCTL_CONFIG}

# M4Bot Security Hardening
# Proteggi dalla scansione delle porte
net.ipv4.tcp_syncookies = 1
# Disabilita IP forwarding
net.ipv4.ip_forward = 0
# Ignora ping richieste di broadcast
net.ipv4.icmp_echo_ignore_broadcasts = 1
# Ignora messaggi di errore bogus
net.ipv4.icmp_ignore_bogus_error_responses = 1
# Proteggi da IP spoofing
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
# Registra pacchetti sospetti
net.ipv4.conf.all.log_martians = 1
net.ipv4.conf.default.log_martians = 1
# Disabilita routing di pacchetti
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
# Disabilita redirect ICMP
net.ipv4.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0
# Disabilita secure redirect ICMP
net.ipv4.conf.all.secure_redirects = 0
net.ipv4.conf.default.secure_redirects = 0
# Disabilita invio di redirect
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0
# Proteggi da problemi di memoria
kernel.randomize_va_space = 2
# Limita l'accesso dmesg
kernel.dmesg_restrict = 1
# Previeni uso di symlink su file di altri utenti
fs.protected_symlinks = 1
# Previeni uso di hardlink su file di altri utenti
fs.protected_hardlinks = 1
EOF
    
    # Applica i cambiamenti
    sysctl -p
    
    print_success "Configurazione kernel completata"
    log_message "Configurazione kernel completata"
}

# 5. Configurazione fail2ban
setup_fail2ban() {
    print_message "Configurazione fail2ban..."
    log_message "Avvio configurazione fail2ban"
    
    # Installa fail2ban se non è già presente
    if ! command -v fail2ban-client &> /dev/null; then
        apt-get install -y fail2ban
        log_message "Fail2ban installato"
    fi
    
    # Configura fail2ban
    FAIL2BAN_CONFIG="/etc/fail2ban/jail.local"
    backup_config ${FAIL2BAN_CONFIG}
    
    cat << EOF > ${FAIL2BAN_CONFIG}
[DEFAULT]
# Ban hosts per 1 ora
bantime = 3600
# Intervallo di ricerca nel log
findtime = 600
# 5 tentativi falliti triggerano un ban
maxretry = 5
# Email di notifica
destemail = root@localhost
sendername = Fail2Ban
# Ban action
banaction = iptables-multiport
action = %(action_mwl)s

# SSH jail
[sshd]
enabled = true
port = ssh
filter = sshd
logpath = /var/log/auth.log
maxretry = 3

# Web protection (nginx)
[nginx-http-auth]
enabled = true
filter = nginx-http-auth
port = http,https
logpath = /var/log/nginx/error.log

# Protezione servizi web M4Bot
[m4bot-web]
enabled = true
port = http,https,5000
filter = m4bot-web
logpath = ${LOG_DIR}/web.log
maxretry = 6
findtime = 300
bantime = 7200
EOF
    
    # Crea un filtro personalizzato per M4Bot
    FAIL2BAN_FILTER="/etc/fail2ban/filter.d/m4bot-web.conf"
    
    cat << EOF > ${FAIL2BAN_FILTER}
[Definition]
failregex = ^.*Failed login attempt from <HOST>.*$
            ^.*Unauthorized access attempt from <HOST>.*$
            ^.*Possible brute force attack from <HOST>.*$
ignoreregex =
EOF
    
    # Avvia o riavvia fail2ban
    systemctl enable fail2ban
    systemctl restart fail2ban
    
    print_success "Fail2ban configurato"
    log_message "Fail2ban configurato"
}

# 6. Configurazione di ModSecurity per Nginx (WAF)
setup_modsecurity() {
    print_message "Configurazione di ModSecurity (Web Application Firewall)..."
    log_message "Avvio configurazione ModSecurity"
    
    # Installa i pacchetti necessari
    apt-get install -y nginx-extras libapache2-mod-security2
    
    # Backup dei file di configurazione di Nginx
    NGINX_CONFIG="/etc/nginx/nginx.conf"
    backup_config ${NGINX_CONFIG}
    
    # Cartella per ModSecurity
    mkdir -p /etc/nginx/modsecurity
    
    # Copia la configurazione di esempio
    cp /etc/modsecurity/modsecurity.conf-recommended /etc/nginx/modsecurity/modsecurity.conf
    
    # Abilita ModSecurity
    sed -i 's/SecRuleEngine DetectionOnly/SecRuleEngine On/' /etc/nginx/modsecurity/modsecurity.conf
    
    # Aggiungi ModSecurity alla configurazione di Nginx
    if ! grep -q "modsecurity on" ${NGINX_CONFIG}; then
        sed -i '/http {/a \\n    # ModSecurity WAF\n    modsecurity on;\n    modsecurity_rules_file /etc/nginx/modsecurity/modsecurity.conf;\n' ${NGINX_CONFIG}
    fi
    
    # Scarica regole OWASP Core Rule Set (CRS)
    if [ ! -d "/etc/nginx/modsecurity/owasp-crs" ]; then
        apt-get install -y git
        git clone https://github.com/coreruleset/coreruleset.git /etc/nginx/modsecurity/owasp-crs
        cp /etc/nginx/modsecurity/owasp-crs/crs-setup.conf.example /etc/nginx/modsecurity/owasp-crs/crs-setup.conf
        
        # Attiva le regole CRS nel file di configurazione
        echo "Include /etc/nginx/modsecurity/owasp-crs/crs-setup.conf" >> /etc/nginx/modsecurity/modsecurity.conf
        echo "Include /etc/nginx/modsecurity/owasp-crs/rules/*.conf" >> /etc/nginx/modsecurity/modsecurity.conf
    fi
    
    # Verifica la configurazione di Nginx
    nginx -t
    
    # Se la verifica ha avuto successo, riavvia Nginx
    if [ $? -eq 0 ]; then
        systemctl restart nginx
        print_success "ModSecurity (WAF) configurato"
        log_message "ModSecurity configurato con successo"
    else
        print_error "Errore nella configurazione di ModSecurity"
        log_message "Errore nella configurazione di ModSecurity"
    fi
}

# 7. Installazione e configurazione di Rootkit Hunter
setup_rkhunter() {
    print_message "Installazione di Rootkit Hunter..."
    log_message "Avvio installazione rkhunter"
    
    # Installa rkhunter
    apt-get install -y rkhunter
    
    # Aggiorna il database
    rkhunter --update
    rkhunter --propupd
    
    # Configura la scansione giornaliera
    RKHUNTER_CONFIG="/etc/default/rkhunter"
    backup_config ${RKHUNTER_CONFIG}
    
    # Modifica per scansioni automatiche
    sed -i 's/CRON_DAILY_RUN=""/CRON_DAILY_RUN="true"/' ${RKHUNTER_CONFIG}
    sed -i 's/CRON_DB_UPDATE=""/CRON_DB_UPDATE="true"/' ${RKHUNTER_CONFIG}
    
    # Esegui una scansione iniziale
    rkhunter --check --sk
    
    print_success "Rootkit Hunter installato e configurato"
    log_message "Rootkit Hunter configurato"
}

# 8. Hardening delle risorse del sistema
harden_resources() {
    print_message "Hardening delle risorse di sistema..."
    log_message "Avvio hardening risorse"
    
    # Limiti di sistema
    LIMITS_CONFIG="/etc/security/limits.conf"
    backup_config ${LIMITS_CONFIG}
    
    # Aggiungi limiti per prevenire fork bomb e altre risorse
    cat << EOF >> ${LIMITS_CONFIG}

# M4Bot Security Limits
* soft nproc 2048
* hard nproc 4096
* soft nofile 4096
* hard nofile 8192
EOF
    
    # Configura le opzioni di avvio
    GRUB_CONFIG="/etc/default/grub"
    backup_config ${GRUB_CONFIG}
    
    # Aggiorna i parametri di avvio del kernel
    if [ -f ${GRUB_CONFIG} ]; then
        # Aggiungi opzioni per la sicurezza
        sed -i 's/GRUB_CMDLINE_LINUX=""/GRUB_CMDLINE_LINUX="ipv6.disable=1 audit=1 apparmor=1 security=apparmor"/' ${GRUB_CONFIG}
        
        # Aggiorna GRUB
        update-grub
    fi
    
    print_success "Hardening delle risorse completato"
    log_message "Hardening risorse completato"
}

# 9. Hardening delle password
harden_passwords() {
    print_message "Configurazione delle politiche di password..."
    log_message "Avvio configurazione politiche password"
    
    # Installa pacchetto per la configurazione delle politiche di password
    apt-get install -y libpam-pwquality
    
    # Backup dei file di configurazione
    PAM_CONFIG="/etc/pam.d/common-password"
    backup_config ${PAM_CONFIG}
    
    # Modifica la configurazione PAM per password più sicure
    if grep -q "pam_pwquality.so" ${PAM_CONFIG}; then
        sed -i 's/pam_pwquality.so.*/pam_pwquality.so retry=3 minlen=12 difok=3 ucredit=-1 lcredit=-1 dcredit=-1 ocredit=-1 reject_username enforce_for_root/' ${PAM_CONFIG}
    else
        sed -i '/pam_unix.so/i password        requisite                       pam_pwquality.so retry=3 minlen=12 difok=3 ucredit=-1 lcredit=-1 dcredit=-1 ocredit=-1 reject_username enforce_for_root' ${PAM_CONFIG}
    fi
    
    # Configura il modulo pwquality
    PWQUALITY_CONFIG="/etc/security/pwquality.conf"
    backup_config ${PWQUALITY_CONFIG}
    
    cat << EOF > ${PWQUALITY_CONFIG}
# Configurazione della qualità delle password per M4Bot
# Minimo 12 caratteri
minlen = 12
# Almeno 1 maiuscola
ucredit = -1
# Almeno 1 minuscola
lcredit = -1
# Almeno 1 numero
dcredit = -1
# Almeno 1 carattere speciale
ocredit = -1
# Massimo 3 caratteri uguali consecutivi
maxrepeat = 3
# Almeno 3 caratteri differenti rispetto alla password precedente
difok = 3
# Rifiuta se contiene il nome utente
reject_username = 1
# 3 tentativi prima del blocco
retry = 3
# Applica anche a root
enforce_for_root = 1
EOF
    
    print_success "Politiche di password configurate"
    log_message "Politiche di password configurate"
}

# 10. Configurazione di lynis (audit di sicurezza)
setup_lynis() {
    print_message "Configurazione di Lynis (audit di sicurezza)..."
    log_message "Avvio configurazione Lynis"
    
    # Installa Lynis
    apt-get install -y lynis
    
    # Crea directory per i report
    LYNIS_REPORT_DIR="${LOG_DIR}/security/lynis"
    mkdir -p ${LYNIS_REPORT_DIR}
    
    # Crea script per audit automatico
    LYNIS_SCRIPT="/usr/local/bin/m4bot-security-audit.sh"
    
    cat << EOF > ${LYNIS_SCRIPT}
#!/bin/bash
# Script per l'audit di sicurezza automatico
DATE=\$(date +%Y%m%d)
REPORT_FILE="${LYNIS_REPORT_DIR}/lynis-report-\${DATE}.txt"
LOG_FILE="${LYNIS_REPORT_DIR}/lynis-log-\${DATE}.log"

# Esegui l'audit
lynis audit system --verbose --report-file=\${REPORT_FILE} > \${LOG_FILE} 2>&1

# Invia email con i risultati
if command -v mail > /dev/null; then
    echo "Report di sicurezza M4Bot del \${DATE}" | mail -s "M4Bot Security Audit" -a \${REPORT_FILE} root
fi
EOF
    
    # Rendi eseguibile lo script
    chmod +x ${LYNIS_SCRIPT}
    
    # Crea job cron settimanale
    CRON_FILE="/etc/cron.weekly/m4bot-security-audit"
    
    cat << EOF > ${CRON_FILE}
#!/bin/bash
# Job cron per l'audit di sicurezza settimanale
/usr/local/bin/m4bot-security-audit.sh
EOF
    
    chmod +x ${CRON_FILE}
    
    # Esegui un audit iniziale
    print_message "Esecuzione audit di sicurezza iniziale..."
    
    lynis audit system --quick
    
    print_success "Lynis configurato per audit settimanali"
    log_message "Lynis configurato"
}

# Funzione principale
main() {
    print_message "INIZIO PROCESSO DI HARDENING DEL SERVER"
    
    # Chiedi all'utente quali passaggi eseguire
    echo "Seleziona i passaggi di hardening da eseguire:"
    echo "1) Aggiornamento del sistema"
    echo "2) Configurazione del firewall (UFW)"
    echo "3) Hardening SSH"
    echo "4) Hardening kernel e networking"
    echo "5) Configurazione fail2ban"
    echo "6) Configurazione di ModSecurity (WAF)"
    echo "7) Installazione di Rootkit Hunter"
    echo "8) Hardening delle risorse di sistema"
    echo "9) Hardening delle password"
    echo "10) Configurazione di Lynis (audit di sicurezza)"
    echo "11) Esegui TUTTI i passaggi"
    echo ""
    
    read -p "Inserisci i numeri separati da spazio (es: 1 3 5) o 11 per tutti: " STEPS
    
    # Converti l'input in array
    read -a STEPS_ARRAY <<< "$STEPS"
    
    # Se l'utente ha selezionato "11", esegui tutti i passaggi
    if [[ " ${STEPS_ARRAY[@]} " =~ " 11 " ]]; then
        update_system
        setup_firewall
        harden_ssh
        harden_kernel
        setup_fail2ban
        setup_modsecurity
        setup_rkhunter
        harden_resources
        harden_passwords
        setup_lynis
    else
        # Esegui solo i passaggi selezionati
        for step in "${STEPS_ARRAY[@]}"; do
            case $step in
                1) update_system ;;
                2) setup_firewall ;;
                3) harden_ssh ;;
                4) harden_kernel ;;
                5) setup_fail2ban ;;
                6) setup_modsecurity ;;
                7) setup_rkhunter ;;
                8) harden_resources ;;
                9) harden_passwords ;;
                10) setup_lynis ;;
                *) print_warning "Passaggio $step non valido, ignorato" ;;
            esac
        done
    fi
    
    print_message "PROCESSO DI HARDENING DEL SERVER COMPLETATO"
    log_message "Processo di hardening completato"
    
    echo ""
    echo "Log delle operazioni: ${HARDENING_LOG}"
    echo "Backup dei file di configurazione: ${BACKUP_DIR}"
    echo ""
    echo "Si consiglia di riavviare il sistema per applicare tutte le modifiche."
    echo "Vuoi riavviare ora? (s/n)"
    
    read -p "Riavviare? [s/n]: " REBOOT
    if [[ "$REBOOT" =~ ^[Ss] ]]; then
        log_message "Riavvio del sistema..."
        reboot
    else
        print_warning "Ricordati di riavviare il sistema per applicare tutte le modifiche"
        log_message "Riavvio rimandato dall'utente"
    fi
}

# Esegui la funzione principale
main 