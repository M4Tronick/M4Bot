/**
 * M4Bot - Main JavaScript file
 */

document.addEventListener('DOMContentLoaded', function() {
    // Enable tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl)
    });

    // Enable popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl)
    });

    // Auto-hide alerts after 5 seconds
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(function(alert) {
            var bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        });
    }, 5000);

    // Command edit functionality
    const editButtons = document.querySelectorAll('.edit-command');
    if (editButtons) {
        editButtons.forEach(button => {
            button.addEventListener('click', function() {
                const id = this.getAttribute('data-id');
                const name = this.getAttribute('data-name');
                const response = this.getAttribute('data-response');
                const cooldown = this.getAttribute('data-cooldown');
                const userLevel = this.getAttribute('data-user-level');
                
                // Update form fields
                document.getElementById('name').value = name;
                document.getElementById('response').value = response;
                document.getElementById('cooldown').value = cooldown;
                
                const userLevelSelect = document.getElementById('user_level');
                if (userLevelSelect) {
                    userLevelSelect.value = userLevel;
                }
                
                // Scroll to form
                const commandForm = document.querySelector('.card-header');
                if (commandForm) {
                    commandForm.scrollIntoView({ behavior: 'smooth' });
                }
            });
        });
    }

    // Handle API calls for bot start/stop
    const apiButtons = document.querySelectorAll('.api-action');
    if (apiButtons) {
        apiButtons.forEach(button => {
            button.addEventListener('click', async function() {
                const action = this.getAttribute('data-action');
                const channelId = this.getAttribute('data-channel');
                const endpoint = `/api/bot/${action}`;
                
                try {
                    // Show spinner
                    this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> In corso...';
                    this.disabled = true;
                    
                    const response = await fetch(endpoint, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ channel_id: channelId })
                    });
                    
                    const data = await response.json();
                    
                    // Reset button state
                    this.disabled = false;
                    if (action === 'start') {
                        this.innerHTML = '<i class="fas fa-play-circle me-2"></i>Avvia Bot';
                    } else {
                        this.innerHTML = '<i class="fas fa-stop-circle me-2"></i>Ferma Bot';
                    }
                    
                    if (response.ok) {
                        showToast('Successo', data.message, 'success');
                    } else {
                        showToast('Errore', data.error, 'danger');
                    }
                } catch (err) {
                    console.error(err);
                    showToast('Errore', 'Si è verificato un errore nella comunicazione con il server', 'danger');
                    
                    // Reset button state
                    this.disabled = false;
                    if (action === 'start') {
                        this.innerHTML = '<i class="fas fa-play-circle me-2"></i>Avvia Bot';
                    } else {
                        this.innerHTML = '<i class="fas fa-stop-circle me-2"></i>Ferma Bot';
                    }
                }
            });
        });
    }

    // Gestione del toggle della dark mode
    const darkModeToggle = document.getElementById('darkModeToggle');
    if (darkModeToggle) {
        // Controlla se è abilitata la modalità scura nel localStorage
        const isDarkMode = localStorage.getItem('darkMode') === 'true';
        
        // Imposta il tema iniziale
        if (isDarkMode) {
            document.documentElement.setAttribute('data-bs-theme', 'dark');
            darkModeToggle.checked = true;
        }
        
        // Gestione del cambio del tema
        darkModeToggle.addEventListener('change', function() {
            if (this.checked) {
                document.documentElement.setAttribute('data-bs-theme', 'dark');
                localStorage.setItem('darkMode', 'true');
            } else {
                document.documentElement.setAttribute('data-bs-theme', 'light');
                localStorage.setItem('darkMode', 'false');
            }
        });
    }

    // Funzione per mostrare il loader durante le richieste AJAX
    function showLoader() {
        // Crea un elemento overlay per il loader
        const overlay = document.createElement('div');
        overlay.className = 'spinner-overlay';
        overlay.id = 'loadingSpinner';
        
        // Crea il contenitore dello spinner
        const spinnerContainer = document.createElement('div');
        spinnerContainer.className = 'spinner-container';
        
        // Crea lo spinner
        const spinner = document.createElement('div');
        spinner.className = 'spinner-border text-primary';
        spinner.setAttribute('role', 'status');
        
        // Crea il testo
        const spinnerText = document.createElement('span');
        spinnerText.className = 'visually-hidden';
        spinnerText.textContent = 'Caricamento...';
        
        // Aggiungi il messaggio sotto lo spinner
        const message = document.createElement('p');
        message.className = 'mt-2';
        message.textContent = 'Caricamento in corso...';
        
        // Assembla gli elementi
        spinner.appendChild(spinnerText);
        spinnerContainer.appendChild(spinner);
        spinnerContainer.appendChild(message);
        overlay.appendChild(spinnerContainer);
        
        // Aggiungi l'overlay al body
        document.body.appendChild(overlay);
    }

    // Funzione per nascondere il loader
    function hideLoader() {
        const loader = document.getElementById('loadingSpinner');
        if (loader) {
            loader.remove();
        }
    }

    // Configura AJAX per mostrare il loader durante le richieste
    $(document).ajaxStart(function() {
        showLoader();
    }).ajaxStop(function() {
        hideLoader();
    });

    // Gestione del form di aggiunta/modifica dei comandi
    const commandForm = document.getElementById('commandForm');
    if (commandForm) {
        commandForm.addEventListener('submit', function(e) {
            // Validazione del form
            const commandName = document.getElementById('commandName').value;
            if (!commandName.startsWith('!')) {
                e.preventDefault();
                alert('Il nome del comando deve iniziare con !');
                return false;
            }
            
            // Mostra il loader
            showLoader();
            return true;
        });
    }

    // Funzione per confermare l'eliminazione
    function confirmDelete(event, message) {
        if (!confirm(message || 'Sei sicuro di voler eliminare questo elemento?')) {
            event.preventDefault();
            return false;
        }
        return true;
    }

    // Aggiungi listener a tutti i pulsanti di eliminazione
    const deleteButtons = document.querySelectorAll('.delete-btn');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            return confirmDelete(e, 'Sei sicuro di voler eliminare questo elemento? Questa azione non può essere annullata.');
        });
    });

    // Gestione dei grafici statistici (se presenti)
    const statisticsCharts = document.querySelectorAll('.statistics-chart');
    statisticsCharts.forEach(chartCanvas => {
        const ctx = chartCanvas.getContext('2d');
        
        // Recupera i dati dal data-attribute
        const chartData = JSON.parse(chartCanvas.dataset.chartData || '{}');
        const chartType = chartCanvas.dataset.chartType || 'line';
        
        // Configurazione del grafico
        const chartConfig = {
            type: chartType,
            data: {
                labels: chartData.labels || [],
                datasets: [{
                    label: chartData.label || 'Dati',
                    data: chartData.data || [],
                    backgroundColor: 'rgba(138, 67, 204, 0.2)',
                    borderColor: 'rgba(138, 67, 204, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        };
        
        // Crea il grafico
        new Chart(ctx, chartConfig);
    });
    
    // Gestione del toggle dello stato di un comando
    const commandToggleSwitches = document.querySelectorAll('.command-toggle');
    commandToggleSwitches.forEach(toggle => {
        toggle.addEventListener('change', function() {
            const commandId = this.dataset.commandId;
            const form = document.getElementById(`toggleForm_${commandId}`);
            if (form) {
                form.submit();
            }
        });
    });
    
    // Funzione per copy to clipboard
    function copyToClipboard(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
    }
    
    // Aggiungi listener ai pulsanti di copia
    const copyButtons = document.querySelectorAll('.copy-btn');
    copyButtons.forEach(button => {
        button.addEventListener('click', function() {
            const textToCopy = this.dataset.copyText;
            copyToClipboard(textToCopy);
            
            // Feedback all'utente
            const originalText = this.innerHTML;
            this.innerHTML = '<i class="fas fa-check"></i> Copiato!';
            setTimeout(() => {
                this.innerHTML = originalText;
            }, 2000);
        });
    });
    
    // Inizializza il sidebar collapse
    const sidebarToggle = document.getElementById('sidebarToggle');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            document.body.classList.toggle('sidebar-collapsed');
            
            // Salva lo stato nel localStorage
            const isCollapsed = document.body.classList.contains('sidebar-collapsed');
            localStorage.setItem('sidebarCollapsed', isCollapsed);
        });
        
        // Ripristina lo stato del sidebar dal localStorage
        const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
        if (isCollapsed) {
            document.body.classList.add('sidebar-collapsed');
        }
    }
});

// Helper function to show toasts
function showToast(title, message, type) {
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        // Create toast container if it doesn't exist
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(container);
    }
    
    const toastId = 'toast-' + Date.now();
    const html = `
    <div id="${toastId}" class="toast" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="toast-header bg-${type} text-white">
            <strong class="me-auto">${title}</strong>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
        <div class="toast-body">
            ${message}
        </div>
    </div>
    `;
    
    document.getElementById('toast-container').insertAdjacentHTML('beforeend', html);
    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement);
    toast.show();
    
    // Auto-remove toast from DOM after it's hidden
    toastElement.addEventListener('hidden.bs.toast', function() {
        toastElement.remove();
    });
}
