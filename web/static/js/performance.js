/**
 * M4Bot - Ottimizzazioni Performance
 * Version: 1.0.0
 * Script per migliorare le prestazioni dell'interfaccia utente M4Bot
 */

document.addEventListener('DOMContentLoaded', function() {
  // Inizializzazione delle ottimizzazioni
  initResourceHints();
  initImageOptimizations();
  initScriptOptimizations();
  initCriticalCssOptimization();
  monitorPerformance();
});

/**
 * Inizializza suggerimenti risorse per precaricamento
 */
function initResourceHints() {
  // Preconnect per domini esterni comuni
  const preconnectDomains = [
    'https://fonts.googleapis.com',
    'https://fonts.gstatic.com',
    'https://cdn.jsdelivr.net',
    'https://api.m4bot.com'
  ];
  
  preconnectDomains.forEach(domain => {
    if (!document.querySelector(`link[rel="preconnect"][href="${domain}"]`)) {
      const link = document.createElement('link');
      link.rel = 'preconnect';
      link.href = domain;
      link.crossOrigin = 'anonymous';
      document.head.appendChild(link);
    }
  });
  
  // Prefetch pagine comuni per navigazione veloce
  if (!navigator.connection || navigator.connection.saveData !== true) {
    const prefetchPages = [
      '/dashboard',
      '/profile',
      '/settings',
      '/analytics'
    ];
    
    prefetchPages.forEach(page => {
      if (!document.querySelector(`link[rel="prefetch"][href="${page}"]`)) {
        const link = document.createElement('link');
        link.rel = 'prefetch';
        link.href = page;
        document.head.appendChild(link);
      }
    });
  }
}

/**
 * Inizializza ottimizzazioni per immagini
 */
function initImageOptimizations() {
  // Lazy loading nativo per immagini fuori viewport
  document.querySelectorAll('img:not([loading])').forEach(img => {
    if (!img.hasAttribute('loading') && !img.classList.contains('critical')) {
      img.setAttribute('loading', 'lazy');
    }
  });
  
  // Assicura che le immagini abbiano dimensioni specificate
  document.querySelectorAll('img:not([width]):not([height])').forEach(img => {
    if (img.naturalWidth && img.naturalHeight) {
      img.setAttribute('width', img.naturalWidth);
      img.setAttribute('height', img.naturalHeight);
    }
  });
  
  // Converte GIF in video dove possibile per migliorare prestazioni
  document.querySelectorAll('img[src$=".gif"]').forEach(gif => {
    // Controlla se esiste una versione MP4 della GIF
    const mp4Path = gif.src.replace('.gif', '.mp4');
    
    // Verifica esistenza del file MP4 (senza caricare il file)
    const xhr = new XMLHttpRequest();
    xhr.open('HEAD', mp4Path, true);
    xhr.onreadystatechange = function() {
      if (xhr.readyState === 4) {
        if (xhr.status === 200) {
          // Crea elemento video
          const video = document.createElement('video');
          video.autoplay = true;
          video.loop = true;
          video.muted = true;
          video.playsInline = true;
          
          // Mantieni attributi di stile e classi
          video.className = gif.className;
          video.style.cssText = gif.style.cssText;
          video.width = gif.width || gif.clientWidth;
          video.height = gif.height || gif.clientHeight;
          
          // Crea source element
          const source = document.createElement('source');
          source.src = mp4Path;
          source.type = 'video/mp4';
          
          // Assembla e sostituisci
          video.appendChild(source);
          gif.parentNode.replaceChild(video, gif);
        }
      }
    };
    xhr.send();
  });
}

/**
 * Ottimizzazioni per script
 */
function initScriptOptimizations() {
  // Raccolta garbage collector per evitare memory leak
  setInterval(() => {
    // Rimuovi event listeners da elementi rimossi
    purgeEventListeners();
    
    // Suggerisci raccolta GC al browser
    if (window.gc) {
      window.gc();
    }
  }, 120000); // Ogni 2 minuti
}

