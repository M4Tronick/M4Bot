/**
 * M4Bot - Test di Accessibilità
 * Version: 1.0.0
 * Script per testare e migliorare l'accessibilità dell'interfaccia M4Bot
 */

// Flag per attivare i test solo in ambiente di sviluppo
const enableAccessibilityTesting = window.location.hostname === 'localhost' || 
                                   window.location.hostname === '127.0.0.1' ||
                                   window.location.search.includes('enable_a11y_test=true');

// Carica axe-core solo in ambiente di sviluppo
if (enableAccessibilityTesting) {
  loadAxeCore();
}

/**
 * Carica la libreria axe-core in modo asincrono
 */
function loadAxeCore() {
  const script = document.createElement('script');
  script.src = 'https://cdn.jsdelivr.net/npm/axe-core@latest/axe.min.js';
  script.async = true;
  script.onload = function() {
    // Inizializza i test di accessibilità quando la libreria è caricata
    initializeAccessibilityTests();
  };
  document.head.appendChild(script);
}

/**
 * Inizializza i test di accessibilità
 */
function initializeAccessibilityTests() {
  // Verifica che axe sia caricato
  if (typeof axe === 'undefined') {
    console.error('axe-core non è stato caricato correttamente.');
    return;
  }

  // Configura axe
  axe.configure({
    reporter: 'v2',
    rules: [
      // Abilita tutte le regole per WCAG 2.1 AA
      { id: 'aria-roles', enabled: true },
      { id: 'color-contrast', enabled: true },
      { id: 'keyboard-accessibility', enabled: true }
    ]
  });

  // Esegui test dopo il caricamento completo della pagina
  window.addEventListener('load', function() {
    // Attendi un po' per assicurarsi che tutti gli script asincroni siano caricati
    setTimeout(runAccessibilityTests, 1000);
  });

  // Aggiungi pulsante per eseguire test on-demand
  createAccessibilityTestButton();
}

/**
 * Esegue i test di accessibilità
 */
function runAccessibilityTests() {
  if (typeof axe === 'undefined') return;

  axe.run(document, {
    rules: {
      // Esclude alcune regole che potrebbero generare falsi positivi
      'region': { enabled: false }
    }
  }).then(results => {
    displayAccessibilityResults(results);
  }).catch(err => {
    console.error('Errore durante l\'esecuzione dei test di accessibilità:', err);
  });
}

/**
 * Mostra i risultati dei test di accessibilità
 */
