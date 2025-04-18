# Sistema di Monitoraggio M4Bot

## Panoramica

Il sistema di monitoraggio è un modulo avanzato integrato nel pannello di amministrazione di M4Bot che consente agli amministratori di:

- Monitorare in tempo reale le prestazioni del sistema (CPU, memoria, disco, rete)
- Visualizzare grafici di utilizzo delle risorse con storico
- Gestire i servizi M4Bot (stato, riavvio)
- Ricevere avvisi su problemi di sistema
- Monitorare le connessioni di rete
- Visualizzare le informazioni dettagliate sul sistema

## Componenti

Il sistema è composto da vari file che lavorano insieme:

### 1. Template HTML (`monitoring.html`)
- Dashboard responsive con interfaccia moderna
- Visualizzazione in tempo reale delle metriche di sistema
- Supporto per tema chiaro/scuro
- Grafici interattivi
- Sezioni per informazioni di sistema, avvisi, servizi, dischi e connessioni di rete

### 2. CSS (`monitoring.css`)
- Stile moderno con effetto glassmorphism
- Supporto per temi chiaro/scuro
- Design responsive per tutte le dimensioni di schermo
- Effetti di animazione per migliorare l'UX
- Stili specifici per grafici, metriche e tabelle

### 3. JavaScript (`monitoring.js`)
- Sistema di aggiornamento automatico configurabile
- Gestione dei grafici con Chart.js
- Gestione dinamica del DOM per aggiornare le metriche in tempo reale
- Funzionalità di interazione utente (riavvio servizi, filtro avvisi)
- Rilevamento automatico del tema
- Sistema di notifiche toast

### 4. Backend Python (`system_monitoring.py`)
- API RESTful per dati di sistema in tempo reale
- Integrazione con psutil per dati accurati di sistema
- Gestione sicura delle operazioni sensibili (riavvio servizi)
- Supporto per monitoraggio avanzato tramite autenticazione con decorator admin_required
- Modello dati strutturato per CPU, memoria, disco, rete e servizi

## Funzionalità

### Metriche in Tempo Reale
- Utilizzo CPU (%)
- Utilizzo Memoria (%)
- Utilizzo Disco (%)
- Attività di Rete (KB/s)

### Grafici di Utilizzo
- Grafico storico CPU
- Grafico storico Memoria
- Grafico attività di Rete

### Informazioni di Sistema
- Sistema operativo e versione
- Hostname e indirizzo IP
- Versione kernel
- Modello CPU e numero di core
- Memoria totale
- Uptime del sistema

### Gestione Servizi
- Elenco dei servizi M4Bot
- Stato di ogni servizio (attivo, arrestato, riavvio in corso)
- Utilizzo risorse per servizio (CPU, memoria)
- Funzionalità di riavvio

### Monitoraggio Disco
- Elenco delle partizioni
- Spazio usato e totale
- Percentuale di utilizzo
- Rappresentazione grafica

### Connessioni di Rete
- Connessioni attive
- Protocollo
- Indirizzi locali e remoti
- Stato della connessione

### Avvisi di Sistema
- Avvisi critici, warning e informativi
- Filtro per livello di gravità
- Sorgente e orario dell'avviso

## Integrazione

Il sistema di monitoraggio è completamente integrato con il pannello di amministrazione M4Bot e accessibile solo agli utenti amministratori. Si integra con:

- Sistema di autenticazione e autorizzazione
- Tema dell'interfaccia utente (chiaro/scuro)
- Modulo di stabilità e sicurezza
- Sistema di notifiche

## Note Tecniche

- Ottimizzazione delle prestazioni con limiti di aggiornamento configurabili
- Gestione della cache per ridurre il carico sul server
- Gestione degli errori robusta
- Compatibilità cross-platform (Linux/Windows)
- Responsive design per dispositivi mobile e desktop 