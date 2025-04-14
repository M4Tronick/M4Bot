# M4Bot - Bot per Kick.com

M4Bot è un bot completo e personalizzabile per la piattaforma Kick.com che permette agli streamer di migliorare l'esperienza della loro chat con comandi personalizzati, giochi interattivi, moderazione e statistiche avanzate.

## Caratteristiche Principali

- **Comandi Personalizzati**: Crea e gestisci comandi personalizzati con cooldown, permessi e risposte dinamiche
- **Giochi in Chat**: Intrattieni i tuoi spettatori con giochi interattivi come dadi, trivia, slot e altro
- **Moderazione**: Mantieni la tua chat pulita con strumenti di moderazione automatici e filtri personalizzabili
- **Sistema di Punti**: Premia i tuoi spettatori con un sistema di punti personalizzato e classifiche competitive
- **Statistiche**: Analizza l'attività della tua chat con statistiche dettagliate e report personalizzati
- **Integrazioni**: Collega il tuo bot con OBS e altri strumenti per migliorare la tua esperienza di streaming
- **Webhook**: Ricevi notifiche in tempo reale per eventi come inizio streaming, nuovi follower e iscrizioni

## Requisiti di Sistema

- Ubuntu 20.04 LTS o superiore
- Python 3.10 o superiore
- PostgreSQL 12 o superiore
- Nginx
- Certificato SSL (opzionale ma consigliato per produzione)

## Installazione

### Installazione automatica

Il modo più semplice per installare M4Bot è utilizzare lo script di installazione automatico:

```bash
# Clona il repository
git clone https://github.com/username/M4Bot.git
cd M4Bot/scripts

# Esegui lo script di installazione
sudo ./install.sh
```

Lo script di installazione configurerà automaticamente:
- Le dipendenze di sistema
- Il database PostgreSQL
- Il server web Nginx
- I certificati SSL (opzionale)
- I servizi systemd
- L'ambiente Python
- I file di configurazione

### Installazione manuale

Se preferisci un'installazione manuale, segui questi passaggi:

1. **Installa le dipendenze**:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip python3-venv nginx postgresql certbot python3-certbot-nginx git supervisor
   ```

2. **Crea l'utente di sistema**:
   ```bash
   sudo useradd -m -s /bin/bash m4bot
   ```

3. **Configura PostgreSQL**:
   ```bash
   sudo -u postgres psql -c "CREATE USER m4bot_user WITH PASSWORD 'password';"
   sudo -u postgres psql -c "CREATE DATABASE m4bot_db OWNER m4bot_user;"
   ```

4. **Configura le directory**:
   ```bash
   sudo mkdir -p /opt/m4bot/bot /opt/m4bot/web /opt/m4bot/bot/logs
   sudo chown -R m4bot:m4bot /opt/m4bot
   ```

5. **Configura l'ambiente Python**:
   ```bash
   cd /opt/m4bot
   python3 -m venv venv
   source venv/bin/activate
   pip install --upgrade pip
   pip install flask flask-babel==2.0.0 quart gunicorn python-dotenv jinja2 pyyaml
   pip install aiohttp asyncpg websockets requests pyyaml python-dotenv cryptography bcrypt
   ```

## Configurazione

### File di configurazione

Il file di configurazione principale è `.env` nella directory principale di M4Bot:

```bash
# Configurazione database
DB_USER=m4bot_user
DB_PASSWORD=password_sicura
DB_NAME=m4bot_db
DB_HOST=localhost

# Configurazione dominio
DOMAIN=m4bot.it
WEB_DOMAIN=m4bot.it
WEB_HOST=0.0.0.0
WEB_PORT=5000

# Chiavi e segreti
SECRET_KEY=chiave_segreta
ENCRYPTION_KEY=chiave_crittografia
CLIENT_ID=id_client_kick
CLIENT_SECRET=secret_client_kick
REDIRECT_URI=https://m4bot.it/auth/callback

# Configurazione log
LOG_LEVEL=INFO
LOG_FILE=/opt/m4bot/bot/logs/m4bot.log
```

## Comandi di gestione

M4Bot include alcuni comandi di gestione per controllare facilmente i servizi:

- `m4bot-start`: Avvia i servizi di M4Bot
- `m4bot-stop`: Ferma i servizi di M4Bot
- `m4bot-restart`: Riavvia i servizi di M4Bot
- `m4bot-status`: Controlla lo stato dei servizi di M4Bot

## Struttura del progetto

```
M4Bot/
├── bot/              # Core del bot
│   ├── m4bot.py      # Punto di ingresso del bot
│   ├── config.py     # Configurazione
│   ├── requirements.txt
│   └── ...
├── web/              # Interfaccia web
│   ├── app.py        # Applicazione Flask
│   ├── templates/    # Template HTML
│   ├── static/       # File statici (CSS, JS, immagini)
│   └── ...
└── scripts/          # Script di gestione
    ├── install.sh    # Script di installazione
    ├── common.sh     # Funzioni comuni
    ├── start.sh      # Avvio dei servizi
    ├── stop.sh       # Arresto dei servizi
    └── ...
