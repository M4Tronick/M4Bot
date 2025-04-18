# M4Bot

## Panoramica

M4Bot è una soluzione completa e avanzata per la gestione dei bot per comunità, integrazioni multipiattaforma, e amministrazione di servizi. Progettato con un'architettura moderna, offre una varietà di funzionalità per gestire interazioni utente, automatizzazioni, e monitoraggio avanzato.

## Caratteristiche Principali

### Interfaccia Utente Avanzata
- **Design Reattivo Completo**: Esperienza utente ottimizzata su desktop, tablet e dispositivi mobili
- **Temi Dinamici**: Supporto per tema chiaro/scuro con rilevamento automatico delle preferenze di sistema
- **Glassmorphism e Neumorfismo**: Interfaccia moderna con effetti vetro e superfici tridimensionali
- **Dashboard Personalizzabile**: Widget drag-and-drop e layout salvabili per scenari diversi
- **Animazioni Fluide**: Microinterazioni e feedback visivi per una migliore esperienza utente
- **Supporto per Schermi ad Alta Risoluzione**: Ottimizzazione per display 4K e Retina

### Punti Canale e Sistema di Fedeltà
- **Sistema Punti Canale**: Implementazione completa di un sistema di punti canale simile a Twitch
- **Attività Recenti**: Visualizzazione delle attività recenti dei punti con caricamento automatico all'avvio della pagina
- **Riscatto Premi**: Sistema di riscatto premi personalizzabili con notifiche
- **Gestione Automatica**: Distribuzione automatica dei punti durante le trasmissioni
- **Cronologia Transazioni**: Registro completo di tutte le transazioni di punti
- **Sistema di Livelli**: Progressione basata sull'attività e la fedeltà degli utenti

### Sicurezza Avanzata (Admin Control)
- **Pannello di Controllo Amministrativo**: Gestione centralizzata della sicurezza e stabilità
- **Protezione DDoS**: Sistema avanzato di protezione contro attacchi distribuiti
- **Web Application Firewall (WAF)**: Protezione perimetrale contro attacchi comuni
- **Rilevamento Intrusioni**: Monitoraggio e notifica automatica di tentativi di accesso non autorizzati
- **Gestione Certificati SSL/TLS**: Rinnovo automatico e monitoraggio scadenze
- **Scanner di Vulnerabilità**: Identificazione e riparazione automatica di vulnerabilità
- **Backup Crittografati**: Sistema automatizzato di backup con crittografia end-to-end
- **Multi-Factor Authentication**: Protezione aggiuntiva per accessi amministrativi

### Stabilità e Continuità del Servizio
- **Aggiornamenti Zero-Downtime**: Implementazione di aggiornamenti senza interruzioni di servizio
- **Sistema di Rollback Automatico**: Ripristino automatico in caso di problemi con aggiornamenti
- **Health Check Avanzati**: Monitoraggio continuo dello stato dei servizi
- **Self-Healing System**: Riparazione automatica dei servizi critici
- **Load Balancing Intelligente**: Distribuzione ottimizzata del carico tra le istanze
- **Modalità Manutenzione Trasparente**: Manutenzione senza interruzione del servizio
- **Migrazione a Caldo del Database**: Aggiornamenti del database senza downtime

### Plugin e Funzionalità Innovative
- **Marketplace di Plugin**: Installazione e aggiornamento automatici di estensioni
- **Sistema di Automazioni Visuale**: Editor grafico per flussi di automazione complessi
- **Integrazione AI/ML**: Analisi del sentiment e generazione automatica di contenuti
- **Analisi Predittiva**: Previsione di tendenze basata sui dati storici
- **Terminal SSH Remoto**: Accesso sicuro da browser per amministrazione
- **Sistema di Notifiche Multi-canale**: Messaggistica tramite vari canali (app, Telegram, webhook)
- **API RESTful Completa**: Integrazione con servizi esterni attraverso API documentata

### Logging e Monitoring (Admin Control)
- **Dashboard di Monitoraggio in Tempo Reale**: Visualizzazione dettagliata dei parametri di sistema
- **Logging Strutturato**: Centralizzazione e categorizzazione avanzata dei log
- **Alerting Intelligente**: Notifiche con riduzione dei falsi positivi
- **Rotazione Automatica dei Log**: Gestione efficiente dello spazio disco
- **Metriche di Performance**: Monitoraggio dettagliato delle prestazioni
- **Analisi di Sicurezza**: Identificazione di pattern sospetti nei log

### Integrazione Webhook Kick.com
- **Notifiche in Tempo Reale**: Ricezione di eventi come inizio streaming, nuovi follower, iscrizioni
- **Azioni Automatiche**: Attivazione di comandi e messaggi in base agli eventi ricevuti
- **Integrazione OBS**: Visualizzazione automatica degli eventi nell'overlay OBS
- **Eventi Personalizzabili**: Selezione degli eventi specifici da ricevere e gestire
- **Sicurezza Webhook**: Verifica dell'autenticità delle richieste tramite firma HMAC

## Requisiti di Sistema

- Sistema operativo: Linux (Ubuntu 20.04 LTS o superiore raccomandato)
- RAM: 4GB minimo (8GB+ raccomandati)
- CPU: 2 core minimo (4+ raccomandati)
- Spazio disco: 20GB minimo
- Python 3.8+
- PostgreSQL 12+
- Redis 6+
- Nginx

## Installazione

### Installazione Standard

```bash
# Clona il repository
git clone https://github.com/yourusername/m4bot.git
cd m4bot

# Esegui lo script di installazione
sudo ./scripts/install.sh
```

