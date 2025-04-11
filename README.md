# M4Bot - Bot per Kick.com

M4Bot è un bot completo e personalizzabile per la piattaforma di streaming Kick.com. Offre funzionalità avanzate per la gestione della chat, comandi personalizzati, giochi interattivi, sistema di punti e molto altro.

## Caratteristiche principali

- **Comandi personalizzati**: Crea e gestisci comandi con risposte dinamiche e cooldown
- **Giochi in chat**: Intrattieni il tuo pubblico con giochi come dadi, trivia e altro
- **Moderazione**: Strumenti per mantenere la chat pulita e gestire gli utenti
- **Sistema di punti**: Premia gli spettatori con un sistema di punti personalizzabile
- **Dashboard web**: Interfaccia intuitiva per la gestione del bot
- **Integrazione con OBS**: Connetti il bot al tuo software di streaming
- **Statistiche dettagliate**: Analizza l'attività della tua chat
- **Sicurezza avanzata**: Protezione dei dati sensibili e delle API keys

## Requisiti di sistema

- Ubuntu 20.04 LTS o superiore
- Python 3.8 o superiore
- PostgreSQL 12 o superiore
- Nginx
- Certificato SSL (generato con Let's Encrypt)

## Installazione

### Installazione automatica

Il modo più semplice per installare M4Bot è utilizzare lo script di installazione automatica:

```bash
wget https://m4bot.it/install.sh
chmod +x install.sh
sudo ./install.sh
```

### Installazione manuale

1. Clona il repository:

```bash
git clone https://github.com/yourusername/m4bot.git
cd m4bot
```

2. Esegui lo script di installazione:

```bash
cd scripts
chmod +x install.sh
sudo ./install.sh
```

3. Avvia il bot:

```bash
sudo m4bot-start
```

## Utilizzo

### Dashboard Web

Accedi alla dashboard web all'indirizzo `https://m4bot.it` (o all'indirizzo del tuo server). Da qui puoi:

1. Registrare un account
2. Connettere il tuo canale Kick.com
3. Configurare comandi personalizzati
4. Gestire giochi e impostazioni
5. Visualizzare statistiche

### Comandi del bot

M4Bot supporta diversi comandi predefiniti:

- `!help` - Mostra un elenco di comandi disponibili
- `!points` - Mostra i punti dell'utente
- `!top` - Mostra la classifica dei punti
- `!game` - Avvia un gioco in chat
- `!commands` - Mostra tutti i comandi personalizzati

### Gestione via CLI

Sono disponibili anche comandi da terminale per gestire il bot:

- `sudo m4bot-start` - Avvia tutti i servizi di M4Bot
- `sudo m4bot-stop` - Ferma tutti i servizi di M4Bot
- `sudo m4bot-status` - Controlla lo stato di M4Bot

## Configurazione

La configurazione principale si trova nel file `config.py`. Puoi modificare:

- Credenziali OAuth di Kick.com
- Impostazioni del database
- Configurazione del server web
- Cooldown predefiniti
- Impostazioni di logging

## Integrazione con Kick.com

M4Bot si integra con Kick.com tramite OAuth 2.0. Quando aggiungi un canale tramite la dashboard web, verrai reindirizzato a Kick.com per autorizzare il bot.

## Supporto

Per assistenza o segnalazioni di bug, puoi:

- Aprire un issue su GitHub
- Contattare il supporto a support@m4bot.it
- Visitare il canale Discord ufficiale: [discord.gg/m4bot](https://discord.gg/m4bot)

## Licenza

M4Bot è distribuito con licenza MIT. Consulta il file LICENSE per ulteriori dettagli.

## Contributi

I contributi sono benvenuti! Consulta CONTRIBUTING.md per le linee guida.

## Ringraziamenti

- [sub20hz/kickbot](https://github.com/sub20hz/kickbot) - Per l'ispirazione e alcune implementazioni di riferimento
- [cibere/kick.py](https://github.com/cibere/kick.py) - Per l'implementazione dell'API wrapper
- Tutti i contributori e tester che hanno reso possibile questo progetto
