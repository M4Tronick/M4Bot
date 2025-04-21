#!/usr/bin/env python3
"""
M4Bot - Sistema di Monitoraggio Integrato

Questo modulo implementa un sistema avanzato di monitoraggio e validazione
configurazioni per tutte le componenti di M4Bot.

Funzionalità:
- Monitoraggio risorse sistema (CPU, memoria, disco, rete)
- Tracciamento performance applicazione
- Monitoraggio servizi e dipendenze
- Validazione configurazioni
- Esportazione metriche in vari formati
- Generazione avvisi su soglie configurabili
"""

import os
import sys
import json
import time
import logging
import asyncio
import platform
import psutil
import smtplib
from email.message import EmailMessage
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set, Union

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/integrated_monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('m4bot.stability.monitor')

class MetricType(Enum):
    """Tipi di metriche supportate."""
    GAUGE = "gauge"       # Valore che può salire e scendere
    COUNTER = "counter"   # Valore che può solo incrementare
    HISTOGRAM = "histogram"  # Distribuzione di valori
    SUMMARY = "summary"   # Simile a histogram ma con percentili pre-calcolati

@dataclass
class Metric:
    """Rappresenta una singola metrica."""
    name: str
    type: MetricType
    description: str
    value: Union[float, Dict[str, float]] = 0.0
    labels: Dict[str, str] = field(default_factory=dict)
    last_update: float = field(default_factory=time.time)
    
    def update(self, value: Union[float, Dict[str, float]]):
        """Aggiorna il valore della metrica."""
        if self.type == MetricType.COUNTER and isinstance(value, (int, float)):
            # I contatori possono solo incrementare
            if isinstance(self.value, (int, float)):
                self.value = max(self.value, value)
            else:
                self.value = value
        else:
            self.value = value
        
        self.last_update = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte la metrica in un dizionario."""
        return {
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "value": self.value,
            "labels": self.labels,
            "last_update": self.last_update
        }

class ConfigValidator:
    """Validatore di configurazioni per M4Bot."""
    
    def __init__(self, schema_directory: Optional[str] = None):
        """
        Inizializza il validatore di configurazioni.
        
        Args:
            schema_directory: Percorso della directory contenente gli schemi (opzionale)
        """
        self.schema_directory = schema_directory or "config/schemas"
        self.schemas = {}
        self._load_schemas()
        
    def _load_schemas(self):
        """Carica gli schemi di validazione dalla directory specificata."""
        if not os.path.exists(self.schema_directory):
            logger.warning(f"Directory schemi non trovata: {self.schema_directory}")
            return
            
        try:
            schema_files = os.listdir(self.schema_directory)
            for file in schema_files:
                if file.endswith(".json") and file != "schema.json":
                    # Estrai il nome del componente dal nome del file
                    component = file.replace(".json", "")
                    schema_path = os.path.join(self.schema_directory, file)
                    
                    with open(schema_path, 'r') as f:
                        self.schemas[component] = json.load(f)
                    
                    logger.debug(f"Schema caricato: {component}")
            
            logger.info(f"Caricati {len(self.schemas)} schemi di configurazione")
        except Exception as e:
            logger.error(f"Errore nel caricamento degli schemi: {e}")
            
    def validate_config(self, component: str, config: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Valida una configurazione utilizzando lo schema appropriato.
        
        Args:
            component: Nome del componente della configurazione
            config: Configurazione da validare
            
        Returns:
            Tuple con stato di validazione (bool) e lista di errori
        """
        # Verifica se esiste uno schema per questo componente
        if component not in self.schemas:
            logger.warning(f"Nessuno schema trovato per il componente: {component}")
            return True, []
            
        schema = self.schemas[component]
        errors = []
        
        # Verifica campi obbligatori
        required_fields = schema.get("required", [])
        for field in required_fields:
            if field not in config:
                errors.append(f"Campo obbligatorio mancante: {field}")
        
        # Verifica proprietà
        properties = schema.get("properties", {})
        for field, field_schema in properties.items():
            if field in config:
                # Verifica tipo
                field_type = field_schema.get("type")
                if field_type:
                    value = config[field]
                    type_valid = self._validate_type(value, field_type)
                    if not type_valid:
                        errors.append(f"Tipo non valido per {field}: atteso {field_type}")
                
                # Verifica enum
                enum_values = field_schema.get("enum")
                if enum_values and config[field] not in enum_values:
                    errors.append(f"Valore non valido per {field}: deve essere uno di {enum_values}")
                
                # Verifica range
                if field_type in ["number", "integer"]:
                    if "minimum" in field_schema and config[field] < field_schema["minimum"]:
                        errors.append(f"Valore troppo basso per {field}: minimo {field_schema['minimum']}")
                    if "maximum" in field_schema and config[field] > field_schema["maximum"]:
                        errors.append(f"Valore troppo alto per {field}: massimo {field_schema['maximum']}")
        
        valid = len(errors) == 0
        return valid, errors
    
    def _validate_type(self, value: Any, expected_type: str) -> bool:
        """Verifica se un valore è del tipo atteso."""
        if expected_type == "string":
            return isinstance(value, str)
        elif expected_type == "number":
            return isinstance(value, (int, float))
        elif expected_type == "integer":
            return isinstance(value, int)
        elif expected_type == "boolean":
            return isinstance(value, bool)
        elif expected_type == "array":
            return isinstance(value, list)
        elif expected_type == "object":
            return isinstance(value, dict)
        elif expected_type == "null":
            return value is None
        elif expected_type == "any":
            return True
        else:
            return False

