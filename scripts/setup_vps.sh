#!/bin/bash
# Script per preparare l'ambiente VPS Linux per M4Bot

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

# Controlla se è root
if [ "$(id -u)" != "0" ]; then
    print_error "Questo script deve essere eseguito come root" 1
fi

print_message "Preparazione dell'ambiente VPS per M4Bot..."

# Aggiorna il sistema
print_message "Aggiornamento del sistema..."
apt-get update && apt-get upgrade -y || print_error "Impossibile aggiornare il sistema" 1
print_success "Sistema aggiornato"

# Installa pacchetti essenziali
print_message "Installazione pacchetti essenziali..."
apt-get install -y python3 python3-pip python3-venv python3-dev git curl wget dos2unix \
    build-essential libssl-dev nginx supervisor redis-server \
    postgresql postgresql-contrib libpq-dev || print_error "Impossibile installare i pacchetti essenziali" 1
print_success "Pacchetti essenziali installati"

# Converti i file del progetto
print_message "Converti i file del progetto per Linux..."
if [ ! -x "scripts/convert_scripts.sh" ]; then
    print_message "Script di conversione non eseguibile, impostando permessi..."
    chmod +x scripts/convert_scripts.sh
fi
./scripts/convert_scripts.sh || print_error "Errore durante la conversione dei file" 1
print_success "File convertiti correttamente"

# Crea ambiente virtuale e installa dipendenze
print_message "Configurazione ambiente Python..."
if [ ! -d "venv" ]; then
    python3 -m venv venv || print_error "Impossibile creare l'ambiente virtuale" 1
    print_success "Ambiente virtuale creato"
fi

print_message "Installazione dipendenze Python..."
source venv/bin/activate
pip install --upgrade pip
pip install wheel setuptools
pip install -r requirements.txt || print_warning "Alcuni pacchetti potrebbero non essere stati installati correttamente"

# Fix specifico per Flask e Babel
print_message "Configurazione Flask e Babel..."
pip install "flask>=2.3.3" "flask-babel>=4.0.0" "Babel>=2.14.0" || print_warning "Errore nell'installazione di Flask-Babel"
print_success "Flask e Babel configurati correttamente"

# Correzione permessi per le directory importanti
print_message "Impostazione permessi corretti per le directory..."
mkdir -p web/translations
chmod -R 755 web/translations
mkdir -p logs
chmod -R 755 logs
chown -R $SUDO_USER:$SUDO_USER . || print_warning "Impossibile cambiare proprietario dei file (ignora se non rilevante)"
print_success "Permessi directory impostati correttamente"

# Verifica l'esecuzione degli script principali
print_message "Verifica dei permessi di esecuzione degli script principali..."
for script in scripts/install.sh scripts/setup.sh scripts/start.sh; do
    if [ ! -x "$script" ]; then
        print_warning "$script non è eseguibile. Impostando i permessi..."
        chmod +x "$script"
    fi
done
print_success "Permessi di esecuzione verificati"

# Installa componenti opzionali
print_message "Vuoi installare componenti opzionali per migliorare le prestazioni? (y/n)"
read -r install_optional

if [ "$install_optional" = "y" ] || [ "$install_optional" = "Y" ]; then
    print_message "Installazione componenti opzionali..."
    apt-get install -y libjpeg-dev libfreetype6-dev libffi-dev || print_warning "Errore nell'installazione dei componenti opzionali"
    pip install "gunicorn>=21.2.0" "uvloop>=0.18.0" "httptools>=0.6.1" || print_warning "Errore nell'installazione dei pacchetti Python opzionali"
    print_success "Componenti opzionali installati"
fi

print_message "L'ambiente VPS è stato preparato. Ora puoi eseguire lo script di installazione con: ./scripts/install.sh" 