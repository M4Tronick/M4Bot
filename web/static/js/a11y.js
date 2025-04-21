/**
 * M4Bot - Miglioramenti di Accessibilità
 * Version: 1.0.0
 * Script che implementa varie funzionalità per migliorare l'accessibilità dell'interfaccia
 */

document.addEventListener('DOMContentLoaded', function() {
  // Inizializza tutti i miglioramenti di accessibilità
  initializeA11y();
});

/**
 * Inizializza tutti i miglioramenti di accessibilità
 */
function initializeA11y() {
  // Aggiungi attributi ARIA mancanti
  enhanceAriaAttributes();
  
  // Migliora l'accessibilità da tastiera
  enhanceKeyboardAccessibility();
  
  // Ottimizza la navigazione con screen reader
  enhanceScreenReaderSupport();
  
  // Migliora la gestione del focus
  enhanceFocusManagement();
  
  // Aggiungi skip links
  addSkipLinks();
  
  // Migliora i form
  enhanceForms();
  
  // Gestisci la modalità alto contrasto
  setupHighContrastMode();
  
  // Configura la dimensione del testo dinamica
  setupDynamicTextSize();
  
  // Installa handlers per gestione accessibilità
  installA11yEventHandlers();
}

/**
 * Migliora gli attributi ARIA in tutta l'applicazione
 */
function enhanceAriaAttributes() {
  // Aggiungi ruoli ARIA ai principali componenti dell'interfaccia
  document.querySelectorAll('nav').forEach(nav => {
    if (!nav.hasAttribute('role')) {
      nav.setAttribute('role', 'navigation');
    }
    if (!nav.hasAttribute('aria-label')) {
      nav.setAttribute('aria-label', 'Navigazione principale');
    }
  });
  
  document.querySelectorAll('main, [role="main"]').forEach(main => {
    if (!main.hasAttribute('role')) {
      main.setAttribute('role', 'main');
    }
  });
  
  document.querySelectorAll('header').forEach(header => {
    if (!header.hasAttribute('role')) {
      header.setAttribute('role', 'banner');
    }
  });
  
  document.querySelectorAll('footer').forEach(footer => {
    if (!footer.hasAttribute('role')) {
      footer.setAttribute('role', 'contentinfo');
    }
  });
  
  document.querySelectorAll('aside').forEach(aside => {
    if (!aside.hasAttribute('role')) {
      aside.setAttribute('role', 'complementary');
    }
    if (!aside.hasAttribute('aria-label')) {
      aside.setAttribute('aria-label', 'Informazioni complementari');
    }
  });
  
  // Migliora pulsanti senza testo
  document.querySelectorAll('button:not([aria-label])').forEach(button => {
    if (!button.textContent.trim()) {
      // Cerca un'icona all'interno del pulsante
      const icon = button.querySelector('i, .icon, svg');
      if (icon && icon.className) {
        // Prova a determinare lo scopo del pulsante dalla classe dell'icona
        let purpose = '';
        const iconClass = icon.className.toLowerCase();
        
        if (iconClass.includes('close') || iconClass.includes('cancel')) {
          purpose = 'Chiudi';
        } else if (iconClass.includes('search')) {
          purpose = 'Cerca';
        } else if (iconClass.includes('menu')) {
          purpose = 'Menu';
        } else if (iconClass.includes('settings')) {
          purpose = 'Impostazioni';
        } else if (iconClass.includes('user') || iconClass.includes('profile')) {
          purpose = 'Profilo';
        } else if (iconClass.includes('notif')) {
          purpose = 'Notifiche';
        } else if (iconClass.includes('edit')) {
          purpose = 'Modifica';
        } else if (iconClass.includes('delete')) {
          purpose = 'Elimina';
        } else if (iconClass.includes('add') || iconClass.includes('plus')) {
          purpose = 'Aggiungi';
        } else {
          purpose = 'Pulsante';
        }
        
        button.setAttribute('aria-label', purpose);
      } else {
        button.setAttribute('aria-label', 'Pulsante');
      }
    }
  });
  
  // Migliora le immagini senza alt text
  document.querySelectorAll('img:not([alt])').forEach(img => {
    // Se l'immagine è decorativa, usa alt vuoto
    if (img.classList.contains('decorative') || 
        img.classList.contains('decoration') || 
        img.parentElement.classList.contains('decoration')) {
      img.setAttribute('alt', '');
    } else {
      // Altrimenti prova a ricavare una descrizione dal contesto
      let alt = '';
      
      // Prova a usare il nome del file come alt text
      if (img.src) {
        const filename = img.src.split('/').pop().split('?')[0];
        alt = filename.split('.')[0].replace(/[-_]/g, ' ');
        
        // Capitalizza la prima lettera
        alt = alt.charAt(0).toUpperCase() + alt.slice(1);
      }
      
      img.setAttribute('alt', alt || 'Immagine');
    }
  });
  
  // Migliora i links con testo poco descrittivo
  document.querySelectorAll('a').forEach(link => {
    const linkText = link.textContent.trim().toLowerCase();
    
    // Controlla se il link ha testo poco descrittivo
    if (linkText === 'clicca qui' || linkText === 'qui' || 
        linkText === 'click here' || linkText === 'link' || 
        linkText === 'leggi di più' || linkText === 'maggiori info') {
      
      // Cerca il contesto del link
      let context = '';
      
      // Prova a trovare un heading più vicino
      let heading = link.closest('section, article, div')?.querySelector('h1, h2, h3, h4, h5, h6');
      if (heading) {
        context = heading.textContent.trim();
      }
      
      if (context) {
        link.setAttribute('aria-label', `${linkText} su ${context}`);
      }
    }
  });
}

