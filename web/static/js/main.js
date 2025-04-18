/**
 * M4Bot - Main JavaScript
 * Versione 2.0 con supporto avanzato per animazioni, interattività e
 * migliore gestione degli eventi utente e della reattività.
 */

// IIFE per incapsulare il codice
(function() {
    // Costanti configurabili
    const CONFIG = {
        animations: {
            enabled: true,
            duration: {
                short: 150,
                medium: 300,
                long: 500
            },
            timing: 'cubic-bezier(0.4, 0, 0.2, 1)'
        },
        sidebar: {
            collapseBreakpoint: 992, // Breakpoint per collassare sidebar (px)
            swipeThreshold: 50      // Soglia per swipe gesture (px)
        },
        scrolling: {
            smoothScroll: true,
            scrollOffset: 70,      // Offset per evitare che header copra il contenuto
            scrollSmoothing: 'smooth'
        },
        feedback: {
            enabled: true,
            haptic: true          // Vibrazione per feedback tattile
        },
        performance: {
            idleTimeout: 90000,    // 1.5 minuti in ms
            lazyLoadThreshold: 200 // Distanza in px per lazy loading 
        }
    };

    // Cache per gli elementi DOM frequentemente utilizzati
    const DOM = {
        body: document.body,
        sidebar: document.querySelector('.sidebar'),
        sidebarToggle: document.querySelector('.sidebar-toggle'),
        toTopButton: document.getElementById('to-top-button'),
        loadingOverlay: document.getElementById('loading-overlay'),
        actionFeedback: document.getElementById('action-feedback'),
        scrollElements: document.querySelectorAll('[data-scroll]'),
        parallaxElements: document.querySelectorAll('.parallax-element'),
        staggeredElements: document.querySelectorAll('.stagger-items'),
        revealElements: document.querySelectorAll('.reveal-on-scroll'),
        root: document.documentElement
    };

    // Stato dell'applicazione
    const state = {
        sidebarOpen: window.innerWidth >= CONFIG.sidebar.collapseBreakpoint,
        serverPingMs: null,
        isOnline: navigator.onLine,
        touchStartX: 0,
        touchEndX: 0,
        isIdle: false,
        isPageVisible: true,
        scrollPosition: 0,
        hasFocus: true
    };

    /**
     * Classe principale per gestire l'app
     */
    class AppManager {
        constructor() {
            this.initializeApp();
            this.setupEventListeners();
        }

        /**
         * Inizializza l'applicazione
         */
        initializeApp() {
            // Imposta lo stato iniziale della sidebar
            this.updateSidebarState(state.sidebarOpen, false);

            // Inizializza i componenti UI principali
            this.initializeUIComponents();

            // Controlla connettività
            this.updateConnectionStatus();

            // Verifica compatibilità browser avanzate
            this.checkBrowserCapabilities();

            // Polling del server ping (heartbeat)
            this.startServerPing();

            // Imposta stato responsivo
            this.handleResponsiveLayout();

            // Rimuovi loading overlay
            this.hideLoadingOverlay();

            // Inizializza lazy loading
            this.initializeLazyLoading();

            // Aggiungi detector idle
            this.setupIdleDetection();

            console.log('M4Bot App initialized successfully');
        }

        /**
         * Nasconde l'overlay di caricamento con animazione
         */
        hideLoadingOverlay() {
            if (!DOM.loadingOverlay) return;

            // Aggiungi classe per attivare animazione
            DOM.loadingOverlay.classList.add('fade-out');

            // Rimuovi dopo animazione
            setTimeout(() => {
                DOM.loadingOverlay.style.display = 'none';
                DOM.loadingOverlay.classList.remove('fade-out');
            }, CONFIG.animations.duration.medium);
        }

        /**
         * Inizializza componenti UI principali
         */
        initializeUIComponents() {
            // Inizializza tooltip bootstrap
            const tooltips = document.querySelectorAll('[data-bs-toggle="tooltip"]');
            if (tooltips.length > 0) {
                [...tooltips].map(tooltip => new bootstrap.Tooltip(tooltip));
            }

            // Inizializza popovers bootstrap
            const popovers = document.querySelectorAll('[data-bs-toggle="popover"]');
            if (popovers.length > 0) {
                [...popovers].map(popover => new bootstrap.Popover(popover));
            }

            // Attiva animazioni elementi 
            this.setupAnimations();
        }

        /**
         * Configura gestori degli eventi
         */
        setupEventListeners() {
            // Toggle sidebar
            if (DOM.sidebarToggle) {
                DOM.sidebarToggle.addEventListener('click', () => {
                    this.toggleSidebar();
                });
            }

            // Chiusura sidebar con click fuori
            document.addEventListener('click', (e) => {
                if (state.sidebarOpen && window.innerWidth < CONFIG.sidebar.collapseBreakpoint) {
                    if (DOM.sidebar && !DOM.sidebar.contains(e.target) && 
                        DOM.sidebarToggle && !DOM.sidebarToggle.contains(e.target)) {
                        this.updateSidebarState(false);
                    }
                }
            });

            // Pulsante torna in cima
            if (DOM.toTopButton) {
                DOM.toTopButton.addEventListener('click', () => {
                    this.scrollToTop();
                });
            }

            // Scroll handler
            window.addEventListener('scroll', this.handleScroll.bind(this), { passive: true });

            // Resize handler
            window.addEventListener('resize', this.debounce(() => {
                this.handleResponsiveLayout();
            }, 250));

            // Touch handlers
            document.addEventListener('touchstart', this.handleTouchStart.bind(this), { passive: true });
            document.addEventListener('touchend', this.handleTouchEnd.bind(this), { passive: true });

            // Connection status handlers
            window.addEventListener('online', this.updateConnectionStatus.bind(this));
            window.addEventListener('offline', this.updateConnectionStatus.bind(this));

            // Gestione visibilità pagina e focus
            document.addEventListener('visibilitychange', this.handleVisibilityChange.bind(this));
            window.addEventListener('focus', this.handleFocus.bind(this));
            window.addEventListener('blur', this.handleBlur.bind(this));

            // Rileva stili preferiti dall'utente
            this.detectUserPreferences();

            // Event handlers per link con hash
            document.querySelectorAll('a[href^="#"]:not([href="#"])').forEach(anchor => {
                anchor.addEventListener('click', (e) => {
                    this.handleHashLinkClick(e);
            });
        });

            // Click handler per pulsanti azione
            document.querySelectorAll('[data-action]').forEach(button => {
                button.addEventListener('click', (e) => {
                    this.handleActionButton(e);
                });
            });

            // Intercetta submit forms per validation
            document.querySelectorAll('form:not([data-novalidate])').forEach(form => {
                form.addEventListener('submit', (e) => {
                    this.handleFormSubmit(e);
                });
            });
        }

        /**
         * Gestione click su link con hash
         */
        handleHashLinkClick(e) {
            const href = e.currentTarget.getAttribute('href');
            const targetElement = document.querySelector(href);
            
            if (targetElement) {
                e.preventDefault();
                
                // Calcola offset per scorrimento
                const headerOffset = CONFIG.scrolling.scrollOffset;
                const elementPosition = targetElement.getBoundingClientRect().top;
                const offsetPosition = elementPosition + window.scrollY - headerOffset;
                
                // Scorri alla posizione
                window.scrollTo({
                    top: offsetPosition,
                    behavior: CONFIG.scrolling.scrollSmoothing
                });
                
                // Focus su elemento per a11y
                targetElement.setAttribute('tabindex', '-1');
                targetElement.focus({ preventScroll: true });
                
                // Aggiorna URL con hash
                history.pushState(null, null, href);
            }
        }

        /**
         * Gestisce il submit dei form
         */
        handleFormSubmit(e) {
            const form = e.currentTarget;
            
            // Se il form non è valido, impediamo submit
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
                
                // Aggiungi classe per attivare stile validazione
                form.classList.add('was-validated');
                
                // Trova primo elemento non valido e fai focus
                const invalidField = form.querySelector(':invalid');
                if (invalidField) {
                    invalidField.focus();
                    
                    // Feedback visivo
                    this.showFeedback('error', 'Verifica i campi evidenziati');
                }
            } else {
                if (form.hasAttribute('data-confirm')) {
                    const confirmMsg = form.getAttribute('data-confirm') || 'Sei sicuro di voler procedere?';
                    
                    if (!confirm(confirmMsg)) {
                        e.preventDefault();
                    }
                }
                
                // Disabilita form durante submit per evitare multi-submit
                if (!form.hasAttribute('data-no-disable')) {
                    const submitBtn = form.querySelector('[type="submit"]');
                    if (submitBtn) {
                        const originalText = submitBtn.innerText;
                        submitBtn.disabled = true;
                        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Elaborazione...';
                        
                        // Riabilita dopo timeout (fallback se AJAX non completa)
            setTimeout(() => {
                            submitBtn.disabled = false;
                            submitBtn.innerText = originalText;
                        }, 5000);
                    }
                }
            }
        }

        /**
         * Gestisce click sui pulsanti azione
         */
        handleActionButton(e) {
            const button = e.currentTarget;
            const action = button.getAttribute('data-action');
            
            if (!action) return;
            
            // Feedback visivo
            this.showClickFeedback(e);
            
            // Esegui azione corrispondente
            switch (action) {
                case 'toggle-sidebar':
                    this.toggleSidebar();
                    break;
                    
                case 'toggle-theme':
                    if (window.toggleTheme) window.toggleTheme();
                    break;
                    
                case 'refresh':
                    this.refreshCurrentContent();
                    break;
                    
                case 'back':
                    history.back();
                    break;
                    
                case 'toggle-notifications':
                    this.toggleNotificationsPanel();
                    break;
                    
                default:
                    // Azioni personalizzate - emetti un evento personalizzato
                    const customEvent = new CustomEvent('actionTriggered', {
                        detail: { action, element: button }
                    });
                    document.dispatchEvent(customEvent);
                    break;
            }
        }

        /**
         * Rileva preferenze utente
         */
        detectUserPreferences() {
            // Rileva preference per riduzione movimento
            const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
            
            const handleMotionPreference = (e) => {
                CONFIG.animations.enabled = !e.matches;
                document.documentElement.classList.toggle('reduced-motion', e.matches);
            };
            
            // Imposta valore iniziale
            handleMotionPreference(prefersReducedMotion);
            
            // Aggiungi listener per cambiamenti
            prefersReducedMotion.addEventListener('change', handleMotionPreference);
            
            // Rileva preferenza contrasto
            const prefersHighContrast = window.matchMedia('(prefers-contrast: more)');
            
            const handleContrastPreference = (e) => {
                document.documentElement.classList.toggle('high-contrast', e.matches);
            };
            
            // Imposta valore iniziale
            handleContrastPreference(prefersHighContrast);
            
            // Aggiungi listener per cambiamenti
            prefersHighContrast.addEventListener('change', handleContrastPreference);
        }

        /**
         * Gestisce cambio stato visibilità pagina
         */
        handleVisibilityChange() {
            state.isPageVisible = document.visibilityState === 'visible';
            
            if (state.isPageVisible) {
                // Ripristina polling per dati in tempo reale
                this.resumePolling();
            } else {
                // Sospendi polling 
                this.pausePolling();
            }
        }

        /**
         * Gestisce focus sulla finestra
         */
        handleFocus() {
            state.hasFocus = true;
            // Riprendi attività in background
            this.resumeBackgroundTasks();
        }

        /**
         * Gestisce perdita focus sulla finestra
         */
        handleBlur() {
            state.hasFocus = false;
            // Sospendi attività pesanti per risparmiare batteria
            this.pauseBackgroundTasks();
        }

        /**
         * Pausa task in background
         */
        pauseBackgroundTasks() {
            if (window.pollingIntervals) {
                Object.keys(window.pollingIntervals).forEach(key => {
                    clearInterval(window.pollingIntervals[key]);
                });
            }
        }

        /**
         * Riprende task in background
         */
        resumeBackgroundTasks() {
            // Implementazione specifica per attività da ripristinare
            this.startServerPing();
        }

        /**
         * Pausa polling dati
         */
        pausePolling() {
            if (window.pingInterval) {
                clearInterval(window.pingInterval);
            }
        }

        /**
         * Riprende polling dati
         */
        resumePolling() {
            this.startServerPing();
        }

        /**
         * Imposta detection per stato idle
         */
        setupIdleDetection() {
            // Lista eventi che resettano lo stato idle
            const resetEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart'];
            
            // Timer per stato idle
            let idleTimer = null;
            
            // Funzione per resettare timer idle
            const resetIdleTimer = () => {
                if (idleTimer) {
                    clearTimeout(idleTimer);
                }
                
                // Se era in stato idle, ripristina
                if (state.isIdle) {
                    state.isIdle = false;
                    this.handleActiveStateChange(true);
                }
                
                // Imposta nuovo timer
                idleTimer = setTimeout(() => {
                    state.isIdle = true;
                    this.handleActiveStateChange(false);
                }, CONFIG.performance.idleTimeout);
            };
            
            // Aggiungi listener per ogni evento che resetta lo stato idle
            resetEvents.forEach(eventName => {
                document.addEventListener(eventName, resetIdleTimer, { passive: true });
            });
            
            // Inizializza timer
            resetIdleTimer();
        }

        /**
         * Gestisce cambio di stato attivo/idle
         */
        handleActiveStateChange(isActive) {
            if (isActive) {
                // L'utente è tornato attivo
                DOM.body.classList.remove('user-idle');
                
                // Riprendi attività intensive
                this.resumeIntensiveTasks();
            } else {
                // L'utente è diventato idle
                DOM.body.classList.add('user-idle');
                
                // Sospendi attività intensive per preservare CPU e batteria
                this.suspendIntensiveTasks();
            }
        }

        /**
         * Sospende attività intensive
         */
        suspendIntensiveTasks() {
            // Sospendi animazioni e polling frequente
            document.documentElement.classList.add('reduce-animations');
            
            // Sospendi worker e task di background
            if (window.backgroundWorkers) {
                Object.values(window.backgroundWorkers).forEach(worker => {
                    worker.postMessage({ action: 'suspend' });
                });
            }
        }

        /**
         * Riprende attività intensive
         */
        resumeIntensiveTasks() {
            // Ripristina animazioni
            document.documentElement.classList.remove('reduce-animations');
            
            // Ripristina worker e task di background
            if (window.backgroundWorkers) {
                Object.values(window.backgroundWorkers).forEach(worker => {
                    worker.postMessage({ action: 'resume' });
                });
            }
        }

        /**
         * Inizializza lazy loading per immagini e contenuti
         */
        initializeLazyLoading() {
            // Utilizza IntersectionObserver se disponibile
            if (!('IntersectionObserver' in window)) return;
            
            // Osserva immagini con attributo data-src
            const lazyImages = document.querySelectorAll('img[data-src], video[data-src]');
            if (lazyImages.length > 0) {
                const imageObserver = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            const element = entry.target;
                            
                            element.src = element.getAttribute('data-src');
                            
                            if (element.getAttribute('data-srcset')) {
                                element.srcset = element.getAttribute('data-srcset');
                            }
                            
                            element.classList.add('loaded');
                            imageObserver.unobserve(element);
                        }
                    });
                }, {
                    rootMargin: `${CONFIG.performance.lazyLoadThreshold}px 0px`,
                    threshold: 0.01
                });
                
                lazyImages.forEach(image => {
                    imageObserver.observe(image);
                });
            }
            
            // Osserva elementi con contenuto lazy (iframes, componenti pesanti)
            const lazyContents = document.querySelectorAll('[data-lazy-load]');
            if (lazyContents.length > 0) {
                const contentObserver = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            const element = entry.target;
                            const contentType = element.getAttribute('data-lazy-load');
                            
                            switch(contentType) {
                                case 'iframe':
                                    this.loadLazyIframe(element);
                                    break;
                                case 'component':
                                    this.loadLazyComponent(element);
                                    break;
                                default:
                                    console.warn('Unknown lazy load type:', contentType);
                            }
                            
                            contentObserver.unobserve(element);
                        }
                    });
                }, {
                    rootMargin: `${CONFIG.performance.lazyLoadThreshold}px 0px`,
                    threshold: 0.01
                });
                
                lazyContents.forEach(content => {
                    contentObserver.observe(content);
                });
            }
        }

        /**
         * Carica iframe in modo lazy
         */
        loadLazyIframe(container) {
            const src = container.getAttribute('data-src');
            if (!src) return;
            
            const iframe = document.createElement('iframe');
            
            // Copia attributi
            const attributes = container.getAttributeNames()
                .filter(name => name.startsWith('data-iframe-'))
                .map(name => ({
                    key: name.replace('data-iframe-', ''),
                    value: container.getAttribute(name)
                }));
            
            // Imposta src e altri attributi
            iframe.src = src;
            attributes.forEach(attr => {
                iframe.setAttribute(attr.key, attr.value);
            });
            
            // Sostituisci placeholder
            container.innerHTML = '';
            container.appendChild(iframe);
            container.classList.add('loaded');
        }

        /**
         * Carica componente in modo lazy
         */
        loadLazyComponent(container) {
            const component = container.getAttribute('data-component');
            if (!component) return;
            
            // Carica contenuto 
            fetch(`/api/components/${component}`)
                .then(response => response.text())
                .then(html => {
                    container.innerHTML = html;
                    container.classList.add('loaded');
                    
                    // Inizializza eventuali script
                    const scripts = container.querySelectorAll('script');
                    scripts.forEach(oldScript => {
                        const newScript = document.createElement('script');
                        
                        // Copia attributi
                        Array.from(oldScript.attributes)
                            .forEach(attr => newScript.setAttribute(attr.name, attr.value));
                        
                        // Copia contenuto
                        newScript.appendChild(document.createTextNode(oldScript.innerHTML));
                        
                        // Sostituisci vecchio script
                        oldScript.parentNode.replaceChild(newScript, oldScript);
                    });
                })
                .catch(error => {
                    console.error('Error loading component:', error);
                    container.innerHTML = `<div class="alert alert-danger">Errore nel caricamento del componente</div>`;
                });
        }

        /**
         * Controlla capacità del browser
         */
        checkBrowserCapabilities() {
            const capabilities = {
                webP: false,
                webGL: false,
                webWorkers: !!window.Worker,
                localStorage: !!window.localStorage,
                serviceWorker: !!navigator.serviceWorker,
                intersection: !!window.IntersectionObserver,
                touch: ('ontouchstart' in window) || (navigator.maxTouchPoints > 0),
                battery: !!navigator.getBattery,
                permissions: !!navigator.permissions,
                bluetooth: !!navigator.bluetooth,
                vibration: !!navigator.vibrate,
                share: !!navigator.share
            };
            
            // Controlla supporto WebP
            const webP = new Image();
            webP.onload = function() { capabilities.webP = (webP.width > 0) && (webP.height > 0); };
            webP.onerror = function() { capabilities.webP = false; };
            webP.src = 'data:image/webp;base64,UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAwA0JaQAA3AA/vlAAA==';
            
            // Controlla supporto WebGL
            try {
                const canvas = document.createElement('canvas');
                capabilities.webGL = !!(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'));
            } catch (e) {
                capabilities.webGL = false;
            }
            
            // Aggiungi classi CSS per feature detection
            Object.keys(capabilities).forEach(feature => {
                if (capabilities[feature]) {
                    document.documentElement.classList.add(`has-${feature}`);
                } else {
                    document.documentElement.classList.add(`no-${feature}`);
                }
            });
            
            // Salva per utilizzo futuro
            window.browserCapabilities = capabilities;
        }

        /**
         * Gestisce touch start
         */
        handleTouchStart(e) {
            state.touchStartX = e.changedTouches[0].screenX;
        }

        /**
         * Gestisce touch end
         */
        handleTouchEnd(e) {
            state.touchEndX = e.changedTouches[0].screenX;
            this.handleSwipeGesture();
        }

        /**
         * Interpreta gesture di swipe
         */
        handleSwipeGesture() {
            const distance = state.touchEndX - state.touchStartX;
            const threshold = CONFIG.sidebar.swipeThreshold;
            
            // Se siamo in modalità mobile
            if (window.innerWidth < CONFIG.sidebar.collapseBreakpoint) {
                if (distance > threshold) {
                    // Swipe da sinistra a destra -> apri sidebar
                    this.updateSidebarState(true);
                } else if (distance < -threshold && state.sidebarOpen) {
                    // Swipe da destra a sinistra -> chiudi sidebar
                    this.updateSidebarState(false);
                }
            }
        }

        /**
         * Aggiorna stato connessione
         */
        updateConnectionStatus() {
            const connectionStatus = document.querySelector('.connection-status');
            const statusIndicator = document.querySelector('.status-indicator');
            const statusText = document.querySelector('.status-text');
            
            if (!connectionStatus || !statusIndicator || !statusText) return;
            
            state.isOnline = navigator.onLine;
            
            if (state.isOnline) {
                statusIndicator.classList.remove('disconnected');
                statusIndicator.classList.add('connected');
                statusText.textContent = 'Online';
                DOM.body.classList.remove('offline-mode');
            } else {
                statusIndicator.classList.remove('connected');
                statusIndicator.classList.add('disconnected');
                statusText.textContent = 'Offline';
                DOM.body.classList.add('offline-mode');
                
                this.showFeedback('error', 'Connessione assente. Alcune funzionalità potrebbero non essere disponibili.');
            }
        }

        /**
         * Mostra feedback con toast
         */
        showFeedback(type, message) {
            // Crea elemento toast per feedback
            const toastContainer = document.querySelector('.toast-container');
            if (!toastContainer) return;
            
            const iconMap = {
                'success': 'fa-check-circle',
                'error': 'fa-exclamation-circle',
                'warning': 'fa-exclamation-triangle',
                'info': 'fa-info-circle'
            };
            
            const typeMap = {
                'success': 'bg-success',
                'error': 'bg-danger',
                'warning': 'bg-warning text-dark',
                'info': 'bg-info text-dark'
            };
            
            const toastElement = document.createElement('div');
            toastElement.className = `toast align-items-center text-white ${typeMap[type] || 'bg-primary'} border-0`;
            toastElement.setAttribute('role', 'alert');
            toastElement.setAttribute('aria-live', 'assertive');
            toastElement.setAttribute('aria-atomic', 'true');
            
            toastElement.innerHTML = `
                <div class="d-flex">
        <div class="toast-body">
                        <i class="fas ${iconMap[type] || 'fa-circle'} me-2"></i>
            ${message}
        </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
    </div>
    `;
    
            toastContainer.appendChild(toastElement);
    const toast = new bootstrap.Toast(toastElement, {
        animation: true,
        autohide: true,
                delay: 3000
    });
    
    toast.show();
    
            // Rimuovi elemento dopo che è nascosto
            toastElement.addEventListener('hidden.bs.toast', () => {
                toastElement.remove();
            });
            
            // Feedback haptic se supportato e abilitato
            if (CONFIG.feedback.haptic && 'vibrate' in navigator && type !== 'info') {
                switch (type) {
                    case 'error':
                        navigator.vibrate([100, 50, 100]);
                        break;
                    case 'warning':
                        navigator.vibrate(100);
                        break;
                    case 'success':
                        navigator.vibrate(50);
                        break;
                }
            }
        }

        /**
         * Mostra feedback visivo per click
         */
        showClickFeedback(e) {
            if (!CONFIG.feedback.enabled || !DOM.actionFeedback) return;
            
            const x = e.clientX;
            const y = e.clientY;
            
            // Posiziona feedback
            DOM.actionFeedback.style.left = `${x}px`;
            DOM.actionFeedback.style.top = `${y}px`;
            
            // Rimuovi classe precedente
            DOM.actionFeedback.classList.remove('animate');
            
            // Force reflow
            void DOM.actionFeedback.offsetWidth;
            
            // Attiva animazione
            DOM.actionFeedback.classList.add('animate');
        }

        /**
         * Avvia ping periodico al server
         */
        startServerPing() {
            // Cancella eventuale interval precedente
            if (window.pingInterval) {
                clearInterval(window.pingInterval);
            }
            
            // Funzione per eseguire ping
            const pingServer = async () => {
                if (!state.isOnline || !state.isPageVisible) return;
                
                try {
                    const startTime = performance.now();
                    const response = await fetch('/api/ping', { 
                        method: 'GET',
                        headers: { 'Cache-Control': 'no-cache' },
                        credentials: 'same-origin'
                    });
                    
                    if (response.ok) {
                        const endTime = performance.now();
                        state.serverPingMs = Math.round(endTime - startTime);
                        
                        // Aggiorna UI
                        this.updatePingDisplay(state.serverPingMs);
                    } else {
                        // Server error
                        this.updatePingDisplay(null);
                    }
                } catch (error) {
                    // Connessione fallita
                    this.updatePingDisplay(null);
                }
            };
            
            // Primo ping immediato
            pingServer();
            
            // Imposta interval per ping periodico (ogni 30s)
            window.pingInterval = setInterval(pingServer, 30000);
            
            // Salva in pollingIntervals
            if (!window.pollingIntervals) {
                window.pollingIntervals = {};
            }
            window.pollingIntervals.ping = window.pingInterval;
        }

        /**
         * Aggiorna display del ping
         */
        updatePingDisplay(ping) {
            const pingElement = document.getElementById('server-ping-value');
            if (!pingElement) return;
            
            if (ping === null) {
                pingElement.textContent = '--';
                pingElement.parentElement.classList.add('text-danger');
            } else {
                pingElement.textContent = ping;
                pingElement.parentElement.classList.remove('text-danger');
                
                // Colore basato sulla latenza
                if (ping < 100) {
                    pingElement.parentElement.className = 'server-ping text-success';
                } else if (ping < 300) {
                    pingElement.parentElement.className = 'server-ping text-warning';
                } else {
                    pingElement.parentElement.className = 'server-ping text-danger';
                }
            }
        }

        /**
         * Gestisce scroll
         */
        handleScroll() {
            // Memorizza posizione
            state.scrollPosition = window.scrollY;
            
            // Gestisce pulsante torna in alto
            this.updateToTopButton();
            
            // Gestisce animazioni al scroll
            this.handleScrollAnimations();
            
            // Header hide/show
            this.handleDynamicHeader();
        }

        /**
         * Gestione header dinamico (nascondi durante scroll down)
         */
        handleDynamicHeader() {
            const header = document.querySelector('.app-status-bar');
            if (!header) return;
            
            const currentScroll = window.scrollY;
            const scrollDelta = currentScroll - (this.lastScroll || 0);
            
            // Memorizza ultima posizione
            this.lastScroll = currentScroll;
            
            // Se lo scroll è significativo
            if (Math.abs(scrollDelta) < 10) return;
            
            if (scrollDelta > 0 && currentScroll > 100) {
                // Scrolling down - nascondi header
                header.classList.add('header-hidden');
            } else {
                // Scrolling up - mostra header
                header.classList.remove('header-hidden');
            }
        }

        /**
         * Aggiorna pulsante torna in cima
         */
        updateToTopButton() {
            if (!DOM.toTopButton) return;
            
            if (window.scrollY > 300) {
                DOM.toTopButton.classList.add('visible');
            } else {
                DOM.toTopButton.classList.remove('visible');
            }
        }

        /**
         * Gestisce animazioni al scroll
         */
        handleScrollAnimations() {
            if (!CONFIG.animations.enabled) return;
            
            // Gestisci elementi reveal-on-scroll
            this.animateRevealElements();
        }

        /**
         * Anima elementi reveal
         */
        animateRevealElements() {
            if (!DOM.revealElements || !('IntersectionObserver' in window)) return;
            
            // Lazy initialize observer
            if (!this.revealObserver) {
                this.revealObserver = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            entry.target.classList.add('visible');
                            this.revealObserver.unobserve(entry.target);
                        }
                    });
                }, { 
                    threshold: 0.1 
                });
                
                // Osserva tutti gli elementi
                DOM.revealElements.forEach(el => {
                    this.revealObserver.observe(el);
                });
            }
        }

        /**
         * Imposta effetto parallax su elementi
         */
        setupParallaxElements() {
            if (!CONFIG.animations.enabled || !DOM.parallaxElements) return;
            
            const handleMouseMove = (e) => {
                const mouseX = e.clientX / window.innerWidth;
                const mouseY = e.clientY / window.innerHeight;
                
                DOM.parallaxElements.forEach(el => {
                    const speed = parseFloat(el.getAttribute('data-parallax-speed')) || 0.05;
                    const moveX = (mouseX - 0.5) * speed * 100;
                    const moveY = (mouseY - 0.5) * speed * 100;
                    
                    el.style.transform = `translate(${moveX}px, ${moveY}px)`;
                });
            };
            
            // Use debounced version for better performance
            document.addEventListener('mousemove', this.debounce(handleMouseMove, 5));
        }

        /**
         * Funzione debounce per limitare chiamate frequenti
         */
        debounce(func, wait) {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        }

        /**
         * Configura animazioni
         */
        setupAnimations() {
            // Parallax
            this.setupParallaxElements();
            
            // Inizializza animazioni stagger
            if (DOM.staggeredElements) {
                setTimeout(() => {
                    DOM.staggeredElements.forEach(el => el.classList.add('animate'));
                }, 100);
    }
}

