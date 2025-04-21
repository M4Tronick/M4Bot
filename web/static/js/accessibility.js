/**
 * M4Bot - Script per l'accessibilità
 * Version: 2.0.0
 * Questo script fornisce funzionalità di accessibilità per l'interfaccia utente di M4Bot
 */

document.addEventListener('DOMContentLoaded', function() {
  // Inizializzazione delle funzionalità di accessibilità
  initializeAccessibility();
  
  // Configurazione degli ascoltatori per gli elementi di accessibilità
  setupAccessibilityListeners();
  
  // Carica le preferenze di accessibilità salvate
  loadAccessibilityPreferences();
});

/**
 * Inizializza le funzionalità di accessibilità di base
 */
function initializeAccessibility() {
  // Imposta attributi ARIA per migliorare la navigazione con screen reader
  setupAriaAttributes();
  
  // Aggiungi le funzionalità di navigazione da tastiera
  setupKeyboardNavigation();
  
  // Aggiungi la funzionalità di salto alla navigazione
  setupSkipLinks();
  
  // Inizializza il controllo del contrasto
  setupContrastControl();
  
  // Inizializza il controllo della dimensione del testo
  setupTextSizeControl();
  
  // Inizializza il controllo per la riduzione delle animazioni
  setupReduceMotionControl();
  
  console.info('Funzionalità di accessibilità inizializzate');
}

/**
 * Imposta attributi ARIA su elementi importanti
 */
function setupAriaAttributes() {
  // Aggiungi ruoli ARIA e attributi a elementi chiave
  document.querySelectorAll('.navbar').forEach(nav => {
    nav.setAttribute('role', 'navigation');
    nav.setAttribute('aria-label', 'Navigazione principale');
  });
  
  document.querySelectorAll('.sidebar').forEach(sidebar => {
    sidebar.setAttribute('role', 'navigation');
    sidebar.setAttribute('aria-label', 'Menu laterale');
  });
  
  document.querySelectorAll('main').forEach(main => {
    main.setAttribute('role', 'main');
  });
  
  document.querySelectorAll('button:not([aria-label])').forEach(button => {
    if (!button.textContent.trim()) {
      // Se il pulsante non ha testo, cerchiamo un'icona e usiamo il suo titolo come etichetta
      const icon = button.querySelector('i[title]');
      if (icon && icon.title) {
        button.setAttribute('aria-label', icon.title);
      }
    }
  });
  
  // Migliora le tabelle per l'accessibilità
  document.querySelectorAll('table').forEach(table => {
    if (!table.getAttribute('role')) {
      table.setAttribute('role', 'grid');
    }
    
    // Assicurati che le celle di intestazione abbiano scope
    table.querySelectorAll('th').forEach(th => {
      if (!th.getAttribute('scope')) {
        const isInHead = th.closest('thead');
        th.setAttribute('scope', isInHead ? 'col' : 'row');
      }
    });
  });
}

/**
 * Configura la navigazione da tastiera avanzata
 */
function setupKeyboardNavigation() {
  // Aggiungi supporto per la navigazione da tastiera
  const keyboardShortcuts = {
    'alt+1': () => navigateTo('dashboard'),
    'alt+2': () => navigateTo('messages'),
    'alt+3': () => navigateTo('commands'),
    'alt+4': () => navigateTo('settings'),
    'alt+h': () => toggleHelpModal(),
    'alt+a': () => toggleAccessibilityMenu(),
    'alt+d': () => toggleDarkMode(),
    'alt+f': () => document.querySelector('#searchInput')?.focus(),
    'escape': () => closeActiveModal()
  };
  
  document.addEventListener('keydown', function(e) {
    const key = (e.altKey ? 'alt+' : '') + e.key.toLowerCase();
    
    if (keyboardShortcuts[key]) {
      e.preventDefault();
      keyboardShortcuts[key]();
    }
    
    // Gestione dei tab e dei focus
    if (e.key === 'Tab') {
      const focusableElements = document.querySelectorAll(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      );
      
      const firstElement = focusableElements[0];
      const lastElement = focusableElements[focusableElements.length - 1];
      
      // Aggiungi un outline visibile per indicare l'elemento focalizzato
      if (document.activeElement) {
        document.activeElement.classList.add('keyboard-focus');
      }
    }
  });
  
  // Rimuovi l'outline quando si usa il mouse
  document.addEventListener('mousedown', function() {
    document.querySelectorAll('.keyboard-focus').forEach(el => {
      el.classList.remove('keyboard-focus');
    });
  });
  
  // Inizializza il modal con le scorciatoie da tastiera
  createKeyboardShortcutsModal(keyboardShortcuts);
}

