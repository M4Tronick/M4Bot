#!/bin/bash
# Script principale per configurare tutte le risorse grafiche e web di M4Bot

# Colori per l'output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "\n${BLUE}======================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}======================================${NC}\n"
}

# Verifica che lo script sia eseguito dalla directory principale
if [ ! -d "scripts" ] || [ ! -d "web" ]; then
    echo -e "${RED}Errore: Esegui questo script dalla directory principale del progetto${NC}"
    exit 1
fi

# Ottieni la directory corrente
CURRENT_DIR=$(pwd)

print_header "Configurazione risorse M4Bot"
echo -e "Directory corrente: ${CURRENT_DIR}"

# Verifica directory custom
CUSTOM_DIR="web/templates/custom"
if [ ! -d "$CUSTOM_DIR" ]; then
    echo -e "${YELLOW}Creazione directory per i template personalizzati...${NC}"
    mkdir -p "$CUSTOM_DIR"
    echo -e "${GREEN}Directory ${CUSTOM_DIR} creata${NC}"
fi

# Download risorse esterne
print_header "Scaricamento risorse esterne"
bash scripts/download_resources.sh

# Creazione favicon
print_header "Gestione favicon"
bash scripts/create_favicon.sh

# Sposta i link ai favicon nella directory custom
echo -e "${YELLOW}Spostamento link favicon nella directory custom...${NC}"
if [ -f "web/static/favicon-links.html" ]; then
    mv web/static/favicon-links.html web/templates/custom/favicon-links.html
    echo -e "${GREEN}File favicon-links.html spostato correttamente${NC}"
else
    echo -e "${RED}File favicon-links.html non trovato${NC}"
fi

# Verifica se utilizzare base_offline.html
if [ -f "web/templates/base_offline.html" ]; then
    echo -e "${YELLOW}È stato trovato il template base_offline.html${NC}"
    echo -e "${YELLOW}Vuoi sostituire il template base.html con la versione offline? (s/n)${NC}"
    read -r response
    if [[ "$response" =~ ^([sS])$ ]]; then
        # Backup del file originale
        if [ ! -f "web/templates/base.html.bak" ]; then
            cp web/templates/base.html web/templates/base.html.bak
            echo -e "${GREEN}Backup del file base.html creato${NC}"
        fi
        
        # Sostituzione del file
        cp web/templates/base_offline.html web/templates/base.html
        echo -e "${GREEN}Il template base.html è stato sostituito con la versione offline${NC}"
    else
        echo -e "${YELLOW}Il template base.html non è stato modificato${NC}"
    fi
fi

print_header "Verifica delle icone nelle pagine"

# Funzione per verificare la presenza di icone Font Awesome in un file
check_icons() {
    local file=$1
    if [ -f "$file" ]; then
        local icons=$(grep -o "fa[sbrld] fa-[a-z-]\+" "$file" | sort | uniq)
        local count=$(echo "$icons" | wc -l)
        echo -e "${YELLOW}File: ${file}${NC}"
        echo -e "${YELLOW}Icone trovate: ${count}${NC}"
        
        # Mostra le prime 5 icone come esempio
        if [ "$count" -gt 0 ]; then
            echo -e "${YELLOW}Esempi:${NC}"
            echo "$icons" | head -n 5 | while read -r icon; do
                echo -e "  - ${icon}"
            done
            
            if [ "$count" -gt 5 ]; then
                echo -e "  - ... e altre $(($count - 5)) icone"
            fi
        fi
    else
        echo -e "${RED}File non trovato: ${file}${NC}"
    fi
    echo
}

# Verifica i principali file di template
for template in web/templates/base.html web/templates/dashboard.html web/templates/login.html web/templates/control_panel.html; do
    check_icons "$template"
done

print_header "Informazioni sulle risorse"

# Mostra informazioni sulle risorse
echo -e "${YELLOW}Directory risorse statiche:${NC}"
find web/static -type d | sort

echo -e "\n${YELLOW}File CSS:${NC}"
find web/static/css -type f -name "*.css" | sort

echo -e "\n${YELLOW}File JavaScript:${NC}"
find web/static/js -type f -name "*.js" | sort

echo -e "\n${YELLOW}Icone e immagini:${NC}"
find web/static/img -type f | sort

print_header "Configurazione completata!"
echo -e "${GREEN}Tutte le risorse sono state configurate con successo.${NC}"
echo -e "${YELLOW}Ora puoi eseguire l'applicazione web per verificare le modifiche.${NC}"
echo -e "${YELLOW}Se riscontri problemi, puoi ripristinare il file base.html originale dalla copia di backup.${NC}" 