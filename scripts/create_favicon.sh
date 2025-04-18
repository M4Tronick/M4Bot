#!/bin/bash
# Script per creare un favicon personalizzato per M4Bot

# Colori per l'output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Creazione favicon per M4Bot...${NC}"

# Verifica se ImageMagick Ã¨ installato
if ! command -v convert &> /dev/null; then
    echo -e "${RED}ImageMagick non Ã¨ installato. Installalo con 'apt-get install imagemagick'${NC}"
    exit 1
fi

# Directory di destinazione
STATIC_DIR="/opt/m4bot/web/static"
mkdir -p "$STATIC_DIR"

# Crea un'icona semplice con un robot
echo -e "${YELLOW}Creazione icona robot...${NC}"
convert -size 256x256 xc:transparent \
    -fill "#3498db" -draw "circle 128,128 128,228" \
    -fill white -draw "circle 90,100 90,120" \
    -fill white -draw "circle 166,100 166,120" \
    -fill white -draw "roundrectangle 68,150 188,175 10,10" \
    -fill white -draw "rectangle 80,175 100,215" \
    -fill white -draw "rectangle 156,175 176,215" \
    "$STATIC_DIR/favicon.png"

# Crea diverse dimensioni per diversi dispositivi
echo -e "${YELLOW}Creazione favicon in diverse dimensioni...${NC}"
convert "$STATIC_DIR/favicon.png" -resize 16x16 "$STATIC_DIR/favicon-16x16.png"
convert "$STATIC_DIR/favicon.png" -resize 32x32 "$STATIC_DIR/favicon-32x32.png"
convert "$STATIC_DIR/favicon.png" -resize 48x48 "$STATIC_DIR/favicon-48x48.png"
convert "$STATIC_DIR/favicon.png" -resize 192x192 "$STATIC_DIR/android-chrome-192x192.png"
convert "$STATIC_DIR/favicon.png" -resize 512x512 "$STATIC_DIR/android-chrome-512x512.png"
convert "$STATIC_DIR/favicon.png" -resize 180x180 "$STATIC_DIR/apple-touch-icon.png"

# Crea il favicon.ico (combina 16x16, 32x32 e 48x48)
echo -e "${YELLOW}Creazione favicon.ico...${NC}"
convert "$STATIC_DIR/favicon-16x16.png" "$STATIC_DIR/favicon-32x32.png" "$STATIC_DIR/favicon-48x48.png" "$STATIC_DIR/favicon.ico"

# Imposta i permessi corretti
echo -e "${YELLOW}Impostazione dei permessi...${NC}"
chown m4bot:m4bot "$STATIC_DIR"/*.png "$STATIC_DIR/favicon.ico"
chmod 644 "$STATIC_DIR"/*.png "$STATIC_DIR/favicon.ico"

echo -e "${GREEN}Favicon creato con successo!${NC}" 