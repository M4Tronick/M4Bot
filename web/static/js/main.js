/**
 * M4Bot - Main JavaScript
 * Funzionalità avanzate e ottimizzazioni per l'interfaccia utente
 * Versione: 3.0
 */

document.addEventListener('DOMContentLoaded', function() {
  // Inizializzazione dei componenti principali
  initLazyLoading();
  initMicroAnimations();
  initPerformanceOptimizations();
  initAdvancedAccessibility();
  initMobileFeatures();
  initNotifications();
  initCustomDashboard();
  initDataVisualization();
  initOfflineMode();
  initPrivacyFeatures();
  
  // Monitoraggio connessione
  setupConnectionMonitoring();
});

/**
 * Lazy Loading per immagini e componenti pesanti
 */
function initLazyLoading() {
  // Implementazione IntersectionObserver per lazy loading nativo
  if ('IntersectionObserver' in window) {
    const lazyImages = document.querySelectorAll('img.lazy-load, iframe.lazy-load, video.lazy-load');
    const imageObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const lazyElement = entry.target;
          
          if (lazyElement.tagName.toLowerCase() === 'img') {
            // Per immagini
            if (lazyElement.dataset.src) {
              lazyElement.src = lazyElement.dataset.src;
            }
            if (lazyElement.dataset.srcset) {
              lazyElement.srcset = lazyElement.dataset.srcset;
            }
          } else if (lazyElement.tagName.toLowerCase() === 'iframe' || lazyElement.tagName.toLowerCase() === 'video') {
            // Per iframe e video
            if (lazyElement.dataset.src) {
              lazyElement.src = lazyElement.dataset.src;
            }
          }
          
          lazyElement.classList.remove('lazy-load');
          lazyElement.classList.add('loaded');
          imageObserver.unobserve(lazyElement);
        }
      });
    }, {
      rootMargin: '200px 0px', // Carica quando si avvicina a 200px dalla viewport
      threshold: 0.01
    });
    
    lazyImages.forEach(image => {
      imageObserver.observe(image);
    });
    
    // Lazy loading per componenti JS pesanti
    const lazyComponents = document.querySelectorAll('[data-component-lazy]');
    const componentObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const component = entry.target;
          const componentType = component.dataset.componentLazy;
          
          // Inizializza il componente in base al tipo
          switch(componentType) {
            case 'chart':
              initChart(component);
              break;
            case 'map':
              initMap(component);
              break;
            case 'video-player':
              initVideoPlayer(component);
              break;
            case 'rich-editor':
              initRichEditor(component);
              break;
          }
          
          componentObserver.unobserve(component);
        }
      });
    }, {
      rootMargin: '100px 0px',
      threshold: 0.01
    });
    
    lazyComponents.forEach(component => {
      componentObserver.observe(component);
    });
  } else {
    // Fallback per browser che non supportano IntersectionObserver
    const lazyImages = document.querySelectorAll('img.lazy-load');
    lazyImages.forEach(img => {
      if (img.dataset.src) {
        img.src = img.dataset.src;
      }
      img.classList.remove('lazy-load');
    });
  }
}

/**
 * Micro-animazioni per feedback utente
 */
function initMicroAnimations() {
  // Effetto click su pulsanti
  const buttons = document.querySelectorAll('.btn, button:not(.btn-plain)');
  buttons.forEach(button => {
    if (!button.classList.contains('no-animation')) {
      button.addEventListener('click', function(e) {
        // Aggiungi classe per animazione solo se non è disabilitata la motion
        if (!document.documentElement.classList.contains('reduced-motion')) {
          this.classList.add('btn-clicked');
          
          // Rimuovi classe dopo animazione
          setTimeout(() => {
            this.classList.remove('btn-clicked');
          }, 300);
        }
      });
    }
  });
  
  // Effetto hover avanzato su card e componenti interattivi
  const interactiveElements = document.querySelectorAll('.interactive-element');
  interactiveElements.forEach(element => {
    element.addEventListener('mousemove', function(e) {
      if (!document.documentElement.classList.contains('reduced-motion')) {
        const rect = this.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        
        // Calcola percentuale della posizione del mouse all'interno dell'elemento
        const posX = (x / rect.width) * 100;
        const posY = (y / rect.height) * 100;
        
        // Applica effetto spostamento 3D limitato
        this.style.transform = `perspective(1000px) rotateX(${(posY - 50) * 0.02}deg) rotateY(${(posX - 50) * -0.02}deg)`;
        
        // Effetto luce
        this.style.background = `radial-gradient(circle at ${posX}% ${posY}%, rgba(255,255,255,0.1) 0%, rgba(255,255,255,0) 60%)`;
      }
    });
    
    element.addEventListener('mouseleave', function() {
      // Reset trasformazione e background
      this.style.transform = 'perspective(1000px) rotateX(0) rotateY(0)';
      this.style.background = '';
                });
            });

  // Effetto animazione per badge "nuovo"
  const newBadges = document.querySelectorAll('.badge.pulse');
  newBadges.forEach(badge => {
    // Già gestito dal CSS con la classe .pulse
            });
        }

        /**
 * Ottimizzazioni performance
 */
