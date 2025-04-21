// Service Worker per M4Bot
const CACHE_NAME = 'm4bot-cache-v1';
const ASSETS_TO_CACHE = [
  '/',
  '/static/css/main.css',
  '/static/css/dashboard.css',
  '/static/js/main.js',
  '/static/js/dashboard.js',
  '/static/img/logo.png',
  '/static/img/icon-192x192.png',
  '/static/img/icon-512x512.png',
  '/offline'
];

// Installazione del service worker e pre-caricamento degli asset
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Cache aperta');
        return cache.addAll(ASSETS_TO_CACHE);
      })
      .then(() => self.skipWaiting())
  );
});

// Pulizia delle cache precedenti
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(cacheName => {
          return cacheName !== CACHE_NAME;
        }).map(cacheName => {
          return caches.delete(cacheName);
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Strategia di caching: network first, poi cache
self.addEventListener('fetch', event => {
  // Ignora le richieste non HTTP
  if (!event.request.url.startsWith('http')) return;
  
  // Gestisci solo richieste GET
  if (event.request.method !== 'GET') return;
  
  // Evita di cachare richieste API
  if (event.request.url.includes('/api/')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Clona la risposta per memorizzarla in cache
        const responseToCache = response.clone();
        
        caches.open(CACHE_NAME)
          .then(cache => {
            // Memorizza in cache solo le risposte valide
            if (response.status === 200) {
              cache.put(event.request, responseToCache);
            }
          });
          
        return response;
      })
      .catch(() => {
        // In caso di errore di rete, tenta di servire dalla cache
        return caches.match(event.request)
          .then(cachedResponse => {
            // Se l'asset è in cache, restituiscilo
            if (cachedResponse) {
              return cachedResponse;
            }
            
            // Se è una richiesta di pagina, mostra la pagina offline
            if (event.request.mode === 'navigate') {
              return caches.match('/offline');
            }
            
            // Altrimenti, fallisci elegantemente
            return new Response('Contenuto non disponibile offline', {
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

// Gestione dei messaggi
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

// Gestione della sincronizzazione in background
self.addEventListener('sync', event => {
  if (event.tag === 'sync-data') {
    event.waitUntil(syncData());
  }
});

// Funzione per sincronizzare i dati quando si ritorna online
function syncData() {
  return fetch('/api/sync')
    .then(response => response.json())
    .then(data => {
      console.log('Sincronizzazione completata', data);
    })
    .catch(error => {
      console.error('Errore durante la sincronizzazione', error);
    });
} 