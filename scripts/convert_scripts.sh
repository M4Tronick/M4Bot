#!/bin/bash
# Script per convertire i file del progetto per l'uso su VPS Linux
# Risolve problemi di fine riga e imposta i permessi corretti

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

# Verifico se è installato dos2unix
if ! command -v dos2unix &> /dev/null; then
    print_warning "dos2unix non è installato. Tentativo di installazione..."
    apt-get update && apt-get install -y dos2unix || {
        print_error "Impossibile installare dos2unix. Installa manualmente con: apt-get install dos2unix" 1
    }
    print_success "dos2unix installato"
fi

print_message "Conversione dei file del progetto per VPS Linux..."

# Converti fine riga in tutti gli script shell
print_message "Conversione fine riga negli script shell..."
find scripts -type f -name "*.sh" -exec dos2unix {} \; || print_error "Errore durante la conversione degli script" 1
print_success "Fine riga negli script convertiti correttamente"

# Imposta permessi di esecuzione su tutti gli script shell
print_message "Impostazione permessi di esecuzione negli script..."
find scripts -type f -name "*.sh" -exec chmod +x {} \; || print_error "Errore durante l'impostazione dei permessi di esecuzione" 1
print_success "Permessi di esecuzione impostati correttamente"

# Converti fine riga nei file Python
print_message "Conversione fine riga nei file Python..."
find . -type f -name "*.py" -exec dos2unix {} \; || print_warning "Errore durante la conversione dei file Python"
print_success "Fine riga nei file Python convertiti correttamente"

# Converti fine riga nei file di configurazione
print_message "Conversione fine riga nei file di configurazione..."
find . -type f -name "*.cfg" -exec dos2unix {} \; || print_warning "Errore durante la conversione dei file di configurazione"
print_success "Fine riga nei file di configurazione convertiti correttamente"

# Converti fine riga nei file di servizio
print_message "Conversione fine riga nei file di servizio..."
find scripts -type f -name "*.service" -exec dos2unix {} \; || print_warning "Errore durante la conversione dei file di servizio"
print_success "Fine riga nei file di servizio convertiti correttamente"

# Corregge problemi di percorsi
print_message "Controllo percorsi nei file di configurazione..."
if [ -f .env ]; then
    # Correggi percorsi in .env
    sed -i 's/\\/\//g' .env || print_warning "Errore durante la correzione dei percorsi in .env"
    print_success "Percorsi in .env corretti"
fi

print_message "Conversione completata con successo!"
print_success "Il progetto è pronto per essere utilizzato su VPS Linux."
