/**
 * EventQueueManager - Sistema di coda eventi per M4Bot
 * Gestisce la memorizzazione temporanea di eventi in caso di disconnessione
 * e garantisce l'invio ordinato degli eventi quando la connessione è ripristinata.
 */

class EventQueueManager {
    constructor(options = {}) {
        this.options = {
            storagePrefix: options.storagePrefix || 'event_queue_',
            maxQueueSize: options.maxQueueSize || 1000,
            processingInterval: options.processingInterval || 5000,
            retryInterval: options.retryInterval || 10000,
            maxRetries: options.maxRetries || 5,
            endpointUrl: options.endpointUrl || '/api/events',
            onQueueChanged: options.onQueueChanged || function() {},
            onProcessSuccess: options.onProcessSuccess || function() {},
            onProcessError: options.onProcessError || function() {},
            debug: options.debug !== undefined ? options.debug : false
        };

        // Stato corrente
        this.isOnline = true;
        this.isProcessing = false;
        this.retryCount = 0;
        this.queue = [];
        this.processingTimeout = null;
        this.retryTimeout = null;

        // Carica gli eventi in coda dal local storage
        this._loadQueueFromStorage();

        // Monitora lo stato della connessione
        window.addEventListener('online', () => this._handleOnline());
        window.addEventListener('offline', () => this._handleOffline());

        // Monitora heartbeat per determinare lo stato del server
        document.addEventListener('heartbeat:update', (event) => {
            const status = event.detail || {};
            const webStatus = status.web || {};
            this.isOnline = webStatus.online === true;
            
            if (this.isOnline && this.queue.length > 0) {
                this._processQueue();
            }
        });

        // Inizia il processamento periodico
        this._startProcessing();

        this._log('EventQueueManager inizializzato');
    }

    /**
     * Aggiunge un evento alla coda
     * @param {string} eventType - Tipo di evento
     * @param {Object} eventData - Dati dell'evento 
     * @param {Object} options - Opzioni aggiuntive
     * @returns {string} ID dell'evento
     */
    enqueue(eventType, eventData, options = {}) {
        const eventId = this._generateId();
        const timestamp = new Date().toISOString();
        
        const event = {
            id: eventId,
            type: eventType,
            data: eventData,
            timestamp: timestamp,
            priority: options.priority || 1, // 1: normale, 2: alta, 0: bassa
            attempts: 0,
            status: 'pending' // pending, processing, completed, failed
        };

        // Aggiungi alla coda in base alla priorità
        if (event.priority > 1) {
            // Alta priorità: inserisci all'inizio
            this.queue.unshift(event);
        } else {
            // Normale/bassa priorità: aggiungi alla fine
            this.queue.push(event);
        }

        // Limita la dimensione della coda
        if (this.queue.length > this.options.maxQueueSize) {
            this._log(`Coda piena, rimuovo eventi più vecchi con bassa priorità`);
            // Rimuovi gli eventi più vecchi con priorità bassa
            const lowPriorityEvents = this.queue.filter(e => e.priority === 0 && e.status === 'pending');
            if (lowPriorityEvents.length > 0) {
                this.queue = this.queue.filter(e => !(e.priority === 0 && e.status === 'pending'));
            } else {
                // Se non ci sono eventi a bassa priorità, rimuovi il più vecchio
                this.queue.shift();
            }
        }

        // Salva la coda
        this._saveQueueToStorage();
        
        // Notifica il cambiamento
        this.options.onQueueChanged(this.queue);

        // Se online, avvia il processamento
        if (this.isOnline && !this.isProcessing) {
            this._processQueue();
        }

        return eventId;
    }

    /**
     * Verifica stato di un evento specifico
     * @param {string} eventId - ID dell'evento
     * @returns {Object|null} Stato dell'evento o null se non trovato
     */
    getEventStatus(eventId) {
        const event = this.queue.find(e => e.id === eventId);
        return event ? { 
            id: event.id,
            type: event.type,
            status: event.status,
            timestamp: event.timestamp,
            attempts: event.attempts
        } : null;
    }

    /**
     * Ottiene le statistiche della coda
     * @returns {Object} Statistiche della coda
     */
    getQueueStats() {
        const totalEvents = this.queue.length;
        const pendingEvents = this.queue.filter(e => e.status === 'pending').length;
        const processingEvents = this.queue.filter(e => e.status === 'processing').length;
        const completedEvents = this.queue.filter(e => e.status === 'completed').length;
        const failedEvents = this.queue.filter(e => e.status === 'failed').length;
        
        return {
            total: totalEvents,
            pending: pendingEvents,
            processing: processingEvents,
            completed: completedEvents,
            failed: failedEvents,
            isOnline: this.isOnline,
            isProcessing: this.isProcessing,
            retryCount: this.retryCount
        };
    }

