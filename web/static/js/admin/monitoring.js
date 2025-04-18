/**
 * Sistema di monitoraggio M4Bot
 * JavaScript per la visualizzazione in tempo reale dei dati di sistema
 */

// IIFE per evitare conflitti di namespace
(function() {
    // Configurazione
    const config = {
        defaultUpdateInterval: 10000, // 10 secondi
        chartOptions: {
            animation: {
                duration: 750,
                easing: 'easeOutQuart'
            },
            scales: {
                x: {
                    grid: {
                        display: false
                    }
                },
                y: {
                    beginAtZero: true,
                    max: 100
                }
            },
            elements: {
                line: {
                    tension: 0.3
                },
                point: {
                    radius: 0,
                    hoverRadius: 5
                }
            },
            plugins: {
                tooltip: {
                    mode: 'index',
                    intersect: false
                },
                legend: {
                    position: 'top'
                }
            },
            responsive: true,
            maintainAspectRatio: false
        },
        maxDataPoints: 20,
        loadingDelay: 500 // Ritardo per mostrare l'overlay di caricamento
    };

    // Stato dell'applicazione
    let state = {
        updateInterval: config.defaultUpdateInterval,
        updateTimer: null,
        charts: {},
        data: {
            cpu: [],
            memory: [],
            network: {
                rx: [],
                tx: []
            },
            timestamp: []
        },
        isUpdating: false,
        isDarkTheme: document.body.classList.contains('dark-theme')
    };

    // Cache DOM elements
    const elements = {
        loadingOverlay: document.getElementById('loading-overlay'),
        refreshButton: document.getElementById('refresh-btn'),
        updateIntervalSelect: document.getElementById('update-interval'),
        cpuUsage: document.getElementById('cpu-usage'),
        memoryUsage: document.getElementById('memory-usage'),
        diskUsage: document.getElementById('disk-usage'),
        networkUsage: document.getElementById('network-usage'),
        cpuChart: document.getElementById('cpu-chart'),
        memoryChart: document.getElementById('memory-chart'),
        networkChart: document.getElementById('network-chart'),
        systemInfo: document.getElementById('system-info'),
        alertsList: document.getElementById('alerts-list'),
        alertsFilter: document.getElementById('alerts-filter'),
        servicesList: document.getElementById('services-list'),
        disksList: document.getElementById('disks-list'),
        networkConnectionsList: document.getElementById('network-connections-list'),
        toastContainer: document.getElementById('toast-container'),
        serviceRestartModal: document.getElementById('service-restart-modal'),
        serviceRestartButton: document.getElementById('confirm-restart')
    };

    // Inizializzazione
    function init() {
        setupEventListeners();
        initializeCharts();
        updateSystemData();
        
        // Impostazione dell'intervallo di aggiornamento dal select
        const intervalValue = elements.updateIntervalSelect.value;
        if (intervalValue !== 'manual') {
            setUpdateInterval(parseInt(intervalValue));
        }
        
        // Rileva cambiamenti di tema
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.attributeName === 'class') {
                    state.isDarkTheme = document.body.classList.contains('dark-theme');
                    updateChartsTheme();
                }
            });
        });
        
        observer.observe(document.body, { attributes: true });
    }

    // Setup dei listener di eventi
    function setupEventListeners() {
        // Aggiornamento manuale
        elements.refreshButton.addEventListener('click', function() {
            updateSystemData();
        });

        // Cambio dell'intervallo di aggiornamento
        elements.updateIntervalSelect.addEventListener('change', function() {
            const value = this.value;
            if (value === 'manual') {
                clearUpdateInterval();
            } else {
                setUpdateInterval(parseInt(value));
            }
        });

        // Filtro avvisi
        if (elements.alertsFilter) {
            elements.alertsFilter.addEventListener('change', function() {
                filterAlerts(this.value);
            });
        }

        // Modal di riavvio servizio
        document.addEventListener('click', function(e) {
            if (e.target && e.target.classList.contains('restart-service')) {
                const serviceId = e.target.dataset.service;
                const serviceName = e.target.dataset.name;
                showRestartModal(serviceId, serviceName);
            }
        });

        // Conferma riavvio servizio
        if (elements.serviceRestartButton) {
            elements.serviceRestartButton.addEventListener('click', function() {
                const serviceId = this.dataset.service;
                restartService(serviceId);
            });
        }
    }

    // Inizializzazione grafici
    function initializeCharts() {
        // Grafico CPU
        if (elements.cpuChart) {
            const cpuChartCtx = elements.cpuChart.getContext('2d');
            state.charts.cpu = new Chart(cpuChartCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Utilizzo CPU %',
                        data: [],
                        backgroundColor: 'rgba(255, 107, 107, 0.2)',
                        borderColor: 'rgba(255, 107, 107, 1)',
                        fill: true
                    }]
                },
                options: config.chartOptions
            });
        }

        // Grafico memoria
        if (elements.memoryChart) {
            const memoryChartCtx = elements.memoryChart.getContext('2d');
            state.charts.memory = new Chart(memoryChartCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Utilizzo Memoria %',
                        data: [],
                        backgroundColor: 'rgba(77, 150, 255, 0.2)',
                        borderColor: 'rgba(77, 150, 255, 1)',
                        fill: true
                    }]
                },
                options: config.chartOptions
            });
        }

        // Grafico rete
        if (elements.networkChart) {
            const networkChartCtx = elements.networkChart.getContext('2d');
            state.charts.network = new Chart(networkChartCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        {
                            label: 'Download (KB/s)',
                            data: [],
                            backgroundColor: 'rgba(107, 255, 158, 0.2)',
                            borderColor: 'rgba(107, 255, 158, 1)',
                            fill: true
                        },
                        {
                            label: 'Upload (KB/s)',
                            data: [],
                            backgroundColor: 'rgba(255, 193, 69, 0.2)',
                            borderColor: 'rgba(255, 193, 69, 1)',
                            fill: true
                        }
                    ]
                },
                options: {
                    ...config.chartOptions,
                    scales: {
                        ...config.chartOptions.scales,
                        y: {
                            beginAtZero: true,
                            // Non imposto max per adattarsi automaticamente ai dati
                        }
                    }
                }
            });
        }

        updateChartsTheme();
    }

    // Aggiorna il tema dei grafici in base al tema dell'interfaccia
    function updateChartsTheme() {
        const chartDefaults = {
            color: state.isDarkTheme ? '#e9ecef' : '#666',
            borderColor: state.isDarkTheme ? 'rgba(255, 255, 255, 0.1)' : 'rgba(0, 0, 0, 0.1)'
        };

        Chart.defaults.color = chartDefaults.color;
        
        // Aggiorna grafici esistenti
        Object.values(state.charts).forEach(chart => {
            chart.options.scales.x.grid.color = chartDefaults.borderColor;
            chart.options.scales.y.grid.color = chartDefaults.borderColor;
            chart.update();
        });
    }

    // Imposta l'intervallo di aggiornamento
    function setUpdateInterval(interval) {
        clearUpdateInterval();
        state.updateInterval = interval;
        state.updateTimer = setInterval(updateSystemData, interval);
        showToast(`Aggiornamento automatico impostato ogni ${interval/1000} secondi`);
    }

    // Cancella l'intervallo di aggiornamento
    function clearUpdateInterval() {
        if (state.updateTimer) {
            clearInterval(state.updateTimer);
            state.updateTimer = null;
        }
    }

    // Aggiorna i dati di sistema
    function updateSystemData() {
        if (state.isUpdating) return;
        
        state.isUpdating = true;
        showLoading();
        
        fetch('/admin/api/system/stats')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Errore HTTP ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                updateMetrics(data);
                updateCharts(data);
                updateSystemInfo(data.system_info);
                updateAlerts(data.alerts);
                updateServices(data.services);
                updateDisks(data.disks);
                updateNetworkConnections(data.network_connections);
                hideLoading();
                state.isUpdating = false;
            })
            .catch(error => {
                console.error('Errore durante l\'aggiornamento dei dati:', error);
                showError('Impossibile aggiornare i dati. Riprova più tardi.');
                hideLoading();
                state.isUpdating = false;
            });
    }

    // Mostra l'overlay di caricamento
    function showLoading() {
        setTimeout(() => {
            if (state.isUpdating) {
                elements.loadingOverlay.classList.add('visible');
            }
        }, config.loadingDelay);
    }

    // Nasconde l'overlay di caricamento
    function hideLoading() {
        elements.loadingOverlay.classList.remove('visible');
    }

    // Aggiorna le metriche in tempo reale
    function updateMetrics(data) {
        if (elements.cpuUsage) {
            elements.cpuUsage.textContent = `${data.cpu.usage.toFixed(1)}%`;
        }
        
        if (elements.memoryUsage) {
            elements.memoryUsage.textContent = `${data.memory.usage.toFixed(1)}%`;
        }
        
        if (elements.diskUsage) {
            elements.diskUsage.textContent = `${data.disk.usage.toFixed(1)}%`;
        }
        
        if (elements.networkUsage) {
            elements.networkUsage.innerHTML = `${data.network.rx_rate.toFixed(1)} / ${data.network.tx_rate.toFixed(1)} KB/s`;
        }
    }

    // Aggiorna i dati dei grafici
    function updateCharts(data) {
        // Aggiungi timestamp
        const timestamp = new Date().toLocaleTimeString();
        state.data.timestamp.push(timestamp);
        
        // Limita il numero di punti dati
        if (state.data.timestamp.length > config.maxDataPoints) {
            state.data.timestamp.shift();
        }
        
        // Aggiorna dati CPU
        if (state.charts.cpu) {
            state.data.cpu.push(data.cpu.usage);
            if (state.data.cpu.length > config.maxDataPoints) {
                state.data.cpu.shift();
            }
            
            state.charts.cpu.data.labels = state.data.timestamp;
            state.charts.cpu.data.datasets[0].data = state.data.cpu;
            state.charts.cpu.update();
        }
        
        // Aggiorna dati memoria
        if (state.charts.memory) {
            state.data.memory.push(data.memory.usage);
            if (state.data.memory.length > config.maxDataPoints) {
                state.data.memory.shift();
            }
            
            state.charts.memory.data.labels = state.data.timestamp;
            state.charts.memory.data.datasets[0].data = state.data.memory;
            state.charts.memory.update();
        }
        
        // Aggiorna dati rete
        if (state.charts.network) {
            state.data.network.rx.push(data.network.rx_rate);
            state.data.network.tx.push(data.network.tx_rate);
            
            if (state.data.network.rx.length > config.maxDataPoints) {
                state.data.network.rx.shift();
                state.data.network.tx.shift();
            }
            
            state.charts.network.data.labels = state.data.timestamp;
            state.charts.network.data.datasets[0].data = state.data.network.rx;
            state.charts.network.data.datasets[1].data = state.data.network.tx;
            state.charts.network.update();
        }
    }

    // Aggiorna le informazioni di sistema
    function updateSystemInfo(systemInfo) {
        if (!elements.systemInfo) return;
        
        let html = '';
        
        if (systemInfo) {
            html += `<div class="system-info-item">
                <span class="system-info-label">Sistema operativo:</span>
                <span class="system-info-value">${systemInfo.os_name} ${systemInfo.os_version}</span>
            </div>`;
            
            html += `<div class="system-info-item">
                <span class="system-info-label">Hostname:</span>
                <span class="system-info-value">${systemInfo.hostname}</span>
            </div>`;
            
            html += `<div class="system-info-item">
                <span class="system-info-label">Kernel:</span>
                <span class="system-info-value">${systemInfo.kernel_version}</span>
            </div>`;
            
            html += `<div class="system-info-item">
                <span class="system-info-label">CPU:</span>
                <span class="system-info-value">${systemInfo.cpu_model} (${systemInfo.cpu_cores} cores)</span>
            </div>`;
            
            html += `<div class="system-info-item">
                <span class="system-info-label">Memoria totale:</span>
                <span class="system-info-value">${systemInfo.total_memory} GB</span>
            </div>`;
            
            html += `<div class="system-info-item">
                <span class="system-info-label">Uptime:</span>
                <span class="system-info-value">${systemInfo.uptime}</span>
            </div>`;
            
            html += `<div class="system-info-item">
                <span class="system-info-label">Indirizzo IP:</span>
                <span class="system-info-value">${systemInfo.ip_address}</span>
            </div>`;
        } else {
            html = '<div class="loading-placeholder">Informazioni di sistema non disponibili</div>';
        }
        
        elements.systemInfo.innerHTML = html;
    }

    // Aggiorna la lista degli avvisi
    function updateAlerts(alerts) {
        if (!elements.alertsList) return;
        
        let html = '';
        
        if (alerts && alerts.length > 0) {
            alerts.forEach(alert => {
                const alertClass = `alert-${alert.severity.toLowerCase()}`;
                const alertTime = new Date(alert.timestamp).toLocaleString();
                
                html += `<div class="alert-item ${alertClass}" data-severity="${alert.severity.toLowerCase()}">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <div class="fw-semibold">${alert.message}</div>
                            <div class="mt-1 small text-muted">${alert.source}</div>
                        </div>
                        <span class="alert-timestamp">${alertTime}</span>
                    </div>
                </div>`;
            });
        } else {
            html = '<div class="alert-item">Nessun avviso presente</div>';
        }
        
        elements.alertsList.innerHTML = html;
        
        // Applica filtro corrente
        if (elements.alertsFilter) {
            filterAlerts(elements.alertsFilter.value);
        }
    }

    // Filtra gli avvisi per gravità
    function filterAlerts(severity) {
        if (!elements.alertsList) return;
        
        const alertItems = elements.alertsList.querySelectorAll('.alert-item');
        
        alertItems.forEach(item => {
            if (severity === 'all' || item.dataset.severity === severity) {
                item.style.display = '';
            } else {
                item.style.display = 'none';
            }
        });
    }

    // Aggiorna la lista dei servizi
    function updateServices(services) {
        if (!elements.servicesList) return;
        
        let html = '';
        
        if (services && services.length > 0) {
            html = '<div class="table-responsive"><table class="table align-middle"><thead><tr>' +
                   '<th>Nome</th><th>Stato</th><th>PID</th><th>CPU</th><th>Memoria</th><th>Azioni</th>' +
                   '</tr></thead><tbody>';
                   
            services.forEach(service => {
                const statusClass = service.status === 'running' ? 'status-running' : 
                                   (service.status === 'stopped' ? 'status-stopped' : 'status-restarting');
                
                html += `<tr>
                    <td class="fw-medium">${service.name}</td>
                    <td><span class="status-badge ${statusClass}">${service.status}</span></td>
                    <td>${service.pid || 'N/A'}</td>
                    <td>${service.cpu ? service.cpu.toFixed(1) + '%' : 'N/A'}</td>
                    <td>${service.memory ? service.memory.toFixed(1) + '%' : 'N/A'}</td>
                    <td>
                        <div class="d-flex gap-2">
                            <button class="btn btn-sm btn-primary restart-service" 
                                    data-service="${service.id}" 
                                    data-name="${service.name}" 
                                    ${service.status === 'stopped' ? 'disabled' : ''}>
                                <i class="bi bi-arrow-clockwise"></i>
                            </button>
                        </div>
                    </td>
                </tr>`;
            });
            
            html += '</tbody></table></div>';
        } else {
            html = '<div class="alert alert-info">Nessun servizio trovato</div>';
        }
        
        elements.servicesList.innerHTML = html;
    }

    // Aggiorna la lista dei dischi
    function updateDisks(disks) {
        if (!elements.disksList) return;
        
        let html = '';
        
        if (disks && disks.length > 0) {
            disks.forEach(disk => {
                const usagePercent = (disk.used / disk.total) * 100;
                let progressClass = 'bg-success';
                
                if (usagePercent > 85) {
                    progressClass = 'bg-danger';
                } else if (usagePercent > 70) {
                    progressClass = 'bg-warning';
                }
                
                html += `<div class="disk-usage">
                    <div class="disk-info">
                        <span class="disk-path">${disk.mount}</span>
                        <span class="disk-space">${formatSize(disk.used)} / ${formatSize(disk.total)}</span>
                    </div>
                    <div class="progress">
                        <div class="progress-bar ${progressClass}" role="progressbar" 
                             style="width: ${usagePercent.toFixed(1)}%" 
                             aria-valuenow="${usagePercent.toFixed(1)}" 
                             aria-valuemin="0" 
                             aria-valuemax="100"></div>
                    </div>
                </div>`;
            });
        } else {
            html = '<div class="alert alert-info">Nessun disco trovato</div>';
        }
        
        elements.disksList.innerHTML = html;
    }

    // Aggiorna le connessioni di rete
    function updateNetworkConnections(connections) {
        if (!elements.networkConnectionsList) return;
        
        let html = '';
        
        if (connections && connections.length > 0) {
            html = '<div class="table-responsive"><table class="table"><thead><tr>' +
                   '<th>Protocollo</th><th>Indirizzo locale</th><th>Indirizzo remoto</th><th>Stato</th>' +
                   '</tr></thead><tbody>';
            
            connections.forEach(conn => {
                html += `<tr>
                    <td>${conn.protocol}</td>
                    <td>${conn.local_address}:${conn.local_port}</td>
                    <td>${conn.remote_address}:${conn.remote_port}</td>
                    <td>${conn.state}</td>
                </tr>`;
            });
            
            html += '</tbody></table></div>';
        } else {
            html = '<div class="alert alert-info">Nessuna connessione attiva</div>';
        }
        
        elements.networkConnectionsList.innerHTML = html;
    }

    // Mostra modale di conferma riavvio servizio
    function showRestartModal(serviceId, serviceName) {
        if (!elements.serviceRestartModal) return;
        
        const titleElement = elements.serviceRestartModal.querySelector('.modal-title');
        const bodyElement = elements.serviceRestartModal.querySelector('.modal-body p');
        
        if (titleElement) {
            titleElement.textContent = `Riavvia ${serviceName}`;
        }
        
        if (bodyElement) {
            bodyElement.textContent = `Sei sicuro di voler riavviare il servizio "${serviceName}"? Questa operazione potrebbe interrompere temporaneamente il servizio.`;
        }
        
        elements.serviceRestartButton.dataset.service = serviceId;
        
        const modal = new bootstrap.Modal(elements.serviceRestartModal);
        modal.show();
    }

    // Riavvia un servizio
    function restartService(serviceId) {
        showLoading();
        
        fetch(`/admin/api/service/restart/${serviceId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': getCsrfToken()
            }
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Errore HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            hideLoading();
            if (data.success) {
                showToast('Servizio riavviato con successo', 'success');
                updateSystemData(); // Aggiorna tutti i dati
            } else {
                showToast(data.message || 'Errore durante il riavvio del servizio', 'danger');
            }
        })
        .catch(error => {
            hideLoading();
            console.error('Errore durante il riavvio del servizio:', error);
            showToast('Errore durante il riavvio del servizio', 'danger');
        });
    }

    // Mostra un toast di notifica
    function showToast(message, type = 'info') {
        if (!elements.toastContainer) return;
        
        const toastId = 'toast-' + Date.now();
        const icon = type === 'success' ? 'bi-check-circle-fill' :
                    type === 'danger' ? 'bi-exclamation-circle-fill' :
                    type === 'warning' ? 'bi-exclamation-triangle-fill' : 'bi-info-circle-fill';
                    
        const html = `
        <div id="${toastId}" class="toast align-items-center border-0 text-bg-${type}" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="bi ${icon} me-2"></i> ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>`;
        
        elements.toastContainer.insertAdjacentHTML('beforeend', html);
        
        const toastElement = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastElement, {
            delay: 5000,
            autohide: true
        });
        
        toast.show();
        
        // Rimuovi il toast dal DOM dopo che è stato nascosto
        toastElement.addEventListener('hidden.bs.toast', function() {
            this.remove();
        });
    }

    // Mostra un messaggio di errore
    function showError(message) {
        showToast(message, 'danger');
    }

    // Ottieni il token CSRF
    function getCsrfToken() {
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        return metaTag ? metaTag.getAttribute('content') : '';
    }

    // Formatta le dimensioni dei file in formato leggibile
    function formatSize(bytes) {
        if (bytes === 0) return '0 B';
        
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        
        return parseFloat((bytes / Math.pow(1024, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Inizializza il modulo quando il documento è pronto
    document.addEventListener('DOMContentLoaded', init);
    
})(); 