#!/bin/bash
# Script per scaricare le risorse web esterne per M4Bot

# Colori per l'output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}Scaricamento risorse web per M4Bot...${NC}"

# Directory di destinazione
STATIC_DIR="web/static"
FONTS_DIR="$STATIC_DIR/fonts"
CSS_DIR="$STATIC_DIR/css"
JS_DIR="$STATIC_DIR/js"
WEBFONTS_DIR="$STATIC_DIR/webfonts"

# Crea le directory se non esistono
mkdir -p "$FONTS_DIR" "$CSS_DIR" "$JS_DIR" "$WEBFONTS_DIR"

# Directory temporanea
TMP_DIR=$(mktemp -d)

# Funzione per scaricare un file
download_file() {
    local url=$1
    local dest=$2
    echo -e "${YELLOW}Scaricamento $(basename "$dest")...${NC}"
    wget -q "$url" -O "$dest" || { 
        echo -e "${RED}Errore durante il download di $(basename "$dest")${NC}"
        return 1
    }
    echo -e "${GREEN}$(basename "$dest") scaricato con successo${NC}"
    return 0
}

# Scarica Font Awesome
echo -e "${BLUE}Scaricamento Font Awesome...${NC}"
FONTAWESOME_VERSION="6.2.1" # Versione attualmente utilizzata nel progetto
FONTAWESOME_URL="https://use.fontawesome.com/releases/v$FONTAWESOME_VERSION/fontawesome-free-$FONTAWESOME_VERSION-web.zip"

download_file "$FONTAWESOME_URL" "$TMP_DIR/fontawesome.zip"
if [ $? -eq 0 ]; then
    echo -e "${YELLOW}Estrazione Font Awesome...${NC}"
    unzip -q "$TMP_DIR/fontawesome.zip" -d "$TMP_DIR"
    
    echo -e "${YELLOW}Copia dei file CSS di Font Awesome...${NC}"
    cp "$TMP_DIR/fontawesome-free-$FONTAWESOME_VERSION-web/css/all.min.css" "$CSS_DIR/"
    
    echo -e "${YELLOW}Copia dei webfonts di Font Awesome...${NC}"
    cp -r "$TMP_DIR/fontawesome-free-$FONTAWESOME_VERSION-web/webfonts/"* "$WEBFONTS_DIR/"
    
    echo -e "${GREEN}Font Awesome installato con successo${NC}"
else
    echo -e "${RED}Impossibile scaricare Font Awesome, continuo con le altre risorse${NC}"
fi

# Scarica Bootstrap
echo -e "${BLUE}Scaricamento Bootstrap...${NC}"
BOOTSTRAP_VERSION="5.2.3" # Versione attualmente utilizzata nel progetto
BOOTSTRAP_CSS_URL="https://cdn.jsdelivr.net/npm/bootstrap@$BOOTSTRAP_VERSION/dist/css/bootstrap.min.css"
BOOTSTRAP_JS_URL="https://cdn.jsdelivr.net/npm/bootstrap@$BOOTSTRAP_VERSION/dist/js/bootstrap.bundle.min.js"

download_file "$BOOTSTRAP_CSS_URL" "$CSS_DIR/bootstrap.min.css"
download_file "$BOOTSTRAP_JS_URL" "$JS_DIR/bootstrap.bundle.min.js"

# Scarica Chart.js
echo -e "${BLUE}Scaricamento Chart.js...${NC}"
CHARTJS_URL="https://cdn.jsdelivr.net/npm/chart.js"
download_file "$CHARTJS_URL" "$JS_DIR/chart.min.js"

# Scarica jQuery
echo -e "${BLUE}Scaricamento jQuery...${NC}"
JQUERY_VERSION="3.6.3" # Versione attualmente utilizzata nel progetto
JQUERY_URL="https://code.jquery.com/jquery-$JQUERY_VERSION.min.js"
download_file "$JQUERY_URL" "$JS_DIR/jquery.min.js"

