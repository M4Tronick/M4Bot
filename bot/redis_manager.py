import os
import logging
import asyncio
import redis.asyncio as redis
from typing import Any, Dict, List, Optional, Tuple, Union, Set
from datetime import datetime, timedelta
import json
import socket
import hashlib
import secrets
import time

# Configurazione logging
logger = logging.getLogger("RedisManager")

class RedisManager:
    """
    Gestisce le connessioni a Redis con funzionalità avanzate come:
    - Gestione pool di connessioni
    - Retry automatici con backoff esponenziale
    - Rotazione chiavi per sicurezza
    - Monitoraggio delle performance
    - Gestione della cache con scadenza
    """
    
    def __init__(self, 
                 host: str = "localhost", 
                 port: int = 6379, 
                 db: int = 0, 
                 password: Optional[str] = None,
                 key_prefix: str = "m4bot",
                 max_connections: int = 10,
                 connection_timeout: int = 10,
                 key_rotation_interval: int = 7,  # giorni
                 key_rotation_enabled: bool = True,
                 compression_threshold: int = 1024,  # byte
                 monitor_commands: bool = True):
        """
        Inizializza il gestore Redis
        
        Args:
            host: Host Redis
            port: Porta Redis
            db: Numero database Redis
            password: Password per l'autenticazione Redis
            key_prefix: Prefisso per le chiavi Redis
            max_connections: Numero massimo di connessioni nel pool
            connection_timeout: Timeout per le connessioni in secondi
            key_rotation_interval: Intervallo in giorni per la rotazione delle chiavi
            key_rotation_enabled: Se attivare la rotazione automatica delle chiavi
            compression_threshold: Soglia in byte per la compressione dei dati
            monitor_commands: Se monitorare le performance dei comandi
        """
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.key_prefix = key_prefix
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self.key_rotation_interval = key_rotation_interval
        self.key_rotation_enabled = key_rotation_enabled
        self.compression_threshold = compression_threshold
        self.monitor_commands = monitor_commands
        
        # Pool di connessioni
        self.pool = None
        self.is_connected = False
        
        # Metriche e monitoring
        self.command_stats: Dict[str, Dict[str, Union[int, float]]] = {}
        self.last_health_check = None
        self.health_status = {}
        
        # Cache delle chiavi
        self.key_list_cache = set()
        self.key_list_cache_time = None
        self.key_list_cache_ttl = timedelta(minutes=5)
        
        # Rotazione chiavi
        self.current_key_version = 1
        self.key_rotation_last_time = None
        
        # Crea directory per i log
        os.makedirs("logs/redis", exist_ok=True)

    async def connect(self) -> bool:
        """
        Connette a Redis con retry e backoff esponenziale
        
        Returns:
            bool: True se la connessione è riuscita, False altrimenti
        """
        retry_count = 0
        max_retries = 5
        base_retry_delay = 2  # secondi
        
        while retry_count < max_retries:
            try:
                logger.info(f"Tentativo di connessione a Redis {self.host}:{self.port} (DB {self.db}): {retry_count + 1}")
                
                # Crea il connection pool
                self.pool = redis.ConnectionPool(
                    host=self.host,
                    port=self.port,
                    db=self.db,
                    password=self.password,
                    max_connections=self.max_connections,
                    socket_timeout=self.connection_timeout,
                    socket_connect_timeout=self.connection_timeout,
                    retry_on_timeout=True,
                    health_check_interval=30  # 30 secondi
                )
                
                # Verifica la connessione
                async with redis.Redis(connection_pool=self.pool) as r:
                    await r.ping()
                    info = await r.info()
                    logger.info(f"Connesso a Redis: {info.get('redis_version', 'Unknown')}")
                    
                    # Carica l'attuale versione della chiave se esiste
                    key_version = await r.get(f"{self.key_prefix}:key_version")
                    if key_version:
                        self.current_key_version = int(key_version)
                    else:
                        # Imposta la versione iniziale delle chiavi
                        await r.set(f"{self.key_prefix}:key_version", self.current_key_version)
                    
                    # Recupera l'ultima rotazione delle chiavi
                    last_rotation = await r.get(f"{self.key_prefix}:last_key_rotation")
                    if last_rotation:
                        self.key_rotation_last_time = datetime.fromisoformat(last_rotation.decode('utf-8'))
                    else:
                        self.key_rotation_last_time = datetime.now()
                        await r.set(f"{self.key_prefix}:last_key_rotation", self.key_rotation_last_time.isoformat())
                
                self.is_connected = True
                
                # Esegui un controllo iniziale dello stato di salute
                await self.health_check()
                
                return True
            except Exception as e:
                retry_count += 1
                retry_delay = base_retry_delay * (2 ** (retry_count - 1))  # Backoff esponenziale
                logger.error(f"Errore nella connessione a Redis: {e}")
                
                if retry_count < max_retries:
                    logger.info(f"Ritentativo tra {retry_delay} secondi...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.critical("Numero massimo di tentativi di connessione Redis raggiunto")
                    break
        
        self.is_connected = False
        return False

    async def disconnect(self):
        """Chiude la connessione a Redis"""
        if self.pool:
            self.pool.disconnect()
            self.is_connected = False
            logger.info("Connessione a Redis chiusa")

    async def _get_redis(self):
        """
        Ottiene una connessione dal pool
        
        Returns:
            Redis: Connessione Redis
        """
        if not self.is_connected:
            raise RedisError("Redis non connesso")
        
        return redis.Redis(connection_pool=self.pool)

    def _format_key(self, key: str) -> str:
        """
        Formatta una chiave con prefisso e versione
        
        Args:
            key: Chiave da formattare
            
        Returns:
            str: Chiave formattata
        """
        if self.key_rotation_enabled:
            return f"{self.key_prefix}:v{self.current_key_version}:{key}"
        else:
            return f"{self.key_prefix}:{key}"

    async def set(self, key: str, value: Any, ttl: Optional[int] = None, nx: bool = False, xx: bool = False) -> bool:
        """
        Imposta un valore in Redis
        
        Args:
            key: Chiave da impostare
            value: Valore da memorizzare (supporta oggetti complessi con serializzazione JSON)
            ttl: Tempo di vita in secondi
            nx: Se True, imposta solo se la chiave non esiste
            xx: Se True, imposta solo se la chiave esiste già
            
        Returns:
            bool: True se l'operazione è riuscita, False altrimenti
        """
        if not self.is_connected:
            raise RedisError("Redis non connesso")
        
        start_time = time.time()
        formatted_key = self._format_key(key)
        
        try:
            # Serializza oggetti complessi
            if not isinstance(value, (str, bytes, int, float)):
                serialized_value = json.dumps(value)
                # Flag per indicare che il valore è serializzato
                formatted_key = f"{formatted_key}:json"
            else:
                serialized_value = value
            
            # Comprimi valori grandi se necessario
            if isinstance(serialized_value, str) and len(serialized_value) > self.compression_threshold:
                import zlib
                serialized_value = zlib.compress(serialized_value.encode('utf-8'))
                formatted_key = f"{formatted_key}:compressed"
            
            async with await self._get_redis() as r:
                result = await r.set(formatted_key, serialized_value, ex=ttl, nx=nx, xx=xx)
                
                # Aggiunge la chiave alla cache locale
                if result and self.key_list_cache_time:
                    self.key_list_cache.add(formatted_key)
                
                # Registra statistiche comando
                if self.monitor_commands:
                    command_time = (time.time() - start_time) * 1000  # ms
                    self._update_command_stats("SET", command_time)
                
                return bool(result)
        except Exception as e:
            logger.error(f"Errore nell'impostazione della chiave {key}: {e}")
            raise RedisError(f"Errore nell'impostazione della chiave: {e}")

    async def get(self, key: str, default_value: Any = None) -> Any:
        """
        Recupera un valore da Redis
        
        Args:
            key: Chiave da recuperare
            default_value: Valore da restituire se la chiave non esiste
            
        Returns:
            Any: Valore recuperato o default_value se non trovato
        """
        if not self.is_connected:
            raise RedisError("Redis non connesso")
        
        start_time = time.time()
        formatted_key = self._format_key(key)
        
        try:
            async with await self._get_redis() as r:
                # Tenta prima con il formato attuale
                result = await r.get(formatted_key)
                
                # Se non trovato e la rotazione è abilitata, prova con la versione precedente
                if result is None and self.key_rotation_enabled and self.current_key_version > 1:
                    prev_key = f"{self.key_prefix}:v{self.current_key_version-1}:{key}"
                    result = await r.get(prev_key)
                    
                    # Se trovato nella versione precedente, migra alla versione attuale
                    if result is not None:
                        logger.debug(f"Migrazione chiave {key} dalla versione precedente")
                        ttl = await r.ttl(prev_key)
                        if ttl > 0:
                            await r.set(formatted_key, result, ex=ttl)
                        else:
                            await r.set(formatted_key, result)
                
                # Controlla se il valore è in JSON o compresso
                if result is not None:
                    if formatted_key.endswith(":json:compressed") or formatted_key.endswith(":compressed:json"):
                        import zlib
                        decompressed = zlib.decompress(result)
                        result = json.loads(decompressed.decode('utf-8'))
                    elif formatted_key.endswith(":json"):
                        result = json.loads(result)
                    elif formatted_key.endswith(":compressed"):
                        import zlib
                        result = zlib.decompress(result).decode('utf-8')
                
                # Registra statistiche comando
                if self.monitor_commands:
                    command_time = (time.time() - start_time) * 1000  # ms
                    self._update_command_stats("GET", command_time)
                
                return result if result is not None else default_value
        except Exception as e:
            logger.error(f"Errore nel recupero della chiave {key}: {e}")
            return default_value

    async def delete(self, key: str) -> bool:
        """
        Elimina una chiave da Redis
        
        Args:
            key: Chiave da eliminare
            
        Returns:
            bool: True se la chiave è stata eliminata, False altrimenti
        """
        if not self.is_connected:
            raise RedisError("Redis non connesso")
        
        start_time = time.time()
        formatted_key = self._format_key(key)
        
        try:
            async with await self._get_redis() as r:
                # Controlla varianti della chiave (json, compressed)
                variants = [
                    formatted_key,
                    f"{formatted_key}:json",
                    f"{formatted_key}:compressed",
                    f"{formatted_key}:json:compressed",
                    f"{formatted_key}:compressed:json"
                ]
                
                # Elimina tutte le possibili varianti
                deleted = 0
                for variant in variants:
                    deleted += await r.delete(variant)
                
                # Rimuovi dalla cache locale
                if self.key_list_cache_time:
                    for variant in variants:
                        self.key_list_cache.discard(variant)
                
                # Registra statistiche comando
                if self.monitor_commands:
                    command_time = (time.time() - start_time) * 1000  # ms
                    self._update_command_stats("DELETE", command_time)
                
                return deleted > 0
        except Exception as e:
            logger.error(f"Errore nell'eliminazione della chiave {key}: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """
        Verifica se una chiave esiste in Redis
        
        Args:
            key: Chiave da verificare
            
        Returns:
            bool: True se la chiave esiste, False altrimenti
        """
        if not self.is_connected:
            raise RedisError("Redis non connesso")
        
        start_time = time.time()
        formatted_key = self._format_key(key)
        
        try:
            async with await self._get_redis() as r:
                # Verifica anche varianti della chiave
                variants = [
                    formatted_key,
                    f"{formatted_key}:json",
                    f"{formatted_key}:compressed",
                    f"{formatted_key}:json:compressed",
                    f"{formatted_key}:compressed:json"
                ]
                
                # Verifica l'esistenza di tutte le possibili varianti
                for variant in variants:
                    if await r.exists(variant):
                        # Registra statistiche comando
                        if self.monitor_commands:
                            command_time = (time.time() - start_time) * 1000  # ms
                            self._update_command_stats("EXISTS", command_time)
                        return True
                
                # Se la rotazione delle chiavi è abilitata, controlla anche la versione precedente
                if self.key_rotation_enabled and self.current_key_version > 1:
                    prev_key = f"{self.key_prefix}:v{self.current_key_version-1}:{key}"
                    variants_prev = [
                        prev_key,
                        f"{prev_key}:json",
                        f"{prev_key}:compressed",
                        f"{prev_key}:json:compressed",
                        f"{prev_key}:compressed:json"
                    ]
                    
                    for variant in variants_prev:
                        if await r.exists(variant):
                            # Registra statistiche comando
                            if self.monitor_commands:
                                command_time = (time.time() - start_time) * 1000  # ms
                                self._update_command_stats("EXISTS", command_time)
                            return True
                
                # Registra statistiche comando
                if self.monitor_commands:
                    command_time = (time.time() - start_time) * 1000  # ms
                    self._update_command_stats("EXISTS", command_time)
                
                return False
        except Exception as e:
            logger.error(f"Errore nella verifica dell'esistenza della chiave {key}: {e}")
            return False

    async def expire(self, key: str, ttl: int) -> bool:
        """
        Imposta il tempo di vita di una chiave
        
        Args:
            key: Chiave da impostare
            ttl: Tempo di vita in secondi
            
        Returns:
            bool: True se l'operazione è riuscita, False altrimenti
        """
        if not self.is_connected:
            raise RedisError("Redis non connesso")
        
        start_time = time.time()
        formatted_key = self._format_key(key)
        
        try:
            async with await self._get_redis() as r:
                # Controlla varianti della chiave
                variants = [
                    formatted_key,
                    f"{formatted_key}:json",
                    f"{formatted_key}:compressed",
                    f"{formatted_key}:json:compressed",
                    f"{formatted_key}:compressed:json"
                ]
                
                # Imposta TTL su tutte le possibili varianti
                success = False
                for variant in variants:
                    if await r.exists(variant):
                        await r.expire(variant, ttl)
                        success = True
                
                # Registra statistiche comando
                if self.monitor_commands:
                    command_time = (time.time() - start_time) * 1000  # ms
                    self._update_command_stats("EXPIRE", command_time)
                
                return success
        except Exception as e:
            logger.error(f"Errore nell'impostazione del TTL per la chiave {key}: {e}")
            return False

    async def ttl(self, key: str) -> int:
        """
        Ottiene il tempo di vita rimanente di una chiave
        
        Args:
            key: Chiave da verificare
            
        Returns:
            int: TTL in secondi, -1 se non ha TTL, -2 se non esiste
        """
        if not self.is_connected:
            raise RedisError("Redis non connesso")
        
        start_time = time.time()
        formatted_key = self._format_key(key)
        
        try:
            async with await self._get_redis() as r:
                # Controlla varianti della chiave
                variants = [
                    formatted_key,
                    f"{formatted_key}:json",
                    f"{formatted_key}:compressed",
                    f"{formatted_key}:json:compressed",
                    f"{formatted_key}:compressed:json"
                ]
                
                # Cerca TTL su tutte le possibili varianti
                for variant in variants:
                    if await r.exists(variant):
                        ttl = await r.ttl(variant)
                        
                        # Registra statistiche comando
                        if self.monitor_commands:
                            command_time = (time.time() - start_time) * 1000  # ms
                            self._update_command_stats("TTL", command_time)
                        
                        return ttl
                
                # Registra statistiche comando
                if self.monitor_commands:
                    command_time = (time.time() - start_time) * 1000  # ms
                    self._update_command_stats("TTL", command_time)
                
                return -2  # Chiave non esistente
        except Exception as e:
            logger.error(f"Errore nel recupero del TTL per la chiave {key}: {e}")
            return -2

    async def keys(self, pattern: str = "*") -> List[str]:
        """
        Ottiene chiavi che corrispondono a un pattern
        
        Args:
            pattern: Pattern per filtrare le chiavi
            
        Returns:
            List[str]: Lista di chiavi
        """
        if not self.is_connected:
            raise RedisError("Redis non connesso")
        
        start_time = time.time()
        
        try:
            async with await self._get_redis() as r:
                # Aggiungi il prefisso al pattern
                prefixed_pattern = f"{self.key_prefix}*{pattern}"
                
                # Recupera le chiavi
                keys = await r.keys(prefixed_pattern)
                
                # Registra statistiche comando
                if self.monitor_commands:
                    command_time = (time.time() - start_time) * 1000  # ms
                    self._update_command_stats("KEYS", command_time)
                
                # Rimuovi il prefisso per restituire le chiavi originali
                result = []
                prefix_len = len(self.key_prefix) + 1  # +1 per il ":"
                
                for key in keys:
                    key_str = key.decode('utf-8')
                    # Rimuovi il prefisso e gli eventuali suffissi (:json, :compressed)
                    clean_key = key_str[prefix_len:]
                    
                    # Se è abilitata la rotazione delle chiavi, rimuovi anche il prefisso della versione
                    if self.key_rotation_enabled and clean_key.startswith(f"v{self.current_key_version}:"):
                        clean_key = clean_key[len(f"v{self.current_key_version}:"):]
                    
                    # Rimuovi suffissi
                    for suffix in [":json", ":compressed", ":json:compressed", ":compressed:json"]:
                        if clean_key.endswith(suffix):
                            clean_key = clean_key[:-len(suffix)]
                    
                    result.append(clean_key)
                
                return result
        except Exception as e:
            logger.error(f"Errore nel recupero delle chiavi con pattern {pattern}: {e}")
            return []

    async def flush_db(self) -> bool:
        """
        Svuota il database Redis corrente
        
        Returns:
            bool: True se l'operazione è riuscita, False altrimenti
        """
        if not self.is_connected:
            raise RedisError("Redis non connesso")
        
        start_time = time.time()
        
        try:
            async with await self._get_redis() as r:
                # Svuota solo le chiavi che iniziano con il prefisso
                keys = await r.keys(f"{self.key_prefix}*")
                
                if keys:
                    # Elimina in batch per migliorare le prestazioni
                    await r.delete(*keys)
                
                # Resetta la cache delle chiavi
                self.key_list_cache = set()
                self.key_list_cache_time = None
                
                # Registra statistiche comando
                if self.monitor_commands:
                    command_time = (time.time() - start_time) * 1000  # ms
                    self._update_command_stats("FLUSH", command_time)
                
                return True
        except Exception as e:
            logger.error(f"Errore nello svuotamento del database Redis: {e}")
            return False

    async def health_check(self) -> Dict[str, Any]:
        """
        Esegue un controllo dello stato di salute di Redis
        
        Returns:
            Dict[str, Any]: Informazioni sullo stato di salute
        """
        if not self.is_connected:
            self.health_status = {
                "status": "offline",
                "latency": -1,
                "used_memory": -1,
                "max_memory": -1,
                "memory_usage_percent": -1,
                "connected_clients": -1,
                "uptime": -1,
                "last_check": datetime.now().isoformat()
            }
            return self.health_status
        
        try:
            start_time = time.time()
            
            async with await self._get_redis() as r:
                # Misura latenza
                await r.ping()
                latency = (time.time() - start_time) * 1000  # ms
                
                # Ottieni informazioni di sistema
                info = await r.info()
                
                # Analizza le informazioni
                memory_info = {
                    "used_memory": int(info.get("used_memory", 0)),
                    "maxmemory": int(info.get("maxmemory", 0)),
                    "connected_clients": int(info.get("connected_clients", 0)),
                    "uptime_in_seconds": int(info.get("uptime_in_seconds", 0))
                }
                
                # Calcola la percentuale di utilizzo della memoria
                memory_usage_percent = -1
                if memory_info["maxmemory"] > 0:
                    memory_usage_percent = (memory_info["used_memory"] / memory_info["maxmemory"]) * 100
                
                # Aggiorna lo stato di salute
                self.health_status = {
                    "status": "online",
                    "latency": latency,
                    "used_memory": memory_info["used_memory"],
                    "max_memory": memory_info["maxmemory"],
                    "memory_usage_percent": memory_usage_percent,
                    "connected_clients": memory_info["connected_clients"],
                    "uptime": memory_info["uptime_in_seconds"],
                    "last_check": datetime.now().isoformat()
                }
                
                # Registra statistiche di salute
                self.last_health_check = datetime.now()
                
                # Registra allarmi
                if memory_usage_percent > 90:
                    logger.warning(f"Redis memoria quasi esaurita: {memory_usage_percent:.1f}% in uso")
                
                if latency > 100:  # ms
                    logger.warning(f"Alta latenza Redis: {latency:.2f}ms")
                
                return self.health_status
        except Exception as e:
            logger.error(f"Errore nel controllo dello stato di salute Redis: {e}")
            self.health_status = {
                "status": "error",
                "error": str(e),
                "last_check": datetime.now().isoformat()
            }
            return self.health_status

    async def rotate_keys(self, force: bool = False) -> bool:
        """
        Esegue la rotazione delle chiavi per sicurezza
        
        Args:
            force: Se True, forza la rotazione anche se non è passato l'intervallo
            
        Returns:
            bool: True se la rotazione è avvenuta, False altrimenti
        """
        if not self.is_connected or not self.key_rotation_enabled:
            return False
        
        # Verifica se è necessaria la rotazione
        now = datetime.now()
        if not force and self.key_rotation_last_time:
            time_since_last = now - self.key_rotation_last_time
            if time_since_last.days < self.key_rotation_interval:
                logger.debug(f"Rotazione chiavi non necessaria. Prossima rotazione tra {self.key_rotation_interval - time_since_last.days} giorni")
                return False
        
        try:
            logger.info("Avvio rotazione chiavi Redis")
            
            async with await self._get_redis() as r:
                # Incrementa la versione delle chiavi
                new_version = self.current_key_version + 1
                await r.set(f"{self.key_prefix}:key_version", new_version)
                
                # Aggiorna l'ultimo tempo di rotazione
                await r.set(f"{self.key_prefix}:last_key_rotation", now.isoformat())
                
                # Aggiorna i valori locali
                self.current_key_version = new_version
                self.key_rotation_last_time = now
                
                # Resetta la cache delle chiavi
                self.key_list_cache = set()
                self.key_list_cache_time = None
                
                logger.info(f"Rotazione chiavi completata. Nuova versione: {new_version}")
                return True
        except Exception as e:
            logger.error(f"Errore nella rotazione delle chiavi: {e}")
            return False

    def _update_command_stats(self, command: str, execution_time: float):
        """
        Aggiorna le statistiche dei comandi
        
        Args:
            command: Nome del comando Redis
            execution_time: Tempo di esecuzione in millisecondi
        """
        if command not in self.command_stats:
            self.command_stats[command] = {
                "count": 0,
                "total_time": 0,
                "min_time": float('inf'),
                "max_time": 0,
                "avg_time": 0
            }
        
        stats = self.command_stats[command]
        stats["count"] += 1
        stats["total_time"] += execution_time
        stats["min_time"] = min(stats["min_time"], execution_time)
        stats["max_time"] = max(stats["max_time"], execution_time)
        stats["avg_time"] = stats["total_time"] / stats["count"]

    async def get_stats(self) -> Dict[str, Any]:
        """
        Ottiene statistiche di utilizzo Redis
        
        Returns:
            Dict[str, Any]: Statistiche di utilizzo
        """
        if not self.is_connected:
            return {"status": "offline"}
        
        # Ottieni l'ultimo stato di salute o esegui un controllo
        if not self.last_health_check or (datetime.now() - self.last_health_check).seconds > 60:
            await self.health_check()
        
        stats = {
            "health": self.health_status,
            "commands": self.command_stats,
            "key_stats": {
                "current_version": self.current_key_version,
                "last_rotation": self.key_rotation_last_time.isoformat() if self.key_rotation_last_time else None,
                "rotation_interval_days": self.key_rotation_interval
            }
        }
        
        # Ottieni statistiche sulle chiavi
        try:
            async with await self._get_redis() as r:
                # Conta le chiavi per ogni versione
                key_counts = {}
                
                if self.key_rotation_enabled:
                    for version in range(1, self.current_key_version + 1):
                        count = len(await r.keys(f"{self.key_prefix}:v{version}:*"))
                        key_counts[f"v{version}"] = count
                else:
                    count = len(await r.keys(f"{self.key_prefix}:*"))
                    key_counts["total"] = count
                
                stats["key_stats"]["counts"] = key_counts
                
            return stats
        except Exception as e:
            logger.error(f"Errore nel recupero delle statistiche Redis: {e}")
            return {"status": "error", "error": str(e)}

    async def clear_expired_keys(self) -> int:
        """
        Pulisce le chiavi scadute
        
        Returns:
            int: Numero di chiavi eliminate
        """
        if not self.is_connected:
            return 0
        
        try:
            async with await self._get_redis() as r:
                # Ottieni tutte le chiavi con il prefisso
                keys = await r.keys(f"{self.key_prefix}*")
                
                # Verifica TTL per ogni chiave
                expired = 0
                for key in keys:
                    ttl = await r.ttl(key)
                    if ttl == -1:  # Chiave senza TTL
                        continue
                    if ttl <= 0:  # Chiave scaduta
                        await r.delete(key)
                        expired += 1
                
                # Resetta la cache delle chiavi
                if expired > 0:
                    self.key_list_cache = set()
                    self.key_list_cache_time = None
                
                return expired
        except Exception as e:
            logger.error(f"Errore nella pulizia delle chiavi scadute: {e}")
            return 0

    async def memory_usage(self, key: str) -> int:
        """
        Ottiene l'utilizzo di memoria di una chiave
        
        Args:
            key: Chiave da verificare
            
        Returns:
            int: Memoria utilizzata in byte, -1 se errore
        """
        if not self.is_connected:
            return -1
        
        formatted_key = self._format_key(key)
        
        try:
            async with await self._get_redis() as r:
                # Controlla varianti della chiave
                variants = [
                    formatted_key,
                    f"{formatted_key}:json",
                    f"{formatted_key}:compressed",
                    f"{formatted_key}:json:compressed",
                    f"{formatted_key}:compressed:json"
                ]
                
                # Cerca l'utilizzo di memoria per tutte le possibili varianti
                for variant in variants:
                    if await r.exists(variant):
                        return await r.memory_usage(variant)
                
                return 0  # Chiave non esistente
        except Exception as e:
            logger.error(f"Errore nel recupero dell'utilizzo di memoria per la chiave {key}: {e}")
            return -1

class RedisError(Exception):
    """Eccezione per errori Redis"""
    pass 