class IntegratedMonitor:
    """Sistema integrato di monitoraggio e validazione per M4Bot."""
    
    def __init__(self, config_path: Optional[str] = None, schema_dir: Optional[str] = None):
        """
        Inizializza il sistema integrato.
        
        Args:
            config_path: Percorso del file di configurazione (opzionale)
            schema_dir: Percorso della directory contenente gli schemi (opzionale)
        """
        self.config_path = config_path
        self.config = self._load_config()
        
        # Inizializza il validatore di configurazioni
        self.config_validator = ConfigValidator(schema_dir)
        
        # Collezione di metriche
        self.metrics: Dict[str, Metric] = {}
        
        # Stato del sistema
        self.running = False
        self.collection_task = None
        self.validation_task = None
        
        # Informazioni sul sistema
        self.system_info = self._get_system_info()
        
        # Directory per i dati
        self.data_dir = Path(self.config.get('data_dir', './monitoring_data'))
        self.data_dir.mkdir(exist_ok=True, parents=True)
        
        # Stato dei servizi
        self.services_status = {}
        
        # Stato della configurazione
        self.config_status = {}
        
        # Directory dei log
        os.makedirs("logs", exist_ok=True)
        
        logger.info(f"Sistema di monitoraggio integrato inizializzato")
    
    def _load_config(self) -> Dict[str, Any]:
        """Carica la configurazione dal file."""
        default_config = {
            'system_metrics_interval': 60,
            'app_metrics_interval': 30,
            'service_check_interval': 60,
            'config_check_interval': 300,
            'data_dir': './monitoring_data',
            'log_level': 'INFO',
            'enable_prometheus': False,
            'prometheus_port': 9090,
            'enable_export': True,
            'export_interval': 300,
            'history_days': 7,
            'thresholds': {
                'cpu_warning': 75,
                'cpu_critical': 90,
                'memory_warning': 80,
                'memory_critical': 95,
                'disk_warning': 85,
                'disk_critical': 95
            },
            'alerts': {
                'email': {
                    'enabled': False,
                    'smtp_server': '',
                    'smtp_port': 587,
                    'username': '',
                    'password': '',
                    'sender': '',
                    'recipients': []
                },
                'telegram': {
                    'enabled': False,
                    'bot_token': '',
                    'chat_id': ''
                },
                'discord': {
                    'enabled': False,
                    'webhook_url': ''
                }
            }
        }
        
        if not self.config_path or not os.path.exists(self.config_path):
            logger.warning("File di configurazione non trovato, uso configurazione predefinita")
            return default_config
        
        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Configurazione caricata da {self.config_path}")
            return {**default_config, **config}  # Unisce le configurazioni
        except Exception as e:
            logger.error(f"Errore nel caricamento della configurazione: {e}")
            return default_config
    
    def _get_system_info(self) -> Dict[str, str]:
        """Raccoglie informazioni sul sistema"""
        return {
            "os": platform.system(),
            "os_version": platform.version(),
            "python_version": platform.python_version(),
            "processor": platform.processor(),
            "hostname": platform.node()
        }
    
    def register_metric(self, name: str, metric_type: MetricType, 
                       description: str, initial_value: Union[float, Dict[str, float]] = 0.0,
                       labels: Dict[str, str] = None) -> Metric:
        """
        Registra una nuova metrica.
        
        Args:
            name: Nome univoco della metrica
            metric_type: Tipo di metrica
            description: Descrizione della metrica
            initial_value: Valore iniziale
            labels: Etichette opzionali
            
        Returns:
            Istanza della metrica creata
        """
        if name in self.metrics:
            logger.warning(f"Metrica {name} già esistente, aggiornamento descrizione e labels")
            self.metrics[name].description = description
            if labels:
                self.metrics[name].labels.update(labels or {})
            return self.metrics[name]
        
        metric = Metric(
            name=name,
            type=metric_type,
            description=description,
            value=initial_value,
            labels=labels or {}
        )
        
        self.metrics[name] = metric
        logger.debug(f"Metrica registrata: {name}")
        return metric
    
    def update_metric(self, name: str, value: Union[float, Dict[str, float]]):
        """
        Aggiorna il valore di una metrica.
        
        Args:
            name: Nome della metrica
            value: Nuovo valore
        """
        if name not in self.metrics:
            logger.warning(f"Tentativo di aggiornare metrica non registrata: {name}")
            return
        
        self.metrics[name].update(value)
    
    async def start(self):
        """Avvia il sistema integrato."""
        if self.running:
            logger.warning("Il sistema è già in esecuzione")
            return
        
        self.running = True
        logger.info("Avvio sistema integrato")
        
        # Inizializzazione delle metriche di sistema
        self._init_system_metrics()
        
        # Avvia i task
        self.collection_task = asyncio.create_task(self._collection_loop())
        self.validation_task = asyncio.create_task(self._validation_loop())
    
    async def stop(self):
        """Ferma il sistema integrato."""
        if not self.running:
            return
            
        self.running = False
        logger.info("Arresto sistema integrato")
        
        tasks = []
        if self.collection_task:
            self.collection_task.cancel()
            tasks.append(self.collection_task)
        
        if self.validation_task:
            self.validation_task.cancel()
            tasks.append(self.validation_task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            
        self.collection_task = None
        self.validation_task = None
    
    def _init_system_metrics(self):
        """Inizializza le metriche di sistema predefinite."""
        # CPU
        self.register_metric(
            name="system.cpu.usage_percent", 
            metric_type=MetricType.GAUGE,
            description="Percentuale di utilizzo CPU"
        )
        
        # Memoria
        self.register_metric(
            name="system.memory.usage_percent", 
            metric_type=MetricType.GAUGE,
            description="Percentuale di utilizzo memoria"
        )
        self.register_metric(
            name="system.memory.available_mb", 
            metric_type=MetricType.GAUGE,
            description="Memoria disponibile in MB"
        )
        
        # Disco
        self.register_metric(
            name="system.disk.usage_percent", 
            metric_type=MetricType.GAUGE,
            description="Percentuale di utilizzo disco"
        )
        self.register_metric(
            name="system.disk.free_gb", 
            metric_type=MetricType.GAUGE,
            description="Spazio libero su disco in GB"
        )
        
        # Rete
        self.register_metric(
            name="system.network.bytes_sent", 
            metric_type=MetricType.COUNTER,
            description="Totale byte inviati"
        )
        self.register_metric(
            name="system.network.bytes_recv", 
            metric_type=MetricType.COUNTER,
            description="Totale byte ricevuti"
        )
        
        # Load average
        self.register_metric(
            name="system.load.1min", 
            metric_type=MetricType.GAUGE,
            description="Load average 1 minuto"
        )
        
        # Metriche configurazione
        self.register_metric(
            name="config.valid_components", 
            metric_type=MetricType.GAUGE,
            description="Numero di componenti con configurazione valida"
        )
        self.register_metric(
            name="config.invalid_components", 
            metric_type=MetricType.GAUGE,
            description="Numero di componenti con configurazione non valida"
        )
        
        # Metriche servizi
        self.register_metric(
            name="services.available", 
            metric_type=MetricType.GAUGE,
            description="Numero di servizi disponibili"
        )
        self.register_metric(
            name="services.unavailable", 
            metric_type=MetricType.GAUGE,
            description="Numero di servizi non disponibili"
        )
    
    async def _collection_loop(self):
        """Loop principale di raccolta delle metriche."""
        logger.info("Avvio loop di raccolta metriche")
        
        try:
            import psutil
        except ImportError:
            logger.error("psutil non disponibile, installalo con 'pip install psutil'")
            self.running = False
            return
        
        last_system_collection = 0
        last_app_collection = 0
        last_service_check = 0
        last_export = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                # Raccolta metriche di sistema
                if current_time - last_system_collection >= self.config.get('system_metrics_interval', 60):
                    await self._collect_system_metrics()
                    last_system_collection = current_time
                
                # Raccolta metriche applicazione
                if current_time - last_app_collection >= self.config.get('app_metrics_interval', 30):
                    await self._collect_app_metrics()
                    last_app_collection = current_time
                
                # Controllo servizi
                if current_time - last_service_check >= self.config.get('service_check_interval', 60):
                    await self._check_services()
                    last_service_check = current_time
                
                # Esportazione dati
                if (self.config.get('enable_export', True) and 
                    current_time - last_export >= self.config.get('export_interval', 300)):
                    self._export_metrics()
                    last_export = current_time
                
                # Breve pausa
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                logger.info("Loop di raccolta cancellato")
                break
            except Exception as e:
                logger.error(f"Errore nel loop di raccolta: {e}")
                await asyncio.sleep(5)
    
    async def _validation_loop(self):
        """Loop di validazione delle configurazioni."""
        logger.info("Avvio loop di validazione configurazioni")
        
        last_validation = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                # Validazione configurazioni
                if current_time - last_validation >= self.config.get('config_check_interval', 300):
                    await self._validate_configurations()
                    last_validation = current_time
                
                # Breve pausa
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                logger.info("Loop di validazione cancellato")
                break
            except Exception as e:
                logger.error(f"Errore nel loop di validazione: {e}")
                await asyncio.sleep(5)
    
    async def _collect_system_metrics(self):
        """Raccoglie le metriche di sistema."""
        try:
            import psutil
            
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            self.update_metric("system.cpu.usage_percent", cpu_percent)
            
            # Memoria
            memory = psutil.virtual_memory()
            self.update_metric("system.memory.usage_percent", memory.percent)
            self.update_metric("system.memory.available_mb", memory.available / (1024 * 1024))
            
            # Disco
            disk = psutil.disk_usage('/')
            self.update_metric("system.disk.usage_percent", disk.percent)
            self.update_metric("system.disk.free_gb", disk.free / (1024 * 1024 * 1024))
            
            # Rete
            net_io = psutil.net_io_counters()
            self.update_metric("system.network.bytes_sent", net_io.bytes_sent)
            self.update_metric("system.network.bytes_recv", net_io.bytes_recv)
            
            # Load average
            load = psutil.getloadavg()
            self.update_metric("system.load.1min", load[0])
            
            # Controlla soglie e genera avvisi
            await self._check_thresholds()
            
            logger.debug("Metriche di sistema raccolte")
            
        except Exception as e:
            logger.error(f"Errore nella raccolta metriche di sistema: {e}")
    
    async def _collect_app_metrics(self):
        """Raccoglie le metriche dell'applicazione."""
        # In un'implementazione reale, qui si raccoglierebbero dati da log o API
        # Per ora, simula il caricamento da un file json
        metrics_file = self.data_dir / "app_metrics.json"
        
        if metrics_file.exists():
            try:
                with open(metrics_file, 'r') as f:
                    data = json.load(f)
                
                # Aggiorna le metriche dai dati caricati
                for name, value in data.items():
                    if name in self.metrics:
                        self.update_metric(name, value)
                
                logger.debug("Metriche dell'applicazione raccolte")
                        
            except Exception as e:
                logger.error(f"Errore nel caricamento delle metriche dell'app: {e}")
    
    async def _check_services(self):
        """Verifica lo stato dei servizi."""
        services = self.config.get('services', {})
        if not services:
            return
            
        available = 0
        unavailable = 0
        
        for service_name, service_config in services.items():
            try:
                service_type = service_config.get('type', 'systemd')
                
                if service_type == 'systemd':
                    # Verifica servizio systemd
                    result = await self._check_systemd_service(service_config.get('unit', service_name))
                elif service_type == 'http':
                    # Verifica endpoint HTTP
                    result = await self._check_http_service(service_config.get('url'), 
                                                          service_config.get('expected_status', 200))
                elif service_type == 'process':
                    # Verifica processo
                    result = self._check_process(service_config.get('process_name'))
                else:
                    logger.warning(f"Tipo di servizio sconosciuto: {service_type}")
                    result = False
                
                # Aggiorna lo stato del servizio
                self.services_status[service_name] = {
                    'available': result,
                    'last_check': datetime.now().isoformat()
                }
                
                if result:
                    available += 1
                else:
                    unavailable += 1
                    # Genera un avviso per il servizio non disponibile
                    logger.warning(f"Servizio non disponibile: {service_name}")
                    await self._send_alert(f"Servizio {service_name} non disponibile", "warning")
                
            except Exception as e:
                logger.error(f"Errore nella verifica del servizio {service_name}: {e}")
                self.services_status[service_name] = {
                    'available': False,
                    'last_check': datetime.now().isoformat(),
                    'error': str(e)
                }
                unavailable += 1
        
        # Aggiorna le metriche dei servizi
        self.update_metric("services.available", available)
        self.update_metric("services.unavailable", unavailable)
        
        logger.debug(f"Controllo servizi completato: {available} disponibili, {unavailable} non disponibili")
    
    async def _check_systemd_service(self, service_name: str) -> bool:
        """Verifica lo stato di un servizio systemd."""
        try:
            process = await asyncio.create_subprocess_shell(
                f"systemctl is-active {service_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            # Se il processo è terminato con successo e l'output è "active"
            return process.returncode == 0 and stdout.decode().strip() == "active"
            
        except Exception as e:
            logger.error(f"Errore nella verifica del servizio systemd {service_name}: {e}")
            return False
    
    async def _check_http_service(self, url: str, expected_status: int = 200) -> bool:
        """Verifica lo stato di un servizio HTTP."""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    return response.status == expected_status
                    
        except Exception as e:
            logger.error(f"Errore nella verifica del servizio HTTP {url}: {e}")
            return False
    
    def _check_process(self, process_name: str) -> bool:
        """Verifica se un processo è in esecuzione."""
        try:
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] == process_name:
                    return True
            return False
        except Exception as e:
            logger.error(f"Errore nella verifica del processo {process_name}: {e}")
            return False
    
    async def _validate_configurations(self):
        """Valida tutte le configurazioni nelle directory configurate."""
        config_dirs = self.config.get('config_directories', ["config"])
        
        valid_count = 0
        invalid_count = 0
        
        for config_dir in config_dirs:
            if not os.path.exists(config_dir):
                logger.warning(f"Directory configurazioni non trovata: {config_dir}")
                continue
                
            try:
                for file in os.listdir(config_dir):
                    if file.endswith(".json") and not file.endswith("schema.json"):
                        # Estrai il nome del componente dal nome del file
                        component = file.replace(".json", "")
                        config_path = os.path.join(config_dir, file)
                        
                        with open(config_path, 'r') as f:
                            config = json.load(f)
                        
                        # Valida la configurazione
                        valid, errors = self.config_validator.validate_config(component, config)
                        
                        # Aggiorna lo stato della configurazione
                        self.config_status[component] = {
                            'valid': valid,
                            'errors': errors,
                            'last_check': datetime.now().isoformat()
                        }
                        
                        if valid:
                            valid_count += 1
                            logger.debug(f"Configurazione valida: {component}")
                        else:
                            invalid_count += 1
                            error_msg = f"Configurazione non valida per {component}: {', '.join(errors)}"
                            logger.warning(error_msg)
                            await self._send_alert(error_msg, "warning")
                
            except Exception as e:
                logger.error(f"Errore nella validazione delle configurazioni in {config_dir}: {e}")
        
        # Aggiorna le metriche delle configurazioni
        self.update_metric("config.valid_components", valid_count)
        self.update_metric("config.invalid_components", invalid_count)
        
        logger.info(f"Validazione configurazioni completata: {valid_count} valide, {invalid_count} non valide")
    
    async def _check_thresholds(self):
        """Controlla le soglie delle metriche e genera avvisi."""
        thresholds = self.config.get('thresholds', {})
        
        # CPU
        cpu_value = self.metrics["system.cpu.usage_percent"].value
        cpu_warning = thresholds.get('cpu_warning', 75)
        cpu_critical = thresholds.get('cpu_critical', 90)
        
        if cpu_value >= cpu_critical:
            await self._send_alert(f"Utilizzo CPU critico: {cpu_value:.1f}%", "critical")
        elif cpu_value >= cpu_warning:
            await self._send_alert(f"Utilizzo CPU elevato: {cpu_value:.1f}%", "warning")
        
        # Memoria
        mem_value = self.metrics["system.memory.usage_percent"].value
        mem_warning = thresholds.get('memory_warning', 80)
        mem_critical = thresholds.get('memory_critical', 95)
        
        if mem_value >= mem_critical:
            await self._send_alert(f"Utilizzo memoria critico: {mem_value:.1f}%", "critical")
        elif mem_value >= mem_warning:
            await self._send_alert(f"Utilizzo memoria elevato: {mem_value:.1f}%", "warning")
        
        # Disco
        disk_value = self.metrics["system.disk.usage_percent"].value
        disk_warning = thresholds.get('disk_warning', 85)
        disk_critical = thresholds.get('disk_critical', 95)
        
        if disk_value >= disk_critical:
            await self._send_alert(f"Utilizzo disco critico: {disk_value:.1f}%", "critical")
        elif disk_value >= disk_warning:
            await self._send_alert(f"Utilizzo disco elevato: {disk_value:.1f}%", "warning")
    
    async def _send_alert(self, message: str, level: str = "info"):
        """Invia un avviso tramite i canali configurati."""
        try:
            # Registra nel log
            if level == "critical":
                logger.critical(message)
            elif level == "warning":
                logger.warning(message)
            elif level == "error":
                logger.error(message)
            else:
                logger.info(message)
            
            # Email
            if (self.config.get('alerts', {}).get('email', {}).get('enabled', False) 
                and level in ["critical", "error"]):
                await self._send_email_alert(message, level)
            
            # Telegram
            if self.config.get('alerts', {}).get('telegram', {}).get('enabled', False):
                await self._send_telegram_alert(message, level)
            
            # Discord (webhook)
            if self.config.get('alerts', {}).get('discord', {}).get('enabled', False):
                await self._send_discord_alert(message, level)
        except Exception as e:
            logger.error(f"Errore nell'invio dell'avviso: {e}")
    
    async def _send_email_alert(self, message: str, level: str):
        """Invia un avviso via email."""
        try:
            email_config = self.config.get('alerts', {}).get('email', {})
            
            if not email_config.get('smtp_server') or not email_config.get('recipients'):
                logger.warning("Configurazione email incompleta")
                return
                
            msg = EmailMessage()
            msg.set_content(f"{message}\n\nGenerato da: {self.system_info['hostname']}")
            
            subject_prefix = "CRITICO" if level == "critical" else "AVVISO"
            msg["Subject"] = f"M4Bot {subject_prefix}: {message[:50]}..."
            msg["From"] = email_config.get('sender', "alerts@m4bot.local")
            msg["To"] = ", ".join(email_config.get('recipients', []))
            
            # Invio asincrono dell'email
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, 
                self._send_email, 
                msg, 
                email_config.get('smtp_server'), 
                email_config.get('smtp_port', 587),
                email_config.get('username'),
                email_config.get('password')
            )
            
            logger.info(f"Email di avviso inviata a {len(email_config.get('recipients', []))} destinatari")
            
        except Exception as e:
            logger.error(f"Errore nell'invio dell'email: {e}")
    
    def _send_email(self, msg, smtp_server, smtp_port, username, password):
        """Funzione sincrona per l'invio dell'email."""
        try:
            with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
                if username and password:
                    server.login(username, password)
                server.send_message(msg)
        except Exception as e:
            logger.error(f"Errore nell'invio dell'email: {e}")
    
    async def _send_telegram_alert(self, message: str, level: str):
        """Invia un avviso via Telegram."""
        try:
            import aiohttp
            
            telegram_config = self.config.get('alerts', {}).get('telegram', {})
            
            if not telegram_config.get('bot_token') or not telegram_config.get('chat_id'):
                logger.warning("Configurazione Telegram incompleta")
                return
            
            # Formatta il messaggio
            if level == "critical":
                formatted_message = f"🔴 *CRITICO*: {message}"
            elif level == "error":
                formatted_message = f"🟠 *ERRORE*: {message}"
            elif level == "warning":
                formatted_message = f"🟡 *AVVISO*: {message}"
            else:
                formatted_message = f"🟢 *INFO*: {message}"
            
            # Aggiungi info sul sistema
            formatted_message += f"\n\nHost: {self.system_info['hostname']}"
            
            # Invia il messaggio
            bot_token = telegram_config.get('bot_token')
            chat_id = telegram_config.get('chat_id')
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            
            async with aiohttp.ClientSession() as session:
                await session.post(url, data={
                    "chat_id": chat_id,
                    "text": formatted_message,
                    "parse_mode": "Markdown"
                })
                
            logger.info("Avviso Telegram inviato")
            
        except Exception as e:
            logger.error(f"Errore nell'invio dell'avviso Telegram: {e}")
    
    async def _send_discord_alert(self, message: str, level: str):
        """Invia un avviso via Discord webhook."""
        try:
            import aiohttp
            
            discord_config = self.config.get('alerts', {}).get('discord', {})
            
            if not discord_config.get('webhook_url'):
                logger.warning("Configurazione Discord incompleta")
                return
                
            # Determina il colore dell'embed in base al livello
            if level == "critical":
                color = 16711680  # Rosso
                title = "⚠️ AVVISO CRITICO"
            elif level == "error":
                color = 16744192  # Arancione
                title = "⚠️ ERRORE"
            elif level == "warning":
                color = 16776960  # Giallo
                title = "⚠️ AVVISO"
            else:
                color = 65280  # Verde
                title = "ℹ️ INFORMAZIONE"
            
            # Crea l'embed per Discord
            embed = {
                "title": title,
                "description": message,
                "color": color,
                "timestamp": datetime.now().isoformat(),
                "footer": {
                    "text": f"M4Bot - {self.system_info['hostname']}"
                }
            }
            
            # Invia il webhook
            webhook_url = discord_config.get('webhook_url')
            async with aiohttp.ClientSession() as session:
                await session.post(webhook_url, json={"embeds": [embed]})
                
            logger.info("Avviso Discord inviato")
                
        except Exception as e:
            logger.error(f"Errore nell'invio dell'avviso Discord: {e}")
    
    def _export_metrics(self):
        """Esporta le metriche su file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = self.data_dir / f"metrics_{timestamp}.json"
        
        try:
            data = {
                "timestamp": time.time(),
                "system_info": self.system_info,
                "metrics": {name: metric.to_dict() for name, metric in self.metrics.items()},
                "services_status": self.services_status,
                "config_status": self.config_status
            }
            
            with open(export_file, 'w') as f:
                json.dump(data, f, indent=2)
                
            logger.info(f"Metriche esportate in {export_file}")
            
            # Elimina file vecchi
            self._cleanup_old_exports()
            
        except Exception as e:
            logger.error(f"Errore nell'esportazione delle metriche: {e}")
    
    def _cleanup_old_exports(self):
        """Elimina i file di esportazione più vecchi del periodo configurato."""
        try:
            history_days = self.config.get('history_days', 7)
            cutoff_time = time.time() - (history_days * 86400)
            
            for file in self.data_dir.glob("metrics_*.json"):
                if file.stat().st_mtime < cutoff_time:
                    file.unlink()
                    logger.debug(f"File eliminato: {file}")
                    
        except Exception as e:
            logger.error(f"Errore nella pulizia dei file vecchi: {e}")
    
    def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Restituisce tutte le metriche come dizionario."""
        return {name: metric.to_dict() for name, metric in self.metrics.items()}
    
    def get_system_status(self) -> Dict[str, Any]:
        """Restituisce un riepilogo dello stato del sistema."""
        status = {
            "timestamp": time.time(),
            "system_info": self.system_info,
            "services": self.services_status,
            "configs": self.config_status,
            "thresholds": self.config.get('thresholds', {})
        }
        
        # Aggiungi metriche principali
        if "system.cpu.usage_percent" in self.metrics:
            status["cpu_percent"] = self.metrics["system.cpu.usage_percent"].value
        
        if "system.memory.usage_percent" in self.metrics:
            status["memory_percent"] = self.metrics["system.memory.usage_percent"].value
        
        if "system.disk.usage_percent" in self.metrics:
            status["disk_percent"] = self.metrics["system.disk.usage_percent"].value
        
        return status
    
    def format_prometheus(self) -> str:
        """Formatta le metriche in formato Prometheus."""
        output = []
        
        for name, metric in self.metrics.items():
            # Converti nome in formato Prometheus (punti in underscore)
            prom_name = name.replace('.', '_')
            
            # Aggiungi commento con descrizione
            output.append(f"# HELP {prom_name} {metric.description}")
            output.append(f"# TYPE {prom_name} {metric.type.value}")
            
            # Formatta il valore
            if isinstance(metric.value, (int, float)):
                # Formatta le labels
                labels_str = ""
                if metric.labels:
                    labels = []
                    for k, v in metric.labels.items():
                        labels.append(f'{k}="{v}"')
                    labels_str = f'{{{",".join(labels)}}}'
                
                output.append(f"{prom_name}{labels_str} {metric.value}")
            
            elif isinstance(metric.value, dict) and metric.type in (MetricType.HISTOGRAM, MetricType.SUMMARY):
                # Per istogrammi e sommari, formato speciale
                for k, v in metric.value.items():
                    output.append(f"{prom_name}_{k} {v}")
        
        return "\n".join(output)

