#!/bin/bash
# Script per aggiornare il file .env con i sottodomini

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzioni di utilitÃ 
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

# Verifica se il file .env esiste
ENV_FILE="/opt/m4bot/.env"
if [ ! -f "$ENV_FILE" ]; then
    print_error "File .env non trovato in $ENV_FILE" 1
fi

# Ottieni il dominio principale
print_message "====================================================="
print_message "AGGIORNAMENTO FILE .ENV CON I SOTTODOMINI"
print_message "====================================================="

read -p "Inserisci il dominio principale (es. m4bot.it): " MAIN_DOMAIN
if [ -z "$MAIN_DOMAIN" ]; then
    print_error "Il dominio principale Ã¨ obbligatorio" 1
fi

# Prepara i sottodomini
DASHBOARD_DOMAIN="dashboard.$MAIN_DOMAIN"
CONTROL_DOMAIN="control.$MAIN_DOMAIN"

print_message "Aggiunta dei sottodomini nel file .env: $DASHBOARD_DOMAIN e $CONTROL_DOMAIN"

# Crea un backup del file .env
cp "$ENV_FILE" "${ENV_FILE}.backup"
print_message "Backup creato: ${ENV_FILE}.backup"

# Verifica se le variabili dei sottodomini esistono giÃ  nel file .env
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
print_message "====================================================="
print_message "Ora puoi configurare l'applicazione per utilizzare i nuovi sottodomini"
print_message "=====================================================" 