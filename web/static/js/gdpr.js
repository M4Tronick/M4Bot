/**
 * M4Bot GDPR - Gestione consenso e cookie
 * Questo script gestisce il banner dei cookie GDPR, le impostazioni sulla privacy
 * e il salvataggio delle preferenze dell'utente.
 */

// Configurazione dei cookie
const COOKIE_CONSENT_NAME = 'm4bot_cookie_consent';
const COOKIE_SETTINGS_NAME = 'm4bot_cookie_settings';
const COOKIE_EXPIRY_DAYS = 365;

// Categorie di cookie
const cookieCategories = {
  necessary: {
    name: 'Necessari',
    description: 'Questi cookie sono essenziali per il funzionamento del sito web e non possono essere disattivati.',
    required: true
  },
  functional: {
    name: 'Funzionali',
    description: 'Questi cookie consentono funzionalità avanzate come la personalizzazione e il salvataggio delle preferenze.',
    required: false
  },
  analytics: {
    name: 'Analitici',
    description: 'Questi cookie ci aiutano a capire come i visitatori interagiscono con il sito, raccogliendo informazioni in forma anonima.',
    required: false
  },
  marketing: {
    name: 'Marketing',
    description: 'Questi cookie vengono utilizzati per tracciare i visitatori su diversi siti web e mostrare annunci pertinenti.',
    required: false
  }
};

// Stato corrente del consenso
let currentConsent = {
  necessary: true,
  functional: false,
  analytics: false,
  marketing: false,
  timestamp: null
};

// Funzioni di utilità per i cookie
function setCookie(name, value, days) {
  const expires = new Date();
  expires.setTime(expires.getTime() + days * 24 * 60 * 60 * 1000);
  document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/;SameSite=Lax`;
}

function getCookie(name) {
  const nameEQ = `${name}=`;
  const ca = document.cookie.split(';');
  for (let i = 0; i < ca.length; i++) {
    let c = ca[i];
    while (c.charAt(0) === ' ') c = c.substring(1, c.length);
    if (c.indexOf(nameEQ) === 0) return c.substring(nameEQ.length, c.length);
  }
  return null;
}

function deleteCookie(name) {
  document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 GMT;path=/;SameSite=Lax`;
}

// Carica le impostazioni dell'utente dai cookie
function loadConsent() {
  try {
    const consentCookie = getCookie(COOKIE_CONSENT_NAME);
    const settingsCookie = getCookie(COOKIE_SETTINGS_NAME);
    
    if (consentCookie === 'true' && settingsCookie) {
      const settings = JSON.parse(atob(settingsCookie));
      
      // Verifica che le impostazioni siano valide
      if (settings && typeof settings === 'object') {
        // Mantieni necessary sempre true
        settings.necessary = true;
        
        // Aggiorna lo stato corrente del consenso
        currentConsent = {
          ...currentConsent,
          ...settings
        };
        
        return true;
      }
    }
    
    return false;
  } catch (error) {
    console.error('Errore nel caricamento delle impostazioni dei cookie:', error);
    return false;
  }
}

// Salva le impostazioni dell'utente nei cookie
function saveConsent() {
  try {
    // Aggiungi timestamp per tracciare quando è stato dato il consenso
    currentConsent.timestamp = new Date().toISOString();
    
    // Salva il consenso generale
    setCookie(COOKIE_CONSENT_NAME, 'true', COOKIE_EXPIRY_DAYS);
    
    // Salva le impostazioni dettagliate (Base64 per evitare problemi con caratteri speciali)
    const settingsValue = btoa(JSON.stringify(currentConsent));
    setCookie(COOKIE_SETTINGS_NAME, settingsValue, COOKIE_EXPIRY_DAYS);
    
    // Dispatch dell'evento per informare altre parti dell'applicazione
    document.dispatchEvent(new CustomEvent('consentUpdated', { detail: currentConsent }));
    
    return true;
  } catch (error) {
    console.error('Errore nel salvataggio delle impostazioni dei cookie:', error);
    return false;
  }
}

