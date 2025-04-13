/**
 * M4Bot Icons JavaScript Handler
 * Gestisce le animazioni e interazioni delle icone
 */

document.addEventListener('DOMContentLoaded', function() {
    // Pulsanti con icone pulsanti
    const pulseButtons = document.querySelectorAll('.pulse-button');
    
    pulseButtons.forEach(button => {
        button.addEventListener('mouseenter', function() {
            const icon = this.querySelector('i');
            if (icon) {
                icon.classList.add('icon-pulse');
            }
        });
        
        button.addEventListener('mouseleave', function() {
            const icon = this.querySelector('i');
            if (icon) {
                icon.classList.remove('icon-pulse');
            }
        });
    });

    // Icone che ruotano al passaggio del mouse
    const spinIcons = document.querySelectorAll('.spin-on-hover');
    
    spinIcons.forEach(icon => {
        icon.addEventListener('mouseenter', function() {
            this.classList.add('icon-spin');
        });
        
        icon.addEventListener('mouseleave', function() {
            this.classList.remove('icon-spin');
        });
    });

    // Icone che rimbalzano al passaggio del mouse
    const bounceIcons = document.querySelectorAll('.bounce-on-hover');
    
    bounceIcons.forEach(icon => {
        icon.addEventListener('mouseenter', function() {
            this.classList.add('icon-bounce');
        });
        
        icon.addEventListener('mouseleave', function() {
            this.classList.remove('icon-bounce');
        });
    });

    // Controllo dello stato del bot
    function updateBotStatus() {
        const statusIndicator = document.querySelector('.bot-status-indicator');
        if (!statusIndicator) return;

        // Qui potremmo fare una chiamata API per verificare lo stato reale
        // Per ora simuliamo uno stato casuale
        const states = ['online', 'offline', 'idle'];
        const randomState = states[Math.floor(Math.random() * states.length)];
        
        // Rimuoviamo tutte le classi di stato esistenti
        statusIndicator.classList.remove('status-online', 'status-offline', 'status-idle');
        
        // Aggiungiamo la classe corrispondente allo stato attuale
        statusIndicator.classList.add(`status-${randomState}`);
        
        // Aggiorniamo anche il testo se necessario
        const statusText = statusIndicator.nextElementSibling;
        if (statusText) {
            statusText.textContent = randomState.charAt(0).toUpperCase() + randomState.slice(1);
        }
    }

    // Aggiorniamo lo stato iniziale
    updateBotStatus();
    
    // E poi ogni 30 secondi (solo per simulazione)
    // In produzione si potrebbe fare una chiamata API vera e propria
    setInterval(updateBotStatus, 30000);

    // Animazioni per card di funzionalità
    const featureCards = document.querySelectorAll('.feature-card');
    
    featureCards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            const icon = this.querySelector('.feature-icon');
            if (icon) {
                icon.classList.add('icon-pulse');
            }
        });
        
        card.addEventListener('mouseleave', function() {
            const icon = this.querySelector('.feature-icon');
            if (icon) {
                icon.classList.remove('icon-pulse');
            }
        });
    });
}); 