# Aggiungi questa sezione prima di start_services()

# Funzione per impostare i permessi corretti sui file eseguibili
setup_permissions() {
    print_message "Impostazione dei permessi corretti sui file eseguibili..."
    
    # Imposta permessi eseguibili su script principali
    chmod +x "$BOT_DIR/m4bot.py" || print_warning "Impossibile impostare i permessi su m4bot.py"
    chmod +x "$WEB_DIR/app.py" || print_warning "Impossibile impostare i permessi su app.py"
    
    # Imposta permessi su tutti gli script nella directory scripts
    if [ -d "$SCRIPTS_DIR" ]; then
        find "$SCRIPTS_DIR" -type f -name "*.sh" -exec chmod +x {} \; || print_warning "Impossibile impostare i permessi su alcuni script"
        print_message "Permessi impostati su tutti gli script nella directory scripts/"
    else
        print_warning "Directory scripts/ non trovata"
    fi
    
    # Imposta permessi sui script di gestione
    chmod +x /usr/local/bin/m4bot-* 2>/dev/null || print_warning "Impossibile impostare i permessi su script di gestione"
    
    # Assicurati che le directory abbiano i permessi corretti
    chown -R m4bot:m4bot "$INSTALL_DIR" || print_warning "Impossibile impostare la proprietà delle directory"
    chmod -R 755 "$BOT_DIR" "$WEB_DIR" || print_warning "Impossibile impostare i permessi sulle directory"
    
    # Imposta permessi più restrittivi su file sensibili
    if [ -f "$INSTALL_DIR/.env" ]; then
        chmod 600 "$INSTALL_DIR/.env" || print_warning "Impossibile impostare i permessi sul file .env"
    fi
    
    print_success "Permessi impostati correttamente"
}

