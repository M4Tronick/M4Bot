#!/usr/bin/env python3
"""
M4Bot - Rilevamento Anomalie

Questo modulo implementa algoritmi di rilevamento anomalie per identificare
comportamenti insoliti nel sistema M4Bot prima che causino problemi gravi.
Utilizza approcci statistici e di machine learning per rilevare pattern anomali.

Funzionalità:
- Analisi statistica di metriche di sistema e applicazione
- Rilevamento outlier in tempo reale
- Previsione di trend problematici
- Integrazione con il sistema di self-healing
"""

import os
import json
import time
import logging
import asyncio
import numpy as np
from typing import Dict, List, Any, Optional, Tuple, Union
from datetime import datetime, timedelta
from collections import deque
from dataclasses import dataclass, field

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('m4bot.stability.anomaly_detection')

@dataclass
class MetricSeries:
    """Serie temporale di una metrica con statistiche."""
    name: str
    values: deque = field(default_factory=lambda: deque(maxlen=1000))
    timestamps: deque = field(default_factory=lambda: deque(maxlen=1000))
    mean: float = 0.0
    std_dev: float = 0.0
    min_value: float = float('inf')
    max_value: float = float('-inf')
    last_update: float = field(default_factory=time.time)
    
    def add_value(self, value: float, timestamp: Optional[float] = None):
        """Aggiunge un valore alla serie e aggiorna le statistiche."""
        if timestamp is None:
            timestamp = time.time()
        
        self.values.append(value)
        self.timestamps.append(timestamp)
        self.last_update = timestamp
        
        # Aggiorna min e max
        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)
        
        # Aggiorna statistiche solo se abbiamo abbastanza dati
        if len(self.values) > 1:
            self._update_statistics()
    
    def _update_statistics(self):
        """Aggiorna le statistiche della serie."""
        values_array = np.array(self.values)
        self.mean = np.mean(values_array)
        self.std_dev = np.std(values_array)
    
    def is_anomaly(self, value: float, z_threshold: float = 3.0) -> bool:
        """Determina se un valore è anomalo usando lo Z-score."""
        if len(self.values) < 10:  # Serve un minimo di dati per un rilevamento affidabile
            return False
            
        z_score = abs(value - self.mean) / max(self.std_dev, 0.0001)  # Evita divisione per zero
        return z_score > z_threshold
    
    def recent_trend(self, window: int = 10) -> float:
        """Calcola il trend recente (positivo = crescente, negativo = decrescente)."""
        if len(self.values) < window:
            return 0.0
            
        recent_values = list(self.values)[-window:]
        if len(recent_values) < 2:
            return 0.0
            
        # Calcola pendenza della linea di regressione
        x = np.arange(len(recent_values))
        y = np.array(recent_values)
        
        # Stima della pendenza (può essere migliorata con regressione lineare)
        return (y[-1] - y[0]) / max(len(y) - 1, 1)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte la serie in un dizionario."""
        return {
            "name": self.name,
            "count": len(self.values),
            "mean": self.mean,
            "std_dev": self.std_dev,
            "min": self.min_value,
            "max": self.max_value,
            "last_value": list(self.values)[-1] if self.values else None,
            "last_update": self.last_update
        }

class AnomalyDetector:
    """Sistema di rilevamento anomalie per M4Bot."""
    
    def __init__(self, history_size: int = 1000):
        """
        Inizializza il rilevatore di anomalie.
        
        Args:
            history_size: Dimensione dell'archivio storico per metrica
        """
        self.metrics: Dict[str, MetricSeries] = {}
        self.anomalies: List[Dict[str, Any]] = []
        self.history_size = history_size
        self.running = False
        self.collection_task = None
        
        # Configurazioni
        self.anomaly_threshold = 3.0  # Z-score per considerare un valore anomalo
        self.collection_interval = 60  # secondi tra collezioni di metriche
        
        logger.info("Sistema di rilevamento anomalie inizializzato")
    
    def register_metric(self, name: str) -> MetricSeries:
        """Registra una nuova metrica da monitorare."""
        if name not in self.metrics:
            self.metrics[name] = MetricSeries(name=name)
            logger.info(f"Metrica registrata: {name}")
        return self.metrics[name]
    
    def add_metric_value(self, name: str, value: float, timestamp: Optional[float] = None):
        """Aggiunge un valore a una metrica e verifica anomalie."""
        if name not in self.metrics:
            self.register_metric(name)
        
        metric = self.metrics[name]
        
        # Verifica anomalia prima di aggiungere il valore
        if metric.is_anomaly(value, self.anomaly_threshold):
            self._record_anomaly(name, value, timestamp or time.time())
        
        # Aggiunge il valore
        metric.add_value(value, timestamp)
    
    def _record_anomaly(self, metric_name: str, value: float, timestamp: float):
        """Registra un'anomalia rilevata."""
        metric = self.metrics[metric_name]
        
        anomaly = {
            "metric": metric_name,
            "value": value,
            "timestamp": timestamp,
            "mean": metric.mean,
            "std_dev": metric.std_dev,
            "z_score": abs(value - metric.mean) / max(metric.std_dev, 0.0001)
        }
        
        self.anomalies.append(anomaly)
        logger.warning(f"Anomalia rilevata: {metric_name} = {value} (z-score: {anomaly['z_score']:.2f})")
    
    async def start_collection(self):
        """Avvia la raccolta automatica di metriche di sistema."""
        if self.running:
            logger.warning("La raccolta di metriche è già in esecuzione")
            return
        
        self.running = True
        logger.info("Avvio raccolta metrica di sistema")
        
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
    
    async def _collection_loop(self):
        """Loop di raccolta metriche di sistema."""
        logger.info("Avvio loop di raccolta metriche")
        
        try:
            import psutil
        except ImportError:
            logger.error("psutil non disponibile, installalo con 'pip install psutil'")
            self.running = False
            return
        
        while self.running:
            try:
                # Raccolta CPU
                cpu_percent = psutil.cpu_percent(interval=1)
                self.add_metric_value("system.cpu.percent", cpu_percent)
                
                # Per-core CPU
                per_cpu = psutil.cpu_percent(interval=None, percpu=True)
                for i, cpu in enumerate(per_cpu):
                    self.add_metric_value(f"system.cpu.core.{i}.percent", cpu)
                
                # Memoria
                memory = psutil.virtual_memory()
                self.add_metric_value("system.memory.percent", memory.percent)
                self.add_metric_value("system.memory.available_mb", memory.available / (1024 * 1024))
                
                # Disco
                disk = psutil.disk_usage('/')
                self.add_metric_value("system.disk.percent", disk.percent)
                self.add_metric_value("system.disk.free_gb", disk.free / (1024 * 1024 * 1024))
                
                # Rete (somma di tutti gli adattatori)
                net_io = psutil.net_io_counters()
                self.add_metric_value("system.network.bytes_sent", net_io.bytes_sent)
                self.add_metric_value("system.network.bytes_recv", net_io.bytes_recv)
                
                # Load average
                load = psutil.getloadavg()
                self.add_metric_value("system.load.1min", load[0])
                self.add_metric_value("system.load.5min", load[1])
                self.add_metric_value("system.load.15min", load[2])
                
                # Attendi per il prossimo ciclo
                await asyncio.sleep(self.collection_interval)
                
            except asyncio.CancelledError:
                logger.info("Loop di raccolta metriche cancellato")
                break
            except Exception as e:
                logger.error(f"Errore nella raccolta metriche: {e}")
                await asyncio.sleep(10)  # Attesa più lunga in caso di errore
    
    def get_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Restituisce lo stato attuale di tutte le metriche."""
        return {name: metric.to_dict() for name, metric in self.metrics.items()}
    
    def get_metric(self, name: str) -> Optional[Dict[str, Any]]:
        """Restituisce i dati di una metrica specifica."""
        if name in self.metrics:
            return self.metrics[name].to_dict()
        return None
    
    def get_recent_anomalies(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Restituisce le anomalie più recenti."""
        return sorted(self.anomalies, key=lambda x: x['timestamp'], reverse=True)[:limit]
    
    def get_anomalies_by_metric(self, metric_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Restituisce le anomalie per una metrica specifica."""
        metric_anomalies = [a for a in self.anomalies if a['metric'] == metric_name]
        return sorted(metric_anomalies, key=lambda x: x['timestamp'], reverse=True)[:limit]
    
    def predict_metric_value(self, metric_name: str, 
                           time_ahead: int = 3600) -> Tuple[float, float]:
        """
        Predice il valore futuro di una metrica.
        
        Args:
            metric_name: Nome della metrica
            time_ahead: Secondi nel futuro per la previsione
            
        Returns:
            Tupla (valore_previsto, intervallo_confidenza)
        """
        if metric_name not in self.metrics or len(self.metrics[metric_name].values) < 10:
            return (0.0, 0.0)
        
        metric = self.metrics[metric_name]
        
        # Implementazione semplice: trend lineare
        # In un'implementazione reale, si utilizzerebbe un modello più sofisticato
        trend = metric.recent_trend(window=min(30, len(metric.values)))
        last_value = list(metric.values)[-1]
        
        # Calcola previsione: ultimo valore + trend * tempo
        time_units = time_ahead / self.collection_interval
        predicted_value = last_value + (trend * time_units)
        
        # Intervallo di confidenza semplice (basato sulla deviazione standard)
        confidence = metric.std_dev * 1.96  # 95% di confidenza
        
        return (predicted_value, confidence)
    
    def should_trigger_alert(self, metric_name: str) -> bool:
        """
        Determina se una metrica dovrebbe attivare un alert.
        
        Considera sia il valore attuale che il trend previsto.
        """
        if metric_name not in self.metrics:
            return False
            
        metric = self.metrics[metric_name]
        if len(metric.values) < 10:
            return False
            
        # Controlla se l'ultimo valore è anomalo
        last_value = list(metric.values)[-1]
        if metric.is_anomaly(last_value, self.anomaly_threshold):
            return True
            
        # Controlla se il trend è preoccupante
        trend = metric.recent_trend(window=min(30, len(metric.values)))
        
        # Logica specifica per metriche diverse
        if metric_name == "system.cpu.percent" and last_value > 80 and trend > 0:
            return True
            
        if metric_name == "system.memory.percent" and last_value > 85 and trend > 0:
            return True
            
        if metric_name == "system.disk.percent" and last_value > 90:
            return True
            
        return False
    
    def export_metrics_json(self, filepath: str):
        """Esporta le metriche in formato JSON."""
        data = {
            "metrics": self.get_metrics(),
            "anomalies": self.get_recent_anomalies(),
            "timestamp": time.time()
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Metriche esportate in {filepath}")
    
    def import_metrics_json(self, filepath: str):
        """Importa metriche da un file JSON."""
        if not os.path.exists(filepath):
            logger.error(f"File non trovato: {filepath}")
            return False
            
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                
            import_time = data.get("timestamp", time.time())
            
            # Importa i dati delle metriche
            for name, metric_data in data.get("metrics", {}).items():
                # Crea la metrica se non esiste
                if name not in self.metrics:
                    self.register_metric(name)
                
                # Importa ultimo valore
                if "last_value" in metric_data and metric_data["last_value"] is not None:
                    self.add_metric_value(name, metric_data["last_value"], import_time)
            
            logger.info(f"Metriche importate da {filepath}")
            return True
                
        except Exception as e:
            logger.error(f"Errore nell'importazione delle metriche: {e}")
            return False

# Singola istanza del rilevatore di anomalie
_anomaly_detector = None

def get_anomaly_detector() -> AnomalyDetector:
    """Restituisce l'istanza singleton del rilevatore di anomalie."""
    global _anomaly_detector
    if _anomaly_detector is None:
        _anomaly_detector = AnomalyDetector()
    return _anomaly_detector

# Avvio quando il modulo è eseguito direttamente
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="M4Bot Anomaly Detection System")
    parser.add_argument("--export", type=str, help="Esporta metriche in un file JSON")
    parser.add_argument("--import-file", type=str, help="Importa metriche da un file JSON")
    parser.add_argument("--collect", action="store_true", help="Avvia raccolta metriche di sistema")
    parser.add_argument("--interval", type=int, default=60, help="Intervallo raccolta in secondi")
    parser.add_argument("--duration", type=int, default=3600, help="Durata raccolta in secondi")
    
    args = parser.parse_args()
    
    # Ottieni il rilevatore
    detector = get_anomaly_detector()
    
    if args.import_file:
        detector.import_metrics_json(args.import_file)
    
    if args.collect:
        detector.collection_interval = args.interval
        
        async def run_collection():
            await detector.start_collection()
            await asyncio.sleep(args.duration)
            await detector.stop_collection()
            
            if args.export:
                detector.export_metrics_json(args.export)
        
        asyncio.run(run_collection())
    
    elif args.export:
        detector.export_metrics_json(args.export) 