/**
 * Migliora l'accessibilità da tastiera
 */
function enhanceKeyboardAccessibility() {
  // Assicura che tutti gli elementi interattivi siano raggiungibili da tastiera
  document.querySelectorAll('div[onclick], span[onclick]').forEach(el => {
    if (el.getAttribute('tabindex') === null) {
      el.setAttribute('tabindex', '0');
      el.setAttribute('role', 'button');
    }
  });
  
  // Aggiungi supporto per tastiera ai componenti personalizzati
  document.querySelectorAll('[role="button"], [role="tab"], [role="menuitem"]').forEach(el => {
    if (el.getAttribute('tabindex') === null) {
      el.setAttribute('tabindex', '0');
    }
    
    // Aggiungi supporto per la pressione dei tasti ENTER e SPACE
    if (!el.hasAttribute('data-a11y-keyhandler')) {
      el.setAttribute('data-a11y-keyhandler', 'true');
      
      el.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          el.click();
        }
      });
    }
  });
  
  // Migliora la navigazione delle dropdown
  document.querySelectorAll('.dropdown, .dropdown-menu').forEach(dropdown => {
    const trigger = dropdown.querySelector('.dropdown-toggle, [aria-haspopup="true"]');
    const menu = dropdown.querySelector('.dropdown-menu, [role="menu"]');
    
    if (trigger && menu) {
      // Assicura che trigger e menu abbiano attributi ARIA corretti
      trigger.setAttribute('aria-haspopup', 'true');
      
      if (!trigger.hasAttribute('aria-expanded')) {
        trigger.setAttribute('aria-expanded', 'false');
      }
      
      menu.setAttribute('role', 'menu');
      
      // Aggiungi i gestori di eventi se non presenti
      if (!trigger.hasAttribute('data-a11y-dropdown')) {
        trigger.setAttribute('data-a11y-dropdown', 'true');
        
        // Gestisci apertura/chiusura con tastiera
        trigger.addEventListener('keydown', function(e) {
          if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
            e.preventDefault();
            
            const expanded = trigger.getAttribute('aria-expanded') === 'true';
            trigger.setAttribute('aria-expanded', (!expanded).toString());
            
            if (!expanded) {
              // Se apre, dai il focus al primo elemento del menu
              setTimeout(() => {
                const firstItem = menu.querySelector('[role="menuitem"]');
                if (firstItem) {
                  firstItem.focus();
                }
              }, 100);
            }
          }
        });
        
        // Chiudi menu con ESC
        menu.addEventListener('keydown', function(e) {
          if (e.key === 'Escape') {
            trigger.setAttribute('aria-expanded', 'false');
            trigger.focus();
          }
        });
      }
    }
  });
}

/**
 * Ottimizza la navigazione con screen reader
 */