function initPerformanceOptimizations() {
  // Preconnect per risorse esterne
  const preconnectDomains = [
    'https://fonts.googleapis.com',
    'https://fonts.gstatic.com',
    'https://cdn.jsdelivr.net',
    'https://cdnjs.cloudflare.com'
  ];
  
  preconnectDomains.forEach(domain => {
    const link = document.createElement('link');
    link.rel = 'preconnect';
    link.href = domain;
    link.crossOrigin = 'anonymous';
    document.head.appendChild(link);
  });
  
  // Prefetch pagine comuni
  const commonPages = [
    '/dashboard',
    '/profile',
    '/settings'
  ];
  
  if (!navigator.connection || navigator.connection.saveData !== true) {
    commonPages.forEach(page => {
      const link = document.createElement('link');
      link.rel = 'prefetch';
      link.href = page;
      document.head.appendChild(link);
    });
  }
  
  // Debounce per eventi che causano reflow
  function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
      const later = () => {
        clearTimeout(timeout);
        func(...args);
      };
      clearTimeout(timeout);
      timeout = setTimeout(later, wait);
    };
  }
  
  // Applicazione del debounce all'evento resize
  const resizeHandler = debounce(() => {
    // Esegui operazioni che richiedono reflow
    document.dispatchEvent(new CustomEvent('optimizedResize'));
  }, 100);
  
  window.addEventListener('resize', resizeHandler);
  
  // Rimuovi classi di animazione dopo che sono state completate
  document.addEventListener('animationend', function(e) {
    if (e.target.classList.contains('animate-once')) {
      e.target.classList.remove('animate-once');
      // Rimuovi anche classi di animazione specifiche
      const animationClasses = ['fade-in', 'slide-in-up', 'slide-in-down', 'slide-in-left', 'slide-in-right', 'zoom-in'];
      animationClasses.forEach(className => {
        if (e.target.classList.contains(className)) {
          e.target.classList.remove(className);
        }
      });
    }
  });
}

/**
 * Funzionalità di accessibilità avanzate
 */
function initAdvancedAccessibility() {
  // Aggiungi supporto per scorciatoie da tastiera
  const keyboardShortcuts = {
    'Alt+1': () => navigateTo('/dashboard'),
    'Alt+2': () => navigateTo('/profile'),
    'Alt+3': () => navigateTo('/settings'),
    'Alt+s': () => document.querySelector('#global-search-input')?.focus(),
    'Alt+t': () => window.themeSystem.toggleTheme(),
    'Alt+h': () => toggleHelpModal(),
    'Alt+a': () => toggleAccessibilityMenu(),
    'Escape': () => closeActiveModal()
  };
  
  document.addEventListener('keydown', function(e) {
    // Non eseguire scorciatoie quando si è in un input o textarea
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
      return;
    }
    
    const key = `${e.altKey ? 'Alt+' : ''}${e.ctrlKey ? 'Ctrl+' : ''}${e.shiftKey ? 'Shift+' : ''}${e.key}`;
    
    if (keyboardShortcuts[key]) {
      e.preventDefault();
      keyboardShortcuts[key]();
    }
  });
  
  // Focus visibile migliorato
  document.addEventListener('keydown', function(e) {
    if (e.key === 'Tab') {
      document.body.classList.add('keyboard-navigation');
    }
  });
  
  document.addEventListener('mousedown', function() {
    document.body.classList.remove('keyboard-navigation');
  });
  
  // Gestione annunci per screen reader
  window.a11yAnnounce = function(message, priority = 'polite') {
    const announceElement = document.getElementById('a11y-announce');
    
    if (!announceElement) {
      const newAnnounceElement = document.createElement('div');
      newAnnounceElement.id = 'a11y-announce';
      newAnnounceElement.setAttribute('aria-live', priority);
      newAnnounceElement.className = 'sr-only';
      document.body.appendChild(newAnnounceElement);
      
      setTimeout(() => {
        newAnnounceElement.textContent = message;
      }, 100);
    } else {
      announceElement.setAttribute('aria-live', priority);
      
      // Pulizia e poi aggiunta del nuovo messaggio
      announceElement.textContent = '';
      setTimeout(() => {
        announceElement.textContent = message;
      }, 100);
    }
  };
  
  // Miglioramento menu dropdown per accessibilità
  const dropdownToggles = document.querySelectorAll('[data-bs-toggle="dropdown"]');
  dropdownToggles.forEach(toggle => {
    toggle.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.click();
      }
    });
  });
}

