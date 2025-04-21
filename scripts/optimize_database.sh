#!/bin/bash
# Script per l'ottimizzazione del database di M4Bot
# Esegue VACUUM, ANALYZE e REINDEX per migliorare le performance del database

# Imposta il path di installazione
M4BOT_DIR=${M4BOT_DIR:-"/opt/m4bot"}
LOG_DIR="$M4BOT_DIR/logs/database"
PG_USER=${PG_USER:-"postgres"}
DB_NAME=${DB_NAME:-"m4bot_db"}
DB_USER=${DB_USER:-"m4bot_user"}

# Imposta i colori per i messaggi
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funzione per i messaggi
print_message() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Verifica che il sistema sia Linux
if [ "$(uname)" != "Linux" ]; then
    print_error "Questo script è progettato per funzionare solo su Linux"
    exit 1
fi

# Crea la directory di log se non esiste
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/optimize_db_$(date +%Y%m%d_%H%M%S).log"

# Registra l'inizio dell'ottimizzazione
print_message "Inizio ottimizzazione del database PostgreSQL $(date)" | tee -a "$LOG_FILE"

# Verifica se PostgreSQL è in esecuzione
if ! systemctl is-active --quiet postgresql; then
    print_error "PostgreSQL non è in esecuzione. Avvio del servizio..." | tee -a "$LOG_FILE"
    systemctl start postgresql
    sleep 5
    
    if ! systemctl is-active --quiet postgresql; then
        print_error "Impossibile avviare PostgreSQL. Ottimizzazione annullata." | tee -a "$LOG_FILE"
        exit 1
    fi
fi

# Verifica che il database esista
if ! sudo -u "$PG_USER" psql -lqt | cut -d \| -f 1 | grep -qw "$DB_NAME"; then
    print_error "Database $DB_NAME non trovato. Ottimizzazione annullata." | tee -a "$LOG_FILE"
    exit 1
fi

# Timestamp di inizio
START_TIME=$(date +%s)

# Controllo spazio prima dell'ottimizzazione
print_message "Verifica spazio database prima dell'ottimizzazione..." | tee -a "$LOG_FILE"
DB_SIZE_BEFORE=$(sudo -u "$PG_USER" psql -d "$DB_NAME" -c "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));" | grep -v "row\|pg_size_pretty\|--" | xargs)
echo "Dimensione database prima: $DB_SIZE_BEFORE" | tee -a "$LOG_FILE"

# Esegue VACUUM ANALYZE per aggiornare le statistiche e recuperare spazio
print_message "Esecuzione VACUUM ANALYZE..." | tee -a "$LOG_FILE"
if sudo -u "$PG_USER" psql -d "$DB_NAME" -c "VACUUM ANALYZE;" >> "$LOG_FILE" 2>&1; then
    print_success "VACUUM ANALYZE completato con successo" | tee -a "$LOG_FILE"
else
    print_error "Errore durante VACUUM ANALYZE" | tee -a "$LOG_FILE"
fi

# Esegue ottimizzazione di routine per ogni tabella
print_message "Ottimizzazione delle tabelle..." | tee -a "$LOG_FILE"

# Ottieni la lista delle tabelle
TABLES=$(sudo -u "$PG_USER" psql -d "$DB_NAME" -c "SELECT tablename FROM pg_tables WHERE schemaname='public';" | grep -v "row\|tablename\|--" | xargs)

# Ciclo su ogni tabella
for TABLE in $TABLES; do
    print_message "Ottimizzazione tabella $TABLE..." | tee -a "$LOG_FILE"
    
    # VACUUM ANALYZE per la tabella specifica
    if sudo -u "$PG_USER" psql -d "$DB_NAME" -c "VACUUM ANALYZE $TABLE;" >> "$LOG_FILE" 2>&1; then
        echo "  - VACUUM ANALYZE completato" >> "$LOG_FILE"
    else
        print_error "  - Errore durante VACUUM ANALYZE su $TABLE" | tee -a "$LOG_FILE"
    fi
    
    # REINDEX per la tabella
    if sudo -u "$PG_USER" psql -d "$DB_NAME" -c "REINDEX TABLE $TABLE;" >> "$LOG_FILE" 2>&1; then
        echo "  - REINDEX completato" >> "$LOG_FILE"
    else
        print_error "  - Errore durante REINDEX su $TABLE" | tee -a "$LOG_FILE"
    fi
done

# Ottimizzazione più aggressiva con VACUUM FULL (opzionale)
if [ "$1" == "--full" ]; then
    print_warning "Esecuzione VACUUM FULL. Questa operazione può richiedere molto tempo e bloccare le tabelle..." | tee -a "$LOG_FILE"
    if sudo -u "$PG_USER" psql -d "$DB_NAME" -c "VACUUM FULL;" >> "$LOG_FILE" 2>&1; then
        print_success "VACUUM FULL completato con successo" | tee -a "$LOG_FILE"
    else
        print_error "Errore durante VACUUM FULL" | tee -a "$LOG_FILE"
    fi
fi