Lo script di installazione configura automaticamente:
- Ambiente Python virtualenv
- Database PostgreSQL
- Server Redis
- Proxy Nginx
- Certificati SSL con Let's Encrypt
- Servizi systemd per avvio automatico

### Installazione con Docker

```bash
# Clona il repository
git clone https://github.com/yourusername/m4bot.git
cd m4bot

# Avvia con Docker Compose
docker-compose up -d
```

## Aggiornamento Zero-Downtime

M4Bot supporta aggiornamenti senza interruzioni del servizio:

```bash
# Aggiornamento con zero downtime
sudo ./scripts/update.sh --zero-downtime

# Aggiornamento con hotfix (solo correzioni critiche)
sudo ./scripts/update.sh --hotfix
```

## Configurazione

La configurazione principale si trova nel file `.env`. Per una configurazione avanzata, modifica i file nella directory `config/`.

```
# Esempio di configurazione .env
DB_HOST=localhost
DB_NAME=m4bot_db
DB_USER=m4bot_user
DB_PASSWORD=your_secure_password

REDIS_HOST=localhost
REDIS_PORT=6379

SECRET_KEY=your_very_secure_secret_key
```

## Installazione su VPS Linux

### 1. Preparazione dell'ambiente VPS

```bash
# Rendi eseguibili gli script
chmod +x scripts/convert_scripts.sh scripts/setup_vps.sh

# Esegui lo script di preparazione VPS
sudo ./scripts/setup_vps.sh
```

Questo script:
- Aggiorna il sistema
- Installa i pacchetti essenziali
- Converte i file per l'uso su Linux (corregge le terminazioni di riga e i permessi)
- Prepara l'ambiente Python con le dipendenze necessarie
- Configura Flask e Babel alle versioni più recenti
- Imposta i permessi corretti per le directory critiche
- Prepara l'ambiente per l'installazione principale

### 2. Esecuzione dell'installazione

```bash
sudo ./scripts/install.sh
```

### 3. Verifica dell'installazione

```bash
sudo ./scripts/status.sh
```

### Comandi utili per VPS

- Avviare i servizi: `sudo ./scripts/start.sh`
- Fermare i servizi: `sudo ./scripts/stop.sh`
- Riavviare i servizi: `sudo ./scripts/restart.sh`
- Controllare lo stato: `sudo ./scripts/status.sh`
- Ottimizzare il database: `sudo ./scripts/optimize_db.sh`
- Backup del sistema: `sudo ./scripts/backup.sh`

## Configurazione Webhook Kick.com

### 1. Requisiti

- Un account Kick.com con accesso API (client ID e client secret)
- M4Bot installato e configurato
- Un server pubblicamente accessibile con HTTPS per ricevere i webhook

### 2. Configurazione nel pannello M4Bot

1. Accedi al tuo account M4Bot
2. Vai su **Webhook** nel menu principale
3. Seleziona il canale per cui vuoi configurare i webhook
4. Inserisci l'URL dell'endpoint (senza https://)
5. Genera o inserisci una chiave segreta (serve a verificare l'autenticità delle richieste)
6. Seleziona gli eventi che vuoi ricevere
7. Clicca su "Salva Configurazione"

### 3. Eventi disponibili

| Evento | Descrizione | Payload |
|--------|-------------|---------|
| `livestream.online` | Lo streaming è iniziato | Dati del livestream |
| `livestream.offline` | Lo streaming è terminato | Dati finali dello streaming |
| `follower.new` | Nuovo follower | Dati del follower |
| `channel.updated` | Modifiche al canale | Dati aggiornati del canale |
| `chatroom.message` | Nuovo messaggio in chat | Contenuto del messaggio |
| `subscription.new` | Nuova iscrizione | Dati dell'abbonamento |

### 4. Integrazione con OBS

M4Bot può automaticamente mostrare eventi webhook nell'overlay OBS:

1. Vai nelle impostazioni del canale
2. Nella scheda "OBS Integration", abilita "Show webhook events in overlay"
3. Configura quali eventi mostrare e per quanto tempo
4. Usa l'URL generato come Browser Source in OBS

## Architettura

M4Bot è costruito con un'architettura modulare che comprende:

- **Core**: Gestione principale dell'applicazione e orchestrazione dei servizi
- **Web**: Interfaccia web con Flask/Quart e sistema di template
- **API**: Endpoints RESTful per integrazione con servizi esterni
- **Plugins**: Sistema estensibile di funzionalità aggiuntive
- **Security**: Moduli avanzati per sicurezza e stabilità
- **Services**: Componenti di servizio indipendenti

## Modifiche recenti

### Implementazione Sistema Punti Canale
- Aggiunta funzionalità di caricamento automatico dell'attività recente all'avvio della pagina
- Ottimizzazione della visualizzazione dell'attività dei punti canale
- Miglioramento della gestione delle transazioni e riscatti dei premi
- Sviluppo frontend per l'interfaccia utente dei punti canale
- Implementazione di chiamate AJAX per aggiornamenti in tempo reale

## Contribuire

Siamo felici di ricevere contributi! Per favore, segui questi passi:

1. Fai un fork del repository
2. Crea un branch per la tua funzionalità (`git checkout -b feature/amazing-feature`)
3. Fai commit delle tue modifiche (`git commit -m 'Add some amazing feature'`)
4. Push al branch (`git push origin feature/amazing-feature`)
5. Apri una Pull Request

## Licenza

Questo progetto è distribuito sotto la licenza MIT. Vedi il file `LICENSE` per maggiori informazioni.