/**
 * Funzionalità mobile avanzate
 */
function initMobileFeatures() {
  // Rileva se siamo su mobile
  const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
  
  if (isMobile) {
    document.body.classList.add('is-mobile-device');
    
    // Aggiungi supporto per gesti mobile
    const gestureElements = document.querySelectorAll('.supports-gestures');
    
    if ('ontouchstart' in window) {
      gestureElements.forEach(element => {
        let touchStartX = 0;
        let touchStartY = 0;
        let touchEndX = 0;
        let touchEndY = 0;
        
        element.addEventListener('touchstart', function(e) {
          touchStartX = e.changedTouches[0].screenX;
          touchStartY = e.changedTouches[0].screenY;
        }, false);
        
        element.addEventListener('touchend', function(e) {
          touchEndX = e.changedTouches[0].screenX;
          touchEndY = e.changedTouches[0].screenY;
          handleGesture(this, touchStartX, touchStartY, touchEndX, touchEndY);
        }, false);
      });
    }
    
    // Modalità una mano su telefoni grandi
    const oneHandModeButton = document.getElementById('one-hand-mode');
    if (oneHandModeButton) {
      oneHandModeButton.addEventListener('click', function() {
        document.body.classList.toggle('one-hand-mode');
        localStorage.setItem('oneHandMode', document.body.classList.contains('one-hand-mode'));
      });
      
      // Ripristina stato precedente
      if (localStorage.getItem('oneHandMode') === 'true') {
        document.body.classList.add('one-hand-mode');
      }
    }
    
    // Adattamenti UI per schermi più piccoli
    const screenWidth = window.innerWidth;
    if (screenWidth < 768) {
      // Semplifica alcuni componenti UI per schermi molto piccoli
      document.querySelectorAll('.simplify-mobile').forEach(el => {
        el.classList.add('mobile-simplified');
                });
            }
        }
}

/**
 * Gestione notifiche avanzate
 */
