# Changelog: Sistema di Rotazione Credenziali

## Versione 1.1.0 (Attuale)

### Miglioramenti all'API REST

- **Versionamento API**: Aggiunto prefisso `/api/v1` a tutti gli endpoint per una migliore organizzazione
- **Documentazione interattiva**: Aggiunta interfaccia Swagger disponibile su `/api/docs`
- **CORS supporto**: Aggiunto middleware CORS per consentire chiamate cross-origin
- **Verbi HTTP corretti**: 
  - Modificati da `POST` a `PUT` gli endpoint per operazioni idempotenti come la rotazione
  - Aggiunto `PATCH` per aggiornamenti parziali delle credenziali
  - Aggiunto `DELETE` per la rimozione delle credenziali
- **Maggiore coerenza nelle route**:
  - Endpoint rotazioni rinominati da `/pending` e `/upcoming` a `/rotations/pending` e `/rotations/upcoming`
- **Documentazione migliorata**:
  - Aggiunti tag per categorizzare gli endpoint
  - Descrizioni più complete per ogni endpoint
  - Esempi aggiunti ai modelli di dati
- **Gestione errori centralizzata**: 
  - Gestore eccezioni globale per risposte di errore coerenti
  - Formato standard delle risposte di errore
- **Modelli dati aggiornati**:
  - Aggiunto modello `CredentialUpdate` per aggiornamenti parziali
  - Aggiunti esempi nei modelli per la documentazione
- **Nuovo endpoint per l'aggiornamento**:
  - Aggiunto endpoint `PATCH /api/v1/credentials/{name}` per l'aggiornamento parziale

### Nuovi file e script

- **Documentazione API**: Aggiunto file `api/security/README.md` con documentazione dettagliata dell'API
- **Script di test**: Aggiunto script `scripts/test_credential_rotation_api.py` per testare tutti gli endpoint

## Versione 1.0.0

### Implementazione iniziale

- Sistema di rotazione automatica delle credenziali
- Backup cifrato delle credenziali
- API REST per la gestione delle credenziali
- Servizio per l'esecuzione automatica delle rotazioni
- Script di inizializzazione per generare i valori iniziali 