function enhanceScreenReaderSupport() {
  // Aggiungi regioni di pagina se mancanti
  if (!document.querySelector('main, [role="main"]')) {
    const mainContent = document.querySelector('#content, #main-content, .main-content, .container:not(header .container):not(footer .container)');
    if (mainContent) {
      mainContent.setAttribute('role', 'main');
    }
  }
  
  // Aggiungi attributi per informazioni dinamiche
  document.querySelectorAll('.alert, .notification, .message').forEach(el => {
    if (!el.hasAttribute('role')) {
      el.setAttribute('role', 'alert');
    }
    if (!el.hasAttribute('aria-live')) {
      el.setAttribute('aria-live', 'polite');
    }
  });
  
  // Aggiungi attributi a elementi con stato
  document.querySelectorAll('.active').forEach(el => {
    if (el.tagName === 'LI' || el.tagName === 'A' || el.hasAttribute('role')) {
      if (!el.hasAttribute('aria-current')) {
        el.setAttribute('aria-current', 'true');
      }
    }
  });
  
  // Migliora le tabelle
  document.querySelectorAll('table').forEach(table => {
    // Aggiungi caption per le tabelle che non ne hanno
    if (!table.querySelector('caption')) {
      const tableContext = table.closest('section, article, div');
      let heading = null;
      
      if (tableContext) {
        heading = tableContext.querySelector('h1, h2, h3, h4, h5, h6');
      }
      
      if (heading) {
        const caption = document.createElement('caption');
        caption.textContent = heading.textContent;
        table.prepend(caption);
      }
    }
    
    // Assicura che le celle di intestazione abbiano scope
    table.querySelectorAll('th').forEach(th => {
      if (!th.hasAttribute('scope')) {
        const isInThead = th.closest('thead') !== null;
        const isFirstCell = Array.from(th.parentElement.children).indexOf(th) === 0;
        
        if (isInThead) {
          th.setAttribute('scope', 'col');
        } else if (isFirstCell) {
          th.setAttribute('scope', 'row');
        }
      }
    });
  });
  
  // Aggiungi regioni di landmark mancanti
  if (!document.querySelector('aside, [role="complementary"]')) {
    const sidebar = document.querySelector('.sidebar, #sidebar, .side-panel');
    if (sidebar) {
      sidebar.setAttribute('role', 'complementary');
      sidebar.setAttribute('aria-label', 'Barra laterale');
    }
  }
}

/**
 * Migliora la gestione del focus
 */
function enhanceFocusManagement() {
  // Stili di focus personalizzati
  if (!document.getElementById('a11y-focus-styles')) {
    const style = document.createElement('style');
    style.id = 'a11y-focus-styles';
    style.textContent = `
      :focus:not(:focus-visible) {
        outline: none;
      }
      :focus-visible {
        outline: 3px solid #2563EB !important;
        outline-offset: 2px !important;
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.3) !important;
      }
    `;
    document.head.appendChild(style);
  }
  
  // Aggiungi gestione del focus per modali
  document.querySelectorAll('.modal, [role="dialog"]').forEach(modal => {
    if (!modal.hasAttribute('data-a11y-modal')) {
      modal.setAttribute('data-a11y-modal', 'true');
      
      // Trova elementi focusabili nella modale
      const focusableElements = modal.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
      
      if (focusableElements.length > 0) {
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];
        
        // Tieni il focus all'interno della modale
        modal.addEventListener('keydown', function(e) {
          if (e.key === 'Tab') {
            if (e.shiftKey && document.activeElement === firstElement) {
              e.preventDefault();
              lastElement.focus();
            } else if (!e.shiftKey && document.activeElement === lastElement) {
              e.preventDefault();
              firstElement.focus();
            }
          }
        });
      }
    }
  });
  
  // Migliora la gestione dei tab panel
  document.querySelectorAll('[role="tablist"]').forEach(tablist => {
    const tabs = tablist.querySelectorAll('[role="tab"]');
    const panels = [];
    
    // Cerca i tab panel associati
    tabs.forEach(tab => {
      const panelId = tab.getAttribute('aria-controls');
      if (panelId) {
        const panel = document.getElementById(panelId);
        if (panel) {
          panels.push(panel);
          
          // Assicura che il panel abbia attributi corretti
          panel.setAttribute('role', 'tabpanel');
          
          if (!panel.hasAttribute('aria-labelledby')) {
            panel.setAttribute('aria-labelledby', tab.id);
          }
          
          // Assicura che i tab panel non attivi non siano nel tab order
          if (!tab.classList.contains('active') && tab.getAttribute('aria-selected') !== 'true') {
            panel.setAttribute('tabindex', '-1');
          } else {
            panel.setAttribute('tabindex', '0');
          }
        }
      }
    });
    
    // Gestisci la navigazione della tastiera
    tablist.addEventListener('keydown', function(e) {
      if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
        const currentTab = document.activeElement;
        if (currentTab && currentTab.getAttribute('role') === 'tab') {
          e.preventDefault();
          
          const tabArray = Array.from(tabs);
          const currentIndex = tabArray.indexOf(currentTab);
          let newIndex;
          
          if (e.key === 'ArrowRight') {
            newIndex = (currentIndex + 1) % tabs.length;
          } else {
            newIndex = (currentIndex - 1 + tabs.length) % tabs.length;
          }
          
          tabArray[newIndex].focus();
          tabArray[newIndex].click();
        }
      }
    });
  });
}

