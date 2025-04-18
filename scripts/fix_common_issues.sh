#!/bin/bash
# Script per risolvere i problemi piÃ¹ comuni di M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica privilegi root
check_root

print_message "=== RIPARAZIONE M4BOT ==="
print_message "Questo script tenterÃ  di risolvere i problemi piÃ¹ comuni di M4Bot"

# Configurazione
M4BOT_DIR="/opt/m4bot"
WEB_DIR="$M4BOT_DIR/web"
BOT_DIR="$M4BOT_DIR/bot"
LOGS_DIR="$BOT_DIR/logs"
DB_NAME="m4bot_db"
DB_USER="m4bot_user"

# 1. Riparazione common.sh
print_message "1. Riparazione dello script common.sh..."
if [ ! -f "/usr/local/bin/common.sh" ] && [ -f "$(dirname "$0")/common.sh" ]; then
    cp "$(dirname "$0")/common.sh" /usr/local/bin/
    chmod +x /usr/local/bin/common.sh
    print_success "File common.sh copiato in /usr/local/bin/"
else
    print_message "File common.sh giÃ  presente"
fi

# 2. Riparazione directory dei log
print_message "2. Riparazione della directory dei log..."
mkdir -p "$LOGS_DIR"
chown -R m4bot:m4bot "$M4BOT_DIR" || true
chmod -R 755 "$LOGS_DIR"
print_success "Directory dei log creata e permessi impostati"

# 3. Riparazione servizi
print_message "3. Riparazione dei servizi..."
systemctl daemon-reload
systemctl restart postgresql nginx

# 4. Riparazione del database
print_message "4. Verifica del database..."
if ! sudo -u postgres psql -lqt | grep -q "$DB_NAME"; then
    print_warning "Database $DB_NAME non trovato, creazione in corso..."
    
    # Genera una password sicura
    DB_PASSWORD=$(openssl rand -hex 12)
    
    # Crea l'utente e il database
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';"
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
    
    # Salva le credenziali del database
    cat > "$M4BOT_DIR/.env" << EOF
DB_USER=$DB_USER
DB_PASSWORD=$DB_PASSWORD
DB_NAME=$DB_NAME
DB_HOST=localhost
EOF
    chmod 600 "$M4BOT_DIR/.env"
    chown m4bot:m4bot "$M4BOT_DIR/.env"
    
    print_success "Database creato con successo"
else
    print_message "Database $DB_NAME giÃ  esistente"
fi

# 5. Verifica dei file principali
print_message "5. Verifica dei file principali..."
if [ ! -f "$WEB_DIR/app.py" ] || [ ! -f "$BOT_DIR/m4bot.py" ]; then
    print_warning "File principali mancanti, tentativo di clonazione dal repository..."
    
    # Salva qualsiasi file esistente
    if [ -d "$M4BOT_DIR" ]; then
        BACKUP_DIR="/tmp/m4bot_backup_$(date +%s)"
        mkdir -p "$BACKUP_DIR"
        cp -r "$M4BOT_DIR" "$BACKUP_DIR"
        print_message "Backup creato in $BACKUP_DIR"
    fi
    
    # Clone del repository
    TEMP_DIR="/tmp/m4bot_repo"
    rm -rf "$TEMP_DIR"
    git clone https://github.com/M4Tronick/M4Bot.git "$TEMP_DIR"
    
    if [ -d "$TEMP_DIR" ]; then
        # Copia i file mancanti
        if [ ! -f "$WEB_DIR/app.py" ] && [ -f "$TEMP_DIR/web/app.py" ]; then
            mkdir -p "$WEB_DIR"
            cp -r "$TEMP_DIR/web/"* "$WEB_DIR/"
            print_success "File web copiati dal repository"
        fi
        
        if [ ! -f "$BOT_DIR/m4bot.py" ] && [ -f "$TEMP_DIR/bot/m4bot.py" ]; then
            mkdir -p "$BOT_DIR"
            cp -r "$TEMP_DIR/bot/"* "$BOT_DIR/"
            print_success "File bot copiati dal repository"
        fi
        
        # Pulisci
        rm -rf "$TEMP_DIR"
    else
        print_error "Impossibile clonare il repository"
    fi
fi

