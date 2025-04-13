/**
 * M4Bot - Sistema di Heartbeat
 * Monitoraggio dello stato di connessione e gestione disconnessioni
 */

class HeartbeatSystem {
  constructor(options = {}) {
    // Configurazione default
    this.config = {
      heartbeatInterval: options.heartbeatInterval || 15000, // 15 secondi
      reconnectInterval: options.reconnectInterval || 5000,  // 5 secondi
      maxReconnectAttempts: options.maxReconnectAttempts || 10,
      apiEndpoint: options.apiEndpoint || '/api/heartbeat',
      onStatusChange: options.onStatusChange || (() => {}),
      onReconnect: options.onReconnect || (() => {}),
      onDisconnect: options.onDisconnect || (() => {}),
      debug: options.debug || false
    };

    // Stato del sistema
    this.state = {
      status: 'disconnected', // disconnected, connecting, connected, reconnecting
      reconnectAttempts: 0,
      lastHeartbeat: null,
      timerId: null,
      reconnectTimerId: null,
      events: []
    };

    // Inizializzazione della coda eventi
    this.eventQueue = new EventQueue({
      processInterval: 1000,
      maxQueueSize: 100,
      onQueueFull: this.handleQueueFull.bind(this)
    });
    
    this.init();
  }

  init() {
    this.log('Inizializzazione sistema heartbeat');
    
    // Aggiungiamo listener per eventi di connettività browser
    window.addEventListener('online', () => this.handleOnline());
    window.addEventListener('offline', () => this.handleOffline());
    
    // Aggiungiamo listener per visibilità pagina
    document.addEventListener('visibilitychange', () => this.handleVisibilityChange());
    
    // Iniziamo il monitoraggio se siamo online
    if (navigator.onLine) {
      this.start();
    } else {
      this.updateStatus('disconnected');
    }
    
    // Integrazione con eventuali WebSocket esistenti
    this.setupWebSocketIntegration();
  }

  start() {
    this.log('Avvio sistema heartbeat');
    this.stopHeartbeat(); // Fermiamo eventuali timer esistenti
    
    // Eseguiamo subito il primo controllo
    this.sendHeartbeat();
    
    // Impostiamo il timer per i controlli periodici
    this.state.timerId = setInterval(() => {
      this.sendHeartbeat();
    }, this.config.heartbeatInterval);
    
    this.updateStatus('connecting');
  }

  stop() {
    this.log('Arresto sistema heartbeat');
    this.stopHeartbeat();
    this.stopReconnect();
    this.updateStatus('disconnected');
  }

  stopHeartbeat() {
    if (this.state.timerId) {
      clearInterval(this.state.timerId);
      this.state.timerId = null;
    }
  }

  stopReconnect() {
    if (this.state.reconnectTimerId) {
      clearTimeout(this.state.reconnectTimerId);
      this.state.reconnectTimerId = null;
    }
  }

  async sendHeartbeat() {
    this.log('Invio heartbeat al server');
    
    try {
      const startTime = performance.now();
      const response = await fetch(this.config.apiEndpoint, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'X-Requested-With': 'XMLHttpRequest'
        },
        credentials: 'same-origin'
      });
      
      const endTime = performance.now();
      const latency = Math.round(endTime - startTime);
      
