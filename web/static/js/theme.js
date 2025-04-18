/**
 * M4Bot - Theme Manager 2.0
 * Sistema avanzato per gestione temi chiari/scuri con rilevamento automatico,
 * transizioni fluide e memorizzazione delle preferenze.
 */

// IIFE per evitare inquinamento del global scope
(function() {
    // Costanti e definizioni configurabili
    const THEME_STORAGE_KEY = 'm4bot_theme_preference';
    const COLOR_MODE_KEY = 'data-bs-theme';
    const TRANSITION_DURATION = 300; // durata transizione in ms
    
    // Stati del tema
    const THEMES = {
        LIGHT: 'light',
        DARK: 'dark',
        AUTO: 'auto'
    };
    
    // Colori per personalizzare i meta tag
    const META_COLORS = {
        [THEMES.LIGHT]: '#ffffff',
        [THEMES.DARK]: '#121212'
    };
    
    // Riferimenti DOM
    const htmlElement = document.documentElement;
    const themeToggle = document.getElementById('darkModeToggle');
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    
    /**
     * Classe principale per gestire i temi
     */
    class ThemeManager {
        constructor() {
            this.currentTheme = THEMES.LIGHT;
            this.systemPrefersDark = false;
            this.isTransitioning = false;
        }
        
        /**
         * Inizializza il gestore dei temi
         */
        init() {
            // Rileva preferenze sistema
            this._detectSystemPreference();
            
            // Carica tema salvato
            this._loadSavedTheme();
            
            // Aggiunge event listeners
            this._setupEventListeners();
            
            // Applica tema iniziale senza transizione
            this._applyTheme(this.currentTheme, false);
            
            // Inizializza toggle switch
            this._updateToggleState();
            
            console.log('Theme Manager initialized:', {
                theme: this.currentTheme,
                systemPreference: this.systemPrefersDark ? 'dark' : 'light'
            });
        }
        
        /**
         * Rileva preferenze di sistema per il tema scuro
         */
        _detectSystemPreference() {
            const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)');
            this.systemPrefersDark = systemPrefersDark.matches;
            
            // Listener per cambiamenti nelle preferenze di sistema
            systemPrefersDark.addEventListener('change', e => {
                this.systemPrefersDark = e.matches;
                
                // Aggiorna tema se in modalità AUTO
                if (this.currentTheme === THEMES.AUTO) {
                    this._applyTheme(THEMES.AUTO);
                }
            });
        }
        
        /**
         * Carica il tema salvato dal localStorage
         */
        _loadSavedTheme() {
            try {
                const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
                if (savedTheme && Object.values(THEMES).includes(savedTheme)) {
                    this.currentTheme = savedTheme;
                } else {
                    // Default è AUTO se non c'è un tema salvato
                    this.currentTheme = THEMES.AUTO;
                }
            } catch (e) {
                console.error('Error loading saved theme:', e);
                this.currentTheme = THEMES.AUTO;
            }
        }
        
        /**
         * Configura event listeners
         */
        _setupEventListeners() {
            if (themeToggle) {
                themeToggle.addEventListener('change', () => {
                    const newTheme = themeToggle.checked ? THEMES.DARK : THEMES.LIGHT;
                    this.setTheme(newTheme);
                });
                
                // Doppio click per modalità AUTO
                themeToggle.addEventListener('dblclick', (e) => {
                    e.preventDefault();
                    this.setTheme(THEMES.AUTO);
                });
            }
            
            // Shortcut da tastiera (Alt+Shift+D per modalità scura, Alt+Shift+L per modalità chiara, Alt+Shift+A per modalità auto)
            document.addEventListener('keydown', (e) => {
                if (e.altKey && e.shiftKey) {
                    if (e.key === 'D' || e.key === 'd') {
                        this.setTheme(THEMES.DARK);
                    } else if (e.key === 'L' || e.key === 'l') {
                        this.setTheme(THEMES.LIGHT);
                    } else if (e.key === 'A' || e.key === 'a') {
                        this.setTheme(THEMES.AUTO);
                    }
                }
            });
        }
        
        /**
         * Aggiorna lo stato dello switch in base al tema corrente
         */
        _updateToggleState() {
            if (!themeToggle) return;
            
            const effectiveTheme = this._getEffectiveTheme();
            themeToggle.checked = effectiveTheme === THEMES.DARK;
            
            // Aggiunge classe per indicare modalità AUTO
            themeToggle.parentElement?.classList.toggle('auto-mode', this.currentTheme === THEMES.AUTO);
            
            // Aggiorna tooltip
            const tooltip = themeToggle.parentElement?.querySelector('.tooltip-text');
            if (tooltip) {
                tooltip.textContent = this.currentTheme === THEMES.AUTO 
                    ? 'Tema automatico (doppio click per cambiare)' 
                    : (effectiveTheme === THEMES.DARK ? 'Passa al tema chiaro' : 'Passa al tema scuro');
            }
        }
        
        /**
         * Determina il tema effettivo (risolve AUTO in LIGHT o DARK)
         */
        _getEffectiveTheme() {
            if (this.currentTheme === THEMES.AUTO) {
                return this.systemPrefersDark ? THEMES.DARK : THEMES.LIGHT;
            }
            return this.currentTheme;
        }
        
        /**
         * Applica un tema con transizione
         * @param {string} theme - Tema da applicare
         * @param {boolean} animate - Se applicare animazione (default: true)
         */
        _applyTheme(theme, animate = true) {
            if (this.isTransitioning) return;
            
            const effectiveTheme = theme === THEMES.AUTO 
                ? (this.systemPrefersDark ? THEMES.DARK : THEMES.LIGHT)
                : theme;
            
            // Se animazione richiesta
            if (animate) {
                this.isTransitioning = true;
                
                // Aggiungi classe per animazione fade-out
                document.body.classList.add('theme-transition');
                document.body.style.opacity = '0.92';
                
                // Attendi fine transizione
                setTimeout(() => {
                    // Applica il tema
                    htmlElement.setAttribute(COLOR_MODE_KEY, effectiveTheme);
                    this._updateMetaTags(effectiveTheme);
                    
                    // Animazione fade-in
                    document.body.style.opacity = '1';
                    
                    // Rimuovi classe al termine
                    setTimeout(() => {
                        document.body.classList.remove('theme-transition');
                        this.isTransitioning = false;
                    }, TRANSITION_DURATION);
                    
                }, TRANSITION_DURATION / 2);
            } else {
                // Applica senza animazione
                htmlElement.setAttribute(COLOR_MODE_KEY, effectiveTheme);
                this._updateMetaTags(effectiveTheme);
            }
            
            // Dispatch evento personalizzato
            document.dispatchEvent(new CustomEvent('themeChanged', {
                detail: {
                    theme: theme,
                    effectiveTheme: effectiveTheme
                }
            }));
        }
        
        /**
         * Aggiorna meta tag per la colorazione UI del browser
         */
        _updateMetaTags(theme) {
            if (metaThemeColor) {
                metaThemeColor.setAttribute('content', META_COLORS[theme] || META_COLORS[THEMES.LIGHT]);
            }
        }
        
        /**
         * Salva il tema nel localStorage
         */
        _saveTheme(theme) {
            try {
                localStorage.setItem(THEME_STORAGE_KEY, theme);
            } catch (e) {
                console.error('Error saving theme preference:', e);
            }
        }
        
        /**
         * API pubblica per impostare il tema
         * @param {string} theme - Tema da impostare
         */
        setTheme(theme) {
            if (!Object.values(THEMES).includes(theme)) {
                console.error('Invalid theme:', theme);
                return;
            }
            
            this.currentTheme = theme;
            this._applyTheme(theme);
            this._saveTheme(theme);
            this._updateToggleState();
            
            // Feedback visivo
            this._showFeedback(theme);
        }
        
        /**
         * Mostra un feedback visivo per il cambio tema
         */
        _showFeedback(theme) {
            // Crea elemento toast per feedback
            const toastContainer = document.querySelector('.toast-container');
            if (!toastContainer) return;
            
            const iconClass = {
                [THEMES.LIGHT]: 'fa-sun',
                [THEMES.DARK]: 'fa-moon',
                [THEMES.AUTO]: 'fa-magic'
            };
            
            const themeName = {
                [THEMES.LIGHT]: 'chiaro',
                [THEMES.DARK]: 'scuro',
                [THEMES.AUTO]: 'automatico'
            };
            
            const toastElement = document.createElement('div');
            toastElement.className = 'toast align-items-center text-white bg-primary border-0';
            toastElement.setAttribute('role', 'alert');
            toastElement.setAttribute('aria-live', 'assertive');
            toastElement.setAttribute('aria-atomic', 'true');
            
            toastElement.innerHTML = `
                <div class="d-flex">
                    <div class="toast-body">
                        <i class="fas ${iconClass[theme] || 'fa-circle'} me-2"></i>
                        Tema ${themeName[theme] || theme} attivato
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
            `;
            
            toastContainer.appendChild(toastElement);
            const toast = new bootstrap.Toast(toastElement, {
                animation: true,
                autohide: true,
                delay: 2000
            });
            
            toast.show();
            
            // Rimuovi elemento dopo che è nascosto
            toastElement.addEventListener('hidden.bs.toast', () => {
                toastElement.remove();
            });
        }
        
        /**
         * Alterna tra tema chiaro e scuro
         */
        toggleTheme() {
            const newTheme = this._getEffectiveTheme() === THEMES.DARK ? THEMES.LIGHT : THEMES.DARK;
            this.setTheme(newTheme);
        }
    }
    
    // Crea e inizializza il theme manager quando il DOM è pronto
    document.addEventListener('DOMContentLoaded', () => {
        window.themeManager = new ThemeManager();
        window.themeManager.init();
        
        // Espone metodo globale per toggle tema
        window.toggleTheme = () => window.themeManager.toggleTheme();
    });
    
    // Aggiungi stili CSS per transizione tema
    const style = document.createElement('style');
    style.textContent = `
        .theme-transition {
            transition: opacity ${TRANSITION_DURATION}ms ease;
        }
        
        .switch .auto-mode .slider {
            background: linear-gradient(135deg, #5e45e2, #34c3ff);
        }
        
        @media (prefers-reduced-motion: reduce) {
            .theme-transition {
                transition: none;
            }
        }
    `;
    document.head.appendChild(style);
})(); 