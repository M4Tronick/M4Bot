// M4Bot Service Worker
const CACHE_NAME = 'M4Bot-v1';
const RESOURCES_TO_CACHE = [
  '/',
  '/offline',
  '/static/css/main.css',
  '/static/js/main.js',
  '/static/img/logo.png',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  '/static/offline.html'
];

// Installazione del service worker
self.addEventListener('install', event => {
  console.log('Service Worker: Installazione in corso');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Service Worker: Apertura cache');
        return cache.addAll(RESOURCES_TO_CACHE);
      })
      .then(() => {
        console.log('Service Worker: Risorse memorizzate nella cache');
        return self.skipWaiting();
      })
      .catch(error => {
        console.error('Errore durante la memorizzazione nella cache:', error);
      })
  );
});

// Attivazione del service worker
self.addEventListener('activate', event => {
  console.log('Service Worker: Attivazione in corso');
  
  // Rimuovi tutte le vecchie cache
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('Service Worker: Eliminazione vecchia cache', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => {
      console.log('Service Worker: Rivendicazione dei clients');
      return self.clients.claim();
    })
  );
});

// Gestione delle richieste di rete
self.addEventListener('fetch', event => {
  // Gestisci solo le richieste GET
  if (event.request.method !== 'GET') return;
  
  // Ignora le richieste a endpoint di API
  if (event.request.url.includes('/api/')) {
    return;
  }

  console.log('Service Worker: Intercettazione fetch', event.request.url);
  
  event.respondWith(
    caches.match(event.request)
      .then(cachedResponse => {
        // Ritorna la risorsa dalla cache se esiste
        if (cachedResponse) {
          console.log('Service Worker: Risposta dalla cache per', event.request.url);
          return cachedResponse;
        }
        
        // Altrimenti, fai una richiesta alla rete
        console.log('Service Worker: Fetch dalla rete per', event.request.url);
        return fetch(event.request)
          .then(response => {
            // Se la risposta non è valida, restituisci un errore
            if (!response || response.status !== 200 || response.type !== 'basic') {
              console.log('Service Worker: Risposta non valida dalla rete');
              return response;
            }
            
            // Clona la risposta perché non possiamo usare il corpo più di una volta
            let responseToCache = response.clone();
            
            // Aggiungi la risposta alla cache per uso futuro
            caches.open(CACHE_NAME)
              .then(cache => {
                console.log('Service Worker: Memorizzazione nella cache', event.request.url);
                cache.put(event.request, responseToCache);
              });
            
            return response;
          })
          .catch(error => {
            console.log('Service Worker: Errore di rete', error);
            
            // Verifica se è una richiesta di pagina
            if (event.request.headers.get('Accept').includes('text/html')) {
              return caches.match('/static/offline.html');
            }
            
            return new Response('Risorsa non disponibile offline', {
              status: 503,
              statusText: 'Service Unavailable'
            });
          });
      })
  );
});

// Gestione delle notifiche push
self.addEventListener('push', event => {
  if (!event.data) return;
  
  try {
    const data = event.data.json();
    
    const options = {
      body: data.body || 'Nuova notifica da M4Bot',
      icon: '/static/img/icon-192.png',
      badge: '/static/img/badge.png',
      data: data.url || '/',
      vibrate: [100, 50, 100],
      actions: data.actions || []
    };
    
    event.waitUntil(
      self.registration.showNotification(data.title || 'M4Bot', options)
    );
  } catch (error) {
    console.error('Errore durante l\'elaborazione della notifica push:', error);
  }
});

// Gestione dei click sulle notifiche
self.addEventListener('notificationclick', event => {
  console.log('Service Worker: Click su notifica');
  
  event.notification.close();
  
  event.waitUntil(
    clients.matchAll({ type: 'window' })
      .then(clientList => {
        // Se c'è una finestra client aperta, focalizzala
        for (const client of clientList) {
          if (client.url === event.notification.data && 'focus' in client) {
            return client.focus();
          }
        }
        // Altrimenti apri una nuova finestra
        if (clients.openWindow) {
          return clients.openWindow(event.notification.data);
        }
      })
  );
});

// Gestione della sincronizzazione in background
self.addEventListener('sync', event => {
  console.log('Service Worker: Evento di sincronizzazione', event.tag);
  
  if (event.tag === 'sync-data') {
    event.waitUntil(
      // Qui implementare la logica per sincronizzare i dati
      console.log('Service Worker: Sincronizzazione dati in corso')
    );
  }
}); 