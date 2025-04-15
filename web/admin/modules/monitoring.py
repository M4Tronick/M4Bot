"""
Modulo per il monitoraggio di server e servizi.
Implementa la raccolta di metriche, analisi delle prestazioni e gestione degli avvisi.
"""

import os
import asyncio
import datetime
import logging
import json
import socket
import platform
import time
from typing import Dict, List, Optional, Union, Any

import psutil
import aiohttp
import asyncpg
import aioredis
import docker
from dateutil import parser

logger = logging.getLogger('monitoring')

class MetricsCollector:
    """Raccoglie le metriche localmente e da server remoti."""
    
    def __init__(self, db_pool: asyncpg.Pool, redis_pool: aioredis.ConnectionPool):
        self.db_pool = db_pool
        self.redis_pool = redis_pool
        self.collectors = {}
        self.docker_client = None
        
        try:
            self.docker_client = docker.from_env()
            logger.info("Docker client inizializzato con successo")
        except Exception as e:
            logger.warning(f"Impossibile connettersi al daemon Docker: {e}")
    
    async def collect_system_metrics(self, host_id: str = 'local') -> Dict[str, Any]:
        """Raccoglie le metriche di sistema dall'host locale."""
        metrics = {
            'host_id': host_id,
            'timestamp': datetime.datetime.now().isoformat(),
            'cpu': {
                'usage_percent': psutil.cpu_percent(interval=1),
                'cores_physical': psutil.cpu_count(logical=False),
                'cores_logical': psutil.cpu_count(logical=True),
                'load_avg': os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
            },
            'memory': {
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'used': psutil.virtual_memory().used,
                'percent': psutil.virtual_memory().percent
            },
            'disk': {
                'total': psutil.disk_usage('/').total,
                'free': psutil.disk_usage('/').free,
                'used': psutil.disk_usage('/').used,
                'percent': psutil.disk_usage('/').percent
            },
            'network': {
                'bytes_sent': psutil.net_io_counters().bytes_sent,
                'bytes_recv': psutil.net_io_counters().bytes_recv,
                'packets_sent': psutil.net_io_counters().packets_sent,
                'packets_recv': psutil.net_io_counters().packets_recv,
                'errors_in': psutil.net_io_counters().errin,
                'errors_out': psutil.net_io_counters().errout
            }
        }
        
        # Aggiungi info sul sistema operativo
        metrics['system'] = {
            'name': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'hostname': socket.gethostname(),
            'uptime': int(time.time() - psutil.boot_time())
        }
        
        return metrics
        
    async def collect_docker_metrics(self) -> Dict[str, Any]:
        """Raccoglie le metriche dei container Docker."""
        if not self.docker_client:
            return {'containers': []}
            
        try:
            containers = self.docker_client.containers.list()
            container_metrics = []
            
            for container in containers:
                stats = container.stats(stream=False)
                
                # Calcola CPU e memoria
                cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                            stats['precpu_stats']['cpu_usage']['total_usage']
                system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                              stats['precpu_stats']['system_cpu_usage']
                cpu_percent = 0.0
                if system_delta > 0:
                    cpu_percent = (cpu_delta / system_delta) * 100.0
                    
                mem_usage = stats['memory_stats'].get('usage', 0)
                mem_limit = stats['memory_stats'].get('limit', 1)
                mem_percent = (mem_usage / mem_limit) * 100.0 if mem_limit > 0 else 0
                
                container_metrics.append({
                    'id': container.id,
                    'name': container.name,
                    'status': container.status,
                    'image': container.image.tags[0] if container.image.tags else container.image.id,
                    'cpu_percent': round(cpu_percent, 2),
                    'memory_usage': mem_usage,
                    'memory_limit': mem_limit,
                    'memory_percent': round(mem_percent, 2),
                    'network_rx': stats.get('networks', {}).get('eth0', {}).get('rx_bytes', 0),
                    'network_tx': stats.get('networks', {}).get('eth0', {}).get('tx_bytes', 0)
                })
            
            return {'containers': container_metrics}
        except Exception as e:
            logger.error(f"Errore nella raccolta delle metriche Docker: {e}")
            return {'containers': [], 'error': str(e)}
    
    async def collect_database_metrics(self) -> Dict[str, Any]:
        """Raccoglie le metriche dal database PostgreSQL."""
        metrics = {
            'postgres': {
                'connections': 0,
                'active_queries': 0,
                'locks': 0,
                'uptime': 0,
                'size': 0,
                'replication_lag': None
            }
        }
        
        try:
            async with self.db_pool.acquire() as conn:
                # Numero di connessioni
                conn_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM pg_stat_activity
                """)
                metrics['postgres']['connections'] = conn_count
                
                # Query attive
                active_queries = await conn.fetchval("""
                    SELECT COUNT(*) FROM pg_stat_activity
                    WHERE state = 'active' AND pid <> pg_backend_pid()
                """)
                metrics['postgres']['active_queries'] = active_queries
                
                # Locks
                locks = await conn.fetchval("""
                    SELECT COUNT(*) FROM pg_locks
                """)
                metrics['postgres']['locks'] = locks
                
                # Uptime
                uptime = await conn.fetchval("""
                    SELECT EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time()))::integer
                """)
                metrics['postgres']['uptime'] = uptime
                
                # Dimensione database
                db_size = await conn.fetchval("""
                    SELECT pg_database_size(current_database())
                """)
                metrics['postgres']['size'] = db_size
                
                # Lag di replicazione (se è uno slave)
                try:
                    replication_lag = await conn.fetchval("""
                        SELECT EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp()))::integer
                        WHERE pg_is_in_recovery()
                    """)
                    metrics['postgres']['replication_lag'] = replication_lag
                except:
                    # Non è uno slave o non supporta la funzione
                    pass
        except Exception as e:
            logger.error(f"Errore nella raccolta delle metriche del database: {e}")
        
        return metrics
    
    async def collect_redis_metrics(self) -> Dict[str, Any]:
        """Raccoglie le metriche da Redis."""
        metrics = {
            'redis': {
                'connected_clients': 0,
                'used_memory': 0,
                'used_memory_peak': 0,
                'memory_fragmentation_ratio': 0,
                'total_commands_processed': 0,
                'total_connections_received': 0,
                'uptime': 0,
                'expired_keys': 0
            }
        }
        
        try:
            redis = aioredis.Redis(connection_pool=self.redis_pool)
            info = await redis.info()
            
            metrics['redis']['connected_clients'] = info.get('connected_clients', 0)
            metrics['redis']['used_memory'] = info.get('used_memory', 0)
            metrics['redis']['used_memory_peak'] = info.get('used_memory_peak', 0)
            metrics['redis']['memory_fragmentation_ratio'] = info.get('mem_fragmentation_ratio', 0)
            metrics['redis']['total_commands_processed'] = info.get('total_commands_processed', 0)
            metrics['redis']['total_connections_received'] = info.get('total_connections_received', 0)
            metrics['redis']['uptime'] = info.get('uptime_in_seconds', 0)
            metrics['redis']['expired_keys'] = info.get('expired_keys', 0)
        except Exception as e:
            logger.error(f"Errore nella raccolta delle metriche Redis: {e}")
        
        return metrics
    
    async def collect_remote_metrics(self, host: Dict[str, Any]) -> Dict[str, Any]:
        """Raccoglie le metriche da un server remoto tramite API."""
        try:
            api_url = host['api_url']
            auth_token = host.get('auth_token')
            
            headers = {}
            if auth_token:
                headers['Authorization'] = f'Bearer {auth_token}'
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{api_url}/api/v1/metrics", headers=headers) as response:
                    if response.status == 200:
                        metrics = await response.json()
                        return metrics
                    else:
                        error_text = await response.text()
                        logger.error(f"Errore nella raccolta delle metriche remote da {host['name']}: {error_text}")
                        return {
                            'host_id': host['id'],
                            'error': f"HTTP {response.status}: {error_text}",
                            'timestamp': datetime.datetime.now().isoformat()
                        }
        except Exception as e:
            logger.error(f"Errore nella connessione al server remoto {host['name']}: {e}")
            return {
                'host_id': host['id'],
                'error': str(e),
                'timestamp': datetime.datetime.now().isoformat()
            }
    
    async def collect_and_store_metrics(self):
        """Raccoglie e salva tutte le metriche nel database."""
        # Metriche di sistema locale
        system_metrics = await self.collect_system_metrics()
        await self._store_metrics('system', system_metrics)
        
        # Metriche Docker
        docker_metrics = await self.collect_docker_metrics()
        await self._store_metrics('docker', docker_metrics)
        
        # Metriche database
        db_metrics = await self.collect_database_metrics()
        await self._store_metrics('database', db_metrics)
        
        # Metriche Redis
        redis_metrics = await self.collect_redis_metrics()
        await self._store_metrics('redis', redis_metrics)
        
        # Metriche da host remoti
        async with self.db_pool.acquire() as conn:
            hosts = await conn.fetch("""
                SELECT id, name, api_url, auth_token, is_active
                FROM monitoring_hosts
                WHERE is_active = true
            """)
            
            for host in hosts:
                host_dict = dict(host)
                remote_metrics = await self.collect_remote_metrics(host_dict)
                await self._store_metrics(f"remote_{host['id']}", remote_metrics)
    
    async def _store_metrics(self, metrics_type: str, metrics: Dict[str, Any]):
        """Salva le metriche nel database."""
        try:
            timestamp = metrics.get('timestamp', datetime.datetime.now().isoformat())
            if isinstance(timestamp, str):
                timestamp = parser.parse(timestamp)
            
            metrics_json = json.dumps(metrics)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO metrics (type, timestamp, data)
                    VALUES ($1, $2, $3)
                """, metrics_type, timestamp, metrics_json)
                
            # Salva anche l'ultima metrica in Redis per accesso rapido
            async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                await redis.set(f"metrics:{metrics_type}:latest", metrics_json)
                await redis.expire(f"metrics:{metrics_type}:latest", 3600)  # Scade dopo 1 ora
                
            logger.debug(f"Metriche {metrics_type} salvate correttamente")
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle metriche {metrics_type}: {e}")