      if (response.ok) {
        const data = await response.json();
        this.handleSuccessfulHeartbeat(data, latency);
      } else {
        throw new Error(`Server response: ${response.status}`);
      }
    } catch (error) {
      this.handleFailedHeartbeat(error);
    }
  }

  handleSuccessfulHeartbeat(data, latency) {
    this.log(`Heartbeat riuscito (${latency}ms)`);
    
    // Aggiorniamo lo stato
    this.state.lastHeartbeat = new Date();
    this.state.reconnectAttempts = 0;
    
    // Se eravamo in stato di reconnecting, ora siamo di nuovo connessi
    if (this.state.status !== 'connected') {
      this.updateStatus('connected');
      
      // Processare eventi in coda se presenti
      if (this.eventQueue.size() > 0) {
        this.log(`Processamento di ${this.eventQueue.size()} eventi in coda`);
        this.eventQueue.processAll();
      }
    }
    
    // Aggiungiamo l'evento alla lista per il grafico
    this.addLatencyDataPoint(latency);
    
    // Verifichiamo se ci sono aggiornamenti o modifiche dal server
    if (data && data.serverTime) {
      this.syncWithServer(data);
    }
  }

  handleFailedHeartbeat(error) {
    this.log(`Heartbeat fallito: ${error.message}`, 'error');
    
    // Se eravamo connessi, passiamo a reconnecting
    if (this.state.status === 'connected') {
      this.updateStatus('reconnecting');
    }
    
    // Fermiamo il timer di heartbeat
    this.stopHeartbeat();
    
    // Iniziamo il processo di riconnessione
    this.startReconnect();
  }

  startReconnect() {
    // Se abbiamo superato il numero massimo di tentativi, ci fermiamo
    if (this.state.reconnectAttempts >= this.config.maxReconnectAttempts) {
      this.log('Numero massimo di tentativi di riconnessione raggiunto', 'error');
      this.updateStatus('disconnected');
      return;
    }
    
    this.state.reconnectAttempts++;
    
    // Calcoliamo intervallo con backoff esponenziale
    const backoffMultiplier = Math.min(Math.pow(1.5, this.state.reconnectAttempts - 1), 5);
    const reconnectTimeout = this.config.reconnectInterval * backoffMultiplier;
    
    this.log(`Tentativo di riconnessione ${this.state.reconnectAttempts}/${this.config.maxReconnectAttempts} tra ${Math.round(reconnectTimeout / 1000)}s`);
    
    // Impostiamo il timer per la riconnessione
    this.stopReconnect(); // Fermiamo eventuali timer esistenti
    this.state.reconnectTimerId = setTimeout(() => {
      this.sendHeartbeat();
      
      // Se il heartbeat fallisce, tenteremo di nuovo
      if (this.state.status === 'reconnecting') {
        this.startReconnect();
      }
    }, reconnectTimeout);
  }

  updateStatus(newStatus) {
    if (this.state.status === newStatus) return;
    
    const oldStatus = this.state.status;
    this.state.status = newStatus;
    
    this.log(`Stato connessione: ${oldStatus} -> ${newStatus}`);
    
    // Invochiamo il callback di cambio stato
    this.config.onStatusChange(newStatus, oldStatus);
    
    // Eseguiamo azioni specifiche in base allo stato
    if (newStatus === 'connected' && oldStatus === 'reconnecting') {
      this.config.onReconnect();
    } else if (newStatus === 'disconnected' && (oldStatus === 'connected' || oldStatus === 'reconnecting')) {
      this.config.onDisconnect();
    }
    
    // Aggiorniamo l'interfaccia utente
    this.updateUI(newStatus);
    
    // Se siamo disconnessi, fermiamo tutto
    if (newStatus === 'disconnected') {
      this.stopHeartbeat();
      this.stopReconnect();
    }
  }

  updateUI(status) {
    const statusIndicators = document.querySelectorAll('.connection-status .status-indicator');
    const statusTexts = document.querySelectorAll('.connection-status .status-text');
    
    if (statusIndicators.length === 0) return;
    
    // Aggiorniamo tutte le istanze dell'indicatore di stato
    statusIndicators.forEach(indicator => {
      indicator.className = 'status-indicator';
      indicator.classList.add(status);
    });
    
    // Aggiorniamo i testi di stato
    statusTexts.forEach(text => {
      switch (status) {
        case 'connected':
          text.textContent = 'Connesso';
          break;
        case 'connecting':
          text.textContent = 'Connessione...';
          break;
        case 'reconnecting':
          text.textContent = `Riconnessione (${this.state.reconnectAttempts}/${this.config.maxReconnectAttempts})`;
          break;
        case 'disconnected':
          text.textContent = 'Disconnesso';
          break;
      }
    });
  }

  handleOnline() {
    this.log('Connessione di rete disponibile');
    if (this.state.status === 'disconnected') {
      this.start();
    }
  }

  handleOffline() {
    this.log('Connessione di rete persa', 'warning');
    this.updateStatus('disconnected');
  }

  handleVisibilityChange() {
    if (document.visibilityState === 'visible') {
      this.log('Pagina visibile, controllo connessione');
      // Se siamo disconnessi o in riconnessione, proviamo a riconnetterci immediatamente
      if (this.state.status === 'disconnected' || this.state.status === 'reconnecting') {
        this.stopReconnect();
        this.sendHeartbeat();
      }
    } else {
      this.log('Pagina nascosta');
      // Possiamo rallentare gli heartbeat quando la pagina non è visibile
      // per risparmiare risorse
    }
  }

  addLatencyDataPoint(latency) {
    // Aggiungiamo il dato alla lista per visualizzazione
    this.state.events.push({
      time: new Date(),
      latency,
      status: this.state.status
    });
    
    // Manteniamo solo gli ultimi 100 eventi
    if (this.state.events.length > 100) {
      this.state.events.shift();
    }
    
    // Aggiorniamo il grafico se disponibile
    this.updateLatencyChart();
  }

  updateLatencyChart() {
    // Se esiste un elemento canvas per il grafico, lo aggiorniamo
    const chartCanvas = document.getElementById('latency-chart');
    if (!chartCanvas || !window.Chart) return;
    
    // Implementazione grafico latenza
    // Questa è solo una struttura base, va implementata con una libreria come Chart.js
  }

  syncWithServer(data) {
    // Sincronizzazione con il server
    if (data.serverTime) {
      const serverTime = new Date(data.serverTime);
      const clientTime = new Date();
      const timeDiff = Math.abs(serverTime - clientTime);
      
      if (timeDiff > 5000) {
        this.log(`Differenza orario con server: ${Math.round(timeDiff / 1000)}s`, 'warning');
      }
    }
    
    // Se ci sono comandi dal server, li eseguiamo
    if (data.commands && Array.isArray(data.commands)) {
      data.commands.forEach(cmd => this.executeServerCommand(cmd));
    }
  }

  executeServerCommand(command) {
    this.log(`Esecuzione comando dal server: ${command.type}`);
    
    switch (command.type) {
      case 'reload':
        window.location.reload();
        break;
      case 'redirect':
        if (command.url) {
          window.location.href = command.url;
        }
        break;
      case 'notification':
        this.showNotification(command.title, command.message, command.options);
        break;
      case 'execute':
        if (command.function && typeof window[command.function] === 'function') {
          try {
            window[command.function].apply(null, command.args || []);
          } catch (error) {
            this.log(`Errore nell'esecuzione di ${command.function}: ${error.message}`, 'error');
          }
        }
        break;
    }
  }

  showNotification(title, message, options = {}) {
    if ('Notification' in window) {
      // Chiediamo il permesso se necessario
      if (Notification.permission !== 'granted' && Notification.permission !== 'denied') {
        Notification.requestPermission();
      }
      
      if (Notification.permission === 'granted') {
        new Notification(title, {
          body: message,
          icon: options.icon || '/static/img/logo.png',
          ...options
        });
      }
    }
  }

  registerEventHandler(eventType, handler) {
    if (!this.eventHandlers) {
      this.eventHandlers = {};
    }
    
    if (!this.eventHandlers[eventType]) {
      this.eventHandlers[eventType] = [];
    }
    
    this.eventHandlers[eventType].push(handler);
    this.log(`Handler registrato per evento: ${eventType}`);
  }

  triggerEvent(event) {
    if (this.state.status === 'connected') {
      // Se siamo connessi, processiamo subito l'evento
      this.processEvent(event);
    } else {
      // Altrimenti lo mettiamo in coda
      this.log(`Accodamento evento ${event.type} (stato: ${this.state.status})`);
      this.eventQueue.add(event);
    }
  }

  processEvent(event) {
    this.log(`Processamento evento: ${event.type}`);
    
    if (this.eventHandlers && this.eventHandlers[event.type]) {
      this.eventHandlers[event.type].forEach(handler => {
        try {
          handler(event);
        } catch (error) {
          this.log(`Errore nel processamento dell'evento ${event.type}: ${error.message}`, 'error');
        }
      });
    }
  }

  handleQueueFull() {
    this.log('Coda eventi piena, rimozione eventi più vecchi', 'warning');
    // Quando la coda è piena, possiamo implementare strategie specifiche
    // ad esempio, rimuovere eventi a bassa priorità o aggregare eventi simili
  }

  setupWebSocketIntegration() {
    // Integrazione con WebSocket esistenti nel sistema
    // Se l'app utilizza già WebSocket, possiamo utilizzarli per il heartbeat
    if (window.m4botWebSocket) {
      this.log('Integrazione con WebSocket esistente');
      
      const ws = window.m4botWebSocket;
      
      // Intercettiamo gli eventi del WebSocket
      const originalOnOpen = ws.onopen;
      const originalOnClose = ws.onclose;
      const originalOnError = ws.onerror;
      
      ws.onopen = (event) => {
        this.updateStatus('connected');
        if (originalOnOpen) originalOnOpen.call(ws, event);
      };
      
      ws.onclose = (event) => {
        this.updateStatus('reconnecting');
        if (originalOnClose) originalOnClose.call(ws, event);
      };
      
      ws.onerror = (event) => {
        this.updateStatus('reconnecting');
        if (originalOnError) originalOnError.call(ws, event);
      };
    }
  }

  log(message, level = 'info') {
    if (!this.config.debug && level === 'info') return;
    
    const timestamp = new Date().toISOString().split('T')[1].split('Z')[0];
    
    switch (level) {
      case 'error':
        console.error(`[Heartbeat ${timestamp}] ${message}`);
        break;
      case 'warning':
        console.warn(`[Heartbeat ${timestamp}] ${message}`);
        break;
      default:
        console.log(`[Heartbeat ${timestamp}] ${message}`);
    }
  }

  // Utilità per ottenere i dati di monitoraggio
  getMonitoringData() {
    return {
      status: this.state.status,
      lastHeartbeat: this.state.lastHeartbeat,
      reconnectAttempts: this.state.reconnectAttempts,
      events: [...this.state.events],
      queueSize: this.eventQueue.size()
    };
  }
}

