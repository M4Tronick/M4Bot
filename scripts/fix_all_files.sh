#!/bin/bash
# Script per correggere automaticamente tutti i file nella cartella M4Bot
# Questo script analizza e corregge errori comuni in tutti i tipi di file

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Directory di installazione (modificare se necessario)
INSTALL_DIR="/opt/m4bot"

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

# Funzione per mostrare una barra di progresso da riga di comando
show_progress() {
    local percent=$1
    local width=50
    local num_chars=$((percent * width / 100))
    
    # Costruisci la barra
    printf "["
    for ((i=0; i<width; i++)); do
        if [ $i -lt $num_chars ]; then
            printf "#"
        else
            printf " "
        fi
    done
    printf "] %3d%%\r" $percent
}

# Controlla che lo script sia eseguito come root
if [ "$(id -u)" != "0" ]; then
    print_error "Questo script deve essere eseguito come root" 1
fi

# Se viene passato un parametro, usa quello come directory di installazione
if [ -n "$1" ]; then
    INSTALL_DIR="$1"
fi

# Verifica che la directory esista
if [ ! -d "$INSTALL_DIR" ]; then
    print_error "Directory $INSTALL_DIR non trovata" 1
fi

print_message "Scansione e correzione di tutti i file in $INSTALL_DIR..."

# Contatori per statistiche
TOTAL_FILES=0
FIXED_FILES=0
CHECKED_EXTENSIONS=0

# Ottieni il numero totale di file da processare (per la barra di progresso)
FILE_COUNT=$(find "$INSTALL_DIR" -type f | wc -l)
if [ "$FILE_COUNT" -eq 0 ]; then
    FILE_COUNT=1  # Evita divisione per zero
fi

# Funzione interna per aggiornare la barra di progresso
update_progress() {
    local file_num=$1
    local percent=$((file_num * 100 / FILE_COUNT))
    show_progress $percent
}

# 1. Correggi i file Python (.py)
print_message "Correzione file Python..."
PY_FILES=$(find "$INSTALL_DIR" -type f -name "*.py")
PY_COUNT=0

