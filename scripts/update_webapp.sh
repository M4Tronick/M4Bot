#!/bin/bash
# Script per aggiornare l'applicazione web per supportare i sottodomini

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

# Verifica se l'app web esiste
WEB_DIR="/opt/m4bot/web"
APP_FILE="$WEB_DIR/app.py"
if [ ! -f "$APP_FILE" ]; then
    print_error "File app.py non trovato in $APP_FILE" 1
fi

print_message "====================================================="
print_message "AGGIORNAMENTO APP WEB PER SUPPORTARE I SOTTODOMINI"
print_message "====================================================="

# Crea backup del file app.py
cp "$APP_FILE" "${APP_FILE}.backup"
print_message "Backup creato: ${APP_FILE}.backup"

# Modifica il file app.py per supportare i sottodomini
print_message "Aggiornamento dell'applicazione web per gestire i sottodomini..."

# Aggiungi il codice per gestire i sottodomini dopo l'import di request
SUBDOMAIN_CODE=$(cat << 'EOF'

# Gestione dei sottodomini
def get_subdomain():
    """Ottiene il sottodominio dalla richiesta."""
    host = request.headers.get('Host', '')
    if not host or '.' not in host:
        return None
    
    parts = host.split('.')
    if len(parts) > 2:
        return parts[0]
    return None

@app.before_request
async def route_by_subdomain():
    """Gestisce il routing in base al sottodominio."""
    subdomain = get_subdomain()
    
    # Se non è un sottodominio, continua normalmente
    if not subdomain or subdomain == 'www':
        return None
        
    # Gestione sottodominio dashboard
    if subdomain == 'dashboard':
        if request.path == '/':
            return redirect(url_for('dashboard'))
        return None
        
    # Gestione sottodominio control
    if subdomain == 'control':
        if request.path == '/':
            return redirect(url_for('system_health'))
        return None
EOF
)

# Inserisci il codice per i sottodomini dopo l'import di request
# Cerca la riga dove viene importato request
REQUEST_LINE=$(grep -n "from quart import" "$APP_FILE" | head -1 | cut -d':' -f1)

if [ -n "$REQUEST_LINE" ]; then
    # Inserisci il codice dopo la riga di import
    sed -i "${REQUEST_LINE}r /dev/stdin" "$APP_FILE" <<< "$SUBDOMAIN_CODE"
    print_success "Codice per la gestione dei sottodomini aggiunto con successo"
else
    print_error "Impossibile trovare il punto di inserimento per il codice dei sottodomini" 1
fi

# Riavvio del servizio web
print_message "Riavvio del servizio web..."
if systemctl is-active --quiet m4bot-web.service; then
    systemctl restart m4bot-web.service
    if [ $? -eq 0 ]; then
        print_success "Servizio web riavviato con successo"
    else
        print_error "Impossibile riavviare il servizio web" 0
        print_message "Puoi riavviarlo manualmente con: sudo systemctl restart m4bot-web.service"
    fi
else
    print_warning "Servizio web non attivo, avvio del servizio..."
    systemctl start m4bot-web.service
    if [ $? -eq 0 ]; then
        print_success "Servizio web avviato con successo"
    else
        print_error "Impossibile avviare il servizio web" 0
        print_message "Puoi avviarlo manualmente con: sudo systemctl start m4bot-web.service"
    fi
fi

print_message "====================================================="
print_message "L'APPLICAZIONE WEB È STATA AGGIORNATA"
print_message "====================================================="
print_message "Ora i sottodomini saranno gestiti correttamente:"
print_message "- dashboard.dominio.it → accesso diretto alla dashboard"
print_message "- control.dominio.it → accesso diretto al pannello di controllo"
print_message "=====================================================" 