# Funzione per scaricare e configurare le risorse web
setup_web_assets() {
    print_message "Download e configurazione risorse web..."
    
    # Directory di destinazione
    STATIC_DIR="$INSTALL_DIR/web/static"
    FONTS_DIR="$STATIC_DIR/fonts"
    CSS_DIR="$STATIC_DIR/css"
    JS_DIR="$STATIC_DIR/js"
    WEBFONTS_DIR="$STATIC_DIR/webfonts"
    CUSTOM_DIR="$INSTALL_DIR/web/templates/custom"
    
    # Crea le directory se non esistono
    mkdir -p "$FONTS_DIR" "$CSS_DIR" "$JS_DIR" "$WEBFONTS_DIR" "$CUSTOM_DIR"
    
    # Directory temporanea
    TMP_DIR=$(mktemp -d)
    
    # Funzione per scaricare un file
    download_file() {
        local url=$1
        local dest=$2
        print_message "Scaricamento $(basename "$dest")..."
        wget -q "$url" -O "$dest" || { 
            print_warning "Errore durante il download di $(basename "$dest")"
            return 1
        }
        print_success "$(basename "$dest") scaricato con successo"
        return 0
    }
    
    # Scarica Font Awesome
    print_message "Scaricamento Font Awesome..."
    FONTAWESOME_VERSION="6.2.1"
    FONTAWESOME_URL="https://use.fontawesome.com/releases/v$FONTAWESOME_VERSION/fontawesome-free-$FONTAWESOME_VERSION-web.zip"
    
    download_file "$FONTAWESOME_URL" "$TMP_DIR/fontawesome.zip"
    if [ $? -eq 0 ]; then
        print_message "Estrazione Font Awesome..."
        unzip -q "$TMP_DIR/fontawesome.zip" -d "$TMP_DIR"
        
        print_message "Copia dei file CSS di Font Awesome..."
        cp "$TMP_DIR/fontawesome-free-$FONTAWESOME_VERSION-web/css/all.min.css" "$CSS_DIR/"
        
        print_message "Copia dei webfonts di Font Awesome..."
        cp -r "$TMP_DIR/fontawesome-free-$FONTAWESOME_VERSION-web/webfonts/"* "$WEBFONTS_DIR/"
        
        print_success "Font Awesome installato con successo"
    else
        print_warning "Impossibile scaricare Font Awesome, continuo con le altre risorse"
    fi
    
    # Scarica Bootstrap
    print_message "Scaricamento Bootstrap..."
    BOOTSTRAP_VERSION="5.2.3"
    BOOTSTRAP_CSS_URL="https://cdn.jsdelivr.net/npm/bootstrap@$BOOTSTRAP_VERSION/dist/css/bootstrap.min.css"
    BOOTSTRAP_JS_URL="https://cdn.jsdelivr.net/npm/bootstrap@$BOOTSTRAP_VERSION/dist/js/bootstrap.bundle.min.js"
    
    download_file "$BOOTSTRAP_CSS_URL" "$CSS_DIR/bootstrap.min.css"
    download_file "$BOOTSTRAP_JS_URL" "$JS_DIR/bootstrap.bundle.min.js"
    
    # Scarica Chart.js
    print_message "Scaricamento Chart.js..."
    CHARTJS_URL="https://cdn.jsdelivr.net/npm/chart.js"
    download_file "$CHARTJS_URL" "$JS_DIR/chart.min.js"
    
    # Scarica jQuery
    print_message "Scaricamento jQuery..."
    JQUERY_VERSION="3.6.3"
    JQUERY_URL="https://code.jquery.com/jquery-$JQUERY_VERSION.min.js"
    download_file "$JQUERY_URL" "$JS_DIR/jquery.min.js"
    
    # Scarica Google Fonts
    print_message "Scaricamento Google Fonts (Roboto)..."
    GOOGLE_FONTS_URL="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&display=swap"
    FONTS_CSS="$CSS_DIR/google-fonts.css"
    
    wget -q --header="User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36" "$GOOGLE_FONTS_URL" -O "$FONTS_CSS"
    
    if [ $? -eq 0 ]; then
        print_message "Estrazione URL dei font..."
        FONT_URLS=$(grep -o "https://fonts.gstatic.com/[^)]*" "$FONTS_CSS")
        
        for url in $FONT_URLS; do
            FONT_FILENAME=$(basename "$url")
            download_file "$url" "$FONTS_DIR/$FONT_FILENAME"
            
            # Sostituisci gli URL nel CSS con percorsi locali
            sed -i "s|$url|../fonts/$FONT_FILENAME|g" "$FONTS_CSS"
        done
        
        print_success "Google Fonts scaricati con successo"
    else
        print_warning "Impossibile scaricare Google Fonts, continuo con le altre risorse"
    fi
    
    # Crea un file CSS aggiuntivo per gestire le icone in modo coerente
    print_message "Creazione del file icons-offline.css..."
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
    
    # Creazione e configurazione favicon
    print_message "Creazione e configurazione favicon..."
    
    # Verifica se ImageMagick è installato
    if command -v convert &> /dev/null; then
        # Crea un'icona semplice con un robot
        print_message "Creazione del favicon..."
        convert -size 256x256 xc:transparent \
            -fill "#6a5bc2" -draw "circle 128,128 128,228" \
            -fill white -draw "circle 90,100 90,120" \
            -fill white -draw "circle 166,100 166,120" \
            -fill white -draw "roundrectangle 68,150 188,175 10,10" \
            -fill white -draw "rectangle 80,175 100,215" \
            -fill white -draw "rectangle 156,175 176,215" \
            "$STATIC_DIR/img/favicon.png"
        
        # Crea diverse dimensioni per diversi dispositivi
        print_message "Creazione favicon in diverse dimensioni..."
        convert "$STATIC_DIR/img/favicon.png" -resize 16x16 "$STATIC_DIR/img/favicon-16x16.png"
        convert "$STATIC_DIR/img/favicon.png" -resize 32x32 "$STATIC_DIR/img/favicon-32x32.png"
        convert "$STATIC_DIR/img/favicon.png" -resize 48x48 "$STATIC_DIR/img/favicon-48x48.png"
        convert "$STATIC_DIR/img/favicon.png" -resize 192x192 "$STATIC_DIR/img/android-chrome-192x192.png"
        convert "$STATIC_DIR/img/favicon.png" -resize 512x512 "$STATIC_DIR/img/android-chrome-512x512.png"
        convert "$STATIC_DIR/img/favicon.png" -resize 180x180 "$STATIC_DIR/img/apple-touch-icon.png"
        
        # Crea il favicon.ico (combina 16x16, 32x32 e 48x48)
        convert "$STATIC_DIR/img/favicon-16x16.png" "$STATIC_DIR/img/favicon-32x32.png" "$STATIC_DIR/img/favicon-48x48.png" "$STATIC_DIR/img/favicon.ico"
        
        print_success "Favicon creato con successo"
    else
        # Creazione di un favicon SVG semplice se ImageMagick non è disponibile
        print_message "ImageMagick non è disponibile, creazione di un favicon SVG semplice..."
        
        mkdir -p "$STATIC_DIR/img"
        cat > "$STATIC_DIR/img/favicon.svg" << EOF
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <circle cx="50" cy="50" r="50" fill="#6a5bc2"/>
  <text x="50" y="65" font-family="Arial" font-size="50" text-anchor="middle" fill="white">M4</text>
</svg>
EOF
        
        print_success "Favicon SVG creato con successo"
    fi
    
    # Creazione del file per i link ai favicon nell'head
    print_message "Creazione dei link ai favicon..."
    cat > "$CUSTOM_DIR/favicon-links.html" << EOF
<!-- Favicon link tags -->
<link rel="icon" type="image/svg+xml" href="{{ url_for('static', filename='img/favicon.svg') }}">
<link rel="icon" type="image/png" sizes="32x32" href="{{ url_for('static', filename='img/favicon-32x32.png') }}">
<link rel="icon" type="image/png" sizes="16x16" href="{{ url_for('static', filename='img/favicon-16x16.png') }}">
<link rel="apple-touch-icon" sizes="180x180" href="{{ url_for('static', filename='img/apple-touch-icon.png') }}">
<link rel="manifest" href="{{ url_for('static', filename='site.webmanifest') }}">
EOF

    # Creazione del file manifest per PWA
    print_message "Creazione del file manifest per PWA..."
    cat > "$STATIC_DIR/site.webmanifest" << EOF
{
    "name": "M4Bot",
    "short_name": "M4Bot",
    "icons": [
        {
            "src": "/static/img/android-chrome-192x192.png",
            "sizes": "192x192",
            "type": "image/png"
        },
        {
            "src": "/static/img/android-chrome-512x512.png",
            "sizes": "512x512",
            "type": "image/png"
        }
    ],
    "theme_color": "#6a5bc2",
    "background_color": "#ffffff",
    "display": "standalone"
}
EOF
    
    # Creazione del template base offline
    print_message "Creazione del template base offline..."
    cat > "$INSTALL_DIR/web/templates/base_offline.html" << EOF
<!DOCTYPE html>
<html lang="it" data-bs-theme="light">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}M4Bot{% endblock %}</title>
    
    <!-- Bootstrap CSS (locale) -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/bootstrap.min.css') }}">
    
    <!-- Font Awesome (locale) -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/all.min.css') }}">
    
    <!-- Google Fonts (locale) -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/google-fonts.css') }}">
    
    <!-- Favicon -->
    {% include 'custom/favicon-links.html' ignore missing %}
    
    <!-- Custom CSS -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/icons.css') }}">
    <link rel="stylesheet" href="{{ url_for('static', filename='css/icons-offline.css') }}">
    
    {% block head %}{% endblock %}
    {% block extra_css %}{% endblock %}
