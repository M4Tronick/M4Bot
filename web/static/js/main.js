/**
 * M4Bot - main.js
 * Script principale per l'interfaccia web di M4Bot
 */

document.addEventListener('DOMContentLoaded', function() {
    // Inizializza i tooltips di Bootstrap
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Inizializza i popovers di Bootstrap
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

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
