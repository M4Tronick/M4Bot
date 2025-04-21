"""
Gestore della cache per M4Bot.

Questo modulo fornisce funzionalità di caching avanzate per migliorare 
le prestazioni dell'applicazione.
"""

import time
import json
import pickle
import logging
import asyncio
import hashlib
from typing import Dict, List, Any, Optional, Union, Callable, Tuple
from datetime import datetime, timedelta
from functools import wraps

# Configurazione logging
logger = logging.getLogger('m4bot.cache')

class CacheItem:
    """Rappresenta un elemento nella cache con metadati."""
    
    def __init__(self, key: str, value: Any, ttl: int = 300):
        """
        Inizializza un elemento della cache.
        
        Args:
            key: Chiave di cache
            value: Valore da memorizzare
            ttl: Tempo di vita in secondi (default: 5 minuti)
        """
        self.key = key
        self.value = value
        self.ttl = ttl
        self.created_at = time.time()
        self.last_accessed = time.time()
        self.access_count = 0
    
    def is_expired(self) -> bool:
        """Verifica se l'elemento è scaduto."""
        return time.time() > (self.created_at + self.ttl)
    
    def access(self) -> Any:
        """Accede all'elemento, aggiorna i metadati e restituisce il valore."""
        self.last_accessed = time.time()
        self.access_count += 1
        return self.value
    
    def get_metadata(self) -> Dict[str, Any]:
        """Ottiene i metadati dell'elemento."""
        return {
            'key': self.key,
            'ttl': self.ttl,
            'created_at': datetime.fromtimestamp(self.created_at).isoformat(),
            'last_accessed': datetime.fromtimestamp(self.last_accessed).isoformat(),
            'access_count': self.access_count,
            'expired': self.is_expired(),
            'age': int(time.time() - self.created_at)
        }