# Funzione principale di avvio
async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="M4Bot Sistema di Monitoraggio Integrato")
    parser.add_argument("--config", type=str, help="Percorso del file di configurazione")
    parser.add_argument("--schema-dir", type=str, help="Percorso della directory schemi")
    parser.add_argument("--duration", type=int, default=0, help="Durata in secondi (0 per infinito)")
    parser.add_argument("--export", type=str, help="Esporta metriche su file")
    
    args = parser.parse_args()
    
    # Crea istanza del sistema integrato
    monitor = IntegratedMonitor(args.config, args.schema_dir)
    
    try:
        # Avvia il sistema
        await monitor.start()
        
        if args.duration > 0:
            # Esecuzione per un tempo limitato
            logger.info(f"Esecuzione per {args.duration} secondi")
            await asyncio.sleep(args.duration)
        else:
            # Esecuzione indefinita
            logger.info("Esecuzione indefinita, premi Ctrl+C per terminare")
            # Attendi indefinitamente
            while True:
                await asyncio.sleep(60)
                
    except KeyboardInterrupt:
        logger.info("Interruzione da tastiera")
    except Exception as e:
        logger.error(f"Errore durante l'esecuzione: {e}")
    finally:
        # Ferma il sistema
        await monitor.stop()
        
        # Esporta le metriche se richiesto
        if args.export:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_file = args.export.format(timestamp=timestamp)
            
            data = {
                "timestamp": time.time(),
                "system_info": monitor.system_info,
                "metrics": monitor.get_all_metrics(),
                "services_status": monitor.services_status,
                "config_status": monitor.config_status
            }
            
            with open(export_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"Metriche esportate in {export_file}")

if __name__ == "__main__":
    asyncio.run(main()) 