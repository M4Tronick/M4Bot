/**
 * M4Bot - Dashboard Customizer
 * Implementazione avanzata per la personalizzazione della dashboard
 * con funzionalità drag-and-drop e gestione widget
 */

(function() {
    'use strict';
    
    // Configurazione
    const config = {
        storageKey: 'dashboard_layout',
        widgetsListKey: 'available_widgets',
        editMode: false,
        gridster: null,
        widgets: [],
        availableWidgets: [],
        breakpoints: {
            xs: 576,
            sm: 768,
            md: 992,
            lg: 1200
        }
    };
    
    // Selettori DOM
    const selectors = {
        dashboard: '#dashboard-container',
        widgets: '.dashboard-widget',
        editButton: '#edit-dashboard',
        saveButton: '#save-dashboard',
        cancelButton: '#cancel-dashboard-edit',
        addWidgetButton: '#add-widget',
        widgetModal: '#widget-modal',
        widgetsList: '#widgets-list',
        widgetTemplate: '#widget-template'
    };
    
    /**
     * Inizializza il customizer della dashboard
     */
    function init() {
        // Verifica se la dashboard è presente
        const dashboardContainer = document.querySelector(selectors.dashboard);
        if (!dashboardContainer) return;
        
        // Carica il layout salvato o usa quello predefinito
        loadDashboardLayout();
        
        // Carica i widget disponibili
        loadAvailableWidgets();
        
        // Inizializza i pulsanti
        initButtons();
        
        // Inizializza gli eventi
        initEvents();
        
        console.log('Dashboard Customizer inizializzato');
    }
    
    /**
     * Inizializza i pulsanti di controllo
     */
    function initButtons() {
        // Bottone per attivare/disattivare la modalità modifica
        const editButton = document.querySelector(selectors.editButton);
        if (editButton) {
            editButton.addEventListener('click', toggleEditMode);
        }
        
        // Bottone per salvare il layout
        const saveButton = document.querySelector(selectors.saveButton);
        if (saveButton) {
            saveButton.addEventListener('click', saveDashboardLayout);
        }
        
        // Bottone per annullare le modifiche
        const cancelButton = document.querySelector(selectors.cancelButton);
        if (cancelButton) {
            cancelButton.addEventListener('click', cancelEdit);
        }
        
        // Bottone per aggiungere un widget
        const addWidgetButton = document.querySelector(selectors.addWidgetButton);
        if (addWidgetButton) {
            addWidgetButton.addEventListener('click', showWidgetModal);
        }
    }
    
    /**
     * Inizializza gli eventi
     */
    function initEvents() {
        // Evento resize della finestra
        window.addEventListener('resize', debounce(handleResize, 250));
        
        // Evento per il filtro dei widget nel modale
        const widgetSearch = document.querySelector('#widget-search');
        if (widgetSearch) {
            widgetSearch.addEventListener('input', filterWidgets);
        }
    }
    
    /**
     * Attiva/disattiva la modalità di modifica
     */
    function toggleEditMode() {
        const dashboardContainer = document.querySelector(selectors.dashboard);
        if (!dashboardContainer) return;
        
        config.editMode = !config.editMode;
        
        if (config.editMode) {
            // Attiva la modalità modifica
            dashboardContainer.classList.add('edit-mode');
            
            // Mostra i pulsanti di salvataggio e annullamento
            document.querySelector(selectors.saveButton).classList.remove('d-none');
            document.querySelector(selectors.cancelButton).classList.remove('d-none');
            document.querySelector(selectors.addWidgetButton).classList.remove('d-none');
            document.querySelector(selectors.editButton).classList.add('d-none');
            
            // Inizializza Gridster se non è già stato fatto
            initGridster();
            
            // Notifica l'utente
            if (window.showActionFeedback) {
                showActionFeedback('info', 'Modalità modifica dashboard attivata', 3000);
            }
        } else {
            // Disattiva la modalità modifica
            dashboardContainer.classList.remove('edit-mode');
            
            // Nascondi i pulsanti di salvataggio e annullamento
            document.querySelector(selectors.saveButton).classList.add('d-none');
            document.querySelector(selectors.cancelButton).classList.add('d-none');
            document.querySelector(selectors.addWidgetButton).classList.add('d-none');
            document.querySelector(selectors.editButton).classList.remove('d-none');
            
            // Disattiva Gridster
            if (config.gridster) {
                config.gridster.disable();
            }
        }
    }
    
    /**
     * Inizializza Gridster per il drag-and-drop
     */
    function initGridster() {
        // Se Gridster è già inizializzato, semplicemente attivalo
        if (config.gridster) {
            config.gridster.enable();
            return;
        }
        
        // Inizializza Gridster
        const dashboardContainer = document.querySelector(selectors.dashboard);
        
        // Calcola la larghezza ideale della griglia in base alla dimensione del container
        const containerWidth = dashboardContainer.offsetWidth;
        const gridCols = calculateGridCols(containerWidth);
        
        // Configura Gridster
        config.gridster = new Gridster({
            element: dashboardContainer,
            draggable: {
                handle: '.widget-header',
                start: function(e, ui) {
                    ui.helper.addClass('dragging');
                },
                stop: function(e, ui) {
                    ui.helper.removeClass('dragging');
                }
            },
            resize: {
                enabled: true,
                handle: '.resize-handle',
                start: function(e, ui) {
                    ui.element.addClass('resizing');
                },
                stop: function(e, ui) {
                    ui.element.removeClass('resizing');
                    // Aggiorna il contenuto del widget dopo il ridimensionamento
                    const widgetId = ui.element.getAttribute('data-widget-id');
                    refreshWidgetContent(widgetId);
                }
            },
            min_cols: gridCols,
            max_cols: gridCols,
            min_rows: 3,
            widget_selector: selectors.widgets,
            widget_margins: [10, 10],
            widget_base_dimensions: [Math.floor((containerWidth - 20) / gridCols) - 20, 100]
        });
        
        // Abilita la modifica
        config.gridster.enable();
    }
    
    /**
     * Calcola il numero di colonne in base alla larghezza del container
     */
    function calculateGridCols(width) {
        if (width < config.breakpoints.xs) return 1;
        if (width < config.breakpoints.sm) return 2;
        if (width < config.breakpoints.md) return 3;
        if (width < config.breakpoints.lg) return 4;
        return 6;
    }
    
    /**
     * Gestisce il ridimensionamento della finestra
     */
    function handleResize() {
        if (!config.gridster) return;
        
        // Ricalcola il layout della griglia
        const dashboardContainer = document.querySelector(selectors.dashboard);
        const containerWidth = dashboardContainer.offsetWidth;
        const gridCols = calculateGridCols(containerWidth);
        
        // Aggiorna le dimensioni di Gridster
        config.gridster.set_options({
            min_cols: gridCols,
            max_cols: gridCols,
            widget_base_dimensions: [Math.floor((containerWidth - 20) / gridCols) - 20, 100]
        });
        
        // Rigenera il layout
        config.gridster.generate_grid_and_stylesheet();
        config.gridster.init();
    }
    
    /**
     * Mostra il modale per aggiungere un widget
     */
    function showWidgetModal() {
        const modal = document.querySelector(selectors.widgetModal);
        if (!modal) return;
        
        // Popola la lista di widget disponibili
        populateWidgetsList();
        
        // Mostra il modale
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
    }
    
    /**
     * Popola la lista di widget disponibili nel modale
     */
    function populateWidgetsList() {
        const widgetsList = document.querySelector(selectors.widgetsList);
        if (!widgetsList) return;
        
        // Svuota la lista
        widgetsList.innerHTML = '';
        
        // Aggiungi widget disponibili
        config.availableWidgets.forEach(widget => {
            // Crea l'elemento widget
            const widgetItem = document.createElement('div');
            widgetItem.className = 'col-md-4 mb-3';
            widgetItem.innerHTML = `
                <div class="card h-100 widget-card">
                    <div class="card-body text-center">
                        <i class="fas fa-${widget.icon} fa-2x mb-3 text-primary"></i>
                        <h5 class="card-title">${widget.title}</h5>
                        <p class="card-text small">${widget.description}</p>
                        <button class="btn btn-sm btn-primary mt-2 add-widget-btn" data-widget-type="${widget.type}">
                            <i class="fas fa-plus me-1"></i>Aggiungi
                        </button>
                    </div>
                </div>
            `;
            
            // Aggiungi evento per il pulsante di aggiunta
            const addButton = widgetItem.querySelector('.add-widget-btn');
            addButton.addEventListener('click', () => {
                addWidget(widget);
                // Chiudi il modale
                const modal = document.querySelector(selectors.widgetModal);
                const modalInstance = bootstrap.Modal.getInstance(modal);
                modalInstance.hide();
            });
            
            // Aggiungi alla lista
            widgetsList.appendChild(widgetItem);
        });
    }
    
    /**
     * Filtra i widget nel modale
     */
    function filterWidgets(event) {
        const searchTerm = event.target.value.toLowerCase();
        const widgetCards = document.querySelectorAll('.widget-card');
        
        widgetCards.forEach(card => {
            const title = card.querySelector('.card-title').textContent.toLowerCase();
            const description = card.querySelector('.card-text').textContent.toLowerCase();
            
            if (title.includes(searchTerm) || description.includes(searchTerm)) {
                card.closest('.col-md-4').style.display = '';
            } else {
                card.closest('.col-md-4').style.display = 'none';
            }
        });
    }
    
    /**
     * Aggiunge un nuovo widget alla dashboard
     */
    function addWidget(widget) {
        if (!config.gridster) return;
        
        // Genera un ID univoco per il widget
        const widgetId = 'widget-' + Date.now();
        
        // Crea l'elemento widget
        const widgetElement = document.createElement('div');
        widgetElement.className = 'dashboard-widget';
        widgetElement.setAttribute('data-widget-id', widgetId);
        widgetElement.setAttribute('data-widget-type', widget.type);
        
        // Default size
        const size = widget.defaultSize || { rows: 2, cols: 2 };
        
        // Aggiungi contenuto del widget
        widgetElement.innerHTML = `
            <div class="widget-wrapper">
                <div class="widget-header">
                    <h3 class="widget-title">
                        <i class="fas fa-${widget.icon} me-2"></i>${widget.title}
                    </h3>
                    <div class="widget-controls">
                        <button class="btn btn-sm widget-refresh" title="Aggiorna widget">
                            <i class="fas fa-sync-alt"></i>
                        </button>
                        <button class="btn btn-sm widget-remove" title="Rimuovi widget">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>
                <div class="widget-body">
                    <div class="widget-content">
                        <div class="widget-loading">
                            <div class="spinner-border text-primary" role="status">
                                <span class="visually-hidden">Caricamento...</span>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="resize-handle"></div>
            </div>
        `;
        
        // Aggiungi evento per il pulsante di rimozione
        const removeButton = widgetElement.querySelector('.widget-remove');
        removeButton.addEventListener('click', function() {
            removeWidget(widgetElement);
        });
        
        // Aggiungi evento per il pulsante di refresh
        const refreshButton = widgetElement.querySelector('.widget-refresh');
        refreshButton.addEventListener('click', function() {
            refreshWidgetContent(widgetId);
        });
        
        // Aggiungi il widget a Gridster
        config.gridster.add_widget(widgetElement, size.cols, size.rows);
        
        // Aggiungi ai widget configurati
        config.widgets.push({
            id: widgetId,
            type: widget.type,
            title: widget.title,
            icon: widget.icon,
            size: size
        });
        
        // Carica il contenuto del widget
        loadWidgetContent(widgetId, widget.type);
        
        // Notifica l'utente
        if (window.showActionFeedback) {
            showActionFeedback('success', `Widget "${widget.title}" aggiunto!`, 3000);
        }
    }
    
    /**
     * Rimuove un widget dalla dashboard
     */
    function removeWidget(widgetElement) {
        if (!config.gridster) return;
        
        const widgetId = widgetElement.getAttribute('data-widget-id');
        
        // Chiedi conferma
        if (confirm('Sei sicuro di voler rimuovere questo widget?')) {
            // Rimuovi da Gridster
            config.gridster.remove_widget(widgetElement);
            
            // Rimuovi dalla configurazione
            config.widgets = config.widgets.filter(w => w.id !== widgetId);
            
            // Notifica l'utente
            if (window.showActionFeedback) {
                showActionFeedback('info', 'Widget rimosso', 3000);
            }
        }
    }
    
    /**
     * Carica il contenuto di un widget tramite AJAX
     */
    function loadWidgetContent(widgetId, widgetType) {
        const widgetElement = document.querySelector(`[data-widget-id="${widgetId}"]`);
        if (!widgetElement) return;
        
        const widgetContent = widgetElement.querySelector('.widget-content');
        
        // Mostra il loader
        widgetContent.innerHTML = `
            <div class="widget-loading">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Caricamento...</span>
                </div>
            </div>
        `;
        
        // Carica il contenuto del widget tramite AJAX
        fetch(`/api/widgets/${widgetType}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error('Errore nel caricamento del widget');
                }
                return response.text();
            })
            .then(html => {
                widgetContent.innerHTML = html;
                
                // Inizializza eventuali script nel widget
                initializeWidgetScripts(widgetElement, widgetType);
            })
            .catch(error => {
                console.error('Errore nel caricamento del widget:', error);
                widgetContent.innerHTML = `
                    <div class="widget-error">
                        <i class="fas fa-exclamation-triangle text-warning"></i>
                        <p>Errore nel caricamento del widget</p>
                        <button class="btn btn-sm btn-outline-primary retry-load">Riprova</button>
                    </div>
                `;
                
                // Aggiungi evento per il pulsante di retry
                const retryButton = widgetContent.querySelector('.retry-load');
                if (retryButton) {
                    retryButton.addEventListener('click', function() {
                        loadWidgetContent(widgetId, widgetType);
                    });
                }
            });
    }
    
    /**
     * Aggiorna il contenuto di un widget
     */
    function refreshWidgetContent(widgetId) {
        const widgetElement = document.querySelector(`[data-widget-id="${widgetId}"]`);
        if (!widgetElement) return;
        
        const widgetType = widgetElement.getAttribute('data-widget-type');
        loadWidgetContent(widgetId, widgetType);
    }
    
    /**
     * Inizializza script specifici per un widget
     */
    function initializeWidgetScripts(widgetElement, widgetType) {
        // Esegui script in base al tipo di widget
        switch (widgetType) {
            case 'chart':
                initializeChartWidget(widgetElement);
                break;
            case 'stats':
                initializeStatsWidget(widgetElement);
                break;
            case 'calendar':
                initializeCalendarWidget(widgetElement);
                break;
            case 'followers':
                initializeFollowersWidget(widgetElement);
                break;
            // Altri tipi di widget...
        }
    }
    
    /**
     * Inizializza un widget chart
     */
    function initializeChartWidget(widgetElement) {
        const canvas = widgetElement.querySelector('canvas');
        if (!canvas) return;
        
        // Inizializza Chart.js
        const ctx = canvas.getContext('2d');
        new Chart(ctx, {
            type: 'line',
            data: JSON.parse(canvas.getAttribute('data-chart')),
            options: {
                responsive: true,
                maintainAspectRatio: false
            }
        });
    }
    
    /**
     * Inizializza un widget stats
     */
    function initializeStatsWidget(widgetElement) {
        // Inizializza counter ed elementi animati
        const counters = widgetElement.querySelectorAll('.counter-value');
        counters.forEach(counter => {
            const value = parseInt(counter.getAttribute('data-value'), 10);
            animateCounter(counter, 0, value, 1500);
        });
    }
    
    /**
     * Inizializza un widget calendario
     */
    function initializeCalendarWidget(widgetElement) {
        const calendarEl = widgetElement.querySelector('.calendar');
        if (!calendarEl) return;
        
        // Inizializza il calendario
        const calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: 'dayGridMonth',
            locale: 'it',
            height: 'auto',
            events: JSON.parse(calendarEl.getAttribute('data-events') || '[]')
        });
        
        calendar.render();
    }
    
    /**
     * Inizializza un widget followers
     */
    function initializeFollowersWidget(widgetElement) {
        // Implementazione basata sulle necessità
    }
    
    /**
     * Anima un contatore numerico
     */
    function animateCounter(element, start, end, duration) {
        const range = end - start;
        const increment = end > start ? 1 : -1;
        const stepTime = Math.abs(Math.floor(duration / range));
        let current = start;
        
        const timer = setInterval(() => {
            current += increment;
            element.textContent = current;
            
            if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
                element.textContent = end;
                clearInterval(timer);
            }
        }, stepTime);
    }
    
    /**
     * Salva il layout della dashboard
     */
    function saveDashboardLayout() {
        if (!config.gridster) return;
        
        // Ottieni il layout corrente da Gridster
        const serializedLayout = config.gridster.serialize();
        
        // Mappa il layout serializzato ai widget configurati
        const dashboardLayout = {
            widgets: config.widgets.map((widget, index) => {
                const layoutItem = serializedLayout[index] || {};
                return {
                    id: widget.id,
                    type: widget.type,
                    title: widget.title,
                    icon: widget.icon,
                    size: {
                        rows: layoutItem.size_y || widget.size.rows,
                        cols: layoutItem.size_x || widget.size.cols
                    },
                    position: {
                        row: layoutItem.row || 0,
                        col: layoutItem.col || 0
                    }
                };
            })
        };
        
        // Salva il layout nel localStorage
        localStorage.setItem(config.storageKey, JSON.stringify(dashboardLayout));
        
        // Disattiva la modalità modifica
        toggleEditMode();
        
        // Notifica l'utente
        if (window.showActionFeedback) {
            showActionFeedback('success', 'Layout dashboard salvato', 3000);
        }
        
        // Invia il layout al server (se necessario)
        saveDashboardToServer(dashboardLayout);
    }
    
    /**
     * Annulla le modifiche al layout
     */
    function cancelEdit() {
        // Ripristina il layout precedente
        loadDashboardLayout();
        
        // Disattiva la modalità modifica
        toggleEditMode();
        
        // Notifica l'utente
        if (window.showActionFeedback) {
            showActionFeedback('info', 'Modifiche annullate', 3000);
        }
    }
    
    /**
     * Carica il layout della dashboard
     */
    function loadDashboardLayout() {
        // Ottieni il layout salvato
        const savedLayout = localStorage.getItem(config.storageKey);
        
        if (savedLayout) {
            try {
                const dashboardLayout = JSON.parse(savedLayout);
                config.widgets = dashboardLayout.widgets || [];
                
                // Applica il layout
                applyDashboardLayout();
            } catch (error) {
                console.error('Errore nel parsing del layout salvato:', error);
                // Usa il layout predefinito
                loadDefaultLayout();
            }
        } else {
            // Nessun layout salvato, usa quello predefinito
            loadDefaultLayout();
        }
    }
    
    /**
     * Applica il layout della dashboard
     */
    function applyDashboardLayout() {
        const dashboardContainer = document.querySelector(selectors.dashboard);
        if (!dashboardContainer) return;
        
        // Svuota il container
        dashboardContainer.innerHTML = '';
        
        // Aggiungi i widget configurati
        config.widgets.forEach(widget => {
            // Crea l'elemento widget
            const widgetElement = document.createElement('div');
            widgetElement.className = 'dashboard-widget';
            widgetElement.setAttribute('data-widget-id', widget.id);
            widgetElement.setAttribute('data-widget-type', widget.type);
            widgetElement.setAttribute('data-row', widget.position?.row || 0);
            widgetElement.setAttribute('data-col', widget.position?.col || 0);
            widgetElement.setAttribute('data-sizex', widget.size?.cols || 2);
            widgetElement.setAttribute('data-sizey', widget.size?.rows || 2);
            
            // Aggiungi contenuto del widget
            widgetElement.innerHTML = `
                <div class="widget-wrapper">
                    <div class="widget-header">
                        <h3 class="widget-title">
                            <i class="fas fa-${widget.icon} me-2"></i>${widget.title}
                        </h3>
                        <div class="widget-controls">
                            <button class="btn btn-sm widget-refresh" title="Aggiorna widget">
                                <i class="fas fa-sync-alt"></i>
                            </button>
                            <button class="btn btn-sm widget-remove" title="Rimuovi widget">
                                <i class="fas fa-times"></i>
                            </button>
                        </div>
                    </div>
                    <div class="widget-body">
                        <div class="widget-content">
                            <div class="widget-loading">
                                <div class="spinner-border text-primary" role="status">
                                    <span class="visually-hidden">Caricamento...</span>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="resize-handle"></div>
                </div>
            `;
            
            // Aggiungi evento per il pulsante di rimozione
            const removeButton = widgetElement.querySelector('.widget-remove');
            removeButton.addEventListener('click', function() {
                removeWidget(widgetElement);
            });
            
            // Aggiungi evento per il pulsante di refresh
            const refreshButton = widgetElement.querySelector('.widget-refresh');
            refreshButton.addEventListener('click', function() {
                refreshWidgetContent(widget.id);
            });
            
            // Aggiungi il widget al container
            dashboardContainer.appendChild(widgetElement);
            
            // Carica il contenuto del widget
            loadWidgetContent(widget.id, widget.type);
        });
    }
    
    /**
     * Carica il layout predefinito
     */
    function loadDefaultLayout() {
        // Layout predefinito
        config.widgets = [
            {
                id: 'widget-stats',
                type: 'stats',
                title: 'Statistiche',
                icon: 'chart-bar',
                size: { rows: 2, cols: 3 },
                position: { row: 0, col: 0 }
            },
            {
                id: 'widget-chart',
                type: 'chart',
                title: 'Grafico Attività',
                icon: 'chart-line',
                size: { rows: 2, cols: 3 },
                position: { row: 0, col: 3 }
            },
            {
                id: 'widget-followers',
                type: 'followers',
                title: 'Nuovi Follower',
                icon: 'users',
                size: { rows: 2, cols: 2 },
                position: { row: 2, col: 0 }
            },
            {
                id: 'widget-calendar',
                type: 'calendar',
                title: 'Calendario Stream',
                icon: 'calendar-alt',
                size: { rows: 2, cols: 2 },
                position: { row: 2, col: 2 }
            },
            {
                id: 'widget-todo',
                type: 'todo',
                title: 'To-Do',
                icon: 'tasks',
                size: { rows: 2, cols: 2 },
                position: { row: 2, col: 4 }
            }
        ];
        
        // Applica il layout
        applyDashboardLayout();
    }
    
    /**
     * Carica i widget disponibili
     */
    function loadAvailableWidgets() {
        // Controlla se ci sono widget disponibili in localStorage
        const savedWidgets = localStorage.getItem(config.widgetsListKey);
        
        if (savedWidgets) {
            try {
                config.availableWidgets = JSON.parse(savedWidgets);
            } catch (error) {
                console.error('Errore nel parsing dei widget disponibili:', error);
                loadDefaultWidgets();
            }
        } else {
            // Carica i widget dal server o usa quelli predefiniti
            fetch('/api/widgets')
                .then(response => {
                    if (!response.ok) {
                        throw new Error('Errore nel caricamento dei widget');
                    }
                    return response.json();
                })
                .then(widgets => {
                    config.availableWidgets = widgets;
                    localStorage.setItem(config.widgetsListKey, JSON.stringify(widgets));
                })
                .catch(error => {
                    console.error('Errore nel caricamento dei widget disponibili:', error);
                    loadDefaultWidgets();
                });
        }
    }
    
    /**
     * Carica i widget predefiniti
     */
    function loadDefaultWidgets() {
        // Widget predefiniti
        config.availableWidgets = [
            {
                type: 'stats',
                title: 'Statistiche',
                description: 'Mostra le statistiche principali del canale',
                icon: 'chart-bar',
                defaultSize: { rows: 2, cols: 3 }
            },
            {
                type: 'chart',
                title: 'Grafico Attività',
                description: 'Visualizza un grafico dell\'attività nel tempo',
                icon: 'chart-line',
                defaultSize: { rows: 2, cols: 3 }
            },
            {
                type: 'followers',
                title: 'Nuovi Follower',
                description: 'Lista dei nuovi follower recenti',
                icon: 'users',
                defaultSize: { rows: 2, cols: 2 }
            },
            {
                type: 'calendar',
                title: 'Calendario Stream',
                description: 'Calendario con gli stream programmati',
                icon: 'calendar-alt',
                defaultSize: { rows: 2, cols: 2 }
            },
            {
                type: 'todo',
                title: 'To-Do',
                description: 'Lista di cose da fare per gli stream',
                icon: 'tasks',
                defaultSize: { rows: 2, cols: 2 }
            },
            {
                type: 'twitch',
                title: 'Integrazione Twitch',
                description: 'Stato e statistiche del canale Twitch',
                icon: 'twitch',
                defaultSize: { rows: 2, cols: 2 }
            },
            {
                type: 'youtube',
                title: 'Integrazione YouTube',
                description: 'Stato e statistiche del canale YouTube',
                icon: 'youtube',
                defaultSize: { rows: 2, cols: 2 }
            },
            {
                type: 'discord',
                title: 'Integrazione Discord',
                description: 'Membri online e attività del server Discord',
                icon: 'discord',
                defaultSize: { rows: 2, cols: 2 }
            },
            {
                type: 'donations',
                title: 'Donazioni Recenti',
                description: 'Lista delle donazioni più recenti',
                icon: 'hand-holding-usd',
                defaultSize: { rows: 2, cols: 2 }
            },
            {
                type: 'weather',
                title: 'Meteo',
                description: 'Condizioni meteo attuali nella tua zona',
                icon: 'cloud-sun',
                defaultSize: { rows: 1, cols: 2 }
            },
            {
                type: 'notes',
                title: 'Note',
                description: 'Appunti e note personali',
                icon: 'sticky-note',
                defaultSize: { rows: 2, cols: 2 }
            },
            {
                type: 'goals',
                title: 'Obiettivi',
                description: 'Monitora gli obiettivi del canale',
                icon: 'bullseye',
                defaultSize: { rows: 1, cols: 2 }
            }
        ];
    }
    
    /**
     * Salva il layout della dashboard sul server
     */
    function saveDashboardToServer(layout) {
        fetch('/api/dashboard/layout', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(layout)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error('Errore nel salvataggio del layout');
            }
            return response.json();
        })
        .then(data => {
            console.log('Layout salvato sul server');
        })
        .catch(error => {
            console.error('Errore nel salvataggio del layout sul server:', error);
            // Il layout è comunque salvato in localStorage, quindi non è un problema critico
        });
    }
    
    /**
     * Utility function per debounce
     */
    function debounce(func, wait) {
        let timeout;
        return function(...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), wait);
        };
    }
    
    // Inizializza il customizer quando il documento è pronto
    document.addEventListener('DOMContentLoaded', init);
    
    // Esponi API pubblica
    window.dashboardCustomizer = {
        toggleEditMode,
        refreshAllWidgets: function() {
            config.widgets.forEach(widget => {
                refreshWidgetContent(widget.id);
            });
        },
        addWidget: function(widgetType) {
            const widget = config.availableWidgets.find(w => w.type === widgetType);
            if (widget) {
                addWidget(widget);
            }
        },
        saveLayout: saveDashboardLayout,
        resetLayout: loadDefaultLayout
    };
})(); 