class CacheManager:
    """Gestore della cache con supporto per diverse strategie di scadenza e pulizia."""
    
    def __init__(self):
        """Inizializza il gestore della cache."""
        self.cache = {}  # Tipo Dict[str, CacheItem]
        self.stats = {
            'hits': 0,
            'misses': 0,
            'size': 0,
            'evictions': 0,
            'expire_runs': 0
        }
        self.max_size = 1000  # Dimensione massima della cache
        self.cleanup_threshold = 0.8  # Soglia per la pulizia (% della dimensione massima)
        self.cleanup_percentage = 0.2  # Percentuale di elementi da rimuovere durante la pulizia
        self.last_cleanup = time.time()
        self.cleanup_interval = 60  # Intervallo minimo in secondi tra le pulizie
        
        # Avvia un task per la pulizia periodica
        asyncio.create_task(self._periodic_cleanup())
    
    async def _periodic_cleanup(self):
        """Task per la pulizia periodica della cache."""
        while True:
            try:
                await asyncio.sleep(300)  # Controlla ogni 5 minuti
                self.cleanup()
            except Exception as e:
                logger.error(f"Errore nella pulizia periodica della cache: {e}")
                await asyncio.sleep(600)  # Aspetta 10 minuti in caso di errore
    
    def get(self, key: str) -> Optional[Any]:
        """
        Ottiene un valore dalla cache.
        
        Args:
            key: Chiave di cache
            
        Returns:
            Any: Valore memorizzato, o None se non trovato o scaduto
        """
        cache_item = self.cache.get(key)
        
        if not cache_item:
            self.stats['misses'] += 1
            return None
        
        if cache_item.is_expired():
            self.remove(key)
            self.stats['misses'] += 1
            return None
        
        self.stats['hits'] += 1
        return cache_item.access()
    
    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """
        Memorizza un valore nella cache.
        
        Args:
            key: Chiave di cache
            value: Valore da memorizzare
            ttl: Tempo di vita in secondi
            
        Returns:
            bool: True se l'operazione è riuscita
        """
        # Controlla se è necessario eseguire la pulizia
        current_size = len(self.cache)
        if current_size >= int(self.max_size * self.cleanup_threshold):
            self.cleanup()
        
        # Memorizza il valore
        self.cache[key] = CacheItem(key, value, ttl)
        self.stats['size'] = len(self.cache)
        return True
    
    def remove(self, key: str) -> bool:
        """
        Rimuove un elemento dalla cache.
        
        Args:
            key: Chiave di cache
            
        Returns:
            bool: True se l'elemento è stato trovato e rimosso
        """
        if key in self.cache:
            del self.cache[key]
            self.stats['size'] = len(self.cache)
            return True
        return False
    
    def clear(self) -> None:
        """Cancella completamente la cache."""
        self.cache = {}
        self.stats['size'] = 0
        logger.info("Cache completamente svuotata")
    
    def cleanup(self) -> int:
        """
        Esegue la pulizia della cache rimuovendo elementi scaduti e, se necessario, quelli meno utilizzati.
        
        Returns:
            int: Numero di elementi rimossi
        """
        now = time.time()
        
        # Limita la frequenza delle pulizie
        if now - self.last_cleanup < self.cleanup_interval:
            return 0
        
        self.last_cleanup = now
        self.stats['expire_runs'] += 1
        removed_count = 0
        
        # Prima rimuovi gli elementi scaduti
        expired_keys = [k for k, v in self.cache.items() if v.is_expired()]
        for key in expired_keys:
            self.remove(key)
            removed_count += 1
        
        # Se necessario, rimuovi anche elementi in base a LRU (Least Recently Used)
        current_size = len(self.cache)
        if current_size > self.max_size:
            # Calcola quanti elementi rimuovere
            to_remove = int(current_size * self.cleanup_percentage)
            
            # Ordina gli elementi per ultimo accesso
            items = sorted(
                self.cache.items(), 
                key=lambda x: x[1].last_accessed
            )
            
            # Rimuovi gli elementi meno recentemente utilizzati
            for key, _ in items[:to_remove]:
                self.remove(key)
                removed_count += 1
                self.stats['evictions'] += 1
        
        logger.info(f"Pulizia cache completata: {removed_count} elementi rimossi, {len(self.cache)} rimanenti")
        return removed_count
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Ottiene statistiche sulla cache.
        
        Returns:
            Dict[str, Any]: Statistiche della cache
        """
        hit_ratio = 0
        total_requests = self.stats['hits'] + self.stats['misses']
        if total_requests > 0:
            hit_ratio = (self.stats['hits'] / total_requests) * 100
        
        return {
            'hits': self.stats['hits'],
            'misses': self.stats['misses'],
            'size': self.stats['size'],
            'max_size': self.max_size,
            'evictions': self.stats['evictions'],
            'hit_ratio': round(hit_ratio, 2),
            'items': len(self.cache),
            'expire_runs': self.stats['expire_runs'],
            'last_cleanup': datetime.fromtimestamp(self.last_cleanup).isoformat() if self.last_cleanup else None
        }
    
    def get_keys(self, pattern: str = None) -> List[str]:
        """
        Ottiene le chiavi nella cache, opzionalmente filtrate per pattern.
        
        Args:
            pattern: Pattern per filtrare le chiavi
            
        Returns:
            List[str]: Lista di chiavi
        """
        if pattern:
            return [k for k in self.cache.keys() if pattern in k]
        return list(self.cache.keys())
    
    def get_items_metadata(self, limit: int = 100, pattern: str = None) -> List[Dict[str, Any]]:
        """
        Ottiene metadati degli elementi nella cache.
        
        Args:
            limit: Numero massimo di elementi da restituire
            pattern: Pattern per filtrare le chiavi
            
        Returns:
            List[Dict[str, Any]]: Metadati degli elementi
        """
        items = []
        
        # Filtra le chiavi se necessario
        keys = self.get_keys(pattern)
        
        # Limita il numero di elementi
        keys = keys[:limit]
        
        # Ottieni i metadati
        for key in keys:
            if key in self.cache:
                items.append(self.cache[key].get_metadata())
        
        return items


# Istanza globale del gestore della cache
_cache_manager = None

def get_cache_manager() -> CacheManager:
    """
    Ottiene l'istanza globale del gestore della cache.
    
    Returns:
        CacheManager: Istanza del gestore della cache
    """
    global _cache_manager
    
    if _cache_manager is None:
        _cache_manager = CacheManager()
    
    return _cache_manager

def cached(ttl: int = 300):
    """
    Decorator per memorizzare nella cache i risultati di funzioni e metodi.
    
    Args:
        ttl: Tempo di vita in secondi (default: 5 minuti)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Ottieni il gestore della cache
            cache_manager = get_cache_manager()
            
            # Crea una chiave unica basata su funzione, argomenti e parametri
            key_parts = [
                func.__module__,
                func.__name__,
                str(args),
                str(sorted(kwargs.items()))
            ]
            cache_key = hashlib.md5(":".join(key_parts).encode()).hexdigest()
            
            # Controlla se il risultato è nella cache
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Esegui la funzione
            result = await func(*args, **kwargs)
            
            # Memorizza il risultato
            cache_manager.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    
    return decorator 