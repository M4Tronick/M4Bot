#!/usr/bin/env python3
"""
M4Bot - Architettura a Microservizi

Questo modulo implementa il framework base per l'architettura a microservizi di M4Bot.
Gestisce la comunicazione tra servizi, il discovery, l'autenticazione e il monitoraggio.
"""

import os
import sys
import json
import time
import uuid
import logging
import socket
import asyncio
import aiohttp
import hashlib
import hmac
import random
from typing import Dict, List, Any, Optional, Callable, Union, Set, Tuple
from datetime import datetime, timedelta
from functools import wraps
from dataclasses import dataclass, field, asdict

# Configurazione del logging
logger = logging.getLogger('m4bot.stability.microservices')

# Costanti per l'identificazione dei servizi
SERVICE_TYPES = {
    'web': 'frontend web',
    'api': 'api gateway',
    'bot': 'bot core',
    'db': 'database',
    'auth': 'authentication',
    'chat': 'chat handler',
    'commands': 'command processor',
    'rewards': 'reward system',
    'notifications': 'notification system',
    'monitoring': 'monitoring service',
    'scheduler': 'task scheduler',
    'integration': 'external integration'
}

# Stati dei servizi
class ServiceStatus:
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"
    UNKNOWN = "unknown"

@dataclass
class ServiceInfo:
    """Informazioni su un servizio attivo nel sistema."""
    id: str  # ID univoco del servizio
    type: str  # Tipo di servizio (da SERVICE_TYPES)
    name: str  # Nome descrittivo
    version: str  # Versione del servizio
    host: str  # Hostname del servizio
    port: int  # Porta del servizio
    status: str = ServiceStatus.UNKNOWN  # Stato attuale
    urls: Dict[str, str] = field(default_factory=dict)  # Endpoint del servizio
    metadata: Dict[str, Any] = field(default_factory=dict)  # Metadati aggiuntivi
    health_check_url: Optional[str] = None  # URL per health check
    last_seen: Optional[float] = None  # Timestamp ultimo aggiornamento
    capabilities: Set[str] = field(default_factory=set)  # Funzionalità offerte

    def to_dict(self) -> Dict[str, Any]:
        """Converte l'oggetto in un dizionario."""
        result = asdict(self)
        # Converte set a lista per la serializzazione
        result['capabilities'] = list(self.capabilities)
        return result

    def get_base_url(self) -> str:
        """Restituisce l'URL base del servizio."""
        protocol = "https" if self.metadata.get("secure", False) else "http"
        return f"{protocol}://{self.host}:{self.port}"
    
    def is_healthy(self) -> bool:
        """Verifica se il servizio è considerato operativo."""
        return self.status in [ServiceStatus.RUNNING, ServiceStatus.DEGRADED]
    
    def is_stale(self, max_age_seconds: int = 60) -> bool:
        """Verifica se il servizio non è aggiornato."""
        if self.last_seen is None:
            return True
        return (time.time() - self.last_seen) > max_age_seconds