/**
 * Coda eventi con gestione delle priorità
 */
class EventQueue {
  constructor(options = {}) {
    this.queue = [];
    this.processing = false;
    this.config = {
      processInterval: options.processInterval || 1000,
      maxQueueSize: options.maxQueueSize || 100,
      onQueueFull: options.onQueueFull || (() => {}),
      onProcess: options.onProcess || (() => {})
    };
  }

  add(event) {
    // Assegniamo priorità di default se non specificata
    if (event.priority === undefined) {
      event.priority = 5; // Priorità media
    }

    // Aggiungiamo timestamp se non presente
    if (!event.timestamp) {
      event.timestamp = Date.now();
    }

    // Controlliamo se la coda è piena
    if (this.queue.length >= this.config.maxQueueSize) {
      this.config.onQueueFull();
      
      // Rimuoviamo l'evento a priorità più bassa
      // o il più vecchio a pari priorità
      this.removeLowestPriorityEvent();
    }

    // Inseriamo l'evento ordinato per priorità (e timestamp a pari priorità)
    let inserted = false;
    for (let i = 0; i < this.queue.length; i++) {
      if (
        event.priority > this.queue[i].priority || 
        (event.priority === this.queue[i].priority && event.timestamp < this.queue[i].timestamp)
      ) {
        this.queue.splice(i, 0, event);
        inserted = true;
        break;
      }
    }

    if (!inserted) {
      this.queue.push(event);
    }

    return this.queue.length;
  }