/**
 * Crea modal per le scorciatoie da tastiera
 */
function createKeyboardShortcutsModal(shortcuts) {
  // Controlla se il modal esiste già
  if (document.getElementById('keyboardShortcutsModal')) {
    return;
  }
  
  const modal = document.createElement('div');
  modal.id = 'keyboardShortcutsModal';
  modal.className = 'modal fade';
  modal.setAttribute('tabindex', '-1');
  modal.setAttribute('aria-labelledby', 'keyboardShortcutsModalLabel');
  modal.setAttribute('aria-hidden', 'true');
  
  // Crea il contenuto del modal
  let shortcutsList = '';
  for (const [key, value] of Object.entries(shortcuts)) {
    const formattedKey = key.replace('alt+', 'Alt + ').replace('escape', 'Esc');
    let description = '';
    
    if (key === 'alt+1') description = 'Vai alla Dashboard';
    if (key === 'alt+2') description = 'Vai a Messaggi';
    if (key === 'alt+3') description = 'Vai a Comandi';
    if (key === 'alt+4') description = 'Vai a Impostazioni';
    if (key === 'alt+h') description = 'Apri la Guida';
    if (key === 'alt+a') description = 'Apri menu Accessibilità';
    if (key === 'alt+d') description = 'Attiva/disattiva modalità scura';
    if (key === 'alt+f') description = 'Focalizza la barra di ricerca';
    if (key === 'escape') description = 'Chiudi finestra attiva';
    
    shortcutsList += `
      <tr>
        <td><kbd>${formattedKey}</kbd></td>
        <td>${description}</td>
      </tr>
    `;
  }
  
  modal.innerHTML = `
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title" id="keyboardShortcutsModalLabel">Scorciatoie da Tastiera</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Chiudi"></button>
        </div>
        <div class="modal-body">
          <p>Usa queste scorciatoie per navigare più velocemente:</p>
          <table class="table">
            <thead>
              <tr>
                <th scope="col">Tasto</th>
                <th scope="col">Azione</th>
              </tr>
            </thead>
            <tbody>
              ${shortcutsList}
            </tbody>
          </table>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Chiudi</button>
        </div>
      </div>
    </div>
  `;
  
  document.body.appendChild(modal);
}

/**
 * Funzioni di navigazione per le scorciatoie da tastiera
 */
function navigateTo(page) {
  const navLinks = {
    'dashboard': '/dashboard',
    'messages': '/messages',
    'commands': '/commands',
    'settings': '/settings'
  };
  
  if (navLinks[page]) {
    window.location.href = navLinks[page];
  }
}

function toggleHelpModal() {
  const helpModal = new bootstrap.Modal(document.getElementById('helpModal'));
  helpModal.toggle();
}

function toggleAccessibilityMenu() {
  const accessibilityMenu = document.getElementById('accessibilityMenu');
  if (accessibilityMenu) {
    accessibilityMenu.classList.toggle('show');
  }
}

function closeActiveModal() {
  const activeModal = document.querySelector('.modal.show');
  if (activeModal) {
    const modal = bootstrap.Modal.getInstance(activeModal);
    if (modal) {
      modal.hide();
    }
  }
}

function toggleDarkMode() {
  const currentTheme = document.documentElement.getAttribute('data-bs-theme');
  const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
  
  document.documentElement.setAttribute('data-bs-theme', newTheme);
  localStorage.setItem('theme', newTheme);
  
  // Aggiorna le icone dei toggle del tema
  document.querySelectorAll('.theme-icon').forEach(icon => {
    icon.classList.toggle('d-none');
  });
  
  // Aggiorna anche la preferenza di accessibilità
  saveAccessibilityPreference('darkMode', newTheme === 'dark');
}

/**
 * Configura i link di salto per migliorare la navigazione da tastiera
 */
function setupSkipLinks() {
  // Aggiungi il link per saltare al contenuto principale se non esiste
  if (!document.getElementById('skip-to-content')) {
    const skipLink = document.createElement('a');
    skipLink.id = 'skip-to-content';
    skipLink.href = '#main-content';
    skipLink.className = 'skip-link';
    skipLink.textContent = 'Vai al contenuto principale';
    
    document.body.insertBefore(skipLink, document.body.firstChild);
    
    // Assicurati che il contenuto principale abbia un ID appropriato
    const mainContent = document.querySelector('main');
    if (mainContent && !mainContent.id) {
      mainContent.id = 'main-content';
    }
  }
}

