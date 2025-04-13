/**
 * Sistema di Heartbeat per M4Bot
 * Monitora lo stato del bot e dei servizi connessi
 */

class HeartbeatMonitor {
    constructor(options = {}) {
        this.options = {
            interval: options.interval || 15000, // Intervallo di controllo in ms (default 15s)
            endpoints: options.endpoints || {
                bot: '/api/status/bot',
                web: '/api/status/web',
                database: '/api/status/database',
                kick_api: '/api/status/kick_api'
            },
            onStatusChange: options.onStatusChange || function() {},
            maxRetries: options.maxRetries || 3,
            autoRestart: options.autoRestart !== undefined ? options.autoRestart : true
        };

        this.status = {
            bot: {
                online: false,
                lastCheck: null,
                responseTime: null,
                errors: 0,
                history: []
            },
            web: {
                online: false,
                lastCheck: null,
                responseTime: null,
                errors: 0,
                history: []
            },
            database: {
                online: false,
                lastCheck: null,
                responseTime: null,
                errors: 0,
                history: []
            },
            kick_api: {
                online: false,
                lastCheck: null,
                responseTime: null,
                errors: 0,
                history: []
            }
        };

        this.retryCount = 0;
        this.intervalId = null;
    }

    /**
     * Avvia il monitoraggio
     */
    start() {
        if (this.intervalId) {
            console.warn('Heartbeat monitor is already running');
            return;
        }

        this.checkAllServices();
        this.intervalId = setInterval(() => this.checkAllServices(), this.options.interval);
        console.log(`Heartbeat monitor started (interval: ${this.options.interval}ms)`);
    }

    /**
     * Ferma il monitoraggio
     */
    stop() {
        if (this.intervalId) {
            clearInterval(this.intervalId);
            this.intervalId = null;
            console.log('Heartbeat monitor stopped');
        }
    }

    /**
     * Controlla tutti i servizi
     */
    async checkAllServices() {
        for (const service in this.options.endpoints) {
            if (this.options.endpoints.hasOwnProperty(service)) {
                await this.checkService(service, this.options.endpoints[service]);
            }
        }

        // Invia lo stato aggiornato attraverso il callback
        this.options.onStatusChange(this.status);
        
        // Aggiorna l'UI se il metodo updateStatusUI esiste
        if (typeof this.updateStatusUI === 'function') {
            this.updateStatusUI();
        }
    }