  removeLowestPriorityEvent() {
    if (this.queue.length === 0) return null;
    
    let lowestPriorityIndex = 0;
    let lowestPriority = this.queue[0].priority;
    let oldestTimestamp = this.queue[0].timestamp;
    
    // Troviamo l'evento con priorità più bassa
    // (o il più vecchio a pari priorità)
    for (let i = 1; i < this.queue.length; i++) {
      if (
        this.queue[i].priority < lowestPriority ||
        (this.queue[i].priority === lowestPriority && this.queue[i].timestamp < oldestTimestamp)
      ) {
        lowestPriorityIndex = i;
        lowestPriority = this.queue[i].priority;
        oldestTimestamp = this.queue[i].timestamp;
      }
    }
    
    return this.queue.splice(lowestPriorityIndex, 1)[0];
  }

  process() {
    if (this.queue.length === 0 || this.processing) return;
    
    this.processing = true;
    
    const event = this.queue.shift();
    try {
      this.config.onProcess(event);
    } catch (error) {
      console.error(`Errore nel processamento dell'evento: ${error.message}`);
    }
    
    this.processing = false;
    
    // Se ci sono altri eventi, programmiamo il prossimo processo
    if (this.queue.length > 0) {
      setTimeout(() => this.process(), this.config.processInterval);
    }
  }

