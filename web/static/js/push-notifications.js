/**
 * M4Bot - Sistema di Notifiche Push
 * Gestisce la richiesta di permessi, la registrazione e la ricezione di notifiche push
 */

(function() {
    'use strict';
    
    // Configurazione
    const config = {
        vapidPublicKey: 'BE5ygQt8-Z5HN8F_z3nFx4-3QYJ7Yc_lbZLUO28E0-tg_qkuLgXjBDZjvDzQiWpNbV8pLNfTX_u0aF_UCPW3RYU',
        notificationsEnabled: false,
        notificationOptions: {
            iconUrl: '/static/icons/icon-192x192.png',
            badgeUrl: '/static/icons/badge-96x96.png',
            defaultTitle: 'M4Bot',
            defaultOptions: {
                vibrate: [100, 50, 100],
                icon: '/static/icons/icon-192x192.png',
                badge: '/static/icons/badge-96x96.png'
            }
        }
    };
    
    // Controlli per l'interfaccia
    let pushToggle;
    let permissionControls;
    let pushStatus;
    
    // Inizializza il sistema di notifiche push
    function init() {
        // Verifica supporto per notifiche push
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) {
            console.warn('Push notifications non supportate dal browser');
            updateUIState('unsupported');
            return;
        }
        
        // Trova elementi UI
        pushToggle = document.getElementById('push-toggle');
        permissionControls = document.getElementById('permission-controls');
        pushStatus = document.querySelector('.push-status');
        
        // Se gli elementi UI non esistono, siamo in una pagina che non li usa
        if (!pushToggle) return;
        
        // Registrazione del Service Worker se non è già registrato
        registerServiceWorker().then(() => {
            // Verifica lo stato attuale delle notifiche
            checkNotificationStatus();
            
            // Aggiungi event listeners
            pushToggle.addEventListener('change', handleToggleChange);
            
            // Trova pulsante per richiedere permessi
            const requestPermissionBtn = document.getElementById('request-permission');
            if (requestPermissionBtn) {
                requestPermissionBtn.addEventListener('click', requestNotificationPermission);
            }
            
            // Trova pulsante per test notifiche
            const testNotificationBtn = document.getElementById('test-notification');
            if (testNotificationBtn) {
                testNotificationBtn.addEventListener('click', sendTestNotification);
            }
        });
    }
    
    // Registra il Service Worker
    async function registerServiceWorker() {
        try {
            const registration = await navigator.serviceWorker.register('/static/js/service-worker.js');
            console.log('Service Worker registrato con successo:', registration);
            return registration;
        } catch (error) {
            console.error('Errore nella registrazione del Service Worker:', error);
            updateUIState('error');
            return null;
        }
    }
    
    // Verifica lo stato attuale delle notifiche
    async function checkNotificationStatus() {
        // Controlla il permesso delle notifiche
        const permission = Notification.permission;
        
        // Se il permesso è garantito, verifica se l'utente è già sottoscritto
        if (permission === 'granted') {
            const registration = await navigator.serviceWorker.ready;
            const subscription = await registration.pushManager.getSubscription();
            
            if (subscription) {
                // Utente già sottoscritto
                config.notificationsEnabled = true;
                updateUIState('subscribed');
            } else {
                // Permesso concesso ma non sottoscritto
                updateUIState('permission-granted');
            }
        } else if (permission === 'denied') {
            // Permesso negato
            updateUIState('permission-denied');
        } else {
            // Permesso non ancora richiesto
            updateUIState('permission-default');
        }
    }
    
    // Gestisce il cambio stato del toggle
    async function handleToggleChange(event) {
        const isChecked = event.target.checked;
        
        try {
            if (isChecked) {
                await subscribeToPushNotifications();
            } else {
                await unsubscribeFromPushNotifications();
            }
        } catch (error) {
            console.error('Errore nel gestire la sottoscrizione:', error);
            pushToggle.checked = !isChecked; // Ripristina stato precedente
            showActionFeedback('error', 'Si è verificato un errore con le notifiche push');
        }
    }
    
    // Sottoscrivi alle notifiche push
    async function subscribeToPushNotifications() {
        try {
            // Richiedi permesso se non già concesso
            if (Notification.permission !== 'granted') {
                const permission = await Notification.requestPermission();
                if (permission !== 'granted') {
                    throw new Error('Permesso per le notifiche non concesso');
                }
            }
            
            // Ottieni la registrazione del service worker
            const registration = await navigator.serviceWorker.ready;
            
            // Converti la chiave pubblica VAPID in un ArrayBuffer
            const applicationServerKey = urlBase64ToUint8Array(config.vapidPublicKey);
            
            // Sottoscrivi l'utente
            const subscription = await registration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: applicationServerKey
            });
            
            // Invia la sottoscrizione al server
            await sendSubscriptionToServer(subscription);
            
            // Aggiorna lo stato
            config.notificationsEnabled = true;
            updateUIState('subscribed');
            
            showActionFeedback('success', 'Notifiche push attivate');
            return true;
        } catch (error) {
            console.error('Errore nella sottoscrizione alle notifiche push:', error);
            updateUIState('error');
            throw error;
        }
    }
    
    // Annulla la sottoscrizione alle notifiche push
    async function unsubscribeFromPushNotifications() {
        try {
            const registration = await navigator.serviceWorker.ready;
            const subscription = await registration.pushManager.getSubscription();
            
            if (subscription) {
                // Cancella sottoscrizione
                await subscription.unsubscribe();
                
                // Comunica al server
                await sendUnsubscriptionToServer(subscription);
                
                // Aggiorna stato
                config.notificationsEnabled = false;
                updateUIState('permission-granted');
                
                showActionFeedback('info', 'Notifiche push disattivate');
                return true;
            }
            
            return false;
        } catch (error) {
            console.error('Errore nella cancellazione della sottoscrizione:', error);
            throw error;
        }
    }
    
    // Richiede il permesso per le notifiche (pulsante dedicato)
    async function requestNotificationPermission() {
        try {
            const permission = await Notification.requestPermission();
            
            if (permission === 'granted') {
                updateUIState('permission-granted');
                showActionFeedback('success', 'Permesso concesso. Attiva le notifiche per riceverle.');
            } else if (permission === 'denied') {
                updateUIState('permission-denied');
                showActionFeedback('warning', 'Permesso negato. Cambia le impostazioni del browser per ricevere notifiche.');
            } else {
                updateUIState('permission-default');
            }
            
            return permission;
        } catch (error) {
            console.error('Errore nella richiesta di permesso:', error);
            updateUIState('error');
            throw error;
        }
    }
    
    // Invia la sottoscrizione al server
    async function sendSubscriptionToServer(subscription) {
        try {
            const response = await fetch('/api/notifications/subscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    subscription: subscription.toJSON(),
                    user_id: getUserId()
                })
            });
            
            if (!response.ok) {
                throw new Error('Errore nella registrazione della sottoscrizione');
            }
            
            return await response.json();
        } catch (error) {
            console.error('Errore nell\'invio della sottoscrizione al server:', error);
            throw error;
        }
    }
    
    // Comunica al server la cancellazione della sottoscrizione
    async function sendUnsubscriptionToServer(subscription) {
        try {
            const response = await fetch('/api/notifications/unsubscribe', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    endpoint: subscription.endpoint,
                    user_id: getUserId()
                })
            });
            
            if (!response.ok) {
                throw new Error('Errore nella cancellazione della sottoscrizione');
            }
            
            return await response.json();
        } catch (error) {
            console.error('Errore nella comunicazione della cancellazione:', error);
            throw error;
        }
    }
    
    // Invia una notifica di test
    async function sendTestNotification() {
        try {
            if (!config.notificationsEnabled) {
                showActionFeedback('warning', 'Attiva prima le notifiche push');
                return;
            }
            
            const response = await fetch('/api/notifications/test', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: getUserId()
                })
            });
            
            if (!response.ok) {
                throw new Error('Errore nell\'invio della notifica di test');
            }
            
            showActionFeedback('info', 'Notifica di test inviata');
            return await response.json();
        } catch (error) {
            console.error('Errore nell\'invio della notifica di test:', error);
            showActionFeedback('error', 'Errore nell\'invio della notifica di test');
            throw error;
        }
    }
    
    // Aggiorna lo stato dell'interfaccia utente
    function updateUIState(state) {
        if (!pushToggle || !permissionControls || !pushStatus) return;
        
        // Reimposta tutto
        pushToggle.disabled = false;
        pushToggle.checked = false;
        permissionControls.style.display = 'none';
        
        // Status text
        let statusText = '';
        
        switch (state) {
            case 'unsupported':
                statusText = 'Le notifiche push non sono supportate dal tuo browser.';
                pushToggle.disabled = true;
                break;
                
            case 'permission-default':
                statusText = 'Richiedi il permesso per ricevere notifiche.';
                pushToggle.disabled = true;
                permissionControls.style.display = 'block';
                break;
                
            case 'permission-granted':
                statusText = 'Permesso concesso. Attiva le notifiche per riceverle.';
                pushToggle.disabled = false;
                break;
                
            case 'permission-denied':
                statusText = 'Permesso negato. Modifica le impostazioni del browser.';
                pushToggle.disabled = true;
                break;
                
            case 'subscribed':
                statusText = 'Notifiche push attive.';
                pushToggle.disabled = false;
                pushToggle.checked = true;
                break;
                
            case 'error':
                statusText = 'Si è verificato un errore con le notifiche push.';
                break;
        }
        
        // Aggiorna testo status
        if (pushStatus) {
            pushStatus.textContent = statusText;
        }
    }
    
    // Utility: Converte Base64 URL-safe in Uint8Array (per applicationServerKey)
    function urlBase64ToUint8Array(base64String) {
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
    }
    
    // Utility: Ottieni ID utente
    function getUserId() {
        const userIdMeta = document.querySelector('meta[name="user-id"]');
        return userIdMeta ? userIdMeta.content : '';
    }
    
    // Inizializza quando il DOM è pronto
    document.addEventListener('DOMContentLoaded', init);
})(); 