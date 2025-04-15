"""
Architettura a Microservizi per M4Bot

Questo modulo fornisce l'infrastruttura per gestire l'architettura a microservizi di M4Bot,
consentendo una migliore scalabilità, isolamento dei componenti e resilienza.
"""

import os
import sys
import json
import time
import uuid
import asyncio
import logging
import signal
import socket
import threading
import multiprocessing
from typing import Dict, List, Any, Optional, Callable, Tuple, Union
from datetime import datetime
from enum import Enum
import aiohttp
import zmq
import zmq.asyncio
from quart import Quart, jsonify, request, websocket, abort
from dataclasses import dataclass, field, asdict
import yaml

# Configurazione logger
logger = logging.getLogger('m4bot.services')

# Definizione tipi di servizio
class ServiceType(Enum):
    WEB = 'web'              # Interfaccia web
    BOT = 'bot'              # Core del bot
    CHAT = 'chat'            # Gestione chat
    COMMANDS = 'commands'    # Processamento comandi
    DATABASE = 'database'    # Accesso al DB
    AUTH = 'auth'            # Autenticazione
    INTEGRATION = 'integration'  # Integrazioni esterne
    ANALYTICS = 'analytics'  # Analisi dati
    WEBHOOK = 'webhook'      # Gestione webhook
    MODERATION = 'moderation'  # Moderazione contenuti
    CACHE = 'cache'          # Caching
    REWARDS = 'rewards'      # Sistema ricompense
    NOTIFICATIONS = 'notifications'  # Sistema notifiche
    WORKER = 'worker'        # Worker generico
    SCHEDULER = 'scheduler'  # Pianificazione attività
    UTILITY = 'utility'      # Utilità varie

# Stati del servizio
class ServiceStatus(Enum):
    STARTING = 'starting'
    RUNNING = 'running'
    STOPPING = 'stopping'
    STOPPED = 'stopped'
    ERROR = 'error'
    RESTARTING = 'restarting'
    DEGRADED = 'degraded'
    MAINTENANCE = 'maintenance'

@dataclass
class ServiceInfo:
    id: str
    type: ServiceType
    name: str
    host: str = 'localhost'
    port: int = 0
    pid: int = 0
    status: ServiceStatus = ServiceStatus.STOPPED
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    health_endpoint: Optional[str] = None
    started_at: Optional[str] = None
    last_heartbeat: Optional[str] = None
    version: str = '1.0.0'
    restart_count: int = 0
    max_restarts: int = 5
    auto_restart: bool = True

@dataclass
class ServiceMessage:
    sender: str
    type: str
    data: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    ttl: int = 60  # Tempo di vita in secondi

