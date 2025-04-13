# Integrazione Webhook Kick.com in M4Bot

Questo documento spiega come configurare e utilizzare l'integrazione webhook con Kick.com in M4Bot.

## Panoramica

I webhook di Kick.com permettono a M4Bot di ricevere notifiche in tempo reale per eventi che accadono sul canale, come:
- Inizio/fine streaming
- Nuovi follower
- Nuove iscrizioni
- Messaggi in chat
- Aggiornamenti al canale

Questi eventi possono attivare automaticamente azioni nel bot, come messaggi personalizzati, comandi, o visualizzazioni nell'overlay OBS.

## Requisiti

- Un account Kick.com con accesso API (client ID e client secret)
- M4Bot installato e configurato
- Un server pubblicamente accessibile con HTTPS per ricevere i webhook (o tunnel come ngrok in sviluppo)

## Configurazione

### 1. Configurazione webhook sul tuo server

Per ricevere i webhook di Kick, il tuo server deve avere un endpoint pubblicamente accessibile via HTTPS.

L'endpoint predefinito è: `https://tuo-dominio.com/api/webhook/kick`

Se stai sviluppando localmente, puoi usare strumenti come [ngrok](https://ngrok.com/) per creare un tunnel:
```
ngrok http 8000
```

### 2. Configurazione nel pannello M4Bot

1. Accedi al tuo account M4Bot
2. Vai su **Webhook** nel menu principale
3. Seleziona il canale per cui vuoi configurare i webhook
4. Inserisci l'URL dell'endpoint (senza https://)
5. Genera o inserisci una chiave segreta (serve a verificare l'autenticità delle richieste)
6. Seleziona gli eventi che vuoi ricevere
7. Clicca su "Salva Configurazione"

### 3. Testing

Puoi testare la tua configurazione usando il pulsante "Test" nella pagina di gestione webhook. 
Questo invierà un evento di prova al tuo endpoint per verificare che funzioni correttamente.

## Eventi disponibili

| Evento | Descrizione | Payload |
|--------|-------------|---------|
| `livestream.online` | Lo streaming è iniziato | Dati del livestream |
| `livestream.offline` | Lo streaming è terminato | Dati finali dello streaming |
| `follower.new` | Nuovo follower | Dati del follower |
| `channel.updated` | Modifiche al canale | Dati aggiornati del canale |
| `chatroom.message` | Nuovo messaggio in chat | Contenuto del messaggio |
| `subscription.new` | Nuova iscrizione | Dati dell'abbonamento |

## Formato del Payload

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

## Integrazione con OBS

M4Bot può automaticamente mostrare eventi webhook nell'overlay OBS:

1. Vai nelle impostazioni del canale
2. Nella scheda "OBS Integration", abilita "Show webhook events in overlay"
3. Configura quali eventi mostrare e per quanto tempo
4. Usa l'URL generato come Browser Source in OBS

## Personalizzazione degli Handler

Se hai accesso al codice sorgente di M4Bot, puoi personalizzare gli handler degli eventi nei seguenti file:

- `web/app.py` - Funzioni `handle_stream_start()`, `handle_new_follower()`, etc.

## Sicurezza

- Non condividere mai la tua chiave segreta
- Verifica sempre la firma HMAC nei webhook in arrivo
- Limita gli IP che possono chiamare il tuo endpoint webhook (se possibile)
- Monitora regolarmente i log webhook per attività sospette

## Risoluzione dei problemi

Se i webhook non funzionano correttamente, verifica:

1. L'URL dell'endpoint è accessibile pubblicamente
2. Il tuo server è in grado di ricevere richieste HTTPS
3. La chiave segreta è configurata correttamente
4. Gli eventi desiderati sono abilitati
5. Controlla i log dell'applicazione per errori

## Risorse aggiuntive

- [Documentazione ufficiale Kick.com](https://docs.kick.com/)
- [Esempi di implementazione](https://docs.kick.com/events)
- [Guida alla sicurezza webhook](https://docs.kick.com/webhooks)

## Supporto

Per assistenza con l'integrazione webhook, contatta il supporto M4Bot o consulta il forum della community. 