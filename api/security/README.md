# API REST per la Rotazione delle Credenziali

Questa API fornisce endpoint per gestire la rotazione automatica e sicura delle credenziali in M4Bot.

## Informazioni Generali

- **Base URL**: `http://localhost:8080/api/v1`
- **Versione**: 1.0.0
- **Documentazione Swagger**: `http://localhost:8080/api/docs`

## Autenticazione

Tutte le richieste API richiedono un token di autenticazione nell'header:

```
Authorization: Bearer YOUR_TOKEN
```

Il token predefinito è `test-token` o può essere configurato tramite la variabile d'ambiente `CREDENTIAL_API_TOKEN`.

## Endpoint

### Stato del Servizio

- **GET `/api/v1/health`**
  - Verifica lo stato del servizio API
  - Non richiede autenticazione
  - Risposta: `{"status": "ok", "service": "credential-rotation-api", "version": "1.0.0"}`

### Gestione Credenziali

- **GET `/api/v1/credentials`**
  - Elenca tutte le credenziali registrate nel sistema
  - Richiede autenticazione
  - Risposta: Array di oggetti `CredentialResponse`

- **GET `/api/v1/credentials/{name}`**
  - Ottiene i dettagli di una credenziale specifica
  - Richiede autenticazione
  - Parametri path:
    - `name`: Nome della credenziale
  - Risposta: Oggetto `CredentialResponse`

- **POST `/api/v1/credentials`**
  - Registra una nuova credenziale
  - Richiede autenticazione
  - Body: Oggetto `CredentialCreate`
  - Risposta: Oggetto `RotationResponse`

- **PATCH `/api/v1/credentials/{name}`**
  - Aggiorna una credenziale esistente
  - Richiede autenticazione
  - Parametri path:
    - `name`: Nome della credenziale
  - Body: Oggetto `CredentialUpdate`
  - Risposta: Oggetto `CredentialResponse`

- **DELETE `/api/v1/credentials/{name}`**
  - Elimina una credenziale
  - Richiede autenticazione
  - Parametri path:
    - `name`: Nome della credenziale
  - Risposta: 204 No Content

### Operazioni di Rotazione

- **PUT `/api/v1/credentials/{name}/rotate`**
  - Ruota manualmente una credenziale
  - Richiede autenticazione
  - Parametri path:
    - `name`: Nome della credenziale
  - Risposta: Oggetto `RotationResponse`

- **PUT `/api/v1/credentials/{name}/rollback`**
  - Ripristina una credenziale a un valore precedente
  - Richiede autenticazione
  - Parametri path:
    - `name`: Nome della credenziale
  - Parametri query:
    - `timestamp` (opzionale): Timestamp specifico del backup
  - Risposta: Oggetto `RotationResponse`

- **PUT `/api/v1/rotations/pending`**
  - Ruota tutte le credenziali in attesa
  - Richiede autenticazione
  - Risposta: Array di oggetti `RotationResponse`

- **GET `/api/v1/rotations/pending`**
  - Elenca le credenziali in attesa di rotazione
  - Richiede autenticazione
  - Risposta: Array di oggetti con informazioni sulle credenziali in attesa

- **GET `/api/v1/rotations/upcoming`**
  - Elenca le credenziali con rotazione imminente
  - Richiede autenticazione
  - Parametri query:
    - `days`: Numero di giorni da considerare (default: 7)
  - Risposta: Array di oggetti con informazioni sulle credenziali con rotazione imminente

## Modelli di Dati

### CredentialBase

```json
{
  "name": "string",
  "type": "string",
  "service": "string",
  "description": "string"
}
```

### CredentialCreate

```json
{
  "name": "string",
  "type": "string",
  "service": "string",
  "description": "string",
  "value": "string",
  "rotation_schedule": "string",
  "custom_interval_days": "integer"
}
```

### CredentialUpdate

```json
{
  "type": "string",
  "service": "string",
  "description": "string",
  "rotation_schedule": "string",
  "custom_interval_days": "integer"
}
```

### CredentialResponse

```json
{
  "name": "string",
  "type": "string",
  "service": "string",
  "description": "string",
  "last_rotation": "string",
  "next_rotation": "string",
  "days_to_rotation": "integer"
}
```

### RotationResponse

```json
{
  "success": "boolean",
  "message": "string",
  "credential_name": "string",
  "service": "string",
  "next_rotation": "string"
}
```

## Tipi di Credenziali Supportati

- `api_key`: Chiavi API (es. OpenAI, Twitch)
- `db_password`: Password del database
- `jwt_secret`: Segreti JWT
- `encryption_key`: Chiavi di cifratura
- `access_token`: Token di accesso
- `refresh_token`: Token di aggiornamento
- `ssh_key`: Chiavi SSH
- `service_account`: Account di servizio
- `webhook_secret`: Segreti per i webhook

## Frequenze di Rotazione Supportate

- `daily`: Ogni giorno
- `weekly`: Ogni settimana
- `monthly`: Ogni mese (approssimato a 30 giorni)
- `quarterly`: Ogni trimestre (90 giorni)
- `custom`: Intervallo personalizzato in giorni (richiede `custom_interval_days`)

## Esempi di Utilizzo

### Registrare una nuova credenziale

```bash
curl -X POST http://localhost:8080/api/v1/credentials \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "api_key_example",
    "type": "api_key",
    "service": "example_service",
    "description": "API key di esempio",
    "value": "abcdef1234567890",
    "rotation_schedule": "monthly"
  }'
```

### Ruotare una credenziale

```bash
curl -X PUT http://localhost:8080/api/v1/credentials/api_key_example/rotate \
  -H "Authorization: Bearer test-token"
```

### Elencare le credenziali in attesa di rotazione

```bash
curl -X GET http://localhost:8080/api/v1/rotations/pending \
  -H "Authorization: Bearer test-token"
```

## Gestione Errori

L'API restituisce risposte di errore standardizzate nei seguenti formati:

### Errore 4xx (Errore client)

```json
{
  "detail": "Messaggio di errore specifico",
  "status_code": 400,
  "path": "/api/v1/path/che/ha/generato/errore"
}
```

### Errore 5xx (Errore server)

```json
{
  "detail": "Errore interno del server",
  "status_code": 500,
  "path": "/api/v1/path/che/ha/generato/errore"
}
```

## Integrazione con Altri Sistemi

L'API può essere integrata con:

- **Dashboard di monitoraggio**: Per visualizzare lo stato delle credenziali
- **Sistemi CI/CD**: Per automatizzare la rotazione durante i deployment
- **Script di automazione**: Per gestire le credenziali da script personalizzati 