class ServiceRegistry:
    """Registro centrale dei servizi disponibili."""
    
    def __init__(self, registry_file: Optional[str] = None):
        self.services: Dict[str, ServiceInfo] = {}
        self.registry_file = registry_file or os.path.expanduser('~/.m4bot/services.json')
        self.lock = threading.RLock()
        self._load_registry()
    
    def _load_registry(self):
        """Carica il registro dei servizi da file."""
        if os.path.exists(self.registry_file):
            try:
                with open(self.registry_file, 'r') as f:
                    data = json.load(f)
                
                with self.lock:
                    for service_data in data.get('services', []):
                        service_id = service_data.get('id')
                        if service_id:
                            # Converte tipi Enum da stringhe
                            if 'type' in service_data:
                                service_data['type'] = ServiceType(service_data['type'])
                            if 'status' in service_data:
                                service_data['status'] = ServiceStatus(service_data['status'])
                            
                            self.services[service_id] = ServiceInfo(**service_data)
                
                logger.info(f"Registro servizi caricato: {len(self.services)} servizi trovati")
            except Exception as e:
                logger.error(f"Errore nel caricamento del registro servizi: {e}")
                # Inizializza con un registro vuoto
                self.services = {}
        else:
            logger.info("Registro servizi non trovato, inizializzazione nuovo registro")
            # Crea la directory se non esiste
            os.makedirs(os.path.dirname(self.registry_file), exist_ok=True)
            self._save_registry()
    
    def _save_registry(self):
        """Salva il registro dei servizi su file."""
        try:
            # Converti ServiceInfo in dizionari e gestisci Enum
            services_data = []
            with self.lock:
                for service in self.services.values():
                    service_dict = asdict(service)
                    # Converti Enum in stringhe
                    if 'type' in service_dict and isinstance(service_dict['type'], ServiceType):
                        service_dict['type'] = service_dict['type'].value
                    if 'status' in service_dict and isinstance(service_dict['status'], ServiceStatus):
                        service_dict['status'] = service_dict['status'].value
                    services_data.append(service_dict)
            
            # Scrivi su file
            with open(self.registry_file, 'w') as f:
                json.dump({'services': services_data}, f, indent=2)
            
            logger.debug("Registro servizi salvato con successo")
        except Exception as e:
            logger.error(f"Errore nel salvataggio del registro servizi: {e}")
    
    def register_service(self, service: ServiceInfo) -> bool:
        """Registra un nuovo servizio."""
        with self.lock:
            # Verifica se esiste già
            if service.id in self.services:
                logger.warning(f"Servizio {service.id} già registrato, aggiornamento")
            
            # Aggiungi il servizio
            self.services[service.id] = service
            self._save_registry()
            
            logger.info(f"Servizio registrato: {service.id} ({service.name})")
            return True
    
    def unregister_service(self, service_id: str) -> bool:
        """Rimuove un servizio dal registro."""
        with self.lock:
            if service_id in self.services:
                del self.services[service_id]
                self._save_registry()
                logger.info(f"Servizio rimosso: {service_id}")
                return True
            else:
                logger.warning(f"Tentativo di rimozione servizio non registrato: {service_id}")
                return False
    
    def get_service(self, service_id: str) -> Optional[ServiceInfo]:
        """Ottiene informazioni su un servizio specifico."""
        with self.lock:
            return self.services.get(service_id)
    
    def find_services(self, service_type: Optional[ServiceType] = None, 
                    status: Optional[ServiceStatus] = None) -> List[ServiceInfo]:
        """Trova servizi in base a tipo e/o stato."""
        with self.lock:
            result = []
            for service in self.services.values():
                match_type = service_type is None or service.type == service_type
                match_status = status is None or service.status == status
                
                if match_type and match_status:
                    result.append(service)
            
            return result
    
    def update_service_status(self, service_id: str, status: ServiceStatus, 
                            metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Aggiorna lo stato di un servizio."""
        with self.lock:
            if service_id in self.services:
                service = self.services[service_id]
                old_status = service.status
                service.status = status
                service.last_heartbeat = datetime.now().isoformat()
                
                if metadata:
                    service.metadata.update(metadata)
                
                self._save_registry()
                logger.info(f"Stato servizio {service_id} aggiornato: {old_status.value} -> {status.value}")
                return True
            else:
                logger.warning(f"Tentativo di aggiornamento servizio non registrato: {service_id}")
                return False
    
    def get_dependency_graph(self) -> Dict[str, List[str]]:
        """Restituisce il grafo delle dipendenze tra servizi."""
        with self.lock:
            dependency_graph = {}
            for service_id, service in self.services.items():
                dependency_graph[service_id] = service.dependencies
            
            return dependency_graph
    
    def check_service_health(self, service_id: str) -> Tuple[bool, Dict[str, Any]]:
        """Verifica lo stato di salute di un servizio."""
        service = self.get_service(service_id)
        if not service:
            return False, {"error": "Servizio non trovato"}
        
        # Verifica se il servizio ha un endpoint di health
        if not service.health_endpoint:
            # Verifica solo in base allo stato e all'ultimo heartbeat
            if service.status != ServiceStatus.RUNNING:
                return False, {"error": f"Servizio in stato {service.status.value}"}
            
            # Controlla l'ultimo heartbeat
            if service.last_heartbeat:
                try:
                    last_hb = datetime.fromisoformat(service.last_heartbeat)
                    now = datetime.now()
                    if (now - last_hb).total_seconds() > 60:
                        return False, {"error": "Heartbeat obsoleto"}
                except Exception:
                    pass
            
            return True, {"status": "Ok", "message": "Servizio attivo"}
        
        # Se c'è un endpoint di health, chiamalo
        try:
            # TODO: Implementare chiamata all'endpoint
            return True, {"status": "Ok", "message": "Health check eseguito con successo"}
        except Exception as e:
            return False, {"error": f"Health check fallito: {str(e)}"}

class ServiceBus:
    """Bus di comunicazione tra servizi basato su ZeroMQ."""
    
    def __init__(self, service_id: str, registry: ServiceRegistry, 
                 bus_address: str = 'tcp://127.0.0.1:5555'):
        self.service_id = service_id
        self.registry = registry
        self.bus_address = bus_address
        
        # Inizializza contesto ZeroMQ asincrono
        self.context = zmq.asyncio.Context()
        
        # Socket per pubblicazione messaggi
        self.publisher = self.context.socket(zmq.PUB)
        self.publisher.connect(bus_address)
        
        # Socket per ricezione messaggi
        self.subscriber = self.context.socket(zmq.SUB)
        self.subscriber.connect(bus_address)
        
        # Registra per ricevere messaggi destinati a questo servizio e broadcast
        self.subscriber.setsockopt_string(zmq.SUBSCRIBE, self.service_id)
        self.subscriber.setsockopt_string(zmq.SUBSCRIBE, "broadcast")
        
        # Gestori messaggi
        self.message_handlers: Dict[str, Callable] = {}
        
        # Task di ascolto
        self.listen_task = None
        self.running = False
    
    async def start(self):
        """Avvia il bus di servizio."""
        if self.running:
            return
        
        self.running = True
        self.listen_task = asyncio.create_task(self._listen_for_messages())
        logger.info(f"Service bus avviato per {self.service_id}")
    
    async def stop(self):
        """Ferma il bus di servizio."""
        if not self.running:
            return
        
        self.running = False
        if self.listen_task:
            self.listen_task.cancel()
            try:
                await self.listen_task
            except asyncio.CancelledError:
                pass
        
        # Chiudi i socket
        self.publisher.close()
        self.subscriber.close()
        
        logger.info(f"Service bus fermato per {self.service_id}")
    
    async def publish(self, message_type: str, data: Dict[str, Any], 
                     target: Optional[str] = None, correlation_id: Optional[str] = None,
                     reply_to: Optional[str] = None) -> str:
        """Pubblica un messaggio sul bus."""
        # Crea il messaggio
        message = ServiceMessage(
            sender=self.service_id,
            type=message_type,
            data=data,
            correlation_id=correlation_id,
            reply_to=reply_to or self.service_id
        )
        
        # Converti in JSON
        message_json = json.dumps(asdict(message))
        
        # Invia il messaggio
        topic = target or "broadcast"
        await self.publisher.send_multipart([topic.encode(), message_json.encode()])
        
        logger.debug(f"Messaggio pubblicato: {message_type} -> {topic}")
        return message.id
    
    async def publish_and_wait(self, message_type: str, data: Dict[str, Any], 
                              target: str, timeout: int = 10) -> Optional[ServiceMessage]:
        """Pubblica un messaggio e attende una risposta."""
        # Crea un ID di correlazione unico
        correlation_id = str(uuid.uuid4())
        
        # Crea una future per la risposta
        response_future = asyncio.Future()
        
        # Registra un handler temporaneo per la risposta
        async def response_handler(message: ServiceMessage):
            if not response_future.done():
                response_future.set_result(message)
        
        # Registra l'handler per questo ID di correlazione
        temp_handler_key = f"_temp_{correlation_id}"
        self.register_handler(temp_handler_key, response_handler)
        
        try:
            # Pubblica il messaggio
            await self.publish(
                message_type=message_type,
                data=data,
                target=target,
                correlation_id=correlation_id,
                reply_to=self.service_id
            )
            
            # Attendi la risposta con timeout
            try:
                response = await asyncio.wait_for(response_future, timeout)
                return response
            except asyncio.TimeoutError:
                logger.warning(f"Timeout attesa risposta per {message_type} a {target}")
                return None
        finally:
            # Rimuovi l'handler temporaneo
            self.unregister_handler(temp_handler_key)
    
    def register_handler(self, message_type: str, handler: Callable):
        """Registra un handler per un tipo di messaggio."""
        self.message_handlers[message_type] = handler
        logger.debug(f"Handler registrato per {message_type}")
    
    def unregister_handler(self, message_type: str):
        """Rimuove un handler per un tipo di messaggio."""
        if message_type in self.message_handlers:
            del self.message_handlers[message_type]
            logger.debug(f"Handler rimosso per {message_type}")
    
    async def _listen_for_messages(self):
        """Task in background che ascolta i messaggi in arrivo."""
        logger.info(f"Service bus in ascolto per {self.service_id}")
        
        while self.running:
            try:
                # Ricezione non bloccante con timeout
                data = await self.subscriber.poll(timeout=100)
                if not data:
                    # Nessun messaggio disponibile
                    await asyncio.sleep(0.01)
                    continue
                
                # Leggi il messaggio completo
                [topic, message_bytes] = await self.subscriber.recv_multipart()
                topic = topic.decode()
                
                # Processa solo se è per questo servizio o broadcast
                if topic not in [self.service_id, "broadcast"]:
                    continue
                
                # Decodifica il messaggio
                message_json = message_bytes.decode()
                message_data = json.loads(message_json)
                
                # Ricostruisci l'oggetto ServiceMessage
                message = ServiceMessage(**message_data)
                
                # Ignora messaggi inviati da questo stesso servizio
                if message.sender == self.service_id:
                    continue
                
                logger.debug(f"Messaggio ricevuto: {message.type} da {message.sender}")
                
                # Verifica se c'è un handler per questo tipo di messaggio
                handler = self.message_handlers.get(message.type)
                if handler:
                    # Processa in background per non bloccare la ricezione
                    asyncio.create_task(self._process_message(handler, message))
                elif message.correlation_id and message.correlation_id in self.message_handlers:
                    # Gestisci risposte a richieste di correlazione
                    handler = self.message_handlers.get(f"_temp_{message.correlation_id}")
                    if handler:
                        asyncio.create_task(self._process_message(handler, message))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Errore nella ricezione messaggi: {e}")
                await asyncio.sleep(1)  # Evita loop di errori rapidi
    
    async def _process_message(self, handler: Callable, message: ServiceMessage):
        """Processa un messaggio invocando l'handler appropriato."""
        try:
            await handler(message)
        except Exception as e:
            logger.error(f"Errore nell'handler per {message.type}: {e}")

class ServiceManager:
    """Gestisce il ciclo di vita dei servizi."""
    
    def __init__(self, registry: ServiceRegistry, config_file: Optional[str] = None):
        self.registry = registry
        self.config_file = config_file or os.path.expanduser('~/.m4bot/services_config.yaml')
        self.active_processes: Dict[str, multiprocessing.Process] = {}
        self.service_configs: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        self._load_config()
    
    def _load_config(self):
        """Carica la configurazione dei servizi."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    self.service_configs = yaml.safe_load(f) or {}
                
                logger.info(f"Configurazione servizi caricata: {len(self.service_configs)} servizi configurati")
            except Exception as e:
                logger.error(f"Errore nel caricamento della configurazione servizi: {e}")
                self.service_configs = {}
        else:
            logger.info("File di configurazione servizi non trovato, inizializzazione predefinita")
            self.service_configs = {}
            self._save_config()
    
    def _save_config(self):
        """Salva la configurazione dei servizi."""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            with open(self.config_file, 'w') as f:
                yaml.dump(self.service_configs, f, default_flow_style=False)
            
            logger.debug("Configurazione servizi salvata con successo")
        except Exception as e:
            logger.error(f"Errore nel salvataggio della configurazione servizi: {e}")
    
    def start_service(self, service_id: str) -> bool:
        """Avvia un servizio."""
        with self.lock:
            # Verifica se il servizio è già attivo
            if service_id in self.active_processes:
                process = self.active_processes[service_id]
                if process.is_alive():
                    logger.warning(f"Servizio {service_id} già in esecuzione")
                    return True
                else:
                    # Rimuovi il processo terminato
                    del self.active_processes[service_id]
            
            # Ottieni informazioni sul servizio
            service = self.registry.get_service(service_id)
            if not service:
                logger.error(f"Servizio {service_id} non trovato nel registro")
                return False
            
            # Ottieni la configurazione del servizio
            config = self.service_configs.get(service_id, {})
            
            # Verifica che il servizio abbia un modulo di avvio
            module_path = config.get('module_path')
            if not module_path:
                logger.error(f"Percorso modulo mancante per il servizio {service_id}")
                return False
            
            # Crea il processo
            try:
                process = multiprocessing.Process(
                    target=self._service_process_main,
                    args=(service_id, module_path, config),
                    name=f"Service-{service_id}"
                )
                
                # Avvia il processo
                process.start()
                
                # Registra il processo attivo
                self.active_processes[service_id] = process
                
                # Aggiorna lo stato nel registro
                self.registry.update_service_status(
                    service_id=service_id,
                    status=ServiceStatus.STARTING,
                    metadata={"pid": process.pid, "started_at": datetime.now().isoformat()}
                )
                
                logger.info(f"Servizio {service_id} avviato con PID {process.pid}")
                return True
            except Exception as e:
                logger.error(f"Errore nell'avvio del servizio {service_id}: {e}")
                self.registry.update_service_status(
                    service_id=service_id,
                    status=ServiceStatus.ERROR,
                    metadata={"error": str(e)}
                )
                return False
    
    def stop_service(self, service_id: str, force: bool = False) -> bool:
        """Ferma un servizio."""
        with self.lock:
            if service_id not in self.active_processes:
                logger.warning(f"Servizio {service_id} non in esecuzione")
                return False
            
            process = self.active_processes[service_id]
            
            # Aggiorna lo stato
            self.registry.update_service_status(
                service_id=service_id,
                status=ServiceStatus.STOPPING
            )
            
            try:
                # Invia segnale di terminazione
                if force:
                    process.terminate()
                else:
                    # Invia segnale SIGTERM (più gentile)
                    os.kill(process.pid, signal.SIGTERM)
                
                # Attendi la terminazione
                process.join(timeout=10)
                
                # Se ancora in esecuzione e force=True, termina forzatamente
                if process.is_alive() and force:
                    process.kill()
                    process.join(timeout=5)
                
                # Verifica se il processo è terminato
                if not process.is_alive():
                    # Rimuovi il processo dalla lista
                    del self.active_processes[service_id]
                    
                    # Aggiorna lo stato
                    self.registry.update_service_status(
                        service_id=service_id,
                        status=ServiceStatus.STOPPED
                    )
                    
                    logger.info(f"Servizio {service_id} fermato correttamente")
                    return True
                else:
                    logger.warning(f"Impossibile terminare il servizio {service_id}")
                    return False
            except Exception as e:
                logger.error(f"Errore nell'arresto del servizio {service_id}: {e}")
                return False
    
    def restart_service(self, service_id: str) -> bool:
        """Riavvia un servizio."""
        with self.lock:
            # Ferma il servizio se in esecuzione
            if service_id in self.active_processes:
                self.stop_service(service_id)
            
            # Aggiorna lo stato
            service = self.registry.get_service(service_id)
            if service:
                service.restart_count += 1
                self.registry.update_service_status(
                    service_id=service_id,
                    status=ServiceStatus.RESTARTING,
                    metadata={"restart_count": service.restart_count}
                )
            
            # Avvia il servizio
            return self.start_service(service_id)
    
    def get_service_status(self, service_id: str) -> Tuple[Optional[ServiceStatus], Dict[str, Any]]:
        """Ottiene lo stato corrente di un servizio."""
        with self.lock:
            service = self.registry.get_service(service_id)
            if not service:
                return None, {"error": "Servizio non trovato"}
            
            # Verifica se il processo è in esecuzione
            process_running = False
            pid = None
            
            if service_id in self.active_processes:
                process = self.active_processes[service_id]
                process_running = process.is_alive()
                pid = process.pid
            
            # Raccogli informazioni aggiuntive
            info = {
                "id": service.id,
                "name": service.name,
                "type": service.type.value,
                "status": service.status.value,
                "pid": pid,
                "process_running": process_running,
                "started_at": service.started_at,
                "last_heartbeat": service.last_heartbeat,
                "restart_count": service.restart_count
            }
            
            # Se il processo non è in esecuzione ma lo stato è RUNNING, aggiorna lo stato
            if not process_running and service.status == ServiceStatus.RUNNING:
                self.registry.update_service_status(
                    service_id=service_id,
                    status=ServiceStatus.ERROR,
                    metadata={"error": "Process terminated unexpectedly"}
                )
                info["status"] = ServiceStatus.ERROR.value
            
            return service.status, info
    
    def configure_service(self, service_id: str, config: Dict[str, Any]) -> bool:
        """Aggiorna la configurazione di un servizio."""
        with self.lock:
            self.service_configs[service_id] = config
            self._save_config()
            return True
    
    def _service_process_main(self, service_id: str, module_path: str, config: Dict[str, Any]):
        """Funzione principale eseguita dal processo del servizio."""
        try:
            # Configura il logging per questo processo
            log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            logging.basicConfig(level=logging.INFO, format=log_format)
            
            logger = logging.getLogger(f'service.{service_id}')
            logger.info(f"Processo servizio {service_id} avviato")
            
            # Imposta gestore segnali per terminazione pulita
            self._setup_signal_handlers(service_id)
            
            # Carica il modulo dinamicamente
            sys.path.append(os.path.dirname(module_path))
            module_name = os.path.basename(module_path).replace('.py', '')
            
            try:
                module = __import__(module_name)
                
                # Cerca la funzione main
                if hasattr(module, 'main'):
                    # Esegui la funzione main del modulo
                    module.main(service_id=service_id, config=config)
                else:
                    logger.error(f"Funzione main non trovata nel modulo {module_name}")
            except Exception as e:
                logger.error(f"Errore nell'esecuzione del modulo {module_name}: {e}", exc_info=True)
                sys.exit(1)
        except Exception as e:
            logger.error(f"Errore fatale nel processo del servizio {service_id}: {e}", exc_info=True)
            sys.exit(1)
    
    def _setup_signal_handlers(self, service_id: str):
        """Configura i gestori di segnali per la terminazione ordinata."""
        def signal_handler(signum, frame):
            logger = logging.getLogger(f'service.{service_id}')
            logger.info(f"Ricevuto segnale {signum}, terminazione in corso...")
            sys.exit(0)
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

class ServiceAPI:
    """API HTTP per gestire i servizi."""
    
    def __init__(self, app: Quart, registry: ServiceRegistry, manager: ServiceManager):
        self.app = app
        self.registry = registry
        self.manager = manager
        self.setup_routes()
    
    def setup_routes(self):
        """Configura le route dell'API."""
        # Elenco servizi
        @self.app.route('/api/services', methods=['GET'])
        async def list_services():
            services = []
            for service in self.registry.services.values():
                # Converte Enum in stringhe
                service_dict = asdict(service)
                if 'type' in service_dict and isinstance(service_dict['type'], ServiceType):
                    service_dict['type'] = service_dict['type'].value
                if 'status' in service_dict and isinstance(service_dict['status'], ServiceStatus):
                    service_dict['status'] = service_dict['status'].value
                
                # Aggiungi stato processo
                status, info = self.manager.get_service_status(service.id)
                service_dict.update({
                    "process_info": info
                })
                
                services.append(service_dict)
            
            return jsonify({"services": services})
        
        # Dettagli servizio
        @self.app.route('/api/services/<service_id>', methods=['GET'])
        async def get_service(service_id):
            service = self.registry.get_service(service_id)
            if not service:
                return jsonify({"error": "Servizio non trovato"}), 404
            
            # Converti Enum in stringhe
            service_dict = asdict(service)
            if 'type' in service_dict and isinstance(service_dict['type'], ServiceType):
                service_dict['type'] = service_dict['type'].value
            if 'status' in service_dict and isinstance(service_dict['status'], ServiceStatus):
                service_dict['status'] = service_dict['status'].value
            
            # Aggiungi stato processo
            status, info = self.manager.get_service_status(service.id)
            service_dict.update({
                "process_info": info
            })
            
            return jsonify(service_dict)
        
        # Avvia servizio
        @self.app.route('/api/services/<service_id>/start', methods=['POST'])
        async def start_service(service_id):
            if not self.registry.get_service(service_id):
                return jsonify({"error": "Servizio non trovato"}), 404
            
            success = self.manager.start_service(service_id)
            if success:
                return jsonify({"status": "ok", "message": f"Servizio {service_id} avviato"})
            else:
                return jsonify({"error": f"Impossibile avviare il servizio {service_id}"}), 500
        
        # Ferma servizio
        @self.app.route('/api/services/<service_id>/stop', methods=['POST'])
        async def stop_service(service_id):
            if not self.registry.get_service(service_id):
                return jsonify({"error": "Servizio non trovato"}), 404
            
            data = await request.get_json(silent=True) or {}
            force = data.get('force', False)
            
            success = self.manager.stop_service(service_id, force=force)
            if success:
                return jsonify({"status": "ok", "message": f"Servizio {service_id} fermato"})
            else:
                return jsonify({"error": f"Impossibile fermare il servizio {service_id}"}), 500
        
        # Riavvia servizio
        @self.app.route('/api/services/<service_id>/restart', methods=['POST'])
        async def restart_service(service_id):
            if not self.registry.get_service(service_id):
                return jsonify({"error": "Servizio non trovato"}), 404
            
            success = self.manager.restart_service(service_id)
            if success:
                return jsonify({"status": "ok", "message": f"Servizio {service_id} riavviato"})
            else:
                return jsonify({"error": f"Impossibile riavviare il servizio {service_id}"}), 500
        
        # Registra servizio
        @self.app.route('/api/services', methods=['POST'])
        async def register_service():
            data = await request.get_json()
            
            try:
                # Converti stringhe in Enum
                if 'type' in data:
                    data['type'] = ServiceType(data['type'])
                if 'status' in data:
                    data['status'] = ServiceStatus(data['status'])
                
                service = ServiceInfo(**data)
                
                success = self.registry.register_service(service)
                if success:
                    return jsonify({"status": "ok", "message": f"Servizio {service.id} registrato"})
                else:
                    return jsonify({"error": "Errore nella registrazione del servizio"}), 500
            except Exception as e:
                return jsonify({"error": str(e)}), 400
        
        # Configura servizio
        @self.app.route('/api/services/<service_id>/config', methods=['PUT'])
        async def configure_service(service_id):
            if not self.registry.get_service(service_id):
                return jsonify({"error": "Servizio non trovato"}), 404
            
            config = await request.get_json()
            
            success = self.manager.configure_service(service_id, config)
            if success:
                return jsonify({"status": "ok", "message": f"Configurazione servizio {service_id} aggiornata"})
            else:
                return jsonify({"error": f"Impossibile configurare il servizio {service_id}"}), 500
        
        # Rimuovi servizio
        @self.app.route('/api/services/<service_id>', methods=['DELETE'])
        async def unregister_service(service_id):
            if not self.registry.get_service(service_id):
                return jsonify({"error": "Servizio non trovato"}), 404
            
            # Ferma il servizio se in esecuzione
            status, _ = self.manager.get_service_status(service_id)
            if status in [ServiceStatus.RUNNING, ServiceStatus.STARTING]:
                self.manager.stop_service(service_id, force=True)
            
            # Rimuovi dal registro
            success = self.registry.unregister_service(service_id)
            if success:
                return jsonify({"status": "ok", "message": f"Servizio {service_id} rimosso"})
            else:
                return jsonify({"error": f"Impossibile rimuovere il servizio {service_id}"}), 500
        
        # Health check servizio
        @self.app.route('/api/services/<service_id>/health', methods=['GET'])
        async def check_service_health(service_id):
            if not self.registry.get_service(service_id):
                return jsonify({"error": "Servizio non trovato"}), 404
            
            healthy, info = self.registry.check_service_health(service_id)
            
            if healthy:
                return jsonify({"status": "healthy", "details": info})
            else:
                return jsonify({"status": "unhealthy", "details": info}), 503
        
        # Ottieni grafo dipendenze
        @self.app.route('/api/services/dependencies', methods=['GET'])
        async def get_dependency_graph():
            graph = self.registry.get_dependency_graph()
            return jsonify({"dependencies": graph})

def create_service(service_type: ServiceType, name: str, 
                  config: Dict[str, Any] = None) -> ServiceInfo:
    """
    Factory per creare un nuovo servizio con ID generato automaticamente.
    
    Args:
        service_type: Tipo di servizio
        name: Nome del servizio
        config: Configurazione opzionale
        
    Returns:
        ServiceInfo: Informazioni sul servizio creato
    """
    service_id = f"{service_type.value}_{int(time.time())}_{str(uuid.uuid4())[:8]}"
    
    service = ServiceInfo(
        id=service_id,
        type=service_type,
        name=name,
        status=ServiceStatus.STOPPED,
        metadata=config or {}
    )
    
    return service

def get_available_port(start_port: int = 8000, max_attempts: int = 100) -> int:
    """
    Trova una porta disponibile a partire da start_port.
    
    Args:
        start_port: Porta iniziale da controllare
        max_attempts: Numero massimo di tentativi
        
    Returns:
        int: Porta disponibile
    """
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('localhost', port)) != 0:
                return port
    
    raise RuntimeError(f"Nessuna porta disponibile trovata tra {start_port} e {start_port + max_attempts - 1}")

