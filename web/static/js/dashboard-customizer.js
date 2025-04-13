/**
 * M4Bot - Dashboard Customizer
 * Gestisce il layout personalizzabile della dashboard
 */

document.addEventListener('DOMContentLoaded', function() {
    const dashboard = document.getElementById('customizable-dashboard');
    if (!dashboard) return;
    
    // Inizializza drag-and-drop
    initializeDragAndDrop();
    
    // Carica layout salvato
    loadUserLayout();
    
    // Abilita pulsante di salvataggio
    document.getElementById('save-layout').addEventListener('click', saveUserLayout);
    
    // Toggle modalità di edit
    document.getElementById('toggle-edit-mode').addEventListener('click', toggleEditMode);
});

/**
 * Inizializza il drag-and-drop per i widget della dashboard
 */
function initializeDragAndDrop() {
    let items = document.querySelectorAll('.dashboard-card');
    
    items.forEach(item => {
        // Aggiungi maniglia e pulsanti solo in modalità edit
        const cardHeader = item.querySelector('.card-header');
        if (cardHeader) {
            const cardHandle = document.createElement('div');
            cardHandle.className = 'card-handle edit-control';
            cardHandle.innerHTML = '<i class="fas fa-grip-horizontal"></i>';
            cardHeader.prepend(cardHandle);
        }
        
        // Aggiungi pulsanti di controllo dimensione
        const sizeControls = document.createElement('div');
        sizeControls.className = 'size-controls edit-control';
        sizeControls.innerHTML = `
            <button class="btn-size" data-action="expand" title="Espandi"><i class="fas fa-expand"></i></button>
            <button class="btn-size" data-action="contract" title="Riduci"><i class="fas fa-compress"></i></button>
            <button class="btn-visibility" data-action="toggle" title="Mostra/Nascondi"><i class="fas fa-eye"></i></button>
        `;
        item.appendChild(sizeControls);
        
        // Gestione eventi drag
        item.setAttribute('draggable', 'true');
        item.addEventListener('dragstart', handleDragStart);
        item.addEventListener('dragend', handleDragEnd);
        
        // Gestione ridimensionamento
        sizeControls.querySelectorAll('.btn-size').forEach(btn => {
            btn.addEventListener('click', handleResize);
        });
        
        // Gestione visibilità
        sizeControls.querySelector('.btn-visibility').addEventListener('click', handleVisibility);
    });
    
    // Aggiungi eventi drag sulla dashboard
    dashboard.addEventListener('dragover', handleDragOver);
    dashboard.addEventListener('dragenter', handleDragEnter);
    dashboard.addEventListener('dragleave', handleDragLeave);
    dashboard.addEventListener('drop', handleDrop);
    
    // Nascondi controlli di editing all'inizio
    document.querySelectorAll('.edit-control').forEach(el => {
        el.style.display = 'none';
    });
}

/**
 * Carica il layout salvato dell'utente
 */
function loadUserLayout() {
    // Tenta di caricare dal localStorage
    const savedLayout = localStorage.getItem('dashboard_layout');
    if (!savedLayout) return;
    
    try {
        const layout = JSON.parse(savedLayout);
        
        // Applica layout salvato
        layout.forEach(item => {
            const card = document.getElementById(item.id);
            if (!card) return;
            
            // Imposta dimensione
            if (item.size) {
                setCardSize(card, item.size);
            }
            
            // Imposta visibilità
            if (item.visible === false) {
                card.classList.add('d-none');
                const visibilityBtn = card.querySelector('.btn-visibility i');
                if (visibilityBtn) {
                    visibilityBtn.className = 'fas fa-eye-slash';
                }
            }
            
            // Imposta ordine
            if (typeof item.order === 'number') {
                card.style.order = item.order;
            }
        });
    } catch (error) {
        console.error('Errore caricamento layout dashboard:', error);
    }
}

/**
 * Salva il layout personalizzato dell'utente
 */
function saveUserLayout() {
    const layout = [];
    document.querySelectorAll('.dashboard-card').forEach(card => {
        layout.push({
            id: card.id,
            order: parseInt(card.style.order) || Array.from(card.parentNode.children).indexOf(card),
            size: card.dataset.size || 'normal',
            visible: !card.classList.contains('d-none')
        });
    });
    
    // Salva nel localStorage
    localStorage.setItem('dashboard_layout', JSON.stringify(layout));
    
    // Invia al server
    fetch('/api/dashboard/layout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ layout })
    })
    .then(response => response.json())
    .then(data => {
        showToast('Successo', 'Layout salvato con successo', 'success');
    })
    .catch(error => {
        console.error('Errore salvataggio layout:', error);
        // Salvataggio locale riuscito comunque
        showToast('Avviso', 'Layout salvato localmente, ma non sul server', 'warning');
    });
}

/**
 * Attiva/disattiva la modalità di editing
 */