function initNotifications() {
  // Sistema di notifiche push
  if ('Notification' in window && 'PushManager' in window) {
    // Variabile per memorizzare sottoscrizione notifiche
    let pushSubscription = null;
    
    // API per controllare le notifiche
    window.notificationSystem = {
      // Richiedi permesso notifiche
      requestPermission: async function() {
        try {
          const permission = await Notification.requestPermission();
          if (permission === 'granted') {
            this.subscribeUserToPush();
            return true;
          }
          return false;
        } catch (error) {
          console.error('Errore nella richiesta permessi notifiche:', error);
          return false;
        }
      },
      
      // Iscrivere utente alle notifiche push
      subscribeUserToPush: async function() {
        try {
          const registration = await navigator.serviceWorker.getRegistration();
          pushSubscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: this.urlBase64ToUint8Array(window.VAPID_PUBLIC_KEY || '')
          });
          
          // Invia la sottoscrizione al server
          await fetch('/api/push-subscription', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify(pushSubscription)
          });
          
          return true;
        } catch (error) {
          console.error('Errore nella sottoscrizione push:', error);
          return false;
        }
      },
      
      // Utility per convertire chiave VAPID
      urlBase64ToUint8Array: function(base64String) {
        const padding = '='.repeat((4 - base64String.length % 4) % 4);
        const base64 = (base64String + padding)
          .replace(/-/g, '+')
          .replace(/_/g, '/');
        
        const rawData = window.atob(base64);
        const outputArray = new Uint8Array(rawData.length);
        
        for (let i = 0; i < rawData.length; ++i) {
          outputArray[i] = rawData.charCodeAt(i);
        }
        return outputArray;
      },
      
      // Mostra notifica locale
      showNotification: function(title, options = {}) {
        if (!('Notification' in window)) return;
        
        if (Notification.permission === 'granted') {
          navigator.serviceWorker.getRegistration().then(registration => {
            registration.showNotification(title, {
              badge: '/static/icons/badge-icon.png',
              icon: '/static/icons/notification-icon.png',
              ...options
            });
                });
            }
        }
    };
    
    // Pulsante per iscriversi alle notifiche
    const notificationButton = document.getElementById('enable-notifications');
    if (notificationButton) {
      notificationButton.addEventListener('click', async function() {
        const result = await window.notificationSystem.requestPermission();
        if (result) {
          this.classList.add('subscribed');
          this.textContent = 'Notifiche attivate';
        }
      });
    }
            }
        }

        /**
 * Dashboard personalizzabile
 */
function initCustomDashboard() {
  // Implementazione del sistema di widget trascinabili
  const customDashboard = document.querySelector('.custom-dashboard');
  if (!customDashboard) return;
  
  // Verifica che la libreria Sortable sia caricata
  if (typeof Sortable !== 'undefined') {
    // Abilita il riordinamento dei widget
    const widgetContainer = customDashboard.querySelector('.widget-container');
    if (widgetContainer) {
      const sortable = Sortable.create(widgetContainer, {
        animation: 150,
        handle: '.widget-header',
        ghostClass: 'widget-ghost',
        chosenClass: 'widget-chosen',
        dragClass: 'widget-drag',
        onEnd: function(evt) {
          // Salva l'ordine dei widget
          const widgetOrder = Array.from(widgetContainer.children).map(widget => {
            return widget.dataset.widgetId;
          });
          
          localStorage.setItem('dashboardWidgetOrder', JSON.stringify(widgetOrder));
          
          // Aggiorna il dashboard sul server
          fetch('/api/dashboard-layout', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({ widgetOrder })
          }).catch(error => {
            console.error('Errore nel salvataggio layout dashboard:', error);
          });
        }
      });
    }
    
    // Aggiungi pulsanti per aggiungere/rimuovere widget
    const addWidgetButton = customDashboard.querySelector('.add-widget-button');
    if (addWidgetButton) {
      addWidgetButton.addEventListener('click', function() {
        const widgetSelector = document.getElementById('widget-selector');
        if (widgetSelector) {
          widgetSelector.classList.add('show');
        }
      });
    }
    
    // Gestisci selezione widget
    const widgetOptions = document.querySelectorAll('.widget-option');
    widgetOptions.forEach(option => {
      option.addEventListener('click', function() {
        const widgetType = this.dataset.widgetType;
        addWidgetToDashboard(widgetType);
        
        // Chiudi selettore
        const widgetSelector = document.getElementById('widget-selector');
        if (widgetSelector) {
          widgetSelector.classList.remove('show');
        }
      });
    });
  }
}

/**
 * Visualizzazione dati avanzata
 */
function initDataVisualization() {
  // Inizializzazione grafici con animazioni
  const chartElements = document.querySelectorAll('[data-chart-type]');
  
  chartElements.forEach(element => {
    // Se il chart è configurato per lazy loading, salta
    if (element.classList.contains('lazy-load')) return;
    
    initChart(element);
  });
  
  // Implementazione tema coordinato per i grafici
  document.addEventListener('themeChanged', function(event) {
    const theme = event.detail.theme;
    updateChartsTheme(theme);
  });
}

/**
 * Inizializza un grafico
 */