/**
 * Aggiungi skip links per facilitare la navigazione da tastiera
 */
function addSkipLinks() {
  // Se esistono già skip link, non aggiungerli di nuovo
  if (document.querySelector('.skip-link, .skip-to-content')) {
    return;
  }
  
  // Individua le principali aree della pagina
  const mainContent = document.querySelector('main, [role="main"], #content, #main-content');
  const navigation = document.querySelector('nav, [role="navigation"]');
  const footer = document.querySelector('footer, [role="contentinfo"]');
  
  // Crea container per i link
  const skipLinksContainer = document.createElement('div');
  skipLinksContainer.className = 'skip-links';
  skipLinksContainer.style.cssText = `
    position: absolute;
    top: -1000px;
    left: -1000px;
    height: 1px;
    width: 1px;
    text-align: left;
    overflow: hidden;
    z-index: 9999;
  `;
  
  // Stile per i link
  const linkStyle = `
    position: absolute;
    top: 1000px;
    left: 1000px;
    height: auto;
    width: auto;
    padding: 1rem 1.5rem;
    background-color: #f8f9fa;
    border: 2px solid #2563EB;
    border-radius: 0.25rem;
    color: #1a202c;
    font-size: 1rem;
    font-weight: 600;
    text-decoration: none;
    z-index: 9999;
  `;
  
  // Crea link per il contenuto principale
  if (mainContent) {
    const skipToMain = document.createElement('a');
    
    // Assicura che il target abbia un ID
    if (!mainContent.id) {
      mainContent.id = 'main-content';
    }
    
    skipToMain.href = `#${mainContent.id}`;
    skipToMain.className = 'skip-link';
    skipToMain.textContent = 'Vai al contenuto principale';
    skipToMain.style.cssText = linkStyle;
    
    // Gestione focus
    skipToMain.addEventListener('focus', function() {
      this.style.top = '1rem';
      this.style.left = '1rem';
    });
    
    skipToMain.addEventListener('blur', function() {
      this.style.top = '-1000px';
      this.style.left = '-1000px';
    });
    
    skipLinksContainer.appendChild(skipToMain);
  }
  
  // Crea link per la navigazione
  if (navigation) {
    const skipToNav = document.createElement('a');
    
    if (!navigation.id) {
      navigation.id = 'navigation';
    }
    
    skipToNav.href = `#${navigation.id}`;
    skipToNav.className = 'skip-link';
    skipToNav.textContent = 'Vai alla navigazione';
    skipToNav.style.cssText = linkStyle;
    
    skipToNav.addEventListener('focus', function() {
      this.style.top = '1rem';
      this.style.left = '1rem';
    });
    
    skipToNav.addEventListener('blur', function() {
      this.style.top = '-1000px';
      this.style.left = '-1000px';
    });
    
    skipLinksContainer.appendChild(skipToNav);
  }
  
  // Crea link per il footer
  if (footer) {
    const skipToFooter = document.createElement('a');
    
    if (!footer.id) {
      footer.id = 'footer';
    }
    
    skipToFooter.href = `#${footer.id}`;
    skipToFooter.className = 'skip-link';
    skipToFooter.textContent = 'Vai al footer';
    skipToFooter.style.cssText = linkStyle;
    
    skipToFooter.addEventListener('focus', function() {
      this.style.top = '1rem';
      this.style.left = '1rem';
    });
    
    skipToFooter.addEventListener('blur', function() {
      this.style.top = '-1000px';
      this.style.left = '-1000px';
    });
    
    skipLinksContainer.appendChild(skipToFooter);
  }
  
  // Aggiungi i link alla pagina
  if (skipLinksContainer.children.length > 0) {
    document.body.prepend(skipLinksContainer);
  }
}

