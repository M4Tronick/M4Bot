#!/bin/bash
# Script di diagnostica per M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica privilegi root
check_root

print_message "=== DIAGNOSI M4BOT ==="
print_message "Analisi completa dei problemi..."

# Configurazione
M4BOT_DIR="/opt/m4bot"
WEB_DIR="$M4BOT_DIR/web"
BOT_DIR="$M4BOT_DIR/bot"
LOGS_DIR="$BOT_DIR/logs"
DB_NAME="m4bot_db"
DB_USER="m4bot_user"

# Controllo 1: Verifica che le directory esistano
print_message "1. Verifica delle directory..."
for dir in "$M4BOT_DIR" "$WEB_DIR" "$BOT_DIR" "$LOGS_DIR"; do
    if [ -d "$dir" ]; then
        print_success "Directory $dir esiste"
    else
        print_error "Directory $dir NON esiste"
        mkdir -p "$dir"
        print_warning "Directory $dir creata"
    fi
done

# Controllo 2: Verifica che i file principali esistano
print_message "2. Verifica dei file principali..."
if [ -f "$WEB_DIR/app.py" ]; then
    print_success "File app.py esiste"
    echo "Contenuto app.py (prime 10 righe):"
    head -n 10 "$WEB_DIR/app.py"
else
    print_error "File app.py NON esiste nel percorso $WEB_DIR"
fi

if [ -f "$BOT_DIR/m4bot.py" ]; then
    print_success "File m4bot.py esiste"
    echo "Contenuto m4bot.py (prime 10 righe):"
    head -n 10 "$BOT_DIR/m4bot.py"
else
    print_error "File m4bot.py NON esiste nel percorso $BOT_DIR"
fi

# Controllo 3: Verifica dei servizi systemd
print_message "3. Verifica dei servizi systemd..."
for service in "m4bot-bot.service" "m4bot-web.service"; do
    if systemctl list-unit-files | grep -q "$service"; then
        print_success "Servizio $service esiste"
        systemctl status "$service" --no-pager
    else
        print_error "Servizio $service NON esiste"
    fi
done

# Controllo 4: Verifica dell'ambiente virtuale Python
print_message "4. Verifica dell'ambiente virtuale..."
if [ -d "$M4BOT_DIR/venv" ]; then
    print_success "Ambiente virtuale esiste"
    "$M4BOT_DIR/venv/bin/pip" list | grep -E 'flask|psycopg2|requests'
else
    print_error "Ambiente virtuale NON esiste"
fi

# Controllo 5: Verifica del database
print_message "5. Verifica del database PostgreSQL..."
# Verifica che PostgreSQL sia in esecuzione
if systemctl is-active --quiet postgresql; then
    print_success "PostgreSQL Ã¨ in esecuzione"
    
    # Verifica che il database esista
    if sudo -u postgres psql -lqt | grep -q "$DB_NAME"; then
        print_success "Database $DB_NAME esiste"
        # Verifica le tabelle nel database
        echo "Tabelle nel database:"
        sudo -u postgres psql -d "$DB_NAME" -c "\dt"
    else
        print_error "Database $DB_NAME NON esiste"
    fi
else
    print_error "PostgreSQL NON Ã¨ in esecuzione"
fi

# Controllo 6: Verifica di Nginx
print_message "6. Verifica di Nginx..."
# Verifica che Nginx sia in esecuzione
if systemctl is-active --quiet nginx; then
    print_success "Nginx Ã¨ in esecuzione"
    # Verifica la configurazione
    nginx -t
    # Verifica i siti attivi
    echo "Siti abilitati:"
    ls -la /etc/nginx/sites-enabled/
else
    print_error "Nginx NON Ã¨ in esecuzione"
fi

# Controllo 7: Verifica dei log
print_message "7. Verifica dei log..."
# Visualizza gli ultimi errori nei log di sistema
echo "Ultimi errori dei servizi m4bot:"
journalctl -u m4bot-bot.service -u m4bot-web.service --since "1 hour ago" | grep -i "error\|critical\|exception"

# Controllo 8: Verifica delle porte
print_message "8. Verifica delle porte..."
# Verifica che la porta 5000 sia in ascolto
if netstat -tuln | grep -q ":5000 "; then
    print_success "La porta 5000 Ã¨ in ascolto"
else
    print_error "La porta 5000 NON Ã¨ in ascolto"
    echo "Porte in ascolto:"
    netstat -tuln | grep "LISTEN"
fi

# Controllo 9: Verifica dei permessi
print_message "9. Verifica dei permessi..."
echo "Permessi directory M4Bot:"
ls -la "$M4BOT_DIR"
echo "Permessi directory web:"
ls -la "$WEB_DIR"
echo "Permessi directory bot:"
ls -la "$BOT_DIR"

# Controllo 10: Verifica dello script common.sh
print_message "10. Verifica degli script wrapper..."
if [ -f "/usr/local/bin/common.sh" ]; then
    print_success "File common.sh esiste in /usr/local/bin/"
else
    print_error "File common.sh NON esiste in /usr/local/bin/"
    if [ -f "$(dirname "$0")/common.sh" ]; then
        cp "$(dirname "$0")/common.sh" /usr/local/bin/
        chmod +x /usr/local/bin/common.sh
        print_warning "File common.sh copiato in /usr/local/bin/"
    fi
fi

# Suggerimenti finali
print_message "=== SUGGERIMENTI ==="
print_message "Se ci sono errori relativi ai file mancanti, verifica che il repository sia stato clonato correttamente"
print_message "Se ci sono errori relativi ai servizi, puoi riavviarli con: sudo systemctl restart m4bot-bot.service m4bot-web.service"
print_message "Se ci sono errori relativi al database, verifica le credenziali in $M4BOT_DIR/.env"
print_message "Se ci sono errori relativi a Nginx, verifica la configurazione in /etc/nginx/sites-available/m4bot"

print_message "=== AZIONI CORRETTIVE ==="
read -p "Vuoi tentare di risolvere automaticamente i problemi riscontrati? (s/n): " fix_issues
if [[ "$fix_issues" == "s" || "$fix_issues" == "S" ]]; then
    print_message "Tentativo di risoluzione dei problemi..."
    
    # Ricreazione delle directory di log mancanti
    mkdir -p "$LOGS_DIR"
    chown -R m4bot:m4bot "$LOGS_DIR"
    chmod -R 755 "$LOGS_DIR"
    
    # Riavvio dei servizi
    systemctl restart postgresql
    systemctl restart nginx
    systemctl restart m4bot-bot.service
    systemctl restart m4bot-web.service
    
    # Verifica dello stato finale
    print_message "Stato finale dei servizi:"
    systemctl status m4bot-bot.service --no-pager
    systemctl status m4bot-web.service --no-pager
fi 