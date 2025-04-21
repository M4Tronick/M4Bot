/**
 * M4Bot - Service Worker Avanzato
 * Gestisce caching delle risorse e funzionalità offline
 */

// Versione della cache - incrementare questo valore per forzare un aggiornamento della cache
const CACHE_VERSION = 'v1';
const CACHE_NAME = `m4bot-cache-${CACHE_VERSION}`;
const OFFLINE_URL = '/offline.html';

// Risorse da memorizzare nella cache durante l'installazione
const PRECACHE_URLS = [
    '/',
    '/offline.html',
  '/static/css/main.css',
  '/static/js/main.js',
  '/static/img/logo.png',
  '/static/img/icon-192.png',
  '/static/img/icon-512.png',
  '/static/manifest.json'
];

// Risorse dell'applicazione da cachare
const APP_SHELL = [
  '/',
    '/static/css/style.css',
  '/static/css/accessibility.css',
    '/static/js/main.js',
  '/static/js/accessibility.js',
  '/static/js/bootstrap.bundle.min.js',
  '/static/js/jquery.min.js',
    '/static/img/logo.png',
  '/static/img/favicon.ico',
    '/static/icons/icon-192x192.png',
    '/static/manifest.json'
];

// Risorse statiche che vogliamo sempre cachare
const STATIC_ASSETS = [
  '/static/css/',
  '/static/js/',
  '/static/img/',
  '/static/icons/'
];

// Pagine e API che devono essere sempre caricate dalla rete
const NETWORK_ONLY = [
  '/api/user/profile',
  '/api/auth/',
  '/api/admin/',
  '/admin/',
    '/login',
  '/logout',
  '/register'
];

// Limiti di caching
const API_CACHE_DURATION = 60 * 5; // 5 minuti in secondi
const PAGE_CACHE_DURATION = 60 * 60 * 24; // 24 ore in secondi
const MAX_API_CACHE_ITEMS = 50; // Massimo numero di richieste API da cachare
const MAX_PAGE_CACHE_ITEMS = 20; // Massimo numero di pagine da cachare

/**
 * Installa il service worker e cacha le risorse essenziali
 */
self.addEventListener('install', event => {
  console.log('[Service Worker] Installazione...');
    
  // Salta la fase di attesa e passa direttamente ad attivare il worker
    self.skipWaiting();
    
    event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[Service Worker] Memorizzazione in cache delle risorse essenziali');
        return cache.addAll(PRECACHE_URLS);
      })
      .catch(error => {
        console.error('[Service Worker] Errore durante la pre-cache:', error);
        })
    );
});

/**
 * Attivazione: pulisci le vecchie cache
 */
self.addEventListener('activate', event => {
  console.log('[Service Worker] Attivazione...');
    
  // Prendi il controllo immediatamente
    self.clients.claim();
    
  // Elimina le vecchie cache
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.filter(cacheName => {
          return cacheName.startsWith('m4bot-cache-') && cacheName !== CACHE_NAME;
                }).map(cacheName => {
          console.log('[Service Worker] Eliminazione della cache obsoleta:', cacheName);
                    return caches.delete(cacheName);
                })
            );
        })
    );
});

/**
 * Intercetta le richieste e gestisci caching e funzionalità offline
 */
self.addEventListener('fetch', event => {
  // Salta le richieste che non sono GET o che sono verso altri domini
  if (event.request.method !== 'GET' || !event.request.url.startsWith(self.location.origin)) {
    return;
  }
  
  const url = new URL(event.request.url);
  
  // Gestione speciale per risorse dell'app shell
  if (APP_SHELL.includes(url.pathname)) {
    event.respondWith(cacheFirst(event.request));
        return;
    }
    
  // Gestione API (network first con fallback a cache)
  if (url.pathname.startsWith('/api/')) {
    // Controlla se è un endpoint che deve essere sempre fresco
    if (NETWORK_ONLY.some(pattern => url.pathname.startsWith(pattern))) {
      event.respondWith(networkOnly(event.request));
    } else {
      event.respondWith(networkFirstWithTimeout(event.request, 3000));
    }
        return;
    }
    
  // Gestione risorse statiche (cache first con aggiornamento in background)
  if (isStaticAsset(url.pathname)) {
    event.respondWith(cacheFirst(event.request));
        return;
    }

  // Gestione pagine HTML (network first con fallback a cache)
  if (url.pathname.endsWith('/') || url.pathname.endsWith('.html')) {
    event.respondWith(networkFirst(event.request));
        return;
    }
    
  // Per tutto il resto, usa staleWhileRevalidate
  event.respondWith(staleWhileRevalidate(event.request));
});

