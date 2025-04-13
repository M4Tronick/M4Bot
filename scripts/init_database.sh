#!/bin/bash
# Script per inizializzare la struttura del database M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

print_message "Inizializzazione della struttura del database M4Bot..."

# Parametri del database
DB_NAME=${1:-"m4bot_db"}
DB_USER=${2:-"m4bot_user"}
DB_PASSWORD=${3:-"m4bot_password"}

# Verifica la connessione al database
print_message "Verifica della connessione al database..."
su - postgres -c "psql -d $DB_NAME -c 'SELECT 1;'" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    print_error "Impossibile connettersi al database $DB_NAME" 0
    print_message "Assicurati che il database sia stato creato con setup_postgres.sh"
    exit 1
fi

# Creazione delle tabelle principali
print_message "Creazione delle tabelle principali..."
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

-- Tabella comandi
CREATE TABLE IF NOT EXISTS commands (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    name VARCHAR(255) NOT NULL,
    response TEXT,
    cooldown INTEGER DEFAULT 0,
    user_level VARCHAR(50) DEFAULT 'everyone',
    enabled BOOLEAN DEFAULT TRUE,
    is_advanced BOOLEAN DEFAULT FALSE,
    custom_code TEXT,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (channel_id, name)
);

-- Tabella messaggi chat
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    user_id VARCHAR(255),
    username VARCHAR(255),
    content TEXT,
    is_command BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabella punti canale
CREATE TABLE IF NOT EXISTS channel_points (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    user_id VARCHAR(255),
    points INTEGER DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE (channel_id, user_id)
);

-- Tabella impostazioni canale
CREATE TABLE IF NOT EXISTS channel_settings (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id) UNIQUE,
    welcome_message TEXT,
    prefix VARCHAR(10) DEFAULT '!',
    chat_rules TEXT,
    auto_mod_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Tabella predizioni
CREATE TABLE IF NOT EXISTS predictions (
    id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(id),
    title VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'active',
    options JSONB NOT NULL,
    winner_option INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ends_at TIMESTAMP WITH TIME ZONE
);

-- Tabella sessioni
CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(255) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    data JSONB,
    expires_at TIMESTAMP WITH TIME ZONE
);

-- Indici
CREATE INDEX IF NOT EXISTS idx_chat_messages_channel_id ON chat_messages(channel_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_timestamp ON chat_messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_commands_channel_id ON commands(channel_id);
CREATE INDEX IF NOT EXISTS idx_channel_points_channel_id ON channel_points(channel_id);
EOF

# Applica lo script SQL
su - postgres -c "psql -d $DB_NAME -f /tmp/init_m4bot_tables.sql"
if [ $? -ne 0 ]; then
    print_error "Errore nella creazione delle tabelle" 1
fi

# Pulizia
rm -f /tmp/init_m4bot_tables.sql

# Crea un utente amministratore iniziale
print_message "Creazione dell'utente amministratore..."
read -p "Nome utente admin (default: admin): " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-"admin"}

read -p "Email admin (default: admin@m4bot.it): " ADMIN_EMAIL
ADMIN_EMAIL=${ADMIN_EMAIL:-"admin@m4bot.it"}

read -s -p "Password admin (default: admin123): " ADMIN_PASSWORD
echo ""
ADMIN_PASSWORD=${ADMIN_PASSWORD:-"admin123"}

# Genera hash della password (usando Python perché è più facile)
PASS_HASH=$(python3 -c "import bcrypt; print(bcrypt.hashpw('$ADMIN_PASSWORD'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'))")

# Inserisci l'utente admin
su - postgres -c "psql -d $DB_NAME -c \"INSERT INTO users (username, email, password_hash, is_admin) VALUES ('$ADMIN_USER', '$ADMIN_EMAIL', '$PASS_HASH', TRUE) ON CONFLICT (username) DO NOTHING;\""

print_success "Database inizializzato con successo!"
print_message "Utente admin: $ADMIN_USER"
print_message "Email admin: $ADMIN_EMAIL" 