```

## Integrazione Webhook Kick.com

### Panoramica

I webhook di Kick.com permettono a M4Bot di ricevere notifiche in tempo reale per eventi che accadono sul canale, come:
- Inizio/fine streaming
- Nuovi follower
- Nuove iscrizioni
- Messaggi in chat
- Aggiornamenti al canale

Questi eventi possono attivare automaticamente azioni nel bot, come messaggi personalizzati, comandi, o visualizzazioni nell'overlay OBS.

### Requisiti

- Un account Kick.com con accesso API (client ID e client secret)
- M4Bot installato e configurato
- Un server pubblicamente accessibile con HTTPS per ricevere i webhook (o tunnel come ngrok in sviluppo)

### Configurazione

#### 1. Configurazione webhook sul tuo server

Per ricevere i webhook di Kick, il tuo server deve avere un endpoint pubblicamente accessibile via HTTPS.

L'endpoint predefinito è: `https://tuo-dominio.com/api/webhook/kick`

Se stai sviluppando localmente, puoi usare strumenti come [ngrok](https://ngrok.com/) per creare un tunnel:
```
ngrok http 8000
```

#### 2. Configurazione nel pannello M4Bot

1. Accedi al tuo account M4Bot
2. Vai su **Webhook** nel menu principale
3. Seleziona il canale per cui vuoi configurare i webhook
4. Inserisci l'URL dell'endpoint (senza https://)
5. Genera o inserisci una chiave segreta (serve a verificare l'autenticità delle richieste)
6. Seleziona gli eventi che vuoi ricevere
7. Clicca su "Salva Configurazione"

#### 3. Testing

Puoi testare la tua configurazione usando il pulsante "Test" nella pagina di gestione webhook. 
Questo invierà un evento di prova al tuo endpoint per verificare che funzioni correttamente.

### Eventi disponibili

| Evento | Descrizione | Payload |
|--------|-------------|---------|
| `livestream.online` | Lo streaming è iniziato | Dati del livestream |
| `livestream.offline` | Lo streaming è terminato | Dati finali dello streaming |
| `follower.new` | Nuovo follower | Dati del follower |
| `channel.updated` | Modifiche al canale | Dati aggiornati del canale |
| `chatroom.message` | Nuovo messaggio in chat | Contenuto del messaggio |
| `subscription.new` | Nuova iscrizione | Dati dell'abbonamento |

### Formato del Payload

Ogni evento ha un formato di payload specifico, ma in generale tutti seguono questa struttura base:

```json
{
  "event_type": "nome.evento",
  "channel_id": "123456",
  "timestamp": "2023-06-15T12:34:56Z",
  "data": {
    // Dati specifici dell'evento
  }
}
```

### Esempi di Payload

#### Streaming iniziato

```json
{
  "event_type": "livestream.online",
  "channel_id": "123456",
  "timestamp": "2023-06-15T12:34:56Z",
  "data": {
    "stream_id": "789012",
    "title": "Titolo dello streaming",
    "started_at": "2023-06-15T12:34:56Z",
    "category": {
      "id": "12345",
      "name": "Just Chatting"
    }
  }
}
```

#### Nuovo follower

```json
{
  "event_type": "follower.new",
  "channel_id": "123456",
  "timestamp": "2023-06-15T12:34:56Z",
  "data": {
    "follower": {
      "id": "789012",
      "username": "nuovo_follower",
      "display_name": "Nuovo Follower",
      "followed_at": "2023-06-15T12:34:56Z"
    }
  }
}
```

### Integrazione con OBS

M4Bot può automaticamente mostrare eventi webhook nell'overlay OBS:

1. Vai nelle impostazioni del canale
2. Nella scheda "OBS Integration", abilita "Show webhook events in overlay"
3. Configura quali eventi mostrare e per quanto tempo
4. Usa l'URL generato come Browser Source in OBS

### Personalizzazione degli Handler

Se hai accesso al codice sorgente di M4Bot, puoi personalizzare gli handler degli eventi nei seguenti file:

- `web/app.py` - Funzioni `handle_stream_start()`, `handle_new_follower()`, etc.

### Sicurezza

- Non condividere mai la tua chiave segreta
- Verifica sempre la firma HMAC nei webhook in arrivo
- Limita gli IP che possono chiamare il tuo endpoint webhook (se possibile)
- Monitora regolarmente i log webhook per attività sospette

## Risoluzione dei problemi

### Servizio web non si avvia

Se il servizio web non si avvia, controlla:

1. **Error di compatibilità di Flask-Babel**:
   ```bash
   # Installa la versione corretta di Flask-Babel
   source /opt/m4bot/venv/bin/activate
   pip install flask-babel==2.0.0
   ```

2. **Errori nei log**:
   ```bash
   sudo journalctl -u m4bot-web.service -n 50
   ```

### Servizio bot non si avvia

Se il servizio bot non si avvia, controlla:

1. **Problemi con l'event loop**:
   ```bash
   # Controlla i log del bot
   sudo journalctl -u m4bot-bot.service -n 50
   ```

2. **Verifica il file .env**:
   ```bash
   # Assicurati che tutte le variabili necessarie siano presenti
   sudo nano /opt/m4bot/.env
   ```

### Directory di log mancanti

Se ricevi errori relativi alla directory di log:

```bash
sudo mkdir -p /opt/m4bot/bot/logs
sudo chown -R m4bot:m4bot /opt/m4bot/bot/logs
```

### Problemi con webhook

Se i webhook non funzionano correttamente, verifica:

1. L'URL dell'endpoint è accessibile pubblicamente
2. Il tuo server è in grado di ricevere richieste HTTPS
3. La chiave segreta è configurata correttamente
4. Gli eventi desiderati sono abilitati
5. Controlla i log dell'applicazione per errori

## Manutenzione del server

Per mantenere il server in condizioni ottimali, sono stati aggiunti degli script di manutenzione:

### Backup automatico

Lo script `backup.sh` crea backup giornalieri del database e dei file di configurazione:

```bash
sudo /opt/m4bot/scripts/backup.sh
```

Per automatizzare il backup, aggiungilo al crontab:
```bash
sudo crontab -e
# Aggiungi questa riga per un backup giornaliero alle 2:00
0 2 * * * /opt/m4bot/scripts/backup.sh
```

### Sicurezza del server

Lo script `secure.sh` configura il server con le migliori pratiche di sicurezza:

```bash
sudo /opt/m4bot/scripts/secure.sh
```

Questo script configura:
- Firewall UFW
- Fail2ban per prevenire attacchi brute force
- Hardening SSL/TLS
- Protezione DDoS di base

### Monitoraggio

Lo script `monitor.sh` monitora lo stato del server e dei servizi:

```bash
sudo /opt/m4bot/scripts/monitor.sh
```

Per monitoraggio continuo, impostalo come cron job:
```bash
sudo crontab -e
# Aggiungi questa riga per eseguire il monitoraggio ogni 10 minuti
*/10 * * * * /opt/m4bot/scripts/monitor.sh > /var/log/m4bot_monitor.log 2>&1
```

### Ottimizzazione del database

Lo script `optimize_db.sh` esegue la manutenzione del database PostgreSQL:

```bash
sudo /opt/m4bot/scripts/optimize_db.sh
```

Per automatizzare, impostalo come cron job settimanale:
```bash
sudo crontab -e
# Aggiungi questa riga per eseguire l'ottimizzazione ogni domenica alle 3:00
0 3 * * 0 /opt/m4bot/scripts/optimize_db.sh
```

## Ottimizzazione delle prestazioni

### Riduzione dell'uso di memoria

Se la VPS ha risorse limitate, puoi ottimizzare M4Bot:

1. **Configura PostgreSQL per basso consumo di memoria**:
   ```bash
   sudo nano /etc/postgresql/12/main/postgresql.conf
   ```
   
   Modifica questi parametri:
   ```
   shared_buffers = 128MB
   work_mem = 4MB
   maintenance_work_mem = 32MB
   ```

2. **Riduci i worker di Nginx**:
   ```bash
   sudo nano /etc/nginx/nginx.conf
   ```
   
   Modifica questi parametri:
   ```
   worker_processes 2;
   worker_connections 512;
   ```

3. **Limita i worker dell'app web**:
   Per ridurre l'uso di memoria dell'app web, modifica il servizio systemd:
   ```bash
   sudo nano /etc/systemd/system/m4bot-web.service
   ```
   
   Modifica la riga `ExecStart` se usi gunicorn:
   ```
   ExecStart=/opt/m4bot/venv/bin/gunicorn -w 2 -b 127.0.0.1:5000 app:app
   ```

## Accesso all'interfaccia web

Dopo l'installazione, puoi accedere all'interfaccia web tramite:

```
https://tuo-dominio.it
```

Credenziali di default:
- Username: admin
- Password: admin123

**IMPORTANTE**: Cambia la password dell'amministratore dopo il primo accesso.

## Risorse aggiuntive

- [Documentazione ufficiale Kick.com](https://docs.kick.com/)
- [Esempi di implementazione](https://docs.kick.com/events)
- [Guida alla sicurezza webhook](https://docs.kick.com/webhooks)

## Licenza

M4Bot è rilasciato sotto licenza MIT.

## Supporto

Per assistenza, contatta il supporto all'indirizzo support@m4bot.it o apri un issue sulla repository GitHub.