/**
         * Aggiorna stato sidebar
         */
        updateSidebarState(isOpen, animate = true) {
            if (!DOM.sidebar) return;
            
            state.sidebarOpen = isOpen;
            
            if (isOpen) {
                if (animate) {
                    DOM.sidebar.classList.add('opening');
                }
                DOM.sidebar.classList.add('open');
                document.body.classList.add('sidebar-open');
            } else {
                if (animate) {
                    DOM.sidebar.classList.add('closing');
                }
                DOM.sidebar.classList.remove('open');
                document.body.classList.remove('sidebar-open');
            }
            
            // Rimuovi classi transizione dopo l'animazione
            if (animate) {
                setTimeout(() => {
                    DOM.sidebar.classList.remove('opening', 'closing');
                }, CONFIG.animations.duration.medium);
            }
        }

        /**
         * Toggle stato sidebar
         */
        toggleSidebar() {
            this.updateSidebarState(!state.sidebarOpen);
        }

        /**
         * Gestisce layout responsivo
         */
        handleResponsiveLayout() {
            const isDesktop = window.innerWidth >= CONFIG.sidebar.collapseBreakpoint;
            
            // Aggiorna stato sidebar basato su breakpoint
            if (isDesktop) {
                // Su desktop, sidebar è aperta di default
                this.updateSidebarState(true, false);
                document.body.classList.remove('mobile-view');
                document.body.classList.add('desktop-view');
            } else {
                // Su mobile, sidebar è chiusa di default
                this.updateSidebarState(false, false);
                document.body.classList.remove('desktop-view');
                document.body.classList.add('mobile-view');
            }
        }

        /**
         * Scroll alla cima della pagina
         */
        scrollToTop() {
            window.scrollTo({
                top: 0,
                behavior: CONFIG.scrolling.smoothScroll ? 'smooth' : 'auto'
            });
        }

        /**
         * Aggiorna contenuto corrente
         */
        refreshCurrentContent() {
            // Mostra overlay loading
            if (DOM.loadingOverlay) {
                DOM.loadingOverlay.style.display = 'flex';
            }
            
            // Refresh page
            window.location.reload();
        }
    }

    // Inizializza quando DOM è pronto
    document.addEventListener('DOMContentLoaded', () => {
        window.appManager = new AppManager();
    });
})();