/**
 * Ottimizzazione CSS critico
 */
function initCriticalCssOptimization() {
  // Carica CSS non critici in modo asincrono
  document.querySelectorAll('link[rel="stylesheet"][data-critical="false"]').forEach(link => {
    link.setAttribute('media', 'print');
    link.setAttribute('onload', "this.media='all'");
  });
}

/**
 * Monitoraggio metriche prestazioni
 */
function monitorPerformance() {
  // Metriche web vitals
  if ('PerformanceObserver' in window) {
    try {
      // First Input Delay (FID)
      const fidObserver = new PerformanceObserver((entryList) => {
        for (const entry of entryList.getEntries()) {
          const delay = entry.processingStart - entry.startTime;
          console.log('FID:', delay);
          reportPerformanceMetric('fid', delay);
        }
      });
      
      fidObserver.observe({ type: 'first-input', buffered: true });
      
      // Largest Contentful Paint (LCP)
      const lcpObserver = new PerformanceObserver((entryList) => {
        const entries = entryList.getEntries();
        const lastEntry = entries[entries.length - 1];
        console.log('LCP:', lastEntry.startTime);
        reportPerformanceMetric('lcp', lastEntry.startTime);
      });
      
      lcpObserver.observe({ type: 'largest-contentful-paint', buffered: true });
      
      // Cumulative Layout Shift (CLS)
      let clsValue = 0;
      let clsEntries = [];
      
      const clsObserver = new PerformanceObserver((entryList) => {
        for (const entry of entryList.getEntries()) {
          if (!entry.hadRecentInput) {
            clsValue += entry.value;
            clsEntries.push(entry);
          }
        }
        console.log('CLS:', clsValue);
        reportPerformanceMetric('cls', clsValue);
      });
      
      clsObserver.observe({ type: 'layout-shift', buffered: true });
      
    } catch (e) {
      console.error('Error monitoring performance metrics:', e);
    }
  }
  
  // Monitora tempo di caricamento pagina
  window.addEventListener('load', () => {
    setTimeout(() => {
      const navigationTiming = performance.getEntriesByType('navigation')[0];
      const pageLoadTime = navigationTiming.loadEventEnd - navigationTiming.startTime;
      console.log('Page Load Time:', pageLoadTime);
      reportPerformanceMetric('pageLoadTime', pageLoadTime);
    }, 0);
  });
}

/**
 * Invia metriche prestazioni al server
 */
function reportPerformanceMetric(metricName, value) {
  if (navigator.sendBeacon) {
    const data = {
      metricName: metricName,
      value: value,
      url: window.location.href,
      timestamp: Date.now()
    };
    
    navigator.sendBeacon('/api/performance-metrics', JSON.stringify(data));
  }
}

/**
 * Rimuovi listener da elementi rimossi per evitare memory leak
 */
function purgeEventListeners() {
  // Cerca listener orfani (per sistemi di gestione eventi personalizzati)
  if (window.eventRegistry) {
    for (const [elementId, listeners] of Object.entries(window.eventRegistry)) {
      if (!document.getElementById(elementId)) {
        delete window.eventRegistry[elementId];
      }
    }
  }
}

/**
 * Debounce per eventi frequenti
 */
function debounce(func, wait) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

/**
 * Throttle per eventi ad alta frequenza
 */
function throttle(func, limit) {
  let inThrottle;
  return function(...args) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

// Applica throttle a eventi ad alta frequenza
window.addEventListener('resize', throttle(() => {
  // Aggiorna UI responsive
  document.dispatchEvent(new CustomEvent('optimizedResize'));
}, 100));

window.addEventListener('scroll', throttle(() => {
  // Gestione scroll ottimizzata
  document.dispatchEvent(new CustomEvent('optimizedScroll'));
}, 50)); 