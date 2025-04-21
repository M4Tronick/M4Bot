#!/usr/bin/env python3
"""
M4Bot - Sistema di Monitoraggio

Questo modulo implementa un sistema avanzato di monitoraggio per tutte le componenti
di M4Bot, tracciando metriche di sistema, performance delle applicazioni e stato
dei servizi.

Funzionalità:
- Monitoraggio risorse sistema (CPU, memoria, disco, rete)
- Tracciamento performance applicazione (tempi di risposta, throughput)
- Monitoraggio servizi e dipendenze
- Esportazione metriche in vari formati (Prometheus, JSON, CSV)
- Generazione avvisi su soglie configurabili
"""

import os
import sys
import json
import time
import logging
import asyncio
import datetime
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('m4bot.stability.monitoring')

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

class SystemMonitor:
    """Sistema di monitoraggio per M4Bot."""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Inizializza il sistema di monitoraggio.
        
        Args:
            config_path: Percorso del file di configurazione (opzionale)
        """
        self.metrics: Dict[str, Metric] = {}
        self.config_path = config_path
        self.config = self._load_config()
        
        # Stato del sistema
        self.running = False
        self.collection_task = None
        
        # Directory per i dati
        self.data_dir = Path(self.config.get('data_dir', './monitoring_data'))
        self.data_dir.mkdir(exist_ok=True, parents=True)
        
        # Intervalli di raccolta
        self.system_metrics_interval = self.config.get('system_metrics_interval', 60)
        self.app_metrics_interval = self.config.get('app_metrics_interval', 30)
        self.service_check_interval = self.config.get('service_check_interval', 60)
        
        logger.info(f"Sistema di monitoraggio inizializzato, dati in {self.data_dir}")
    
    def _load_config(self) -> Dict[str, Any]:
        """Carica la configurazione dal file."""
        default_config = {
            'system_metrics_interval': 60,
            'app_metrics_interval': 30,
            'service_check_interval': 60,
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
    
    def get_metric(self, name: str) -> Optional[Metric]:
        """Restituisce una metrica per nome."""
        return self.metrics.get(name)
    
    def get_metrics_by_prefix(self, prefix: str) -> Dict[str, Metric]:
        """Restituisce tutte le metriche che iniziano con un prefisso."""
        return {name: metric for name, metric in self.metrics.items() 
                if name.startswith(prefix)}
    
    async def start_collection(self):
        """Avvia la raccolta automatica di metriche."""
        if self.running:
            logger.warning("La raccolta è già in esecuzione")
            return
        
        self.running = True
        logger.info("Avvio raccolta metriche")
        
        # Inizializziamo le metriche di sistema
        self._init_system_metrics()
        
        # Avvia il task di raccolta
        self.collection_task = asyncio.create_task(self._collection_loop())
    
    async def stop_collection(self):
        """Ferma la raccolta automatica di metriche."""
        if not self.running:
            return
            
        self.running = False
        logger.info("Arresto raccolta metriche")
        
        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                pass
            self.collection_task = None
    
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
        
        # Metriche applicazione
        self.register_metric(
            name="app.requests.total", 
            metric_type=MetricType.COUNTER,
            description="Totale richieste ricevute"
        )
        self.register_metric(
            name="app.requests.error", 
            metric_type=MetricType.COUNTER,
            description="Totale errori nelle richieste"
        )
        self.register_metric(
            name="app.response_time.ms", 
            metric_type=MetricType.HISTOGRAM,
            description="Tempi di risposta in millisecondi",
            initial_value={"sum": 0, "count": 0, "min": 0, "max": 0}
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
                if current_time - last_system_collection >= self.system_metrics_interval:
                    await self._collect_system_metrics()
                    last_system_collection = current_time
                
                # Raccolta metriche applicazione
                if current_time - last_app_collection >= self.app_metrics_interval:
                    await self._collect_app_metrics()
                    last_app_collection = current_time
                
                # Controllo servizi
                if current_time - last_service_check >= self.service_check_interval:
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
            self._check_thresholds()
            
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
                        
            except Exception as e:
                logger.error(f"Errore nel caricamento delle metriche dell'app: {e}")
    
    async def _check_services(self):
        """Verifica lo stato dei servizi."""
        # In un'implementazione reale, qui si verificherebbero i servizi
        # da monitorare, utilizzando systemctl, docker inspect, ecc.
        pass
    
    def _check_thresholds(self):
        """Controlla le soglie delle metriche e genera avvisi."""
        thresholds = self.config.get('thresholds', {})
        
        # CPU
        cpu_value = self.get_metric("system.cpu.usage_percent").value
        cpu_warning = thresholds.get('cpu_warning', 75)
        cpu_critical = thresholds.get('cpu_critical', 90)
        
        if cpu_value >= cpu_critical:
            logger.critical(f"CPU usage critical: {cpu_value}%")
            # Qui si genererebbero avvisi
        elif cpu_value >= cpu_warning:
            logger.warning(f"CPU usage high: {cpu_value}%")
        
        # Memoria
        mem_value = self.get_metric("system.memory.usage_percent").value
        mem_warning = thresholds.get('memory_warning', 80)
        mem_critical = thresholds.get('memory_critical', 95)
        
        if mem_value >= mem_critical:
            logger.critical(f"Memory usage critical: {mem_value}%")
        elif mem_value >= mem_warning:
            logger.warning(f"Memory usage high: {mem_value}%")
        
        # Disco
        disk_value = self.get_metric("system.disk.usage_percent").value
        disk_warning = thresholds.get('disk_warning', 85)
        disk_critical = thresholds.get('disk_critical', 95)
        
        if disk_value >= disk_critical:
            logger.critical(f"Disk usage critical: {disk_value}%")
        elif disk_value >= disk_warning:
            logger.warning(f"Disk usage high: {disk_value}%")
    
    def _export_metrics(self):
        """Esporta le metriche su file."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = self.data_dir / f"metrics_{timestamp}.json"
        
        try:
            data = {
                "timestamp": time.time(),
                "metrics": {name: metric.to_dict() for name, metric in self.metrics.items()}
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
        cpu = self.get_metric("system.cpu.usage_percent")
        memory = self.get_metric("system.memory.usage_percent")
        disk = self.get_metric("system.disk.usage_percent")
        
        return {
            "cpu_percent": cpu.value if cpu else None,
            "memory_percent": memory.value if memory else None,
            "disk_percent": disk.value if disk else None,
            "timestamp": time.time()
        }
    
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

# Singola istanza del sistema di monitoraggio
_system_monitor = None

def get_system_monitor(config_path: Optional[str] = None) -> SystemMonitor:
    """Restituisce l'istanza singleton del sistema di monitoraggio."""
    global _system_monitor
    if _system_monitor is None:
        _system_monitor = SystemMonitor(config_path)
    return _system_monitor

# Avvio quando il modulo è eseguito direttamente
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="M4Bot System Monitoring")
    parser.add_argument("--config", type=str, help="Percorso del file di configurazione")
    parser.add_argument("--collect", action="store_true", help="Avvia raccolta metriche")
    parser.add_argument("--duration", type=int, default=3600, help="Durata raccolta in secondi")
    parser.add_argument("--export", type=str, help="Esporta metriche attuali in un file JSON")
    
    args = parser.parse_args()
    
    # Ottieni il monitor
    monitor = get_system_monitor(args.config)
    
    if args.collect:
        async def run_collection():
            await monitor.start_collection()
            await asyncio.sleep(args.duration)
            await monitor.stop_collection()
            
            if args.export:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                export_file = args.export.format(timestamp=timestamp)
                
                data = {
                    "timestamp": time.time(),
                    "metrics": monitor.get_all_metrics()
                }
                
                with open(export_file, 'w') as f:
                    json.dump(data, f, indent=2)
                
                print(f"Metriche esportate in {export_file}")
        
        asyncio.run(run_collection())
    
    elif args.export:
        # Esporta metriche attuali
        monitor._init_system_metrics()  # Inizializza le metriche
        
        data = {
            "timestamp": time.time(),
            "metrics": monitor.get_all_metrics()
        }
        
        with open(args.export, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Metriche vuote esportate in {args.export}") 