// Applica le impostazioni di consenso (attiva/disattiva script e cookie)
function applyConsent() {
  // Script di analisi (Google Analytics, ecc.)
  if (currentConsent.analytics) {
    enableAnalytics();
  } else {
    disableAnalytics();
  }
  
  // Script funzionali
  if (currentConsent.functional) {
    enableFunctionalScripts();
  } else {
    disableFunctionalScripts();
  }
  
  // Script di marketing
  if (currentConsent.marketing) {
    enableMarketingScripts();
  } else {
    disableMarketingScripts();
  }
}

// Abilita Analytics
function enableAnalytics() {
  // Implementazione specifica per il tuo sistema di analytics
  // Esempio per Google Analytics
  if (window.ga && window.ga.loaded) {
    window.ga('consent', 'update', {
      analytics_storage: 'granted'
    });
  }
}

// Disabilita Analytics
function disableAnalytics() {
  // Implementazione specifica per il tuo sistema di analytics
  // Esempio per Google Analytics
  if (window.ga && window.ga.loaded) {
    window.ga('consent', 'update', {
      analytics_storage: 'denied'
    });
  }
  
  // Rimuovi cookie di analytics
  deleteCookie('_ga');
  deleteCookie('_gid');
  deleteCookie('_gat');
}

// Funzioni per script funzionali (personalizzazione, ecc.)
function enableFunctionalScripts() {
  // Implementazione specifica per i tuoi script funzionali
}

function disableFunctionalScripts() {
  // Implementazione specifica per disabilitare script funzionali
  // Rimuovi i cookie funzionali
  const functionalCookies = ['preferences', 'session_settings'];
  functionalCookies.forEach(cookie => deleteCookie(cookie));
}

// Funzioni per script di marketing
function enableMarketingScripts() {
  // Implementazione specifica per script di marketing
}

function disableMarketingScripts() {
  // Implementazione specifica per disabilitare script di marketing
  // Rimuovi cookie di marketing
  const marketingCookies = ['_fbp', '_gcl_au'];
  marketingCookies.forEach(cookie => deleteCookie(cookie));
}

// Mostra il banner GDPR
function showBanner() {
  const banner = document.querySelector('.gdpr-banner');
  if (banner) {
    setTimeout(() => {
      banner.classList.add('show');
    }, 1000); // Mostra con un leggero ritardo per non disturbare immediatamente
  }
}

// Nascondi il banner GDPR
function hideBanner() {
  const banner = document.querySelector('.gdpr-banner');
  if (banner) {
    banner.classList.remove('show');
  }
}

// Mostra il modale delle impostazioni sulla privacy
function showPrivacySettings() {
  const modal = document.querySelector('.privacy-settings-modal');
  if (modal) {
    // Aggiorna lo stato degli switch in base alle impostazioni correnti
    Object.keys(cookieCategories).forEach(category => {
      const checkbox = document.querySelector(`#privacy-${category}`);
      if (checkbox) {
        checkbox.checked = currentConsent[category];
        checkbox.disabled = cookieCategories[category].required;
      }
    });
    
    modal.classList.add('show');
  }
}

// Nascondi il modale delle impostazioni sulla privacy
function hidePrivacySettings() {
  const modal = document.querySelector('.privacy-settings-modal');
  if (modal) {
    modal.classList.remove('show');
  }
}

// Accetta tutti i cookie
function acceptAllCookies() {
  Object.keys(cookieCategories).forEach(category => {
    currentConsent[category] = true;
  });
  
  saveConsent();
  applyConsent();
  hideBanner();
}

// Accetta solo i cookie necessari
function acceptNecessaryCookies() {
  Object.keys(cookieCategories).forEach(category => {
    currentConsent[category] = cookieCategories[category].required;
  });
  
  saveConsent();
  applyConsent();
  hideBanner();
}

// Salva le preferenze personalizzate
function savePreferences() {
  Object.keys(cookieCategories).forEach(category => {
    if (!cookieCategories[category].required) {
      const checkbox = document.querySelector(`#privacy-${category}`);
      if (checkbox) {
        currentConsent[category] = checkbox.checked;
      }
    }
  });
  
  saveConsent();
  applyConsent();
  hidePrivacySettings();
  hideBanner();
}

