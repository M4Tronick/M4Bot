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

    // Helper function to make standardized API calls
    async function callApi(endpoint, method = 'GET', data = null, showLoader = true) {
        try {
            if (showLoader) {
                showLoader();
            }
            
            const options = {
                method: method,
                headers: {
                    'Content-Type': 'application/json'
                }
            };
            
            if (data) {
                options.body = JSON.stringify(data);
            }
            
            const response = await fetch(endpoint, options);
            const responseData = await response.json();
            
            if (!response.ok) {
                throw new Error(responseData.error || 'Si è verificato un errore nella richiesta');
            }
            
            return responseData;
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
                    
                    const data = await callApi(endpoint, 'POST', { channel_id: channelId }, false);
                    
                    // Show success message
                    showToast('Successo', data.message, 'success');
                } catch (error) {
                    // Error handling is done in the callApi function
                } finally {
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

    // Dark mode toggle
    const darkModeToggle = document.getElementById('darkModeToggle');
    if (darkModeToggle) {
        // Check if dark mode is enabled in localStorage
        const isDarkMode = localStorage.getItem('darkMode') === 'true';
        
        // Set initial theme
        if (isDarkMode) {
            document.documentElement.setAttribute('data-bs-theme', 'dark');
            darkModeToggle.checked = true;
        }
        
        // Handle theme toggle
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

    // Function to show loader during API requests
    function showLoader() {
        // Create overlay element for the loader
        const overlay = document.createElement('div');
        overlay.className = 'spinner-overlay';
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
        
        // Add overlay to body
        document.body.appendChild(overlay);
    }

    // Function to hide loader
    function hideLoader() {
        const loader = document.getElementById('loadingSpinner');
        if (loader) {
            loader.remove();
        }
    }

    // Form validation for command form
    const commandForm = document.getElementById('commandForm');
    if (commandForm) {
        commandForm.addEventListener('submit', function(e) {
            // Validate form
            const commandName = document.getElementById('commandName').value;
            if (!commandName.startsWith('!')) {
                e.preventDefault();
                showToast('Errore', 'Il nome del comando deve iniziare con !', 'danger');
                return false;
            }
            
            // Show loader
            showLoader();
            return true;
        });
    }

    // Function to confirm deletion
    function confirmDelete(event, message) {
        if (!confirm(message || 'Sei sicuro di voler eliminare questo elemento?')) {
            event.preventDefault();
            return false;
        }
        return true;
    }

    // Add listeners to all delete buttons
    const deleteButtons = document.querySelectorAll('.delete-btn');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            return confirmDelete(e, 'Sei sicuro di voler eliminare questo elemento? Questa azione non può essere annullata.');
        });
    });

    // Initialize statistics charts
    const statisticsCharts = document.querySelectorAll('.statistics-chart');
    statisticsCharts.forEach(chartCanvas => {
        const ctx = chartCanvas.getContext('2d');
        
        // Get data from data-attribute
        const chartData = JSON.parse(chartCanvas.dataset.chartData || '{}');
        const chartType = chartCanvas.dataset.chartType || 'line';
        
        // Chart configuration
        const chartConfig = {
            type: chartType,
            data: {
                labels: chartData.labels || [],
                datasets: [{
                    label: chartData.label || 'Data',
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
        
        // Create chart
        new Chart(ctx, chartConfig);
    });
    
    // Command toggle switch handler
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
    
    // Copy to clipboard function
    function copyToClipboard(text) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
    }
    
    // Add listeners to copy buttons
    const copyButtons = document.querySelectorAll('.copy-btn');
    copyButtons.forEach(button => {
        button.addEventListener('click', function() {
            const textToCopy = this.dataset.copyText;
            copyToClipboard(textToCopy);
            
            // User feedback
            const originalText = this.innerHTML;
            this.innerHTML = '<i class="fas fa-check"></i> Copiato!';
            setTimeout(() => {
                this.innerHTML = originalText;
            }, 2000);
        });
    });
    
    // Initialize sidebar collapse
    const sidebarToggle = document.getElementById('sidebarToggle');
    if (sidebarToggle) {
        sidebarToggle.addEventListener('click', function() {
            document.body.classList.toggle('sidebar-collapsed');
            
            // Save state in localStorage
            const isCollapsed = document.body.classList.contains('sidebar-collapsed');
            localStorage.setItem('sidebarCollapsed', isCollapsed);
        });
        
        // Restore sidebar state from localStorage
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
