/**
 * M4Bot - Sistema di Badge e Achievement
 * Gestisce i badge, gli obiettivi e mostra le notifiche di progressi raggiunti
 */

(function() {
    'use strict';
    
    // Configurazione
    const config = {
        storageKey: 'user_achievements',
        storageCompletedKey: 'completed_achievements',
        apiEndpoint: '/api/achievements',
        notificationDuration: 6000,
        showPopups: true,
        badges: [],
        userBadges: [],
        completedAchievements: [],
        achievementTypes: {
            FOLLOWER: 'follower',
            STREAMING: 'streaming',
            MESSAGE: 'message',
            FOLLOW: 'follow',
            SUBSCRIPTION: 'subscription',
            DONATION: 'donation',
            COMMAND: 'command',
            CUSTOM: 'custom'
        }
    };
    
    // Selettori DOM
    const selectors = {
        badgeContainer: '#badges-container',
        achievementContainer: '#achievements-container',
        popupContainer: '.achievement-popup-container',
        badgeModal: '#badge-modal',
        achievementModal: '#achievement-modal'
    };
    
    /**
     * Inizializza il sistema di badge e achievement
     */
    function init() {
        // Crea il container per i popup se non esiste
        createPopupContainer();
        
        // Carica la configurazione e i badge
        loadBadges()
            .then(() => {
                // Carica i badge utente
                return loadUserBadges();
            })
            .then(() => {
                // Carica gli achievement completati
                return loadCompletedAchievements();
            })
            .then(() => {
                // Verifica se ci sono nuovi achievement da mostrare
                checkNewAchievements();
                
                // Inizializza il rendering dei badge
                renderBadges();
                
                // Inizializza i listener degli eventi
                initEventListeners();
                
                console.log('Sistema di badge e achievement inizializzato');
            })
            .catch(error => {
                console.error('Errore nell\'inizializzazione del sistema di badge:', error);
            });
    }
    
    /**
     * Crea il container per i popup
     */
    function createPopupContainer() {
        // Se esiste già, non fare nulla
        if (document.querySelector(selectors.popupContainer)) {
            return;
        }
        
        // Crea container per i popup
        const popupContainer = document.createElement('div');
        popupContainer.className = 'achievement-popup-container';
        document.body.appendChild(popupContainer);
    }
    
    /**
     * Carica i badge disponibili
     */
    async function loadBadges() {
        try {
            // Primo tentativo: API
            const response = await fetch(config.apiEndpoint);
            
            if (response.ok) {
                const data = await response.json();
                config.badges = data.badges || [];
                return;
            }
        } catch (error) {
            console.warn('Impossibile caricare i badge dall\'API, uso quelli predefiniti:', error);
        }
        
        // Fallback: badge predefiniti
        config.badges = [
            {
                id: 'streamer_novice',
                name: 'Streamer Novizio',
                description: 'Completato il primo stream',
                icon: 'play-circle',
                color: '#28a745',
                category: 'streaming',
                type: config.achievementTypes.STREAMING,
                condition: 'first_stream',
                threshold: 1,
                level: 1
            },
            {
                id: 'streamer_intermediate',
                name: 'Streamer Affermato',
                description: 'Completato 10 stream',
                icon: 'play-circle',
                color: '#17a2b8',
                category: 'streaming',
                type: config.achievementTypes.STREAMING,
                condition: 'stream_count',
                threshold: 10,
                level: 2
            },
            {
                id: 'streamer_advanced',
                name: 'Streamer Esperto',
                description: 'Completato 50 stream',
                icon: 'play-circle',
                color: '#007bff',
                category: 'streaming',
                type: config.achievementTypes.STREAMING,
                condition: 'stream_count',
                threshold: 50,
                level: 3
            },
            {
                id: 'streamer_pro',
                name: 'Streamer Professionista',
                description: 'Completato 100 stream',
                icon: 'play-circle',
                color: '#dc3545',
                category: 'streaming',
                type: config.achievementTypes.STREAMING,
                condition: 'stream_count',
                threshold: 100,
                level: 4
            },
            {
                id: 'follower_starter',
                name: 'Prime Connessioni',
                description: 'Raggiunti 10 follower',
                icon: 'users',
                color: '#28a745',
                category: 'community',
                type: config.achievementTypes.FOLLOWER,
                condition: 'follower_count',
                threshold: 10,
                level: 1
            },
            {
                id: 'follower_growing',
                name: 'Comunità in Crescita',
                description: 'Raggiunti 100 follower',
                icon: 'users',
                color: '#17a2b8',
                category: 'community',
                type: config.achievementTypes.FOLLOWER,
                condition: 'follower_count',
                threshold: 100,
                level: 2
            },
            {
                id: 'follower_popular',
                name: 'Streamer Popolare',
                description: 'Raggiunti 1000 follower',
                icon: 'users',
                color: '#007bff',
                category: 'community',
                type: config.achievementTypes.FOLLOWER,
                condition: 'follower_count',
                threshold: 1000,
                level: 3
            },
            {
                id: 'sub_starter',
                name: 'Primo Abbonato',
                description: 'Ottenuto il primo abbonato',
                icon: 'star',
                color: '#ffc107',
                category: 'subscription',
                type: config.achievementTypes.SUBSCRIPTION,
                condition: 'sub_count',
                threshold: 1,
                level: 1
            },
            {
                id: 'sub_growing',
                name: 'Abbonati in Crescita',
                description: 'Raggiunti 10 abbonati',
                icon: 'star',
                color: '#fd7e14',
                category: 'subscription',
                type: config.achievementTypes.SUBSCRIPTION,
                condition: 'sub_count',
                threshold: 10,
                level: 2
            },
            {
                id: 'sub_popular',
                name: 'Abbonati Fedeli',
                description: 'Raggiunti 50 abbonati',
                icon: 'star',
                color: '#dc3545',
                category: 'subscription',
                type: config.achievementTypes.SUBSCRIPTION,
                condition: 'sub_count',
                threshold: 50,
                level: 3
            },
            {
                id: 'chat_starter',
                name: 'Conversatore',
                description: '100 messaggi in chat',
                icon: 'comment',
                color: '#28a745',
                category: 'engagement',
                type: config.achievementTypes.MESSAGE,
                condition: 'chat_count',
                threshold: 100,
                level: 1
            },
            {
                id: 'chat_active',
                name: 'Conversatore Attivo',
                description: '1000 messaggi in chat',
                icon: 'comment',
                color: '#17a2b8',
                category: 'engagement',
                type: config.achievementTypes.MESSAGE,
                condition: 'chat_count',
                threshold: 1000,
                level: 2
            },
            {
                id: 'chat_pro',
                name: 'Re della Chat',
                description: '10000 messaggi in chat',
                icon: 'comment',
                color: '#007bff',
                category: 'engagement',
                type: config.achievementTypes.MESSAGE,
                condition: 'chat_count',
                threshold: 10000,
                level: 3
            },
            {
                id: 'hours_5',
                name: 'Maratoneta Iniziale',
                description: '5 ore di streaming',
                icon: 'clock',
                color: '#28a745',
                category: 'streaming',
                type: config.achievementTypes.STREAMING,
                condition: 'stream_hours',
                threshold: 5,
                level: 1
            },
            {
                id: 'hours_50',
                name: 'Maratoneta Intermedio',
                description: '50 ore di streaming',
                icon: 'clock',
                color: '#17a2b8',
                category: 'streaming',
                type: config.achievementTypes.STREAMING,
                condition: 'stream_hours',
                threshold: 50,
                level: 2
            },
            {
                id: 'hours_100',
                name: 'Maratoneta Esperto',
                description: '100 ore di streaming',
                icon: 'clock',
                color: '#007bff',
                category: 'streaming',
                type: config.achievementTypes.STREAMING,
                condition: 'stream_hours',
                threshold: 100,
                level: 3
            },
            {
                id: 'hours_500',
                name: 'Maratoneta Professionista',
                description: '500 ore di streaming',
                icon: 'clock',
                color: '#dc3545',
                category: 'streaming',
                type: config.achievementTypes.STREAMING,
                condition: 'stream_hours',
                threshold: 500,
                level: 4
            },
            {
                id: 'first_donation',
                name: 'Primo Supporto',
                description: 'Ricevuta la prima donazione',
                icon: 'hand-holding-usd',
                color: '#28a745',
                category: 'donation',
                type: config.achievementTypes.DONATION,
                condition: 'donation_count',
                threshold: 1,
                level: 1
            },
            {
                id: 'donation_10',
                name: 'Supporto Crescente',
                description: 'Ricevute 10 donazioni',
                icon: 'hand-holding-usd',
                color: '#17a2b8',
                category: 'donation',
                type: config.achievementTypes.DONATION,
                condition: 'donation_count',
                threshold: 10,
                level: 2
            },
            {
                id: 'donation_50',
                name: 'Supporto Sostanziale',
                description: 'Ricevute 50 donazioni',
                icon: 'hand-holding-usd',
                color: '#007bff',
                category: 'donation',
                type: config.achievementTypes.DONATION,
                condition: 'donation_count',
                threshold: 50,
                level: 3
            }
        ];
    }
    
    /**
     * Carica i badge dell'utente
     */
    async function loadUserBadges() {
        try {
            // Tenta caricamento dall'API
            const response = await fetch(`${config.apiEndpoint}/user`);
            
            if (response.ok) {
                const data = await response.json();
                config.userBadges = data.badges || [];
                return;
            }
        } catch (error) {
            console.warn('Impossibile caricare i badge utente dall\'API, uso il localStorage:', error);
        }
        
        // Fallback: localStorage
        try {
            const savedBadges = localStorage.getItem(config.storageKey);
            if (savedBadges) {
                config.userBadges = JSON.parse(savedBadges);
            } else {
                config.userBadges = [];
            }
        } catch (error) {
            console.error('Errore nel parsing dei badge dell\'utente dal localStorage:', error);
            config.userBadges = [];
        }
    }
    
    /**
     * Carica gli achievement completati dell'utente
     */
    async function loadCompletedAchievements() {
        try {
            // Tenta caricamento dall'API
            const response = await fetch(`${config.apiEndpoint}/completed`);
            
            if (response.ok) {
                const data = await response.json();
                config.completedAchievements = data.achievements || [];
                return;
            }
        } catch (error) {
            console.warn('Impossibile caricare gli achievement completati dall\'API, uso il localStorage:', error);
        }
        
        // Fallback: localStorage
        try {
            const savedAchievements = localStorage.getItem(config.storageCompletedKey);
            if (savedAchievements) {
                config.completedAchievements = JSON.parse(savedAchievements);
            } else {
                config.completedAchievements = [];
            }
        } catch (error) {
            console.error('Errore nel parsing degli achievement completati dal localStorage:', error);
            config.completedAchievements = [];
        }
    }
    
    /**
     * Verifica se ci sono nuovi achievement da mostrare
     */
    function checkNewAchievements() {
        // Filtra gli achievement completati che non sono ancora stati mostrati
        const newAchievements = config.completedAchievements.filter(achievement => !achievement.shown);
        
        // Se ci sono nuovi achievement, mostra i popup
        if (newAchievements.length > 0 && config.showPopups) {
            // Mostra i popup con un ritardo tra loro
            newAchievements.forEach((achievement, index) => {
                setTimeout(() => {
                    showAchievementPopup(achievement);
                    
                    // Marca come mostrato
                    achievement.shown = true;
                }, index * 3000); // 3 secondi di ritardo tra i popup
            });
            
            // Aggiorna gli achievement completati
            saveCompletedAchievements();
        }
    }
    
    /**
     * Inizializza i listener degli eventi
     */
    function initEventListeners() {
        // Listener per eventi dal server (WebSocket)
        initWebSocketListener();
        
        // Listener per le interazioni dell'utente
        document.addEventListener('click', function(event) {
            // Gestione click sui badge
            if (event.target.closest('.badge-item')) {
                const badgeItem = event.target.closest('.badge-item');
                const badgeId = badgeItem.getAttribute('data-badge-id');
                
                if (badgeId) {
                    showBadgeDetails(badgeId);
                }
            }
            
            // Gestione click sugli achievement
            if (event.target.closest('.achievement-item')) {
                const achievementItem = event.target.closest('.achievement-item');
                const achievementId = achievementItem.getAttribute('data-achievement-id');
                
                if (achievementId) {
                    showAchievementDetails(achievementId);
                }
            }
        });
    }
    
    /**
     * Inizializza il listener WebSocket per eventi dal server
     */
    function initWebSocketListener() {
        // Se WebSocket non è supportato, esci
        if (!window.WebSocket) {
            return;
        }
        
        // Controlla se esiste già una connessione WebSocket in app.js
        if (window.appWebSocket) {
            // Aggiungi handler per eventi achievement
            window.addEventListener('websocket-message', function(e) {
                const message = e.detail;
                
                // Controlla se è un evento di achievement
                if (message.type === 'achievement') {
                    handleAchievementEvent(message.data);
                }
            });
        } else {
            // Crea una nuova connessione WebSocket
            try {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/achievements`;
                
                const socket = new WebSocket(wsUrl);
                
                socket.onmessage = function(event) {
                    try {
                        const message = JSON.parse(event.data);
                        
                        // Gestisci evento
                        if (message.type === 'achievement') {
                            handleAchievementEvent(message.data);
                        }
                    } catch (error) {
                        console.error('Errore nella gestione del messaggio WebSocket:', error);
                    }
                };
                
                socket.onopen = function() {
                    console.log('Connessione WebSocket per achievement stabilita');
                };
                
                socket.onerror = function(error) {
                    console.error('Errore WebSocket:', error);
                };
                
                socket.onclose = function() {
                    console.log('Connessione WebSocket per achievement chiusa');
                    // Riconnessione dopo un ritardo
                    setTimeout(initWebSocketListener, 3000);
                };
            } catch (error) {
                console.error('Errore nella creazione della connessione WebSocket:', error);
            }
        }
    }
    
    /**
     * Gestisce un evento di achievement
     */
    function handleAchievementEvent(data) {
        // Verifica il tipo di evento
        if (data.event === 'new_achievement') {
            // Nuovo achievement sbloccato
            const achievement = data.achievement;
            
            // Aggiungi l'achievement alla lista dei completati se non è già presente
            if (!config.completedAchievements.some(a => a.id === achievement.id)) {
                config.completedAchievements.push({
                    id: achievement.id,
                    date: new Date().toISOString(),
                    shown: false
                });
                
                // Salva gli achievement completati
                saveCompletedAchievements();
                
                // Mostra il popup
                if (config.showPopups) {
                    showAchievementPopup(achievement);
                }
                
                // Aggiorna UI
                renderBadges();
            }
        } else if (data.event === 'progress_update') {
            // Aggiornamento del progresso di un achievement
            updateAchievementProgress(data.achievement, data.progress);
        }
    }
    
    /**
     * Aggiorna il progresso di un achievement
     */
    function updateAchievementProgress(achievementId, progress) {
        // Trova l'achievement
        const achievement = config.badges.find(badge => badge.id === achievementId);
        if (!achievement) return;
        
        // Aggiorna il progresso nell'UI
        const progressElement = document.querySelector(`.achievement-progress[data-achievement-id="${achievementId}"]`);
        if (progressElement) {
            // Calcola la percentuale
            const percent = Math.min(100, Math.round((progress / achievement.threshold) * 100));
            
            // Aggiorna la barra di progresso
            const progressBar = progressElement.querySelector('.progress-bar');
            if (progressBar) {
                progressBar.style.width = `${percent}%`;
                progressBar.setAttribute('aria-valuenow', percent);
                
                // Aggiorna testo
                const progressText = progressElement.querySelector('.progress-text');
                if (progressText) {
                    progressText.textContent = `${progress}/${achievement.threshold}`;
                }
            }
        }
    }
    
    /**
     * Mostra un popup per un achievement appena sbloccato
     */
    function showAchievementPopup(achievement) {
        // Se l'achievement è un oggetto con ID, trova i dettagli completi
        if (typeof achievement === 'object' && achievement.id) {
            const achievementId = achievement.id;
            const fullAchievement = config.badges.find(badge => badge.id === achievementId);
            
            if (fullAchievement) {
                achievement = fullAchievement;
            }
        }
        
        // Crea l'elemento popup
        const popupElement = document.createElement('div');
        popupElement.className = 'achievement-popup';
        popupElement.innerHTML = `
            <div class="achievement-popup-icon" style="background-color: ${achievement.color || '#007bff'}">
                <i class="fas fa-${achievement.icon || 'award'}"></i>
            </div>
            <div class="achievement-popup-content">
                <h4 class="achievement-popup-title">Achievement Sbloccato!</h4>
                <h5>${achievement.name}</h5>
                <p>${achievement.description}</p>
            </div>
            <button type="button" class="achievement-popup-close" title="Chiudi">×</button>
        `;
        
        // Aggiungi evento di chiusura
        const closeButton = popupElement.querySelector('.achievement-popup-close');
        closeButton.addEventListener('click', function() {
            removePopup(popupElement);
        });
        
        // Aggiungi al container
        const popupContainer = document.querySelector(selectors.popupContainer);
        popupContainer.appendChild(popupElement);
        
        // Animazione di entrata
        setTimeout(() => {
            popupElement.classList.add('show');
        }, 10);
        
        // Riproduci suono (se configurato e disponibile)
        playAchievementSound();
        
        // Rimuovi automaticamente dopo il timeout
        setTimeout(() => {
            removePopup(popupElement);
        }, config.notificationDuration);
        
        // Funzione per rimuovere il popup con animazione
        function removePopup(element) {
            element.classList.remove('show');
            element.classList.add('hide');
            
            // Rimuovi l'elemento dopo l'animazione
            setTimeout(() => {
                if (element.parentNode) {
                    element.parentNode.removeChild(element);
                }
            }, 300);
        }
    }
    
    /**
     * Riproduce un suono per l'achievement sbloccato
     */
    function playAchievementSound() {
        try {
            const sound = new Audio('/static/sounds/achievement.mp3');
            sound.volume = 0.5;
            sound.play().catch(e => console.log('Errore nella riproduzione del suono:', e));
        } catch (error) {
            console.log('Suono non supportato:', error);
        }
    }
    
    /**
     * Renderizza i badge nella pagina
     */
    function renderBadges() {
        // Trova i container di badge e achievement
        const badgeContainer = document.querySelector(selectors.badgeContainer);
        const achievementContainer = document.querySelector(selectors.achievementContainer);
        
        // Se non ci sono container, esci
        if (!badgeContainer && !achievementContainer) {
            return;
        }
        
        // Renderizza badge ottenuti
        if (badgeContainer) {
            renderUserBadges(badgeContainer);
        }
        
        // Renderizza achievement (ottenuti e da ottenere)
        if (achievementContainer) {
            renderAchievements(achievementContainer);
        }
    }
    
    /**
     * Renderizza i badge dell'utente
     */
    function renderUserBadges(container) {
        // Svuota il container
        container.innerHTML = '';
        
        // Ottieni i badge dell'utente (ID dei badge ottenuti)
        const userBadgeIds = config.userBadges.map(badge => badge.id);
        
        // Filtra i badge ottenuti
        const earnedBadges = config.badges.filter(badge => userBadgeIds.includes(badge.id));
        
        // Se non ci sono badge ottenuti, mostra un messaggio
        if (earnedBadges.length === 0) {
            container.innerHTML = `
                <div class="text-center py-4">
                    <i class="fas fa-award fa-3x text-muted mb-3"></i>
                    <h5>Nessun Badge Ottenuto</h5>
                    <p class="text-muted">Continua a streamare per sbloccare badge!</p>
                </div>
            `;
            return;
        }
        
        // Crea gli elementi badge
        earnedBadges.forEach(badge => {
            const badgeElement = document.createElement('div');
            badgeElement.className = 'col-md-3 col-sm-4 col-6 mb-4';
            badgeElement.innerHTML = `
                <div class="badge-item" data-badge-id="${badge.id}">
                    <div class="badge-icon" style="background-color: ${badge.color || '#007bff'}">
                        <i class="fas fa-${badge.icon || 'award'}"></i>
                    </div>
                    <h5 class="badge-name">${badge.name}</h5>
                    <p class="badge-description">${badge.description}</p>
                </div>
            `;
            
            container.appendChild(badgeElement);
        });
    }
    
    /**
     * Renderizza gli achievement (ottenuti e da ottenere)
     */
    function renderAchievements(container) {
        // Svuota il container
        container.innerHTML = '';
        
        // ID degli achievement completati
        const completedIds = config.completedAchievements.map(a => a.id);
        
        // Raggruppa gli achievement per categoria
        const categories = {};
        config.badges.forEach(badge => {
            const category = badge.category || 'other';
            if (!categories[category]) {
                categories[category] = [];
            }
            categories[category].push(badge);
        });
        
        // Crea gli elementi per categoria
        Object.keys(categories).forEach(category => {
            const badges = categories[category];
            
            // Crea sezione categoria
            const categoryElement = document.createElement('div');
            categoryElement.className = 'achievement-category mb-5';
            
            // Titolo categoria (formatta la prima lettera maiuscola)
            const categoryTitle = category.charAt(0).toUpperCase() + category.slice(1);
            
            categoryElement.innerHTML = `
                <h3 class="achievement-category-title mb-4">${categoryTitle}</h3>
                <div class="row" id="category-${category}"></div>
            `;
            
            // Aggiungi gli achievement della categoria
            const categoryContainer = categoryElement.querySelector(`#category-${category}`);
            
            badges.forEach(badge => {
                const isCompleted = completedIds.includes(badge.id);
                const achievementElement = document.createElement('div');
                achievementElement.className = 'col-md-4 col-sm-6 mb-4';
                
                // Trova dettagli progresso per achievement non completati
                let progressHtml = '';
                if (!isCompleted && badge.threshold) {
                    // TODO: recuperare il progresso effettivo dall'API
                    const currentProgress = 0; // Valore esempio
                    const percent = Math.min(100, Math.round((currentProgress / badge.threshold) * 100));
                    
                    progressHtml = `
                        <div class="achievement-progress" data-achievement-id="${badge.id}">
                            <div class="progress">
                                <div class="progress-bar" role="progressbar" style="width: ${percent}%" 
                                     aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100"></div>
                            </div>
                            <div class="progress-text">${currentProgress}/${badge.threshold}</div>
                        </div>
                    `;
                }
                
                achievementElement.innerHTML = `
                    <div class="achievement-item ${isCompleted ? 'completed' : ''}" data-achievement-id="${badge.id}">
                        <div class="achievement-icon" style="background-color: ${badge.color || '#007bff'}">
                            <i class="fas fa-${badge.icon || 'award'}"></i>
                            ${isCompleted ? '<div class="achievement-completed-badge"><i class="fas fa-check"></i></div>' : ''}
                        </div>
                        <h5 class="achievement-name">${badge.name}</h5>
                        <p class="achievement-description">${badge.description}</p>
                        ${progressHtml}
                    </div>
                `;
                
                categoryContainer.appendChild(achievementElement);
            });
            
            container.appendChild(categoryElement);
        });
    }
    
    /**
     * Mostra i dettagli di un badge
     */
    function showBadgeDetails(badgeId) {
        // Trova il badge
        const badge = config.badges.find(b => b.id === badgeId);
        if (!badge) return;
        
        // Trova il modale o crealo se non esiste
        let modal = document.querySelector(selectors.badgeModal);
        
        if (!modal) {
            modal = document.createElement('div');
            modal.className = 'modal fade';
            modal.id = 'badge-modal';
            modal.tabIndex = '-1';
            modal.setAttribute('aria-labelledby', 'badge-modal-title');
            modal.setAttribute('aria-hidden', 'true');
            
            modal.innerHTML = `
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="badge-modal-title">Dettagli Badge</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Chiudi"></button>
                        </div>
                        <div class="modal-body">
                            <!-- Contenuto dinamico -->
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Chiudi</button>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
        }
        
        // Popolamento del modale con i dettagli del badge
        const modalBody = modal.querySelector('.modal-body');
        
        // Trova la data di ottenimento
        const badgeData = config.userBadges.find(b => b.id === badgeId);
        const earnedDate = badgeData ? new Date(badgeData.date).toLocaleDateString() : 'N/A';
        
        modalBody.innerHTML = `
            <div class="text-center mb-4">
                <div class="badge-icon-large mx-auto mb-3" style="background-color: ${badge.color || '#007bff'}">
                    <i class="fas fa-${badge.icon || 'award'}"></i>
                </div>
                <h2>${badge.name}</h2>
                <p class="lead">${badge.description}</p>
                <div class="badge-details mt-4">
                    <div class="row">
                        <div class="col-6">
                            <h6>Categoria</h6>
                            <p>${badge.category ? badge.category.charAt(0).toUpperCase() + badge.category.slice(1) : 'Altro'}</p>
                        </div>
                        <div class="col-6">
                            <h6>Livello</h6>
                            <p>${badge.level || 1}</p>
                        </div>
                        <div class="col-12">
                            <h6>Ottenuto il</h6>
                            <p>${earnedDate}</p>
                        </div>
                    </div>
                </div>
            </div>
        `;
        
        // Mostra il modale
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
    }
    
    /**
     * Mostra i dettagli di un achievement
     */
    function showAchievementDetails(achievementId) {
        // Trova l'achievement
        const achievement = config.badges.find(b => b.id === achievementId);
        if (!achievement) return;
        
        // Trova il modale o crealo se non esiste
        let modal = document.querySelector(selectors.achievementModal);
        
        if (!modal) {
            modal = document.createElement('div');
            modal.className = 'modal fade';
            modal.id = 'achievement-modal';
            modal.tabIndex = '-1';
            modal.setAttribute('aria-labelledby', 'achievement-modal-title');
            modal.setAttribute('aria-hidden', 'true');
            
            modal.innerHTML = `
                <div class="modal-dialog">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h5 class="modal-title" id="achievement-modal-title">Dettagli Achievement</h5>
                            <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Chiudi"></button>
                        </div>
                        <div class="modal-body">
                            <!-- Contenuto dinamico -->
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Chiudi</button>
                        </div>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
        }
        
        // Popolamento del modale con i dettagli dell'achievement
        const modalBody = modal.querySelector('.modal-body');
        
        // Controlla se è completato
        const isCompleted = config.completedAchievements.some(a => a.id === achievementId);
        const completedData = config.completedAchievements.find(a => a.id === achievementId);
        const completedDate = completedData ? new Date(completedData.date).toLocaleDateString() : 'Non ancora';
        
        // TODO: recuperare il progresso effettivo dall'API
        const currentProgress = 0; // Valore esempio
        const percent = achievement.threshold ? Math.min(100, Math.round((currentProgress / achievement.threshold) * 100)) : 0;
        
        let progressHtml = '';
        if (!isCompleted && achievement.threshold) {
            progressHtml = `
                <div class="achievement-progress-detail mt-4">
                    <h6>Progresso</h6>
                    <div class="progress">
                        <div class="progress-bar" role="progressbar" style="width: ${percent}%" 
                             aria-valuenow="${percent}" aria-valuemin="0" aria-valuemax="100"></div>
                    </div>
                    <div class="progress-text text-center mt-1">${currentProgress}/${achievement.threshold}</div>
                </div>
            `;
        }
        
        modalBody.innerHTML = `
            <div class="text-center mb-4">
                <div class="badge-icon-large mx-auto mb-3 ${isCompleted ? 'completed' : ''}" 
                     style="background-color: ${achievement.color || '#007bff'}">
                    <i class="fas fa-${achievement.icon || 'award'}"></i>
                    ${isCompleted ? '<div class="achievement-completed-badge"><i class="fas fa-check"></i></div>' : ''}
                </div>
                <h2>${achievement.name}</h2>
                <p class="lead">${achievement.description}</p>
                <div class="achievement-details mt-4">
                    <div class="row">
                        <div class="col-6">
                            <h6>Categoria</h6>
                            <p>${achievement.category ? achievement.category.charAt(0).toUpperCase() + achievement.category.slice(1) : 'Altro'}</p>
                        </div>
                        <div class="col-6">
                            <h6>Livello</h6>
                            <p>${achievement.level || 1}</p>
                        </div>
                        <div class="col-12">
                            <h6>Completato</h6>
                            <p>${isCompleted ? completedDate : 'Non ancora completato'}</p>
                        </div>
                    </div>
                    ${progressHtml}
                </div>
            </div>
        `;
        
        // Mostra il modale
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
    }
    
    /**
     * Salva gli achievement completati
     */
    function saveCompletedAchievements() {
        localStorage.setItem(config.storageCompletedKey, JSON.stringify(config.completedAchievements));
    }
    
    // Stili CSS per i popup e badge
    function addStyles() {
        if (document.getElementById('achievement-styles')) return;
        
        const styleElement = document.createElement('style');
        styleElement.id = 'achievement-styles';
        styleElement.textContent = `
            /* Container per popup achievement */
            .achievement-popup-container {
                position: fixed;
                top: 20px;
                right: 20px;
                width: 300px;
                z-index: 9999;
            }
            
            /* Popup achievement */
            .achievement-popup {
                background-color: var(--card-bg, #fff);
                border-radius: 8px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                display: flex;
                margin-bottom: 10px;
                opacity: 0;
                overflow: hidden;
                position: relative;
                transform: translateX(100%);
                transition: all 0.3s ease;
            }
            
            .achievement-popup.show {
                opacity: 1;
                transform: translateX(0);
            }
            
            .achievement-popup.hide {
                opacity: 0;
                transform: translateX(100%);
            }
            
            .achievement-popup-icon {
                align-items: center;
                background-color: #007bff;
                color: #fff;
                display: flex;
                font-size: 24px;
                justify-content: center;
                padding: 15px;
                width: 60px;
            }
            
            .achievement-popup-content {
                flex: 1;
                padding: 12px 15px;
            }
            
            .achievement-popup-title {
                color: var(--bs-primary, #007bff);
                font-size: 14px;
                font-weight: 600;
                margin: 0 0 4px 0;
            }
            
            .achievement-popup-content h5 {
                font-size: 16px;
                margin: 0 0 8px 0;
            }
            
            .achievement-popup-content p {
                color: var(--text-secondary, #6c757d);
                font-size: 13px;
                margin: 0;
            }
            
            .achievement-popup-close {
                background: none;
                border: none;
                color: var(--text-secondary, #6c757d);
                cursor: pointer;
                font-size: 20px;
                line-height: 1;
                padding: 5px;
                position: absolute;
                right: 5px;
                top: 5px;
            }
            
            /* Stili per i badge */
            .badge-item {
                background-color: var(--card-bg, #fff);
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                cursor: pointer;
                padding: 20px;
                text-align: center;
                transition: all 0.2s ease;
            }
            
            .badge-item:hover {
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                transform: translateY(-5px);
            }
            
            .badge-icon {
                align-items: center;
                background-color: #007bff;
                border-radius: 50%;
                color: #fff;
                display: flex;
                font-size: 30px;
                height: 80px;
                justify-content: center;
                margin: 0 auto 15px;
                width: 80px;
            }
            
            .badge-name {
                font-size: 16px;
                margin-bottom: 10px;
            }
            
            .badge-description {
                color: var(--text-secondary, #6c757d);
                font-size: 13px;
                margin-bottom: 0;
            }
            
            /* Stili per gli achievement */
            .achievement-item {
                background-color: var(--card-bg, #fff);
                border-radius: 8px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                cursor: pointer;
                padding: 20px;
                text-align: center;
                transition: all 0.2s ease;
                position: relative;
            }
            
            .achievement-item:hover {
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                transform: translateY(-5px);
            }
            
            .achievement-item.completed {
                background-color: rgba(var(--success-rgb, 40, 167, 69), 0.1);
            }
            
            .achievement-icon {
                align-items: center;
                background-color: #007bff;
                border-radius: 50%;
                color: #fff;
                display: flex;
                font-size: 25px;
                height: 70px;
                justify-content: center;
                margin: 0 auto 15px;
                position: relative;
                width: 70px;
            }
            
            .achievement-completed-badge {
                align-items: center;
                background-color: var(--bs-success, #28a745);
                border-radius: 50%;
                bottom: -5px;
                color: #fff;
                display: flex;
                font-size: 12px;
                height: 25px;
                justify-content: center;
                position: absolute;
                right: -5px;
                width: 25px;
            }
            
            .achievement-name {
                font-size: 16px;
                margin-bottom: 8px;
            }
            
            .achievement-description {
                color: var(--text-secondary, #6c757d);
                font-size: 13px;
                margin-bottom: 10px;
            }
            
            .achievement-progress {
                margin-top: 10px;
            }
            
            .achievement-progress .progress {
                height: 8px;
                margin-bottom: 5px;
            }
            
            .achievement-progress .progress-text {
                color: var(--text-secondary, #6c757d);
                font-size: 12px;
                text-align: center;
            }
            
            .achievement-category-title {
                border-bottom: 1px solid var(--border-color, rgba(0,0,0,.125));
                font-size: 1.5rem;
                margin-bottom: 1.5rem;
                padding-bottom: 0.5rem;
            }
            
            /* Stili per dettagli popup */
            .badge-icon-large {
                align-items: center;
                background-color: #007bff;
                border-radius: 50%;
                color: #fff;
                display: flex;
                font-size: 40px;
                height: 120px;
                justify-content: center;
                margin-bottom: 20px;
                position: relative;
                width: 120px;
            }
            
            .badge-icon-large.completed .achievement-completed-badge {
                font-size: 16px;
                height: 35px;
                width: 35px;
            }
            
            .achievement-progress-detail .progress {
                height: 12px;
            }
            
            /* Media query */
            @media (max-width: 576px) {
                .achievement-popup-container {
                    bottom: 20px;
                    left: 20px;
                    right: 20px;
                    top: auto;
                    width: auto;
                }
            }
        `;
        
        document.head.appendChild(styleElement);
    }
    
    // Aggiungi gli stili CSS
    addStyles();
    
    // Inizializza il sistema
    document.addEventListener('DOMContentLoaded', init);
    
    // Esponi l'API pubblica
    window.achievementSystem = {
        showPopup: showAchievementPopup,
        enablePopups: function(enabled) {
            config.showPopups = enabled;
        },
        refreshBadges: renderBadges,
        getBadges: function() {
            return config.userBadges;
        },
        getAchievements: function() {
            return config.completedAchievements;
        }
    };
})(); 