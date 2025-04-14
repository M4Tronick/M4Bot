#!/bin/bash
# Script di backup automatico per M4Bot
# Consigliato: aggiungere a crontab per esecuzione giornaliera
# crontab -e
# 0 2 * * * /opt/m4bot/scripts/backup.sh

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

# Imposta data per il nome del file
DATE=$(date +"%Y-%m-%d")
BACKUP_DIR="/opt/m4bot/backups"
DB_BACKUP="$BACKUP_DIR/db_backup_$DATE.sql"
CONFIG_BACKUP="$BACKUP_DIR/config_backup_$DATE.tar.gz"

# Crea directory backup se non esiste
mkdir -p $BACKUP_DIR

print_message "Avvio backup di M4Bot..."

# Backup del database
print_message "Backup del database PostgreSQL..."
sudo -u postgres pg_dump m4bot_db > $DB_BACKUP
if [ $? -eq 0 ]; then
    print_success "Backup del database completato: $DB_BACKUP"
else
    print_error "Errore durante il backup del database" 1
fi

# Backup dei file di configurazione
print_message "Backup dei file di configurazione..."
tar -czf $CONFIG_BACKUP /opt/m4bot/.env /opt/m4bot/bot/config.py /etc/nginx/sites-available/m4bot
if [ $? -eq 0 ]; then
    print_success "Backup dei file di configurazione completato: $CONFIG_BACKUP"
else
    print_error "Errore durante il backup dei file di configurazione" 1
fi

# Elimina backup più vecchi di 7 giorni
print_message "Pulizia dei backup precedenti..."
find $BACKUP_DIR -name "db_backup_*.sql" -type f -mtime +7 -delete
find $BACKUP_DIR -name "config_backup_*.tar.gz" -type f -mtime +7 -delete

print_message "Backup completato con successo."
print_message "I file di backup sono disponibili in: $BACKUP_DIR" 