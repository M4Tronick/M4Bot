"""
Framework per l'architettura a microservizi di M4Bot

Questo modulo fornisce le componenti base per implementare un'architettura
a microservizi scalabile e resiliente. Include:

- Registry di servizi con scoperta dinamica
- Comunicazione asincrona tra servizi
- Bilanciamento del carico
- Circuit breaker per la tolleranza ai guasti
- Monitoraggio dello stato di salute
- Scalabilità automatica
"""

import asyncio
import json
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import aiohttp
import pika
from prometheus_client import Counter, Gauge, start_http_server

# Configurazione del logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("microservice_framework")

# Metriche Prometheus
SERVICE_REQUESTS = Counter("service_requests_total", "Numero totale di richieste al servizio", ["service_name"])
SERVICE_ERRORS = Counter("service_errors_total", "Numero totale di errori del servizio", ["service_name"])
SERVICE_LATENCY = Gauge("service_latency_seconds", "Latenza del servizio in secondi", ["service_name"])
CIRCUIT_STATE = Gauge("circuit_breaker_state", "Stato del circuit breaker (0=chiuso, 1=aperto, 2=semi-aperto)", ["service_name"])
ACTIVE_INSTANCES = Gauge("service_active_instances", "Numero di istanze attive per servizio", ["service_name"])

class ServiceStatus(Enum):
    """Stati possibili per un servizio."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"

class CircuitState(Enum):
    """Stati possibili per il circuit breaker."""
    CLOSED = 0  # Funzionamento normale
    OPEN = 1    # Non permette richieste
    HALF_OPEN = 2  # Test di ripristino

@dataclass
class ServiceInstance:
    """Rappresenta un'istanza di un servizio."""
    id: str
    name: str
    host: str
    port: int
    version: str
    status: ServiceStatus = ServiceStatus.STARTING
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_heartbeat: float = field(default_factory=time.time)

@dataclass
class CircuitBreaker:
    """Implementa il pattern Circuit Breaker per la resilienza."""
    failure_threshold: int = 5
    reset_timeout: float = 30.0
    half_open_max_calls: int = 3
    
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    last_failure_time: float = 0
    half_open_calls: int = 0
    
    def record_success(self):
        """Registra una chiamata riuscita."""
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.half_open_calls = 0
                logger.info("Circuit breaker tornato a CLOSED dopo successi in HALF_OPEN")
    
    def record_failure(self):
        """Registra un fallimento e potenzialmente apre il circuito."""
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning("Circuit breaker passato a OPEN")
        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.half_open_calls = 0
            logger.warning("Circuit breaker tornato a OPEN dopo fallimento in HALF_OPEN")
    
    def allow_request(self) -> bool:
        """Determina se permettere una richiesta in base allo stato del circuito."""
        if self.state == CircuitState.CLOSED:
            return True
        
        if self.state == CircuitState.OPEN:
            # Verifica se è tempo di tentare il ripristino
            if time.time() - self.last_failure_time > self.reset_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                logger.info("Circuit breaker passato a HALF_OPEN")
                return True
            return False
        
        # Stato HALF_OPEN - consente un numero limitato di richieste
        return self.half_open_calls < self.half_open_max_calls

class ServiceRegistry:
    """Registry centralizzato per la gestione e scoperta dei servizi."""
    
    def __init__(self):
        self._services: Dict[str, Dict[str, ServiceInstance]] = {}
        self._lock = asyncio.Lock()
    
    async def register(self, service: ServiceInstance) -> bool:
        """Registra un nuovo servizio nel registry."""
        async with self._lock:
            if service.name not in self._services:
                self._services[service.name] = {}
            
            self._services[service.name][service.id] = service
            logger.info(f"Servizio registrato: {service.name} (ID: {service.id})")
            ACTIVE_INSTANCES.labels(service_name=service.name).inc()
            return True
    
    async def unregister(self, service_name: str, service_id: str) -> bool:
        """Rimuove un servizio dal registry."""
        async with self._lock:
            if service_name in self._services and service_id in self._services[service_name]:
                del self._services[service_name][service_id]
                logger.info(f"Servizio rimosso: {service_name} (ID: {service_id})")
                
                if not self._services[service_name]:
                    del self._services[service_name]
                
                ACTIVE_INSTANCES.labels(service_name=service_name).dec()
                return True
            return False
    
    async def get_services(self, service_name: str) -> List[ServiceInstance]:
        """Restituisce tutte le istanze disponibili di un servizio."""
        async with self._lock:
            if service_name in self._services:
                return list(self._services[service_name].values())
            return []
    
    async def get_service(self, service_name: str) -> Optional[ServiceInstance]:
        """Restituisce un'istanza casuale di un servizio (bilanciamento del carico semplice)."""
        instances = await self.get_services(service_name)
        healthy_instances = [i for i in instances if i.status == ServiceStatus.HEALTHY]
        
        if healthy_instances:
            return random.choice(healthy_instances)
        return None
    
    async def update_status(self, service_name: str, service_id: str, status: ServiceStatus) -> bool:
        """Aggiorna lo stato di un servizio."""
        async with self._lock:
            if (service_name in self._services and 
                service_id in self._services[service_name]):
                self._services[service_name][service_id].status = status
                return True
            return False
    
    async def heartbeat(self, service_name: str, service_id: str) -> bool:
        """Aggiorna il timestamp dell'ultimo heartbeat di un servizio."""
        async with self._lock:
            if (service_name in self._services and 
                service_id in self._services[service_name]):
                self._services[service_name][service_id].last_heartbeat = time.time()
                return True
            return False
    
    async def clean_stale_services(self, max_age: float = 60.0) -> int:
        """Rimuove i servizi che non hanno inviato heartbeat recentemente."""
        now = time.time()
        to_remove = []
        
        async with self._lock:
            for service_name, instances in self._services.items():
                for service_id, instance in instances.items():
                    if now - instance.last_heartbeat > max_age:
                        to_remove.append((service_name, service_id))
            
            for service_name, service_id in to_remove:
                await self.unregister(service_name, service_id)
            
            return len(to_remove)