# Ottimizzazione indici del database
print_message "Ottimizzazione indici del database..." | tee -a "$LOG_FILE"
if sudo -u "$PG_USER" psql -d "$DB_NAME" -c "REINDEX DATABASE $DB_NAME;" >> "$LOG_FILE" 2>&1; then
    print_success "Ottimizzazione indici completata con successo" | tee -a "$LOG_FILE"
else
    print_error "Errore durante l'ottimizzazione degli indici" | tee -a "$LOG_FILE"
fi

# Aggiorna le statistiche del pianificatore
print_message "Aggiornamento statistiche del pianificatore..." | tee -a "$LOG_FILE"
if sudo -u "$PG_USER" psql -d "$DB_NAME" -c "ANALYZE;" >> "$LOG_FILE" 2>&1; then
    print_success "Aggiornamento statistiche completato con successo" | tee -a "$LOG_FILE"
else
    print_error "Errore durante l'aggiornamento delle statistiche" | tee -a "$LOG_FILE"
fi

# Verifica tabelle e indici non utilizzati (solo informativo)
print_message "Verifica tabelle e indici non utilizzati..." | tee -a "$LOG_FILE"
sudo -u "$PG_USER" psql -d "$DB_NAME" -c "
SELECT relname AS table_name,
       n_live_tup AS row_count,
       pg_size_pretty(pg_relation_size(relid)) AS size
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;" >> "$LOG_FILE" 2>&1

sudo -u "$PG_USER" psql -d "$DB_NAME" -c "
SELECT indexrelname AS index_name,
       relname AS table_name,
       idx_scan AS usage_count,
       pg_size_pretty(pg_relation_size(i.indexrelid)) AS size
FROM pg_stat_user_indexes i
JOIN pg_stat_user_tables t ON i.relid = t.relid
ORDER BY idx_scan DESC;" >> "$LOG_FILE" 2>&1

# Verifica lo spazio dopo l'ottimizzazione
print_message "Verifica spazio database dopo l'ottimizzazione..." | tee -a "$LOG_FILE"
DB_SIZE_AFTER=$(sudo -u "$PG_USER" psql -d "$DB_NAME" -c "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));" | grep -v "row\|pg_size_pretty\|--" | xargs)
echo "Dimensione database dopo: $DB_SIZE_AFTER" | tee -a "$LOG_FILE"

# Calcola il tempo impiegato
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

# Registra la conclusione dell'ottimizzazione
print_success "Ottimizzazione del database completata in $MINUTES minuti e $SECONDS secondi" | tee -a "$LOG_FILE"
print_message "Log salvato in: $LOG_FILE" | tee -a "$LOG_FILE"

# Registra nel database l'ottimizzazione (se possibile)
if command -v python3 > /dev/null; then
    print_message "Registrazione dell'ottimizzazione nel database..." | tee -a "$LOG_FILE"
    PYTHON_SCRIPT=$(cat << 'EOF'
import sys
import os
import asyncio
import asyncpg
from datetime import datetime

async def log_optimization():
    try:
        # Prova a ottenere la connessione dal file .env
        import dotenv
        dotenv.load_dotenv(os.path.join(os.environ.get('M4BOT_DIR', '/opt/m4bot'), '.env'))
        
        db_url = os.environ.get('DATABASE_URL')
        if not db_url:
            db_user = os.environ.get('DB_USER', 'm4bot_user')
            db_pass = os.environ.get('DB_PASSWORD', 'm4bot_password')
            db_name = os.environ.get('DB_NAME', 'm4bot_db')
            db_host = os.environ.get('DB_HOST', 'localhost')
            db_url = f"postgresql://{db_user}:{db_pass}@{db_host}/{db_name}"
        
        conn = await asyncpg.connect(db_url)
        
        # Verifica se esiste la tabella database_maintenance
        table_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'database_maintenance')"
        )
        
        if not table_exists:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS database_maintenance (
                    id SERIAL PRIMARY KEY,
                    operation TEXT NOT NULL,
                    execution_time FLOAT,
                    executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """)
        
        # Inserisci il record di ottimizzazione
        await conn.execute(
            "INSERT INTO database_maintenance (operation, execution_time, executed_at) VALUES ($1, $2, $3)",
            "optimize_script", float(sys.argv[1]), datetime.now()
        )
        
        await conn.close()
        print("Ottimizzazione registrata nel database")
    except Exception as e:
        print(f"Errore durante la registrazione nel database: {e}")

if __name__ == "__main__":
    asyncio.run(log_optimization())
EOF
)
    echo "$PYTHON_SCRIPT" > /tmp/log_optimization.py
    
    # Esegui lo script Python passando la durata dell'ottimizzazione
    if python3 /tmp/log_optimization.py "$DURATION" >> "$LOG_FILE" 2>&1; then
        print_success "Registrazione dell'ottimizzazione completata" | tee -a "$LOG_FILE"
    else
        print_warning "Errore durante la registrazione dell'ottimizzazione" | tee -a "$LOG_FILE"
    fi
    
    # Rimuovi lo script temporaneo
    rm -f /tmp/log_optimization.py
fi

exit 0 