function initChart(element) {
  const chartType = element.dataset.chartType;
  const chartData = JSON.parse(element.dataset.chartData || '{}');
  const chartOptions = JSON.parse(element.dataset.chartOptions || '{}');
  const chartId = element.id;
  
  if (!chartId) return;
  
  // Verifica che Chart.js sia caricato
  if (typeof Chart !== 'undefined') {
    // Aggiungi animazioni fluide
    const defaultOptions = {
      animation: {
        duration: 1000,
        easing: 'easeOutQuart'
      },
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        tooltip: {
          animation: {
            duration: 100
          },
          backdropPadding: 6,
          backgroundColor: 'rgba(0, 0, 0, 0.7)',
          titleFont: {
            weight: 'bold'
          }
        },
        legend: {
          labels: {
            usePointStyle: true,
            padding: 15
          }
        }
      }
    };
    
    // Opzioni specifiche per il tema corrente
    const theme = document.documentElement.getAttribute('data-bs-theme') || 'light';
    const themeOptions = getChartThemeOptions(theme);
    
    // Unisci opzioni
    const mergedOptions = deepMerge(defaultOptions, themeOptions, chartOptions);
    
    // Crea il grafico
    const ctx = document.getElementById(chartId).getContext('2d');
    const chart = new Chart(ctx, {
      type: chartType,
      data: chartData,
      options: mergedOptions
    });
    
    // Salva l'istanza del grafico per riferimento futuro
    element.chart = chart;
  }
}

/**
 * Ottieni opzioni di tema per i grafici
 */
function getChartThemeOptions(theme) {
  if (theme === 'dark') {
    return {
      color: 'rgba(255, 255, 255, 0.7)',
      scales: {
        x: {
          grid: {
            color: 'rgba(255, 255, 255, 0.1)'
          },
          ticks: {
            color: 'rgba(255, 255, 255, 0.7)'
          }
        },
        y: {
          grid: {
            color: 'rgba(255, 255, 255, 0.1)'
          },
          ticks: {
            color: 'rgba(255, 255, 255, 0.7)'
          }
        }
      },
      plugins: {
        legend: {
          labels: {
            color: 'rgba(255, 255, 255, 0.9)'
          }
        },
        tooltip: {
          backgroundColor: 'rgba(30, 30, 30, 0.8)',
          titleColor: 'rgba(255, 255, 255, 0.9)',
          bodyColor: 'rgba(255, 255, 255, 0.7)'
        }
      }
    };
  }
  
  return {
    color: 'rgba(0, 0, 0, 0.7)',
    scales: {
      x: {
        grid: {
          color: 'rgba(0, 0, 0, 0.1)'
        },
        ticks: {
          color: 'rgba(0, 0, 0, 0.7)'
        }
      },
      y: {
        grid: {
          color: 'rgba(0, 0, 0, 0.1)'
        },
        ticks: {
          color: 'rgba(0, 0, 0, 0.7)'
        }
      }
    },
    plugins: {
      legend: {
        labels: {
          color: 'rgba(0, 0, 0, 0.8)'
        }
      },
      tooltip: {
        backgroundColor: 'rgba(245, 245, 245, 0.9)',
        titleColor: 'rgba(0, 0, 0, 0.9)',
        bodyColor: 'rgba(0, 0, 0, 0.7)'
      }
    }
            };
        }

        /**
 * Aggiorna il tema di tutti i grafici
 */
function updateChartsTheme(theme) {
  const chartElements = document.querySelectorAll('[data-chart-type]');
  
  chartElements.forEach(element => {
    if (element.chart) {
      const chart = element.chart;
      const themeOptions = getChartThemeOptions(theme);
      
      // Aggiorna opzioni del grafico
      deepMerge(chart.options, themeOptions);
      
      // Aggiorna il grafico
      chart.update();
    }
  });
}

/**
 * Funzionalità offline
 */
function initOfflineMode() {
  // Monitora stato della connessione
  window.addEventListener('online', updateConnectionStatus);
  window.addEventListener('offline', updateConnectionStatus);
  
  // Controlla stato iniziale
  updateConnectionStatus();
  
  // Cache dei dati per modalità offline
  if ('caches' in window) {
    // Registra dati da cachare per uso offline
    const cachableRequests = [
      '/api/user-profile',
      '/api/dashboard-summary',
      '/api/recent-activity'
    ];
    
    // Crea una cache per i dati API
    caches.open('api-data-cache').then(cache => {
      // Cache dei dati API
      cachableRequests.forEach(url => {
        fetch(url)
                .then(response => {
            if (response.ok) {
              // Clona la risposta per poterla usare e cachare
              const responseToCache = response.clone();
              cache.put(url, responseToCache);
            }
          })
          .catch(error => {
            console.error('Errore nel caching dei dati:', error);
          });
      });
    });
  }
}

