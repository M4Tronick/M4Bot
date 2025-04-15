#!/bin/bash
# Script unificato per configurare i sottodomini in M4Bot

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzioni di utilità
check_root() {
    if [ "$(id -u)" != "0" ]; then
        echo -e "${RED}Errore: Questo script deve essere eseguito come root${NC}"
        exit 1
    fi
}

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

# Verifica i prerequisiti
check_prerequisites() {
    print_message "Verificando i prerequisiti..."
    
    # Verifica se Nginx è installato
    if ! command -v nginx &> /dev/null; then
        print_error "Nginx non è installato" 1
    fi
    
    # Verifica se Certbot è installato
    if ! command -v certbot &> /dev/null; then
        print_error "Certbot non è installato" 1
    fi
    
    # Verifica se il file di configurazione di M4Bot esiste
    if [ ! -f "/etc/nginx/sites-available/m4bot" ]; then
        print_error "File di configurazione Nginx per M4Bot non trovato" 1
    fi
    
    # Verifica file .env
    if [ ! -f "/opt/m4bot/.env" ]; then
        print_error "File .env non trovato in /opt/m4bot/.env" 1
    fi
    
    # Verifica file app.py
    if [ ! -f "/opt/m4bot/web/app.py" ]; then
        print_error "File app.py non trovato in /opt/m4bot/web/app.py" 1
    fi
    
    print_success "Prerequisiti verificati"
}

