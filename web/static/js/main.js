/**
 * M4Bot - Main JavaScript file
 * Versione ottimizzata con transizioni fluide e miglioramenti grafici
 */

document.addEventListener('DOMContentLoaded', function() {
    // Inizializzazione hardware-accelerated per elementi animati
    document.querySelectorAll('.animated, .transition-element').forEach(el => {
        el.classList.add('hardware-accelerated');
    });

    // Enable tooltips with improved animation
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl, {
            animation: true,
            delay: { show: 200, hide: 100 }
        });
    });

    // Enable popovers with improved animation
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
    var popoverList = popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl, {
            animation: true,
            delay: { show: 200, hide: 100 }
        });
    });

    // Auto-hide alerts after 5 seconds with smooth fade
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(function(alert) {
            alert.classList.add('fade-out');
            setTimeout(() => {
                var bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }, 500);
        });
    }, 5000);

    // Command edit functionality with smooth scroll
    const editButtons = document.querySelectorAll('.edit-command');
    if (editButtons) {
        editButtons.forEach(button => {
            button.addEventListener('click', function() {
                const id = this.getAttribute('data-id');
                const name = this.getAttribute('data-name');
                const response = this.getAttribute('data-response');
                const cooldown = this.getAttribute('data-cooldown');
                const userLevel = this.getAttribute('data-user-level');
                
                // Update form fields with subtle animation
                const nameField = document.getElementById('name');
                const responseField = document.getElementById('response');
                const cooldownField = document.getElementById('cooldown');
                
                if (nameField && responseField && cooldownField) {
                    nameField.value = name;
                    responseField.value = response;
                    cooldownField.value = cooldown;
                    
                    // Apply highlight effect
                    [nameField, responseField, cooldownField].forEach(field => {
                        field.classList.add('highlight-update');
                        setTimeout(() => field.classList.remove('highlight-update'), 1000);
                    });
                }
                
                const userLevelSelect = document.getElementById('user_level');
                if (userLevelSelect) {
                    userLevelSelect.value = userLevel;
                }
                
                // Scroll to form with improved smoothness
                const commandForm = document.querySelector('.card-header');
                if (commandForm) {
                    commandForm.scrollIntoView({ 
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            });
        });
    }

    // Helper function to make standardized API calls with improved error handling
    async function callApi(endpoint, method = 'GET', data = null, showLoader = true) {
        try {
            if (showLoader) {
                showLoader();
            }
            
            const options = {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                credentials: 'same-origin'
            };
            
            if (data) {
                options.body = JSON.stringify(data);
            }
            
            const response = await fetch(endpoint, options);
            
            // Handle non-JSON responses
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                const responseData = await response.json();
                
                if (!response.ok) {
                    throw new Error(responseData.error || 'Si è verificato un errore nella richiesta');
                }
                
                return responseData;
            } else {
                // Handle non-JSON responses
                if (!response.ok) {
                    throw new Error('Si è verificato un errore nella richiesta');
                }
                
                return { success: true, message: 'Operazione completata' };
            }
        } catch (error) {
            console.error('API Error:', error);
            showToast('Errore', error.message, 'danger');
            throw error;
        } finally {
            if (showLoader) {
                hideLoader();
            }
        }
    }

    // Handle API calls for bot start/stop with improved feedback
    const apiButtons = document.querySelectorAll('.api-action');
    if (apiButtons) {
        apiButtons.forEach(button => {
            button.addEventListener('click', async function() {
                const action = this.getAttribute('data-action');
                const channelId = this.getAttribute('data-channel');
                const endpoint = `/api/bot/${action}`;
                
                // Check if button is already in progress
                if (this.classList.contains('in-progress')) {
                    return;
                }
                
                try {
                    // Show spinner and prevent double-clicks
                    this.classList.add('in-progress');
                    this.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> In corso...';
                    this.disabled = true;
                    
                    const data = await callApi(endpoint, 'POST', { channel_id: channelId }, false);
                    
                    // Show success message
                    showToast('Successo', data.message, 'success');
                    
                    // Update UI status indicators if present
                    const statusIndicator = document.querySelector(`.status-indicator[data-channel="${channelId}"]`);
                    if (statusIndicator) {
                        if (action === 'start') {
                            statusIndicator.className = 'status-indicator active';
                            statusIndicator.innerHTML = '<i class="fas fa-circle text-success"></i> Attivo';
                        } else {
                            statusIndicator.className = 'status-indicator inactive';
                            statusIndicator.innerHTML = '<i class="fas fa-circle text-danger"></i> Inattivo';
                        }
                        
                        // Animate status change
                        statusIndicator.classList.add('status-changed');
                        setTimeout(() => statusIndicator.classList.remove('status-changed'), 1000);
                    }
                } catch (error) {
                    // Error handling is done in the callApi function
                } finally {
                    // Reset button state
                    this.classList.remove('in-progress');
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

    // Dark mode toggle with smooth transition
    const darkModeToggle = document.getElementById('darkModeToggle');
    if (darkModeToggle) {
        // Check if dark mode is enabled in localStorage
        const isDarkMode = localStorage.getItem('darkMode') === 'true';
        
        // Set initial theme
        if (isDarkMode) {
            document.documentElement.setAttribute('data-bs-theme', 'dark');
            darkModeToggle.checked = true;
        }
        
        // Add transition class to body for smooth theme change
        document.body.classList.add('theme-transition');
        
        // Handle theme toggle
        darkModeToggle.addEventListener('change', function() {
            // Add transition class for animation
            document.body.classList.add('theme-changing');
            
            if (this.checked) {
                document.documentElement.setAttribute('data-bs-theme', 'dark');
                localStorage.setItem('darkMode', 'true');
            } else {
                document.documentElement.setAttribute('data-bs-theme', 'light');
                localStorage.setItem('darkMode', 'false');
            }
            
            // Remove transition class after animation completes
            setTimeout(() => {
                document.body.classList.remove('theme-changing');
            }, 500);
        });
    }

    // Function to show loader during API requests with improved animation
    function showLoader() {
        // Create overlay element for the loader
        const overlay = document.createElement('div');
        overlay.className = 'spinner-overlay hardware-accelerated';
        overlay.id = 'loadingSpinner';
        
        // Create spinner container
        const spinnerContainer = document.createElement('div');
        spinnerContainer.className = 'spinner-container';
        
        // Create spinner
        const spinner = document.createElement('div');
        spinner.className = 'spinner-border text-primary';
        spinner.setAttribute('role', 'status');
        
        // Create text
        const spinnerText = document.createElement('span');
        spinnerText.className = 'visually-hidden';
        spinnerText.textContent = 'Caricamento...';
        
        // Add message below spinner
        const message = document.createElement('p');
        message.className = 'mt-2';
        message.textContent = 'Caricamento in corso...';
        
        // Assemble elements
        spinner.appendChild(spinnerText);
        spinnerContainer.appendChild(spinner);
        spinnerContainer.appendChild(message);
        overlay.appendChild(spinnerContainer);
        
        // Add overlay to body with fade-in effect
        document.body.appendChild(overlay);
        
        // Trigger animation
        setTimeout(() => overlay.classList.add('visible'), 10);
    }

    // Function to hide loader with fade out effect
    function hideLoader() {
        const loader = document.getElementById('loadingSpinner');
        if (loader) {
            // Add fade-out class
            loader.classList.remove('visible');
            
            // Remove element after animation completes
            setTimeout(() => {
                if (loader.parentNode) {
                    loader.parentNode.removeChild(loader);
                }
            }, 300);
        }
    }

    // Form validation for command form with improved user feedback
    const commandForm = document.getElementById('commandForm');
    if (commandForm) {
        commandForm.addEventListener('submit', function(e) {
            // Validate form
            const commandName = document.getElementById('commandName');
            
            if (commandName && !commandName.value.startsWith('!')) {
                e.preventDefault();
                
                // Highlight field with error
                commandName.classList.add('is-invalid');
                
                // Add error message
                let feedbackElement = commandName.nextElementSibling;
                if (!feedbackElement || !feedbackElement.classList.contains('invalid-feedback')) {
                    feedbackElement = document.createElement('div');
                    feedbackElement.className = 'invalid-feedback';
                    commandName.parentNode.insertBefore(feedbackElement, commandName.nextSibling);
                }
                feedbackElement.textContent = 'Il nome del comando deve iniziare con !';
                
                // Show toast with shake animation
                showToast('Errore', 'Il nome del comando deve iniziare con !', 'danger');
                
                // Focus field
                commandName.focus();
                
                return false;
            }
            
            // Show loader
            showLoader();
            return true;
        });
    }

    // Function to confirm deletion with improved modal
    function confirmDelete(event, message) {
        event.preventDefault();
        
        // Use custom modal instead of browser confirm
        const modalId = 'confirmDeleteModal';
        let modal = document.getElementById(modalId);
        
        // Create modal if it doesn't exist
        if (!modal) {
            const modalHTML = `
            <div class="modal fade" id="${modalId}" tabindex="-1" aria-labelledby="confirmDeleteModalLabel" aria-hidden="true">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content">
                        <div class="modal-header bg-danger text-white">
                            <h5 class="modal-title" id="confirmDeleteModalLabel">Conferma eliminazione</h5>
                            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal" aria-label="Close"></button>
                        </div>
                        <div class="modal-body">
                            <p id="confirmDeleteModalMessage"></p>
                        </div>
                        <div class="modal-footer">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Annulla</button>
                            <button type="button" class="btn btn-danger" id="confirmDeleteButton">Elimina</button>
                        </div>
                    </div>
                </div>
            </div>
            `;
            
            document.body.insertAdjacentHTML('beforeend', modalHTML);
            modal = document.getElementById(modalId);
        }
        
        // Set message
        document.getElementById('confirmDeleteModalMessage').textContent = message || 'Sei sicuro di voler eliminare questo elemento? Questa azione non può essere annullata.';
        
        // Store the source element for later use
        const sourceElement = event.currentTarget;
        
        // Get original form action or link href
        let originalAction;
        if (sourceElement.tagName === 'A') {
            originalAction = sourceElement.getAttribute('href');
        } else if (sourceElement.closest('form')) {
            originalAction = sourceElement.closest('form').getAttribute('action');
        }
        
        // Open modal
        const modalInstance = new bootstrap.Modal(modal);
        modalInstance.show();
        
        // Handle confirm button
        const confirmButton = document.getElementById('confirmDeleteButton');
        
        // Remove existing event listeners
        const newConfirmButton = confirmButton.cloneNode(true);
        confirmButton.parentNode.replaceChild(newConfirmButton, confirmButton);
        
        // Add new event listener
        newConfirmButton.addEventListener('click', function() {
            if (sourceElement.tagName === 'A') {
                window.location.href = originalAction;
            } else if (sourceElement.closest('form')) {
                sourceElement.closest('form').submit();
            }
            modalInstance.hide();
        });
        
        return false;
    }

    // Add listeners to all delete buttons
    const deleteButtons = document.querySelectorAll('.delete-btn');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            return confirmDelete(e, 'Sei sicuro di voler eliminare questo elemento? Questa azione non può essere annullata.');
        });
    });

    // Initialize statistics charts with smooth animations
    const statisticsCharts = document.querySelectorAll('.statistics-chart');
    statisticsCharts.forEach(chartCanvas => {
        const ctx = chartCanvas.getContext('2d');
        
        // Get data from data-attribute
        const chartData = JSON.parse(chartCanvas.dataset.chartData || '{}');
        const chartType = chartCanvas.dataset.chartType || 'line';
        
        // Chart configuration with improved animation
        const chartConfig = {
            type: chartType,
            data: {
                labels: chartData.labels || [],
                datasets: [{
                    label: chartData.label || 'Data',
                    data: chartData.data || [],
                    backgroundColor: 'rgba(138, 67, 204, 0.2)',
                    borderColor: 'rgba(138, 67, 204, 1)',
                    borderWidth: 1,
                    tension: 0.4, // Smoother curves for line charts
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: 1000,
                    easing: 'easeOutQuart'
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            drawBorder: false
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                },
                plugins: {
                    legend: {
                        labels: {
                            usePointStyle: true,
                            padding: 20
                        }
                    },
                    tooltip: {
                        enabled: true,
                        mode: 'index',
                        intersect: false,
                        animation: {
                            duration: 100
                        },
                        backgroundColor: 'rgba(0, 0, 0, 0.7)',
                        padding: 10,
                        cornerRadius: 4
                    }
                },
                interaction: {
                    mode: 'nearest',
                    axis: 'x',
                    intersect: false
                }
            }
        };
        
        // Create chart
        new Chart(ctx, chartConfig);
    });
    
    // Command toggle switch handler with improved feedback
    const commandToggleSwitches = document.querySelectorAll('.command-toggle');
    commandToggleSwitches.forEach(toggle => {
        toggle.addEventListener('change', function() {
            const commandId = this.dataset.commandId;
            const commandName = this.dataset.commandName || 'Comando';
            const form = document.getElementById(`toggleForm_${commandId}`);
            
            // Apply visual feedback
            const label = this.closest('label');
            if (label) {
                label.classList.add('toggle-animate');
                setTimeout(() => label.classList.remove('toggle-animate'), 500);
            }
            
            if (form) {
                // Show micro-loader
                const loaderElement = document.createElement('span');
                loaderElement.className = 'toggle-loader';
                loaderElement.innerHTML = '<span class="spinner-grow spinner-grow-sm" role="status" aria-hidden="true"></span>';
                
                this.parentNode.appendChild(loaderElement);
                
                // Submit form
                form.submit();
                
                // Show toast
                const status = this.checked ? 'attivato' : 'disattivato';
                showToast('Comando aggiornato', `${commandName} è stato ${status}`, 'info');
            }
        });
    });
    
    // Copy to clipboard function with better feedback
    function copyToClipboard(text) {
        // Use modern clipboard API if available
        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(text)
                .catch(error => {
                    console.error('Clipboard API error:', error);
                    // Fallback to older method
                    fallbackCopyToClipboard(text);
                });
        } else {
            // Fallback for browsers that don't support clipboard API
            fallbackCopyToClipboard(text);
        }
    }
    
    // Fallback copy method
    function fallbackCopyToClipboard(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
    }
    
    // Add listeners to copy buttons with improved feedback
    const copyButtons = document.querySelectorAll('.copy-btn');
    copyButtons.forEach(button => {
        button.addEventListener('click', function() {
            const textToCopy = this.dataset.copyText;
            copyToClipboard(textToCopy);
            
            // User feedback with animation
            const originalText = this.innerHTML;
            const originalClass = this.className;
            
            this.innerHTML = '<i class="fas fa-check"></i> Copiato!';
            this.className = originalClass + ' copy-success pulse-effect';
            
            setTimeout(() => {
                this.innerHTML = originalText;
                this.className = originalClass;
            }, 2000);
        });
    });
    
    // Initialize sidebar collapse with smooth transition
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarElement = document.querySelector('.sidebar');
    
    if (sidebarToggle && sidebarElement) {
        // Add smooth transition class
        sidebarElement.classList.add('transition-enabled');
        
        sidebarToggle.addEventListener('click', function() {
            document.body.classList.toggle('sidebar-collapsed');
            
            // Save state in localStorage
            const isCollapsed = document.body.classList.contains('sidebar-collapsed');
            localStorage.setItem('sidebarCollapsed', isCollapsed);
            
            // Add animation class
            sidebarElement.classList.add('animating');
            setTimeout(() => sidebarElement.classList.remove('animating'), 300);
        });
        
        // Restore sidebar state from localStorage
        const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
        if (isCollapsed) {
            document.body.classList.add('sidebar-collapsed');
        }
    }
    
    // Fix navigation links - ensure all links are valid
    document.querySelectorAll('a[href]:not([href^="#"]):not([href^="mailto:"]):not([href^="tel:"]):not([href^="http"]):not([href^="https"])').forEach(link => {
        // Check for links missing leading slash
        if (link.getAttribute('href') && !link.getAttribute('href').startsWith('/') && !link.getAttribute('href').startsWith('./')) {
            link.setAttribute('href', '/' + link.getAttribute('href'));
        }
        
        // Add active class to current page links
        if (link.getAttribute('href') === window.location.pathname || 
            link.getAttribute('href') === window.location.pathname + window.location.search) {
            link.classList.add('active');
            
            // Also add active class to parent list item if in a navbar
            const parentLi = link.closest('li');
            if (parentLi) {
                parentLi.classList.add('active');
                
                // If in a dropdown, also activate the dropdown toggle
                const dropdownMenu = parentLi.closest('.dropdown-menu');
                if (dropdownMenu) {
                    const dropdownToggle = document.querySelector(`[data-bs-toggle="dropdown"][aria-expanded="false"][data-bs-auto-close]`);
                    if (dropdownToggle) {
                        dropdownToggle.classList.add('active');
                    }
                }
            }
        }
    });
    
    // Initialize page transitions
    document.addEventListener('click', function(e) {
        // Only process links that navigate within the site
        const link = e.target.closest('a');
        if (link && link.getAttribute('href') && 
            !link.getAttribute('href').startsWith('#') && 
            !link.getAttribute('href').startsWith('http') && 
            !link.getAttribute('href').startsWith('mailto:') &&
            !link.getAttribute('href').startsWith('tel:') &&
            !link.hasAttribute('download') &&
            !link.hasAttribute('target') &&
            !e.ctrlKey && !e.metaKey) {
            
            e.preventDefault();
            
            // Add page transition effect
            document.body.classList.add('page-transition-out');
            
            // Navigate after transition
            setTimeout(() => {
                window.location.href = link.href;
            }, 300);
        }
    });
    
    // Add page-in transition class on load
    document.body.classList.add('page-transition-in');
    
    // Remove transition class after animation completes
    setTimeout(() => {
        document.body.classList.remove('page-transition-in');
    }, 500);

    registerNotificationHandlers();
});

// Helper function to show toasts with improved animations
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
    const typeIcon = {
        'success': '<i class="fas fa-check-circle me-2"></i>',
        'danger': '<i class="fas fa-exclamation-circle me-2"></i>',
        'warning': '<i class="fas fa-exclamation-triangle me-2"></i>',
        'info': '<i class="fas fa-info-circle me-2"></i>'
    };
    
    const icon = typeIcon[type] || '';
    
    const html = `
    <div id="${toastId}" class="toast hardware-accelerated" role="alert" aria-live="assertive" aria-atomic="true">
        <div class="toast-header bg-${type} text-white">
            <strong class="me-auto">${icon}${title}</strong>
            <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
        <div class="toast-body">
            ${message}
        </div>
    </div>
    `;
    
    document.getElementById('toast-container').insertAdjacentHTML('beforeend', html);
    const toastElement = document.getElementById(toastId);
    
    // Apply entrance animation
    toastElement.classList.add('toast-enter');
    
    const toast = new bootstrap.Toast(toastElement, {
        animation: true,
        autohide: true,
        delay: 5000
    });
    
    toast.show();
    
    // Remove entrance animation after it completes
    setTimeout(() => {
        if (toastElement) {
            toastElement.classList.remove('toast-enter');
        }
    }, 300);
    
    // Add exit animation before hiding
    toastElement.addEventListener('hide.bs.toast', function() {
        this.classList.add('toast-exit');
    });
    
    // Auto-remove toast from DOM after it's hidden
    toastElement.addEventListener('hidden.bs.toast', function() {
        this.remove();
    });
}

/**
 * Mostra un feedback visuale per un'azione
 * @param {string} type - Tipo di feedback: success, error, warning, info
 * @param {string} message - Messaggio da mostrare
 * @param {number} duration - Durata in millisecondi
 */
function showActionFeedback(type = 'success', message, duration = 3000) {
    // Rimuovi qualsiasi feedback esistente
    const existingFeedback = document.querySelector('.action-feedback');
    if (existingFeedback) {
        existingFeedback.remove();
    }
    
    // Crea elemento feedback
    const feedback = document.createElement('div');
    feedback.className = `action-feedback ${type}`;
    
    // Icona appropriata per il tipo
    let icon;
    switch (type) {
        case 'success': icon = 'check-circle'; break;
        case 'error': icon = 'times-circle'; break;
        case 'warning': icon = 'exclamation-triangle'; break;
        default: icon = 'info-circle';
    }
    
    feedback.innerHTML = `
        <i class="fas fa-${icon} me-2"></i>
        <span>${message}</span>
    `;
    
    // Aggiungi al DOM
    document.body.appendChild(feedback);
    
    // Trigger animazione
    setTimeout(() => feedback.classList.add('show'), 10);
    
    // Rimuovi dopo durata specificata
    setTimeout(() => {
        feedback.classList.remove('show');
        setTimeout(() => feedback.remove(), 300);
    }, duration);
    
    return feedback;
}

/**
 * Registra gli handler per le notifiche nell'applicazione
 * Gestisce notifiche push, notifiche in-app e feedback
 */
function registerNotificationHandlers() {
    // Verifica supporto per notifiche
    if ('Notification' in window) {
        // Gestisce il click sul pulsante di richiesta permessi
        const notificationPermissionBtn = document.getElementById('request-notification-permission');
        if (notificationPermissionBtn) {
            notificationPermissionBtn.addEventListener('click', requestNotificationPermission);
        }
        
        // Aggiorna UI in base allo stato attuale
        updateNotificationUI();
    }
    
    // Gestione notifiche in-app (toast)
    const notificationToasts = document.querySelectorAll('[data-notification]');
    notificationToasts.forEach(toast => {
        const type = toast.dataset.notificationType || 'info';
        const message = toast.dataset.notification;
        const duration = parseInt(toast.dataset.notificationDuration || '5000', 10);
        
        if (message) {
            setTimeout(() => {
                showActionFeedback(type, message, duration);
                toast.remove(); // Rimuovi dopo averlo mostrato
            }, 500);
        }
    });
}

/**
 * Richiede il permesso per le notifiche
 */
async function requestNotificationPermission() {
    try {
        const permission = await Notification.requestPermission();
        
        if (permission === 'granted') {
            showActionFeedback('success', 'Permesso notifiche accordato!', 3000);
        } else if (permission === 'denied') {
            showActionFeedback('warning', 'Permesso notifiche negato. Modifica le impostazioni del browser.', 5000);
        }
        
        updateNotificationUI();
        return permission;
    } catch (error) {
        console.error('Errore nella richiesta permesso notifiche:', error);
        showActionFeedback('error', 'Errore nella richiesta permesso notifiche', 3000);
        return null;
    }
}

/**
 * Aggiorna l'interfaccia utente in base allo stato delle notifiche
 */
function updateNotificationUI() {
    const permission = Notification.permission;
    const notificationStatus = document.getElementById('notification-permission-status');
    const notificationToggle = document.getElementById('notification-toggle');
    const permissionBtn = document.getElementById('request-notification-permission');
    
    if (!notificationStatus && !notificationToggle && !permissionBtn) return;
    
    // Aggiorna stato testo
    if (notificationStatus) {
        let statusText = '';
        let statusClass = '';
        
        switch (permission) {
            case 'granted':
                statusText = 'Accordato';
                statusClass = 'text-success';
                break;
            case 'denied':
                statusText = 'Negato';
                statusClass = 'text-danger';
                break;
            default:
                statusText = 'Non richiesto';
                statusClass = 'text-warning';
        }
        
        notificationStatus.textContent = statusText;
        notificationStatus.className = statusClass;
    }
    
    // Aggiorna toggle
    if (notificationToggle) {
        notificationToggle.disabled = permission !== 'granted';
    }
    
    // Aggiorna pulsante permesso
    if (permissionBtn) {
        permissionBtn.style.display = permission === 'default' ? 'block' : 'none';
    }
}
