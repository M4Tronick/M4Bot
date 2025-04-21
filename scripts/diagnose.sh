#!/bin/bash
# Script di diagnosi per M4Bot
# Esegue controlli sul sistema e verifica che tutti i componenti funzionino correttamente

# Variabili di configurazione
M4BOT_DIR="/opt/m4bot"
WEB_DIR="$M4BOT_DIR/web"
BOT_DIR="$M4BOT_DIR/bot"
DB_NAME="m4bot_db"
DB_USER="m4bot_user"

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
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[AVVISO]${NC} $1"
}

# Banner di avvio
echo "================================================="
echo "      M4BOT - DIAGNOSTICA DI SISTEMA"
echo "================================================="
echo ""

# Controllo 1: Verifica directory di installazione
print_message "1. Verifica directory di installazione..."
if [ -d "$M4BOT_DIR" ]; then
    print_success "Directory di installazione $M4BOT_DIR esiste"
    # Verifica i file principali
    if [ -d "$BOT_DIR" ]; then
        print_success "Directory bot $BOT_DIR esiste"
    else
        print_error "Directory bot $BOT_DIR NON esiste"
    fi

    if [ -d "$WEB_DIR" ]; then
        print_success "Directory web $WEB_DIR esiste"
    else
        print_error "Directory web $WEB_DIR NON esiste"
    fi

    if [ -f "$BOT_DIR/m4bot.py" ]; then
        print_success "File principale del bot esiste"
    else
        print_error "File m4bot.py NON esiste"
    fi

    if [ -f "$WEB_DIR/app.py" ]; then
        print_success "File principale web esiste"
    else
        print_error "File app.py NON esiste"
    fi
else
    print_error "Directory di installazione $M4BOT_DIR NON esiste"
fi

# Controllo 2: Verifica stato servizi systemd
print_message "2. Verifica dei servizi systemd..."
if systemctl is-active --quiet m4bot-bot.service; then
    print_success "Servizio m4bot-bot.service è attivo"
else
    print_error "Servizio m4bot-bot.service NON è attivo"
fi

if systemctl is-active --quiet m4bot-web.service; then
    print_success "Servizio m4bot-web.service è attivo"
else
    print_error "Servizio m4bot-web.service NON è attivo"
fi

# Controllo 3: Verifica stato servizi dependencies
print_message "3. Verifica dei servizi di supporto..."
if systemctl is-active --quiet postgresql; then
    print_success "PostgreSQL è in esecuzione"
else
    print_error "PostgreSQL NON è in esecuzione"
fi

if systemctl is-active --quiet nginx; then
    print_success "Nginx è in esecuzione"
else
    print_error "Nginx NON è in esecuzione"
fi

# Controllo 4: Verifica ambiente virtuale Python
print_message "4. Verifica dell'ambiente virtuale Python..."
if [ -d "$M4BOT_DIR/venv" ]; then
    print_success "Ambiente virtuale esiste"
    # Verifica principali dipendenze
    if [ -f "$M4BOT_DIR/venv/bin/python" ]; then
        "$M4BOT_DIR/venv/bin/python" --version
    else
        print_error "Python non trovato nell'ambiente virtuale"
    fi
else
    print_error "Ambiente virtuale NON esiste"
fi

# Controllo 5: Verifica del database
print_message "5. Verifica del database PostgreSQL..."
# Verifica che PostgreSQL sia in esecuzione
if systemctl is-active --quiet postgresql; then
    print_success "PostgreSQL è in esecuzione"
    
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
    print_error "PostgreSQL NON è in esecuzione"
fi

# Controllo 6: Verifica di Nginx
print_message "6. Verifica di Nginx..."
# Verifica che Nginx sia in esecuzione
if systemctl is-active --quiet nginx; then
    print_success "Nginx è in esecuzione"
    # Verifica la configurazione
    nginx -t
    # Verifica i siti attivi
    echo "Siti abilitati:"
    ls -la /etc/nginx/sites-enabled/
else
    print_error "Nginx NON è in esecuzione"
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
    print_success "La porta 5000 è in ascolto"
else
    print_error "La porta 5000 NON è in ascolto"
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
    print_success "Script common.sh trovato in /usr/local/bin/"
else
    print_error "Script common.sh NON trovato in /usr/local/bin/"
fi

if [ -f "/usr/local/bin/m4bot-start" ]; then
    print_success "Script wrapper m4bot-start trovato"
else
    print_error "Script wrapper m4bot-start NON trovato"
fi

# Controllo 11: Verifica della connettività di rete
print_message "11. Verifica della connettività di rete..."
if ping -c 1 google.com &> /dev/null; then
    print_success "Connettività Internet disponibile"
else
    print_error "Connettività Internet NON disponibile"
fi

# Controllo 12: Verifica dello spazio su disco
print_message "12. Verifica dello spazio su disco..."
df -h /
FREE_SPACE=$(df -k / | awk 'NR==2 {print $4}')
if [ "$FREE_SPACE" -lt 1048576 ]; then  # Meno di 1GB
    print_warning "Spazio su disco inferiore a 1GB!"
else
    print_success "Spazio su disco sufficiente"
fi

# Controllo 13: Verifica delle risorse di sistema
print_message "13. Verifica delle risorse di sistema..."
echo "Utilizzo CPU:"
top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}'
echo "Memoria disponibile:"
free -h

# Controllo 14: Verifica delle configurazioni SSL
print_message "14. Verifica delle configurazioni SSL..."
if [ -d "/etc/letsencrypt/live" ]; then
    print_success "Directory Let's Encrypt trovata"
    ls -la /etc/letsencrypt/live
else
    print_warning "Directory Let's Encrypt NON trovata"
fi

# Controllo 15: Verifica della versione di sistema operativo
print_message "15. Verifica della versione di sistema operativo..."
. /etc/os-release
echo "Sistema operativo: $PRETTY_NAME"

# Controllo 16: Verifica degli aggiornamenti disponibili
print_message "16. Verifica degli aggiornamenti disponibili..."
apt update -qq
UPDATES=$(apt list --upgradable 2>/dev/null | grep -c "upgradable")
echo "Aggiornamenti disponibili: $UPDATES"

# Riepilogo finale
echo ""
echo "================================================="
echo "      DIAGNOSTICA COMPLETATA"
echo "================================================="
echo ""
print_message "Se sono stati rilevati errori, prova ad eseguire lo script fix_common_issues.sh per risolverli automaticamente."
print_message "Per assistenza manuale, visita: https://m4bot.it/docs/troubleshooting" 