def setup_microservices_app(quart_app: Quart) -> Tuple[ServiceRegistry, ServiceManager]:
    """
    Configura l'applicazione per supportare i microservizi.
    
    Args:
        quart_app: Applicazione Quart
        
    Returns:
        Tuple: (ServiceRegistry, ServiceManager)
    """
    # Crea registro e manager
    registry = ServiceRegistry()
    manager = ServiceManager(registry)
    
    # Configura API
    api = ServiceAPI(quart_app, registry, manager)
    
    # Aggiungi endpoint principale per health check
    @quart_app.route('/health')
    async def health_check():
        return jsonify({"status": "healthy"})
    
    # Configura WebSocket per monitoring in tempo reale
    @quart_app.websocket('/ws/services')
    async def services_ws():
        # Autenticazione?
        
        while True:
            try:
                # Invia aggiornamenti periodici
                services = []
                for service in registry.services.values():
                    # Converti Enum in stringhe
                    service_dict = asdict(service)
                    if 'type' in service_dict and isinstance(service_dict['type'], ServiceType):
                        service_dict['type'] = service_dict['type'].value
                    if 'status' in service_dict and isinstance(service_dict['status'], ServiceStatus):
                        service_dict['status'] = service_dict['status'].value
                    
                    # Aggiungi stato processo
                    status, info = manager.get_service_status(service.id)
                    service_dict.update({
                        "process_info": info
                    })
                    
                    services.append(service_dict)
                
                await websocket.send(json.dumps({
                    "type": "services_update",
                    "data": {"services": services}
                }))
                
                # Attendi prima del prossimo aggiornamento
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Errore nel WebSocket services: {e}")
                break
    
    return registry, manager 