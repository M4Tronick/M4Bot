#!/usr/bin/env python3
"""
M4Bot - Sistema di Monitoraggio Proattivo

Questo modulo implementa un sistema di monitoraggio avanzato con:
- Metriche di performance (CPU, memoria, disco)
- Monitoraggio dei servizi (disponibilità, latenza)
- Alerting intelligente con threshold adattivi
- Dashboard di stato per tutti i servizi
- Correlazione eventi per diagnostica avanzata
"""

import os
import time
import json
import logging
import asyncio
import platform
import socket
import threading
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set, Callable
from dataclasses import dataclass, field, asdict

import psutil
import aiohttp
import numpy as np
from prometheus_client import Counter, Gauge, Histogram, start_http_server

# Configurazione logging
logger = logging.getLogger('m4bot.stability.monitoring')

# Metriche Prometheus
CPU_GAUGE = Gauge('m4bot_cpu_usage_percent', 'Percentuale di utilizzo CPU')
MEMORY_GAUGE = Gauge('m4bot_memory_usage_percent', 'Percentuale di utilizzo memoria')
DISK_GAUGE = Gauge('m4bot_disk_usage_percent', 'Percentuale di utilizzo disco')
SERVICE_UP_GAUGE = Gauge('m4bot_service_up', 'Stato servizio (1=up, 0=down)', ['service'])
REQUEST_LATENCY = Histogram('m4bot_request_latency_seconds', 'Latenza richieste HTTP', ['endpoint'])
ERROR_COUNTER = Counter('m4bot_errors_total', 'Numero totale di errori', ['service', 'severity'])
ALERT_COUNTER = Counter('m4bot_alerts_triggered', 'Numero di alert generati', ['type'])

# Configurazione predefinita
DEFAULT_CONFIG = {
    'monitoring_interval': 30,     # Intervallo di campionamento in secondi
    'enable_prometheus': True,     # Esporre metriche per Prometheus
    'prometheus_port': 9090,       # Porta per esporre metriche Prometheus
    'enable_alerting': True,       # Abilita sistema di alert
    'alert_methods': {             # Metodi di notifica alert
        'log': True,               # Log su file
        'webhook': None,           # URL webhook per notifiche
        'email': None,             # Configurazione email
        'webui': True              # Notifiche su interfaccia web
    },
    'thresholds': {                # Soglie per alert
        'cpu_high': 80,            # % CPU
        'memory_high': 85,         # % memoria
        'disk_high': 90,           # % disco
        'service_latency': 1000,   # ms massimi per risposta servizio
        'adaptive': True,          # Usa threshold adattivi basati su deviazioni standard
        'adaptive_factor': 2.5     # Numero di deviazioni standard per threshold adattivi
    },
    'services': [                  # Servizi da monitorare
        {
            'name': 'web',
            'type': 'http',
            'url': 'http://localhost:5000/health',
            'method': 'GET',
            'expected_status': 200,
            'timeout': 5
        },
        {
            'name': 'bot',
            'type': 'http', 
            'url': 'http://localhost:5001/health',
            'method': 'GET',
            'expected_status': 200,
            'timeout': 5
        },
        {
            'name': 'database',
            'type': 'postgres',
            'host': 'localhost',
            'port': 5432,
            'user': 'postgres',
            'password': '',
            'database': 'm4bot_db',
            'timeout': 5
        },
        {
            'name': 'nginx',
            'type': 'port',
            'host': 'localhost',
            'port': 80,
            'timeout': 2
        }
    ],
    'data_retention': {            # Conservazione dati storici
        'metrics': 30,             # Giorni di conservazione metriche
        'alerts': 90,              # Giorni di conservazione alert
        'detailed_metrics': 7      # Giorni di conservazione metriche dettagliate
    }
}

@dataclass
class Metric:
    """Classe di una metrica di sistema."""
    timestamp: float
    name: str
    value: float
    unit: str = ""
    labels: Dict[str, str] = field(default_factory=dict)