/**
 * Verifica se un pathname è una risorsa statica
 */
function isStaticAsset(pathname) {
  return STATIC_ASSETS.some(path => pathname.startsWith(path));
}

/**
 * Strategia Cache First: prova prima dalla cache, poi dalla rete
 */
async function cacheFirst(request) {
  try {
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Se non è in cache, recupera dalla rete e salva in cache
    const networkResponse = await fetch(request);
    await updateCache(request, networkResponse.clone());
    return networkResponse;
  } catch (error) {
    console.error('Cache first fallito:', error);
    // Se sia la cache che la rete falliscono, ritorna pagina di errore
    return caches.match('/static/emergency.html');
  }
}

/**
 * Strategia Network First: prova prima dalla rete, poi dalla cache
 */
async function networkFirst(request) {
  try {
    // Prova a recuperare dalla rete
    const networkResponse = await fetch(request);
    
    // Salva in cache per uso offline futuro
    await updateCache(request, networkResponse.clone());
    return networkResponse;
  } catch (error) {
    console.log('Network request fallita, uso cache:', request.url);
    
    // Se la rete fallisce, usa la cache
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Se non è disponibile in cache, mostra pagina offline
    return caches.match('/static/emergency.html');
  }
}

/**
 * Strategia Network First con timeout: passa alla cache se la rete è lenta
 */
async function networkFirstWithTimeout(request, timeoutMs) {
  return new Promise(resolve => {
    let timeoutId;
    
    // Imposta un timeout per la richiesta di rete
    const timeoutPromise = new Promise(resolveTimeout => {
      timeoutId = setTimeout(() => {
        resolveTimeout('TIMEOUT');
      }, timeoutMs);
    });
    
    // Tenta di recuperare dalla rete
    fetch(request.clone())
      .then(networkResponse => {
        clearTimeout(timeoutId);
        
        // Aggiorna la cache con la risposta fresca
        updateCache(request, networkResponse.clone());
        resolve(networkResponse);
      })
      .catch(error => {
        console.log('Network request fallita (timeout):', error);
        clearTimeout(timeoutId);
        
        // Fallback alla cache
        caches.match(request)
          .then(cachedResponse => {
            if (cachedResponse) {
              resolve(cachedResponse);
            } else {
              // Nessuna cache disponibile, mostra pagina offline
              resolve(caches.match('/static/emergency.html'));
            }
          });
      });
    
    // Se scade il timeout, usa la cache
    timeoutPromise.then(result => {
      if (result === 'TIMEOUT') {
        console.log('Network request timeout, uso cache:', request.url);
        
        // Ottieni dalla cache
        caches.match(request)
          .then(cachedResponse => {
            if (cachedResponse) {
              resolve(cachedResponse);
            } else {
              // Continua ad aspettare la rete
              console.log('Nessuna cache disponibile, continuo ad attendere la rete');
            }
          });
      }
    });
  });
}

/**
 * Strategia Stale While Revalidate: usa la cache mentre aggiorna in background
 */
async function staleWhileRevalidate(request) {
  try {
    const cache = await caches.open(CACHE_NAME);
    
    // Prova prima dalla cache
    const cachedResponse = await cache.match(request);
    
    // Avvia aggiornamento dalla rete in background
    const networkResponsePromise = fetch(request)
      .then(networkResponse => {
        // Aggiorna la cache con la risposta fresca
        updateCache(request, networkResponse.clone());
        return networkResponse;
      })
      .catch(error => {
        console.error('Errore nel recupero da rete:', error);
      });
    
    // Restituisci subito la risposta dalla cache se disponibile
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Altrimenti aspetta la risposta dalla rete
    return await networkResponsePromise;
  } catch (error) {
    console.error('Stale-while-revalidate fallito:', error);
    return caches.match('/static/emergency.html');
  }
}

/**
 * Strategia Network Only: usa solo la rete (per contenuti sensibili)
 */
async function networkOnly(request) {
  try {
    return await fetch(request);
  } catch (error) {
    console.error('Network only fallito:', error);
    return caches.match('/static/emergency.html');
  }
}