    /**
     * Elimina manualmente un evento dalla coda
     * @param {string} eventId - ID dell'evento da eliminare
     * @returns {boolean} True se l'evento è stato eliminato, false altrimenti
     */
    removeEvent(eventId) {
        const initialLength = this.queue.length;
        this.queue = this.queue.filter(e => e.id !== eventId);
        
        if (this.queue.length !== initialLength) {
            this._saveQueueToStorage();
            this.options.onQueueChanged(this.queue);
            return true;
        }
        
        return false;
    }

    /**
     * Svuota completamente la coda
     * @param {boolean} onlyCompleted - Se true, elimina solo gli eventi completati
     */
    clearQueue(onlyCompleted = false) {
        if (onlyCompleted) {
            this.queue = this.queue.filter(e => e.status !== 'completed');
        } else {
            this.queue = [];
        }
        
        this._saveQueueToStorage();
        this.options.onQueueChanged(this.queue);
    }

    /**
     * Riprova a processare gli eventi falliti
     */
    retryFailedEvents() {
        for (const event of this.queue) {
            if (event.status === 'failed') {
                event.status = 'pending';
                event.attempts = 0;
            }
        }
        
        this._saveQueueToStorage();
        this.options.onQueueChanged(this.queue);
        
        if (this.isOnline) {
            this._processQueue();
        }
    }

    /**
     * Inizia il processamento periodico
     * @private
     */
    _startProcessing() {
        clearTimeout(this.processingTimeout);
        
        this.processingTimeout = setTimeout(() => {
            if (this.isOnline && this.queue.some(e => e.status === 'pending')) {
                this._processQueue();
            }
            this._startProcessing();
        }, this.options.processingInterval);
    }

