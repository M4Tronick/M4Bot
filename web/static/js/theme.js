/**
 * M4Bot - Gestione Tema e Animazioni Avanzate
 * Questo file gestisce il passaggio tra tema chiaro e scuro e le animazioni dell'interfaccia
 * con ottimizzazioni per le prestazioni e fluidità
 */

(function() {
    'use strict';
    
    // Impostazioni del tema
    const themeSettings = {
        darkMode: false,
        themeTransition: 300,
        savePreference: true,
        animations: true,        // Se abilitare le animazioni
        reducedMotion: false,    // Modalità a movimento ridotto per accessibilità
        parallelEffects: true,   // Se utilizzare effetti avanzati in parallelo
        userPreferenceSet: false // Flag per indicare se l'utente ha impostato una preferenza esplicita
    };
    
    // Cache per gli elementi DOM frequentemente usati
    const DOM = {
        html: document.documentElement,
        body: document.body,
        darkModeToggle: document.getElementById('darkModeToggle'),
        cards: document.querySelectorAll('.card'),
        buttons: document.querySelectorAll('.btn'),
        sidebar: document.querySelector('.sidebar'),
        sidebarItems: document.querySelectorAll('.sidebar-item'),
        toastContainer: document.querySelector('.toast-container'),
        statusIndicator: document.querySelector('.status-indicator'),
        statusText: document.querySelector('.status-text'),
        mainContent: document.querySelector('.main-content'),
        loader: document.getElementById('loading-overlay')
    };
    
    // Controlla preferenze di riduzione del movimento per accessibilità
    function checkReducedMotion() {
        themeSettings.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        
        if (themeSettings.reducedMotion) {
            document.body.classList.add('reduced-motion');
            themeSettings.animations = false;
        }
    }
    
    // Rileva le capacità/prestazioni del dispositivo
    function detectDeviceCapabilities() {
        // Rileva dispositivi a bassa potenza o browser meno performanti
        const isLowPower = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) && 
                           navigator.hardwareConcurrency && navigator.hardwareConcurrency < 4;
        
        if (isLowPower) {
            themeSettings.parallelEffects = false;
            document.body.classList.add('low-power-device');
        }
    }
    
    // Controlla se è stato salvato un tema nelle preferenze
    function loadSavedTheme() {
        const savedTheme = localStorage.getItem('m4bot-theme-preference');
        const savedAnimations = localStorage.getItem('m4bot-animations');
        
        if (savedTheme) {
            themeSettings.darkMode = savedTheme === 'dark';
            themeSettings.userPreferenceSet = true;
        } else {
            // Usa la preferenza di sistema
            themeSettings.darkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
            themeSettings.userPreferenceSet = false;
        }
        
        if (savedAnimations !== null) {
            themeSettings.animations = savedAnimations === 'true';
        }
        
        applyTheme();
        updateAnimationsState();
        
        // Notifica console per debugging
        console.log(`Tema caricato: ${themeSettings.darkMode ? 'dark' : 'light'} (preferenza utente: ${themeSettings.userPreferenceSet ? 'sì' : 'no'})`);
    }
    
    // Applica il tema attuale con transizione fluida
    function applyTheme() {
        // Prepara la transizione fluida
        DOM.body.classList.add('theme-transitioning');
        
        if (themeSettings.darkMode) {
            DOM.body.classList.add('dark-mode');
            DOM.html.setAttribute('data-bs-theme', 'dark');
            if (DOM.darkModeToggle) DOM.darkModeToggle.checked = true;
        } else {
            DOM.body.classList.remove('dark-mode');
            DOM.html.setAttribute('data-bs-theme', 'light');
            if (DOM.darkModeToggle) DOM.darkModeToggle.checked = false;
        }
        
        // Aggiorna l'attributo di data-theme nel body
        DOM.body.setAttribute('data-theme', themeSettings.darkMode ? 'dark' : 'light');
        
        // Rimuovi la classe di transizione dopo il completamento
        setTimeout(() => {
            DOM.body.classList.remove('theme-transitioning');
        }, themeSettings.themeTransition);
        
        // Salva la preferenza
        if (themeSettings.savePreference && themeSettings.userPreferenceSet) {
            localStorage.setItem('m4bot-theme-preference', themeSettings.darkMode ? 'dark' : 'light');
        }
    }
    
    // Aggiorna lo stato delle animazioni
    function updateAnimationsState() {
        if (themeSettings.animations) {
            DOM.body.classList.remove('no-animations');
        } else {
            DOM.body.classList.add('no-animations');
        }
        
        localStorage.setItem('m4bot-animations', themeSettings.animations);
    }
    
    // Gestisce il cambio tema e listener degli eventi
    function setupThemeToggle() {
        if (DOM.darkModeToggle) {
            // Imposta lo stato iniziale del toggle
            if (themeSettings.darkMode) {
                DOM.darkModeToggle.checked = true;
            }
            
            // Aggiungi l'event listener
            DOM.darkModeToggle.addEventListener('change', function() {
                themeSettings.darkMode = this.checked;
                themeSettings.userPreferenceSet = true; // L'utente ha esplicitamente scelto
                applyTheme();
                addRippleToToggle();
                
                // Mostra toast di conferma
                if (window.showToast) {
                    const message = themeSettings.darkMode ? 
                        'Tema scuro attivato' : 
                        'Tema chiaro attivato';
                    window.showToast(message, 'info', {
                        duration: 2000,
                        sound: false
                    });
                }
            });
            
            console.log("Theme toggle setup completato");
        } else {
            console.warn("Theme toggle non trovato nel DOM");
        }
        
        // Ascolta anche i cambiamenti del sistema
        const darkModeMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        darkModeMediaQuery.addEventListener('change', (e) => {
            // Applica il tema di sistema solo se l'utente non ha impostato una preferenza
            if (!themeSettings.userPreferenceSet) {
                themeSettings.darkMode = e.matches;
                applyTheme();
            }
        });
        
        // Ascolta le preferenze per la riduzione del movimento
        const reducedMotionMediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
        reducedMotionMediaQuery.addEventListener('change', checkReducedMotion);
    }
    
    // Aggiungi effetto ripple specifico per il toggle
    function addRippleToToggle() {
        if (!DOM.darkModeToggle || !themeSettings.animations) return;
        
        const toggle = DOM.darkModeToggle.closest('.theme-toggle');
        if (!toggle) return;
        
        const ripple = document.createElement('span');
        ripple.className = 'theme-toggle-ripple';
        toggle.appendChild(ripple);
        
        // Animazione del ripple
        requestAnimationFrame(() => {
            ripple.style.transform = 'scale(1)';
            ripple.style.opacity = '0';
            
            setTimeout(() => {
                ripple.remove();
            }, 600);
        });
    }
    
    // Effetti di ripple sui bottoni con ottimizzazione delle prestazioni
    function addRippleEffects() {
        if (!themeSettings.animations) return;
        
        const buttons = document.querySelectorAll('.btn, .card-action, .nav-link, [data-ripple]');
        
        buttons.forEach(button => {
            // Verifica se l'effetto è già stato aggiunto
            if (button.getAttribute('data-has-ripple') === 'true') return;
            
            button.setAttribute('data-has-ripple', 'true');
            
            button.addEventListener('mousedown', function(e) {
                if (!themeSettings.animations) return;
                
                // Previeni troppe animazioni simultanee
                const ripples = this.querySelectorAll('.ripple-effect');
                if (ripples.length > 2) {
                    ripples[0].remove(); // Rimuovi il più vecchio
                }
                
                const rect = this.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;
                
                const circle = document.createElement('span');
                circle.classList.add('ripple-effect');
                
                // Calcola le dimensioni per coprire l'intero elemento
                const diameter = Math.max(rect.width, rect.height) * 2;
                circle.style.width = circle.style.height = `${diameter}px`;
                circle.style.left = `${x}px`;
                circle.style.top = `${y}px`;
                
                // Usa requestAnimationFrame per animazioni più fluide
                requestAnimationFrame(() => {
                    this.appendChild(circle);
                    
                    // Rimuovi dopo l'animazione per evitare sovraccarico DOM
                    setTimeout(() => {
                        circle.remove();
                    }, 600);
                });
            });
        });
    }
    
    // Animazioni avanzate per le carte con effetto di profondità
    function setupCardAnimations() {
        if (!themeSettings.animations || !themeSettings.parallelEffects) return;
        
        DOM.cards.forEach((card, index) => {
            // Aggiungi classe per fade-in con delay progressivo
            card.classList.add('hardware-accelerated', 'fade-in');
            card.style.animationDelay = `${index * 0.05}s`;
            
            // Aggiungi effetto hover 3D se non presente
            if (!card.classList.contains('card-hover-effect') && themeSettings.parallelEffects) {
                card.classList.add('card-hover-effect');
                
                // Aggiungi effetto di parallasse 3D al passaggio del mouse
                card.addEventListener('mousemove', function(e) {
                    if (!themeSettings.animations) return;
                    
                    const rect = this.getBoundingClientRect();
                    const x = e.clientX - rect.left;
                    const y = e.clientY - rect.top;
                    
                    // Calcola la rotazione basata sulla posizione del mouse
                    const centerX = rect.width / 2;
                    const centerY = rect.height / 2;
                    const rotateX = (y - centerY) / 20;
                    const rotateY = (centerX - x) / 20;
                    
                    this.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.02, 1.02, 1.02) translateY(-3px)`;
                });
                
                // Ripristina l'aspetto originale quando il mouse esce
                card.addEventListener('mouseleave', function() {
                    this.style.transform = '';
                });
            }
        });
    }
    
    // Animazione avanzata per la sidebar con effetto di profondità
    function setupSidebarAnimations() {
        if (!themeSettings.animations) return;
        
        const sidebar = DOM.sidebar;
        const sidebarItems = DOM.sidebarItems;
        
        if (sidebar) {
            sidebar.classList.add('hardware-accelerated');
            
            if (window.innerWidth > 992) {
                sidebar.classList.add('slide-in');
            }
            
            sidebarItems.forEach((item, index) => {
                item.classList.add('hardware-accelerated', 'fade-in');
                item.style.animationDelay = `${0.2 + index * 0.03}s`;
                
                // Aggiungi effetto hover avanzato
                if (themeSettings.parallelEffects) {
                    const link = item.querySelector('.sidebar-link');
                    if (link) {
                        link.addEventListener('mouseenter', function() {
                            if (!themeSettings.animations) return;
                            this.classList.add('pulse-subtle');
                        });
                        
                        link.addEventListener('mouseleave', function() {
                            this.classList.remove('pulse-subtle');
                        });
                    }
                }
            });
        }
    }
    
    // Sistema avanzato di notifiche toast con effetti fisici
    function setupToastNotifications() {
        window.showToast = function(message, type = 'info', options = {}) {
            if (!DOM.toastContainer) return;
            
            const toastContainer = DOM.toastContainer;
            const toast = document.createElement('div');
            toast.classList.add('toast', `toast-${type}`, 'hardware-accelerated');
            
            if (options.customClass) {
                toast.classList.add(options.customClass);
            }
            
            toast.innerHTML = `
                <div class="toast-header">
                    <i class="fas ${getIconForToastType(type)} me-2"></i>
                    <span class="toast-title">${options.title || getToastTitle(type)}</span>
                    <button type="button" class="btn-close ms-auto"></button>
                </div>
                <div class="toast-body">
                    ${message}
                </div>
            `;
            
            toastContainer.appendChild(toast);
            
            // Ottimizza il rendering con requestAnimationFrame
            requestAnimationFrame(() => {
                // Verifica se ci sono troppe notifiche e rimuovi le più vecchie
                const toasts = toastContainer.querySelectorAll('.toast:not(.hiding)');
                if (toasts.length > 5) {
                    for (let i = 0; i < toasts.length - 5; i++) {
                        removeToast(toasts[i]);
                    }
                }
                
                // Mostra con animazione
                toast.classList.add('show');
                
                // Effetto di entrata fisica con rimbalzo
                if (themeSettings.animations && themeSettings.parallelEffects) {
                    toast.style.animationName = 'bounceInRight';
                }
                
                // Riproduci suono se abilitato
                if (options.sound !== false) {
                    playNotificationSound(type);
                }
            });
            
            // Auto-hide dopo 5 secondi (o il tempo specificato)
            const duration = options.duration || 5000;
            if (duration > 0) {
                setTimeout(() => {
                    removeToast(toast);
                }, duration);
            }
            
            // Funzionalità del pulsante di chiusura
            const closeBtn = toast.querySelector('.btn-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    removeToast(toast);
                });
            }
            
            // Aggiungi interazione al tocco/hover
            if (themeSettings.animations && themeSettings.parallelEffects) {
                toast.addEventListener('mouseenter', function() {
                    this.classList.add('toast-hover');
                });
                
                toast.addEventListener('mouseleave', function() {
                    this.classList.remove('toast-hover');
                });
            }
            
            return toast;
        };
        
        function removeToast(toast) {
            if (!toast || toast.classList.contains('hiding')) return;
            
            toast.classList.add('hiding');
            
            // Usa una transizione più elegante se abilitato
            if (themeSettings.animations && themeSettings.parallelEffects) {
                toast.style.animationName = 'bounceOutRight';
            }
            
            // Rimuovi dopo la transizione
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }
        
        function getIconForToastType(type) {
            switch (type) {
                case 'success': return 'fa-check-circle';
                case 'warning': return 'fa-exclamation-triangle';
                case 'danger': return 'fa-times-circle';
                case 'info':
                default: return 'fa-info-circle';
            }
        }
        
        function getToastTitle(type) {
            switch (type) {
                case 'success': return 'Successo';
                case 'warning': return 'Attenzione';
                case 'danger': return 'Errore';
                case 'info':
                default: return 'Informazione';
            }
        }
        
        function playNotificationSound(type) {
            if (!themeSettings.animations) return;
            
            // Implementa un semplice sistema di suoni
            try {
                const audio = new Audio();
                audio.volume = 0.5;
                
                // Seleziona un suono appropriato per il tipo
                switch (type) {
                    case 'success':
                        audio.src = '/static/sounds/success.mp3';
                        break;
                    case 'warning':
                    case 'danger':
                        audio.src = '/static/sounds/alert.mp3';
                        break;
                    default:
                        audio.src = '/static/sounds/notification.mp3';
                }
                
                audio.play().catch(e => console.log('Audio non supportato:', e));
            } catch (e) {
                // Ignora gli errori audio su browser che non supportano l'API
            }
        }
    }
    
    // Verifica connessione con effetti avanzati
    function setupConnectionStatus() {
        const statusIndicator = DOM.statusIndicator;
        const statusText = DOM.statusText;
        
        if (statusIndicator && statusText) {
            const updateStatus = (online) => {
                if (online) {
                    statusIndicator.classList.remove('disconnected', 'reconnecting');
                    statusIndicator.classList.add('connected');
                    statusText.textContent = 'Online';
                    
                    if (themeSettings.animations) {
                        statusIndicator.classList.add('pulse');
                        setTimeout(() => {
                            statusIndicator.classList.remove('pulse');
                        }, 2000);
                    }
                    
                    window.showToast('Connessione ristabilita!', 'success', {
                        customClass: 'connection-toast'
                    });
                } else {
                    statusIndicator.classList.remove('connected', 'reconnecting');
                    statusIndicator.classList.add('disconnected');
                    statusText.textContent = 'Offline';
                    
                    if (themeSettings.animations) {
                        statusIndicator.classList.add('shake');
                        setTimeout(() => {
                            statusIndicator.classList.remove('shake');
                        }, 500);
                    }
                    
                    window.showToast('Connessione persa. Controlla la tua rete.', 'danger', {
                        customClass: 'connection-toast',
                        duration: 0 // Non scompare automaticamente
                    });
                }
            };
            
            // Gestisci eventi online/offline
            window.addEventListener('online', () => updateStatus(true));
            window.addEventListener('offline', () => updateStatus(false));
            
            // Imposta lo stato iniziale
            updateStatus(navigator.onLine);
        }
    }
    
    // Implementa animazioni basate sullo scroll
    function setupScrollAnimations() {
        if (!themeSettings.animations) return;
        
        const animateOnScroll = () => {
            const elements = document.querySelectorAll('.reveal-on-scroll:not(.visible)');
            
            elements.forEach(element => {
                const elementTop = element.getBoundingClientRect().top;
                const elementVisible = 150;
                
                if (elementTop < window.innerHeight - elementVisible) {
                    element.classList.add('visible');
                }
            });
        };
        
        // Ottimizza le prestazioni con throttling
        let scrollTimeout;
        const throttledScroll = () => {
            if (scrollTimeout) return;
            
            scrollTimeout = setTimeout(() => {
                animateOnScroll();
                scrollTimeout = null;
            }, 100);
        };
        
        window.addEventListener('scroll', throttledScroll);
        
        // Esegui anche all'inizio per gli elementi già visibili
        animateOnScroll();
    }
    
    // Gestisci smooth scroll per i link interni
    function setupSmoothScroll() {
        document.querySelectorAll('a[href^="#"]:not([href="#"])').forEach(anchor => {
            anchor.addEventListener('click', function(e) {
                const targetId = this.getAttribute('href');
                const targetElement = document.querySelector(targetId);
                
                if (targetElement) {
                    e.preventDefault();
                    
                    // Soluzione più fluida rispetto a scrollIntoView
                    const targetPosition = targetElement.getBoundingClientRect().top + window.pageYOffset;
                    const startPosition = window.pageYOffset;
                    const distance = targetPosition - startPosition;
                    const duration = 800;
                    let start = null;
                    
                    const step = (timestamp) => {
                        if (!start) start = timestamp;
                        const progress = timestamp - start;
                        
                        // Funzione di easing per un movimento più naturale
                        const easeInOutQuad = (t) => {
                            return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
                        };
                        
                        window.scrollTo(0, startPosition + distance * easeInOutQuad(Math.min(progress / duration, 1)));
                        
                        if (progress < duration) {
                            window.requestAnimationFrame(step);
                        }
                    };
                    
                    window.requestAnimationFrame(step);
                }
            });
        });
    }
    
    // Effetto parallasse avanzato per elementi di sfondo
    function setupParallaxEffects() {
        if (!themeSettings.animations || !themeSettings.parallelEffects) return;
        
        const parallaxContainers = document.querySelectorAll('.parallax-container');
        
        parallaxContainers.forEach(container => {
            const layers = container.querySelectorAll('.parallax-layer');
            
            // Movimento basato sul mouse
            container.addEventListener('mousemove', function(e) {
                const rect = this.getBoundingClientRect();
                const mouseX = (e.clientX - rect.left) / rect.width;
                const mouseY = (e.clientY - rect.top) / rect.height;
                
                layers.forEach(layer => {
                    const depth = parseFloat(layer.getAttribute('data-depth') || 0.1);
                    const translateX = (mouseX - 0.5) * depth * 50;
                    const translateY = (mouseY - 0.5) * depth * 50;
                    
                    layer.style.transform = `translate3d(${translateX}px, ${translateY}px, 0)`;
                });
            });
            
            // Ripristina quando il mouse esce
            container.addEventListener('mouseleave', function() {
                layers.forEach(layer => {
                    layer.style.transform = 'translate3d(0, 0, 0)';
                });
            });
        });
    }
    
    // Ottimizza il caricamento iniziale della pagina
    function optimizeInitialLoad() {
        // Nascondi il loader quando la pagina è caricata
        if (DOM.loader) {
            if (document.readyState === 'complete') {
                hideLoader();
            } else {
                window.addEventListener('load', hideLoader);
            }
        }
        
        function hideLoader() {
            if (!DOM.loader) return;
            
            // Usa una transizione fluida
            DOM.loader.style.opacity = '0';
            
            setTimeout(() => {
                DOM.loader.style.display = 'none';
                
                // Anima l'entrata del contenuto principale
                if (DOM.mainContent && themeSettings.animations) {
                    DOM.mainContent.classList.add('page-transition', 'active');
                }
            }, 300);
        }
    }
    
    // Transizioni avanzate tra pagine
    function setupPageTransitions() {
        if (!themeSettings.animations) return;
        
        // Supporto per pre-caricamento delle pagine
        document.querySelectorAll('a[data-prefetch="true"]').forEach(link => {
            link.addEventListener('mouseenter', () => {
                const href = link.getAttribute('href');
                if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
                    const prefetcher = document.createElement('link');
                    prefetcher.rel = 'prefetch';
                    prefetcher.href = href;
                    document.head.appendChild(prefetcher);
                }
            });
        });
        
        // Aggiungi effetto di transizione quando si cambia pagina
        document.querySelectorAll('a:not([href^="#"]):not([target="_blank"])').forEach(link => {
            link.addEventListener('click', function(e) {
                const href = this.getAttribute('href');
                
                // Salta i link che non sono navigazione
                if (!href || href.startsWith('#') || href.startsWith('javascript:') || this.getAttribute('target') === '_blank') {
                    return;
                }
                
                // Preveniamo il comportamento di default per aggiungere la nostra transizione
                if (themeSettings.animations && themeSettings.parallelEffects) {
                    e.preventDefault();
                    
                    // Animazione di uscita
                    document.body.classList.add('page-exiting');
                    
                    // Cambia pagina dopo l'animazione
                    setTimeout(() => {
                        window.location.href = href;
                    }, 300);
                }
            });
        });
    }
    
    // Funzione per reimpostare il tema alle preferenze di sistema
    function resetThemeToSystem() {
        themeSettings.userPreferenceSet = false;
        localStorage.removeItem('m4bot-theme-preference');
        themeSettings.darkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
        applyTheme();
        
        // Aggiorna il toggle
        if (DOM.darkModeToggle) {
            DOM.darkModeToggle.checked = themeSettings.darkMode;
        }
        
        // Mostra toast di conferma
        if (window.showToast) {
            window.showToast('Tema reimpostato sulle preferenze di sistema', 'info', {
                duration: 2000,
                sound: false
            });
        }
    }
    
    // Esporta funzioni per l'accesso globale
    window.themeManager = {
        toggleDarkMode: () => {
            themeSettings.darkMode = !themeSettings.darkMode;
            themeSettings.userPreferenceSet = true;
            applyTheme();
            
            // Aggiorna il toggle
            if (DOM.darkModeToggle) {
                DOM.darkModeToggle.checked = themeSettings.darkMode;
            }
        },
        setDarkMode: (isDark) => {
            themeSettings.darkMode = !!isDark;
            themeSettings.userPreferenceSet = true;
            applyTheme();
            
            // Aggiorna il toggle
            if (DOM.darkModeToggle) {
                DOM.darkModeToggle.checked = themeSettings.darkMode;
            }
        },
        resetToSystemPreference: resetThemeToSystem,
        getThemeInfo: () => {
            return {
                darkMode: themeSettings.darkMode,
                userPreferenceSet: themeSettings.userPreferenceSet,
                reducedMotion: themeSettings.reducedMotion,
                animations: themeSettings.animations
            };
        }
    };
    
    // Controllo per la modalità streaming
    function initStreamingMode() {
        // Crea il pulsante di toggle per la modalità streaming
        if (!document.querySelector('.streaming-mode-toggle')) {
            const streamingToggle = document.createElement('div');
            streamingToggle.className = 'streaming-mode-toggle';
            streamingToggle.title = 'Modalità streaming';
            streamingToggle.innerHTML = '<i class="fas fa-tv"></i>';
            document.body.appendChild(streamingToggle);
            
            // Evento click per attivare/disattivare la modalità streaming
            streamingToggle.addEventListener('click', toggleStreamingMode);
        }
        
        // Controllo se la modalità streaming era attiva
        const streamingModeEnabled = localStorage.getItem('streamingMode') === 'true';
        if (streamingModeEnabled) {
            enableStreamingMode();
        }
    }
    
    // Funzione per attivare/disattivare la modalità streaming
    function toggleStreamingMode() {
        const streamingModeEnabled = document.documentElement.getAttribute('data-theme') === 'streaming';
        
        if (streamingModeEnabled) {
            disableStreamingMode();
        } else {
            enableStreamingMode();
        }
    }
    
    // Abilita la modalità streaming
    function enableStreamingMode() {
        // Salva il tema precedente
        const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
        localStorage.setItem('previousTheme', currentTheme);
        
        // Imposta modalità streaming
        document.documentElement.setAttribute('data-theme', 'streaming');
        localStorage.setItem('streamingMode', 'true');
        
        // Notifica l'utente
        if (window.showActionFeedback) {
            showActionFeedback('success', 'Modalità streaming attivata', 3000);
        }
        
        // Aggiorna l'interfaccia
        const streamingToggle = document.querySelector('.streaming-mode-toggle');
        if (streamingToggle) {
            streamingToggle.innerHTML = '<i class="fas fa-times"></i>';
            streamingToggle.title = 'Disattiva modalità streaming';
        }
        
        // Aggiorna i controlli del tema
        updateThemeControls('streaming');
    }
    
    // Disabilita la modalità streaming
    function disableStreamingMode() {
        // Recupera il tema precedente
        const previousTheme = localStorage.getItem('previousTheme') || 'light';
        
        // Ripristina il tema precedente
        document.documentElement.setAttribute('data-theme', previousTheme);
        localStorage.setItem('streamingMode', 'false');
        
        // Notifica l'utente
        if (window.showActionFeedback) {
            showActionFeedback('info', 'Modalità streaming disattivata', 3000);
        }
        
        // Aggiorna l'interfaccia
        const streamingToggle = document.querySelector('.streaming-mode-toggle');
        if (streamingToggle) {
            streamingToggle.innerHTML = '<i class="fas fa-tv"></i>';
            streamingToggle.title = 'Modalità streaming';
        }
        
        // Aggiorna i controlli del tema
        updateThemeControls(previousTheme);
    }
    
    // Sistema di temi stagionali
    function initSeasonalThemes() {
        // Verifica se l'utente ha disabilitato i temi stagionali
        const seasonalThemesDisabled = localStorage.getItem('disableSeasonalThemes') === 'true';
        if (seasonalThemesDisabled) {
            return;
        }
        
        // Verifica la data corrente
        const now = new Date();
        const month = now.getMonth() + 1; // Gennaio = 1, Dicembre = 12
        const day = now.getDate();
        
        // Temi stagionali
        let seasonalTheme = null;
        let seasonalThemeDescription = '';
        
        // Natale (1-25 dicembre)
        if (month === 12 && day <= 25) {
            seasonalTheme = 'christmas';
            seasonalThemeDescription = 'Tema natalizio';
        }
        // Halloween (15-31 ottobre)
        else if (month === 10 && day >= 15) {
            seasonalTheme = 'halloween';
            seasonalThemeDescription = 'Tema Halloween';
        }
        // San Valentino (1-14 febbraio)
        else if (month === 2 && day <= 14) {
            seasonalTheme = 'valentine';
            seasonalThemeDescription = 'Tema San Valentino';
        }
        // Primavera (marzo-maggio)
        else if (month >= 3 && month <= 5) {
            seasonalTheme = 'spring';
            seasonalThemeDescription = 'Tema primaverile';
        }
        // Estate (giugno-agosto)
        else if (month >= 6 && month <= 8) {
            seasonalTheme = 'summer';
            seasonalThemeDescription = 'Tema estivo';
        }
        // Autunno (settembre-novembre, escludendo Halloween)
        else if (month >= 9 && month <= 11 && !(month === 10 && day >= 15)) {
            seasonalTheme = 'autumn';
            seasonalThemeDescription = 'Tema autunnale';
        }
        
        // Se abbiamo un tema stagionale e non è già stato applicato oggi
        if (seasonalTheme) {
            const lastSeasonalThemeDate = localStorage.getItem('lastSeasonalThemeDate');
            const today = now.toDateString();
            
            // Aggiungiamo un CSS dinamico per il tema stagionale se necessario
            if (!document.querySelector(`link[href*="${seasonalTheme}-theme.css"]`)) {
                const seasonalCSS = document.createElement('link');
                seasonalCSS.rel = 'stylesheet';
                seasonalCSS.href = `/static/css/seasonal/${seasonalTheme}-theme.css`;
                document.head.appendChild(seasonalCSS);
            }
            
            // Notifica l'utente solo una volta al giorno
            if (lastSeasonalThemeDate !== today) {
                localStorage.setItem('lastSeasonalThemeDate', today);
                
                // Mostra notifica dopo un ritardo
                setTimeout(() => {
                    if (window.showActionFeedback) {
                        showActionFeedback('info', `${seasonalThemeDescription} disponibile! Vuoi attivarlo?`, 10000);
                        
                        // Aggiungiamo anche una notifica più completa
                        if (window.notificationSystem) {
                            notificationSystem.info(`${seasonalThemeDescription} disponibile!`, {
                                title: 'Tema stagionale',
                                duration: 10000,
                                onClick: function() {
                                    applySeasonalTheme(seasonalTheme);
                                }
                            });
                        }
                    }
                }, 3000);
            }
            
            // Aggiungiamo un pulsante nel selettore di temi
            addSeasonalThemeOption(seasonalTheme, seasonalThemeDescription);
        }
    }
    
    // Aggiunge un'opzione per il tema stagionale nel selettore
    function addSeasonalThemeOption(theme, description) {
        const themeSelector = document.getElementById('theme-selector');
        if (!themeSelector) return;
        
        // Verifica se l'opzione esiste già
        if (!themeSelector.querySelector(`option[value="${theme}"]`)) {
            const option = document.createElement('option');
            option.value = theme;
            option.textContent = description;
            option.className = 'seasonal-theme-option';
            themeSelector.appendChild(option);
        }
    }
    
    // Applica un tema stagionale
    function applySeasonalTheme(theme) {
        // Imposta il tema
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        
        // Aggiorna interfaccia
        updateThemeControls(theme);
        
        // Notifica l'utente
        if (window.showActionFeedback) {
            showActionFeedback('success', 'Tema stagionale applicato!', 3000);
        }
    }
    
    // Aggiorna i controlli degli altri temi
    function updateThemeControls(activeTheme) {
        // Aggiorna il selettore di tema se presente
        const themeSelector = document.getElementById('theme-selector');
        if (themeSelector) {
            themeSelector.value = activeTheme;
        }
        
        // Aggiorna dark mode toggle se presente
        const darkModeToggle = document.getElementById('darkModeToggle');
        if (darkModeToggle) {
            darkModeToggle.checked = activeTheme === 'dark' || activeTheme === 'streaming';
        }
    }
    
    // Inizializza tutte le funzionalità con un approccio a fasi
    function init() {
        // Rileva preferenze e capacità del dispositivo
        checkReducedMotion();
        detectDeviceCapabilities();
        
        // Fase 1: Caricamento base e ottimizzazione
        loadSavedTheme();
        optimizeInitialLoad();
        
        // Fase 2: Setup completo del tema e interazioni di base
        setupThemeToggle();
        addRippleEffects();
        
        // Fase 3: Animazioni avanzate e interazioni
        requestAnimationFrame(() => {
            setupCardAnimations();
            setupSidebarAnimations();
            setupToastNotifications();
            setupConnectionStatus();
            
            // Fase 4: Gestione dello scroll e parallasse (ritardata per performance)
            setTimeout(() => {
                setupScrollAnimations();
                setupSmoothScroll();
                setupParallaxEffects();
                setupPageTransitions();
                
                // Fase 5: Notifica di benvenuto (ulteriormente ritardata)
                setTimeout(() => {
                    if (window.showToast && themeSettings.animations) {
                        window.showToast('Benvenuto su M4Bot! Esplora tutte le nuove funzionalità.', 'info', {
                            title: 'Benvenuto'
                        });
                    }
                }, 1000);
            }, 300);
        });
        
        // Inizializza la modalità streaming
        initStreamingMode();
        
        // Inizializza i temi stagionali
        initSeasonalThemes();
    }
    
    // Inizializza quando il DOM è pronto con event listener ottimizzato
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(); 