# Scarica Google Fonts
echo -e "${BLUE}Scaricamento Google Fonts (Roboto)...${NC}"
GOOGLE_FONTS_URL="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap"
FONTS_CSS="$CSS_DIR/google-fonts.css"

wget -q --header="User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36" "$GOOGLE_FONTS_URL" -O "$FONTS_CSS"

if [ $? -eq 0 ]; then
    echo -e "${YELLOW}Estrazione URL dei font...${NC}"
    FONT_URLS=$(grep -o "https://fonts.gstatic.com/[^)]*" "$FONTS_CSS")
    
    for url in $FONT_URLS; do
        FONT_FILENAME=$(basename "$url")
        download_file "$url" "$FONTS_DIR/$FONT_FILENAME"
        
        # Sostituisci gli URL nel CSS con percorsi locali
        sed -i "s|$url|../fonts/$FONT_FILENAME|g" "$FONTS_CSS"
    done
    
    echo -e "${GREEN}Google Fonts scaricati con successo${NC}"
else
    echo -e "${RED}Impossibile scaricare Google Fonts, continuo con le altre risorse${NC}"
fi

# Aggiorna il template base per utilizzare le risorse locali
echo -e "${BLUE}Aggiornamento del template base per utilizzare le risorse locali...${NC}"

# Crea un file CSS aggiuntivo per gestire le icone in modo coerente
echo -e "${YELLOW}Creazione del file icons-offline.css...${NC}"
cat > "$CSS_DIR/icons-offline.css" << EOF
/* Integrazioni per icone offline - M4Bot */

/* Fix percorsi Font Awesome */
@font-face {
    font-family: 'Font Awesome 5 Free';
    font-style: normal;
    font-weight: 900;
    font-display: block;
    src: url("../webfonts/fa-solid-900.woff2") format("woff2"),
         url("../webfonts/fa-solid-900.woff") format("woff");
}

@font-face {
    font-family: 'Font Awesome 5 Free';
    font-style: normal;
    font-weight: 400;
    font-display: block;
    src: url("../webfonts/fa-regular-400.woff2") format("woff2"),
         url("../webfonts/fa-regular-400.woff") format("woff");
}

@font-face {
    font-family: 'Font Awesome 5 Brands';
    font-style: normal;
    font-weight: 400;
    font-display: block;
    src: url("../webfonts/fa-brands-400.woff2") format("woff2"),
         url("../webfonts/fa-brands-400.woff") format("woff");
}

/* Classi di supporto per le icone */
.icon-pulse {
    animation: icon-pulse 2s infinite;
}

.icon-spin {
    animation: icon-spin 2s linear infinite;
}

.icon-bounce {
    animation: icon-bounce 2s ease infinite;
}

@keyframes icon-pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.1); }
    100% { transform: scale(1); }
}

@keyframes icon-spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

@keyframes icon-bounce {
    0%, 100% {
        transform: translateY(0);
    }
    50% {
        transform: translateY(-5px);
    }
}
EOF

# Pulisci
rm -rf "$TMP_DIR"

echo -e "${GREEN}Risorse web scaricate e configurate con successo!${NC}"
echo -e "${YELLOW}Nota: Per utilizzare le risorse offline, modifica il file base.html${NC}"
echo -e "${YELLOW}Sostituisci i riferimenti CDN con i percorsi locali seguenti:${NC}"
echo -e "${YELLOW}  - Bootstrap CSS: {{ url_for('static', filename='css/bootstrap.min.css') }}${NC}"
echo -e "${YELLOW}  - Font Awesome: {{ url_for('static', filename='css/all.min.css') }}${NC}"
echo -e "${YELLOW}  - Google Fonts: {{ url_for('static', filename='css/google-fonts.css') }}${NC}"
echo -e "${YELLOW}  - jQuery: {{ url_for('static', filename='js/jquery.min.js') }}${NC}"
echo -e "${YELLOW}  - Bootstrap JS: {{ url_for('static', filename='js/bootstrap.bundle.min.js') }}${NC}"
echo -e "${YELLOW}  - Chart.js: {{ url_for('static', filename='js/chart.min.js') }}${NC}" 