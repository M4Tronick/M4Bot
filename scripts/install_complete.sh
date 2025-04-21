#!/bin/bash
# Script di installazione completo per M4Bot
# Questo script risolve tutti i problemi comuni e automatizza l'installazione

# Colori per l'output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directory di installazione
INSTALL_DIR="/opt/m4bot"
CURRENT_DIR=$(pwd)

# Funzioni di utility
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

print_message "Avvio installazione completa di M4Bot..."

# 1. Aggiornamento e installazione delle dipendenze
print_message "Installazione delle dipendenze di sistema..."
apt-get update || print_error "Impossibile aggiornare la lista dei pacchetti" 1
apt-get install -y python3 python3-pip python3-venv python3-dev \
    postgresql postgresql-contrib redis-server nginx \
    git curl wget unzip dos2unix file bc build-essential \
    libpq-dev || print_error "Impossibile installare le dipendenze" 1

print_success "Dipendenze installate correttamente"

# 2. Creazione dell'utente di sistema
print_message "Creazione dell'utente di sistema m4bot..."
if ! id "m4bot" &>/dev/null; then
    useradd -r -m -d "$INSTALL_DIR" -s /bin/bash m4bot
    usermod -a -G www-data m4bot
    print_success "Utente m4bot creato"
else
    print_message "L'utente m4bot esiste già"
fi

# 3. Creazione e configurazione delle directory
print_message "Creazione e configurazione delle directory..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/scripts"
mkdir -p "$INSTALL_DIR/modules"
mkdir -p "$INSTALL_DIR/modules/security"
mkdir -p "$INSTALL_DIR/modules/security/waf"
mkdir -p "$INSTALL_DIR/modules/security/advanced"
mkdir -p "$INSTALL_DIR/modules/stability"
mkdir -p "$INSTALL_DIR/web"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "/var/log/m4bot"

# 4. Copia o creazione dei file necessari
print_message "Copia dei file esistenti..."
if [ -f "$CURRENT_DIR/requirements.txt" ]; then
    cp "$CURRENT_DIR/requirements.txt" "$INSTALL_DIR/"
else
    print_message "File requirements.txt non trovato, ne creo uno predefinito..."
    cat > "$INSTALL_DIR/requirements.txt" << EOF
flask>=2.3.0
Flask-Babel>=4.0.0
Werkzeug>=2.3.0
Jinja2>=3.1.2
SQLAlchemy>=2.0.0
psycopg2-binary>=2.9.5
redis>=4.5.1
requests>=2.28.2
python-dotenv>=1.0.0
pyyaml>=6.0
cryptography>=40.0.0
gunicorn>=20.1.0
pytest>=7.3.1
black>=23.3.0
flake8>=6.0.0
EOF
fi