function displayAccessibilityResults(results) {
  // Conteggio totale dei problemi
  const violations = results.violations;
  const totalIssues = violations.reduce((total, violation) => total + violation.nodes.length, 0);
  
  // Se non ci sono problemi, mostra solo un messaggio nella console
  if (totalIssues === 0) {
    console.info('🎉 Nessun problema di accessibilità rilevato!');
    return;
  }

  // Crea un pannello nella UI per mostrare i problemi
  const resultsPanel = document.createElement('div');
  resultsPanel.id = 'm4bot-a11y-results';
  resultsPanel.style.cssText = `
    position: fixed;
    bottom: 20px;
    right: 20px;
    width: 350px;
    max-height: 400px;
    overflow-y: auto;
    background: white;
    border: 1px solid #ddd;
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    padding: 15px;
    font-family: sans-serif;
    font-size: 14px;
    z-index: 9999;
    color: #333;
  `;

  // Intestazione del pannello
  const header = document.createElement('div');
  header.style.cssText = `
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
    border-bottom: 1px solid #eee;
    padding-bottom: 10px;
  `;
  
  const title = document.createElement('h3');
  title.textContent = `Problemi di Accessibilità (${totalIssues})`;
  title.style.margin = '0';
  title.style.fontSize = '16px';
  
  const closeButton = document.createElement('button');
  closeButton.textContent = '×';
  closeButton.style.cssText = `
    background: none;
    border: none;
    font-size: 20px;
    cursor: pointer;
    padding: 0 5px;
  `;
  closeButton.onclick = function() {
    resultsPanel.remove();
  };
  
  header.appendChild(title);
  header.appendChild(closeButton);
  resultsPanel.appendChild(header);

  // Lista dei problemi raggruppati per tipo
  violations.forEach(violation => {
    const issueSection = document.createElement('div');
    issueSection.style.cssText = `
      margin-bottom: 15px;
      padding-bottom: 15px;
      border-bottom: 1px solid #eee;
    `;
    
    // Intestazione del problema
    const issueHeader = document.createElement('div');
    
    // Assegna colore in base all'impatto
    let impactColor = '#999'; // default
    if (violation.impact === 'critical') impactColor = '#d63031';
    else if (violation.impact === 'serious') impactColor = '#e17055';
    else if (violation.impact === 'moderate') impactColor = '#fdcb6e';
    else if (violation.impact === 'minor') impactColor = '#74b9ff';
    
    const impactBadge = document.createElement('span');
    impactBadge.textContent = violation.impact.toUpperCase();
    impactBadge.style.cssText = `
      display: inline-block;
      padding: 2px 6px;
      border-radius: 3px;
      background-color: ${impactColor};
      color: white;
      font-size: 12px;
      margin-right: 8px;
    `;
    
    const issueTitle = document.createElement('h4');
    issueTitle.textContent = violation.description;
    issueTitle.style.cssText = `
      margin: 5px 0;
      font-size: 15px;
      display: inline;
    `;
    
    issueHeader.appendChild(impactBadge);
    issueHeader.appendChild(issueTitle);
    
    // Sottotitolo con il tipo di problema WCAG
    const issueSubtitle = document.createElement('p');
    issueSubtitle.textContent = `${violation.help} (${violation.nodes.length} istanze)`;
    issueSubtitle.style.cssText = `
      margin: 5px 0 10px;
      font-size: 13px;
      color: #666;
    `;
    
    // Lista degli elementi con problemi
    const instancesList = document.createElement('ul');
    instancesList.style.cssText = `
      margin: 5px 0;
      padding-left: 20px;
      font-size: 13px;
    `;
    
    // Limita a 3 elementi per non sovraccaricare la UI
    const displayNodes = violation.nodes.slice(0, 3);
    
    displayNodes.forEach(node => {
      const instance = document.createElement('li');
      
      // Descrizione dell'elemento
      let elementDesc = node.html.replace(/</g, '&lt;').replace(/>/g, '&gt;');
      if (elementDesc.length > 50) {
        elementDesc = elementDesc.substring(0, 50) + '...';
      }
      
      instance.innerHTML = `
        <code style="font-size: 12px; background: #f8f8f8; padding: 2px 4px; border-radius: 3px;">${elementDesc}</code>
      `;
      
      // Pulsante "Evidenzia" per mostrare l'elemento sulla pagina
      const highlightButton = document.createElement('button');
      highlightButton.textContent = 'Evidenzia';
      highlightButton.style.cssText = `
        background: #ddd;
        border: none;
        border-radius: 3px;
        padding: 3px 6px;
        margin-left: 8px;
        font-size: 11px;
        cursor: pointer;
      `;
      highlightButton.onclick = function() {
        highlightElement(node.target);
      };
      
      instance.appendChild(highlightButton);
      instancesList.appendChild(instance);
    });
    
    // Se ci sono più di 3 elementi, mostra un messaggio
    if (violation.nodes.length > 3) {
      const moreItems = document.createElement('li');
      moreItems.textContent = `E altri ${violation.nodes.length - 3} elementi...`;
      moreItems.style.fontStyle = 'italic';
      moreItems.style.color = '#666';
      instancesList.appendChild(moreItems);
    }
    
    // Link alla documentazione
    const helpLink = document.createElement('a');
    helpLink.href = violation.helpUrl;
    helpLink.textContent = 'Come risolvere';
    helpLink.target = '_blank';
    helpLink.style.cssText = `
      display: inline-block;
      margin-top: 5px;
      font-size: 12px;
      color: #0984e3;
      text-decoration: none;
    `;
    
    // Assembla la sezione del problema
    issueSection.appendChild(issueHeader);
    issueSection.appendChild(issueSubtitle);
    issueSection.appendChild(instancesList);
    issueSection.appendChild(helpLink);
    
    resultsPanel.appendChild(issueSection);
  });

  // Aggiungi il pannello alla pagina
  document.body.appendChild(resultsPanel);
}

