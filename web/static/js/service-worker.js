// M4Bot Service Worker
const CACHE_NAME = 'M4Bot-v1.0.0';
const OFFLINE_URL = '/offline.html';

// Risorse da precaricare e cachare
const PRECACHE_ASSETS = [
  '/',
  '/offline.html',
  '/static/css/style.css',
  '/static/css/modern-theme.css',
  '/static/css/dark-theme.css',
  '/static/css/animations.css',
  '/static/js/main.js',
  '/static/js/theme.js',
  '/static/js/notifications.js',
  '/static/img/logo.png',
  '/static/img/logo-dark.png',
  '/static/icons/favicon.ico',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png'
];

// Installazione del Service Worker
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log('Service Worker: Precaching assets');
        return cache.addAll(PRECACHE_ASSETS);
      })
      .then(() => self.skipWaiting()) // Forza il nuovo service worker ad attivarsi immediatamente
  );
});

// Attivazione e pulizia delle vecchie cache
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((cacheName) => {
          if (cacheName !== CACHE_NAME) {
            console.log('Service Worker: Eliminazione cache obsoleta', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim()) // Prende il controllo di tutti i client
  );
});

// Strategia di caching: Network first, poi cache, poi offline fallback
self.addEventListener('fetch', (event) => {
  // Ignora le richieste non GET
  if (event.request.method !== 'GET') return;

  // Ignora le richieste API - usiamo il network per dati freschi
  if (event.request.url.includes('/api/')) return;

  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        // Se la risposta è valida, crea una copia da memorizzare nella cache
        if (networkResponse.ok) {
          const clonedResponse = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, clonedResponse);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // Se il network fallisce, prova a servire dalla cache
        return caches.match(event.request)
          .then((cachedResponse) => {
            // Se c'è una risposta in cache, usala
            if (cachedResponse) {
              return cachedResponse;
            }
            
            // Se la richiesta era per una pagina HTML, mostra la pagina offline
            if (event.request.headers.get('Accept')?.includes('text/html')) {
              return caches.match(OFFLINE_URL);
            }
            
            // Altrimenti, fallisce con errore
            return new Response('Nessuna connessione e nessuna cache disponibile', {
              status: 503,
              statusText: 'Service Unavailable',
              headers: new Headers({
                'Content-Type': 'text/plain'
              })
            });
          });
      })
  );
});

// Gestione notifiche push
self.addEventListener('push', (event) => {
  if (!event.data) return;

  const data = event.data.json();
  const options = {
    body: data.message,
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/badge-96x96.png',
    data: {
      url: data.url || '/'
    },
    actions: data.actions || [],
    vibrate: [100, 50, 100],
    timestamp: data.timestamp || Date.now()
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Gestione click su notifica
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  // Gestisce il click su un'azione specifica
  if (event.action) {
    // Puoi gestire azioni specifiche qui
    console.log('Azione cliccata:', event.action);
  }

  // Apri o focalizza una finestra esistente
  event.waitUntil(
    clients.matchAll({type: 'window'})
      .then((clientList) => {
        const url = event.notification.data.url;
        // Controlla se c'è già una finestra aperta con l'URL target
        for (const client of clientList) {
          if (client.url === url && 'focus' in client) {
            return client.focus();
          }
        }
        // Altrimenti apri una nuova finestra
        if (clients.openWindow) {
          return clients.openWindow(url);
        }
      })
  );
});

// Sincronizzazione in background
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-automation-changes') {
    event.waitUntil(syncAutomationChanges());
  } else if (event.tag === 'sync-pending-commands') {
    event.waitUntil(syncPendingCommands());
  }
});

// Sincronizza le modifiche alle automazioni
async function syncAutomationChanges() {
  try {
    const db = await openDatabase();
    const pendingChanges = await db.getAll('pendingAutomationChanges');
    
    for (const change of pendingChanges) {
      try {
        const response = await fetch('/api/automations/sync', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify(change)
        });
        
        if (response.ok) {
          await db.delete('pendingAutomationChanges', change.id);
        }
      } catch (err) {
        console.error('Errore durante la sincronizzazione:', err);
      }
    }
  } catch (err) {
    console.error('Errore nell\'accesso al database:', err);
  }
}

// Sincronizza i comandi in sospeso
async function syncPendingCommands() {
  // Implementazione simile a syncAutomationChanges
  console.log('Sincronizzazione comandi in sospeso');
}

// Helper per aprire il database IndexedDB
function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('M4BotOfflineDB', 1);
    
    request.onerror = () => reject(request.error);
    request.onsuccess = () => resolve(request.result);
    
    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      if (!db.objectStoreNames.contains('pendingAutomationChanges')) {
        db.createObjectStore('pendingAutomationChanges', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('pendingCommands')) {
        db.createObjectStore('pendingCommands', { keyPath: 'id' });
      }
    };
  });
} 