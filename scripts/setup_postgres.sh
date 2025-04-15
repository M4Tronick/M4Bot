#!/bin/bash
# Script per configurare il database PostgreSQL per M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

print_message "Configurazione del database PostgreSQL..."

# Verifica che PostgreSQL sia in esecuzione
check_postgres

# Parametri del database
DB_NAME=${1:-"m4bot_db"}
DB_USER=${2:-"m4bot_user"}
DB_PASSWORD=${3:-"m4bot_password"}

# Creiamo l'utente e il database PostgreSQL
print_message "Creazione dell'utente database $DB_USER..."
su - postgres -c "psql -c \"CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';\""

print_message "Creazione del database $DB_NAME..."
su - postgres -c "psql -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER;\""

print_message "Configurazione dei privilegi..."
su - postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;\""

print_success "Database configurato con successo!"
print_message "Nome database: $DB_NAME"
print_message "Utente database: $DB_USER" 