/**
 * Configura il controllo del contrasto
 */
function setupContrastControl() {
  const contrastToggle = document.getElementById('highContrastToggle');
  if (contrastToggle) {
    contrastToggle.addEventListener('change', function() {
      document.body.classList.toggle('high-contrast-mode', this.checked);
      saveAccessibilityPreference('highContrast', this.checked);
    });
  }
  
  // Aggiungi pulsante nel dropdown di accessibilità se non esiste
  const accessibilityDropdown = document.querySelector('.accessibility-dropdown .dropdown-menu');
  if (accessibilityDropdown && !document.getElementById('highContrastMenuItem')) {
    const contrastItem = document.createElement('div');
    contrastItem.className = 'dropdown-item';
    contrastItem.id = 'highContrastMenuItem';
    contrastItem.innerHTML = `
      <div class="form-check form-switch">
        <input class="form-check-input" type="checkbox" id="highContrastToggle">
        <label class="form-check-label" for="highContrastToggle">Alto contrasto</label>
      </div>
    `;
    accessibilityDropdown.appendChild(contrastItem);
    
    // Aggiungi ascoltatore per il pulsante appena creato
    document.getElementById('highContrastToggle').addEventListener('change', function() {
      document.body.classList.toggle('high-contrast-mode', this.checked);
      saveAccessibilityPreference('highContrast', this.checked);
    });
  }
}

/**
 * Configura il controllo della dimensione del testo
 */
function setupTextSizeControl() {
  // Aggiungi pulsanti per il controllo della dimensione del testo
  const accessibilityDropdown = document.querySelector('.accessibility-dropdown .dropdown-menu');
  if (accessibilityDropdown && !document.getElementById('textSizeControls')) {
    const textSizeItem = document.createElement('div');
    textSizeItem.className = 'dropdown-item';
    textSizeItem.id = 'textSizeControls';
    textSizeItem.innerHTML = `
      <div class="d-flex align-items-center">
        <span class="me-2">Dimensione testo:</span>
        <div class="btn-group btn-group-sm">
          <button class="btn btn-outline-secondary" id="decreaseText" aria-label="Riduci dimensione testo">A-</button>
          <button class="btn btn-outline-secondary" id="resetText" aria-label="Ripristina dimensione testo">A</button>
          <button class="btn btn-outline-secondary" id="increaseText" aria-label="Aumenta dimensione testo">A+</button>
        </div>
      </div>
    `;
    accessibilityDropdown.appendChild(textSizeItem);
    
    // Aggiungi ascoltatori ai pulsanti
    document.getElementById('decreaseText').addEventListener('click', function() {
      adjustTextSize(-1);
    });
    
    document.getElementById('resetText').addEventListener('click', function() {
      resetTextSize();
    });
    
    document.getElementById('increaseText').addEventListener('click', function() {
      adjustTextSize(1);
    });
  }
}

/**
 * Regola la dimensione del testo
 */
function adjustTextSize(direction) {
  let currentSize = parseInt(localStorage.getItem('textSizeAdjustment') || '0');
  currentSize += direction;
  
  // Limita l'intervallo di regolazione da -3 a 5
  currentSize = Math.max(-3, Math.min(5, currentSize));
  
  // Applica la nuova dimensione
  applyTextSize(currentSize);
  
  // Salva la preferenza
  localStorage.setItem('textSizeAdjustment', currentSize.toString());
  saveAccessibilityPreference('textSize', currentSize);
}

/**
 * Applica la dimensione del testo
 */
function applyTextSize(sizeAdjustment) {
  // Rimuovi tutte le classi di dimensione esistenti
  document.body.classList.remove(
    'text-size--3', 'text-size--2', 'text-size--1',
    'text-size-0',
    'text-size-1', 'text-size-2', 'text-size-3', 'text-size-4', 'text-size-5'
  );
  
  // Aggiungi la classe appropriata
  document.body.classList.add(`text-size-${sizeAdjustment}`);
}

/**
 * Ripristina la dimensione del testo predefinita
 */
function resetTextSize() {
  document.body.classList.remove(
    'text-size--3', 'text-size--2', 'text-size--1',
    'text-size-0',
    'text-size-1', 'text-size-2', 'text-size-3', 'text-size-4', 'text-size-5'
  );
  
  document.body.classList.add('text-size-0');
  localStorage.setItem('textSizeAdjustment', '0');
  saveAccessibilityPreference('textSize', 0);
}

/**
 * Configura il controllo per la riduzione delle animazioni
 */
