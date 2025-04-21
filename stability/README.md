# Moduli di Stabilità M4Bot

Questo pacchetto contiene i moduli per garantire la stabilità, l'auto-guarigione e il monitoraggio del sistema M4Bot.

## Componenti Principali

### Self-Healing System

Il sistema di auto-guarigione monitora continuamente i servizi di M4Bot e li ripristina automaticamente in caso di guasti o malfunzionamenti.

**Caratteristiche principali:**
- Monitoraggio continuo di servizi (systemd, docker, processi, API)
- Rilevamento automatico di guasti
- Riavvio automatico di servizi problematici
- Gestione delle risorse di sistema
- Cronologia dettagliata delle riparazioni

**Utilizzo:**
```bash
# Avvio del sistema di self-healing
python stability/self_healing/self_healing_system.py --config path/to/config.json

# O tramite systemd
systemctl start m4bot-self-healing
```

### Monitoring System

Il sistema di monitoraggio raccoglie e analizza metriche di sistema e dell'applicazione, identificando potenziali problemi e generando avvisi.

**Caratteristiche principali:**
- Monitoraggio risorse di sistema (CPU, memoria, disco, rete)
- Tracciamento performance applicazione
- Esportazione metriche in formati diversi (JSON, Prometheus)
- Alerting basato su soglie configurabili

**Utilizzo:**
```bash
# Avvio del sistema di monitoraggio
python scripts/monitor_system.py --config path/to/config.json

# Raccolta per un periodo definito con esportazione
python scripts/monitor_system.py --duration 3600 --export output.json

# O tramite systemd
systemctl start m4bot-monitoring
```

### Chaos Testing

Il modulo di chaos testing introduce deliberatamente guasti e condizioni anomale nel sistema per verificarne la resilienza e le capacità di auto-riparazione.

**Caratteristiche principali:**
- Simulazione di guasti di servizi
- Test di sovraccarico risorse
- Simulazione di errori di rete e latenza
- Test di resilienza del database
- Generazione di report dettagliati

**Utilizzo:**
```bash
# Esecuzione di una suite di test standard
python stability/self_healing/chaos_testing.py

# Esecuzione di un test specifico
python stability/self_healing/chaos_testing.py --test service_kill_web
```

### Anomaly Detection

Il modulo di rilevamento anomalie identifica comportamenti insoliti del sistema attraverso analisi statistiche e algoritmi di machine learning.

**Caratteristiche principali:**
- Analisi statistica di metriche
- Rilevamento outlier in tempo reale
- Previsione di trend problematici
- Integrazione con il sistema di self-healing

**Utilizzo:**
```bash
# Avvio del rilevamento anomalie
python stability/self_healing/anomaly_detection.py --collect

# Esportazione dei risultati
python stability/self_healing/anomaly_detection.py --export anomalies.json
```

## Installazione

L'installazione completa di tutti i moduli di stabilità può essere eseguita con lo script di setup:

```bash
# Installazione
sudo ./scripts/setup_stability.sh
```

Questo script:
1. Installa le dipendenze necessarie
2. Crea e configura le directory necessarie
3. Genera i file di configurazione di esempio
4. Configura i servizi systemd
5. Avvia i servizi di monitoraggio e self-healing

## Configurazione

I file di configurazione si trovano nella directory `M4Bot-Config`:

- `self_healing.json`: Configurazione del sistema di auto-guarigione
- `monitoring.json`: Configurazione del sistema di monitoraggio

Per modificare le configurazioni, modifica questi file e riavvia i servizi corrispondenti:

```bash
systemctl restart m4bot-self-healing
systemctl restart m4bot-monitoring
```

## Directory principali

- `stability/self_healing/`: Sistema di auto-guarigione
- `stability/monitoring/`: Sistema di monitoraggio
- `stability/testing/`: Framework di testing automatizzato
- `stability/self_healing/chaos_reports/`: Report dei test di chaos
- `stability/monitoring/monitoring_data/`: Dati di monitoraggio raccolti
- `logs/reports/`: Report generati dai vari moduli 