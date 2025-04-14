#!/bin/bash
# Script di verifica della configurazione di M4Bot
# Controlla che tutti i componenti siano configurati correttamente

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

print_message "Avvio verifica della configurazione di M4Bot..."

# Array per tenere traccia dei problemi trovati
declare -a PROBLEMS

# Verifica i file e directory principali
check_path() {
    local path="$1"
    local type="$2"  # file o directory
    local critical="$3"  # true/false se è critico
    
    if [ "$type" = "file" ] && [ ! -f "$path" ]; then
        if [ "$critical" = "true" ]; then
            print_error "File critico non trovato: $path"
            PROBLEMS+=("File critico mancante: $path")
        else
            print_warning "File non trovato: $path"
            PROBLEMS+=("File mancante: $path")
        fi
        return 1
    elif [ "$type" = "directory" ] && [ ! -d "$path" ]; then
        if [ "$critical" = "true" ]; then
            print_error "Directory critica non trovata: $path"
            PROBLEMS+=("Directory critica mancante: $path")
        else
            print_warning "Directory non trovata: $path"
            PROBLEMS+=("Directory mancante: $path")
        fi
        return 1
    fi
    
    return 0
}

# Verifica delle directory principali
print_message "Controllo delle directory principali..."
check_path "/opt/m4bot" "directory" "true"
check_path "/opt/m4bot/bot" "directory" "true"
check_path "/opt/m4bot/web" "directory" "true"
check_path "/opt/m4bot/bot/logs" "directory" "false"

# Verifica dei file principali
print_message "Controllo dei file principali..."
check_path "/opt/m4bot/.env" "file" "true"
check_path "/opt/m4bot/bot/m4bot.py" "file" "true"
check_path "/opt/m4bot/web/app.py" "file" "true"

# Verifica delle configurazioni di sistema
print_message "Controllo delle configurazioni di sistema..."
check_path "/etc/systemd/system/m4bot-bot.service" "file" "true"
check_path "/etc/systemd/system/m4bot-web.service" "file" "true"
check_path "/etc/nginx/sites-available/m4bot" "file" "true"
check_path "/etc/nginx/sites-enabled/m4bot" "file" "true"

# Verifica che il link simbolico sia corretto
if [ -L "/etc/nginx/sites-enabled/m4bot" ]; then
    if [ "$(readlink -f /etc/nginx/sites-enabled/m4bot)" != "/etc/nginx/sites-available/m4bot" ]; then
        print_warning "Il link simbolico di Nginx non punta al file corretto"
        PROBLEMS+=("Link simbolico Nginx non valido")
    fi
fi

# Verifica ambiente virtuale Python
print_message "Controllo dell'ambiente virtuale Python..."
if [ ! -d "/opt/m4bot/venv" ]; then
    print_error "Ambiente virtuale Python non trovato"
    PROBLEMS+=("Ambiente virtuale Python mancante")
elif [ ! -f "/opt/m4bot/venv/bin/python" ]; then
    print_error "Eseguibile Python non trovato nell'ambiente virtuale"
    PROBLEMS+=("Eseguibile Python non trovato nell'ambiente virtuale")
fi

# Verifica le dipendenze Python
if [ -d "/opt/m4bot/venv" ] && [ -f "/opt/m4bot/venv/bin/pip" ]; then
    print_message "Controllo delle dipendenze Python..."
    
    MISSING_DEPS=0
    for dep in flask flask-babel quart gunicorn python-dotenv jinja2 pyyaml aiohttp asyncpg websockets requests cryptography bcrypt; do
        if ! /opt/m4bot/venv/bin/pip freeze | grep -i "$dep" > /dev/null; then
            print_warning "Dipendenza Python mancante: $dep"
            PROBLEMS+=("Dipendenza Python mancante: $dep")
            MISSING_DEPS=1
        fi
    done
    
    if [ $MISSING_DEPS -eq 0 ]; then
        print_success "Tutte le dipendenze Python risultano installate"
    fi
fi

# Verifica il file .env
if [ -f "/opt/m4bot/.env" ]; then
    print_message "Controllo del file .env..."
    
    MISSING_ENV=0
    for var in DB_USER DB_PASSWORD DB_NAME DB_HOST SECRET_KEY ENCRYPTION_KEY CLIENT_ID CLIENT_SECRET REDIRECT_URI; do
        if ! grep -q "^$var=" "/opt/m4bot/.env"; then
            print_warning "Variabile ambiente mancante: $var"
            PROBLEMS+=("Variabile ambiente mancante: $var")
            MISSING_ENV=1
        fi
    done
    
    if [ $MISSING_ENV -eq 0 ]; then
        print_success "Tutte le variabili ambiente richieste sono presenti"
    fi
fi

# Verifica del database PostgreSQL
print_message "Controllo del database PostgreSQL..."
if ! systemctl is-active --quiet postgresql; then
    print_error "PostgreSQL non è in esecuzione"
    PROBLEMS+=("PostgreSQL non è in esecuzione")
else
    # Controlla se esiste il database
    if ! sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw m4bot_db; then
        print_error "Database m4bot_db non trovato in PostgreSQL"
        PROBLEMS+=("Database m4bot_db non trovato")
    else
        print_success "Database m4bot_db trovato"
        
        # Controlla le tabelle principali
        TABLE_CHECK=$(sudo -u postgres psql -d m4bot_db -c "\dt" | grep -E 'users|channels|commands|chat_messages|user_points' | wc -l)
        if [ "$TABLE_CHECK" -lt 5 ]; then
            print_warning "Alcune tabelle principali potrebbero mancare nel database"
            PROBLEMS+=("Tabelle database incomplete")
        else
            print_success "Tabelle database sembrano corrette"
        fi
    fi