/**
 * Migliora l'accessibilità dei form
 */
function enhanceForms() {
  // Aggiungi label mancanti
  document.querySelectorAll('input, select, textarea').forEach(field => {
    // Salta i campi nascosti e i campi con label
    if (field.type === 'hidden' || field.type === 'submit' || field.type === 'button') {
      return;
    }
    
    // Cerca se il campo ha già una label
    const id = field.id;
    let hasLabel = false;
    
    if (id) {
      hasLabel = document.querySelector(`label[for="${id}"]`) !== null;
    }
    
    // Cerca una label come parent
    const parentLabel = field.closest('label');
    hasLabel = hasLabel || parentLabel !== null;
    
    // Se non ha label, aggiungila
    if (!hasLabel) {
      // Crea un id se non esiste
      if (!id) {
        const newId = 'field-' + Math.random().toString(36).substr(2, 9);
        field.id = newId;
      }
      
      // Prova a determinare la label dal placeholder o dal name
      let labelText = '';
      
      if (field.hasAttribute('placeholder')) {
        labelText = field.getAttribute('placeholder');
      } else if (field.hasAttribute('name')) {
        labelText = field.getAttribute('name')
          .replace(/[-_]/g, ' ')
          .replace(/([A-Z])/g, ' $1')
          .replace(/^\w/, c => c.toUpperCase());
      } else {
        // Fallback generico
        labelText = field.type.charAt(0).toUpperCase() + field.type.slice(1);
      }
      
      // Crea e inserisci la label prima del campo
      const label = document.createElement('label');
      label.setAttribute('for', field.id);
      label.textContent = labelText;
      
      field.parentNode.insertBefore(label, field);
      
      // Per mantenere il layout, nascondi visivamente la label ma mantienila accessibile
      label.style.cssText = `
        position: absolute;
        height: 1px;
        width: 1px;
        overflow: hidden;
        clip: rect(1px 1px 1px 1px);
        clip: rect(1px, 1px, 1px, 1px);
      `;
      
      // Assicurati che il campo abbia un aria-label
      if (!field.hasAttribute('aria-label')) {
        field.setAttribute('aria-label', labelText);
      }
    }
    
    // Aggiungi attributi per i campi obbligatori
    if (field.hasAttribute('required') && !field.hasAttribute('aria-required')) {
      field.setAttribute('aria-required', 'true');
    }
    
    // Aggiungi messaggi di errore per la validazione
    if (!field.hasAttribute('aria-describedby') && field.hasAttribute('required')) {
      const errorId = field.id + '-error';
      const errorMessage = document.createElement('div');
      errorMessage.id = errorId;
      errorMessage.className = 'form-error-message';
      errorMessage.setAttribute('aria-live', 'polite');
      errorMessage.style.cssText = `
        color: #e53e3e;
        font-size: 0.875rem;
        margin-top: 0.25rem;
        display: none;
      `;
      
      field.setAttribute('aria-describedby', errorId);
      field.parentNode.insertBefore(errorMessage, field.nextSibling);
      
      // Aggiungi gestione dell'evento di validazione
      field.addEventListener('invalid', function() {
        // Mostra il messaggio di errore
        errorMessage.textContent = this.validationMessage;
        errorMessage.style.display = 'block';
      });
      
      field.addEventListener('input', function() {
        // Nascondi il messaggio quando l'utente corregge
        errorMessage.style.display = 'none';
      });
    }
  });
}

/**
 * Configura la modalità alto contrasto
 */