# Registro globale dei servizi
class ServiceRegistry:
    """Registro per tenere traccia di tutti i servizi nel sistema."""
    
    def __init__(self):
        self.services: Dict[str, ServiceInfo] = {}
        self.service_types: Dict[str, List[str]] = {stype: [] for stype in SERVICE_TYPES}
        self._lock = asyncio.Lock()
    
    async def register(self, service: ServiceInfo) -> bool:
        """Registra un servizio nel registro."""
        async with self._lock:
            if service.id in self.services:
                # Aggiorna servizio esistente
                old_service = self.services[service.id]
                # Mantiene lo stato se non specificato
                if service.status == ServiceStatus.UNKNOWN:
                    service.status = old_service.status
            
            service.last_seen = time.time()
            self.services[service.id] = service
            
            # Aggiorna indice per tipo
            if service.type not in self.service_types:
                self.service_types[service.type] = []
            
            if service.id not in self.service_types[service.type]:
                self.service_types[service.type].append(service.id)
            
            logger.info(f"Servizio registrato: {service.name} (ID: {service.id}, Tipo: {service.type})")
            return True
    
    async def unregister(self, service_id: str) -> bool:
        """Rimuove un servizio dal registro."""
        async with self._lock:
            if service_id not in self.services:
                return False
            
            service = self.services[service_id]
            del self.services[service_id]
            
            # Aggiorna indice per tipo
            if service.type in self.service_types and service_id in self.service_types[service.type]:
                self.service_types[service.type].remove(service_id)
            
            logger.info(f"Servizio rimosso: {service.name} (ID: {service_id})")
            return True
    
    async def update_status(self, service_id: str, status: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Aggiorna lo stato di un servizio."""
        async with self._lock:
            if service_id not in self.services:
                return False
            
            self.services[service_id].status = status
            self.services[service_id].last_seen = time.time()
            
            if metadata:
                self.services[service_id].metadata.update(metadata)
            
            logger.debug(f"Stato servizio aggiornato - ID: {service_id}, Stato: {status}")
            return True
    
    def get_service(self, service_id: str) -> Optional[ServiceInfo]:
        """Restituisce le informazioni di un servizio specifico."""
        return self.services.get(service_id)
    
    def get_services_by_type(self, service_type: str) -> List[ServiceInfo]:
        """Restituisce tutti i servizi di un determinato tipo."""
        if service_type not in self.service_types:
            return []
        
        return [self.services[service_id] for service_id in self.service_types[service_type] 
                if service_id in self.services]
    
    def get_healthy_services_by_type(self, service_type: str) -> List[ServiceInfo]:
        """Restituisce i servizi operativi di un determinato tipo."""
        services = self.get_services_by_type(service_type)
        return [s for s in services if s.is_healthy()]
    
    async def cleanup_stale_services(self, max_age_seconds: int = 60) -> int:
        """Rimuove i servizi non aggiornati da tempo."""
        to_remove = []
        
        # Identifica i servizi da rimuovere
        for service_id, service in self.services.items():
            if service.is_stale(max_age_seconds):
                to_remove.append(service_id)
        
        # Rimuove i servizi
        removed = 0
        for service_id in to_remove:
            result = await self.unregister(service_id)
            if result:
                removed += 1
        
        if removed > 0:
            logger.info(f"Rimossi {removed} servizi non aggiornati")
        
        return removed
    
    def get_all_services(self) -> List[ServiceInfo]:
        """Restituisce tutti i servizi registrati."""
        return list(self.services.values())
    
    def find_service_by_capability(self, capability: str) -> List[ServiceInfo]:
        """Trova servizi che offrono una determinata funzionalità."""
        return [s for s in self.services.values() if capability in s.capabilities]

# Registro globale dei servizi (singleton)
service_registry = ServiceRegistry()

# Classe per la gestione del servizio corrente
class ServiceManager:
    """Gestisce il ciclo di vita e la registrazione del servizio corrente."""
    
    def __init__(self, service_type: str, service_name: str, version: str, port: int):
        """
        Inizializza un nuovo gestore del servizio.
        
        Args:
            service_type: Tipo di servizio (da SERVICE_TYPES)
            service_name: Nome descrittivo del servizio
            version: Versione del servizio
            port: Porta su cui il servizio è in ascolto
        """
        if service_type not in SERVICE_TYPES:
            logger.warning(f"Tipo di servizio non riconosciuto: {service_type}")
        
        self.service_id = f"{service_type}-{uuid.uuid4()}"
        self.service_type = service_type
        self.service_name = service_name
        self.version = version
        self.port = port
        self.host = self._get_hostname()
        self.status = ServiceStatus.STARTING
        self.capabilities: Set[str] = set()
        self.metadata: Dict[str, Any] = {
            "start_time": time.time(),
            "secure": False  # Impostare a True se HTTPS
        }
        self.urls: Dict[str, str] = {}
        self.health_check_url = None
        
        # Client per comunicazione con altri servizi
        self.client_session: Optional[aiohttp.ClientSession] = None
        
        # Riferimento al registro
        self.registry = service_registry
        
        # Task in background
        self.tasks: List[asyncio.Task] = []
        
        logger.info(f"Servizio inizializzato: {service_name} ({service_type})")
    
    def _get_hostname(self) -> str:
        """Ottiene l'hostname del servizio."""
        # In ambiente di produzione, utilizzare il nome del servizio DNS o l'IP del container
        try:
            hostname = socket.gethostname()
            # Verifica se hostname è risolvibile
            socket.gethostbyname(hostname)
            return hostname
        except:
            # Fallback all'IP di localhost
            return "127.0.0.1"
    
    def get_service_info(self) -> ServiceInfo:
        """Crea un oggetto ServiceInfo per il servizio."""
        return ServiceInfo(
            id=self.service_id,
            type=self.service_type,
            name=self.service_name,
            version=self.version,
            host=self.host,
            port=self.port,
            status=self.status,
            urls=self.urls,
            metadata=self.metadata,
            health_check_url=self.health_check_url,
            last_seen=time.time(),
            capabilities=self.capabilities
        )
    
    def add_capability(self, capability: str) -> None:
        """Aggiunge una funzionalità al servizio."""
        self.capabilities.add(capability)
    
    def add_url(self, name: str, path: str) -> None:
        """Aggiunge un endpoint al servizio."""
        base_url = f"http://{self.host}:{self.port}"
        url = f"{base_url}{path}"
        self.urls[name] = url
        
        if name == "health":
            self.health_check_url = url
    
    async def register(self) -> bool:
        """Registra il servizio nel registro globale."""
        service_info = self.get_service_info()
        return await self.registry.register(service_info)
    
    async def update_status(self, status: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Aggiorna lo stato del servizio."""
        self.status = status
        
        if metadata:
            self.metadata.update(metadata)
        
        return await self.registry.update_status(self.service_id, status, metadata)
    
    async def start(self) -> None:
        """Avvia il servizio e tutte le attività ausiliarie."""
        # Inizializza la sessione client
        if self.client_session is None:
            self.client_session = aiohttp.ClientSession()
        
        # Imposta il servizio come in avvio
        await self.update_status(ServiceStatus.STARTING)
        
        # Avvia task in background per heartbeat periodico
        heartbeat_task = asyncio.create_task(self._heartbeat_task())
        self.tasks.append(heartbeat_task)
        
        # Aggiorna lo stato a RUNNING
        await self.update_status(ServiceStatus.RUNNING)
        
        logger.info(f"Servizio avviato: {self.service_name} (ID: {self.service_id})")
    
    async def stop(self) -> None:
        """Ferma il servizio e tutte le attività ausiliarie."""
        # Imposta il servizio come in arresto
        await self.update_status(ServiceStatus.STOPPING)
        
        # Cancella tutti i task in background
        for task in self.tasks:
            if not task.done():
                task.cancel()
        
        # Attende che tutti i task terminino
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        
        # Chiude la sessione client
        if self.client_session:
            await self.client_session.close()
            self.client_session = None
        
        # Aggiorna lo stato a STOPPED
        await self.update_status(ServiceStatus.STOPPED)
        
        # Rimuovi dal registro
        await self.registry.unregister(self.service_id)
        
        logger.info(f"Servizio fermato: {self.service_name} (ID: {self.service_id})")
    
    async def _heartbeat_task(self) -> None:
        """Task in background per inviare heartbeat periodici."""
        try:
            while True:
                # Aggiorna il timestamp last_seen nel registro
                await self.registry.update_status(self.service_id, self.status)
                
                # Esegui pulizia di servizi non aggiornati
                await self.registry.cleanup_stale_services()
                
                # Attendi fino al prossimo heartbeat
                await asyncio.sleep(30)  # Ogni 30 secondi
        except asyncio.CancelledError:
            logger.debug("Task heartbeat cancellato")
        except Exception as e:
            logger.error(f"Errore nel task heartbeat: {e}")
    
    async def find_service(self, service_type: str) -> Optional[ServiceInfo]:
        """
        Trova un servizio del tipo specificato da utilizzare.
        Implementa un semplice algoritmo di bilanciamento del carico.
        """
        healthy_services = self.registry.get_healthy_services_by_type(service_type)
        
        if not healthy_services:
            return None
        
        if len(healthy_services) == 1:
            return healthy_services[0]
        
        # Selezione casuale per bilanciamento del carico semplice
        return random.choice(healthy_services)
    
    async def call_service(self, service_type: str, endpoint: str, method: str = "GET", 
                           params: Optional[Dict[str, Any]] = None, 
                           data: Optional[Any] = None,
                           headers: Optional[Dict[str, str]] = None,
                           timeout: int = 30) -> Optional[Any]:
        """
        Chiama un endpoint su un servizio del tipo specificato.
        Implementa retry automatico con fallback ad altri servizi dello stesso tipo.
        
        Args:
            service_type: Tipo di servizio da chiamare
            endpoint: Endpoint da chiamare (es. "/api/users")
            method: Metodo HTTP (GET, POST, PUT, DELETE)
            params: Parametri query string
            data: Dati da inviare (per POST/PUT)
            headers: Header HTTP personalizzati
            timeout: Timeout in secondi
            
        Returns:
            Any: Risposta dal servizio o None se fallisce
        """
        if self.client_session is None:
            self.client_session = aiohttp.ClientSession()
        
        # Trova un servizio disponibile
        service = await self.find_service(service_type)
        if not service:
            logger.error(f"Nessun servizio disponibile di tipo: {service_type}")
            return None
        
        # Costruisci l'URL completo
        base_url = service.get_base_url()
        url = f"{base_url}{endpoint}"
        
        # Header standard
        request_headers = {
            "Content-Type": "application/json",
            "X-Source-Service": self.service_id,
            "X-Service-Type": self.service_type
        }
        
        # Aggiungi header personalizzati
        if headers:
            request_headers.update(headers)
        
        # Converte i dati in JSON se necessario
        json_data = None
        if data is not None:
            if isinstance(data, (dict, list)):
                json_data = data
            else:
                request_headers["Content-Type"] = "text/plain"
        
        try:
            # Esegui la richiesta
            async with self.client_session.request(
                method, url,
                params=params,
                json=json_data if json_data is not None else None,
                data=data if json_data is None and data is not None else None,
                headers=request_headers,
                timeout=timeout
            ) as response:
                # Verifica il codice di stato
                if response.status >= 400:
                    logger.warning(f"Chiamata servizio fallita: {method} {url}, Status: {response.status}")
                    return None
                
                # Tenta di parsare come JSON
                try:
                    return await response.json()
                except:
                    # Altrimenti restituisci il testo
                    return await response.text()
        
        except asyncio.TimeoutError:
            logger.error(f"Timeout nella chiamata servizio: {method} {url}")
            return None
        except Exception as e:
            logger.error(f"Errore nella chiamata servizio: {method} {url} - {str(e)}")
            return None

# Gestione della comunicazione tra servizi

@dataclass
class Message:
    """Messaggio per la comunicazione tra servizi."""
    id: str  # ID univoco del messaggio
    source: str  # ID del servizio di origine
    target: Optional[str]  # ID del servizio di destinazione (None per broadcast)
    type: str  # Tipo di messaggio
    payload: Dict[str, Any]  # Payload del messaggio
    timestamp: float  # Timestamp di creazione
    reply_to: Optional[str] = None  # ID messaggio a cui si risponde

    @staticmethod
    def create(source: str, type: str, payload: Dict[str, Any], 
              target: Optional[str] = None, reply_to: Optional[str] = None) -> 'Message':
        """Crea un nuovo messaggio."""
        return Message(
            id=str(uuid.uuid4()),
            source=source,
            target=target,
            type=type,
            payload=payload,
            timestamp=time.time(),
            reply_to=reply_to
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte il messaggio in un dizionario."""
        return asdict(self)
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Message':
        """Crea un messaggio da un dizionario."""
        return Message(**data)

class MessageBroker:
    """Broker per la gestione dei messaggi tra servizi."""
    
    def __init__(self):
        self.subscribers: Dict[str, Set[Callable]] = {}
        self.service_listeners: Dict[str, Set[Callable]] = {}
        self._lock = asyncio.Lock()
    
    async def publish(self, message: Message) -> bool:
        """Pubblica un messaggio ai sottoscrittori interessati."""
        handlers_called = 0
        
        # Consegna ai sottoscrittori per tipo di messaggio
        if message.type in self.subscribers:
            for handler in self.subscribers[message.type]:
                try:
                    await handler(message)
                    handlers_called += 1
                except Exception as e:
                    logger.error(f"Errore nell'handler del messaggio {message.type}: {e}")
        
        # Consegna ai listener specifici per servizio di destinazione
        if message.target and message.target in self.service_listeners:
            for handler in self.service_listeners[message.target]:
                try:
                    await handler(message)
                    handlers_called += 1
                except Exception as e:
                    logger.error(f"Errore nel service listener per {message.target}: {e}")
        
        return handlers_called > 0
    
    async def subscribe(self, message_type: str, handler: Callable) -> None:
        """Sottoscrive un handler a un tipo di messaggio."""
        async with self._lock:
            if message_type not in self.subscribers:
                self.subscribers[message_type] = set()
            
            self.subscribers[message_type].add(handler)
    
    async def unsubscribe(self, message_type: str, handler: Callable) -> bool:
        """Rimuove un handler dalla sottoscrizione."""
        async with self._lock:
            if message_type in self.subscribers and handler in self.subscribers[message_type]:
                self.subscribers[message_type].remove(handler)
                return True
            return False
    
    async def register_service_listener(self, service_id: str, handler: Callable) -> None:
        """Registra un handler per messaggi destinati a un servizio specifico."""
        async with self._lock:
            if service_id not in self.service_listeners:
                self.service_listeners[service_id] = set()
            
            self.service_listeners[service_id].add(handler)
    
    async def unregister_service_listener(self, service_id: str, handler: Callable) -> bool:
        """Rimuove un handler per messaggi destinati a un servizio specifico."""
        async with self._lock:
            if service_id in self.service_listeners and handler in self.service_listeners[service_id]:
                self.service_listeners[service_id].remove(handler)
                return True
            return False

# Broker globale di messaggi (singleton)
message_broker = MessageBroker()

# Classe per la gestione del sistema di microservizi
class MicroserviceFramework:
    """Framework per la gestione del sistema di microservizi."""
    
    def __init__(self, service_type: str, service_name: str, version: str, port: int):
        """
        Inizializza il framework per un servizio.
        
        Args:
            service_type: Tipo di servizio
            service_name: Nome del servizio
            version: Versione del servizio
            port: Porta su cui il servizio è in ascolto
        """
        self.service_manager = ServiceManager(service_type, service_name, version, port)
        self.message_handlers: Dict[str, Callable] = {}
        self.is_running = False
    
    async def start(self) -> None:
        """Avvia il framework e registra il servizio."""
        # Avvia il service manager
        await self.service_manager.start()
        
        # Registra handler per messaggi
        for message_type, handler in self.message_handlers.items():
            await message_broker.subscribe(message_type, handler)
        
        # Registra handler per messaggi diretti
        await message_broker.register_service_listener(
            self.service_manager.service_id, self._handle_direct_message
        )
        
        self.is_running = True
        logger.info(f"Framework microservizi avviato per {self.service_manager.service_name}")
    
    async def stop(self) -> None:
        """Ferma il framework e rimuove il servizio dal registro."""
        self.is_running = False
        
        # Rimuovi handler messaggi
        for message_type, handler in self.message_handlers.items():
            await message_broker.unsubscribe(message_type, handler)
        
        # Rimuovi handler messaggi diretti
        await message_broker.unregister_service_listener(
            self.service_manager.service_id, self._handle_direct_message
        )
        
        # Ferma il service manager
        await self.service_manager.stop()
        
        logger.info(f"Framework microservizi fermato per {self.service_manager.service_name}")
    
    async def _handle_direct_message(self, message: Message) -> None:
        """Handler per messaggi diretti al servizio."""
        logger.debug(f"Messaggio diretto ricevuto: {message.type} da {message.source}")
        
        # Controlla se c'è un handler registrato per questo tipo di messaggio
        if message.type in self.message_handlers:
            try:
                await self.message_handlers[message.type](message)
            except Exception as e:
                logger.error(f"Errore nel gestore messaggio diretto {message.type}: {e}")
    
    def register_message_handler(self, message_type: str, handler: Callable) -> None:
        """Registra un handler per un tipo di messaggio."""
        self.message_handlers[message_type] = handler
        
        # Se già in esecuzione, registra immediatamente
        if self.is_running:
            asyncio.create_task(message_broker.subscribe(message_type, handler))
    
    async def send_message(self, type: str, payload: Dict[str, Any], 
                         target: Optional[str] = None, reply_to: Optional[str] = None) -> str:
        """
        Invia un messaggio ad altri servizi.
        
        Args:
            type: Tipo di messaggio
            payload: Payload del messaggio
            target: ID servizio destinatario (None per broadcast)
            reply_to: ID messaggio a cui si risponde
            
        Returns:
            str: ID del messaggio inviato
        """
        # Crea il messaggio
        message = Message.create(
            source=self.service_manager.service_id,
            type=type,
            payload=payload,
            target=target,
            reply_to=reply_to
        )
        
        # Pubblica il messaggio
        await message_broker.publish(message)
        
        return message.id
    
    async def call_service(self, service_type: str, endpoint: str, **kwargs) -> Optional[Any]:
        """Proxy al metodo call_service del ServiceManager."""
        return await self.service_manager.call_service(service_type, endpoint, **kwargs)
    
    def get_service_info(self) -> ServiceInfo:
        """Restituisce le informazioni sul servizio corrente."""
        return self.service_manager.get_service_info()
    
    async def update_status(self, status: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Aggiorna lo stato del servizio."""
        return await self.service_manager.update_status(status, metadata)
    
    def add_capability(self, capability: str) -> None:
        """Aggiunge una funzionalità al servizio."""
        self.service_manager.add_capability(capability)
    
    def add_url(self, name: str, path: str) -> None:
        """Aggiunge un endpoint al servizio."""
        self.service_manager.add_url(name, path)
    
    async def find_service(self, service_type: str) -> Optional[ServiceInfo]:
        """Trova un servizio del tipo specificato."""
        return await self.service_manager.find_service(service_type)
    
    async def find_service_by_capability(self, capability: str) -> Optional[ServiceInfo]:
        """Trova un servizio che offre una determinata funzionalità."""
        services = service_registry.find_service_by_capability(capability)
        
        if not services:
            return None
        
        # Filtra solo quelli healthy
        healthy = [s for s in services if s.is_healthy()]
        
        if not healthy:
            return None
        
        # Selezione casuale
        return random.choice(healthy)

# Utilità per l'autenticazione tra servizi

def generate_service_token(service_id: str, secret: str, expiry_seconds: int = 3600) -> str:
    """
    Genera un token JWT-like per l'autenticazione tra servizi.
    
    Args:
        service_id: ID del servizio
        secret: Chiave segreta condivisa
        expiry_seconds: Scadenza del token in secondi
        
    Returns:
        str: Token JWT-like
    """
    now = int(time.time())
    expiry = now + expiry_seconds
    
    # Crea il payload
    payload = {
        "iss": service_id,  # issuer
        "iat": now,  # issued at
        "exp": expiry,  # expiry
        "jti": str(uuid.uuid4())  # unique ID
    }
    
    # Codifica header e payload
    header = {"alg": "HS256", "typ": "JWT"}
    header_encoded = base64.urlsafe_b64encode(json.dumps(header).encode()).decode().rstrip("=")
    payload_encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    
    # Crea firma
    signature_input = f"{header_encoded}.{payload_encoded}".encode()
    signature = hmac.new(secret.encode(), signature_input, hashlib.sha256).digest()
    signature_encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    
    # Componi il token
    token = f"{header_encoded}.{payload_encoded}.{signature_encoded}"
    
    return token

def verify_service_token(token: str, secret: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Verifica un token di servizio.
    
    Args:
        token: Token da verificare
        secret: Chiave segreta condivisa
        
    Returns:
        Tuple[bool, Optional[Dict]]: (valido, payload)
    """
    try:
        # Dividi il token
        parts = token.split(".")
        if len(parts) != 3:
            return False, None
        
        header_encoded, payload_encoded, signature_encoded = parts
        
        # Verifica la firma
        signature_input = f"{header_encoded}.{payload_encoded}".encode()
        expected_signature = hmac.new(secret.encode(), signature_input, hashlib.sha256).digest()
        actual_signature = base64.urlsafe_b64decode(signature_encoded + "==")
        
        if not hmac.compare_digest(expected_signature, actual_signature):
            return False, None
        
        # Decodifica il payload
        payload_padded = payload_encoded + "=" * ((4 - len(payload_encoded) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_padded).decode())
        
        # Verifica la scadenza
        now = int(time.time())
        if payload.get("exp", 0) < now:
            return False, None
        
        return True, payload
    
    except Exception as e:
        logger.error(f"Errore nella verifica del token: {e}")
        return False, None

# Decoratore per proteggere gli endpoint con autenticazione servizio
def require_service_auth(secret: str):
    """
    Decoratore per richiedere autenticazione tra servizi negli endpoint.
    Da usare con framework web come Quart.
    
    Args:
        secret: Chiave segreta condivisa
    """
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            from quart import request, jsonify
            
            # Estrai il token dall'header
            auth_header = request.headers.get("Authorization")
            if not auth_header or not auth_header.startswith("Bearer "):
                return jsonify({"error": "Autenticazione richiesta"}), 401
            
            token = auth_header[7:]  # Rimuovi "Bearer "
            
            # Verifica il token
            valid, payload = verify_service_token(token, secret)
            
            if not valid:
                return jsonify({"error": "Token non valido o scaduto"}), 401
            
            # Passa il payload del token alla funzione
            kwargs["service_token"] = payload
            
            return await f(*args, **kwargs)
        return decorated_function
    return decorator

# Health check assistito
async def run_health_check(registry: ServiceRegistry, service_id: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Esegue un health check su un servizio.
    
    Args:
        registry: Registro dei servizi
        service_id: ID del servizio da controllare
        
    Returns:
        Tuple[bool, Dict]: (healthy, dettagli)
    """
    service = registry.get_service(service_id)
    if not service:
        return False, {"error": "Servizio non trovato"}
    
    if not service.health_check_url:
        return False, {"error": "Health check URL non disponibile"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(service.health_check_url, timeout=5) as response:
                if response.status != 200:
                    return False, {"status": response.status, "message": "Health check fallito"}
                
                data = await response.json()
                return True, data
    
    except asyncio.TimeoutError:
        return False, {"error": "Timeout nel health check"}
    except Exception as e:
        return False, {"error": str(e)}

# Sistema di monitoraggio e metriche
class MetricsCollector:
    """Raccoglie metriche dai servizi per monitoraggio e diagnostica."""
    
    def __init__(self):
        self.metrics: Dict[str, Dict[str, List[Tuple[float, Any]]]] = {}
        self._lock = asyncio.Lock()
    
    async def record_metric(self, service_id: str, metric_name: str, value: Any) -> None:
        """
        Registra una metrica per un servizio.
        
        Args:
            service_id: ID del servizio
            metric_name: Nome della metrica
            value: Valore della metrica
        """
        async with self._lock:
            if service_id not in self.metrics:
                self.metrics[service_id] = {}
            
            if metric_name not in self.metrics[service_id]:
                self.metrics[service_id][metric_name] = []
            
            # Aggiungi la metrica con timestamp
            self.metrics[service_id][metric_name].append((time.time(), value))
            
            # Limita la dimensione della cronologia (mantieni ultimi 100 punti)
            if len(self.metrics[service_id][metric_name]) > 100:
                self.metrics[service_id][metric_name] = self.metrics[service_id][metric_name][-100:]
    
    async def get_latest_metric(self, service_id: str, metric_name: str) -> Optional[Any]:
        """Restituisce l'ultimo valore di una metrica."""
        async with self._lock:
            if (service_id in self.metrics and 
                metric_name in self.metrics[service_id] and 
                self.metrics[service_id][metric_name]):
                return self.metrics[service_id][metric_name][-1][1]
            return None
    
    async def get_metric_history(self, service_id: str, metric_name: str, 
                               minutes: int = 5) -> List[Tuple[float, Any]]:
        """Restituisce la cronologia di una metrica."""
        now = time.time()
        cutoff = now - (minutes * 60)
        
        async with self._lock:
            if (service_id in self.metrics and 
                metric_name in self.metrics[service_id]):
                return [(ts, val) for ts, val in self.metrics[service_id][metric_name] 
                       if ts >= cutoff]
            return []
    
    async def get_service_metrics(self, service_id: str) -> Dict[str, Any]:
        """Restituisce tutte le metriche per un servizio."""
        result = {}
        
        async with self._lock:
            if service_id in self.metrics:
                for metric_name, values in self.metrics[service_id].items():
                    if values:
                        result[metric_name] = values[-1][1]  # Ultimo valore
        
        return result
    
    async def cleanup_old_metrics(self, max_age_minutes: int = 60) -> int:
        """Rimuove metriche vecchie."""
        now = time.time()
        cutoff = now - (max_age_minutes * 60)
        removed = 0
        
        async with self._lock:
            for service_id in list(self.metrics.keys()):
                for metric_name in list(self.metrics[service_id].keys()):
                    # Filtra le metriche più recenti del cutoff
                    new_values = [(ts, val) for ts, val in self.metrics[service_id][metric_name] 
                                 if ts >= cutoff]
                    
                    removed += len(self.metrics[service_id][metric_name]) - len(new_values)
                    self.metrics[service_id][metric_name] = new_values
                    
                    # Rimuovi la metrica se vuota
                    if not self.metrics[service_id][metric_name]:
                        del self.metrics[service_id][metric_name]
                
                # Rimuovi il servizio se non ha più metriche
                if not self.metrics[service_id]:
                    del self.metrics[service_id]
        
        return removed

# Collector globale per le metriche (singleton)
metrics_collector = MetricsCollector()

# Task in background per pulizia e manutenzione automatica
async def maintenance_task():
    """Task per la manutenzione periodica del sistema."""
    try:
        while True:
            # Pulisci servizi non aggiornati
            await service_registry.cleanup_stale_services(max_age_seconds=120)
            
            # Pulisci metriche vecchie
            await metrics_collector.cleanup_old_metrics(max_age_minutes=120)
            
            # Attendi fino al prossimo ciclo
            await asyncio.sleep(60)  # Ogni minuto
    except asyncio.CancelledError:
        logger.debug("Task manutenzione cancellato")
    except Exception as e:
        logger.error(f"Errore nel task manutenzione: {e}")

# Funzione di inizializzazione del framework
def initialize_framework() -> None:
    """Inizializza il framework di microservizi."""
    # Avvia il task di manutenzione
    asyncio.create_task(maintenance_task())
    
    logger.info("Framework di microservizi inizializzato")

# Inizializzazione del modulo
if __name__ != "__main__":
    logger.info("Modulo architettura microservizi caricato") 