# Funzione principale
main() {
    clear
    check_root
    check_prerequisites
    
    print_message "====================================================="
    print_message "CONFIGURAZIONE COMPLETA DEI SOTTODOMINI PER M4BOT"
    print_message "====================================================="
    
    # Raccolta delle informazioni
    read -p "Inserisci il dominio principale (es. m4bot.it): " MAIN_DOMAIN
    if [ -z "$MAIN_DOMAIN" ]; then
        print_error "Il dominio principale è obbligatorio" 1
    fi
    
    read -p "Inserisci un indirizzo email per Let's Encrypt (default: admin@$MAIN_DOMAIN): " EMAIL
    if [ -z "$EMAIL" ]; then
        EMAIL="admin@$MAIN_DOMAIN"
        print_warning "Nessun email inserito, utilizzo l'email predefinita: $EMAIL"
    fi
    
    # Prepara i sottodomini
    DASHBOARD_DOMAIN="dashboard.$MAIN_DOMAIN"
    CONTROL_DOMAIN="control.$MAIN_DOMAIN"
    
    print_message "====================================================="
    print_message "CONFIGURAZIONE PER:"
    print_message "Dominio principale: $MAIN_DOMAIN"
    print_message "Dashboard: $DASHBOARD_DOMAIN"
    print_message "Control Panel: $CONTROL_DOMAIN"
    print_message "Email: $EMAIL"
    print_message "====================================================="
    
    # Chiedi conferma
    read -p "Vuoi procedere con la configurazione? (s/n): " confirm
    if [[ $confirm != "s" && $confirm != "S" ]]; then
        print_message "Configurazione annullata."
        exit 0
    fi
    
    # FASE 1: Aggiorna la configurazione Nginx
    print_message "FASE 1: Aggiornamento della configurazione Nginx..."
    
    # Backup della configurazione Nginx originale
    cp /etc/nginx/sites-available/m4bot /etc/nginx/sites-available/m4bot.backup.$(date +%Y%m%d)
    print_message "Backup creato: /etc/nginx/sites-available/m4bot.backup.$(date +%Y%m%d)"
    
    # Modifica configurazione Nginx per includere i sottodomini
    sed -i "s/server_name $MAIN_DOMAIN www.$MAIN_DOMAIN;/server_name $MAIN_DOMAIN www.$MAIN_DOMAIN $DASHBOARD_DOMAIN $CONTROL_DOMAIN;/" /etc/nginx/sites-available/m4bot
    
    # Testa la configurazione Nginx
    nginx -t
    if [ $? -ne 0 ]; then
        print_error "Configurazione Nginx non valida, ripristino dal backup" 0
        cp /etc/nginx/sites-available/m4bot.backup.$(date +%Y%m%d) /etc/nginx/sites-available/m4bot
        nginx -t || print_error "Impossibile ripristinare la configurazione" 1
        exit 1
    fi
    
    # Riavvia Nginx
    systemctl restart nginx
    if [ $? -ne 0 ]; then
        print_error "Impossibile riavviare Nginx, ripristino dal backup" 0
        cp /etc/nginx/sites-available/m4bot.backup.$(date +%Y%m%d) /etc/nginx/sites-available/m4bot
        nginx -t && systemctl restart nginx || print_error "Impossibile ripristinare la configurazione" 1
        exit 1
    fi
    
    print_success "Configurazione Nginx aggiornata"
    
    # FASE 2: Aggiorna il certificato SSL
    print_message "FASE 2: Aggiornamento del certificato SSL..."
    
    certbot --nginx -d $MAIN_DOMAIN -d www.$MAIN_DOMAIN -d $DASHBOARD_DOMAIN -d $CONTROL_DOMAIN --non-interactive --agree-tos --email $EMAIL
    
    if [ $? -ne 0 ]; then
        print_error "Impossibile aggiornare il certificato SSL" 0
        print_message "Puoi provare ad aggiornarlo manualmente con il comando:"
        print_message "certbot --nginx -d $MAIN_DOMAIN -d www.$MAIN_DOMAIN -d $DASHBOARD_DOMAIN -d $CONTROL_DOMAIN"
        
        # Chiedi se continuare nonostante l'errore
        read -p "Vuoi continuare con le altre fasi? (s/n): " continue_setup
        if [[ $continue_setup != "s" && $continue_setup != "S" ]]; then
            print_message "Configurazione interrotta."
            exit 1
        fi
    else
        print_success "Certificato SSL aggiornato per includere i sottodomini"
    fi
    
    # FASE 3: Aggiorna il file .env
    print_message "FASE 3: Aggiornamento del file .env..."
    
    # Crea un backup del file .env
    ENV_FILE="/opt/m4bot/.env"
    cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d)"
    print_message "Backup creato: ${ENV_FILE}.backup.$(date +%Y%m%d)"
    
    # Verifica se le variabili dei sottodomini esistono già nel file .env
    if grep -q "DASHBOARD_DOMAIN" "$ENV_FILE"; then
        # Aggiorna i valori esistenti
        sed -i "s/DASHBOARD_DOMAIN=.*/DASHBOARD_DOMAIN=$DASHBOARD_DOMAIN/" "$ENV_FILE"
        sed -i "s/CONTROL_DOMAIN=.*/CONTROL_DOMAIN=$CONTROL_DOMAIN/" "$ENV_FILE"
        print_message "Sottodomini aggiornati nel file .env"
    else
        # Aggiungi le nuove variabili
        echo "" >> "$ENV_FILE"
        echo "# Sottodomini" >> "$ENV_FILE"
        echo "DASHBOARD_DOMAIN=$DASHBOARD_DOMAIN" >> "$ENV_FILE"
        echo "CONTROL_DOMAIN=$CONTROL_DOMAIN" >> "$ENV_FILE"
        print_message "Sottodomini aggiunti al file .env"
    fi
    
    print_success "File .env aggiornato con successo"
    
    # FASE 4: Aggiorna l'app web
    print_message "FASE 4: Aggiornamento dell'applicazione web..."
    
    # Crea backup del file app.py
    APP_FILE="/opt/m4bot/web/app.py"
    cp "$APP_FILE" "${APP_FILE}.backup.$(date +%Y%m%d)"
    print_message "Backup creato: ${APP_FILE}.backup.$(date +%Y%m%d)"
    
    # Codice per gestire i sottodomini
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
    
    # Controlla se il codice è già presente
    if grep -q "def get_subdomain" "$APP_FILE"; then
        print_warning "Il codice per i sottodomini sembra essere già presente, salto questo passaggio"
    else
        # Cerca la riga dove viene importato request
        REQUEST_LINE=$(grep -n "from quart import" "$APP_FILE" | head -1 | cut -d':' -f1)
        
        if [ -n "$REQUEST_LINE" ]; then
            # Inserisci il codice dopo la riga di import
            sed -i "${REQUEST_LINE}r /dev/stdin" "$APP_FILE" <<< "$SUBDOMAIN_CODE"
            print_success "Codice per la gestione dei sottodomini aggiunto con successo"
        else
            print_error "Impossibile trovare il punto di inserimento per il codice dei sottodomini" 0
            print_warning "Dovrai aggiungere manualmente il codice per la gestione dei sottodomini"
        fi
    fi
    
    # FASE 5: Riavvio dei servizi
    print_message "FASE 5: Riavvio dei servizi..."
    
    # Riavvio del servizio web
    if systemctl is-active --quiet m4bot-web.service; then
        systemctl restart m4bot-web.service
        print_message "Servizio web riavviato"
    else
        systemctl start m4bot-web.service
        print_message "Servizio web avviato"
    fi
    
    print_message "====================================================="
    print_message "CONFIGURAZIONE DEI SOTTODOMINI COMPLETATA"
    print_message "====================================================="
    print_message "I sottodomini sono stati configurati con successo:"
    print_message "- $MAIN_DOMAIN → sito principale"
    print_message "- $DASHBOARD_DOMAIN → accesso diretto alla dashboard"
    print_message "- $CONTROL_DOMAIN → accesso diretto al pannello di controllo"
    print_message "====================================================="
    print_message "NOTA: Potrebbe essere necessario attendere qualche minuto"
    print_message "      affinché i DNS si aggiornino completamente."
    print_message "====================================================="
}

# Esecuzione dello script
main 