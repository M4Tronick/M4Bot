#!/bin/bash
# Script per scaricare le risorse web necessarie per M4Bot

# Colori per l'output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Scaricamento risorse per M4Bot...${NC}"

# Directory di destinazione
ASSETS_DIR="/opt/m4bot/web/static"
FONTS_DIR="$ASSETS_DIR/fonts"
CSS_DIR="$ASSETS_DIR/css"
JS_DIR="$ASSETS_DIR/js"

# Crea le directory se non esistono
mkdir -p "$FONTS_DIR" "$CSS_DIR" "$JS_DIR"

# Scarica Font Awesome
echo -e "${YELLOW}Scaricamento Font Awesome...${NC}"
FONTAWESOME_VERSION="6.4.0"
FONTAWESOME_URL="https://use.fontawesome.com/releases/v$FONTAWESOME_VERSION/fontawesome-free-$FONTAWESOME_VERSION-web.zip"
TMP_DIR=$(mktemp -d)
wget "$FONTAWESOME_URL" -O "$TMP_DIR/fontawesome.zip"

if [ $? -ne 0 ]; then
    echo -e "${RED}Errore durante il download di Font Awesome${NC}"
    exit 1
fi

# Estrai Font Awesome
echo -e "${YELLOW}Estrazione Font Awesome...${NC}"
unzip -q "$TMP_DIR/fontawesome.zip" -d "$TMP_DIR"

# Copia i file necessari
echo -e "${YELLOW}Copia dei file necessari...${NC}"
cp -r "$TMP_DIR/fontawesome-free-$FONTAWESOME_VERSION-web/css/"* "$CSS_DIR/"
cp -r "$TMP_DIR/fontawesome-free-$FONTAWESOME_VERSION-web/webfonts/"* "$FONTS_DIR/"
cp -r "$TMP_DIR/fontawesome-free-$FONTAWESOME_VERSION-web/js/"* "$JS_DIR/"

# Pulisci
rm -rf "$TMP_DIR"

# Scarica Chart.js
echo -e "${YELLOW}Scaricamento Chart.js...${NC}"
CHARTJS_VERSION="3.9.1"
CHARTJS_URL="https://cdn.jsdelivr.net/npm/chart.js@$CHARTJS_VERSION/dist/chart.min.js"
wget "$CHARTJS_URL" -O "$JS_DIR/chart.min.js"

if [ $? -ne 0 ]; then
    echo -e "${RED}Errore durante il download di Chart.js${NC}"
    exit 1
fi

# Scarica Bootstrap
echo -e "${YELLOW}Scaricamento Bootstrap...${NC}"
BOOTSTRAP_VERSION="5.3.0"
BOOTSTRAP_CSS_URL="https://cdn.jsdelivr.net/npm/bootstrap@$BOOTSTRAP_VERSION/dist/css/bootstrap.min.css"
BOOTSTRAP_JS_URL="https://cdn.jsdelivr.net/npm/bootstrap@$BOOTSTRAP_VERSION/dist/js/bootstrap.bundle.min.js"

wget "$BOOTSTRAP_CSS_URL" -O "$CSS_DIR/bootstrap.min.css"
if [ $? -ne 0 ]; then
    echo -e "${RED}Errore durante il download di Bootstrap CSS${NC}"
    exit 1
fi

wget "$BOOTSTRAP_JS_URL" -O "$JS_DIR/bootstrap.bundle.min.js"
if [ $? -ne 0 ]; then
    echo -e "${RED}Errore durante il download di Bootstrap JS${NC}"
    exit 1
fi

# Imposta i permessi corretti
echo -e "${YELLOW}Impostazione dei permessi...${NC}"
chown -R m4bot:m4bot "$ASSETS_DIR"
chmod -R 755 "$ASSETS_DIR"

echo -e "${GREEN}Risorse scaricate e configurate con successo!${NC}" 