# Sistema di Rotazione Automatica delle Credenziali per M4Bot

Questo modulo implementa un sistema avanzato per la rotazione automatica e sicura delle credenziali utilizzate da M4Bot (API keys, token, password del database, ecc.).

## Funzionalità

- **Rotazione periodica programmabile**: rotazione automatica delle credenziali in base a diverse pianificazioni (giornaliera, settimanale, mensile, trimestrale o personalizzata)
- **Backup sicuro e cifrato**: ogni credenziale viene salvata con cifratura prima di essere modificata
- **Notifiche automatiche**: avvisi prima della rotazione delle credenziali
- **Sistema di rollback**: possibilità di ripristinare credenziali precedenti in caso di problemi
- **API REST**: interfaccia HTTP completa per gestire la rotazione delle credenziali
- **Servizio dedicato**: un servizio che esegue automaticamente le rotazioni programmate

## Struttura

Il sistema è composto dai seguenti componenti:

- **Modulo principale**: `security/credential_rotation.py`
- **File di configurazione**: `config/security/credential_rotation.json`
- **Directory di backup**: `security/backups/credentials/`
- **Script di inizializzazione**: `scripts/initialize_credentials.py`
- **Servizio di rotazione**: `services/credential_rotation_service.py`
- **API REST**: `api/security/credential_rotation_api.py`
- **Documentazione API**: `api/security/README.md`

## Utilizzo

### 1. Inizializzazione

Per inizializzare il sistema e generare i valori iniziali per le credenziali:

```bash
python scripts/initialize_credentials.py
```

Opzioni:
- `--config`: percorso del file di configurazione (default: `config/security/credential_rotation.json`)
- `--no-backup`: non creare backup delle credenziali

### 2. Servizio di rotazione

Per avviare il servizio che esegue automaticamente le rotazioni programmate:

```bash
python services/credential_rotation_service.py
```

Opzioni:
- `--config`: percorso del file di configurazione
- `--run-once`: esegui una singola rotazione e termina
- `--notify-only`: controlla solo le notifiche senza eseguire rotazioni

### 3. API REST

Per avviare il server API:

```bash
python api/security/credential_rotation_api.py
```

Il server API sarà disponibile con la seguente struttura:

- **URL base**: `http://localhost:8080/api/v1`
- **Documentazione interattiva**: `http://localhost:8080/api/docs`

#### Autenticazione

Tutte le richieste API richiedono un token di autenticazione nell'header:

```
Authorization: Bearer YOUR_TOKEN
```

Il token predefinito è `test-token` o può essere configurato tramite la variabile d'ambiente `CREDENTIAL_API_TOKEN`.

#### Endpoint principali

- **Stato del servizio**: `GET /api/v1/health`
- **Gestione credenziali**:
  - Lista credenziali: `GET /api/v1/credentials`
  - Dettagli credenziale: `GET /api/v1/credentials/{name}`
  - Creazione: `POST /api/v1/credentials`
  - Aggiornamento: `PATCH /api/v1/credentials/{name}`
  - Eliminazione: `DELETE /api/v1/credentials/{name}`
- **Operazioni di rotazione**:
  - Rotazione manuale: `PUT /api/v1/credentials/{name}/rotate`
  - Rollback: `PUT /api/v1/credentials/{name}/rollback`
  - Rotazione di tutte le credenziali in attesa: `PUT /api/v1/rotations/pending`
  - Lista credenziali in attesa: `GET /api/v1/rotations/pending`
  - Lista credenziali con rotazione imminente: `GET /api/v1/rotations/upcoming`

Per la documentazione completa dell'API, consultare il file `api/security/README.md`.

### 4. Utilizzo da riga di comando

Il modulo principale può essere utilizzato anche da riga di comando:

```bash
python security/credential_rotation.py --check
python security/credential_rotation.py --rotate db_password
python security/credential_rotation.py --status
```

## Configurazione

Il file di configurazione `config/security/credential_rotation.json` contiene:

- `enabled`: attiva/disattiva il sistema di rotazione
- `notification_days_before`: giorni di anticipo per le notifiche
- `backup_dir`: directory per i backup delle credenziali
- `backup_retention_days`: giorni di conservazione dei backup
- `encryption_key_env_var`: variabile d'ambiente per la chiave di cifratura
- `credentials`: elenco delle credenziali registrate

Esempio di configurazione:

```json
{
  "enabled": true,
  "notification_days_before": 3,
  "backup_dir": "security/backups/credentials",
  "backup_retention_days": 90,
  "encryption_key_env_var": "CREDENTIAL_BACKUP_KEY",
  "credentials": {
    "db_password": {
      "name": "db_password",
      "type": "db_password",
      "service": "database",
      "rotation_schedule": "monthly",
      "custom_interval_days": null,
      "next_rotation": "2025-05-21T19:38:00.000Z",
      "last_rotation": null,
      "description": "Password del database principale di M4Bot",
      "has_custom_function": false
    }
  }
}
```

## Tipi di credenziali supportati

- `api_key`: chiavi API (es. OpenAI, Twitch)
- `db_password`: password del database
- `jwt_secret`: segreti JWT
- `encryption_key`: chiavi di cifratura
- `access_token`: token di accesso
- `refresh_token`: token di aggiornamento
- `ssh_key`: chiavi SSH
- `service_account`: account di servizio
- `webhook_secret`: segreti per i webhook

## Frequenze di rotazione supportate

- `daily`: ogni giorno
- `weekly`: ogni settimana
- `monthly`: ogni mese (approssimato a 30 giorni)
- `quarterly`: ogni trimestre (90 giorni)
- `custom`: intervallo personalizzato in giorni

## Note sulla sicurezza

- Le credenziali vengono cifrate prima di essere salvate
- La chiave di cifratura viene memorizzata nell'ambiente o in un file protetto
- I backup hanno una durata limitata e vengono eliminati automaticamente
- Il sistema di notifiche avvisa prima delle rotazioni programmate
- L'API REST utilizza autenticazione tramite token

## Integrazione con altri sistemi

Il sistema di rotazione delle credenziali può essere integrato con:

- **Database**: aggiornamento automatico delle credenziali nel database
- **Servizi esterni**: API keys per servizi di terze parti
- **Sistemi di notifica**: invio di avvisi tramite email, Slack, ecc.
- **Dashboard di monitoraggio**: visualizzazione dello stato delle credenziali
- **Pipeline CI/CD**: automazione della rotazione durante i deployment
- **Sistemi di orchestrazione**: integrazione con Kubernetes, Docker Swarm, ecc. 