/**
 * Evidenzia un elemento sulla pagina
 */
function highlightElement(selector) {
  try {
    // Trova l'elemento nella pagina
    const elements = document.querySelectorAll(selector);
    
    if (elements.length === 0) {
      console.warn('Elemento non trovato:', selector);
      return;
    }
    
    // Rimuovi evidenziazioni precedenti
    const prevHighlights = document.querySelectorAll('.m4bot-a11y-highlight');
    prevHighlights.forEach(el => {
      el.remove();
    });
    
    // Evidenzia ogni elemento trovato
    elements.forEach(element => {
      const rect = element.getBoundingClientRect();
      
      // Crea un overlay sopra l'elemento
      const highlight = document.createElement('div');
      highlight.className = 'm4bot-a11y-highlight';
      highlight.style.cssText = `
        position: absolute;
        top: ${window.scrollY + rect.top - 5}px;
        left: ${window.scrollX + rect.left - 5}px;
        width: ${rect.width + 10}px;
        height: ${rect.height + 10}px;
        background: rgba(255, 0, 0, 0.2);
        border: 2px solid red;
        border-radius: 3px;
        pointer-events: none;
        z-index: 9998;
        animation: m4bot-a11y-pulse 1.5s infinite;
      `;
      
      // Aggiungi stile per l'animazione
      if (!document.getElementById('m4bot-a11y-styles')) {
        const style = document.createElement('style');
        style.id = 'm4bot-a11y-styles';
        style.textContent = `
          @keyframes m4bot-a11y-pulse {
            0% { box-shadow: 0 0 0 0 rgba(255, 0, 0, 0.4); }
            70% { box-shadow: 0 0 0 10px rgba(255, 0, 0, 0); }
            100% { box-shadow: 0 0 0 0 rgba(255, 0, 0, 0); }
          }
        `;
        document.head.appendChild(style);
      }
      
      // Aggiungi l'elemento al body
      document.body.appendChild(highlight);
      
      // Scroll all'elemento se non è visibile
      element.scrollIntoView({
        behavior: 'smooth',
        block: 'center'
      });
      
      // Rimuovi l'evidenziazione dopo 3 secondi
      setTimeout(() => {
        highlight.remove();
      }, 3000);
    });
  } catch (e) {
    console.error('Errore durante l\'evidenziazione dell\'elemento:', e);
  }
}

/**
 * Crea un pulsante per eseguire i test on-demand
 */
function createAccessibilityTestButton() {
  const button = document.createElement('button');
  button.id = 'm4bot-a11y-test-button';
  button.textContent = 'Test Accessibilità';
  button.style.cssText = `
    position: fixed;
    bottom: 20px;
    left: 20px;
    background: #0984e3;
    color: white;
    border: none;
    border-radius: 5px;
    padding: 8px 12px;
    font-family: sans-serif;
    font-size: 14px;
    cursor: pointer;
    z-index: 9997;
    box-shadow: 0 2px 5px rgba(0,0,0,0.2);
  `;
  
  button.onclick = function() {
    // Rimuovi risultati precedenti
    const prevResults = document.getElementById('m4bot-a11y-results');
    if (prevResults) {
      prevResults.remove();
    }
    
    // Esegui nuovi test
    runAccessibilityTests();
  };
  
  // Aggiungi il pulsante alla pagina solo in ambiente di sviluppo
  if (enableAccessibilityTesting) {
    document.body.appendChild(button);
  }
} 