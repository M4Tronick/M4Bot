#!/bin/bash
# Script per inizializzare tutte le directory necessarie per M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Directory principale
M4BOT_DIR="/opt/m4bot"
BOT_DIR="$M4BOT_DIR/bot"
WEB_DIR="$M4BOT_DIR/web"

print_message "Creazione delle directory necessarie per M4Bot..."

# Crea directory principale se non esiste
if [ ! -d "$M4BOT_DIR" ]; then
    print_message "Creazione directory principale: $M4BOT_DIR"
    mkdir -p "$M4BOT_DIR"
    if [ $? -ne 0 ]; then
        print_error "Impossibile creare la directory principale" 1
    fi
fi

# Crea le sottodirectory del bot
directories_bot=(
    "$BOT_DIR"
    "$BOT_DIR/logs"
    "$BOT_DIR/languages"
    "$BOT_DIR/data"
    "$BOT_DIR/modules"
    "$BOT_DIR/cache"
)

for dir in "${directories_bot[@]}"; do
    if [ ! -d "$dir" ]; then
        print_message "Creazione directory: $dir"
        mkdir -p "$dir"
        if [ $? -ne 0 ]; then
            print_error "Impossibile creare la directory: $dir" 0
        fi
    fi
done

# Crea le sottodirectory dell'applicazione web
directories_web=(
    "$WEB_DIR"
    "$WEB_DIR/static"
    "$WEB_DIR/static/css"
    "$WEB_DIR/static/js"
    "$WEB_DIR/static/images"
    "$WEB_DIR/static/fonts"
    "$WEB_DIR/templates"
    "$WEB_DIR/uploads"
    "$WEB_DIR/translations"
    "$WEB_DIR/logs"
)

for dir in "${directories_web[@]}"; do
    if [ ! -d "$dir" ]; then
        print_message "Creazione directory: $dir"
        mkdir -p "$dir"
        if [ $? -ne 0 ]; then
            print_error "Impossibile creare la directory: $dir" 0
        fi
    fi
done

# Crea le directory necessarie anche nella directory di sviluppo
DEV_DIR="$HOME/M4Bot"
if [ -d "$DEV_DIR" ]; then
    print_message "Creazione delle directory di sviluppo..."
    
    # Directory del bot
    for dir in "${directories_bot[@]}"; do
        # Sostituisci il percorso assoluto con quello relativo alla directory di sviluppo
        dev_path="${dir/$M4BOT_DIR/$DEV_DIR}"
        if [ ! -d "$dev_path" ]; then
            print_message "Creazione directory di sviluppo: $dev_path"
            mkdir -p "$dev_path"
        fi
    done
    
    # Directory dell'app web
    for dir in "${directories_web[@]}"; do
        # Sostituisci il percorso assoluto con quello relativo alla directory di sviluppo
        dev_path="${dir/$M4BOT_DIR/$DEV_DIR}"
        if [ ! -d "$dev_path" ]; then
            print_message "Creazione directory di sviluppo: $dev_path"
            mkdir -p "$dev_path"
        fi
    done
fi

# Imposta i permessi appropriati
if [ -d "$M4BOT_DIR" ]; then
    print_message "Impostazione dei permessi..."
    
    # Verifica se esiste l'utente m4bot
    if id -u m4bot >/dev/null 2>&1; then
        chown -R m4bot:m4bot "$M4BOT_DIR"
        
        # Imposta i permessi per i file di log
        find "$BOT_DIR/logs" "$WEB_DIR/logs" -type d -exec chmod 755 {} \;
        find "$BOT_DIR/logs" "$WEB_DIR/logs" -type f -exec chmod 644 {} \;
        
        # Imposta i permessi per i file eseguibili
        chmod +x "$BOT_DIR/m4bot.py" 2>/dev/null
        chmod +x "$WEB_DIR/app.py" 2>/dev/null
        
        print_success "Permessi impostati correttamente"
    else
        print_warning "L'utente m4bot non esiste, i permessi non sono stati impostati"
    fi
fi

print_success "Tutte le directory necessarie sono state create!" 