@dataclass
class Alert:
    """Rappresenta un alert generato dal sistema."""
    timestamp: float
    name: str
    service: str
    severity: str  # 'critical', 'warning', 'info'
    message: str
    value: float
    threshold: float
    unit: str = ""
    acknowledged: bool = False
    resolved: bool = False
    resolved_at: Optional[float] = None
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte l'alert in dizionario."""
        return asdict(self)

@dataclass
class ServiceStatus:
    """Stato di un servizio monitorato."""
    name: str
    type: str
    is_up: bool
    last_check: float
    latency: float = 0.0
    error_message: str = ""
    consecutive_failures: int = 0
    status_history: List[bool] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte lo stato in dizionario."""
        result = asdict(self)
        # Limita la history a 100 entries per evitare problemi di serializzazione
        result['status_history'] = result['status_history'][-100:] if result['status_history'] else []
        return result

class MetricCollector:
    """Raccoglie metriche di sistema e dei servizi."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.metrics_history: Dict[str, List[Metric]] = {}
        self.services_status: Dict[str, ServiceStatus] = {}
        self.alerts: List[Alert] = []
        self.recent_metrics: Dict[str, List[float]] = {}  # Per calcoli adattivi
        self.http_session: Optional[aiohttp.ClientSession] = None
        
        # Inizializza connessione database PostgreSQL se necessario
        self.db_conn = None
        
        # Inizializza stato servizi
        for service in config['services']:
            self.services_status[service['name']] = ServiceStatus(
                name=service['name'],
                type=service['type'],
                is_up=False,
                last_check=time.time()
            )
    
    async def start(self):
        """Inizializza e avvia il collector."""
        # Inizializza sessione HTTP
        self.http_session = aiohttp.ClientSession()
        
        if self.config.get('enable_prometheus', False):
            try:
                prometheus_port = self.config.get('prometheus_port', 9090)
                start_http_server(prometheus_port)
                logger.info(f"Server Prometheus avviato sulla porta {prometheus_port}")
            except Exception as e:
                logger.error(f"Impossibile avviare server Prometheus: {e}")
    
    async def stop(self):
        """Arresta il collector."""
        if self.http_session:
            await self.http_session.close()
    
    async def collect_system_metrics(self) -> Dict[str, Metric]:
        """Raccoglie metriche di sistema (CPU, memoria, disco)."""
        now = time.time()
        metrics = {}
        
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            metrics['cpu'] = Metric(
                timestamp=now,
                name='cpu_usage',
                value=cpu_percent,
                unit='percent'
            )
            CPU_GAUGE.set(cpu_percent)
            self._update_metric_history('cpu_usage', cpu_percent)
            
            # Memoria
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            metrics['memory'] = Metric(
                timestamp=now,
                name='memory_usage',
                value=memory_percent,
                unit='percent'
            )
            MEMORY_GAUGE.set(memory_percent)
            self._update_metric_history('memory_usage', memory_percent)
            
            # Disco
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            metrics['disk'] = Metric(
                timestamp=now,
                name='disk_usage',
                value=disk_percent,
                unit='percent'
            )
            DISK_GAUGE.set(disk_percent)
            self._update_metric_history('disk_usage', disk_percent)
            
            # Informazioni di sistema aggiuntive
            metrics['load'] = Metric(
                timestamp=now,
                name='system_load',
                value=os.getloadavg()[0] if hasattr(os, 'getloadavg') else 0,
                unit='load'
            )
            
            # Contatori rete
            net_io = psutil.net_io_counters()
            metrics['network_in'] = Metric(
                timestamp=now,
                name='network_in',
                value=net_io.bytes_recv,
                unit='bytes'
            )
            metrics['network_out'] = Metric(
                timestamp=now,
                name='network_out',
                value=net_io.bytes_sent,
                unit='bytes'
            )
            
            return metrics
        except Exception as e:
            logger.error(f"Errore nel raccogliere metriche di sistema: {e}")
            return {}
    
    async def check_services(self) -> Dict[str, ServiceStatus]:
        """Controlla lo stato dei servizi configurati."""
        results = {}
        for service in self.config['services']:
            service_name = service['name']
            service_type = service['type']
            status = self.services_status.get(
                service_name, 
                ServiceStatus(
                    name=service_name,
                    type=service_type,
                    is_up=False,
                    last_check=time.time()
                )
            )
            
            # Aggiorna il timestamp
            status.last_check = time.time()
            
            try:
                if service_type == 'http':
                    await self._check_http_service(service, status)
                elif service_type == 'postgres':
                    await self._check_postgres_service(service, status)
                elif service_type == 'port':
                    await self._check_port_service(service, status)
                else:
                    logger.warning(f"Tipo di servizio non supportato: {service_type}")
                    status.is_up = False
                    status.error_message = f"Tipo di servizio non supportato: {service_type}"
            except Exception as e:
                logger.error(f"Errore nel controllo del servizio {service_name}: {e}")
                status.is_up = False
                status.error_message = str(e)
                status.consecutive_failures += 1
            
            # Aggiorna history
            status.status_history.append(status.is_up)
            if len(status.status_history) > 1000:  # Limita la lunghezza
                status.status_history = status.status_history[-1000:]
            
            # Aggiorna gauge Prometheus
            SERVICE_UP_GAUGE.labels(service=service_name).set(1 if status.is_up else 0)
            
            # Memorizza risultato
            results[service_name] = status
            self.services_status[service_name] = status
        
        return results
    
    async def _check_http_service(self, service: Dict[str, Any], status: ServiceStatus):
        """Controlla un servizio HTTP."""
        if not self.http_session:
            raise RuntimeError("Sessione HTTP non inizializzata")
        
        url = service['url']
        method = service.get('method', 'GET')
        expected_status = service.get('expected_status', 200)
        timeout = service.get('timeout', 5)
        
        start_time = time.time()
        try:
            if method == 'GET':
                async with self.http_session.get(url, timeout=timeout) as response:
                    status.is_up = response.status == expected_status
                    status.latency = (time.time() - start_time) * 1000  # ms
                    
                    if not status.is_up:
                        status.error_message = f"Stato HTTP non valido: {response.status}"
                        status.consecutive_failures += 1
                    else:
                        status.error_message = ""
                        status.consecutive_failures = 0
            else:
                raise ValueError(f"Metodo HTTP non supportato: {method}")
            
            # Aggiorna istogramma latenza
            REQUEST_LATENCY.labels(endpoint=url).observe(status.latency / 1000)  # secondi
        except asyncio.TimeoutError:
            status.is_up = False
            status.error_message = f"Timeout dopo {timeout} secondi"
            status.latency = timeout * 1000
            status.consecutive_failures += 1
        except Exception as e:
            status.is_up = False
            status.error_message = str(e)
            status.latency = (time.time() - start_time) * 1000
            status.consecutive_failures += 1
    
    async def _check_postgres_service(self, service: Dict[str, Any], status: ServiceStatus):
        """Controlla un servizio PostgreSQL."""
        import asyncpg
        
        host = service.get('host', 'localhost')
        port = service.get('port', 5432)
        user = service.get('user', 'postgres')
        password = service.get('password', '')
        database = service.get('database', 'postgres')
        timeout = service.get('timeout', 5)
        
        start_time = time.time()
        conn = None
        try:
            conn = await asyncpg.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database,
                timeout=timeout
            )
            
            # Esegui una query semplice per verificare il funzionamento
            await conn.fetchval('SELECT 1')
            
            status.is_up = True
            status.latency = (time.time() - start_time) * 1000
            status.error_message = ""
            status.consecutive_failures = 0
        except Exception as e:
            status.is_up = False
            status.error_message = str(e)
            status.latency = (time.time() - start_time) * 1000
            status.consecutive_failures += 1
        finally:
            if conn:
                await conn.close()
    
    async def _check_port_service(self, service: Dict[str, Any], status: ServiceStatus):
        """Controlla se una porta TCP è aperta."""
        host = service.get('host', 'localhost')
        port = service.get('port', 80)
        timeout = service.get('timeout', 2)
        
        start_time = time.time()
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
            
            status.is_up = True
            status.latency = (time.time() - start_time) * 1000
            status.error_message = ""
            status.consecutive_failures = 0
        except (asyncio.TimeoutError, ConnectionRefusedError, socket.gaierror) as e:
            status.is_up = False
            status.error_message = str(e)
            status.latency = (time.time() - start_time) * 1000
            status.consecutive_failures += 1
    
    def _update_metric_history(self, name: str, value: float):
        """Aggiorna la storia delle metriche per calcoli adattivi."""
        if name not in self.recent_metrics:
            self.recent_metrics[name] = []
        
        self.recent_metrics[name].append(value)
        
        # Mantieni solo gli ultimi 100 valori
        if len(self.recent_metrics[name]) > 100:
            self.recent_metrics[name] = self.recent_metrics[name][-100:]
    
    def check_threshold_violations(self) -> List[Alert]:
        """Controlla violazioni di soglia e genera alert."""
        alerts = []
        now = time.time()
        thresholds = self.config['thresholds']
        
        # Controlla CPU
        cpu_value = self.recent_metrics.get('cpu_usage', [0])[-1]
        cpu_threshold = thresholds['cpu_high']
        
        # Se abilitato, calcola soglia adattiva
        if thresholds.get('adaptive', True) and len(self.recent_metrics.get('cpu_usage', [])) > 10:
            # Calcola media e deviazione standard
            cpu_values = np.array(self.recent_metrics['cpu_usage'])
            cpu_mean = np.mean(cpu_values)
            cpu_std = np.std(cpu_values)
            adaptive_factor = thresholds.get('adaptive_factor', 2.5)
            
            # La soglia è la media + X deviazioni standard, ma non superiore alla soglia fissa
            adaptive_threshold = min(
                cpu_mean + (cpu_std * adaptive_factor),
                thresholds['cpu_high']
            )
            
            # Non scendere sotto una soglia ragionevole
            adaptive_threshold = max(adaptive_threshold, 70)
            
            # Usa la soglia adattiva
            cpu_threshold = adaptive_threshold
        
        if cpu_value > cpu_threshold:
            alerts.append(Alert(
                timestamp=now,
                name='high_cpu_usage',
                service='system',
                severity='critical' if cpu_value > cpu_threshold + 10 else 'warning',
                message=f"Utilizzo CPU elevato: {cpu_value:.1f}%",
                value=cpu_value,
                threshold=cpu_threshold,
                unit='percent'
            ))
            ALERT_COUNTER.labels(type='high_cpu').inc()
        
        # Controlla memoria
        memory_value = self.recent_metrics.get('memory_usage', [0])[-1]
        memory_threshold = thresholds['memory_high']
        
        if thresholds.get('adaptive', True) and len(self.recent_metrics.get('memory_usage', [])) > 10:
            memory_values = np.array(self.recent_metrics['memory_usage'])
            memory_mean = np.mean(memory_values)
            memory_std = np.std(memory_values)
            
            adaptive_threshold = min(
                memory_mean + (memory_std * thresholds.get('adaptive_factor', 2.5)),
                thresholds['memory_high']
            )
            adaptive_threshold = max(adaptive_threshold, 75)
            
            memory_threshold = adaptive_threshold
        
        if memory_value > memory_threshold:
            alerts.append(Alert(
                timestamp=now,
                name='high_memory_usage',
                service='system',
                severity='critical' if memory_value > memory_threshold + 10 else 'warning',
                message=f"Utilizzo memoria elevato: {memory_value:.1f}%",
                value=memory_value,
                threshold=memory_threshold,
                unit='percent'
            ))
            ALERT_COUNTER.labels(type='high_memory').inc()
        
        # Controlla disco
        disk_value = self.recent_metrics.get('disk_usage', [0])[-1]
        if disk_value > thresholds['disk_high']:
            alerts.append(Alert(
                timestamp=now,
                name='high_disk_usage',
                service='system',
                severity='critical' if disk_value > thresholds['disk_high'] + 5 else 'warning',
                message=f"Spazio su disco in esaurimento: {disk_value:.1f}%",
                value=disk_value,
                threshold=thresholds['disk_high'],
                unit='percent'
            ))
            ALERT_COUNTER.labels(type='high_disk').inc()
        
        # Controlla latenza servizi
        for service_name, status in self.services_status.items():
            # Servizio offline
            if not status.is_up:
                severity = 'critical' if status.consecutive_failures >= 3 else 'warning'
                alerts.append(Alert(
                    timestamp=now,
                    name='service_down',
                    service=service_name,
                    severity=severity,
                    message=f"Servizio {service_name} non disponibile: {status.error_message}",
                    value=status.consecutive_failures,
                    threshold=1,
                    unit='failures'
                ))
                ALERT_COUNTER.labels(type='service_down').inc()
            
            # Latenza elevata
            elif status.latency > thresholds['service_latency']:
                alerts.append(Alert(
                    timestamp=now,
                    name='high_latency',
                    service=service_name,
                    severity='warning',
                    message=f"Elevata latenza per {service_name}: {status.latency:.1f} ms",
                    value=status.latency,
                    threshold=thresholds['service_latency'],
                    unit='ms'
                ))
                ALERT_COUNTER.labels(type='high_latency').inc()
        
        # Aggiorna la lista di alert
        self.alerts.extend(alerts)
        
        # Raggruppa alert simili
        grouped_alerts = self._group_similar_alerts(alerts)
        
        return grouped_alerts
    
    def _group_similar_alerts(self, alerts: List[Alert]) -> List[Alert]:
        """Raggruppa alert simili per evitare spam."""
        result = []
        grouped = {}
        
        for alert in alerts:
            key = f"{alert.name}:{alert.service}"
            
            if key in grouped:
                # Aggiorna l'alert esistente
                grouped[key].value = max(grouped[key].value, alert.value)
                if alert.severity == 'critical' and grouped[key].severity != 'critical':
                    grouped[key].severity = 'critical'
                    grouped[key].message = alert.message
            else:
                grouped[key] = alert
        
        return list(grouped.values())
    
    async def send_alerts(self, alerts: List[Alert]):
        """Invia gli alert generati attraverso i canali configurati."""
        if not alerts:
            return
        
        if not self.config.get('enable_alerting', True):
            logger.debug(f"Alerting disabilitato, {len(alerts)} alert ignorati.")
            return
        
        alert_methods = self.config.get('alert_methods', {})
        
        # Log su file
        if alert_methods.get('log', True):
            for alert in alerts:
                log_level = {
                    'critical': logger.critical,
                    'warning': logger.warning,
                    'info': logger.info
                }.get(alert.severity, logger.info)
                
                log_level(f"ALERT - {alert.name} - {alert.message} ({alert.service})")
        
        # Webhook
        webhook_url = alert_methods.get('webhook')
        if webhook_url and self.http_session:
            try:
                payload = {
                    'alerts': [alert.to_dict() for alert in alerts],
                    'timestamp': time.time(),
                    'source': socket.gethostname()
                }
                
                async with self.http_session.post(
                    webhook_url,
                    json=payload,
                    timeout=5
                ) as response:
                    if response.status != 200:
                        logger.error(f"Errore nell'invio webhook: HTTP {response.status}")
            except Exception as e:
                logger.error(f"Errore nell'invio degli alert via webhook: {e}")
        
        # Email
        email_config = alert_methods.get('email')
        if email_config:
            # Implementazione invio email
            pass
    
    def get_system_status(self) -> Dict[str, Any]:
        """Restituisce lo stato completo del sistema."""
        # Ottiene le metriche più recenti
        latest_metrics = {}
        for name, values in self.recent_metrics.items():
            if values:
                latest_metrics[name] = values[-1]
        
        # Formatta servizi per output
        services = {}
        for name, status in self.services_status.items():
            services[name] = status.to_dict()
        
        # Alert correnti
        current_alerts = []
        for alert in reversed(self.alerts[-20:]):  # Ultimi 20 alert
            current_alerts.append(alert.to_dict())
        
        # Statistiche globali
        total_services = len(self.services_status)
        active_services = sum(1 for s in self.services_status.values() if s.is_up)
        
        return {
            'timestamp': time.time(),
            'hostname': socket.gethostname(),
            'system': {
                'platform': platform.platform(),
                'cpu_count': psutil.cpu_count(),
                'uptime': time.time() - psutil.boot_time()
            },
            'metrics': latest_metrics,
            'services': {
                'total': total_services,
                'active': active_services,
                'availability': (active_services / total_services * 100) if total_services else 0,
                'details': services
            },
            'alerts': {
                'active': sum(1 for a in self.alerts if not a.resolved),
                'critical': sum(1 for a in self.alerts if not a.resolved and a.severity == 'critical'),
                'warning': sum(1 for a in self.alerts if not a.resolved and a.severity == 'warning'),
                'recent': current_alerts
            }
        }