</head>
<body>
    <!-- Navbar -->
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
        <div class="container">
            <a class="navbar-brand" href="{{ url_for('index') }}">
                <img src="{{ url_for('static', filename='img/logo.png') }}" alt="M4Bot Logo" height="30">
                M4Bot
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav me-auto">
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'index' %}active{% endif %}" href="{{ url_for('index') }}">
                            <i class="fas fa-home nav-icon"></i>Home
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'features' %}active{% endif %}" href="{{ url_for('features') }}">
                            <i class="fas fa-star nav-icon"></i>Funzionalità
                        </a>
                    </li>
                    {% if current_user.is_authenticated %}
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'dashboard' %}active{% endif %}" href="{{ url_for('dashboard') }}">
                            <i class="fas fa-tachometer-alt nav-icon"></i>Dashboard
                        </a>
                    </li>
                    {% endif %}
                </ul>
                
                <ul class="navbar-nav">
                    {% if current_user.is_authenticated %}
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" id="userDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="fas fa-user-circle me-1"></i> {{ current_user.username }}
                        </a>
                        <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="userDropdown">
                            <li><a class="dropdown-item" href="{{ url_for('dashboard') }}"><i class="fas fa-tachometer-alt me-2"></i>Dashboard</a></li>
                            <li><a class="dropdown-item" href="#"><i class="fas fa-user-cog me-2"></i>Profilo</a></li>
                            {% if current_user.is_admin %}
                            <li><a class="dropdown-item" href="https://control.m4bot.it"><i class="fas fa-server me-2"></i>Controllo Server</a></li>
                            {% endif %}
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item" href="{{ url_for('logout') }}"><i class="fas fa-sign-out-alt me-2"></i>Logout</a></li>
                        </ul>
                    </li>
                    {% else %}
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'login' %}active{% endif %}" href="{{ url_for('login') }}">
                            <i class="fas fa-sign-in-alt me-1"></i>Accedi
                        </a>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link {% if request.endpoint == 'register' %}active{% endif %}" href="{{ url_for('register') }}">
                            <i class="fas fa-user-plus me-1"></i>Registrati
                        </a>
                    </li>
                    {% endif %}
                    
                    <!-- Language Selector -->
                    <li class="nav-item dropdown ms-2">
                        <a class="nav-link dropdown-toggle" href="#" id="languageDropdown" role="button" data-bs-toggle="dropdown">
                            <i class="fas fa-globe me-1"></i> {{ current_language_name }}
                        </a>
                        <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="languageDropdown">
                            {% for code, name in available_languages.items() %}
                            <li><a class="dropdown-item {% if current_language == code %}active{% endif %}" href="?lang={{ code }}"><i class="fas fa-check me-1 {% if current_language != code %}invisible{% endif %}"></i>{{ name }}</a></li>
                            {% endfor %}
                        </ul>
                    </li>
                    
                    <li class="nav-item ms-2">
                        <div class="form-check form-switch pt-2">
                            <input class="form-check-input" type="checkbox" id="darkModeToggle">
                            <label class="form-check-label text-light" for="darkModeToggle"><i class="fas fa-moon"></i></label>
                        </div>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <div class="container py-4">
        {% block content %}{% endblock %}
    </div>

    <!-- Footer -->
    <footer class="bg-dark text-white py-4 mt-5">
        <div class="container">
            <div class="row">
                <div class="col-md-4">
                    <h5><i class="fas fa-robot me-2"></i>M4Bot</h5>
                    <p>Il bot più completo e personalizzabile per Kick.com</p>
                </div>
                <div class="col-md-4">
                    <h5><i class="fas fa-link me-2"></i>Link Utili</h5>
                    <ul class="list-unstyled">
                        <li><a href="{{ url_for('index') }}" class="text-decoration-none text-white-50"><i class="fas fa-home me-2"></i>Home</a></li>
                        <li><a href="{{ url_for('features') }}" class="text-decoration-none text-white-50"><i class="fas fa-star me-2"></i>Funzionalità</a></li>
                        <li><a href="#" class="text-decoration-none text-white-50"><i class="fas fa-book me-2"></i>Documentazione</a></li>
                        <li><a href="#" class="text-decoration-none text-white-50"><i class="fas fa-headset me-2"></i>Contatti</a></li>
                    </ul>
                </div>
                <div class="col-md-4">
                    <h5><i class="fas fa-users me-2"></i>Community</h5>
                    <div class="d-flex">
                        <a href="#" class="text-decoration-none text-white-50 me-3 social-icon social-icon-twitter"><i class="fab fa-twitter fa-lg"></i></a>
                        <a href="#" class="text-decoration-none text-white-50 me-3 social-icon social-icon-discord"><i class="fab fa-discord fa-lg"></i></a>
                        <a href="#" class="text-decoration-none text-white-50 me-3 social-icon social-icon-github"><i class="fab fa-github fa-lg"></i></a>
                    </div>
                </div>
            </div>
            <hr>
            <div class="text-center">
                <p class="mb-0"><i class="far fa-copyright me-1"></i>2023 M4Bot. Tutti i diritti riservati.</p>
            </div>
        </div>
    </footer>

    <!-- jQuery (locale) -->
    <script src="{{ url_for('static', filename='js/jquery.min.js') }}"></script>
    
    <!-- Bootstrap JS (locale) -->
    <script src="{{ url_for('static', filename='js/bootstrap.bundle.min.js') }}"></script>
    
    <!-- Chart.js (locale) -->
    <script src="{{ url_for('static', filename='js/chart.min.js') }}"></script>
    
    <!-- Custom JS -->
    <script src="{{ url_for('static', filename='js/main.js') }}"></script>
    {% block scripts %}{% endblock %}
    {% block extra_js %}{% endblock %}