    /**
     * Processa gli eventi in coda
     * @private
     */
    async _processQueue() {
        if (this.isProcessing || !this.isOnline) return;
        
        this.isProcessing = true;
        let processedCount = 0;
        
        try {
            // Trova il primo evento in attesa
            const pendingEvent = this.queue.find(e => e.status === 'pending');
            
            if (!pendingEvent) {
                this.isProcessing = false;
                return;
            }
            
            // Aggiorna lo stato dell'evento
            pendingEvent.status = 'processing';
            pendingEvent.attempts++;
            this._saveQueueToStorage();
            this.options.onQueueChanged(this.queue);
            
            // Invia l'evento al server
            const response = await fetch(this.options.endpointUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    event_type: pendingEvent.type,
                    event_data: pendingEvent.data,
                    event_id: pendingEvent.id,
                    timestamp: pendingEvent.timestamp
                })
            });
            
            if (response.ok) {
                // Evento inviato con successo
                pendingEvent.status = 'completed';
                this.retryCount = 0;
                processedCount++;
                
                this.options.onProcessSuccess(pendingEvent);
            } else {
                // Errore nell'invio
                const errorData = await response.json().catch(() => null);
                this._log(`Errore nell'invio dell'evento: ${response.status}`, errorData);
                
                pendingEvent.status = pendingEvent.attempts >= this.options.maxRetries ? 'failed' : 'pending';
                this.retryCount++;
                
                this.options.onProcessError(pendingEvent, {
                    status: response.status,
                    data: errorData
                });
            }
        } catch (error) {
            this._log(`Errore nel processamento della coda: ${error.message}`);
            
            // Se c'è un evento in elaborazione, aggiornane lo stato
            const processingEvent = this.queue.find(e => e.status === 'processing');
            if (processingEvent) {
                processingEvent.status = processingEvent.attempts >= this.options.maxRetries ? 'failed' : 'pending';
                this.retryCount++;
                
                this.options.onProcessError(processingEvent, {
                    error: error.message
                });
            }
            
            // Imposta lo stato offline in caso di errore di rete
            if (error.name === 'TypeError' && error.message.includes('network')) {
                this.isOnline = false;
            }
        } finally {
            this.isProcessing = false;
            this._saveQueueToStorage();
            this.options.onQueueChanged(this.queue);
            
            // Se ci sono ancora eventi in attesa e siamo online, continua il processamento
            if (this.isOnline && this.queue.some(e => e.status === 'pending')) {
                // Aggiungi un piccolo ritardo per non sovraccaricare il server
                setTimeout(() => this._processQueue(), processedCount > 0 ? 100 : this.options.retryInterval);
            }
        }
    }

    /**
     * Gestisce l'evento 'online'
     * @private
     */
    _handleOnline() {
        this._log('Connessione online rilevata');
        this.isOnline = true;
        
        // Annulla eventuali timer di retry
        clearTimeout(this.retryTimeout);
        
        // Processa la coda se ci sono eventi in attesa
        if (this.queue.some(e => e.status === 'pending')) {
            this._processQueue();
        }
    }

    /**
     * Gestisce l'evento 'offline'
     * @private
     */
    _handleOffline() {
        this._log('Connessione offline rilevata');
        this.isOnline = false;
        
        // Imposta gli eventi in elaborazione come in attesa
        for (const event of this.queue) {
            if (event.status === 'processing') {
                event.status = 'pending';
            }
        }
        
        this._saveQueueToStorage();
        this.options.onQueueChanged(this.queue);
    }

    /**
     * Carica la coda dal local storage
     * @private
     */
    _loadQueueFromStorage() {
        try {
            const storedQueue = localStorage.getItem(`${this.options.storagePrefix}queue`);
            
            if (storedQueue) {
                this.queue = JSON.parse(storedQueue);
                
                // Reimposta eventi in processing come pending
                for (const event of this.queue) {
                    if (event.status === 'processing') {
                        event.status = 'pending';
                    }
                }
                
                this._log(`Coda caricata dal local storage: ${this.queue.length} eventi`);
                this.options.onQueueChanged(this.queue);
            }
        } catch (error) {
            this._log(`Errore nel caricamento della coda dal local storage: ${error.message}`);
            this.queue = [];
        }
    }

    /**
     * Salva la coda nel local storage
     * @private
     */
    _saveQueueToStorage() {
        try {
            // Rimuovi gli eventi completati più vecchi se superano un certo numero
            const completedEvents = this.queue.filter(e => e.status === 'completed');
            
            if (completedEvents.length > 100) {
                // Mantieni solo gli ultimi 100 eventi completati
                const pendingEvents = this.queue.filter(e => e.status !== 'completed');
                const sortedCompleted = completedEvents.sort((a, b) => 
                    new Date(b.timestamp) - new Date(a.timestamp)
                ).slice(0, 100);
                
                this.queue = [...pendingEvents, ...sortedCompleted];
            }
            
            localStorage.setItem(
                `${this.options.storagePrefix}queue`, 
                JSON.stringify(this.queue)
            );
        } catch (error) {
            this._log(`Errore nel salvataggio della coda nel local storage: ${error.message}`);
        }
    }

    /**
     * Genera un ID univoco per un evento
     * @private
     * @returns {string} ID univoco
     */
    _generateId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
    }

    /**
     * Log di debug
     * @private
     * @param {string} message - Messaggio di log
     * @param {*} data - Dati aggiuntivi
     */
    _log(message, data) {
        if (this.options.debug) {
            console.log(`[EventQueue] ${message}`, data !== undefined ? data : '');
        }
    }
}

// Inizializza il gestore di coda quando il DOM è caricato
document.addEventListener('DOMContentLoaded', function() {
    // Crea gestore eventi globale
    window.eventQueue = new EventQueueManager({
        endpointUrl: '/api/events',
        debug: true,
        onQueueChanged: function(queue) {
            // Aggiorna UI con lo stato della coda se necessario
            const queueCountElement = document.getElementById('event-queue-count');
            if (queueCountElement) {
                const pendingCount = queue.filter(e => e.status === 'pending').length;
                queueCountElement.textContent = pendingCount.toString();
                
                if (pendingCount > 0) {
                    queueCountElement.classList.remove('d-none');
                } else {
                    queueCountElement.classList.add('d-none');
                }
            }
        }
    });
    
    // Inizializza UI se presente
    const queueStatsElement = document.getElementById('event-queue-stats');
    if (queueStatsElement) {
        // Aggiorna statistiche ogni 5 secondi
        setInterval(() => {
            const stats = window.eventQueue.getQueueStats();
            queueStatsElement.innerHTML = `
                <div class="queue-stats">
                    <div class="status-indicator ${stats.isOnline ? 'online' : 'offline'}">
                        ${stats.isOnline ? 'Online' : 'Offline'}
                    </div>
                    <div class="stats-counts">
                        <span class="badge bg-primary">${stats.total} totali</span>
                        <span class="badge bg-warning">${stats.pending} in attesa</span>
                        <span class="badge bg-info">${stats.processing} in corso</span>
                        <span class="badge bg-success">${stats.completed} completati</span>
                        <span class="badge bg-danger">${stats.failed} falliti</span>
                    </div>
                </div>
            `;
        }, 5000);
    }
}); 