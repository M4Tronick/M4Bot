import os
import logging
import asyncio
import asyncpg
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Union, Set

# Configura il logging
logger = logging.getLogger("DatabaseManager")

class DatabaseManager:
    """
    Gestisce la connessione e le operazioni del database PostgreSQL
    Fornisce funzionalità avanzate come gestione delle query lente e ottimizzazione
    """
    
    def __init__(self, connection_string: str):
        """
        Inizializza il gestore del database
        
        Args:
            connection_string: Stringa di connessione PostgreSQL
        """
        self.connection_string = connection_string
        self.pool = None
        self.slow_queries: List[Dict[str, Any]] = []
        self.slow_query_threshold = 500  # ms
        self.last_optimization = None
        self.optimization_interval = timedelta(days=7)  # Ottimizzazione settimanale
        self.is_connected = False
        
        # Crea directory per i log
        os.makedirs("logs/database", exist_ok=True)
    
    async def connect(self) -> bool:
        """
        Connette al database PostgreSQL con retry e backoff esponenziale
        
        Returns:
            bool: True se la connessione è riuscita, False altrimenti
        """
        retry_count = 0
        max_retries = 5
        base_retry_delay = 2  # secondi
        
        while retry_count < max_retries:
            try:
                logger.info(f"Tentativo di connessione al database: {retry_count + 1}")
                
                # Configura il pool con timeout, max_size e statement_cache_size
                self.pool = await asyncpg.create_pool(
                    dsn=self.connection_string,
                    min_size=1,
                    max_size=10,
                    command_timeout=60,  # 60 secondi
                    statement_cache_size=200,  # Cache per 200 statement
                    max_inactive_connection_lifetime=300  # 5 minuti
                )
                
                # Verifica la connessione eseguendo una query semplice
                async with self.pool.acquire() as conn:
                    version = await conn.fetchval("SELECT version()")
                    logger.info(f"Connesso al database: {version}")
                
                self.is_connected = True
                
                # Inizializza la tabella per il logging delle query lente se non esiste
                await self._initialize_slow_query_logging()
                
                # Verifica quando è stata eseguita l'ultima ottimizzazione
                await self._check_last_optimization()
                
                return True
            except Exception as e:
                retry_count += 1
                retry_delay = base_retry_delay * (2 ** (retry_count - 1))  # Backoff esponenziale
                logger.error(f"Errore nella connessione al database: {e}")
                
                if retry_count < max_retries:
                    logger.info(f"Ritentativo tra {retry_delay} secondi...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.critical("Numero massimo di tentativi di connessione raggiunto")
                    break
        
        self.is_connected = False
        return False
    
    async def disconnect(self):
        """Chiude la connessione al database"""
        if self.pool:
            await self.pool.close()
            self.is_connected = False
            logger.info("Connessione al database chiusa")
    
    async def execute(self, query: str, *args, timeout: Optional[float] = None) -> str:
        """
        Esegue una query che non restituisce risultati
        
        Args:
            query: Query SQL da eseguire
            *args: Parametri per la query
            timeout: Timeout opzionale per la query (in secondi)
            
        Returns:
            str: Risultato dell'esecuzione della query
        """
        if not self.is_connected:
            raise DatabaseError("Database non connesso")
        
        start_time = time.time()
        
        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(query, *args, timeout=timeout)
                
                execution_time = (time.time() - start_time) * 1000  # Converti in ms
                if execution_time > self.slow_query_threshold:
                    await self._log_slow_query(query, args, execution_time)
                
                return result
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            await self._log_query_error(query, args, e, execution_time)
            raise DatabaseError(f"Errore nell'esecuzione della query: {e}")
    
    async def fetch(self, query: str, *args, timeout: Optional[float] = None) -> List[asyncpg.Record]:
        """
        Esegue una query che restituisce più righe
        
        Args:
            query: Query SQL da eseguire
            *args: Parametri per la query
            timeout: Timeout opzionale per la query (in secondi)
            
        Returns:
            List[asyncpg.Record]: Lista di record restituiti dalla query
        """
        if not self.is_connected:
            raise DatabaseError("Database non connesso")
        
        start_time = time.time()
        
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetch(query, *args, timeout=timeout)
                
                execution_time = (time.time() - start_time) * 1000
                if execution_time > self.slow_query_threshold:
                    await self._log_slow_query(query, args, execution_time)
                
                return result
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            await self._log_query_error(query, args, e, execution_time)
            raise DatabaseError(f"Errore nell'esecuzione della query: {e}")
    
    async def fetchrow(self, query: str, *args, timeout: Optional[float] = None) -> Optional[asyncpg.Record]:
        """
        Esegue una query che restituisce una sola riga
        
        Args:
            query: Query SQL da eseguire
            *args: Parametri per la query
            timeout: Timeout opzionale per la query (in secondi)
            
        Returns:
            Optional[asyncpg.Record]: Record restituito dalla query o None
        """
        if not self.is_connected:
            raise DatabaseError("Database non connesso")
        
        start_time = time.time()
        
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchrow(query, *args, timeout=timeout)
                
                execution_time = (time.time() - start_time) * 1000
                if execution_time > self.slow_query_threshold:
                    await self._log_slow_query(query, args, execution_time)
                
                return result
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            await self._log_query_error(query, args, e, execution_time)
            raise DatabaseError(f"Errore nell'esecuzione della query: {e}")
    
    async def fetchval(self, query: str, *args, timeout: Optional[float] = None) -> Any:
        """
        Esegue una query che restituisce un singolo valore
        
        Args:
            query: Query SQL da eseguire
            *args: Parametri per la query
            timeout: Timeout opzionale per la query (in secondi)
            
        Returns:
            Any: Valore restituito dalla query
        """
        if not self.is_connected:
            raise DatabaseError("Database non connesso")
        
        start_time = time.time()
        
        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(query, *args, timeout=timeout)
                
                execution_time = (time.time() - start_time) * 1000
                if execution_time > self.slow_query_threshold:
                    await self._log_slow_query(query, args, execution_time)
                
                return result
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            await self._log_query_error(query, args, e, execution_time)
            raise DatabaseError(f"Errore nell'esecuzione della query: {e}")
    
    async def transaction(self):
        """
        Crea e restituisce una transazione per eseguire operazioni multiple
        
        Returns:
            AsyncConnection: Connessione con una transazione attiva
        """
        if not self.is_connected:
            raise DatabaseError("Database non connesso")
        
        return self.pool.acquire()
    
    async def optimize_database(self, full: bool = False) -> Dict[str, Any]:
        """
        Esegue operazioni di ottimizzazione sul database
        
        Args:
            full: Se True, esegue un'ottimizzazione completa con VACUUM FULL
            
        Returns:
            Dict[str, Any]: Risultato dell'ottimizzazione
        """
        if not self.is_connected:
            raise DatabaseError("Database non connesso")
        
        start_time = time.time()
        result = {
            "vacuum": None,
            "analyze": None,
            "reindex": None,
            "table_stats": None,
            "execution_time": 0,
            "errors": []
        }
        
        try:
            async with self.pool.acquire() as conn:
                # Ottieni la lista delle tabelle
                tables = await conn.fetch(
                    """
                    SELECT tablename 
                    FROM pg_tables 
                    WHERE schemaname = 'public'
                    """
                )
                
                # VACUUM per recuperare spazio
                if full:
                    logger.info("Esecuzione VACUUM FULL...")
                    try:
                        await conn.execute("VACUUM FULL")
                        result["vacuum"] = "success"
                    except Exception as e:
                        error_msg = f"Errore durante VACUUM FULL: {e}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
                        result["vacuum"] = "error"
                else:
                    logger.info("Esecuzione VACUUM...")
                    try:
                        await conn.execute("VACUUM")
                        result["vacuum"] = "success"
                    except Exception as e:
                        error_msg = f"Errore durante VACUUM: {e}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
                        result["vacuum"] = "error"
                
                # ANALYZE per aggiornare le statistiche
                logger.info("Esecuzione ANALYZE...")
                try:
                    await conn.execute("ANALYZE")
                    result["analyze"] = "success"
                except Exception as e:
                    error_msg = f"Errore durante ANALYZE: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)
                    result["analyze"] = "error"
                
                # REINDEX per ogni tabella
                logger.info("Esecuzione REINDEX...")
                reindex_errors = 0
                for table in tables:
                    table_name = table['tablename']
                    try:
                        await conn.execute(f"REINDEX TABLE {table_name}")
                    except Exception as e:
                        error_msg = f"Errore durante REINDEX di {table_name}: {e}"
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
                        reindex_errors += 1
                
                if reindex_errors == 0:
                    result["reindex"] = "success"
                elif reindex_errors < len(tables):
                    result["reindex"] = "partial"
                else:
                    result["reindex"] = "error"
                
                # Ottieni statistiche sulle tabelle
                try:
                    table_stats = await conn.fetch(
                        """
                        SELECT
                            relname as table_name,
                            pg_size_pretty(pg_total_relation_size(relid)) as total_size,
                            pg_size_pretty(pg_relation_size(relid)) as table_size,
                            pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) as index_size,
                            reltuples::bigint as row_count
                        FROM pg_catalog.pg_statio_user_tables
                        ORDER BY pg_total_relation_size(relid) DESC
                        """
                    )
                    result["table_stats"] = [dict(row) for row in table_stats]
                except Exception as e:
                    error_msg = f"Errore durante il recupero delle statistiche: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)
                
                # Aggiorna la data dell'ultima ottimizzazione
                now = datetime.now()
                await conn.execute(
                    """
                    INSERT INTO database_maintenance (operation, execution_time, executed_at)
                    VALUES ($1, $2, $3)
                    """,
                    "optimize", time.time() - start_time, now
                )
                self.last_optimization = now
        
        except Exception as e:
            error_msg = f"Errore durante l'ottimizzazione: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
        
        result["execution_time"] = time.time() - start_time
        
        # Logga il risultato
        logger.info(f"Ottimizzazione database completata in {result['execution_time']:.2f} secondi")
        
        return result
    
    async def get_slow_queries(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Recupera le query lente più recenti
        
        Args:
            limit: Numero massimo di query da recuperare
            
        Returns:
            List[Dict[str, Any]]: Lista di query lente
        """
        if not self.is_connected:
            raise DatabaseError("Database non connesso")
        
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT 
                        id, query, parameters, execution_time, executed_at
                    FROM 
                        slow_queries
                    ORDER BY 
                        executed_at DESC
                    LIMIT $1
                    """,
                    limit
                )
                
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Errore nel recupero delle query lente: {e}")
            return []
    
    async def _initialize_slow_query_logging(self):
        """Inizializza la tabella per il logging delle query lente"""
        try:
            async with self.pool.acquire() as conn:
                # Crea tabella per le query lente
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS slow_queries (
                        id SERIAL PRIMARY KEY,
                        query TEXT NOT NULL,
                        parameters TEXT,
                        execution_time FLOAT NOT NULL,
                        executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                    """
                )
                
                # Crea tabella per la manutenzione del database
                await conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS database_maintenance (
                        id SERIAL PRIMARY KEY,
                        operation TEXT NOT NULL,
                        execution_time FLOAT,
                        executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                    """
                )
                
                # Crea indice sulla data di esecuzione per le query lente
                await conn.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_slow_queries_executed_at
                    ON slow_queries (executed_at DESC)
                    """
                )
                
                logger.info("Tabelle per il logging delle query inizializzate")
        except Exception as e:
            logger.error(f"Errore nell'inizializzazione delle tabelle di logging: {e}")
    
    async def _check_last_optimization(self):
        """Verifica quando è stata eseguita l'ultima ottimizzazione"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT executed_at 
                    FROM database_maintenance 
                    WHERE operation = 'optimize' 
                    ORDER BY executed_at DESC 
                    LIMIT 1
                    """
                )
                
                if row:
                    self.last_optimization = row['executed_at']
                    logger.info(f"Ultima ottimizzazione database: {self.last_optimization}")
                else:
                    logger.info("Nessuna ottimizzazione precedente trovata")
        except Exception as e:
            logger.error(f"Errore nel controllo dell'ultima ottimizzazione: {e}")
    
    async def _log_slow_query(self, query: str, params: tuple, execution_time: float):
        """
        Registra una query lenta
        
        Args:
            query: Query SQL
            params: Parametri della query
            execution_time: Tempo di esecuzione in millisecondi
        """
        try:
            # Filtra parametri sensibili (password, token, ecc.)
            filtered_params = self._filter_sensitive_params(params)
            
            # Registra query lenta nel database
            async with self.pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO slow_queries (query, parameters, execution_time)
                    VALUES ($1, $2, $3)
                    """,
                    query, str(filtered_params), execution_time
                )
            
            # Aggiungi alla lista in memoria
            self.slow_queries.append({
                "query": query,
                "parameters": filtered_params,
                "execution_time": execution_time,
                "executed_at": datetime.now()
            })
            
            # Mantieni solo le ultime 100 query lente in memoria
            if len(self.slow_queries) > 100:
                self.slow_queries = self.slow_queries[-100:]
            
            logger.warning(f"Query lenta rilevata ({execution_time:.2f}ms): {query}")
            
            # Registra nel file di log
            with open("logs/database/slow_queries.log", "a") as f:
                f.write(f"[{datetime.now().isoformat()}] {execution_time:.2f}ms: {query} - Params: {filtered_params}\n")
                
        except Exception as e:
            logger.error(f"Errore nel logging della query lenta: {e}")
    
    async def _log_query_error(self, query: str, params: tuple, error: Exception, execution_time: float):
        """
        Registra un errore di query
        
        Args:
            query: Query SQL
            params: Parametri della query
            error: Eccezione sollevata
            execution_time: Tempo di esecuzione in millisecondi
        """
        try:
            # Filtra parametri sensibili
            filtered_params = self._filter_sensitive_params(params)
            
            # Registra errore nel file di log
            with open("logs/database/query_errors.log", "a") as f:
                f.write(f"[{datetime.now().isoformat()}] {execution_time:.2f}ms: {query} - Params: {filtered_params}\n")
                f.write(f"Errore: {error}\n\n")
                
            logger.error(f"Errore query ({execution_time:.2f}ms): {query} - {error}")
        except Exception as e:
            logger.error(f"Errore nel logging dell'errore di query: {e}")
    
    def _filter_sensitive_params(self, params: tuple) -> tuple:
        """
        Filtra parametri sensibili sostituendoli con [REDACTED]
        
        Args:
            params: Parametri della query
            
        Returns:
            tuple: Parametri filtrati
        """
        if not params:
            return params
            
        sensitive_keywords = ['password', 'secret', 'token', 'key', 'credential']
        filtered_params = []
        
        for param in params:
            # Se è una stringa, verifica se contiene informazioni sensibili
            if isinstance(param, str):
                is_sensitive = False
                # Controlla se il parametro potrebbe essere sensibile
                if len(param) > 8:  # Parametri sensibili solitamente sono lunghi
                    is_sensitive = any(keyword in param.lower() for keyword in sensitive_keywords)
                
                if is_sensitive:
                    filtered_params.append("[REDACTED]")
                else:
                    filtered_params.append(param)
            else:
                filtered_params.append(param)
        
        return tuple(filtered_params)
    
    async def check_and_optimize_if_needed(self) -> bool:
        """
        Verifica se è necessario ottimizzare il database e lo ottimizza se necessario
        
        Returns:
            bool: True se è stata eseguita l'ottimizzazione, False altrimenti
        """
        if not self.is_connected:
            logger.error("Impossibile ottimizzare il database: non connesso")
            return False
            
        # Verifica se è passato abbastanza tempo dall'ultima ottimizzazione
        if self.last_optimization is None or \
           (datetime.now() - self.last_optimization) > self.optimization_interval:
            logger.info("Esecuzione ottimizzazione database programmata...")
            
            try:
                await self.optimize_database(full=False)
                return True
            except Exception as e:
                logger.error(f"Errore durante l'ottimizzazione programmata: {e}")
                return False
        else:
            logger.debug("Ottimizzazione database non necessaria")
            return False
    
    def set_slow_query_threshold(self, threshold_ms: int):
        """
        Imposta la soglia per considerare una query come 'lenta'
        
        Args:
            threshold_ms: Soglia in millisecondi
        """
        self.slow_query_threshold = threshold_ms
        logger.info(f"Soglia per query lente impostata a {threshold_ms}ms")
    
    def set_optimization_interval(self, days: int):
        """
        Imposta l'intervallo per l'ottimizzazione automatica
        
        Args:
            days: Intervallo in giorni
        """
        self.optimization_interval = timedelta(days=days)
        logger.info(f"Intervallo ottimizzazione database impostato a {days} giorni")

class DatabaseError(Exception):
    """Eccezione per errori di database"""
    pass 