</body>
</html>
EOF
    
    # Chiedi se utilizzare il template offline
    print_message "Vuoi utilizzare il template offline per l'applicazione? (s/n)"
    read -p "" USE_OFFLINE
    if [[ "$USE_OFFLINE" == "s" || "$USE_OFFLINE" == "S" ]]; then
        cp "$INSTALL_DIR/web/templates/base_offline.html" "$INSTALL_DIR/web/templates/base.html"
        print_success "Template base sostituito con la versione offline"
    else
        print_message "Template base non modificato"
    fi
    
    # Pulisci
    rm -rf "$TMP_DIR"
    
    print_success "Risorse web configurate con successo"
}

# Funzione principale
main() {
    clear
    check_root
    confirm_installation
    
    update_system
    install_dependencies
    create_system_user
    setup_database
    initialize_database
    setup_repository
    setup_python_env
    setup_nginx
    setup_ssl
    setup_systemd_services
    setup_management_scripts
    setup_env_file
    setup_permissions    # Imposta permessi corretti sui file eseguibili
    setup_auto_repair    # Configura sistema di auto-riparazione
    setup_web_assets     # Scarica e configura le risorse web
    
    # Avvia i servizi
    start_services
    
    # Mostra le credenziali di accesso
    print_message "====================================================="
    print_message "INSTALLAZIONE COMPLETATA!"
    print_message "====================================================="
    print_message "Credenziali di accesso:"
    print_message "URL: https://$SAVED_DOMAIN"
    print_message "Username: admin"
    print_message "Password: admin123"
    print_message ""
    print_message "IMPORTANTE: Cambia la password dell'amministratore dopo il primo accesso."
    print_message "====================================================="
    print_message "Per gestire M4Bot, usa i seguenti comandi:"
    print_message "m4bot-start    - Avvia i servizi"
    print_message "m4bot-stop     - Ferma i servizi"
    print_message "m4bot-restart  - Riavvia i servizi"
    print_message "m4bot-status   - Controlla lo stato dei servizi"
    print_message "m4bot-repair   - Ripara automaticamente i servizi"
    print_message "====================================================="
    print_message "Dashboard: https://dashboard.$SAVED_DOMAIN"
    print_message "Controllo: https://control.$SAVED_DOMAIN"
    print_message "====================================================="
}

# Esegui lo script
main 