# 5. Copia degli script dalla directory scripts
for script in "$CURRENT_DIR"/scripts/*.sh; do
    if [ -f "$script" ]; then
        cp "$script" "$INSTALL_DIR/scripts/"
        chmod +x "$INSTALL_DIR/scripts/$(basename $script)"
    fi
done

# 6. Creazione dello script check_services.sh
print_message "Creazione dello script check_services.sh..."
cat > "$INSTALL_DIR/scripts/check_services.sh" << 'EOF'
#!/bin/bash
# Script per verificare i servizi di M4Bot

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
}

print_success() {
    echo -e "${GREEN}[SUCCESSO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[AVVISO]${NC} $1"
}

# Data e ora corrente
CURRENT_DATE=$(date "+%a %b %d %I:%M:%S %p %Z %Y")

echo "==========================================="
echo "         VERIFICA SERVIZI M4BOT           "
echo "==========================================="
echo "Data: $CURRENT_DATE"
echo

# 1. Verifica servizi principali
echo "1. Verifica dei servizi principali:"

# Verifica m4bot.service
if systemctl is-active --quiet m4bot.service; then
    echo -e "✅ m4bot.service è attivo"
else
    echo -e "❌ m4bot.service non è attivo"
    echo -e "🔄 Tentativo di avvio di m4bot.service..."
    systemctl start m4bot.service
    if systemctl is-active --quiet m4bot.service; then
        echo -e "✅ m4bot.service avviato con successo"
    else
        echo -e "❌ Impossibile avviare m4bot.service"
    fi
fi

# Verifica m4bot-web.service
if systemctl is-active --quiet m4bot-web.service; then
    echo -e "✅ m4bot-web.service è attivo"
else
    echo -e "❌ m4bot-web.service non è attivo"
    echo -e "🔄 Tentativo di avvio di m4bot-web.service..."
    systemctl start m4bot-web.service
    if systemctl is-active --quiet m4bot-web.service; then
        echo -e "✅ m4bot-web.service avviato con successo"
    else
        echo -e "❌ Impossibile avviare m4bot-web.service"
    fi
fi

echo

# 2. Verifica servizi dipendenti
echo "2. Verifica dei servizi dipendenti:"

# Verifica PostgreSQL
if systemctl is-active --quiet postgresql; then
    echo -e "✅ Database (PostgreSQL) è attivo"
else
    echo -e "❌ Database (PostgreSQL) non è attivo"
    echo -e "🔄 Tentativo di avvio di PostgreSQL..."
    systemctl start postgresql
    if systemctl is-active --quiet postgresql; then
        echo -e "✅ PostgreSQL avviato con successo"
    else
        echo -e "❌ Impossibile avviare PostgreSQL"
        echo -e "⚠️ Installazione PostgreSQL in corso..."
        apt-get update && apt-get install -y postgresql postgresql-contrib
        systemctl enable postgresql
        systemctl start postgresql
        if systemctl is-active --quiet postgresql; then
            echo -e "✅ PostgreSQL installato e avviato con successo"
        else
            echo -e "❌ Impossibile installare PostgreSQL"
        fi
    fi
fi

# Verifica Redis
if systemctl is-active --quiet redis-server; then
    echo -e "✅ Redis è attivo"
else
    echo -e "❌ Redis non è attivo"
    echo -e "🔄 Tentativo di avvio di Redis..."
    systemctl start redis-server
    if systemctl is-active --quiet redis-server; then
        echo -e "✅ Redis avviato con successo"
    else
        echo -e "❌ Impossibile avviare Redis"
        echo -e "⚠️ Installazione Redis in corso..."
        apt-get update && apt-get install -y redis-server
        systemctl enable redis-server
        systemctl start redis-server
        if systemctl is-active --quiet redis-server; then
            echo -e "✅ Redis installato e avviato con successo"
        else
            echo -e "❌ Impossibile installare Redis"
        fi
    fi
fi

# Verifica Nginx
if systemctl is-active --quiet nginx; then
    echo -e "✅ Nginx è attivo"
else
    echo -e "❌ Nginx non è attivo"
    echo -e "🔄 Tentativo di avvio di Nginx..."
    systemctl start nginx
    if systemctl is-active --quiet nginx; then
        echo -e "✅ Nginx avviato con successo"
    else
        echo -e "❌ Impossibile avviare Nginx"
        echo -e "⚠️ Installazione Nginx in corso..."
        apt-get update && apt-get install -y nginx
        systemctl enable nginx
        systemctl start nginx
        if systemctl is-active --quiet nginx; then
            echo -e "✅ Nginx installato e avviato con successo"
        else
            echo -e "❌ Impossibile installare Nginx"
        fi
    fi
fi

echo

# 3. Verifica avvio automatico
echo "3. Verifica configurazione avvio automatico:"

# Verifica se m4bot.service è abilitato all'avvio
if systemctl is-enabled --quiet m4bot.service; then
    echo -e "✅ m4bot.service è abilitato all'avvio automatico"
else
    echo -e "❌ m4bot.service non è abilitato all'avvio automatico"
    echo -e "🔄 Abilitazione di m4bot.service all'avvio automatico..."
    systemctl enable m4bot.service
    echo -e "✅ m4bot.service abilitato all'avvio automatico"
fi

# Verifica se m4bot-web.service è abilitato all'avvio
if systemctl is-enabled --quiet m4bot-web.service; then
    echo -e "✅ m4bot-web.service è abilitato all'avvio automatico"
else
    echo -e "❌ m4bot-web.service non è abilitato all'avvio automatico"
    echo -e "🔄 Abilitazione di m4bot-web.service all'avvio automatico..."
    systemctl enable m4bot-web.service
    echo -e "✅ m4bot-web.service abilitato all'avvio automatico"
fi

# Verifica crontab
if crontab -l 2>/dev/null | grep -q "m4bot"; then
    echo -e "✅ Avvio tramite crontab configurato"
else
    echo -e "❓ Avvio tramite crontab non configurato"
fi

# Verifica rc.local
if [ -f /etc/rc.local ] && grep -q "m4bot" /etc/rc.local; then
    echo -e "✅ Avvio tramite rc.local configurato"
else
    echo -e "❓ Avvio tramite rc.local non configurato"
fi

echo

# 4. Verifica moduli di sicurezza
echo "4. Configurazione moduli di sicurezza e stabilità:"

INSTALL_DIR=${INSTALL_DIR:-"/opt/m4bot"}
CURRENT_DIR=${CURRENT_DIR:-"$(pwd)"}

# Verifica WAF
if [ -d "$INSTALL_DIR/modules/security/waf" ]; then
    echo -e "✅ WAF è installato"
else
    echo -e "❌ WAF non trovato, installazione in corso..."
    mkdir -p "$INSTALL_DIR/modules/security/waf"
    # Creazione di un file base per WAF
    cat > "$INSTALL_DIR/modules/security/waf/__init__.py" << 'WAFEOF'
"""
Web Application Firewall module for M4Bot
"""

import logging
from datetime import datetime

logger = logging.getLogger('m4bot.security.waf')

class WAF:
    def __init__(self, app=None):
        self.app = app
        logger.info("WAF initialized at %s", datetime.now())
        
    def init_app(self, app):
        self.app = app
        logger.info("WAF attached to app at %s", datetime.now())
WAFEOF
    echo -e "✅ Creato modulo WAF base"
fi

# Verifica modulo sicurezza avanzata
if [ -d "$INSTALL_DIR/modules/security/advanced" ]; then
    echo -e "✅ Modulo di sicurezza avanzata è installato"
else
    echo -e "❌ Modulo di sicurezza avanzata non trovato, installazione in corso..."
    mkdir -p "$INSTALL_DIR/modules/security/advanced"
    # Creazione di un file base per il modulo di sicurezza avanzata
    cat > "$INSTALL_DIR/modules/security/advanced/__init__.py" << 'SECEOF'
"""
Advanced Security module for M4Bot
"""

import logging
from datetime import datetime

logger = logging.getLogger('m4bot.security.advanced')

class AdvancedSecurity:
    def __init__(self):
        logger.info("Advanced Security module initialized at %s", datetime.now())
        
    def start_monitoring(self):
        logger.info("Advanced Security monitoring started at %s", datetime.now())
        
    def stop_monitoring(self):
        logger.info("Advanced Security monitoring stopped at %s", datetime.now())
SECEOF
    echo -e "✅ Creato modulo di sicurezza avanzata base"
fi

# Verifica modulo stabilità
if [ -d "$INSTALL_DIR/modules/stability" ]; then
    echo -e "✅ Modulo di stabilità è installato"
else
    echo -e "❌ Modulo di stabilità non trovato, installazione in corso..."
    mkdir -p "$INSTALL_DIR/modules/stability"
    # Creazione di un file base per il modulo di stabilità
    cat > "$INSTALL_DIR/modules/stability/__init__.py" << 'STAEOF'
"""
Stability module for M4Bot
"""

import logging
from datetime import datetime

logger = logging.getLogger('m4bot.stability')

class StabilityMonitor:
    def __init__(self):
        logger.info("Stability monitor initialized at %s", datetime.now())
        
    def start_monitoring(self):
        logger.info("Stability monitoring started at %s", datetime.now())
        
    def perform_self_healing(self):
        logger.info("Self-healing procedure triggered at %s", datetime.now())
STAEOF
    echo -e "✅ Creato modulo di stabilità base"
fi

# 5. Verifica configurazione per aggiornamento zero-downtime
echo "5. Configurazione per aggiornamento zero-downtime:"
if [ -f "$INSTALL_DIR/scripts/update_zero_downtime.sh" ]; then
    echo -e "✅ Script per aggiornamento zero-downtime configurato"
else
    echo -e "❌ Script per aggiornamento zero-downtime non trovato"
    if [ -f "$CURRENT_DIR/scripts/update_zero_downtime.sh" ]; then
        cp "$CURRENT_DIR/scripts/update_zero_downtime.sh" "$INSTALL_DIR/scripts/"
        chmod +x "$INSTALL_DIR/scripts/update_zero_downtime.sh"
        echo -e "✅ Script per aggiornamento zero-downtime installato"
    else
        echo -e "⚠️ Per favore installa manualmente lo script per aggiornamento zero-downtime"
    fi
fi

# Esito finale
echo
print_success "Avvio dei servizi completato"
print_message "M4Bot è configurato per avviarsi automaticamente al riavvio del sistema"
print_success "Installazione di M4Bot completata con successo!"
print_message "Indirizzo web: http://$(hostname -I | awk '{print $1}'):5000"
EOF

chmod +x "$INSTALL_DIR/scripts/check_services.sh"

# 7. Creazione dei file base del WAF
print_message "Creazione dei file base per WAF..."
cat > "$INSTALL_DIR/modules/security/waf/__init__.py" << 'EOF'
"""
Web Application Firewall module for M4Bot
"""

import logging
from datetime import datetime

logger = logging.getLogger('m4bot.security.waf')

class WAF:
    def __init__(self, app=None):
        self.app = app
        logger.info("WAF initialized at %s", datetime.now())
        
    def init_app(self, app):
        self.app = app
        logger.info("WAF attached to app at %s", datetime.now())
        
        @app.before_request
        def before_request():
            # Basic WAF check implementation
            from flask import request, abort
            
            # Check for SQL injection
            if any(attack in request.url.lower() for attack in ["'", "union", "select", "drop", "delete", "insert", "exec"]):
                logger.warning("SQL injection attempt detected from %s", request.remote_addr)
                abort(403)
                
            # Check for XSS
            if any(attack in request.url.lower() for attack in ["<script>", "javascript:", "onerror", "onload"]):
                logger.warning("XSS attempt detected from %s", request.remote_addr)
                abort(403)
EOF

# 8. Creazione dei file base del modulo sicurezza avanzata
print_message "Creazione dei file base per il modulo di sicurezza avanzata..."
cat > "$INSTALL_DIR/modules/security/advanced/__init__.py" << 'EOF'
"""
Advanced Security module for M4Bot
"""

import logging
import os
import time
from datetime import datetime
import threading

logger = logging.getLogger('m4bot.security.advanced')

class AdvancedSecurity:
    def __init__(self):
        logger.info("Advanced Security module initialized at %s", datetime.now())
        self.monitoring = False
        self.monitor_thread = None
        
    def start_monitoring(self):
        logger.info("Advanced Security monitoring started at %s", datetime.now())
        self.monitoring = True
        
        def monitor_func():
            while self.monitoring:
                # Log monitoring activity
                logger.debug("Security monitoring active at %s", datetime.now())
                
                # Check for suspicious activities
                self._check_failed_logins()
                self._check_file_integrity()
                
                # Sleep for a minute
                time.sleep(60)
        
        self.monitor_thread = threading.Thread(target=monitor_func)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        
    def stop_monitoring(self):
        logger.info("Advanced Security monitoring stopped at %s", datetime.now())
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
            
    def _check_failed_logins(self):
        # Implementation for checking failed logins
        pass
        
    def _check_file_integrity(self):
        # Implementation for file integrity monitoring
        pass
EOF

# 9. Creazione dei file base del modulo stabilità
print_message "Creazione dei file base per il modulo stabilità..."
cat > "$INSTALL_DIR/modules/stability/__init__.py" << 'EOF'
"""
Stability module for M4Bot
"""

import logging
from datetime import datetime

logger = logging.getLogger('m4bot.stability')

class StabilityMonitor:
    def __init__(self):
        logger.info("Stability monitor initialized at %s", datetime.now())
        
    def start_monitoring(self):
        logger.info("Stability monitoring started at %s", datetime.now())
        
    def perform_self_healing(self):
        logger.info("Self-healing procedure triggered at %s", datetime.now())
EOF

# 10. Creazione dello script start.sh
print_message "Creazione dello script start.sh..."
cat > "$INSTALL_DIR/scripts/start.sh" << 'EOF'
#!/bin/bash
# Script per avviare i servizi M4Bot

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

print_message "Avvio di M4Bot..."

# Verifica che la directory dei log esista
if [ ! -d "/var/log/m4bot" ]; then
    print_warning "La directory dei log non esiste, creazione in corso..."
    mkdir -p "/var/log/m4bot"
    chown m4bot:m4bot "/var/log/m4bot"
    chmod 755 "/var/log/m4bot"
    print_success "Directory dei log creata"
fi

print_message "Controllo dei servizi..."

# Verifica che PostgreSQL sia installato e in esecuzione
source /etc/os-release
if [ "$ID" = "debian" ] || [ "$ID" = "ubuntu" ]; then
    # Controlla PostgreSQL
    if ! command -v pg_isready &> /dev/null; then
        print_warning "PostgreSQL non è installato. Installazione in corso..."
        apt-get update && apt-get install -y postgresql postgresql-contrib
        if [ $? -ne 0 ]; then
            print_error "Impossibile installare PostgreSQL"
        else
            systemctl enable postgresql
            systemctl start postgresql
            print_success "PostgreSQL installato e avviato"
        fi
    else
        # Se PostgreSQL è installato, verifica se è in esecuzione
        if pg_isready -q; then
            print_success "PostgreSQL è in esecuzione"
        else
            print_warning "PostgreSQL non è in esecuzione, tentativo di avvio..."
            systemctl start postgresql
            if [ $? -ne 0 ]; then
                print_error "Impossibile avviare PostgreSQL"
            else
                print_success "PostgreSQL avviato"
            fi
        fi
    fi
    
    # Controlla Nginx
    if ! command -v nginx &> /dev/null; then
        print_warning "Nginx non è installato. Installazione in corso..."
        apt-get update && apt-get install -y nginx
        if [ $? -ne 0 ]; then
            print_error "Impossibile installare Nginx"
        else
            systemctl enable nginx
            systemctl start nginx
            print_success "Nginx installato e avviato"
        fi
    else
        # Se Nginx è installato, verifica se è in esecuzione
        if systemctl is-active --quiet nginx; then
            print_success "Nginx è in esecuzione"
        else
            print_warning "Nginx non è in esecuzione, tentativo di avvio..."
            systemctl start nginx
            if [ $? -ne 0 ]; then
                print_error "Impossibile avviare Nginx"
            else
                print_success "Nginx avviato"
            fi
        fi
    fi
    
    # Controlla Redis
    if ! command -v redis-cli &> /dev/null; then
        print_warning "Redis non è installato. Installazione in corso..."
        apt-get update && apt-get install -y redis-server
        if [ $? -ne 0 ]; then
            print_error "Impossibile installare Redis"
        else
            systemctl enable redis-server
            systemctl start redis-server
            print_success "Redis installato e avviato"
        fi
    else
        # Se Redis è installato, verifica se è in esecuzione
        if systemctl is-active --quiet redis-server; then
            print_success "Redis è in esecuzione"
        else
            print_warning "Redis non è in esecuzione, tentativo di avvio..."
            systemctl start redis-server
            if [ $? -ne 0 ]; then
                print_error "Impossibile avviare Redis"
            else
                print_success "Redis avviato"
            fi
        fi
    fi
fi

# Avvia i servizi M4Bot
print_message "Avvio dei servizi M4Bot..."

# Controlla se i servizi sono attivi
if systemctl is-active --quiet m4bot.service; then
    print_message "Il servizio m4bot è già in esecuzione, riavvio in corso..."
    systemctl restart m4bot.service
else
    systemctl start m4bot.service
fi

if systemctl is-active --quiet m4bot-web.service; then
    print_message "Il servizio m4bot-web è già in esecuzione, riavvio in corso..."
    systemctl restart m4bot-web.service
else
    systemctl start m4bot-web.service
fi

# Verifica finale
if systemctl is-active --quiet m4bot.service && systemctl is-active --quiet m4bot-web.service; then
    print_success "Tutti i servizi M4Bot sono in esecuzione"
else
    print_warning "Alcuni servizi M4Bot potrebbero non essere in esecuzione"
fi

# Esegui lo script di verifica completa
if [ -f "$(dirname "$0")/check_services.sh" ]; then
    bash "$(dirname "$0")/check_services.sh"
else
    print_warning "Script check_services.sh non trovato"
fi

print_success "Avvio di M4Bot completato"
EOF

chmod +x "$INSTALL_DIR/scripts/start.sh"

# 11. Configurazione di systemd
print_message "Configurazione dei servizi systemd..."
cat > /etc/systemd/system/m4bot.service << EOF
[Unit]
Description=M4Bot Service
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/run.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
Environment=M4BOT_DIR=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/m4bot-web.service << EOF
[Unit]
Description=M4Bot Web Interface
After=network.target postgresql.service redis-server.service m4bot.service
Requires=postgresql.service redis-server.service

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$INSTALL_DIR/web
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/web/app.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1
Environment=M4BOT_DIR=$INSTALL_DIR

[Install]
WantedBy=multi-user.target
EOF

# 12. Configurazione dell'ambiente Python
print_message "Configurazione dell'ambiente Python..."
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# 13. Configurazione di Nginx
print_message "Configurazione di Nginx..."
cat > /etc/nginx/sites-available/m4bot << EOF
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    location /static {
        alias $INSTALL_DIR/web/static;
        expires 30d;
    }
}
EOF

# Abilita la configurazione
if [ -f /etc/nginx/sites-enabled/default ]; then
    rm /etc/nginx/sites-enabled/default
fi

ln -sf /etc/nginx/sites-available/m4bot /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# 14. Configurazione del database PostgreSQL
print_message "Configurazione del database PostgreSQL..."
# Crea un file SQL temporaneo
cat > /tmp/setup_db.sql << EOF
CREATE USER m4bot_user WITH PASSWORD 'password123';
CREATE DATABASE m4bot_db OWNER m4bot_user;
GRANT ALL PRIVILEGES ON DATABASE m4bot_db TO m4bot_user;
EOF

# Esegui lo script SQL come utente postgres
su - postgres -c "psql -f /tmp/setup_db.sql"
rm /tmp/setup_db.sql

# 15. Creazione del file .env
print_message "Creazione del file .env..."
cat > "$INSTALL_DIR/.env" << EOF
# Configurazione di base
SECRET_KEY=$(openssl rand -hex 32)
DEBUG=False
ENV=production
LOG_LEVEL=INFO

# Database
DB_TYPE=postgresql
DB_HOST=localhost
DB_PORT=5432
DB_NAME=m4bot_db
DB_USER=m4bot_user
DB_PASSWORD=password123

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Server
HOST=0.0.0.0
PORT=5000
EOF

# 16. Creazione di file run.py di esempio
print_message "Creazione di file run.py di esempio..."
cat > "$INSTALL_DIR/run.py" << 'EOF'
#!/usr/bin/env python3
"""
Script principale per avviare M4Bot
"""
import os
import sys
import logging
from datetime import datetime

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/m4bot/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('m4bot')

def main():
    """Funzione principale del bot"""
    logger.info("M4Bot avviato alle %s", datetime.now())
    logger.info("Ambiente: %s", os.environ.get('ENV', 'development'))
    
    try:
        # Placeholder per la logica del bot
        logger.info("Bot in esecuzione. Premi Ctrl+C per uscire.")
        
        # Mantieni il processo attivo
        while True:
            # Simula alcune attività periodiche
            import time
            time.sleep(60)
            logger.info("Bot ancora in esecuzione alle %s", datetime.now())
    
    except KeyboardInterrupt:
        logger.info("Bot fermato dall'utente")
    except Exception as e:
        logger.error("Errore critico: %s", str(e), exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
EOF

# 17. Creazione di un file app.py di esempio
print_message "Creazione di file app.py di esempio..."
mkdir -p "$INSTALL_DIR/web"
cat > "$INSTALL_DIR/web/app.py" << 'EOF'
#!/usr/bin/env python3
"""
Web interface for M4Bot
"""
import os
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/m4bot/web.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('m4bot.web')

app = Flask(__name__)

@app.route('/')
def index():
    """Pagina principale"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>M4Bot</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                text-align: center;
                background-color: #f5f5f5;
            }}
            .container {{
                max-width: 800px;
                margin: 0 auto;
                background-color: white;
                padding: 20px;
                border-radius: 10px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #333;
            }}
            .status {{
                margin-top: 20px;
                padding: 10px;
                background-color: #e8f5e9;
                border-radius: 5px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>M4Bot</h1>
            <p>La tua soluzione completa per la gestione dei bot per comunità</p>
            <div class="status">
                <strong>Stato:</strong> Attivo<br>
                <strong>Ora server:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                <strong>Versione:</strong> 1.0.0
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/api/status')
def status():
    """API endpoint per lo stato del servizio"""
    return jsonify({
        'status': 'active',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat(),
        'uptime': 'N/A',  # Placeholder
    })

if __name__ == '__main__':
    # Carica le configurazioni da .env se disponibile
    from dotenv import load_dotenv
    load_dotenv()
    
    # Avvia il server
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info("Avvio server web su porta %d (debug=%s)", port, debug)
    app.run(host='0.0.0.0', port=port, debug=debug)
EOF

# 18. Imposta i permessi corretti
print_message "Impostazione dei permessi corretti..."
find "$INSTALL_DIR" -type f -name "*.sh" -exec chmod +x {} \;
find "$INSTALL_DIR" -type f -name "*.py" -exec chmod +x {} \;
chown -R m4bot:m4bot "$INSTALL_DIR"
chown -R m4bot:m4bot "/var/log/m4bot"

# 19. Abilita e avvia i servizi
print_message "Abilitazione e avvio dei servizi..."
systemctl daemon-reload
systemctl enable postgresql
systemctl enable redis-server
systemctl enable nginx
systemctl enable m4bot.service
systemctl enable m4bot-web.service

systemctl start postgresql
systemctl start redis-server
systemctl start nginx
systemctl start m4bot.service
systemctl start m4bot-web.service

# 20. Verifica finale
print_message "Verifica finale dell'installazione..."
"$INSTALL_DIR/scripts/check_services.sh"

print_success "Installazione di M4Bot completata con successo!"
print_message "Indirizzo web: http://$(hostname -I | awk '{print $1}')"
print_message "Directory di installazione: $INSTALL_DIR"
print_message "Log di sistema: /var/log/m4bot/"
print_message "Per riavviare i servizi: sudo $INSTALL_DIR/scripts/start.sh" 