// Crea e inserisci il banner GDPR e il modale delle impostazioni
function createGDPRElements() {
  // Banner GDPR
  const banner = document.createElement('div');
  banner.className = 'gdpr-banner';
  banner.innerHTML = `
    <div class="gdpr-content">
      <p>Utilizziamo i cookie per offrirti la migliore esperienza sul nostro sito. Per saperne di più, consulta la nostra <a href="/privacy-policy">Privacy Policy</a>.</p>
    </div>
    <div class="gdpr-actions">
      <button class="btn btn-outline-primary gdpr-settings-btn">Impostazioni</button>
      <button class="btn btn-secondary gdpr-necessary-btn">Solo Necessari</button>
      <button class="btn btn-primary gdpr-accept-btn">Accetta Tutti</button>
    </div>
  `;
  
  // Modale delle impostazioni sulla privacy
  const modal = document.createElement('div');
  modal.className = 'privacy-settings-modal';
  
  let categoriesHTML = '';
  Object.keys(cookieCategories).forEach(category => {
    const { name, description, required } = cookieCategories[category];
    categoriesHTML += `
      <div class="privacy-category">
        <h3>${name}</h3>
        <div class="privacy-toggle">
          <label class="switch">
            <input type="checkbox" id="privacy-${category}" ${required ? 'checked disabled' : ''}>
            <span class="slider"></span>
          </label>
          <label for="privacy-${category}">
            ${name}
            <span>${description}</span>
          </label>
        </div>
      </div>
    `;
  });
  
  modal.innerHTML = `
    <div class="privacy-settings-content">
      <div class="privacy-settings-header">
        <h2>Impostazioni Privacy</h2>
      </div>
      <div class="privacy-settings-body">
        <p>Configurazione delle preferenze sui cookie. I cookie necessari non possono essere disabilitati poiché sono essenziali per il funzionamento del sito.</p>
        ${categoriesHTML}
      </div>
      <div class="privacy-settings-footer">
        <button class="btn btn-outline-primary privacy-close-btn">Chiudi</button>
        <button class="btn btn-primary privacy-save-btn">Salva Preferenze</button>
      </div>
    </div>
  `;
  
  // Aggiungi al DOM
  document.body.appendChild(banner);
  document.body.appendChild(modal);
  
  // Aggiungi event listeners
  document.querySelector('.gdpr-accept-btn').addEventListener('click', acceptAllCookies);
  document.querySelector('.gdpr-necessary-btn').addEventListener('click', acceptNecessaryCookies);
  document.querySelector('.gdpr-settings-btn').addEventListener('click', showPrivacySettings);
  document.querySelector('.privacy-close-btn').addEventListener('click', hidePrivacySettings);
  document.querySelector('.privacy-save-btn').addEventListener('click', savePreferences);
  
  // Chiudi il modale cliccando fuori
  modal.addEventListener('click', function(e) {
    if (e.target === modal) {
      hidePrivacySettings();
    }
  });
}

// Inizializza il sistema GDPR
function initGDPR() {
  // Crea gli elementi GDPR
  createGDPRElements();
  
  // Carica le impostazioni salvate
  const hasConsent = loadConsent();
  
  // Se l'utente non ha già dato il consenso, mostra il banner
  if (!hasConsent) {
    showBanner();
  } else {
    // Applica le impostazioni salvate
    applyConsent();
  }
}

// Attendi che il DOM sia completamente caricato
document.addEventListener('DOMContentLoaded', initGDPR);

// Esponi l'API GDPR globalmente
window.M4BotGDPR = {
  showSettings: showPrivacySettings,
  acceptAll: acceptAllCookies,
  acceptNecessary: acceptNecessaryCookies,
  getConsent: () => ({ ...currentConsent }),
  resetConsent: () => {
    deleteCookie(COOKIE_CONSENT_NAME);
    deleteCookie(COOKIE_SETTINGS_NAME);
    location.reload();
  }
}; 