# 6. Riparazione porte
print_message "6. Verifica delle porte..."
if ! netstat -tuln | grep -q ":5000 "; then
    print_warning "La porta 5000 non Ã¨ in ascolto, tentativo di riavvio dei servizi..."
    
    # Verifica se l'app utilizza una porta diversa
    if [ -f "$WEB_DIR/app.py" ]; then
        PORT=$(grep -o "port=[0-9]*" "$WEB_DIR/app.py" | cut -d= -f2)
        if [ -n "$PORT" ] && [ "$PORT" != "5000" ]; then
            print_warning "L'applicazione web utilizza la porta $PORT invece di 5000"
            
            # Aggiorna la configurazione Nginx
            sed -i "s/proxy_pass http:\/\/localhost:5000;/proxy_pass http:\/\/localhost:$PORT;/" /etc/nginx/sites-available/m4bot
            systemctl reload nginx
            print_success "Configurazione Nginx aggiornata per utilizzare la porta $PORT"
        fi
    fi
    
    # Riavvia i servizi
    systemctl restart m4bot-web.service
fi

# 7. Riparazione Nginx
print_message "7. Riparazione di Nginx..."
nginx -t || {
    print_warning "Configurazione Nginx non valida, tentativo di riparazione..."
    
    # Ricrea la configurazione
    cat > /etc/nginx/sites-available/m4bot << EOF
server {
    listen 80;
    server_name _;  # Ascolta su tutti i domini

    location / {
        proxy_pass http://localhost:5000;
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
    
    # Verifica e ricarica
    nginx -t && systemctl reload nginx
    print_success "Configurazione Nginx ricreata"
}

# 8. Riparazione ambiente virtuale
print_message "8. Verifica dell'ambiente virtuale..."
if [ ! -d "$M4BOT_DIR/venv" ]; then
    print_warning "Ambiente virtuale mancante, creazione in corso..."
    python3 -m venv "$M4BOT_DIR/venv"
    
    # Installa le dipendenze base
    "$M4BOT_DIR/venv/bin/pip" install --upgrade pip
    "$M4BOT_DIR/venv/bin/pip" install flask flask-sqlalchemy flask-login psycopg2-binary python-dotenv requests asyncio aiohttp bcrypt
    
    # Installa le dipendenze specifiche
    if [ -f "$WEB_DIR/requirements.txt" ]; then
        "$M4BOT_DIR/venv/bin/pip" install -r "$WEB_DIR/requirements.txt"
    fi
    
    if [ -f "$BOT_DIR/requirements.txt" ]; then
        "$M4BOT_DIR/venv/bin/pip" install -r "$BOT_DIR/requirements.txt"
    fi
    
    print_success "Ambiente virtuale creato e dipendenze installate"
fi

# 9. Inizializzazione del database
print_message "9. Inizializzazione del database..."
if [ -f "$(dirname "$0")/init_database.sh" ]; then
    source "$(dirname "$0")/init_database.sh" "$DB_NAME" "$DB_USER" "$(grep DB_PASSWORD "$M4BOT_DIR/.env" | cut -d= -f2)"
else
    print_warning "File init_database.sh non trovato"
    
    # Crea tabelle base
    print_message "Creazione delle tabelle base..."
    cat > /tmp/init_m4bot_tables.sql << EOF
-- Tabella utenti
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabella canali
CREATE TABLE IF NOT EXISTS channels (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    owner_id INTEGER REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- Tabella sessioni
CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    data JSONB,
    expires_at TIMESTAMP WITH TIME ZONE
);
EOF
    
    sudo -u postgres psql -d "$DB_NAME" -f /tmp/init_m4bot_tables.sql
    rm -f /tmp/init_m4bot_tables.sql
    
    # Crea utente admin
    print_message "Creazione dell'utente admin..."
    ADMIN_USER="admin"
    ADMIN_EMAIL="admin@m4bot.it"
    ADMIN_PASSWORD="admin123"
    
    # Genera hash della password
    PASS_HASH=$(python3 -c "import bcrypt; print(bcrypt.hashpw('$ADMIN_PASSWORD'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'))")
    
    # Inserisci l'utente admin
    sudo -u postgres psql -d "$DB_NAME" -c "INSERT INTO users (username, email, password_hash, is_admin) VALUES ('$ADMIN_USER', '$ADMIN_EMAIL', '$PASS_HASH', TRUE) ON CONFLICT (username) DO NOTHING;"
    
    print_success "Database inizializzato con utente admin"
fi

# 10. Riavvia i servizi
print_message "10. Riavvio dei servizi..."
systemctl restart m4bot-bot.service
systemctl restart m4bot-web.service

# Verifica finale
print_message "=== STATO FINALE ==="
systemctl status postgresql --no-pager
systemctl status nginx --no-pager
systemctl status m4bot-bot.service --no-pager
systemctl status m4bot-web.service --no-pager

print_success "=== RIPARAZIONE COMPLETATA ==="
print_message "Se i problemi persistono, esegui il comando 'diagnose.sh' per un'analisi dettagliata"
print_message "Le credenziali di accesso sono:"
print_message "  Username: admin"
print_message "  Password: admin123" 