function toggleEditMode() {
    const dashboard = document.getElementById('customizable-dashboard');
    const isEditMode = dashboard.classList.toggle('edit-mode');
    
    // Mostra/nascondi controlli di editing
    document.querySelectorAll('.edit-control').forEach(el => {
        el.style.display = isEditMode ? 'block' : 'none';
    });
    
    // Aggiorna testo pulsante
    const toggleBtn = document.getElementById('toggle-edit-mode');
    if (isEditMode) {
        toggleBtn.innerHTML = '<i class="fas fa-check me-1"></i>Fine personalizzazione';
        toggleBtn.classList.replace('btn-outline-primary', 'btn-success');
        
        // Mostra pulsante salva
        document.getElementById('save-layout').classList.remove('d-none');
    } else {
        toggleBtn.innerHTML = '<i class="fas fa-edit me-1"></i>Personalizza';
        toggleBtn.classList.replace('btn-success', 'btn-outline-primary');
        
        // Nascondi pulsante salva
        document.getElementById('save-layout').classList.add('d-none');
    }
}

/**
 * Gestisce l'inizio del drag
 */
function handleDragStart(e) {
    this.classList.add('dragging');
    e.dataTransfer.setData('text/plain', this.id);
    e.dataTransfer.effectAllowed = 'move';
}

/**
 * Gestisce la fine del drag
 */
function handleDragEnd(e) {
    this.classList.remove('dragging');
    document.querySelectorAll('.dashboard-slot').forEach(slot => {
        slot.classList.remove('drag-over');
    });
}

/**
 * Gestisce il drag over su uno slot
 */
function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
}

/**
 * Gestisce l'entrata del drag in uno slot
 */
function handleDragEnter(e) {
    e.preventDefault();
    if (e.target.classList.contains('dashboard-slot')) {
        e.target.classList.add('drag-over');
    }
}

/**
 * Gestisce l'uscita del drag da uno slot
 */
function handleDragLeave(e) {
    if (e.target.classList.contains('dashboard-slot')) {
        e.target.classList.remove('drag-over');
    }
}

/**
 * Gestisce il drop su uno slot
 */
function handleDrop(e) {
    e.preventDefault();
    
    const cardId = e.dataTransfer.getData('text/plain');
    const card = document.getElementById(cardId);
    if (!card) return;
    
    let targetSlot = e.target;
    
    // Trova lo slot più vicino (potrebbe essere un elemento figlio)
    while (targetSlot && !targetSlot.classList.contains('dashboard-slot')) {
        targetSlot = targetSlot.parentElement;
        if (targetSlot === document.body) return; // Sicurezza
    }
    
    if (targetSlot) {
        targetSlot.classList.remove('drag-over');
        targetSlot.appendChild(card);
    }
}

/**
 * Gestisce il ridimensionamento di un widget
 */
function handleResize(e) {
    e.preventDefault();
    const action = this.dataset.action;
    const card = this.closest('.dashboard-card');
    
    if (action === 'expand') {
        // Espandi dimensione
        const currentSize = card.dataset.size || 'normal';
        let newSize;
        
        switch (currentSize) {
            case 'normal':
                newSize = 'wide';
                break;
            case 'wide':
                newSize = 'full';
                break;
            default:
                return; // Già dimensione massima
        }
        
        setCardSize(card, newSize);
    } else if (action === 'contract') {
        // Riduci dimensione
        const currentSize = card.dataset.size || 'normal';
        let newSize;
        
        switch (currentSize) {
            case 'full':
                newSize = 'wide';
                break;
            case 'wide':
                newSize = 'normal';
                break;
            default:
                return; // Già dimensione minima
        }
        
        setCardSize(card, newSize);
    }
}

/**
 * Imposta la dimensione di un widget
 */
function setCardSize(card, size) {
    // Rimuovi classi esistenti
    card.classList.remove('card-normal', 'card-wide', 'card-full');
    
    // Aggiorna attributo data
    card.dataset.size = size;
    
    // Aggiungi classe appropriata
    card.classList.add('card-' + size);
    
    // Aggiorna la dimensione dello slot padre
    const parentSlot = card.closest('.dashboard-slot');
    if (parentSlot) {
        parentSlot.classList.remove('col-md-4', 'col-md-8', 'col-md-12');
        
        switch (size) {
            case 'normal':
                parentSlot.classList.add('col-md-4');
                break;
            case 'wide':
                parentSlot.classList.add('col-md-8');
                break;
            case 'full':
                parentSlot.classList.add('col-md-12');
                break;
        }
    }
}

/**
 * Gestisce la visibilità di un widget
 */
function handleVisibility(e) {
    e.preventDefault();
    const card = this.closest('.dashboard-card');
    const isVisible = !card.classList.contains('d-none');
    
    if (isVisible) {
        // Nascondi card
        card.classList.add('d-none');
        this.querySelector('i').className = 'fas fa-eye-slash';
    } else {
        // Mostra card
        card.classList.remove('d-none');
        this.querySelector('i').className = 'fas fa-eye';
    }
} 