class HealthChecker:
    """Verifica la salute dei servizi e genera avvisi."""
    
    def __init__(self, db_pool: asyncpg.Pool, redis_pool: aioredis.ConnectionPool, notification_manager=None):
        self.db_pool = db_pool
        self.redis_pool = redis_pool
        self.notification_manager = notification_manager
        self.checks = {}
        self.thresholds = {
            'cpu_warning': 75.0,
            'cpu_critical': 90.0,
            'memory_warning': 80.0,
            'memory_critical': 90.0,
            'disk_warning': 80.0,
            'disk_critical': 90.0,
            'service_response_time_warning': 2.0,  # secondi
            'service_response_time_critical': 5.0   # secondi
        }
    
    async def load_thresholds(self):
        """Carica le soglie dal database."""
        try:
            async with self.db_pool.acquire() as conn:
                thresholds = await conn.fetch("""
                    SELECT key, value FROM monitoring_thresholds
                """)
                
                for threshold in thresholds:
                    self.thresholds[threshold['key']] = float(threshold['value'])
                    
            logger.info("Soglie di monitoraggio caricate dal database")
        except Exception as e:
            logger.error(f"Errore nel caricamento delle soglie di monitoraggio: {e}")
    
    async def check_system_health(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Verifica la salute del sistema in base alle metriche raccolte."""
        results = {
            'status': 'ok',
            'checks': [],
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        # CPU
        cpu_percent = metrics.get('cpu', {}).get('usage_percent', 0)
        if cpu_percent >= self.thresholds['cpu_critical']:
            results['checks'].append({
                'component': 'cpu',
                'status': 'critical',
                'message': f"Utilizzo CPU critico: {cpu_percent}%",
                'value': cpu_percent,
                'threshold': self.thresholds['cpu_critical']
            })
            results['status'] = 'critical'
        elif cpu_percent >= self.thresholds['cpu_warning']:
            results['checks'].append({
                'component': 'cpu',
                'status': 'warning',
                'message': f"Utilizzo CPU elevato: {cpu_percent}%",
                'value': cpu_percent,
                'threshold': self.thresholds['cpu_warning']
            })
            if results['status'] != 'critical':
                results['status'] = 'warning'
        else:
            results['checks'].append({
                'component': 'cpu',
                'status': 'ok',
                'message': f"Utilizzo CPU normale: {cpu_percent}%",
                'value': cpu_percent
            })
        
        # Memoria
        memory_percent = metrics.get('memory', {}).get('percent', 0)
        if memory_percent >= self.thresholds['memory_critical']:
            results['checks'].append({
                'component': 'memory',
                'status': 'critical',
                'message': f"Utilizzo memoria critico: {memory_percent}%",
                'value': memory_percent,
                'threshold': self.thresholds['memory_critical']
            })
            results['status'] = 'critical'
        elif memory_percent >= self.thresholds['memory_warning']:
            results['checks'].append({
                'component': 'memory',
                'status': 'warning',
                'message': f"Utilizzo memoria elevato: {memory_percent}%",
                'value': memory_percent,
                'threshold': self.thresholds['memory_warning']
            })
            if results['status'] != 'critical':
                results['status'] = 'warning'
        else:
            results['checks'].append({
                'component': 'memory',
                'status': 'ok',
                'message': f"Utilizzo memoria normale: {memory_percent}%",
                'value': memory_percent
            })
        
        # Disco
        disk_percent = metrics.get('disk', {}).get('percent', 0)
        if disk_percent >= self.thresholds['disk_critical']:
            results['checks'].append({
                'component': 'disk',
                'status': 'critical',
                'message': f"Spazio disco critico: {disk_percent}%",
                'value': disk_percent,
                'threshold': self.thresholds['disk_critical']
            })
            results['status'] = 'critical'
        elif disk_percent >= self.thresholds['disk_warning']:
            results['checks'].append({
                'component': 'disk',
                'status': 'warning',
                'message': f"Spazio disco limitato: {disk_percent}%",
                'value': disk_percent,
                'threshold': self.thresholds['disk_warning']
            })
            if results['status'] != 'critical':
                results['status'] = 'warning'
        else:
            results['checks'].append({
                'component': 'disk',
                'status': 'ok',
                'message': f"Spazio disco adeguato: {disk_percent}%",
                'value': disk_percent
            })
        
        return results
    
    async def check_service_health(self, host_id: str = 'local') -> Dict[str, Any]:
        """Verifica la salute dei servizi configurati."""
        results = {
            'host_id': host_id,
            'status': 'ok',
            'services': [],
            'timestamp': datetime.datetime.now().isoformat()
        }
        
        try:
            async with self.db_pool.acquire() as conn:
                services = await conn.fetch("""
                    SELECT id, name, type, endpoint, expected_status_code, timeout, is_active
                    FROM monitoring_services
                    WHERE host_id = $1 AND is_active = true
                """, host_id)
                
                for service in services:
                    service_result = await self._check_service(dict(service))
                    results['services'].append(service_result)
                    
                    # Aggiorna lo stato globale
                    if service_result['status'] == 'critical' and results['status'] != 'critical':
                        results['status'] = 'critical'
                    elif service_result['status'] == 'warning' and results['status'] not in ['critical']:
                        results['status'] = 'warning'
        except Exception as e:
            logger.error(f"Errore nella verifica dei servizi: {e}")
            results['status'] = 'error'
            results['error'] = str(e)
        
        return results
    
    async def _check_service(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Verifica la salute di un singolo servizio."""
        result = {
            'id': service['id'],
            'name': service['name'],
            'type': service['type'],
            'status': 'ok',
            'response_time': None,
            'error': None
        }
        
        try:
            start_time = time.time()
            
            if service['type'] == 'http':
                # Verifica servizio HTTP
                timeout = aiohttp.ClientTimeout(total=service.get('timeout', 10))
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(service['endpoint']) as response:
                        result['response_time'] = time.time() - start_time
                        result['status_code'] = response.status
                        
                        expected_status = service.get('expected_status_code', 200)
                        if response.status != expected_status:
                            result['status'] = 'critical'
                            result['error'] = f"Status code {response.status}, atteso {expected_status}"
                        elif result['response_time'] >= self.thresholds['service_response_time_critical']:
                            result['status'] = 'critical'
                            result['error'] = f"Tempo di risposta critico: {result['response_time']:.2f}s"
                        elif result['response_time'] >= self.thresholds['service_response_time_warning']:
                            result['status'] = 'warning'
                            result['error'] = f"Tempo di risposta lento: {result['response_time']:.2f}s"
            
            elif service['type'] == 'tcp':
                # Verifica servizio TCP
                host, port = service['endpoint'].split(':')
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, int(port)),
                    timeout=service.get('timeout', 10)
                )
                writer.close()
                await writer.wait_closed()
                result['response_time'] = time.time() - start_time
                
                if result['response_time'] >= self.thresholds['service_response_time_critical']:
                    result['status'] = 'critical'
                    result['error'] = f"Tempo di risposta critico: {result['response_time']:.2f}s"
                elif result['response_time'] >= self.thresholds['service_response_time_warning']:
                    result['status'] = 'warning'
                    result['error'] = f"Tempo di risposta lento: {result['response_time']:.2f}s"
                
            elif service['type'] == 'ping':
                # Esegui ping
                response = os.system(f"ping -c 1 -W {service.get('timeout', 5)} {service['endpoint']} > /dev/null 2>&1")
                result['response_time'] = time.time() - start_time
                
                if response != 0:
                    result['status'] = 'critical'
                    result['error'] = f"Host {service['endpoint']} non raggiungibile"
                elif result['response_time'] >= self.thresholds['service_response_time_critical']:
                    result['status'] = 'critical'
                    result['error'] = f"Tempo di risposta critico: {result['response_time']:.2f}s"
                elif result['response_time'] >= self.thresholds['service_response_time_warning']:
                    result['status'] = 'warning'
                    result['error'] = f"Tempo di risposta lento: {result['response_time']:.2f}s"
            
            else:
                result['status'] = 'warning'
                result['error'] = f"Tipo di servizio non supportato: {service['type']}"
        
        except asyncio.TimeoutError:
            result['status'] = 'critical'
            result['error'] = f"Timeout durante la connessione a {service['endpoint']}"
            result['response_time'] = service.get('timeout', 10)
        except Exception as e:
            result['status'] = 'critical'
            result['error'] = str(e)
        
        # Registra il risultato della verifica
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO service_checks 
                    (service_id, status, response_time, error, timestamp)
                    VALUES ($1, $2, $3, $4, $5)
                """, service['id'], result['status'], result['response_time'], result['error'], 
                    datetime.datetime.now())
        except Exception as e:
            logger.error(f"Errore nel salvataggio del risultato della verifica del servizio: {e}")
        
        # Genera notifica se necessario
        if result['status'] in ['warning', 'critical'] and self.notification_manager:
            await self.notification_manager.send_service_alert(
                service_id=service['id'],
                service_name=service['name'],
                status=result['status'],
                message=result.get('error', 'Problema con il servizio')
            )
        
        return result
    
    async def run_health_checks(self):
        """Esegue tutte le verifiche di salute configurate."""
        # Ottieni le ultime metriche del sistema
        async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
            system_metrics_json = await redis.get('metrics:system:latest')
            
            if system_metrics_json:
                system_metrics = json.loads(system_metrics_json)
                system_health = await self.check_system_health(system_metrics)
                
                # Salva i risultati delle verifiche
                async with self.db_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO health_checks (type, status, data, timestamp)
                        VALUES ($1, $2, $3, $4)
                    """, 'system', system_health['status'], json.dumps(system_health),
                        datetime.datetime.now())
                
                # Genera notifiche se necessario
                if system_health['status'] in ['warning', 'critical'] and self.notification_manager:
                    critical_checks = [c for c in system_health['checks'] if c['status'] in ['warning', 'critical']]
                    for check in critical_checks:
                        await self.notification_manager.send_system_alert(
                            component=check['component'],
                            status=check['status'],
                            message=check['message']
                        )
            
            # Verifica la salute dei servizi
            service_health = await self.check_service_health()
            
            # Salva i risultati delle verifiche
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO health_checks (type, status, data, timestamp)
                    VALUES ($1, $2, $3, $4)
                """, 'services', service_health['status'], json.dumps(service_health),
                    datetime.datetime.now())

class MonitoringManager:
    """Gestisce il monitoraggio completo del sistema."""
    
    def __init__(self, db_pool: asyncpg.Pool, redis_pool: aioredis.ConnectionPool, notification_manager=None):
        self.db_pool = db_pool
        self.redis_pool = redis_pool
        self.notification_manager = notification_manager
        self.metrics_collector = MetricsCollector(db_pool, redis_pool)
        self.health_checker = HealthChecker(db_pool, redis_pool, notification_manager)
        self.collection_task = None
        self.health_check_task = None
        self.metrics_retention_days = 30
    
    async def start_collection(self):
        """Avvia la raccolta periodica delle metriche e i controlli di salute."""
        # Carica le soglie dal database
        await self.health_checker.load_thresholds()
        
        # Avvia il task di raccolta metrica (ogni minuto)
        self.collection_task = asyncio.create_task(self._run_metrics_collection())
        
        # Avvia il task di verifica salute (ogni 2 minuti)
        self.health_check_task = asyncio.create_task(self._run_health_checks())
        
        logger.info("Raccolta metriche e controlli di salute avviati")
    
    async def _run_metrics_collection(self):
        """Task in background per la raccolta periodica delle metriche."""
        while True:
            try:
                await self.metrics_collector.collect_and_store_metrics()
                await self._cleanup_old_metrics()
            except Exception as e:
                logger.error(f"Errore nella raccolta delle metriche: {e}")
            
            # Attendi 60 secondi prima della prossima raccolta
            await asyncio.sleep(60)
    
    async def _run_health_checks(self):
        """Task in background per la verifica periodica della salute del sistema."""
        while True:
            try:
                await self.health_checker.run_health_checks()
            except Exception as e:
                logger.error(f"Errore nell'esecuzione dei controlli di salute: {e}")
            
            # Attendi 2 minuti prima del prossimo controllo
            await asyncio.sleep(120)
    
    async def _cleanup_old_metrics(self):
        """Rimuove le metriche più vecchie del periodo di retention."""
        try:
            cutoff_date = datetime.datetime.now() - datetime.timedelta(days=self.metrics_retention_days)
            
            async with self.db_pool.acquire() as conn:
                # Elimina le metriche vecchie
                await conn.execute("""
                    DELETE FROM metrics
                    WHERE timestamp < $1
                """, cutoff_date)
                
                # Elimina i controlli di salute vecchi
                await conn.execute("""
                    DELETE FROM health_checks
                    WHERE timestamp < $1
                """, cutoff_date)
                
                # Elimina le verifiche dei servizi vecchie
                await conn.execute("""
                    DELETE FROM service_checks
                    WHERE timestamp < $1
                """, cutoff_date)
        except Exception as e:
            logger.error(f"Errore nella pulizia delle metriche vecchie: {e}")
    
    async def get_system_overview(self) -> Dict[str, Any]:
        """Ottiene una panoramica dello stato del sistema."""
        overview = {
            'current_status': 'ok',
            'cpu': 0,
            'memory': 0,
            'disk': 0,
            'uptime': 0,
            'alerts_count': 0,
            'critical_services': 0,
            'updated_at': datetime.datetime.now().isoformat()
        }
        
        try:
            # Ottieni le ultime metriche del sistema
            async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                system_metrics_json = await redis.get('metrics:system:latest')
                
                if system_metrics_json:
                    system_metrics = json.loads(system_metrics_json)
                    overview['cpu'] = system_metrics.get('cpu', {}).get('usage_percent', 0)
                    overview['memory'] = system_metrics.get('memory', {}).get('percent', 0)
                    overview['disk'] = system_metrics.get('disk', {}).get('percent', 0)
                    overview['uptime'] = system_metrics.get('system', {}).get('uptime', 0)
            
            # Ottieni lo stato dei controlli di salute
            async with self.db_pool.acquire() as conn:
                # Stato attuale del sistema
                latest_check = await conn.fetchrow("""
                    SELECT status, timestamp FROM health_checks
                    WHERE type = 'system'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                
                if latest_check:
                    overview['current_status'] = latest_check['status']
                    overview['updated_at'] = latest_check['timestamp'].isoformat()
                
                # Conteggio avvisi attivi
                alerts_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM alerts
                    WHERE resolved_at IS NULL
                """)
                overview['alerts_count'] = alerts_count
                
                # Servizi in stato critico
                critical_services = await conn.fetchval("""
                    SELECT COUNT(DISTINCT service_id) FROM service_checks
                    WHERE status = 'critical'
                    AND timestamp > NOW() - INTERVAL '30 minutes'
                """)
                overview['critical_services'] = critical_services
        except Exception as e:
            logger.error(f"Errore nell'ottenimento della panoramica del sistema: {e}")
        
        return overview
    
    async def get_services_status(self) -> Dict[str, str]:
        """Ottiene lo stato dei servizi principali."""
        status = {
            'web': 'unknown',
            'database': 'unknown',
            'redis': 'unknown',
            'bot': 'unknown',
            'api': 'unknown',
            'jobs': 'unknown',
            'updated_at': datetime.datetime.now().isoformat()
        }
        
        try:
            async with self.db_pool.acquire() as conn:
                services = await conn.fetch("""
                    SELECT s.name, sc.status, sc.timestamp
                    FROM monitoring_services s
                    JOIN service_checks sc ON s.id = sc.service_id
                    WHERE s.name IN ('web', 'database', 'redis', 'bot', 'api', 'jobs')
                    AND sc.timestamp = (
                        SELECT MAX(timestamp) 
                        FROM service_checks 
                        WHERE service_id = s.id
                    )
                """)
                
                for service in services:
                    status[service['name']] = service['status']
                    if service['timestamp']:
                        status['updated_at'] = service['timestamp'].isoformat()
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dello stato dei servizi: {e}")
        
        return status
    
    async def get_monitored_hosts(self) -> List[Dict[str, Any]]:
        """Ottiene l'elenco degli host monitorati."""
        hosts = []
        
        try:
            async with self.db_pool.acquire() as conn:
                host_records = await conn.fetch("""
                    SELECT id, name, description, hostname, api_url, 
                           is_active, created_at, updated_at
                    FROM monitoring_hosts
                    ORDER BY name
                """)
                
                for host in host_records:
                    host_data = dict(host)
                    
                    # Ottieni l'ultimo stato dell'host
                    last_check = await conn.fetchrow("""
                        SELECT status, timestamp FROM health_checks
                        WHERE type = 'remote_' || $1
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """, host['id'])
                    
                    if last_check:
                        host_data['status'] = last_check['status']
                        host_data['last_check'] = last_check['timestamp'].isoformat()
                    else:
                        host_data['status'] = 'unknown'
                        host_data['last_check'] = None
                    
                    # Ottieni il conteggio degli avvisi attivi per questo host
                    alerts_count = await conn.fetchval("""
                        SELECT COUNT(*) FROM alerts
                        WHERE host_id = $1 AND resolved_at IS NULL
                    """, host['id'])
                    host_data['alerts_count'] = alerts_count
                    
                    hosts.append(host_data)
        except Exception as e:
            logger.error(f"Errore nell'ottenimento degli host monitorati: {e}")
        
        return hosts
    
    async def get_host_details(self, host_id: str) -> Dict[str, Any]:
        """Ottiene i dettagli di un host monitorato."""
        try:
            async with self.db_pool.acquire() as conn:
                host = await conn.fetchrow("""
                    SELECT id, name, description, hostname, api_url, 
                           is_active, created_at, updated_at
                    FROM monitoring_hosts
                    WHERE id = $1
                """, host_id)
                
                if not host:
                    return None
                
                host_data = dict(host)
                
                # Ottieni le metriche più recenti
                async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                    metrics_json = await redis.get(f"metrics:remote_{host_id}:latest")
                    
                    if metrics_json:
                        host_data['metrics'] = json.loads(metrics_json)
                
                # Ottieni gli avvisi attivi
                alerts = await conn.fetch("""
                    SELECT id, type, severity, message, created_at
                    FROM alerts
                    WHERE host_id = $1 AND resolved_at IS NULL
                    ORDER BY severity DESC, created_at DESC
                """, host_id)
                host_data['alerts'] = [dict(alert) for alert in alerts]
                
                return host_data
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dei dettagli dell'host {host_id}: {e}")
            return None
    
    async def get_host_metrics(self, host_id: str, hours: int = 24) -> Dict[str, List]:
        """Ottiene le metriche storiche per un host specifico."""
        metrics = {
            'timestamps': [],
            'cpu': [],
            'memory': [],
            'disk': []
        }
        
        try:
            cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=hours)
            
            async with self.db_pool.acquire() as conn:
                # Ottieni le metriche con un intervallo di un'ora
                records = await conn.fetch("""
                    SELECT data, timestamp
                    FROM metrics
                    WHERE type = 'remote_' || $1 AND timestamp > $2
                    ORDER BY timestamp
                """, host_id, cutoff_time)
                
                for record in records:
                    metrics['timestamps'].append(record['timestamp'].isoformat())
                    
                    data = record['data']
                    metrics['cpu'].append(data.get('cpu', {}).get('usage_percent', 0))
                    metrics['memory'].append(data.get('memory', {}).get('percent', 0))
                    metrics['disk'].append(data.get('disk', {}).get('percent', 0))
        except Exception as e:
            logger.error(f"Errore nell'ottenimento delle metriche dell'host {host_id}: {e}")
        
        return metrics
    
    async def get_host_alerts(self, host_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Ottiene gli avvisi recenti per un host specifico."""
        alerts = []
        
        try:
            async with self.db_pool.acquire() as conn:
                alert_records = await conn.fetch("""
                    SELECT id, type, severity, message, created_at, resolved_at
                    FROM alerts
                    WHERE host_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                """, host_id, limit)
                
                alerts = [dict(alert) for alert in alert_records]
        except Exception as e:
            logger.error(f"Errore nell'ottenimento degli avvisi dell'host {host_id}: {e}")
        
        return alerts
    
    async def get_services_list(self) -> List[Dict[str, Any]]:
        """Ottiene l'elenco dei servizi monitorati."""
        services = []
        
        try:
            async with self.db_pool.acquire() as conn:
                service_records = await conn.fetch("""
                    SELECT s.id, s.name, s.type, s.endpoint, s.host_id, s.is_active,
                           h.name as host_name
                    FROM monitoring_services s
                    LEFT JOIN monitoring_hosts h ON s.host_id = h.id
                    ORDER BY h.name, s.name
                """)
                
                for service in service_records:
                    service_data = dict(service)
                    
                    # Ottieni l'ultimo controllo del servizio
                    last_check = await conn.fetchrow("""
                        SELECT status, response_time, error, timestamp
                        FROM service_checks
                        WHERE service_id = $1
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """, service['id'])
                    
                    if last_check:
                        service_data['status'] = last_check['status']
                        service_data['response_time'] = last_check['response_time']
                        service_data['error'] = last_check['error']
                        service_data['last_check'] = last_check['timestamp'].isoformat()
                    else:
                        service_data['status'] = 'unknown'
                        service_data['last_check'] = None
                    
                    services.append(service_data)
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dell'elenco dei servizi: {e}")
        
        return services
    
    async def get_realtime_metrics(self) -> Dict[str, Any]:
        """Ottiene le metriche in tempo reale per l'invio tramite WebSocket."""
        metrics = {}
        
        try:
            # Metriche di sistema locale
            system_metrics = await self.metrics_collector.collect_system_metrics()
            metrics['system'] = {
                'cpu': system_metrics.get('cpu', {}).get('usage_percent', 0),
                'memory': system_metrics.get('memory', {}).get('percent', 0),
                'disk': system_metrics.get('disk', {}).get('percent', 0),
                'timestamp': datetime.datetime.now().isoformat()
            }
            
            # Stato dei servizi
            metrics['services'] = {}
            async with self.db_pool.acquire() as conn:
                services = await conn.fetch("""
                    SELECT s.name, sc.status, sc.response_time
                    FROM monitoring_services s
                    JOIN service_checks sc ON s.id = sc.service_id
                    WHERE sc.timestamp = (
                        SELECT MAX(timestamp) 
                        FROM service_checks 
                        WHERE service_id = s.id
                    )
                """)
                
                for service in services:
                    metrics['services'][service['name']] = {
                        'status': service['status'],
                        'response_time': service['response_time']
                    }
            
            # Avvisi attivi
            metrics['alerts'] = {
                'critical': 0,
                'warning': 0,
                'info': 0
            }
            
            async with self.db_pool.acquire() as conn:
                alert_counts = await conn.fetch("""
                    SELECT severity, COUNT(*) as count
                    FROM alerts
                    WHERE resolved_at IS NULL
                    GROUP BY severity
                """)
                
                for alert in alert_counts:
                    metrics['alerts'][alert['severity']] = alert['count']
        except Exception as e:
            logger.error(f"Errore nell'ottenimento delle metriche in tempo reale: {e}")
            metrics['error'] = str(e)
        
        return metrics
    
    async def get_metrics(self, host_id: str = None, metric_type: str = 'cpu', hours: int = 24) -> Dict[str, List]:
        """Ottiene le metriche per la visualizzazione nei grafici."""
        result = {
            'timestamps': [],
            'values': []
        }
        
        try:
            cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=hours)
            
            async with self.db_pool.acquire() as conn:
                # Prepara la query in base al tipo di metrica
                if host_id and host_id != 'local':
                    query = """
                        SELECT timestamp, data->>'host_id' as host_id, 
                               CASE
                                   WHEN $2 = 'cpu' THEN (data->'cpu'->>'usage_percent')::float
                                   WHEN $2 = 'memory' THEN (data->'memory'->>'percent')::float
                                   WHEN $2 = 'disk' THEN (data->'disk'->>'percent')::float
                                   ELSE 0
                               END as value
                        FROM metrics
                        WHERE type = 'remote_' || $1 AND timestamp > $3
                        ORDER BY timestamp
                    """
                    records = await conn.fetch(query, host_id, metric_type, cutoff_time)
                else:
                    query = """
                        SELECT timestamp, 
                               CASE
                                   WHEN $1 = 'cpu' THEN (data->'cpu'->>'usage_percent')::float
                                   WHEN $1 = 'memory' THEN (data->'memory'->>'percent')::float
                                   WHEN $1 = 'disk' THEN (data->'disk'->>'percent')::float
                                   ELSE 0
                               END as value
                        FROM metrics
                        WHERE type = 'system' AND timestamp > $2
                        ORDER BY timestamp
                    """
                    records = await conn.fetch(query, metric_type, cutoff_time)
                
                for record in records:
                    result['timestamps'].append(record['timestamp'].isoformat())
                    result['values'].append(record['value'])
        except Exception as e:
            logger.error(f"Errore nell'ottenimento delle metriche per il grafico: {e}")
        
        return result 