function setupHighContrastMode() {
  // Crea pulsante per la modalità alto contrasto
  const contrastButton = document.createElement('button');
  contrastButton.type = 'button';
  contrastButton.id = 'high-contrast-toggle';
  contrastButton.setAttribute('aria-pressed', 'false');
  contrastButton.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    z-index: 99;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background-color: #2d3748;
    color: white;
    border: 2px solid white;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 2px 5px rgba(0,0,0,0.2);
  `;
  
  // Aggiungi icona al pulsante
  contrastButton.innerHTML = '<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a10 10 0 0 1 0 20 10 10 0 0 1 0-20z"></path><path d="M12 2v20"></path></svg>';
  contrastButton.setAttribute('aria-label', 'Attiva modalità alto contrasto');
  
  // Crea stile per la modalità alto contrasto
  const contrastStyle = document.createElement('style');
  contrastStyle.id = 'high-contrast-styles';
  contrastStyle.textContent = `
    body.high-contrast {
      background-color: black !important;
      color: white !important;
    }
    
    body.high-contrast a {
      color: yellow !important;
      text-decoration: underline !important;
    }
    
    body.high-contrast button, 
    body.high-contrast .btn, 
    body.high-contrast input[type="button"], 
    body.high-contrast input[type="submit"] {
      background-color: black !important;
      color: white !important;
      border: 2px solid white !important;
      text-decoration: underline !important;
    }
    
    body.high-contrast img {
      filter: grayscale(100%) contrast(120%) !important;
    }
    
    body.high-contrast header, 
    body.high-contrast footer, 
    body.high-contrast nav, 
    body.high-contrast section, 
    body.high-contrast article, 
    body.high-contrast aside {
      background-color: black !important;
      color: white !important;
      border: 1px solid white !important;
    }
    
    body.high-contrast input, 
    body.high-contrast textarea, 
    body.high-contrast select {
      background-color: black !important;
      color: white !important;
      border: 1px solid white !important;
    }
    
    body.high-contrast *:focus {
      outline: 2px solid yellow !important;
      outline-offset: 2px !important;
    }
  `;
  
  // Gestisci il click sul pulsante
  contrastButton.addEventListener('click', function() {
    const isEnabled = document.body.classList.toggle('high-contrast');
    this.setAttribute('aria-pressed', isEnabled.toString());
    
    if (isEnabled) {
      this.setAttribute('aria-label', 'Disattiva modalità alto contrasto');
      localStorage.setItem('high-contrast-mode', 'enabled');
    } else {
      this.setAttribute('aria-label', 'Attiva modalità alto contrasto');
      localStorage.setItem('high-contrast-mode', 'disabled');
    }
  });
  
  // Ripristina lo stato precedente
  if (localStorage.getItem('high-contrast-mode') === 'enabled') {
    document.body.classList.add('high-contrast');
    contrastButton.setAttribute('aria-pressed', 'true');
    contrastButton.setAttribute('aria-label', 'Disattiva modalità alto contrasto');
  }
  
  // Aggiungi elementi alla pagina
  document.head.appendChild(contrastStyle);
  document.body.appendChild(contrastButton);
}

/**
 * Configura la dimensione del testo dinamica
 */
function setupDynamicTextSize() {
  // Crea controlli per la dimensione del testo
  const textSizeControls = document.createElement('div');
  textSizeControls.id = 'text-size-controls';
  textSizeControls.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 70px;
    z-index: 99;
    display: flex;
    gap: 5px;
  `;
  
  // Pulsante per aumentare il testo
  const increaseTextButton = document.createElement('button');
  increaseTextButton.type = 'button';
  increaseTextButton.id = 'increase-text';
  increaseTextButton.innerHTML = 'A+';
  increaseTextButton.setAttribute('aria-label', 'Aumenta dimensione testo');
  increaseTextButton.style.cssText = `
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background-color: #2d3748;
    color: white;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    box-shadow: 0 2px 5px rgba(0,0,0,0.2);
  `;
  
  // Pulsante per diminuire il testo
  const decreaseTextButton = document.createElement('button');
  decreaseTextButton.type = 'button';
  decreaseTextButton.id = 'decrease-text';
  decreaseTextButton.innerHTML = 'A-';
  decreaseTextButton.setAttribute('aria-label', 'Diminuisci dimensione testo');
  decreaseTextButton.style.cssText = `
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background-color: #2d3748;
    color: white;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: bold;
    box-shadow: 0 2px 5px rgba(0,0,0,0.2);
  `;
  
  // Stile per la dimensione del testo
  const textSizeStyle = document.createElement('style');
  textSizeStyle.id = 'text-size-styles';
  
  // Funzione per cambiare la dimensione del testo
  let currentTextSize = parseInt(localStorage.getItem('text-size') || '100');
  
  function updateTextSize(size) {
    // Limita la dimensione tra 80% e 200%
    if (size < 80) size = 80;
    if (size > 200) size = 200;
    
    currentTextSize = size;
    localStorage.setItem('text-size', size.toString());
    
    textSizeStyle.textContent = `
      body, p, div, span, a, button, input, select, textarea, label, li {
        font-size: ${size}% !important;
      }
    `;
    
    // Annuncio per screen reader
    const announcement = document.createElement('div');
    announcement.setAttribute('role', 'status');
    announcement.setAttribute('aria-live', 'polite');
    announcement.style.cssText = `
      position: absolute;
      height: 1px;
      width: 1px;
      overflow: hidden;
      clip: rect(1px 1px 1px 1px);
      clip: rect(1px, 1px, 1px, 1px);
    `;
    announcement.textContent = `Dimensione testo impostata a ${size}%`;
    
    document.body.appendChild(announcement);
    setTimeout(() => announcement.remove(), 1000);
  }
  
  // Gestisci eventi dei pulsanti
  increaseTextButton.addEventListener('click', function() {
    updateTextSize(currentTextSize + 10);
  });
  
  decreaseTextButton.addEventListener('click', function() {
    updateTextSize(currentTextSize - 10);
  });
  
  // Ripristina dimensione precedente
  if (localStorage.getItem('text-size')) {
    updateTextSize(parseInt(localStorage.getItem('text-size')));
  }
  
  // Aggiungi elementi alla pagina
  textSizeControls.appendChild(decreaseTextButton);
  textSizeControls.appendChild(increaseTextButton);
  document.head.appendChild(textSizeStyle);
  document.body.appendChild(textSizeControls);
}

