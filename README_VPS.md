# Installazione di M4Bot su VPS Linux

Questa guida descrive come installare e configurare M4Bot su una VPS Linux.

## Requisiti
- VPS Linux con Ubuntu 20.04 o superiore
- Accesso root o utente con privilegi sudo
- Almeno 2GB di RAM e 10GB di spazio su disco
- Un nome di dominio (opzionale, ma consigliato per SSL)

## Procedura di installazione

### 1. Clona il repository

```bash
git clone https://github.com/username/M4Bot.git
cd M4Bot
```

### 2. Prepara l'ambiente VPS

Prima di eseguire lo script di installazione principale, è necessario preparare l'ambiente della VPS:

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

### 3. Esegui l'installazione

Dopo la preparazione, esegui lo script di installazione principale:

```bash
sudo ./scripts/install.sh
```

Segui le istruzioni a schermo per completare la configurazione.

### 4. Verifica l'installazione

Dopo l'installazione, verifica che tutto funzioni correttamente:

```bash
sudo ./scripts/status.sh
```

## Configurazione di Flask e Babel

M4Bot utilizza le versioni più recenti di Flask (2.3+) e Flask-Babel (4.0+) per supportare al meglio l'ambiente VPS Linux. Il modulo di compatibilità `babel_compat.py` assicura che le traduzioni funzionino correttamente anche con l'uso di framework asincroni come Quart.

Se riscontri problemi con le traduzioni, puoi rigenerare i file di traduzione con:

```bash
cd web
pybabel extract -F babel.cfg -o messages.pot .
pybabel update -i messages.pot -d translations
pybabel compile -d translations
```

## Risoluzione dei problemi

Se riscontri problemi con l'esecuzione degli script, prova a:

1. Assicurarti che gli script abbiano i permessi di esecuzione:
   ```bash
   find scripts -type f -name "*.sh" -exec chmod +x {} \;
   ```

2. Correggere manualmente le terminazioni di riga:
   ```bash
   find scripts -type f -name "*.sh" -exec dos2unix {} \;
   ```

3. Se hai problemi con Flask o Babel, reinstalla manualmente:
   ```bash
   source venv/bin/activate
   pip install --upgrade flask flask-babel Babel
   ```

4. Controlla eventuali errori nei log:
   ```bash
   ./scripts/diagnose.sh
   ```

## Comandi utili

- Avviare i servizi: `sudo ./scripts/start.sh`
- Fermare i servizi: `sudo ./scripts/stop.sh`
- Riavviare i servizi: `sudo ./scripts/restart.sh`
- Controllare lo stato: `sudo ./scripts/status.sh`
- Ottimizzare il database: `sudo ./scripts/optimize_db.sh`
- Backup del sistema: `sudo ./scripts/backup.sh`

## Aggiornamenti

Per aggiornare M4Bot:

```bash
git pull
sudo ./scripts/update_env.sh
sudo ./scripts/restart.sh
``` 