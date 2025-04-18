#!/bin/bash
# Script per ottimizzare il database PostgreSQL di M4Bot
# Consigliato: eseguire settimanalmente
# crontab -e
# 0 3 * * 0 /opt/m4bot/scripts/optimize_db.sh

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

print_message "Avvio ottimizzazione del database PostgreSQL..."

# Verifica se PostgreSQL Ã¨ in esecuzione
if ! systemctl is-active --quiet postgresql; then
    print_error "PostgreSQL non Ã¨ in esecuzione" 1
fi

# Esegue un backup prima dell'ottimizzazione
print_message "Creazione backup di sicurezza..."
BACKUP_DIR="/opt/m4bot/backups"
BACKUP_FILE="$BACKUP_DIR/pre_optimize_$(date +%Y%m%d_%H%M%S).sql"
mkdir -p "$BACKUP_DIR"

sudo -u postgres pg_dump m4bot_db > "$BACKUP_FILE" || print_error "Impossibile creare backup" 1
print_success "Backup creato in $BACKUP_FILE"

# Ottimizzazione delle tabelle (VACUUM)
print_message "Esecuzione VACUUM ANALYZE..."
sudo -u postgres psql -d m4bot_db -c "VACUUM ANALYZE;" || print_warning "Problema durante VACUUM ANALYZE"

# Ricostruzione degli indici
print_message "Ricostruzione degli indici..."
sudo -u postgres psql -d m4bot_db -c "
REINDEX DATABASE m4bot_db;
" || print_warning "Problema durante la ricostruzione degli indici"

# Rimozione dati vecchi e inutilizzati
print_message "Pulizia dei dati vecchi..."

# Mantieni solo gli ultimi 30 giorni di messaggi chat (se necessario)
sudo -u postgres psql -d m4bot_db -c "
DELETE FROM chat_messages WHERE created_at < NOW() - INTERVAL '30 days';
" || print_warning "Problema durante la pulizia dei messaggi vecchi"

print_message "Ottimizzazione delle statistiche del query planner..."
sudo -u postgres psql -d m4bot_db -c "ANALYZE;" || print_warning "Problema durante l'analisi delle statistiche"

# Verifica la dimensione del database
DB_SIZE=$(sudo -u postgres psql -d m4bot_db -c "SELECT pg_size_pretty(pg_database_size('m4bot_db'));" | sed -n 3p | tr -d ' ')
print_message "Dimensione attuale del database: $DB_SIZE"

# Verifica dimensione tabelle principali
print_message "Dimensione delle tabelle principali:"
sudo -u postgres psql -d m4bot_db -c "
SELECT 
    table_name, 
    pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) as size
FROM 
    information_schema.tables
WHERE 
    table_schema = 'public'
ORDER BY 
    pg_total_relation_size(quote_ident(table_name)) DESC
LIMIT 10;
" | sed -n '3,$p'

print_success "Ottimizzazione del database completata con successo!" 