/**
 * Installa gestori di eventi per accessibilità
 */
function installA11yEventHandlers() {
  // Gestisci tasti di scelta rapida per accessibilità
  document.addEventListener('keydown', function(e) {
    // Alt+1: Vai al contenuto principale
    if (e.altKey && e.key === '1') {
      e.preventDefault();
      const mainContent = document.querySelector('main, [role="main"], #content, #main-content');
      if (mainContent) {
        mainContent.tabIndex = -1;
        mainContent.focus();
        setTimeout(() => {
          mainContent.removeAttribute('tabindex');
        }, 100);
      }
    }
    
    // Alt+2: Vai alla navigazione
    if (e.altKey && e.key === '2') {
      e.preventDefault();
      const navigation = document.querySelector('nav, [role="navigation"]');
      if (navigation) {
        navigation.tabIndex = -1;
        navigation.focus();
        setTimeout(() => {
          navigation.removeAttribute('tabindex');
        }, 100);
      }
    }
    
    // Alt+0: Apri menu accessibilità
    if (e.altKey && e.key === '0') {
      e.preventDefault();
      
      // Toggle visibilità controlli accessibilità
      const contrastButton = document.getElementById('high-contrast-toggle');
      const textControls = document.getElementById('text-size-controls');
      
      if (contrastButton) {
        contrastButton.style.display = contrastButton.style.display === 'none' ? 'flex' : 'none';
      }
      
      if (textControls) {
        textControls.style.display = textControls.style.display === 'none' ? 'flex' : 'none';
      }
    }
  });
  
  // Notifica screen reader quando cambia il contenuto della pagina
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'childList' && 
          mutation.addedNodes.length > 0 && 
          !mutation.target.hasAttribute('aria-live')) {
        
        // Verifica se è una modifica significativa
        let isSignificant = false;
        
        for (let i = 0; i < mutation.addedNodes.length; i++) {
          const node = mutation.addedNodes[i];
          
          if (node.nodeType === Node.ELEMENT_NODE) {
            // Considera significative aggiunte di elementi con contenuto
            if (node.textContent && node.textContent.trim() !== '' && 
                !node.classList.contains('m4bot-a11y-highlight') && 
                node.id !== 'm4bot-a11y-results' &&
                !node.classList.contains('skip-link')) {
              
              isSignificant = true;
              break;
            }
          }
        }
        
        if (isSignificant) {
          // Crea una regione live nascosta per notificare lo screen reader
          const liveRegion = document.createElement('div');
          liveRegion.setAttribute('role', 'status');
          liveRegion.setAttribute('aria-live', 'polite');
          liveRegion.style.cssText = `
            position: absolute;
            height: 1px;
            width: 1px;
            overflow: hidden;
            clip: rect(1px 1px 1px 1px);
            clip: rect(1px, 1px, 1px, 1px);
          `;
          liveRegion.textContent = 'Contenuto della pagina aggiornato';
          
          document.body.appendChild(liveRegion);
          setTimeout(() => liveRegion.remove(), 1000);
        }
      }
    });
  });
  
  // Osserva cambiamenti nel body
  observer.observe(document.body, {
    childList: true,
    subtree: true
  });
} 