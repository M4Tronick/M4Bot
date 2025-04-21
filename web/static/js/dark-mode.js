/**
 * Script per gestire la modalità scura con transizioni fluide
 */

// Funzione per impostare la modalità in base alla preferenza dell'utente
function setDarkModePreference(isDarkMode) {
  localStorage.setItem('darkMode', isDarkMode);
  document.body.classList.toggle('dark-mode', isDarkMode);
  updateThemeToggleIcons(isDarkMode);
}

// Funzione per aggiornare le icone del toggle tema
function updateThemeToggleIcons(isDarkMode) {
  const themeIcons = document.querySelectorAll('.theme-toggle-icon');
  themeIcons.forEach(icon => {
    if (isDarkMode) {
      icon.classList.add('theme-icon-dark');
      icon.classList.remove('theme-icon-light');
    } else {
      icon.classList.add('theme-icon-light');
      icon.classList.remove('theme-icon-dark');
    }
  });
}

// Funzione per inizializzare e configurare la modalità scura
function initDarkMode() {
  // Verifica se esiste una preferenza salvata
  const savedDarkMode = localStorage.getItem('darkMode');
  
  // Verifica se il sistema operativo è impostato per la modalità scura
  const prefersDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
  
  // Imposta la modalità scura in base alle preferenze salvate o del sistema
  if (savedDarkMode !== null) {
    setDarkModePreference(savedDarkMode === 'true');
  } else {
    setDarkModePreference(prefersDarkMode);
  }
  
  // Aggiungi i pulsanti di toggle tema
  addThemeToggleButtons();
  
  // Ascolta i cambiamenti nella preferenza del sistema
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
    // Aggiorna solo se l'utente non ha esplicitamente impostato una preferenza
    if (localStorage.getItem('darkMode') === null) {
      setDarkModePreference(e.matches);
    }
  });
}

// Funzione per aggiungere pulsanti di toggle tema
function addThemeToggleButtons() {
  // Cerca i contenitori per i pulsanti di toggle tema
  const themeToggleContainers = document.querySelectorAll('.theme-toggle-container');
  
  if (themeToggleContainers.length === 0) {
    // Se non ci sono contenitori dedicati, aggiungi il pulsante nella navbar
    const navbar = document.querySelector('.navbar-nav');
    if (navbar) {
      const themeToggleItem = document.createElement('li');
      themeToggleItem.className = 'nav-item';
      themeToggleItem.innerHTML = createThemeToggleButton();
      navbar.appendChild(themeToggleItem);
    }
  } else {
    // Se ci sono contenitori dedicati, aggiungi i pulsanti in ciascuno
    themeToggleContainers.forEach(container => {
      container.innerHTML = createThemeToggleButton();
    });
  }
  
  // Aggiungi event listener a tutti i pulsanti di toggle
  const toggleButtons = document.querySelectorAll('.theme-toggle-button');
  toggleButtons.forEach(button => {
    button.addEventListener('click', toggleDarkMode);
  });
}

// Funzione per creare il pulsante di toggle tema
function createThemeToggleButton() {
  const isDarkMode = localStorage.getItem('darkMode') === 'true';
  const lightIconClass = isDarkMode ? '' : 'active';
  const darkIconClass = isDarkMode ? 'active' : '';
  
  return `
    <button class="theme-toggle-button btn" aria-label="Cambia tema">
      <span class="theme-toggle-icon theme-icon-light ${lightIconClass}">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="5"></circle>
          <line x1="12" y1="1" x2="12" y2="3"></line>
          <line x1="12" y1="21" x2="12" y2="23"></line>
          <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
          <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
          <line x1="1" y1="12" x2="3" y2="12"></line>
          <line x1="21" y1="12" x2="23" y2="12"></line>
          <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
          <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
        </svg>
      </span>
      <span class="theme-toggle-icon theme-icon-dark ${darkIconClass}">
        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
        </svg>
      </span>
    </button>
  `;
}

// Funzione per attivare/disattivare la modalità scura
function toggleDarkMode() {
  const currentState = localStorage.getItem('darkMode') === 'true';
  setDarkModePreference(!currentState);
}

// Inizializza la modalità scura quando il DOM è completamente caricato
document.addEventListener('DOMContentLoaded', () => {
    // Elementi DOM
    const themeToggleBtns = document.querySelectorAll('.theme-toggle-btn');
    
    // Controlla se esiste una preferenza salvata
    const savedTheme = localStorage.getItem('theme');
    
    // Applica il tema salvato o usa la preferenza del sistema
    if (savedTheme) {
        applyTheme(savedTheme);
    } else {
        // Controlla la preferenza del sistema operativo
        const prefersDarkMode = window.matchMedia('(prefers-color-scheme: dark)').matches;
        applyTheme(prefersDarkMode ? 'dark' : 'light');
    }
    
    // Aggiungi listener per i pulsanti di toggle
    themeToggleBtns.forEach(btn => {
        btn.addEventListener('click', toggleTheme);
    });
    
    // Aggiungi listener per cambiamenti nelle preferenze del sistema
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        if (!localStorage.getItem('theme')) {
            applyTheme(e.matches ? 'dark' : 'light');
        }
    });
    
    // Funzione per applicare il tema
    function applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        
        // Aggiorna icone e stato dei pulsanti
        updateButtons(theme);
    }
    
    // Funzione per cambiare il tema
    function toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        
        // Aggiungi classe per la transizione
        document.body.classList.add('theme-transition');
        
        // Applica il nuovo tema
        applyTheme(newTheme);
        
        // Rimuovi la classe di transizione dopo il completamento
        setTimeout(() => {
            document.body.classList.remove('theme-transition');
        }, 300); // Corrisponde alla durata della transizione CSS
    }
    
    // Aggiorna lo stato dei pulsanti
    function updateButtons(theme) {
        themeToggleBtns.forEach(btn => {
            // Opzionale: aggiorna l'aria-label per l'accessibilità
            btn.setAttribute('aria-label', theme === 'dark' 
                ? 'Passa alla modalità chiara' 
                : 'Passa alla modalità scura');
            
            // Se usi icone SVG inline, puoi anche aggiornarle qui
            // In alternativa, le icone sono gestite tramite CSS
        });
    }
});

// Stili CSS inline per le icone di toggle
const style = document.createElement('style');
style.textContent = `
  .theme-toggle-button {
    background: transparent;
    border: none;
    cursor: pointer;
    padding: 5px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    outline: none;
  }
  
  .theme-toggle-button:hover {
    background-color: rgba(0, 0, 0, 0.1);
  }
  
  .dark-mode .theme-toggle-button:hover {
    background-color: rgba(255, 255, 255, 0.1);
  }
  
  .theme-toggle-icon {
    display: flex;
    align-items: center;
    justify-content: center;
    position: absolute;
    transition: opacity var(--transition-speed, 0.3s) ease, 
                transform var(--transition-speed, 0.3s) ease;
    opacity: 0;
    transform: scale(0.5);
  }
  
  .theme-icon-light.active {
    opacity: 1;
    transform: scale(1);
  }
  
  .theme-icon-dark.active {
    opacity: 1;
    transform: scale(1);
  }
  
  .theme-toggle-icon svg {
    color: inherit;
  }
  
  @media (prefers-reduced-motion: reduce) {
    .theme-toggle-icon {
      transition: none !important;
    }
  }
`;
document.head.appendChild(style);

// Esporta le funzioni per l'utilizzo in altri moduli
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    setDarkModePreference,
    toggleDarkMode,
    initDarkMode
  };
} 