function setupReduceMotionControl() {
  const accessibilityDropdown = document.querySelector('.accessibility-dropdown .dropdown-menu');
  if (accessibilityDropdown && !document.getElementById('reduceMotionMenuItem')) {
    const motionItem = document.createElement('div');
    motionItem.className = 'dropdown-item';
    motionItem.id = 'reduceMotionMenuItem';
    motionItem.innerHTML = `
      <div class="form-check form-switch">
        <input class="form-check-input" type="checkbox" id="reduceMotionToggle">
        <label class="form-check-label" for="reduceMotionToggle">Riduci animazioni</label>
      </div>
    `;
    accessibilityDropdown.appendChild(motionItem);
    
    // Aggiungi ascoltatore per il pulsante appena creato
    document.getElementById('reduceMotionToggle').addEventListener('change', function() {
      document.body.classList.toggle('reduce-motion', this.checked);
      saveAccessibilityPreference('reduceMotion', this.checked);
    });
  }
}

/**
 * Configura gli ascoltatori per elementi di accessibilità
 */
function setupAccessibilityListeners() {
  // Ascoltatore per il cambio di tema
  const themeToggle = document.getElementById('darkModeToggle');
  if (themeToggle) {
    themeToggle.addEventListener('change', function() {
      toggleDarkMode();
    });
  }
  
  // Ascoltatore per aprire il menu di accessibilità con Alt+A
  document.addEventListener('keydown', function(e) {
    if (e.altKey && e.key.toLowerCase() === 'a') {
      e.preventDefault();
      toggleAccessibilityMenu();
    }
  });
  
  // Ascoltatore per il modal di scorciatoie da tastiera
  const keyboardShortcutsBtn = document.getElementById('keyboardShortcutsBtn');
  if (keyboardShortcutsBtn) {
    keyboardShortcutsBtn.addEventListener('click', function() {
      const keyboardModal = new bootstrap.Modal(document.getElementById('keyboardShortcutsModal'));
      keyboardModal.show();
    });
  }
}

/**
 * Salva le preferenze di accessibilità nell'archiviazione locale
 */
function saveAccessibilityPreference(key, value) {
  // Carica le preferenze esistenti
  let preferences = JSON.parse(localStorage.getItem('accessibilityPreferences') || '{}');
  
  // Aggiorna la preferenza
  preferences[key] = value;
  
  // Salva le preferenze aggiornate
  localStorage.setItem('accessibilityPreferences', JSON.stringify(preferences));
}

/**
 * Carica e applica le preferenze di accessibilità salvate
 */
function loadAccessibilityPreferences() {
  const preferences = JSON.parse(localStorage.getItem('accessibilityPreferences') || '{}');
  
  // Applica le preferenze di tema
  if (preferences.darkMode !== undefined) {
    const currentTheme = document.documentElement.getAttribute('data-bs-theme');
    const preferredTheme = preferences.darkMode ? 'dark' : 'light';
    
    if (currentTheme !== preferredTheme) {
      document.documentElement.setAttribute('data-bs-theme', preferredTheme);
      
      // Aggiorna le icone del tema
      document.querySelectorAll('.theme-icon').forEach(icon => {
        const isDarkIcon = icon.classList.contains('dark-theme-icon');
        icon.classList.toggle('d-none', (preferredTheme === 'dark') !== isDarkIcon);
      });
    }
    
    // Aggiorna anche lo stato dell'interruttore
    const darkModeToggle = document.getElementById('darkModeToggle');
    if (darkModeToggle) {
      darkModeToggle.checked = preferences.darkMode;
    }
  }
  
  // Applica la preferenza di alto contrasto
  if (preferences.highContrast !== undefined) {
    document.body.classList.toggle('high-contrast-mode', preferences.highContrast);
    
    // Aggiorna anche lo stato dell'interruttore
    const contrastToggle = document.getElementById('highContrastToggle');
    if (contrastToggle) {
      contrastToggle.checked = preferences.highContrast;
    }
  }
  
  // Applica la dimensione del testo
  if (preferences.textSize !== undefined) {
    applyTextSize(preferences.textSize);
  }
  
  // Applica la preferenza di riduzione delle animazioni
  if (preferences.reduceMotion !== undefined) {
    document.body.classList.toggle('reduce-motion', preferences.reduceMotion);
    
    // Aggiorna anche lo stato dell'interruttore
    const motionToggle = document.getElementById('reduceMotionToggle');
    if (motionToggle) {
      motionToggle.checked = preferences.reduceMotion;
    }
  }
} 