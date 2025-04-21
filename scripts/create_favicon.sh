#!/bin/bash
# Script per generare favicon e icone per M4Bot

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Verifica se ImageMagick è installato
if ! command -v convert &> /dev/null; then
    echo -e "${RED}ImageMagick non è installato. Installalo con 'apt-get install imagemagick'${NC}"
    exit 1
fi

# Variabili di configurazione
INPUT_IMAGE=${1:-"logo.png"}
OUTPUT_DIR=${2:-"/opt/m4bot/web/static/images/icons"}
TEMP_DIR="/tmp/m4bot_favicon"

# Funzioni di utilità
print_message() {
    echo -e "${BLUE}[M4Bot]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERRORE]${NC} $1"
    exit 1
}

print_success() {
    echo -e "${GREEN}[SUCCESSO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[AVVISO]${NC} $1"
}

# Verifica che l'immagine di input esista
if [ ! -f "$INPUT_IMAGE" ]; then
    print_error "Immagine $INPUT_IMAGE non trovata. Specifica un'immagine esistente."
fi

# Crea directory temporanea e di output
mkdir -p "$TEMP_DIR"
mkdir -p "$OUTPUT_DIR"

print_message "Generazione favicon e icone da $INPUT_IMAGE..."

# Genera favicon.ico (dimensioni multiple)
print_message "Generazione favicon.ico..."
convert "$INPUT_IMAGE" -background transparent \
    \( -clone 0 -resize 16x16 \) \
    \( -clone 0 -resize 32x32 \) \
    \( -clone 0 -resize 48x48 \) \
    \( -clone 0 -resize 64x64 \) \
    -delete 0 -alpha on "$OUTPUT_DIR/favicon.ico"

# Genera icone PNG per varie dimensioni
for size in 16 32 48 64 96 128 192 256 512; do
    print_message "Generazione icona ${size}x${size}..."
    convert "$INPUT_IMAGE" -background transparent -resize "${size}x${size}" "$OUTPUT_DIR/favicon-${size}x${size}.png"
done

# Genera icona per Apple Touch
print_message "Generazione icona Apple Touch..."
convert "$INPUT_IMAGE" -background transparent -resize "180x180" "$OUTPUT_DIR/apple-touch-icon.png"

# Genera icona per Android Chrome
print_message "Generazione icona Android Chrome..."
convert "$INPUT_IMAGE" -background transparent -resize "192x192" "$OUTPUT_DIR/android-chrome-192x192.png"
convert "$INPUT_IMAGE" -background transparent -resize "512x512" "$OUTPUT_DIR/android-chrome-512x512.png"

# Genera manifest.json per PWA
print_message "Generazione manifest.json..."
cat > "$OUTPUT_DIR/site.webmanifest" << EOF
{
    "name": "M4Bot",
    "short_name": "M4Bot",
    "icons": [
        {
            "src": "/static/images/icons/android-chrome-192x192.png",
            "sizes": "192x192",
            "type": "image/png"
        },
        {
            "src": "/static/images/icons/android-chrome-512x512.png",
            "sizes": "512x512",
            "type": "image/png"
        }
    ],
    "theme_color": "#ffffff",
    "background_color": "#ffffff",
    "display": "standalone"
}
EOF

# Pulizia
rm -rf "$TEMP_DIR"

print_success "Favicon e icone generate con successo in $OUTPUT_DIR"
print_message "Aggiungi questi tag al tuo HTML per includere le icone:"
echo -e "${YELLOW}<link rel=\"apple-touch-icon\" sizes=\"180x180\" href=\"/static/images/icons/apple-touch-icon.png\">"
echo "<link rel=\"icon\" type=\"image/png\" sizes=\"32x32\" href=\"/static/images/icons/favicon-32x32.png\">"
echo "<link rel=\"icon\" type=\"image/png\" sizes=\"16x16\" href=\"/static/images/icons/favicon-16x16.png\">"
echo "<link rel=\"manifest\" href=\"/static/images/icons/site.webmanifest\">"
echo "<link rel=\"shortcut icon\" href=\"/static/images/icons/favicon.ico\">${NC}" 