fi

# Verifica i permessi
print_message "Controllo dei permessi dei file..."
if [ -d "/opt/m4bot" ]; then
    OWNER=$(stat -c '%U' /opt/m4bot)
    if [ "$OWNER" != "m4bot" ]; then
        print_warning "I file di M4Bot non appartengono all'utente m4bot"
        PROBLEMS+=("Permessi file non corretti")
    fi
    
    # Controlla se m4bot.py è eseguibile
    if [ -f "/opt/m4bot/bot/m4bot.py" ] && [ ! -x "/opt/m4bot/bot/m4bot.py" ]; then
        print_warning "Il file m4bot.py non è eseguibile"
        PROBLEMS+=("m4bot.py non eseguibile")
    fi
    
    # Controlla se app.py è eseguibile
    if [ -f "/opt/m4bot/web/app.py" ] && [ ! -x "/opt/m4bot/web/app.py" ]; then
        print_warning "Il file app.py non è eseguibile"
        PROBLEMS+=("app.py non eseguibile")
    fi
    
    # Controlla i permessi del file .env
    if [ -f "/opt/m4bot/.env" ]; then
        ENV_PERMS=$(stat -c '%a' /opt/m4bot/.env)
        if [ "$ENV_PERMS" != "600" ] && [ "$ENV_PERMS" != "400" ]; then
            print_warning "Il file .env ha permessi troppo aperti ($ENV_PERMS)"
            PROBLEMS+=("Permessi .env non sicuri")
        fi
    fi
fi

# Verifica dello stato dei servizi
print_message "Controllo dello stato dei servizi..."
for service in m4bot-bot.service m4bot-web.service nginx postgresql; do
    if systemctl is-active --quiet "$service"; then
        print_success "Servizio $service: Attivo"
    else
        print_error "Servizio $service: Non attivo"
        PROBLEMS+=("Servizio non attivo: $service")
    fi
done

# Verifica delle porte
print_message "Controllo delle porte in ascolto..."
if ! command -v netstat &> /dev/null && ! command -v ss &> /dev/null; then
    print_warning "netstat o ss non disponibili, saltando il controllo delle porte"
else
    if command -v netstat &> /dev/null; then
        PORT_CHECK_CMD="netstat -tulpn"
    else
        PORT_CHECK_CMD="ss -tulpn"
    fi
    
    # Controlla la porta 5000 (web app interna)
    if ! $PORT_CHECK_CMD | grep -q ":5000"; then
        print_warning "Porta 5000 (web app) non in ascolto"
        PROBLEMS+=("Porta 5000 non in ascolto")
    else
        print_success "Porta 5000 (web app) in ascolto"
    fi
    
    # Controlla la porta 80 (HTTP)
    if ! $PORT_CHECK_CMD | grep -q ":80"; then
        print_warning "Porta 80 (HTTP) non in ascolto"
        PROBLEMS+=("Porta 80 non in ascolto")
    else
        print_success "Porta 80 (HTTP) in ascolto"
    fi
    
    # Controlla la porta 443 (HTTPS)
    if ! $PORT_CHECK_CMD | grep -q ":443"; then
        print_warning "Porta 443 (HTTPS) non in ascolto"
        PROBLEMS+=("Porta 443 non in ascolto")
    else
        print_success "Porta 443 (HTTPS) in ascolto"
    fi
    
    # Controlla la porta 5432 (PostgreSQL)
    if ! $PORT_CHECK_CMD | grep -q ":5432"; then
        print_warning "Porta 5432 (PostgreSQL) non in ascolto"
        PROBLEMS+=("Porta 5432 non in ascolto")
    else
        print_success "Porta 5432 (PostgreSQL) in ascolto"
    fi
fi

# Verifica della connettività di rete
print_message "Controllo della connettività di rete..."
if command -v curl &> /dev/null; then
    # Controlla se il server web risponde
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost)
    if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
        print_success "Il server web risponde correttamente (HTTP code: $HTTP_CODE)"
    else
        print_warning "Il server web non risponde correttamente (HTTP code: $HTTP_CODE)"
        PROBLEMS+=("Server web non risponde (HTTP code: $HTTP_CODE)")
    fi
else
    print_warning "curl non disponibile, saltando il controllo della connettività HTTP"
fi

# Mostra il risultato complessivo
echo ""
print_message "===== RISULTATO DELLA VERIFICA ====="

if [ ${#PROBLEMS[@]} -eq 0 ]; then
    print_success "Nessun problema rilevato. La configurazione di M4Bot sembra corretta."
else
    print_error "Sono stati rilevati ${#PROBLEMS[@]} problemi:"
    
    for i in "${!PROBLEMS[@]}"; do
        echo "   $((i+1)). ${PROBLEMS[$i]}"
    done
    
    echo ""
    print_message "Suggerimenti per risolvere i problemi:"
    echo "1. Verifica che tutti i file e le directory siano presenti e con i permessi corretti"
    echo "2. Assicurati che tutti i servizi siano in esecuzione con 'systemctl start <servizio>'"
    echo "3. Controlla i log di sistema con 'journalctl -u <servizio>'"
    echo "4. Verifica la configurazione del database PostgreSQL"
    echo "5. Assicurati che il file .env contenga tutte le variabili necessarie"
fi 