    /**
     * Controlla un singolo servizio
     * @param {string} service - Nome del servizio
     * @param {string} endpoint - Endpoint per il controllo
     */
    async checkService(service, endpoint) {
        if (!this.status[service]) {
            console.error(`Service "${service}" is not defined in status object`);
            return;
        }

        const startTime = Date.now();
        let success = false;
        let details = {};

        try {
            const response = await fetch(endpoint, {
                method: 'GET',
                headers: {
                    'Accept': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                cache: 'no-store'
            });

            if (response.ok) {
                const data = await response.json();
                success = data.online === true;
                details = data.details || {};
            } else {
                console.warn(`Service "${service}" check failed: HTTP ${response.status}`);
                success = false;
            }
        } catch (error) {
            console.error(`Service "${service}" check error:`, error);
            success = false;
        }

        const responseTime = Date.now() - startTime;
        const previousStatus = this.status[service].online;

        // Aggiorna lo stato
        this.status[service].online = success;
        this.status[service].lastCheck = new Date();
        this.status[service].responseTime = responseTime;
        this.status[service].details = details;

        // Gestisci la cronologia (max 20 elementi)
        this.status[service].history.unshift({
            timestamp: new Date(),
            online: success,
            responseTime: responseTime
        });
        if (this.status[service].history.length > 20) {
            this.status[service].history.pop();
        }

        // Gestisci i contatori di errore
        if (success) {
            this.status[service].errors = 0;
        } else {
            this.status[service].errors++;
            
            // Se il servizio è offline dopo essere stato online, tenta il riavvio
            if (previousStatus && this.options.autoRestart && service === 'bot') {
                if (this.status[service].errors >= this.options.maxRetries) {
                    console.warn(`Service "${service}" is offline, attempting restart...`);
                    this.restartService(service);
                }
            }
        }

        // Se lo stato è cambiato, notifica
        if (previousStatus !== success) {
            console.log(`Service "${service}" status changed: ${success ? 'online' : 'offline'}`);
            this.notifyStatusChange(service, success);
        }
    }

    /**
     * Riavvia un servizio
     * @param {string} service - Nome del servizio
     */
    async restartService(service) {
        if (service === 'bot') {
            try {
                const response = await fetch('/api/bot/restart', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                const data = await response.json();
                if (data.success) {
                    console.log(`Service "${service}" restart initiated successfully`);
                    // Resetta gli errori per dare tempo al riavvio
                    this.status[service].errors = 0;
                } else {
                    console.error(`Service "${service}" restart failed:`, data.error);
                }
            } catch (error) {
                console.error(`Error restarting service "${service}":`, error);
            }
        } else {
            console.warn(`Restart not implemented for service "${service}"`);
        }
    }

    /**
     * Notifica il cambiamento di stato
     * @param {string} service - Nome del servizio
     * @param {boolean} online - Status online/offline
     */
    notifyStatusChange(service, online) {
        // Aggiornamento UI
        const statusElement = document.getElementById(`${service}-status`);
        if (statusElement) {
            statusElement.className = `status-indicator ${online ? 'online' : 'offline'}`;
            statusElement.setAttribute('title', `${service}: ${online ? 'Online' : 'Offline'}`);
        }

        // Toasts/Notifiche
        const toastContainer = document.getElementById('toast-container');
        if (toastContainer) {
            const toast = document.createElement('div');
            toast.className = `toast ${online ? 'success' : 'error'} show`;
            toast.innerHTML = `
                <div class="toast-header">
                    <i class="fas fa-${online ? 'check-circle' : 'exclamation-circle'} me-2"></i>
                    <strong>${service.charAt(0).toUpperCase() + service.slice(1)}</strong>
                    <small class="ms-auto">${new Date().toLocaleTimeString()}</small>
                </div>
                <div class="toast-body">
                    Il servizio è ora ${online ? 'online' : 'offline'}.
                    ${!online ? 'Riavvio automatico in corso...' : ''}
                </div>
            `;
            toastContainer.appendChild(toast);

            // Rimuovi il toast dopo 5 secondi
            setTimeout(() => {
                toast.className = toast.className.replace('show', '');
                setTimeout(() => {
                    toast.remove();
                }, 500);
            }, 5000);
        }
    }

    /**
     * Aggiorna l'interfaccia utente con lo stato attuale
     */
    updateStatusUI() {
        // Aggiorna la dashboard di stato se la pagina è aperta
        const statusDashboard = document.getElementById('status-dashboard');
        if (!statusDashboard) return;

        for (const service in this.status) {
            if (this.status.hasOwnProperty(service)) {
                const serviceStatus = this.status[service];
                
                // Aggiorna indicatori
                const statusIndicator = document.getElementById(`${service}-status-indicator`);
                if (statusIndicator) {
                    statusIndicator.className = `status-badge ${serviceStatus.online ? 'bg-success' : 'bg-danger'}`;
                    statusIndicator.textContent = serviceStatus.online ? 'Online' : 'Offline';
                }
                
                // Aggiorna tempo di risposta
                const responseTimeElement = document.getElementById(`${service}-response-time`);
                if (responseTimeElement && serviceStatus.responseTime) {
                    responseTimeElement.textContent = `${serviceStatus.responseTime}ms`;
                }
                
                // Aggiorna ultimo controllo
                const lastCheckElement = document.getElementById(`${service}-last-check`);
                if (lastCheckElement && serviceStatus.lastCheck) {
                    lastCheckElement.textContent = serviceStatus.lastCheck.toLocaleString();
                }
                
                // Aggiorna dettagli aggiuntivi
                if (serviceStatus.details) {
                    const detailsContainer = document.getElementById(`${service}-details`);
                    if (detailsContainer) {
                        // Pulisci i dettagli esistenti
                        detailsContainer.innerHTML = '';
                        
                        // Aggiungi i nuovi dettagli
                        for (const key in serviceStatus.details) {
                            if (serviceStatus.details.hasOwnProperty(key)) {
                                const detailItem = document.createElement('div');
                                detailItem.className = 'detail-item';
                                detailItem.innerHTML = `<strong>${key}:</strong> ${serviceStatus.details[key]}`;
                                detailsContainer.appendChild(detailItem);
                            }
                        }
                    }
                }
            }
        }
    }
}

// Inizializza il monitor di heartbeat quando il DOM è caricato
document.addEventListener('DOMContentLoaded', function() {
    // Crea container per i toast se non esiste
    if (!document.getElementById('toast-container')) {
        const toastContainer = document.createElement('div');
        toastContainer.id = 'toast-container';
        toastContainer.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(toastContainer);
    }
    
    // Inizializza e avvia il monitor
    window.heartbeatMonitor = new HeartbeatMonitor({
        onStatusChange: function(status) {
            // Evento personalizzato per notificare altri componenti
            const event = new CustomEvent('heartbeat:update', { detail: status });
            document.dispatchEvent(event);
        }
    });
    
    window.heartbeatMonitor.start();
}); 