  processAll() {
    // Processiamo tutti gli eventi in coda
    const allEvents = [...this.queue];
    this.queue = [];
    
    allEvents.forEach(event => {
      try {
        this.config.onProcess(event);
      } catch (error) {
        console.error(`Errore nel processamento dell'evento: ${error.message}`);
      }
    });
  }

  size() {
    return this.queue.length;
  }

  clear() {
    this.queue = [];
  }
}

// Inizializzazione del sistema di heartbeat all'avvio della pagina
document.addEventListener('DOMContentLoaded', () => {
  // Creiamo un'istanza globale del sistema di heartbeat
  window.heartbeatSystem = new HeartbeatSystem({
    debug: true,
    onStatusChange: (newStatus, oldStatus) => {
      console.log(`Cambio stato connessione: ${oldStatus} -> ${newStatus}`);
      
      // Mostriamo notifica in caso di riconnessione
      if (newStatus === 'connected' && oldStatus === 'reconnecting') {
        showToast('Connessione ripristinata', 'La connessione al server è stata ripristinata.', 'success');
      } else if (newStatus === 'reconnecting') {
        showToast('Problemi di connessione', 'Tentativo di riconnessione in corso...', 'warning');
      } else if (newStatus === 'disconnected') {
        showToast('Disconnesso', 'La connessione al server è stata persa.', 'error');
      }
    }
  });
  
  // Registriamo un handler per la visualizzazione del grafico latenza
  const latencyButton = document.getElementById('show-latency-chart');
  if (latencyButton) {
    latencyButton.addEventListener('click', showLatencyChart);
  }
});

// Funzioni di utilità

function showLatencyChart() {
  if (!window.heartbeatSystem) return;
  
  const data = window.heartbeatSystem.getMonitoringData();
  
  // Qui possiamo implementare la visualizzazione del grafico
  // usando una libreria come Chart.js
  console.log('Dati di latenza:', data);
  
  // Mostriamo un modal con il grafico
  // ...
}

function showToast(title, message, type = 'info') {
  // Funzione da implementare nel sistema di UI
  if (window.showToastMessage) {
    window.showToastMessage(title, message, type);
  } else {
    // Implementazione base se non esiste quella globale
    console.log(`[${type}] ${title}: ${message}`);
  }
} 