class MessageBroker:
    """Gestore per la comunicazione asincrona tra servizi."""
    
    def __init__(self, host: str = "localhost", port: int = 5672):
        self.host = host
        self.port = port
        self.connection = None
        self.channel = None
        self._consumers = {}
    
    async def connect(self):
        """Stabilisce la connessione con il message broker."""
        # In un'implementazione reale, useremmo una libreria asincrona
        # Per ora, simuliamo la connessione
        self.connection = {"host": self.host, "port": self.port}
        self.channel = {}
        logger.info(f"Connesso al message broker: {self.host}:{self.port}")
    
    async def publish(self, queue: str, message: Dict[str, Any]):
        """Pubblica un messaggio sulla coda specificata."""
        if not self.connection:
            await self.connect()
        
        # Simuliamo la pubblicazione
        message_json = json.dumps(message)
        logger.debug(f"Messaggio pubblicato su {queue}: {message_json}")
        
        # In un'implementazione reale:
        # await self.channel.basic_publish(
        #     exchange='',
        #     routing_key=queue,
        #     body=message_json
        # )
    
    async def subscribe(self, queue: str, callback: Callable[[Dict[str, Any]], None]):
        """Sottoscrive a una coda e definisce un callback per i messaggi ricevuti."""
        if not self.connection:
            await self.connect()
        
        self._consumers[queue] = callback
        logger.info(f"Sottoscritto alla coda: {queue}")
        
        # In un'implementazione reale:
        # await self.channel.basic_consume(
        #     queue=queue,
        #     on_message_callback=lambda ch, method, properties, body: callback(json.loads(body))
        # )
    
    async def close(self):
        """Chiude la connessione con il message broker."""
        self._consumers = {}
        self.channel = None
        self.connection = None
        logger.info("Connessione al message broker chiusa")