for py_file in $PY_FILES; do
    TOTAL_FILES=$((TOTAL_FILES + 1))
    PY_COUNT=$((PY_COUNT + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga e encoding
    dos2unix "$py_file" >/dev/null 2>&1
    
    # Correggi problemi di codifica UTF-8
    if ! file "$py_file" | grep -q "UTF-8"; then
        iconv -f ISO-8859-1 -t UTF-8 -o "$py_file.tmp" "$py_file" && mv "$py_file.tmp" "$py_file"
    fi
    
    # Correggi i percorsi nel file (stile Windows a Linux)
    sed -i 's/\\/\//g' "$py_file"
    
    # Correggi problemi comuni
    # Rimuovi spazi bianchi alla fine delle righe
    sed -i 's/[ \t]*$//' "$py_file"
    
    # Correggi problemi di shebang
    if head -n 1 "$py_file" | grep -q "^#!.*python"; then
        sed -i '1s|^#!.*python.*$|#!/usr/bin/env python3|' "$py_file"
        chmod +x "$py_file"
    fi
    
    # Correggi problemi di codice specifici per Flask/Babel
    if grep -q "flask_babel" "$py_file"; then
        # Correzione importazioni di Flask-Babel
        sed -i 's/from flask.ext.babel import/from flask_babel import/g' "$py_file"
        
        # Assicurati che babel_compat sia importato correttamente
        if grep -q "babel_compat" "$py_file" && ! grep -q "from babel_compat import Babel" "$py_file"; then
            sed -i 's/from babel_compat import \*/from babel_compat import Babel, logger as babel_logger/g' "$py_file"
            sed -i 's/from flask_babel import Babel, gettext/from flask_babel import gettext/g' "$py_file"
            FIXED_FILES=$((FIXED_FILES + 1))
        fi
    fi
    
    # Correggi problemi con i PATH relativi
    if grep -q "os.path.join" "$py_file"; then
        # Controlla se c'è un percorso hardcoded Windows
        if grep -q "C:[\\\/]" "$py_file"; then
            sed -i 's|C:[\\\/][^"]*|/opt/m4bot|g' "$py_file"
            FIXED_FILES=$((FIXED_FILES + 1))
        fi
    fi
done

# 2. Correggi i file di shell script (.sh)
print_message "Correzione file shell script..."
SH_FILES=$(find "$INSTALL_DIR" -type f -name "*.sh")
SH_COUNT=0

for sh_file in $SH_FILES; do
    TOTAL_FILES=$((TOTAL_FILES + 1))
    SH_COUNT=$((SH_COUNT + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga
    dos2unix "$sh_file" >/dev/null 2>&1
    
    # Assicurati che sia eseguibile
    chmod +x "$sh_file"
    
    # Correggi problemi comuni
    # Rimuovi spazi bianchi alla fine delle righe
    sed -i 's/[ \t]*$//' "$sh_file"
    
    # Correggi shebang
    if ! head -n 1 "$sh_file" | grep -q "^#!/bin/bash"; then
        sed -i '1s|^#!.*$|#!/bin/bash|' "$sh_file"
        if ! head -n 1 "$sh_file" | grep -q "^#!"; then
            sed -i '1i#!/bin/bash' "$sh_file"
        fi
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
    
    # Correggi percorsi Windows
    if grep -q "C:[\\\/]" "$sh_file"; then
        sed -i 's|C:[\\\/][^"]*|/opt/m4bot|g' "$sh_file"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
    
    # Rimuovi caratteri di controllo
    sed -i 's/\r//g' "$sh_file"
done

# 3. Correggi i file HTML
print_message "Correzione file HTML..."
HTML_FILES=$(find "$INSTALL_DIR" -type f -name "*.html")
HTML_COUNT=0

for html_file in $HTML_FILES; do
    TOTAL_FILES=$((TOTAL_FILES + 1))
    HTML_COUNT=$((HTML_COUNT + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga
    dos2unix "$html_file" >/dev/null 2>&1
    
    # Correggi problemi di encoding
    if ! file "$html_file" | grep -q "UTF-8"; then
        iconv -f ISO-8859-1 -t UTF-8 -o "$html_file.tmp" "$html_file" && mv "$html_file.tmp" "$html_file"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
    
    # Correggi percorsi Windows nelle src e href
    if grep -q "C:[\\\/]" "$html_file"; then
        sed -i 's|C:[\\\/][^"]*|/opt/m4bot|g' "$html_file"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
    
    # Assicurati che il doctype sia presente
    if ! head -n 1 "$html_file" | grep -i -q "<!DOCTYPE"; then
        sed -i '1i<!DOCTYPE html>' "$html_file"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
done

# 4. Correggi i file JavaScript
print_message "Correzione file JavaScript..."
JS_FILES=$(find "$INSTALL_DIR" -type f -name "*.js")
JS_COUNT=0

for js_file in $JS_FILES; do
    TOTAL_FILES=$((TOTAL_FILES + 1))
    JS_COUNT=$((JS_COUNT + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga
    dos2unix "$js_file" >/dev/null 2>&1
    
    # Correggi problemi comuni
    # Rimuovi spazi bianchi alla fine delle righe
    sed -i 's/[ \t]*$//' "$js_file"
    
    # Rimuovi caratteri di controllo
    sed -i 's/\r//g' "$js_file"
    
    # Correggi percorsi Windows
    if grep -q "C:[\\\/]" "$js_file"; then
        sed -i 's|C:[\\\/][^"]*|/opt/m4bot|g' "$js_file"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
done

# 5. Correggi i file CSS
print_message "Correzione file CSS..."
CSS_FILES=$(find "$INSTALL_DIR" -type f -name "*.css")
CSS_COUNT=0

for css_file in $CSS_FILES; do
    TOTAL_FILES=$((TOTAL_FILES + 1))
    CSS_COUNT=$((CSS_COUNT + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga
    dos2unix "$css_file" >/dev/null 2>&1
    
    # Correggi problemi comuni
    # Rimuovi spazi bianchi alla fine delle righe
    sed -i 's/[ \t]*$//' "$css_file"
    
    # Rimuovi caratteri di controllo
    sed -i 's/\r//g' "$css_file"
    
    # Correggi URL con percorsi Windows
    if grep -q "C:[\\\/]" "$css_file"; then
        sed -i 's|C:[\\\/][^"]*|/opt/m4bot|g' "$css_file"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
done

# 6. Correggi i file di configurazione
print_message "Correzione file di configurazione..."
CONFIG_FILES=$(find "$INSTALL_DIR" -type f -name "*.cfg" -o -name "*.ini" -o -name "*.conf" -o -name "*.json" -o -name "*.yml" -o -name "*.yaml" -o -name "*.xml")
CONFIG_COUNT=0

for config_file in $CONFIG_FILES; do
    TOTAL_FILES=$((TOTAL_FILES + 1))
    CONFIG_COUNT=$((CONFIG_COUNT + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga
    dos2unix "$config_file" >/dev/null 2>&1
    
    # Correggi problemi comuni
    # Rimuovi spazi bianchi alla fine delle righe
    sed -i 's/[ \t]*$//' "$config_file"
    
    # Correggi percorsi Windows
    if grep -q "C:[\\\/]" "$config_file"; then
        sed -i 's|C:[\\\/][^"]*|/opt/m4bot|g' "$config_file"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
    
    # Correggi backslash in percorsi
    sed -i 's/\\/\//g' "$config_file"
    
    # Per i file JSON, verifica la validità (se è installato jq)
    if [[ "$config_file" == *.json ]] && command -v jq &> /dev/null; then
        if ! jq . "$config_file" >/dev/null 2>&1; then
            print_warning "File JSON non valido: $config_file (non corretto automaticamente)"
        fi
    fi
done

# 7. Correggi i file di traduzione
print_message "Correzione file di traduzione..."
TRANSLATION_FILES=$(find "$INSTALL_DIR" -type f -name "*.po" -o -name "*.mo")
TRANSLATION_COUNT=0

for translation_file in $TRANSLATION_FILES; do
    TOTAL_FILES=$((TOTAL_FILES + 1))
    TRANSLATION_COUNT=$((TRANSLATION_COUNT + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga
    dos2unix "$translation_file" >/dev/null 2>&1
    
    # Correggi problemi di encoding nei file PO
    if [[ "$translation_file" == *.po ]]; then
        if ! file "$translation_file" | grep -q "UTF-8"; then
            iconv -f ISO-8859-1 -t UTF-8 -o "$translation_file.tmp" "$translation_file" && mv "$translation_file.tmp" "$translation_file"
            FIXED_FILES=$((FIXED_FILES + 1))
        fi
    fi
done

# 8. Correggi i file service per systemd
print_message "Correzione file service per systemd..."
SERVICE_FILES=$(find "$INSTALL_DIR" -type f -name "*.service")
SERVICE_COUNT=0

for service_file in $SERVICE_FILES; do
    TOTAL_FILES=$((TOTAL_FILES + 1))
    SERVICE_COUNT=$((SERVICE_COUNT + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga
    dos2unix "$service_file" >/dev/null 2>&1
    
    # Correggi percorsi
    if grep -q "C:[\\\/]" "$service_file"; then
        sed -i 's|C:[\\\/][^"]*|/opt/m4bot|g' "$service_file"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
    
    # Correggi backslash in percorsi
    sed -i 's/\\/\//g' "$service_file"
    
    # Assicurati che ci siano i comandi di base
    if ! grep -q "\[Service\]" "$service_file"; then
        print_warning "File service non valido: $service_file (non corretto automaticamente)"
    fi
done

# 9. Correggi .env file
if [ -f "$INSTALL_DIR/.env" ]; then
    print_message "Correzione file .env..."
    TOTAL_FILES=$((TOTAL_FILES + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga
    dos2unix "$INSTALL_DIR/.env" >/dev/null 2>&1
    
    # Correggi percorsi Windows
    if grep -q "C:[\\\/]" "$INSTALL_DIR/.env"; then
        sed -i 's|C:[\\\/][^"]*|/opt/m4bot|g' "$INSTALL_DIR/.env"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
    
    # Correggi backslash in percorsi
    sed -i 's/\\/\//g' "$INSTALL_DIR/.env"
    
    # Imposta permessi corretti
    chmod 600 "$INSTALL_DIR/.env"
fi

# 10. Correggi i file README e markdown
print_message "Correzione file README e markdown..."
MD_FILES=$(find "$INSTALL_DIR" -type f -name "*.md")
MD_COUNT=0

for md_file in $MD_FILES; do
    TOTAL_FILES=$((TOTAL_FILES + 1))
    MD_COUNT=$((MD_COUNT + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga
    dos2unix "$md_file" >/dev/null 2>&1
    
    # Correggi percorsi Windows nei comandi di esempio
    if grep -q "C:[\\\/]" "$md_file"; then
        sed -i 's|C:[\\\/][^`]*|/opt/m4bot|g' "$md_file"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
done

# 11. Correggi i file di template (jinja2, twig, etc)
print_message "Correzione file di template..."
TEMPLATE_FILES=$(find "$INSTALL_DIR" -type f -name "*.jinja" -o -name "*.j2" -o -name "*.twig" -o -name "*.template")
TEMPLATE_COUNT=0

for template_file in $TEMPLATE_FILES; do
    TOTAL_FILES=$((TOTAL_FILES + 1))
    TEMPLATE_COUNT=$((TEMPLATE_COUNT + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga
    dos2unix "$template_file" >/dev/null 2>&1
    
    # Correggi percorsi Windows
    if grep -q "C:[\\\/]" "$template_file"; then
        sed -i 's|C:[\\\/][^"]*|/opt/m4bot|g' "$template_file"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
done

# 12. Correggi script SQL
print_message "Correzione file SQL..."
SQL_FILES=$(find "$INSTALL_DIR" -type f -name "*.sql")
SQL_COUNT=0

for sql_file in $SQL_FILES; do
    TOTAL_FILES=$((TOTAL_FILES + 1))
    SQL_COUNT=$((SQL_COUNT + 1))
    update_progress $TOTAL_FILES
    
    # Converti fine riga
    dos2unix "$sql_file" >/dev/null 2>&1
    
    # Rimuovi caratteri di controllo
    sed -i 's/\r//g' "$sql_file"
    
    # Correggi percorsi Windows
    if grep -q "C:[\\\/]" "$sql_file"; then
        sed -i 's|C:[\\\/][^"]*|/opt/m4bot|g' "$sql_file"
        FIXED_FILES=$((FIXED_FILES + 1))
    fi
done

# Infine, correggi i permessi delle directory principali
print_message "Correzione permessi directory principali..."

# Directory web e traduzioni
if [ -d "$INSTALL_DIR/web" ]; then
    chmod -R 755 "$INSTALL_DIR/web"
    if [ -d "$INSTALL_DIR/web/translations" ]; then
        chmod -R 755 "$INSTALL_DIR/web/translations"
    fi
    if [ -d "$INSTALL_DIR/web/static" ]; then
        chmod -R 755 "$INSTALL_DIR/web/static"
    fi
fi

# Directory logs
if [ -d "$INSTALL_DIR/logs" ]; then
    chmod -R 755 "$INSTALL_DIR/logs"
fi

# Directory scripts
if [ -d "$INSTALL_DIR/scripts" ]; then
    chmod -R 755 "$INSTALL_DIR/scripts"
fi

# Tutti i file nella directory bin devono essere eseguibili
if [ -d "$INSTALL_DIR/bin" ]; then
    find "$INSTALL_DIR/bin" -type f -exec chmod +x {} \;
fi

# Imposta il proprietario
chown -R m4bot:m4bot "$INSTALL_DIR"

# Riporta statistiche
CHECKED_EXTENSIONS=$((PY_COUNT + SH_COUNT + HTML_COUNT + JS_COUNT + CSS_COUNT + CONFIG_COUNT + TRANSLATION_COUNT + SERVICE_COUNT + MD_COUNT + TEMPLATE_COUNT + SQL_COUNT + 1))

echo # Nuova riga per non sovrascrivere la barra di progresso
print_success "Correzione file completata"
print_message "Statistiche:"
print_message "- File analizzati: $TOTAL_FILES"
print_message "- File corretti: $FIXED_FILES"
print_message "- Tipi di file controllati: $CHECKED_EXTENSIONS"

# Verifica se ci sono stati errori
if [ $FIXED_FILES -gt 0 ]; then
    print_success "Sono stati corretti $FIXED_FILES file."
else
    print_message "Nessun file necessitava di correzioni."
fi 