/**
 * Funzionalità per la privacy
 */
function initPrivacyFeatures() {
  // Implementazione modalità privacy (offuscamento dati sensibili)
  const privacyModeToggle = document.getElementById('privacy-mode');
  if (privacyModeToggle) {
    privacyModeToggle.addEventListener('change', function() {
      document.body.classList.toggle('privacy-mode', this.checked);
      
      // Salva preferenza
      localStorage.setItem('privacyMode', this.checked);
      
      // Annuncia per screen reader
      if (window.a11yAnnounce) {
        window.a11yAnnounce(this.checked ? 'Modalità privacy attivata' : 'Modalità privacy disattivata');
      }
    });
    
    // Ripristina preferenza
    if (localStorage.getItem('privacyMode') === 'true') {
      privacyModeToggle.checked = true;
      document.body.classList.add('privacy-mode');
    }
  }
  
  // Implementazione blocco automatico per inattività
  const inactivityTimeout = 5 * 60 * 1000; // 5 minuti
  let inactivityTimer;
  
  function resetInactivityTimer() {
    clearTimeout(inactivityTimer);
    inactivityTimer = setTimeout(() => {
      // Attiva modalità privacy se non è già attiva
      if (!document.body.classList.contains('privacy-mode')) {
        document.body.classList.add('privacy-mode');
        if (privacyModeToggle) privacyModeToggle.checked = true;
        
        // Mostra notifica
        if (window.toastSystem) {
          window.toastSystem.show('Modalità privacy attivata per inattività', 'info');
        }
      }
    }, inactivityTimeout);
  }
  
  // Eventi per resettare il timer
  ['mousemove', 'mousedown', 'keypress', 'touchstart', 'scroll'].forEach(event => {
    document.addEventListener(event, resetInactivityTimer);
  });
  
  // Inizializza timer
  resetInactivityTimer();
}

/**
 * Monitoraggio della connessione e gestione indicatori
 */
function setupConnectionMonitoring() {
  // Stato connessione
  updateConnectionStatus();
  
  // Ping del server per verificare la connessione effettiva
  setInterval(() => {
    const startTime = performance.now();
    
    fetch('/api/ping', {
      method: 'HEAD',
      cache: 'no-store'
    })
      .then(() => {
        const endTime = performance.now();
        const pingTime = Math.round(endTime - startTime);
        updatePingDisplay(pingTime);
      })
      .catch(() => {
        updatePingDisplay(-1); // -1 indica errore
      });
  }, 30000); // Ogni 30 secondi
}

/**
 * Aggiorna lo stato della connessione nell'UI
 */
function updateConnectionStatus() {
  const isOnline = navigator.onLine;
            const statusIndicator = document.querySelector('.status-indicator');
            const statusText = document.querySelector('.status-text');
            
  if (statusIndicator && statusText) {
    if (isOnline) {
                statusIndicator.classList.remove('disconnected');
                statusIndicator.classList.add('connected');
                statusText.textContent = 'Online';
            } else {
                statusIndicator.classList.remove('connected');
                statusIndicator.classList.add('disconnected');
                statusText.textContent = 'Offline';
      
      // Notifica utente
      if (window.toastSystem) {
        window.toastSystem.show('Sei offline. Alcune funzionalità potrebbero non essere disponibili.', 'warning');
      }
    }
            }
        }

        /**
 * Aggiorna il display del ping
 */
function updatePingDisplay(pingTime) {
  const pingDisplay = document.getElementById('server-ping-value');
  if (pingDisplay) {
    if (pingTime === -1) {
      pingDisplay.textContent = '--';
      pingDisplay.classList.add('text-danger');
    } else {
      pingDisplay.textContent = pingTime;
      pingDisplay.classList.remove('text-danger');
      
      // Aggiungi classi in base al tempo di ping
      pingDisplay.classList.remove('text-success', 'text-warning', 'text-danger');
      
      if (pingTime < 100) {
        pingDisplay.classList.add('text-success');
      } else if (pingTime < 300) {
        pingDisplay.classList.add('text-warning');
      } else {
        pingDisplay.classList.add('text-danger');
      }
                }
            }
        }

        /**
 * Utility per navigare a una URL
 */