/**
 * Aggiorna la cache con la nuova risposta
 */
async function updateCache(request, response) {
  // Non cachare risposte non valide o non get
  if (!response || response.status !== 200 || request.method !== 'GET') {
    return;
  }
  
  // Non cachare risposte che non vogliono essere cachate
  const cacheControl = response.headers.get('Cache-Control');
  if (cacheControl && (cacheControl.includes('no-store') || cacheControl.includes('no-cache'))) {
    return;
  }
  
  const url = new URL(request.url);
  
  // Imposta la durata appropriata e limiti per API e pagine
  if (url.pathname.startsWith('/api/')) {
    await limitCacheSize(CACHE_NAME, MAX_API_CACHE_ITEMS, entry => {
      return entry.request.url.includes('/api/');
    });
  } else if (url.pathname.endsWith('/') || url.pathname.endsWith('.html')) {
    await limitCacheSize(CACHE_NAME, MAX_PAGE_CACHE_ITEMS, entry => {
      const entryUrl = new URL(entry.request.url);
      return entryUrl.pathname.endsWith('/') || entryUrl.pathname.endsWith('.html');
    });
  }
  
  const cache = await caches.open(CACHE_NAME);
  await cache.put(request, response);
}

/**
 * Limita la dimensione della cache
 */
async function limitCacheSize(cacheName, maxItems, filterFunc) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  const itemsToDelete = keys
    .filter(filterFunc)
    .reverse()
    .slice(maxItems);
    
  await Promise.all(itemsToDelete.map(request => cache.delete(request)));
}

/**
 * Gestione delle sincronizzazioni in background
 */
self.addEventListener('sync', event => {
  if (event.tag === 'syncData') {
    event.waitUntil(syncData());
  }
});

/**
 * Sincronizza i dati in background
 */
async function syncData() {
  try {
    // Recupera richieste in coda
    const db = await openDatabase();
    const pendingRequests = await db.getAll('pending-requests');
    
    // Invia ogni richiesta in coda
    const successfulSyncs = [];
    
    for (const request of pendingRequests) {
      try {
        const response = await fetch(request.url, request.options);
        if (response.ok) {
          successfulSyncs.push(request.id);
        }
      } catch (error) {
        console.error('Errore nella sincronizzazione:', error);
      }
    }
    
    // Rimuovi le richieste completate
    const tx = db.transaction('pending-requests', 'readwrite');
    for (const id of successfulSyncs) {
      await tx.store.delete(id);
    }
    
    // Notifica i clients della sincronizzazione completata
    const clients = await self.clients.matchAll();
    clients.forEach(client => {
      client.postMessage({
        type: 'sync-complete',
        successCount: successfulSyncs.length,
        totalCount: pendingRequests.length
      });
    });
    
    return true;
  } catch (error) {
    console.error('Errore nella sincronizzazione dei dati:', error);
    return false;
  }
}

/**
 * Apre il database IndexedDB
 */
function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('m4bot-offline-db', 1);
    
    request.onupgradeneeded = event => {
            const db = event.target.result;
      if (!db.objectStoreNames.contains('pending-requests')) {
        db.createObjectStore('pending-requests', { keyPath: 'id' });
      }
    };
    
    request.onsuccess = event => resolve(event.target.result);
    request.onerror = event => reject(event.target.error);
  });
}

/**
 * Gestisce i messaggi dai clients
 */
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'CHECK_UPDATE') {
    console.log('[Service Worker] Verifica aggiornamenti...');
    self.registration.update();
  }
});

// Notifiche push
self.addEventListener('push', event => {
  if (!event.data) return;
  
  try {
    const data = event.data.json();
    
    const notificationOptions = {
      body: data.message || 'Nuova notifica da M4Bot',
      icon: '/static/images/logo.png',
      badge: '/static/images/badge.png',
      data: {
        url: data.url || '/'
      }
    };
    
    event.waitUntil(
      self.registration.showNotification('M4Bot', notificationOptions)
    );
    } catch (error) {
    console.error('[Service Worker] Errore nella gestione della notifica push:', error);
  }
});

// Azione click su notifica
self.addEventListener('notificationclick', event => {
  event.notification.close();
  
  if (event.notification.data && event.notification.data.url) {
    event.waitUntil(
      clients.openWindow(event.notification.data.url)
    );
  }
}); 