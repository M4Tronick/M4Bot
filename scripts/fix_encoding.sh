#!/bin/bash
# Script per correggere i problemi di encoding nei file bash

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

# Controlla che lo script sia eseguito come root
if [ "$(id -u)" != "0" ]; then
    print_error "Questo script deve essere eseguito come root" 1
fi

print_message "Correzione problemi di encoding nei file bash..."

# Funzione per correggere un singolo file
fix_file_encoding() {
    local file=$1
    local filename=$(basename "$file")
    
    print_message "Analisi del file: $filename"
    
    # Verifica se il file ha problemi di encoding (cerca caratteri come Ã¨ o Ã)
    if grep -q "Ã¨\|Ã" "$file"; then
        print_warning "Problemi di encoding trovati in $filename"
        
        # Backup del file originale
        cp "$file" "${file}.bak"
        print_message "Backup creato: ${filename}.bak"
        
        # Tenta di correggere con iconv
        iconv -f ISO-8859-1 -t UTF-8 -o "${file}.tmp" "$file"
        if [ $? -eq 0 ]; then
            mv "${file}.tmp" "$file"
            print_success "Encoding corretto per $filename (ISO-8859-1 -> UTF-8)"
            return 0
        else
            rm -f "${file}.tmp"
            
            # Prova un approccio alternativo con sed per sostituire caratteri problematici
            # Sostituisci i caratteri accentati comuni
            sed -i 's/Ã¨/è/g' "$file"
            sed -i 's/Ã/à/g' "$file"
            sed -i 's/Ã¹/ù/g' "$file"
            sed -i 's/Ã²/ò/g' "$file"
            sed -i 's/Ã©/é/g' "$file"
            sed -i 's/Ã¬/ì/g' "$file"
            
            print_success "Encoding corretto per $filename (sostituzione diretta)"
            return 0
        fi
    else
        print_message "Nessun problema di encoding rilevato in $filename"
        return 1
    fi
}

# Lista dei file da correggere
FILES_TO_FIX=(
    "scripts/add_subdomains.sh"
    "scripts/check_config.sh"
    "scripts/monitor.sh"
    "scripts/optimize_db.sh"
    "scripts/secure.sh"
    "scripts/setup_nginx.sh"
    "scripts/setup.sh"
    "scripts/setup_resources.sh"
    "scripts/setup_subdomains.sh"
    "scripts/start.sh"
    "scripts/stop.sh"
    "scripts/update_env.sh"
    "scripts/update_webapp.sh"
    "scripts/restart.sh"
    "scripts/maintenance.sh"
    "scripts/backup.sh"
)

# Contatore di file corretti
FIXED_COUNT=0

# Correggi tutti i file nella lista
for file in "${FILES_TO_FIX[@]}"; do
    if [ -f "$file" ]; then
        fix_file_encoding "$file"
        if [ $? -eq 0 ]; then
            FIXED_COUNT=$((FIXED_COUNT + 1))
        fi
    else
        print_warning "File non trovato: $file"
    fi
done

# Rapporto finale
print_message "====================================================="
print_message "CORREZIONE ENCODING COMPLETATA"
print_message "====================================================="
print_message "File analizzati: ${#FILES_TO_FIX[@]}"
print_message "File corretti: $FIXED_COUNT"
print_message "====================================================="

if [ $FIXED_COUNT -gt 0 ]; then
    print_success "Correzione encoding completata con successo!"
else
    print_warning "Nessun file necessitava di correzioni di encoding"
fi

print_message "Per verificare eventuali problemi residui, esegui:"
print_message "grep -r \"Ã¨\|Ã\" scripts/" 