function navigateTo(url) {
  window.location.href = url;
}

/**
 * Toggle per il modal di help
 */
function toggleHelpModal() {
  const helpModal = document.getElementById('help-modal');
  if (helpModal) {
    const bsModal = new bootstrap.Modal(helpModal);
    bsModal.toggle();
  }
}

/**
 * Toggle per il menu di accessibilità
 */
function toggleAccessibilityMenu() {
  const accessibilityMenu = document.getElementById('accessibilityMenuButton');
  if (accessibilityMenu) {
    accessibilityMenu.click();
  }
}

/**
 * Chiude il modal attivo
 */
function closeActiveModal() {
  const activeModal = document.querySelector('.modal.show');
  if (activeModal) {
    const bsModal = bootstrap.Modal.getInstance(activeModal);
    if (bsModal) {
      bsModal.hide();
                }
            }
        }

        /**
 * Gestione dei gesti touch su mobile
 */
function handleGesture(element, touchStartX, touchStartY, touchEndX, touchEndY) {
  const gestureType = element.dataset.gestureAction;
  if (!gestureType) return;
  
  const minSwipeDistance = 50;
  const deltaX = touchEndX - touchStartX;
  const deltaY = touchEndY - touchStartY;
  
  // Determina il tipo di swipe (orizzontale o verticale)
  const isHorizontalSwipe = Math.abs(deltaX) > Math.abs(deltaY);
  
  if (isHorizontalSwipe && Math.abs(deltaX) > minSwipeDistance) {
    if (deltaX > 0) {
      // Swipe a destra
      if (gestureType === 'navigate-back') {
        window.history.back();
      } else if (gestureType === 'reveal-actions') {
        element.classList.add('actions-revealed');
      }
            } else {
      // Swipe a sinistra
      if (gestureType === 'navigate-forward') {
        window.history.forward();
      } else if (gestureType === 'dismiss') {
        element.classList.add('dismissed');
        setTimeout(() => element.remove(), 300);
      } else if (gestureType === 'hide-actions') {
        element.classList.remove('actions-revealed');
      }
    }
  } else if (!isHorizontalSwipe && Math.abs(deltaY) > minSwipeDistance) {
    if (deltaY > 0) {
      // Swipe in giù
      if (gestureType === 'refresh') {
        location.reload();
      } else if (gestureType === 'collapse') {
        element.classList.add('collapsed');
      }
            } else {
      // Swipe in su
      if (gestureType === 'expand') {
        element.classList.remove('collapsed');
      }
    }
  }
}

/**
 * Utilità per unire oggetti profondamente
 */
function deepMerge(...objects) {
  return objects.reduce((acc, obj) => {
    Object.keys(obj).forEach(key => {
      if (typeof obj[key] === 'object' && obj[key] !== null && typeof acc[key] === 'object' && acc[key] !== null) {
        acc[key] = deepMerge(acc[key], obj[key]);
      } else {
        acc[key] = obj[key];
      }
    });
    return acc;
  }, {});
}

/**
 * Aggiunge un widget alla dashboard
 */