class MonitoringManager:
    """Gestisce il sistema di monitoraggio."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Inizializza il sistema di monitoraggio.
        
        Args:
            config_path: Percorso al file di configurazione JSON
        """
        self.config = DEFAULT_CONFIG
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    loaded_config = json.load(f)
                    self.config.update(loaded_config)
                logger.info(f"Configurazione caricata da {config_path}")
            except Exception as e:
                logger.error(f"Errore nel caricamento della configurazione: {e}")
        
        self.collector = MetricCollector(self.config)
        self.running = False
        self._monitor_task = None
    
    async def start(self):
        """Avvia il monitoraggio."""
        if self.running:
            logger.warning("Il sistema di monitoraggio è già in esecuzione")
            return
        
        await self.collector.start()
        self.running = True
        self._monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Sistema di monitoraggio avviato")
    
    async def stop(self):
        """Arresta il monitoraggio."""
        if not self.running:
            return
        
        self.running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        
        await self.collector.stop()
        logger.info("Sistema di monitoraggio arrestato")
    
    async def _monitoring_loop(self):
        """Loop principale di monitoraggio."""
        interval = self.config.get('monitoring_interval', 30)
        
        while self.running:
            try:
                # Raccoglie metriche di sistema
                metrics = await self.collector.collect_system_metrics()
                
                # Controlla servizi
                await self.collector.check_services()
                
                # Controlla violazioni threshold
                alerts = self.collector.check_threshold_violations()
                
                # Invia alert
                if alerts:
                    await self.collector.send_alerts(alerts)
                
                # Attendi il prossimo ciclo
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Errore nel ciclo di monitoraggio: {e}")
                logger.debug(traceback.format_exc())
                await asyncio.sleep(5)  # Breve pausa in caso di errore
    
    def get_status(self) -> Dict[str, Any]:
        """Restituisce lo stato corrente del sistema."""
        return self.collector.get_system_status()
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Conferma un alert."""
        for alert in self.collector.alerts:
            if str(id(alert)) == alert_id:
                alert.acknowledged = True
                return True
        return False
    
    def resolve_alert(self, alert_id: str, notes: str = "") -> bool:
        """Risolve un alert."""
        for alert in self.collector.alerts:
            if str(id(alert)) == alert_id:
                alert.resolved = True
                alert.resolved_at = time.time()
                if notes:
                    alert.notes = notes
                return True
        return False

# Singleton del manager di monitoraggio
_monitoring_manager = None

def get_monitoring_manager(config_path: Optional[str] = None) -> MonitoringManager:
    """Restituisce l'istanza singleton del MonitoringManager."""
    global _monitoring_manager
    if _monitoring_manager is None:
        _monitoring_manager = MonitoringManager(config_path)
    return _monitoring_manager

async def start_monitoring(config_path: Optional[str] = None):
    """Avvia il sistema di monitoraggio come processo standalone."""
    manager = get_monitoring_manager(config_path)
    await manager.start()
    
    try:
        # Mantiene il processo attivo
        while True:
            await asyncio.sleep(3600)  # 1 ora
    except (asyncio.CancelledError, KeyboardInterrupt):
        await manager.stop()

if __name__ == "__main__":
    # Avvia il sistema di monitoraggio come script standalone
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        config_path = sys.argv[1] if len(sys.argv) > 1 else None
        asyncio.run(start_monitoring(config_path))
    except KeyboardInterrupt:
        print("Monitoraggio interrotto dall'utente") 