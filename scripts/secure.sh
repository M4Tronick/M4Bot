#!/bin/bash
# Script per migliorare la sicurezza del server M4Bot
# Da eseguire dopo l'installazione iniziale

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

print_message "Configurazione delle impostazioni di sicurezza per M4Bot..."

# Installa fail2ban per proteggere da tentativi di accesso non autorizzati
print_message "Installazione di fail2ban..."
apt-get install -y fail2ban || print_error "Impossibile installare fail2ban" 1

# Configura fail2ban per Nginx
cat > /etc/fail2ban/jail.d/nginx.conf << EOF
[nginx-http-auth]
enabled = true
port = http,https
filter = nginx-http-auth
logpath = /var/log/nginx/error.log
maxretry = 5
bantime = 3600
findtime = 600

[nginx-login]
enabled = true
port = http,https
filter = nginx-login
logpath = /var/log/nginx/access.log
maxretry = 5
bantime = 3600
findtime = 600
EOF

# Configura il firewall UFW
print_message "Configurazione del firewall UFW..."
apt-get install -y ufw || print_warning "UFW già installato o impossibile installare"

# Configura le regole UFW
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow http
ufw allow https
ufw allow 5432/tcp comment 'PostgreSQL'

# Abilita UFW in modo non interattivo
print_message "Abilitazione di UFW..."
echo "y" | ufw enable

# Hardening della configurazione SSL di Nginx
print_message "Hardening della configurazione SSL di Nginx..."
cat > /etc/nginx/snippets/ssl-params.conf << EOF
ssl_protocols TLSv1.2 TLSv1.3;
ssl_prefer_server_ciphers on;
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
ssl_session_timeout 1d;
ssl_session_cache shared:SSL:10m;
ssl_session_tickets off;
ssl_stapling on;
ssl_stapling_verify on;
resolver 8.8.8.8 8.8.4.4 valid=300s;
resolver_timeout 5s;
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload";
add_header X-Frame-Options SAMEORIGIN;
add_header X-Content-Type-Options nosniff;
add_header X-XSS-Protection "1; mode=block";
EOF

# Aggiorna il sito Nginx per includere i parametri SSL rafforzati
if [ -f /etc/nginx/sites-available/m4bot ]; then
    # Cerca se è già configurato SSL
    if grep -q "ssl_certificate" /etc/nginx/sites-available/m4bot; then
        print_message "Aggiornamento della configurazione SSL di Nginx..."
        # Aggiunge l'inclusione dei parametri SSL se non presente
        if ! grep -q "include snippets/ssl-params.conf" /etc/nginx/sites-available/m4bot; then
            sed -i '/ssl_certificate/a\\tinclude snippets/ssl-params.conf;' /etc/nginx/sites-available/m4bot
        fi
    else
        print_warning "Il sito Nginx non ha ancora SSL configurato. Eseguire prima la configurazione SSL."
    fi
    
    # Riavvia Nginx per applicare le modifiche
    systemctl restart nginx
else
    print_warning "File di configurazione Nginx non trovato. Saltando l'hardening SSL."
fi

# Configurazione dei permessi dei file
print_message "Configurazione dei permessi dei file..."
find /opt/m4bot -type f -exec chmod 640 {} \;
find /opt/m4bot -type d -exec chmod 750 {} \;
chmod 600 /opt/m4bot/.env
chmod +x /opt/m4bot/bot/m4bot.py
chmod +x /opt/m4bot/web/app.py
chown -R m4bot:m4bot /opt/m4bot

# Configurazione della protezione DDoS di base in Nginx
print_message "Configurazione della protezione DDoS di base in Nginx..."
cat > /etc/nginx/conf.d/rate-limit.conf << EOF
limit_req_zone \$binary_remote_addr zone=m4bot_limit:10m rate=10r/s;
EOF

if [ -f /etc/nginx/sites-available/m4bot ]; then
    # Aggiunge il rate limiting alla location principale se non presente
    if ! grep -q "limit_req" /etc/nginx/sites-available/m4bot; then
        sed -i '/location \/ {/a\\t\tlimit_req zone=m4bot_limit burst=20 nodelay;' /etc/nginx/sites-available/m4bot
    fi
    
    # Riavvia Nginx per applicare le modifiche
    systemctl restart nginx
fi

# Riavvio dei servizi di sicurezza
print_message "Riavvio dei servizi di sicurezza..."
systemctl restart fail2ban

print_success "Configurazione di sicurezza completata!"
print_message "Il server è ora protetto con:"
print_message "- Firewall UFW"
print_message "- Fail2ban per prevenire attacchi brute force"
print_message "- Configurazione SSL rafforzata"
print_message "- Protezione DDoS di base"
print_message "- Permessi di file sicuri" 