function addWidgetToDashboard(widgetType) {
  const widgetContainer = document.querySelector('.widget-container');
  if (!widgetContainer) return;
  
  // Genera ID unico per il widget
  const widgetId = 'widget-' + Date.now();
  
  // Crea elemento widget
  const widget = document.createElement('div');
  widget.className = 'widget';
  widget.dataset.widgetId = widgetId;
  widget.dataset.widgetType = widgetType;
  
  // Contenuto del widget in base al tipo
  let widgetContent = '';
  
  switch (widgetType) {
    case 'stats':
      widgetContent = `
        <div class="widget-header">
          <h3>Statistiche</h3>
          <div class="widget-actions">
            <button class="btn btn-sm btn-icon widget-action" data-action="refresh"><i class="fas fa-sync-alt"></i></button>
            <button class="btn btn-sm btn-icon widget-action" data-action="remove"><i class="fas fa-times"></i></button>
          </div>
        </div>
        <div class="widget-body">
          <div class="d-flex justify-content-between mb-4">
            <div class="stat-item text-center">
              <div class="stat-value">0</div>
              <div class="stat-label">Interazioni</div>
            </div>
            <div class="stat-item text-center">
              <div class="stat-value">0</div>
              <div class="stat-label">Visitatori</div>
            </div>
            <div class="stat-item text-center">
              <div class="stat-value">0</div>
              <div class="stat-label">Conversioni</div>
            </div>
          </div>
          <div class="text-center">
            <a href="/statistics" class="btn btn-sm btn-primary">Visualizza dettagli</a>
          </div>
        </div>
      `;
      break;
    
    case 'chart':
      widgetContent = `
        <div class="widget-header">
          <h3>Grafico</h3>
          <div class="widget-actions">
            <button class="btn btn-sm btn-icon widget-action" data-action="refresh"><i class="fas fa-sync-alt"></i></button>
            <button class="btn btn-sm btn-icon widget-action" data-action="remove"><i class="fas fa-times"></i></button>
          </div>
        </div>
        <div class="widget-body">
          <canvas id="${widgetId}-chart" data-chart-type="line" data-chart-data='{"labels":["Gen","Feb","Mar","Apr","Mag","Giu"],"datasets":[{"label":"Dati","data":[12,19,3,5,2,3],"borderColor":"rgb(75, 192, 192)","tension":0.1}]}'></canvas>
        </div>
      `;
      break;
    
    case 'activity':
      widgetContent = `
        <div class="widget-header">
          <h3>Attività Recenti</h3>
          <div class="widget-actions">
            <button class="btn btn-sm btn-icon widget-action" data-action="refresh"><i class="fas fa-sync-alt"></i></button>
            <button class="btn btn-sm btn-icon widget-action" data-action="remove"><i class="fas fa-times"></i></button>
          </div>
        </div>
        <div class="widget-body">
          <div class="activity-list">
            <div class="activity-item">
              <div class="activity-icon"><i class="fas fa-user"></i></div>
              <div class="activity-content">
                <div class="activity-title">Nuovo utente registrato</div>
                <div class="activity-time">2 minuti fa</div>
              </div>
            </div>
            <div class="activity-item">
              <div class="activity-icon"><i class="fas fa-chart-line"></i></div>
              <div class="activity-content">
                <div class="activity-title">Aggiornamento dashboard</div>
                <div class="activity-time">30 minuti fa</div>
              </div>
            </div>
          </div>
        </div>
      `;
      break;
    
    default:
      widgetContent = `
        <div class="widget-header">
          <h3>Widget</h3>
          <div class="widget-actions">
            <button class="btn btn-sm btn-icon widget-action" data-action="refresh"><i class="fas fa-sync-alt"></i></button>
            <button class="btn btn-sm btn-icon widget-action" data-action="remove"><i class="fas fa-times"></i></button>
          </div>
        </div>
        <div class="widget-body">
          <p>Contenuto del widget</p>
        </div>
      `;
  }
  
  widget.innerHTML = widgetContent;
  widgetContainer.appendChild(widget);
  
  // Inizializza funzionalità del widget
  if (widgetType === 'chart') {
    const chartElement = document.getElementById(`${widgetId}-chart`);
    if (chartElement) {
      initChart(chartElement);
    }
  }
  
  // Aggiungi event listener per le azioni del widget
  const widgetActions = widget.querySelectorAll('.widget-action');
  widgetActions.forEach(action => {
    action.addEventListener('click', function() {
      const actionType = this.dataset.action;
      
      if (actionType === 'remove') {
        widget.classList.add('removing');
        setTimeout(() => {
          widget.remove();
          
          // Aggiorna ordine widget
          const widgetOrder = Array.from(widgetContainer.children).map(w => w.dataset.widgetId);
          localStorage.setItem('dashboardWidgetOrder', JSON.stringify(widgetOrder));
        }, 300);
      } else if (actionType === 'refresh') {
        // Simula aggiornamento
        this.classList.add('rotating');
                setTimeout(() => {
          this.classList.remove('rotating');
        }, 1000);
      }
    });
  });
  
  // Aggiungi classe per animazione di entrata
  setTimeout(() => {
    widget.classList.add('added');
  }, 10);
}