class MicroserviceFramework:
    """Framework principale per la creazione di microservizi."""
    
    def __init__(
        self,
        service_name: str,
        host: str = "0.0.0.0",
        port: int = 8000,
        registry_host: str = "localhost",
        registry_port: int = 8500,
        broker_host: str = "localhost",
        broker_port: int = 5672,
        version: str = "1.0.0",
    ):
        self.service_name = service_name
        self.host = host
        self.port = port
        self.version = version
        self.service_id = f"{service_name}-{uuid.uuid4()}"
        
        # Componenti principali
        self.registry = ServiceRegistry()
        self.message_broker = MessageBroker(broker_host, broker_port)
        
        # Stato del servizio
        self.instance = ServiceInstance(
            id=self.service_id,
            name=service_name,
            host=host,
            port=port,
            version=version,
        )
        
        # Circuit breakers per altri servizi
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Metriche e monitoring
        self.metrics_port = port + 1000  # Porta per Prometheus
        
        # Flag per il controllo del ciclo di vita
        self.running = False
    
    async def start(self):
        """Avvia il microservizio."""
        logger.info(f"Avvio del microservizio: {self.service_name} {self.version}")
        
        # Avvia il server per le metriche Prometheus
        start_http_server(self.metrics_port)
        logger.info(f"Server metriche Prometheus avviato sulla porta {self.metrics_port}")
        
        # Registra il servizio
        self.instance.status = ServiceStatus.STARTING
        await self.registry.register(self.instance)
        
        # Connetti al message broker
        await self.message_broker.connect()
        
        # Imposta lo stato su healthy e avvia il loop di heartbeat
        self.instance.status = ServiceStatus.HEALTHY
        await self.registry.update_status(self.service_name, self.service_id, self.instance.status)
        
        self.running = True
        asyncio.create_task(self._heartbeat_loop())
        
        logger.info(f"Microservizio {self.service_name} avviato e pronto")
    
    async def stop(self):
        """Ferma il microservizio."""
        if not self.running:
            return
        
        logger.info(f"Arresto del microservizio: {self.service_name}")
        
        self.running = False
        self.instance.status = ServiceStatus.STOPPING
        await self.registry.update_status(self.service_name, self.service_id, self.instance.status)
        
        # Chiudi le connessioni
        await self.message_broker.close()
        
        # Rimuovi il servizio dal registry
        await self.registry.unregister(self.service_name, self.service_id)
        
        logger.info(f"Microservizio {self.service_name} arrestato")
    
    async def _heartbeat_loop(self):
        """Loop che invia heartbeat periodici al registry."""
        while self.running:
            try:
                await self.registry.heartbeat(self.service_name, self.service_id)
                await asyncio.sleep(15)  # Invia heartbeat ogni 15 secondi
            except Exception as e:
                logger.error(f"Errore durante l'invio del heartbeat: {e}")
                await asyncio.sleep(5)  # Ritardo più breve in caso di errore
    
    async def call_service(self, service_name: str, endpoint: str, method: str = "GET", 
                          data: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        """Chiama un altro servizio tramite HTTP con circuit breaker."""
        # Recupera o crea un circuit breaker per il servizio
        if service_name not in self.circuit_breakers:
            self.circuit_breakers[service_name] = CircuitBreaker()
        
        circuit = self.circuit_breakers[service_name]
        CIRCUIT_STATE.labels(service_name=service_name).set(circuit.state.value)
        
        if not circuit.allow_request():
            logger.warning(f"Circuit breaker aperto per {service_name}, richiesta rifiutata")
            raise Exception(f"Service {service_name} circuit breaker open")
        
        # Trova un'istanza del servizio
        instance = await self.registry.get_service(service_name)
        if not instance:
            circuit.record_failure()
            CIRCUIT_STATE.labels(service_name=service_name).set(circuit.state.value)
            raise Exception(f"No healthy instances of service {service_name} available")
        
        # Prepara l'URL
        url = f"http://{instance.host}:{instance.port}/{endpoint.lstrip('/')}"
        
        # Misura la latenza
        start_time = time.time()
        
        try:
            # Esegui la richiesta HTTP
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, json=data, timeout=timeout) as response:
                    SERVICE_REQUESTS.labels(service_name=service_name).inc()
                    
                    response_data = await response.json()
                    
                    if response.status >= 400:
                        SERVICE_ERRORS.labels(service_name=service_name).inc()
                        circuit.record_failure()
                        CIRCUIT_STATE.labels(service_name=service_name).set(circuit.state.value)
                        raise Exception(f"Service error: {response.status} - {response_data}")
                    
                    # Registra il successo nel circuit breaker
                    circuit.record_success()
                    CIRCUIT_STATE.labels(service_name=service_name).set(circuit.state.value)
                    
                    return response_data
        except Exception as e:
            SERVICE_ERRORS.labels(service_name=service_name).inc()
            circuit.record_failure()
            CIRCUIT_STATE.labels(service_name=service_name).set(circuit.state.value)
            raise e
        finally:
            # Aggiorna la metrica di latenza
            latency = time.time() - start_time
            SERVICE_LATENCY.labels(service_name=service_name).set(latency)
    
    async def send_message(self, queue: str, message: Dict[str, Any]):
        """Invia un messaggio asincrono attraverso il message broker."""
        await self.message_broker.publish(queue, message)
    
    async def register_handler(self, queue: str, callback: Callable[[Dict[str, Any]], None]):
        """Registra un handler per i messaggi da una coda specifica."""
        await self.message_broker.subscribe(queue, callback)

# Esempio di utilizzo del framework
async def example():
    # Crea un'istanza del microservizio
    service = MicroserviceFramework(
        service_name="example-service",
        host="localhost",
        port=8080,
    )
    
    # Avvia il servizio
    await service.start()
    
    try:
        # Registra un handler per i messaggi
        async def handle_message(message):
            logger.info(f"Messaggio ricevuto: {message}")
        
        await service.register_handler("example-queue", handle_message)
        
        # Simula del lavoro
        for _ in range(3):
            await asyncio.sleep(2)
            
            # Invia un messaggio
            await service.send_message("example-queue", {
                "type": "example",
                "data": {"timestamp": time.time()}
            })
            
            # Chiama un altro servizio
            try:
                result = await service.call_service(
                    service_name="another-service",
                    endpoint="/api/example",
                    method="POST",
                    data={"foo": "bar"}
                )
                logger.info(f"Risultato chiamata: {result}")
            except Exception as e:
                logger.error(f"Errore chiamata servizio: {e}")
    
    finally:
        # Arresta il servizio
        await service.stop()

if __name__ == "__main__":
    # Esempio di esecuzione
    asyncio.run(example()) 