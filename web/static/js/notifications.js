/**
 * M4Bot - Sistema di Notifiche Avanzato
 * Gestisce le notifiche dell'applicazione, gli alert e i messaggi di stato
 * con animazioni fluide e ottimizzazioni per le prestazioni
 */

(function() {
    'use strict';
    
    // Configurazione globale delle notifiche
    const notificationConfig = {
        defaultDuration: 5000,      // 5 secondi
        position: 'top-right',      // posizione: top-right, top-left, bottom-right, bottom-left, top-center
        maxNotifications: 5,        // massimo numero di notifiche simultanee
        soundEnabled: true,         // abilita suoni
        animationDuration: 400,     // durata delle animazioni
        stacked: true,              // notifiche impilate
        animationType: 'bounce',    // tipo di animazione: bounce, fade, slide
        autoClose: true,            // chiusura automatica
        newestOnTop: true,          // mostra le più recenti in cima
        showProgressBar: true,      // mostra barra di progresso
        escapeHtml: true,           // escape del codice HTML nei messaggi
        preventDuplicates: true     // prevenire duplicati
    };
    
    // Configurazione WebSocket per notifiche real-time
    const wsConfig = {
        connected: false,
        reconnectAttempts: 0,
        maxReconnectAttempts: 5,
        reconnectDelay: 3000,
        socket: null,
        token: document.querySelector('meta[name="notification-token"]')?.content || '',
        userId: document.querySelector('meta[name="user-id"]')?.content || ''
    };
    
    // Contatore per gli ID delle notifiche
    let notificationCounter = 0;
    
    // Cache delle notifiche attive
    const activeNotifications = new Map();
    
    // Cache degli elementi DOM
    let toastContainer;
    const audioCache = new Map();
    
    // Contatore per notifiche non lette
    let unreadNotifications = 0;
    
    // Registro per notifiche ricevute
    const notificationHistory = [];
    const MAX_NOTIFICATION_HISTORY = 50;
    
    // Init: Importa CSS, prepara contenitori, e listener globali
    function init() {
        console.debug('[Notifications] Initializing notification system');
        
        // Crea container se non esiste
        toastContainer = document.querySelector('.toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.className = 'toast-container';
            
            // Posizione in base alla configurazione
            setContainerPosition();
            
            document.body.appendChild(toastContainer);
        }
        
        // Carica e prepara suoni di notifica
        preloadSounds();
        
        // Inizializza il contatore delle notifiche non lette
        initNotificationBadge();
        
        // Connetti al server di notifiche
        if (wsConfig.userId) {
            initWebSocketConnection();
        }
        
        // Esporta API globale
        window.notificationSystem = {
            success: (message, options) => showNotification(message, 'success', options),
            info: (message, options) => showNotification(message, 'info', options),
            warning: (message, options) => showNotification(message, 'warning', options),
            error: (message, options) => showNotification(message, 'danger', options),
            confirm: showConfirmation,
            showBanner: showBanner,
            setOptions: setGlobalOptions,
            dismissAll: dismissAllNotifications,
            getActiveCount: () => activeNotifications.size,
            getUnreadCount: () => unreadNotifications,
            clearUnread: clearUnreadNotifications,
            sendTestNotification: sendTestNotification
        };
        
        // Gestione messaggi flash dal server
        handleServerMessages();
        
        // Listener globali per ESC e click esterno
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                const confirmations = document.querySelectorAll('.confirmation-overlay.show');
                if (confirmations.length > 0) {
                    const latestConfirmation = confirmations[confirmations.length - 1];
                    const cancelButton = latestConfirmation.querySelector('[data-action="cancel"]');
                    if (cancelButton) cancelButton.click();
                } else if (notificationConfig.closeOnEsc) {
                    dismissAllNotifications();
                }
            }
        });
        
        // Listener per preferenze di riduzione del movimento
        const reducedMotionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
        if (reducedMotionQuery.matches) {
            notificationConfig.animationDuration = 100;
            notificationConfig.animationType = 'fade';
        }
        
        // Resize observer per posizionamento responsivo
        if (window.ResizeObserver) {
            const resizeObserver = new ResizeObserver(() => {
                setContainerPosition();
            });
            resizeObserver.observe(document.body);
        }
    }
    
    // Posiziona il container in base alla configurazione
    function setContainerPosition() {
        if (!toastContainer) return;
        
        toastContainer.className = 'toast-container';
        toastContainer.classList.add(`position-${notificationConfig.position || 'top-right'}`);
        
        // Ripristina gli stili di posizionamento
        toastContainer.style.top = '';
        toastContainer.style.bottom = '';
        toastContainer.style.left = '';
        toastContainer.style.right = '';
        
        // Imposta la posizione
        const position = notificationConfig.position || 'top-right';
        
        if (position.includes('top')) {
            toastContainer.style.top = '80px';
        } else {
            toastContainer.style.bottom = '20px';
        }
        
        if (position.includes('right')) {
            toastContainer.style.right = '20px';
        } else if (position.includes('left')) {
            toastContainer.style.left = '20px';
        } else if (position.includes('center')) {
            toastContainer.style.left = '50%';
            toastContainer.style.transform = 'translateX(-50%)';
        }
    }
    
    // Precarica i suoni per un uso immediato senza latenza
    function preloadSounds() {
        if (!notificationConfig.soundEnabled) return;
        
        try {
            const sounds = [
                { key: 'success', url: '/static/sounds/success.mp3' },
                { key: 'info', url: '/static/sounds/notification.mp3' },
                { key: 'warning', url: '/static/sounds/alert.mp3' },
                { key: 'danger', url: '/static/sounds/error.mp3' },
                { key: 'click', url: '/static/sounds/click.mp3' }
            ];
            
            sounds.forEach(sound => {
                const audio = new Audio();
                audio.preload = 'auto';
                audio.volume = 0.4;
                audio.src = sound.url;
                audioCache.set(sound.key, audio);
                
                // Trick per precaricamento
                audio.load();
                audio.muted = true;
                audio.play().catch(() => {});
                audio.muted = false;
                audio.currentTime = 0;
            });
        } catch (e) {
            console.warn('[Notifications] Audio preloading failed:', e);
        }
    }
    
    // Aggiorna le opzioni globali
    function setGlobalOptions(options) {
        if (!options || typeof options !== 'object') return;
        
        Object.assign(notificationConfig, options);
        
        // Aggiorna la posizione se è cambiata
        if (options.position) {
            setContainerPosition();
        }
    }
    
    // Mostra una notifica toast con animazioni avanzate
    function showNotification(message, type = 'info', options = {}) {
        if (!toastContainer) return null;
        
        // Controlla per duplicati se abilitato
        if (notificationConfig.preventDuplicates && hasDuplicateNotification(message, type)) {
            return null;
        }
        
        // Controlla il numero massimo di notifiche
        if (activeNotifications.size >= notificationConfig.maxNotifications) {
            // Rimuovi la notifica più vecchia
            const [oldestId] = activeNotifications.keys();
            if (oldestId) {
                const oldestToast = document.getElementById(oldestId);
                if (oldestToast) removeNotification(oldestToast);
            }
        }
        
        // Crea ID univoco
        const id = `notification-${++notificationCounter}`;
        
        // Unisci le opzioni con i default
        const settings = Object.assign({}, {
            duration: notificationConfig.defaultDuration,
            closable: true,
            sound: notificationConfig.soundEnabled && type !== 'info',
            icon: getIconForType(type),
            title: getTitleForType(type),
            onClick: null,
            showProgressBar: notificationConfig.showProgressBar,
            animationType: notificationConfig.animationType,
            customClass: '',
            escapeHtml: notificationConfig.escapeHtml
        }, options);
        
        // Sanifica il messaggio se necessario
        const safeMessage = settings.escapeHtml ? escapeHtml(message) : message;
        
        // Crea elemento toast con hardware acceleration
        const toast = document.createElement('div');
        toast.id = id;
        toast.className = `toast toast-${type} toast-${settings.animationType} hardware-accelerated`;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', type === 'danger' ? 'assertive' : 'polite');
        
        if (settings.customClass) {
            toast.classList.add(settings.customClass);
        }
        
        if (settings.onClick) {
            toast.classList.add('clickable');
            toast.addEventListener('click', (e) => {
                // Evita di attivare onClick quando si clicca sul pulsante di chiusura
                if (!e.target.closest('.btn-close')) {
                    settings.onClick(toast);
                }
                playSound('click');
            });
        }
        
        // Preparazione del template
        let progressBar = '';
        if (settings.showProgressBar && settings.duration > 0) {
            progressBar = `
                <div class="toast-progress-bar-container">
                    <div class="toast-progress-bar" style="animation-duration: ${settings.duration}ms"></div>
                </div>
            `;
        }
        
        // Crea HTML interno con animazioni ottimizzate
        toast.innerHTML = `
            <div class="toast-header transition-colors">
                <i class="fas ${settings.icon} me-2"></i>
                <span class="toast-title">${settings.title}</span>
                ${settings.closable ? '<button type="button" class="btn-close ms-auto" aria-label="Chiudi"></button>' : ''}
            </div>
            <div class="toast-body">
                ${safeMessage}
            </div>
            ${progressBar}
        `;
        
        // Aggiungi al container (in cima o in fondo a seconda della configurazione)
        if (notificationConfig.newestOnTop) {
            toastContainer.prepend(toast);
        } else {
            toastContainer.appendChild(toast);
        }
        
        // Ottimizza il rendering con requestAnimationFrame per animazioni fluide
        requestAnimationFrame(() => {
            // Mostra con animazione dopo il rendering
            setTimeout(() => {
                toast.classList.add('show');
                
                // Aggiungi effetti di profondità e parallasse se supportati
                if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
                    toast.style.transform = 'translateZ(0)';
                }
                
                // Riproduci suono con debounce per evitare sovrapposizioni
                if (settings.sound) {
                    playSound(type);
                }
                
                // Registra nella cache delle notifiche attive
                activeNotifications.set(id, {
                    id,
                    type,
                    message: safeMessage,
                    timestamp: Date.now()
                });
            }, 10);
        });
        
        // Auto-hide dopo il tempo specificato
        if (settings.duration > 0 && notificationConfig.autoClose) {
            toast.autoHideTimeout = setTimeout(() => {
                removeNotification(toast);
            }, settings.duration);
            
            // Pausa il timeout durante l'hover
            toast.addEventListener('mouseenter', () => {
                clearTimeout(toast.autoHideTimeout);
                // Pausa anche l'animazione della progress bar
                const progressBar = toast.querySelector('.toast-progress-bar');
                if (progressBar) progressBar.style.animationPlayState = 'paused';
            });
            
            toast.addEventListener('mouseleave', () => {
                toast.autoHideTimeout = setTimeout(() => {
                    removeNotification(toast);
                }, settings.duration / 2); // Dimezza il tempo rimanente
                // Riprende l'animazione della progress bar
                const progressBar = toast.querySelector('.toast-progress-bar');
                if (progressBar) progressBar.style.animationPlayState = 'running';
            });
        }
        
        // Gestisci interazioni
        setupToastInteractions(toast);
        
        return id;
    }
    
    // Configura le interazioni per una notifica
    function setupToastInteractions(toast) {
        // Click sul pulsante di chiusura
        const closeBtn = toast.querySelector('.btn-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                removeNotification(toast);
                playSound('click');
            });
        }
        
        // Trascina per chiudere su dispositivi touch
        let touchStartX = 0;
        let touchEndX = 0;
        
        toast.addEventListener('touchstart', (e) => {
            touchStartX = e.changedTouches[0].screenX;
        }, { passive: true });
        
        toast.addEventListener('touchend', (e) => {
            touchEndX = e.changedTouches[0].screenX;
            handleSwipe();
        }, { passive: true });
        
        const handleSwipe = () => {
            const diffX = touchEndX - touchStartX;
            if (Math.abs(diffX) > 100) { // minimo 100px di swipe
                // Direzione: destra se positivo, sinistra se negativo
                const direction = diffX > 0 ? 'right' : 'left';
                
                // Animazione di uscita basata sulla direzione
                toast.style.transition = `transform ${notificationConfig.animationDuration / 1000}s cubic-bezier(0.4, 0, 0.2, 1)`;
                toast.style.transform = `translateX(${direction === 'right' ? '100%' : '-100%'})`;
                
                setTimeout(() => {
                    removeNotification(toast);
                }, notificationConfig.animationDuration);
            }
        };
        
        // Aggiungi animazioni hover
        toast.addEventListener('mouseenter', () => {
            toast.classList.add('toast-hover');
        });
        
        toast.addEventListener('mouseleave', () => {
            toast.classList.remove('toast-hover');
        });
    }
    
    // Rimuove una notifica con animazione
    function removeNotification(toast) {
        if (!toast || toast.classList.contains('hiding')) return;
        
        // Previeni molteplici chiamate
        toast.classList.add('hiding');
        
        // Rimuovi dalla cache
        if (toast.id) {
            activeNotifications.delete(toast.id);
        }
        
        // Cancella timeout
        if (toast.autoHideTimeout) {
            clearTimeout(toast.autoHideTimeout);
        }
        
        // Animazione di uscita
        const animationDuration = notificationConfig.animationDuration;
        setTimeout(() => {
            if (toast.parentNode) {
                // Usa una transizione fluida per riorganizzare le notifiche rimanenti
                const remainingToasts = toastContainer.querySelectorAll('.toast:not(.hiding)');
                remainingToasts.forEach(t => {
                    t.style.transition = `all ${animationDuration / 1000}s cubic-bezier(0.4, 0, 0.2, 1)`;
                });
                
                toast.parentNode.removeChild(toast);
            }
        }, animationDuration);
    }
    
    // Chiudi tutte le notifiche
    function dismissAllNotifications() {
        const toasts = toastContainer.querySelectorAll('.toast:not(.hiding)');
        
        // Crea un effetto a cascata
        toasts.forEach((toast, index) => {
            setTimeout(() => {
                removeNotification(toast);
            }, index * 50);
        });
    }
    
    // Controlla se esiste già una notifica simile
    function hasDuplicateNotification(message, type) {
        for (const notification of activeNotifications.values()) {
            if (notification.type === type && notification.message === message) {
                return true;
            }
        }
        return false;
    }
    
    // Sanitizza l'HTML per evitare XSS
    function escapeHtml(unsafe) {
        if (!unsafe || typeof unsafe !== 'string') return '';
        return unsafe
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
    
    // Finestra di conferma migliorata con animazioni fluide
    function showConfirmation(message, options = {}) {
        return new Promise((resolve) => {
            // Rimuovi eventuali overlay esistenti
            const existingOverlays = document.querySelectorAll('.confirmation-overlay');
            existingOverlays.forEach(overlay => {
                overlay.classList.remove('show');
                setTimeout(() => {
                    overlay.remove();
                }, 300);
            });
            
            // Unisci le opzioni con i default
            const settings = Object.assign({}, {
                title: 'Conferma',
                confirmText: 'Conferma',
                cancelText: 'Annulla',
                confirmClass: 'btn-primary',
                cancelClass: 'btn-outline',
                type: 'info',
                escapeHtml: true,
                closeOnEsc: true,
                closeOnClickOutside: true,
                animation: true
            }, options);
            
            // Sanifica il messaggio se necessario
            const safeMessage = settings.escapeHtml ? escapeHtml(message) : message;
            
            // Crea overlay
            const overlay = document.createElement('div');
            overlay.className = 'confirmation-overlay';
            overlay.setAttribute('role', 'dialog');
            overlay.setAttribute('aria-modal', 'true');
            overlay.setAttribute('aria-labelledby', 'confirmation-title');
            
            // Crea dialog
            const dialog = document.createElement('div');
            dialog.className = `confirmation-dialog confirmation-${settings.type} hardware-accelerated`;
            
            dialog.innerHTML = `
                <div class="confirmation-header" id="confirmation-title">
                    <h5>${settings.title}</h5>
                    <button type="button" class="btn-close" data-action="cancel" aria-label="Chiudi"></button>
                </div>
                <div class="confirmation-body">
                    <p>${safeMessage}</p>
                </div>
                <div class="confirmation-footer">
                    <button type="button" class="btn ${settings.cancelClass}" data-action="cancel">${settings.cancelText}</button>
                    <button type="button" class="btn ${settings.confirmClass}" data-action="confirm">${settings.confirmText}</button>
                </div>
            `;
            
            // Aggiungi al body
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);
            
            // Gestisci il click fuori dal dialog
            if (settings.closeOnClickOutside) {
                overlay.addEventListener('click', (e) => {
                    if (e.target === overlay) {
                        handleAction('cancel');
                    }
                });
            }
            
            // Mostra con animazione
            setTimeout(() => {
                overlay.classList.add('show');
                dialog.classList.add('show');
                
                // Focus sul bottone di conferma per accessibilità
                const confirmButton = dialog.querySelector(`[data-action="confirm"]`);
                confirmButton.focus();
                
                // Riproduci suono
                playSound('info');
            }, 10);
            
            // Gestisci eventi
            const handleAction = (action) => {
                // Disabilita i bottoni durante la chiusura
                const buttons = dialog.querySelectorAll('button');
                buttons.forEach(btn => {
                    btn.disabled = true;
                });
                
                // Nascondi con animazione
                overlay.classList.remove('show');
                dialog.classList.remove('show');
                
                // Riproduci suono
                playSound('click');
                
                // Rimuovi dopo l'animazione
                setTimeout(() => {
                    document.body.removeChild(overlay);
                    
                    // Risolvi la promise
                    resolve(action === 'confirm');
                }, 300);
            };
            
            // Ascolta eventi sui bottoni
            dialog.addEventListener('click', (e) => {
                const actionElement = e.target.closest('[data-action]');
                if (actionElement) {
                    const action = actionElement.dataset.action;
                    handleAction(action);
                }
            });
            
            // Gestione tastiera per accessibilità
            dialog.addEventListener('keydown', (e) => {
                if (e.key === 'Escape' && settings.closeOnEsc) {
                    handleAction('cancel');
                } else if (e.key === 'Enter') {
                    const focusedElement = document.activeElement;
                    if (focusedElement.tagName === 'BUTTON' && focusedElement.dataset.action) {
                        handleAction(focusedElement.dataset.action);
                    } else {
                        handleAction('confirm'); // Default a conferma se premuto Enter
                    }
                }
            });
        });
    }
    
    // Banner informativo in cima/fondo alla pagina
    function showBanner(message, type = 'info', options = {}) {
        // Rimuovi banner esistenti se richiesto
        const existingBanner = document.querySelector('.app-banner');
        if (existingBanner && !options.allowMultiple) {
            existingBanner.remove();
        }
        
        // Unisci le opzioni con i default
        const settings = Object.assign({}, {
            duration: 0,  // 0 = permanente fino a chiusura
            closable: true,
            icon: getIconForType(type),
            position: 'top',  // top o bottom
            escapeHtml: true,
            animation: true,
            onClose: null,    // callback alla chiusura
            id: `banner-${Date.now()}`
        }, options);
        
        // Sanifica il messaggio se necessario
        const safeMessage = settings.escapeHtml ? escapeHtml(message) : message;
        
        // Crea banner
        const banner = document.createElement('div');
        banner.id = settings.id;
        banner.className = `app-banner app-banner-${type} app-banner-${settings.position} hardware-accelerated`;
        banner.setAttribute('role', 'alert');
        
        banner.innerHTML = `
            <div class="container-fluid">
                <div class="banner-content">
                    <i class="fas ${settings.icon} me-2"></i>
                    <span>${safeMessage}</span>
                    ${settings.closable ? '<button type="button" class="btn-close" aria-label="Chiudi"></button>' : ''}
                </div>
            </div>
        `;
        
        // Aggiungi al body
        document.body.appendChild(banner);
        
        // Mostra con animazione
        requestAnimationFrame(() => {
            setTimeout(() => {
                banner.classList.add('show');
                
                // Riproduci suono
                playSound(type);
            }, 10);
        });
        
        // Auto-hide dopo la durata impostata
        if (settings.duration > 0) {
            setTimeout(() => {
                hideBanner(banner, settings.onClose);
            }, settings.duration);
        }
        
        // Aggiungi funzionalità al pulsante di chiusura
        if (settings.closable) {
            const closeBtn = banner.querySelector('.btn-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => {
                    hideBanner(banner, settings.onClose);
                    playSound('click');
                });
            }
        }
        
        return banner;
    }
    
    // Nascondi il banner con animazione
    function hideBanner(banner, callback) {
        if (!banner || !banner.classList.contains('show')) return;
        
        banner.classList.remove('show');
        setTimeout(() => {
            if (banner.parentNode) {
                banner.parentNode.removeChild(banner);
                if (typeof callback === 'function') {
                    callback();
                }
            }
        }, notificationConfig.animationDuration);
    }
    
    // Riproduce un suono in modo efficiente
    function playSound(type) {
        if (!notificationConfig.soundEnabled) return;
        
        try {
            // Usa audio cache per performance
            if (audioCache.has(type)) {
                const audio = audioCache.get(type);
                audio.currentTime = 0;
                audio.play().catch(() => {});
            } else {
                // Fallback per tipi non in cache
                const audio = new Audio();
                audio.volume = 0.4;
                
                switch (type) {
                    case 'success': audio.src = '/static/sounds/success.mp3'; break;
                    case 'warning': 
                    case 'danger': audio.src = '/static/sounds/alert.mp3'; break;
                    case 'click': audio.src = '/static/sounds/click.mp3'; break;
                    default: audio.src = '/static/sounds/notification.mp3';
                }
                
                audio.play().catch(() => {});
            }
        } catch (e) {
            console.debug('[Notifications] Sound play failed:', e);
        }
    }
    
    // Gestisce i messaggi flash dal server con animazioni sequenziali
    function handleServerMessages() {
        const flashMessages = document.querySelectorAll('[data-flash-message]');
        if (!flashMessages.length) return;
        
        // Mostra i messaggi con un piccolo ritardo tra loro
        flashMessages.forEach((element, index) => {
            const type = element.dataset.flashType || 'info';
            const message = element.dataset.flashMessage;
            
            // Ritardo crescente per messaggi multipli
            setTimeout(() => {
                // Mostra notifica
                showNotification(message, type);
                
                // Rimuovi elemento
                element.parentNode.removeChild(element);
            }, index * 200);
        });
    }
    
    // Utility per ottenere l'icona per il tipo di notifica
    function getIconForType(type) {
        switch (type) {
            case 'success': return 'fa-check-circle';
            case 'warning': return 'fa-exclamation-triangle';
            case 'danger': return 'fa-times-circle';
            case 'info':
            default: return 'fa-info-circle';
        }
    }
    
    // Utility per ottenere il titolo per il tipo di notifica
    function getTitleForType(type) {
        switch (type) {
            case 'success': return 'Successo';
            case 'warning': return 'Attenzione';
            case 'danger': return 'Errore';
            case 'info':
            default: return 'Informazione';
        }
    }
    
    // Aggiunge il badge per le notifiche non lette
    function initNotificationBadge() {
        // Cerca nella navbar se esiste già
        let badge = document.querySelector('#notification-badge');
        
        if (!badge) {
            // Cerca il punto di inserimento nella navbar
            const navbarRight = document.querySelector('.navbar .navbar-nav');
            
            if (navbarRight) {
                // Crea l'elemento del badge
                const notificationItem = document.createElement('li');
                notificationItem.className = 'nav-item dropdown notification-dropdown';
                
                notificationItem.innerHTML = `
                    <a class="nav-link dropdown-toggle" href="#" id="notificationDropdown" role="button" 
                       data-bs-toggle="dropdown" aria-expanded="false">
                        <i class="fas fa-bell"></i>
                        <span id="notification-badge" class="badge rounded-circle bg-danger d-none">0</span>
                    </a>
                    <div class="dropdown-menu dropdown-menu-end notification-dropdown-menu p-0" aria-labelledby="notificationDropdown">
                        <div class="notification-header d-flex justify-content-between align-items-center p-3 border-bottom">
                            <h6 class="m-0">Notifiche</h6>
                            <button id="mark-all-read" class="btn btn-sm btn-link p-0">Segna tutte come lette</button>
                        </div>
                        <div class="notification-list" style="max-height: 300px; overflow-y: auto;">
                            <div id="empty-notifications" class="text-center p-3">
                                <i class="fas fa-bell-slash text-muted"></i>
                                <p class="mb-0 mt-2">Nessuna notifica</p>
                            </div>
                            <div id="notification-items"></div>
                        </div>
                        <div class="notification-footer border-top p-2 text-center">
                            <a href="/notifications" class="btn btn-sm btn-primary">Vedi tutte</a>
                        </div>
                    </div>
                `;
                
                navbarRight.appendChild(notificationItem);
                badge = notificationItem.querySelector('#notification-badge');
                
                // Aggiungi evento per marcare tutte come lette
                const markAllReadBtn = notificationItem.querySelector('#mark-all-read');
                if (markAllReadBtn) {
                    markAllReadBtn.addEventListener('click', function(e) {
                        e.preventDefault();
                        e.stopPropagation();
                        clearUnreadNotifications();
                    });
                }
            }
        }
        
        // Aggiorna il badge iniziale
        updateNotificationBadge();
    }
    
    // Gestisce la connessione WebSocket per le notifiche real-time
    function initWebSocketConnection() {
        // Verifica se WebSocket è supportato
        if (!window.WebSocket) {
            console.warn('[Notifications] WebSocket non supportato dal browser');
            return;
        }
        
        // Determina l'URL del WebSocket (stesso host, cambio di protocollo)
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/notifications`;
        
        try {
            wsConfig.socket = new WebSocket(wsUrl);
            
            // Gestori eventi per il WebSocket
            wsConfig.socket.onopen = handleSocketOpen;
            wsConfig.socket.onmessage = handleSocketMessage;
            wsConfig.socket.onclose = handleSocketClose;
            wsConfig.socket.onerror = handleSocketError;
            
            console.debug('[Notifications] WebSocket inizializzato');
        } catch (e) {
            console.error('[Notifications] Errore nell\'inizializzazione del WebSocket:', e);
        }
    }
    
    // Gestore evento apertura connessione
    function handleSocketOpen() {
        console.debug('[Notifications] Connessione WebSocket aperta');
        wsConfig.connected = true;
        wsConfig.reconnectAttempts = 0;
        
        // Invia autenticazione
        if (wsConfig.token && wsConfig.userId) {
            wsConfig.socket.send(JSON.stringify({
                type: 'auth',
                user_id: wsConfig.userId,
                token: wsConfig.token
            }));
        }
        
        // Notifica l'utente
        if (window.showToast) {
            window.showToast('Connessione alle notifiche stabilita', 'success', {
                duration: 2000,
                sound: false
            });
        }
    }
    
    // Gestore messaggi in arrivo
    function handleSocketMessage(event) {
        try {
            const data = JSON.parse(event.data);
            
            console.debug('[Notifications] Messaggio WebSocket ricevuto:', data.type);
            
            // Gestisci i diversi tipi di messaggi
            switch (data.type) {
                case 'auth_success':
                    // Autenticazione completata
                    console.debug('[Notifications] Autenticazione WebSocket completata');
                    break;
                    
                case 'auth_error':
                    console.error('[Notifications] Errore di autenticazione WebSocket:', data.message);
                    break;
                    
                case 'unread_count':
                    // Aggiorna contatore notifiche non lette
                    unreadNotifications = data.count;
                    updateNotificationBadge();
                    break;
                    
                case 'notification':
                    // Nuova notifica in arrivo
                    handleNewNotification(data.notification);
                    break;
                    
                case 'notification_list':
                    // Lista di notifiche (usata per caricamento iniziale)
                    handleNotificationList(data.notifications);
                    break;
                    
                default:
                    console.warn('[Notifications] Tipo di messaggio WebSocket sconosciuto:', data.type);
            }
        } catch (e) {
            console.error('[Notifications] Errore nella gestione del messaggio WebSocket:', e);
        }
    }
    
    // Gestore chiusura connessione
    function handleSocketClose(event) {
        wsConfig.connected = false;
        
        console.debug(`[Notifications] Connessione WebSocket chiusa: ${event.code} ${event.reason}`);
        
        // Tentativo di riconnessione se non è stata una chiusura volontaria
        if (event.code !== 1000 && event.code !== 1001) {
            attemptReconnect();
        }
    }
    
    // Gestore errori connessione
    function handleSocketError(error) {
        console.error('[Notifications] Errore WebSocket:', error);
        
        // Non fare nulla qui, il gestore onclose verrà chiamato dopo
    }
    
    // Tentativo di riconnessione
    function attemptReconnect() {
        if (wsConfig.reconnectAttempts >= wsConfig.maxReconnectAttempts) {
            console.warn('[Notifications] Numero massimo di tentativi di riconnessione WebSocket raggiunto');
            return;
        }
        
        wsConfig.reconnectAttempts++;
        
        // Calcola ritardo con backoff esponenziale
        const delay = wsConfig.reconnectDelay * Math.pow(1.5, wsConfig.reconnectAttempts - 1);
        
        console.debug(`[Notifications] Tentativo di riconnessione WebSocket in ${delay}ms (${wsConfig.reconnectAttempts}/${wsConfig.maxReconnectAttempts})`);
        
        setTimeout(() => {
            if (!wsConfig.connected) {
                initWebSocketConnection();
            }
        }, delay);
    }
    
    // Gestisce una nuova notifica
    function handleNewNotification(notification) {
        // Aggiungi alla cronologia
        addToNotificationHistory(notification);
        
        // Incrementa contatore se non è già stato letto
        if (!notification.read) {
            unreadNotifications++;
            updateNotificationBadge();
        }
        
        // Mostra la notifica toast
        showToast(notification.message, notification.level || 'info', {
            title: notification.title || getTitleForType(notification.level || 'info'),
            duration: 5000,
            onClick: function() {
                // Se c'è un URL, naviga verso di esso
                if (notification.url) {
                    window.location.href = notification.url;
                }
            }
        });
        
        // Aggiorna la dropdown con la nuova notifica
        updateNotificationDropdown();
    }
    
    // Gestisce la lista di notifiche
    function handleNotificationList(notifications) {
        if (!Array.isArray(notifications)) return;
        
        // Aggiorna notificationHistory
        notifications.forEach(addToNotificationHistory);
        
        // Conta le non lette
        unreadNotifications = notifications.filter(n => !n.read).length;
        updateNotificationBadge();
        
        // Aggiorna la dropdown
        updateNotificationDropdown();
    }
    
    // Aggiunge una notifica alla cronologia
    function addToNotificationHistory(notification) {
        // Controlla che non sia già presente (basato su ID)
        const existingIndex = notificationHistory.findIndex(n => n.id === notification.id);
        
        if (existingIndex !== -1) {
            // Aggiorna la notifica esistente
            notificationHistory[existingIndex] = notification;
        } else {
            // Aggiungi nuova notifica all'inizio
            notificationHistory.unshift(notification);
            
            // Limita la dimensione della cronologia
            if (notificationHistory.length > MAX_NOTIFICATION_HISTORY) {
                notificationHistory.pop();
            }
        }
    }
    
    // Aggiorna il badge delle notifiche non lette
    function updateNotificationBadge() {
        const badge = document.getElementById('notification-badge');
        if (!badge) return;
        
        if (unreadNotifications > 0) {
            badge.textContent = unreadNotifications > 99 ? '99+' : unreadNotifications;
            badge.classList.remove('d-none');
        } else {
            badge.classList.add('d-none');
        }
    }
    
    // Aggiorna il dropdown delle notifiche
    function updateNotificationDropdown() {
        const notificationItems = document.getElementById('notification-items');
        const emptyNotifications = document.getElementById('empty-notifications');
        
        if (!notificationItems || !emptyNotifications) return;
        
        // Controlla se ci sono notifiche da mostrare
        if (notificationHistory.length === 0) {
            notificationItems.innerHTML = '';
            emptyNotifications.classList.remove('d-none');
            return;
        }
        
        // Mostra le notifiche
        emptyNotifications.classList.add('d-none');
        
        // Limitiamo a mostrare le ultime 10 notifiche nel dropdown
        const recentNotifications = notificationHistory.slice(0, 10);
        
        // Crea HTML
        notificationItems.innerHTML = recentNotifications.map(notification => `
            <div class="notification-item p-3 border-bottom ${notification.read ? '' : 'unread'}" data-id="${notification.id}">
                <div class="d-flex align-items-start">
                    <div class="flex-shrink-0">
                        <i class="fas ${getIconForType(notification.level || 'info')} me-2"></i>
                    </div>
                    <div class="flex-grow-1">
                        <div class="d-flex justify-content-between">
                            <strong>${notification.title || 'Notifica'}</strong>
                            <small class="text-muted">${formatNotificationTime(notification.created_at)}</small>
                        </div>
                        <p class="mb-0">${notification.message}</p>
                    </div>
                </div>
            </div>
        `).join('');
        
        // Aggiungi eventi di click
        notificationItems.querySelectorAll('.notification-item').forEach(item => {
            item.addEventListener('click', function() {
                const notificationId = this.dataset.id;
                const notification = notificationHistory.find(n => n.id == notificationId);
                
                if (notification) {
                    // Marca come letta
                    if (!notification.read) {
                        markNotificationAsRead(notificationId);
                    }
                    
                    // Naviga all'URL se presente
                    if (notification.url) {
                        window.location.href = notification.url;
                    }
                }
            });
        });
    }
    
    // Formatta il timestamp della notifica
    function formatNotificationTime(timestamp) {
        if (!timestamp) return '';
        
        const date = new Date(timestamp);
        const now = new Date();
        const diffMs = now - date;
        const diffSeconds = Math.floor(diffMs / 1000);
        const diffMinutes = Math.floor(diffSeconds / 60);
        const diffHours = Math.floor(diffMinutes / 60);
        const diffDays = Math.floor(diffHours / 24);
        
        if (diffMinutes < 1) {
            return 'Adesso';
        } else if (diffMinutes < 60) {
            return `${diffMinutes} min fa`;
        } else if (diffHours < 24) {
            return `${diffHours} ore fa`;
        } else if (diffDays < 7) {
            return `${diffDays} giorni fa`;
        } else {
            return date.toLocaleDateString();
        }
    }
    
    // Marca una notifica come letta
    function markNotificationAsRead(notificationId) {
        // Aggiorna localmente
        const index = notificationHistory.findIndex(n => n.id == notificationId);
        if (index !== -1) {
            notificationHistory[index].read = true;
            
            // Decrementa contatore se non è già 0
            if (unreadNotifications > 0) {
                unreadNotifications--;
                updateNotificationBadge();
            }
            
            // Aggiorna UI
            updateNotificationDropdown();
        }
        
        // Invia al server se connesso
        if (wsConfig.connected && wsConfig.socket) {
            wsConfig.socket.send(JSON.stringify({
                type: 'mark_read',
                notification_id: notificationId
            }));
        }
    }
    
    // Cancella tutte le notifiche non lette
    function clearUnreadNotifications() {
        // Aggiorna localmente
        notificationHistory.forEach(notification => {
            notification.read = true;
        });
        
        // Reset contatore
        unreadNotifications = 0;
        updateNotificationBadge();
        
        // Aggiorna UI
        updateNotificationDropdown();
        
        // Invia al server se connesso
        if (wsConfig.connected && wsConfig.socket) {
            wsConfig.socket.send(JSON.stringify({
                type: 'mark_all_read'
            }));
        }
    }
    
    // Invia una notifica di test (solo per sviluppo)
    function sendTestNotification() {
        const testNotification = {
            id: 'test-' + Date.now(),
            title: 'Notifica di Test',
            message: 'Questa è una notifica di test per verificare il sistema.',
            level: 'info',
            read: false,
            created_at: new Date().toISOString(),
            url: '#'
        };
        
        handleNewNotification(testNotification);
    }
    
    // Inizializza quando il DOM è pronto con prevenzione di duplicati
    if (document.readyState !== 'loading') {
        if (!window.notificationSystemInitialized) {
            window.notificationSystemInitialized = true;
            init();
        }
    } else {
        document.addEventListener('DOMContentLoaded', function() {
            if (!window.notificationSystemInitialized) {
                window.notificationSystemInitialized = true;
                init();
            }
        });
    }
})(); 