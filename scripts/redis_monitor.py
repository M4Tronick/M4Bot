#!/usr/bin/env python3
"""
Redis Monitor - Sistema di monitoraggio avanzato per Redis
Controlla memoria, latenza, chiavi e altri parametri vitali
per M4Bot in ambiente Linux.
"""

import os
import sys
import time
import json
import logging
import asyncio
import argparse
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

import redis
import aioredis
import psutil
import matplotlib.pyplot as plt
import numpy as np

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join("logs", "redis_monitor.log")),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("RedisMonitor")

class RedisMonitor:
    """Sistema di monitoraggio per Redis"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Inizializza il monitor Redis
        
        Args:
            config: Configurazione del monitor (URL Redis, soglie, etc.)
        """
        self.config = config
        self.redis_url = config.get("redis_url", "redis://localhost:6379/0")
        self.connection = None
        self.async_connection = None
        
        # Definizione delle soglie di allerta
        self.thresholds = {
            "memory_percent": config.get("memory_percent_threshold", 80),  # % della memoria massima
            "latency_ms": config.get("latency_ms_threshold", 100),  # ms
            "evicted_keys": config.get("evicted_keys_threshold", 1000),  # numero di chiavi espulse
            "expired_keys": config.get("expired_keys_threshold", 5000),  # numero di chiavi scadute
            "cpu_percent": config.get("cpu_percent_threshold", 70),  # % della CPU
            "connected_clients": config.get("connected_clients_threshold", 5000),  # numero di client connessi
            "blocked_clients": config.get("blocked_clients_threshold", 50),  # numero di client bloccati
            "fragmentation_ratio": config.get("fragmentation_ratio_threshold", 1.5),  # rapporto di frammentazione
        }
        
        # Storia dei dati raccolti
        self.history = {
            "timestamps": [],
            "memory_usage": [],
            "latency": [],
            "evicted_keys": [],
            "expired_keys": [],
            "connected_clients": [],
            "blocked_clients": [],
            "cpu_usage": [],
            "fragmentation_ratio": [],
        }
        
        # Flag per indicare se ci sono avvisi attivi
        self.active_alerts = {}
        
        # Metriche attuali
        self.current_metrics = {}
        
        # Directory per i report
        self.report_dir = config.get("report_dir", os.path.join("logs", "redis_reports"))
        os.makedirs(self.report_dir, exist_ok=True)
        
        # Directory per i grafici
        self.graphs_dir = os.path.join(self.report_dir, "graphs")
        os.makedirs(self.graphs_dir, exist_ok=True)
        
        logger.info(f"RedisMonitor inizializzato con connessione a {self.redis_url}")
    
    async def connect(self) -> bool:
        """
        Stabilisce connessione con Redis
        
        Returns:
            bool: True se la connessione è riuscita, False altrimenti
        """
        try:
            # Connessione sincrona
            self.connection = redis.from_url(self.redis_url)
            self.connection.ping()  # Verifica la connessione
            
            # Connessione asincrona
            self.async_connection = await aioredis.from_url(self.redis_url)
            await self.async_connection.ping()  # Verifica la connessione
            
            logger.info("Connessione a Redis stabilita con successo")
            return True
        except Exception as e:
            logger.error(f"Errore nella connessione a Redis: {e}")
            return False
    
    async def disconnect(self):
        """Chiude la connessione a Redis"""
        try:
            if self.async_connection:
                await self.async_connection.close()
            if self.connection:
                self.connection.close()
            
            logger.info("Connessione a Redis chiusa")
        except Exception as e:
            logger.error(f"Errore nella chiusura della connessione a Redis: {e}")
    
    async def start_monitoring(self, interval: int = 60):
        """
        Avvia il monitoraggio continuo di Redis
        
        Args:
            interval: Intervallo in secondi tra le verifiche
        """
        if not await self.connect():
            logger.error("Impossibile avviare il monitoraggio: connessione Redis fallita")
            return
        
        logger.info(f"Avvio monitoraggio Redis con intervallo di {interval} secondi")
        
        try:
            while True:
                # Esegui controlli
                await self.check_all_metrics()
                
                # Verifica soglie di allerta
                await self.check_alert_thresholds()
                
                # Aggiorna la storia
                self._update_history()
                
                # Genera report periodico
                if len(self.history["timestamps"]) % 60 == 0:  # ogni 60 controlli
                    await self.generate_report()
                
                # Attendi l'intervallo
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info("Monitoraggio Redis interrotto")
        except Exception as e:
            logger.error(f"Errore nel monitoraggio Redis: {e}")
        finally:
            await self.disconnect()
    
    async def check_all_metrics(self):
        """Esegue tutti i controlli sulle metriche Redis"""
        try:
            # Ottiene le informazioni di base
            info = await self.async_connection.info()
            
            # Memoria utilizzata
            memory_info = await self.check_memory_usage()
            
            # Latenza
            latency = await self.measure_latency()
            
            # Chiavi scadute ed espulse
            self.current_metrics["expired_keys"] = info.get("expired_keys", 0)
            self.current_metrics["evicted_keys"] = info.get("evicted_keys", 0)
            
            # Controllo dell'utilizzo della CPU
            server_info = info.get("server", {})
            self.current_metrics["cpu_usage"] = float(info.get("used_cpu_sys", 0))
            
            # Controllo dei client
            clients_info = info.get("clients", {})
            self.current_metrics["connected_clients"] = info.get("connected_clients", 0)
            self.current_metrics["blocked_clients"] = info.get("blocked_clients", 0)
            
            # Frammentazione della memoria
            self.current_metrics["fragmentation_ratio"] = float(info.get("mem_fragmentation_ratio", 1.0))
            
            # Registra i dati attuali
            log_message = f"Redis metrics - Memory: {memory_info['used_memory_human']}, "
            log_message += f"Latency: {latency:.2f}ms, "
            log_message += f"Expired keys: {self.current_metrics['expired_keys']}, "
            log_message += f"Evicted keys: {self.current_metrics['evicted_keys']}, "
            log_message += f"Connected clients: {self.current_metrics['connected_clients']}, "
            log_message += f"Blocked clients: {self.current_metrics['blocked_clients']}, "
            log_message += f"CPU usage: {self.current_metrics['cpu_usage']}, "
            log_message += f"Fragmentation ratio: {self.current_metrics['fragmentation_ratio']}"
            
            logger.info(log_message)
            
            return self.current_metrics
        except Exception as e:
            logger.error(f"Errore nel controllo delle metriche Redis: {e}")
            return {}
    
    async def check_memory_usage(self) -> Dict[str, Any]:
        """
        Verifica l'utilizzo della memoria di Redis
        
        Returns:
            Dict[str, Any]: Informazioni sull'utilizzo della memoria
        """
        try:
            # Ottenere informazioni sulla memoria
            memory_info = await self.async_connection.info("memory")
            
            # Estrai le informazioni rilevanti
            used_memory = memory_info.get("used_memory", 0)
            used_memory_human = memory_info.get("used_memory_human", "0B")
            used_memory_peak = memory_info.get("used_memory_peak", 0)
            used_memory_peak_human = memory_info.get("used_memory_peak_human", "0B")
            used_memory_rss = memory_info.get("used_memory_rss", 0)
            used_memory_rss_human = memory_info.get("used_memory_rss_human", "0B")
            mem_fragmentation_ratio = memory_info.get("mem_fragmentation_ratio", 1.0)
            
            # Calcola la percentuale di memoria utilizzata rispetto al picco
            if used_memory_peak > 0:
                memory_percent = (used_memory / used_memory_peak) * 100
            else:
                memory_percent = 0
            
            # Aggiorna le metriche correnti
            self.current_metrics["memory_usage"] = used_memory
            self.current_metrics["memory_percent"] = memory_percent
            
            return {
                "used_memory": used_memory,
                "used_memory_human": used_memory_human,
                "used_memory_peak": used_memory_peak,
                "used_memory_peak_human": used_memory_peak_human,
                "used_memory_rss": used_memory_rss,
                "used_memory_rss_human": used_memory_rss_human,
                "mem_fragmentation_ratio": mem_fragmentation_ratio,
                "memory_percent": memory_percent
            }
        except Exception as e:
            logger.error(f"Errore nel controllo della memoria Redis: {e}")
            self.current_metrics["memory_usage"] = 0
            self.current_metrics["memory_percent"] = 0
            return {
                "used_memory": 0,
                "used_memory_human": "0B",
                "used_memory_peak": 0,
                "used_memory_peak_human": "0B",
                "used_memory_rss": 0,
                "used_memory_rss_human": "0B",
                "mem_fragmentation_ratio": 1.0,
                "memory_percent": 0
            }
    
    async def measure_latency(self, samples: int = 5) -> float:
        """
        Misura la latenza di Redis
        
        Args:
            samples: Numero di campioni per la misurazione
            
        Returns:
            float: Latenza media in millisecondi
        """
        try:
            latencies = []
            
            for _ in range(samples):
                start_time = time.time()
                await self.async_connection.ping()
                end_time = time.time()
                
                latency_ms = (end_time - start_time) * 1000
                latencies.append(latency_ms)
            
            # Calcola la latenza media
            avg_latency = statistics.mean(latencies)
            self.current_metrics["latency"] = avg_latency
            
            return avg_latency
        except Exception as e:
            logger.error(f"Errore nella misurazione della latenza Redis: {e}")
            self.current_metrics["latency"] = 0
            return 0
    
    async def get_keyspace_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Ottiene informazioni sullo spazio delle chiavi
        
        Returns:
            Dict[str, Dict[str, Any]]: Informazioni sui database Redis
        """
        try:
            keyspace_info = await self.async_connection.info("keyspace")
            return keyspace_info
        except Exception as e:
            logger.error(f"Errore nell'ottenere informazioni sullo spazio delle chiavi: {e}")
            return {}
    
    async def count_keys_by_type(self) -> Dict[str, int]:
        """
        Conta le chiavi per tipo
        
        Returns:
            Dict[str, int]: Conteggio delle chiavi per tipo
        """
        try:
            # Ottiene tutte le chiavi (attenzione: può essere costoso per database grandi)
            keys = await self.async_connection.keys("*")
            
            # Conta per tipo
            type_counts = {
                "string": 0,
                "list": 0,
                "hash": 0,
                "set": 0,
                "zset": 0,
                "stream": 0,
                "other": 0
            }
            
            for key in keys:
                key_type = await self.async_connection.type(key)
                if key_type in type_counts:
                    type_counts[key_type] += 1
                else:
                    type_counts["other"] += 1
            
            return type_counts
        except Exception as e:
            logger.error(f"Errore nel conteggio delle chiavi per tipo: {e}")
            return {}
    
    async def check_slow_commands(self) -> List[Dict[str, Any]]:
        """
        Verifica i comandi lenti
        
        Returns:
            List[Dict[str, Any]]: Lista dei comandi lenti
        """
        try:
            # Redis deve essere configurato con slowlog-log-slower-than
            # Otteniamo gli ultimi 10 comandi lenti
            slowlogs = await self.async_connection.slowlog_get(10)
            
            return [
                {
                    "id": log[0],
                    "timestamp": datetime.fromtimestamp(log[1]),
                    "duration_us": log[2],  # microsecondi
                    "command": " ".join([arg.decode('utf-8', errors='replace') for arg in log[3]]),
                    "client_ip": log[4].decode('utf-8', errors='replace') if len(log) > 4 else "",
                    "client_name": log[5].decode('utf-8', errors='replace') if len(log) > 5 else ""
                }
                for log in slowlogs
            ]
        except Exception as e:
            logger.error(f"Errore nell'ottenere i comandi lenti: {e}")
            return []
    
    async def optimize_memory(self) -> Dict[str, Any]:
        """
        Ottimizza l'utilizzo della memoria di Redis
        
        Returns:
            Dict[str, Any]: Risultato dell'ottimizzazione
        """
        try:
            # Verifica la configurazione attuale
            config = {}
            for item in await self.async_connection.config_get("*maxmemory*"):
                config[item[0].decode('utf-8')] = item[1].decode('utf-8')
            
            # Se maxmemory non è impostato, suggerisce un'impostazione
            if "maxmemory" not in config or config["maxmemory"] == "0":
                # Ottieni la memoria totale del sistema
                total_memory = psutil.virtual_memory().total
                
                # Suggerisce il 75% della memoria totale del sistema
                suggested_maxmemory = int(total_memory * 0.75)
                logger.warning(f"maxmemory non impostato. Suggerito: {suggested_maxmemory} bytes")
            
            # Verifica la policy di espulsione
            if "maxmemory-policy" not in config or config["maxmemory-policy"] == "noeviction":
                logger.warning(f"maxmemory-policy è impostato su '{config.get('maxmemory-policy', 'noeviction')}'. "
                            "Considera di impostare 'allkeys-lru' o 'volatile-lru'")
            
            # Suggerimenti
            suggestions = []
            
            # Verifica se è impostato un limite di memoria
            if "maxmemory" not in config or config["maxmemory"] == "0":
                suggestions.append("Imposta un limite di memoria con CONFIG SET maxmemory <bytes>")
            
            # Verifica la policy di espulsione
            if "maxmemory-policy" not in config or config["maxmemory-policy"] == "noeviction":
                suggestions.append("Imposta una policy di espulsione con CONFIG SET maxmemory-policy <policy>")
            
            return {
                "current_config": config,
                "suggestions": suggestions
            }
        except Exception as e:
            logger.error(f"Errore nell'ottimizzazione della memoria: {e}")
            return {
                "current_config": {},
                "suggestions": ["Errore durante l'ottimizzazione della memoria"]
            }
    
    async def check_alert_thresholds(self):
        """Verifica le soglie di allerta per le metriche"""
        try:
            alerts = []
            
            # Verifica le soglie per ogni metrica
            for metric, threshold in self.thresholds.items():
                if metric in self.current_metrics and self.current_metrics[metric] > threshold:
                    # Se la metrica supera la soglia, genera un avviso
                    alert_message = f"AVVISO: {metric} ({self.current_metrics[metric]}) supera la soglia ({threshold})"
                    logger.warning(alert_message)
                    alerts.append(alert_message)
                    
                    # Registra l'avviso attivo
                    if metric not in self.active_alerts:
                        self.active_alerts[metric] = {
                            "first_triggered": datetime.now(),
                            "count": 1,
                            "current_value": self.current_metrics[metric],
                            "threshold": threshold
                        }
                        
                        # Invia notifica (implementazione da personalizzare)
                        await self._send_alert_notification(metric, self.current_metrics[metric], threshold)
                    else:
                        # Aggiorna l'avviso esistente
                        self.active_alerts[metric]["count"] += 1
                        self.active_alerts[metric]["current_value"] = self.current_metrics[metric]
                        
                        # Invia notifica di aggiornamento se il conteggio è un multiplo di 5
                        if self.active_alerts[metric]["count"] % 5 == 0:
                            await self._send_alert_notification(
                                metric, 
                                self.current_metrics[metric], 
                                threshold,
                                is_update=True,
                                trigger_count=self.active_alerts[metric]["count"]
                            )
                else:
                    # Se la metrica rientra nella soglia, rimuovi l'avviso attivo
                    if metric in self.active_alerts:
                        # Invia notifica di risoluzione
                        await self._send_alert_notification(
                            metric,
                            self.current_metrics.get(metric, 0),
                            threshold,
                            is_resolved=True
                        )
                        
                        # Rimuovi l'avviso attivo
                        del self.active_alerts[metric]
            
            return alerts
        except Exception as e:
            logger.error(f"Errore nella verifica delle soglie di allerta: {e}")
            return []
    
    async def _send_alert_notification(self, metric: str, current_value: float, threshold: float, 
                                      is_update: bool = False, trigger_count: int = 1,
                                      is_resolved: bool = False):
        """
        Invia una notifica di allerta
        
        Args:
            metric: Nome della metrica
            current_value: Valore attuale
            threshold: Soglia configurata
            is_update: Se è un aggiornamento di un avviso esistente
            trigger_count: Numero di volte in cui l'avviso è stato attivato
            is_resolved: Se l'avviso è stato risolto
        """
        try:
            # Formato della notifica
            if is_resolved:
                subject = f"[RISOLTO] Avviso Redis: {metric}"
                message = f"L'avviso per {metric} è stato risolto.\n"
                message += f"Valore attuale: {current_value}\n"
                message += f"Soglia: {threshold}\n"
                message += f"Timestamp: {datetime.now().isoformat()}\n"
                
                logger.info(f"Avviso risolto per {metric}")
            elif is_update:
                subject = f"[AGGIORNAMENTO] Avviso Redis: {metric}"
                message = f"L'avviso per {metric} è ancora attivo ({trigger_count} volte).\n"
                message += f"Valore attuale: {current_value}\n"
                message += f"Soglia: {threshold}\n"
                message += f"Timestamp: {datetime.now().isoformat()}\n"
                
                logger.warning(f"Avviso aggiornato per {metric} ({trigger_count} volte)")
            else:
                subject = f"[NUOVO] Avviso Redis: {metric}"
                message = f"È stato rilevato un nuovo avviso per {metric}.\n"
                message += f"Valore attuale: {current_value}\n"
                message += f"Soglia: {threshold}\n"
                message += f"Timestamp: {datetime.now().isoformat()}\n"
                
                logger.warning(f"Nuovo avviso per {metric}")
            
            # Implementazione delle notifiche
            # 1. Log
            with open(os.path.join("logs", "redis_alerts.log"), "a") as f:
                f.write(f"{datetime.now().isoformat()} - {subject}: {message}\n")
            
            # 2. Implementazione notifiche via email o Telegram
            # TODO: Implementare in base alle configurazioni
            
            # 3. Salva lo stato
            self._save_alert_state()
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica di allerta: {e}")
    
    def _save_alert_state(self):
        """Salva lo stato degli avvisi attivi su file"""
        try:
            # Crea una copia degli avvisi con datetime convertiti in string
            saveable_alerts = {}
            for metric, alert in self.active_alerts.items():
                saveable_alerts[metric] = alert.copy()
                saveable_alerts[metric]["first_triggered"] = alert["first_triggered"].isoformat()
            
            # Salva su file
            alert_file = os.path.join("logs", "redis_active_alerts.json")
            with open(alert_file, "w") as f:
                json.dump(saveable_alerts, f, indent=2)
        except Exception as e:
            logger.error(f"Errore nel salvataggio dello stato degli avvisi: {e}")
    
    def _load_alert_state(self):
        """Carica lo stato degli avvisi attivi da file"""
        try:
            alert_file = os.path.join("logs", "redis_active_alerts.json")
            if os.path.exists(alert_file):
                with open(alert_file, "r") as f:
                    saved_alerts = json.load(f)
                
                # Converte le date string in datetime
                for metric, alert in saved_alerts.items():
                    alert["first_triggered"] = datetime.fromisoformat(alert["first_triggered"])
                    self.active_alerts[metric] = alert
                
                logger.info(f"Caricati {len(self.active_alerts)} avvisi attivi")
        except Exception as e:
            logger.error(f"Errore nel caricamento dello stato degli avvisi: {e}")
    
    def _update_history(self):
        """Aggiorna la storia delle metriche"""
        try:
            # Aggiunge il timestamp
            self.history["timestamps"].append(datetime.now())
            
            # Aggiunge le metriche
            for metric in ["memory_usage", "latency", "expired_keys", "evicted_keys",
                          "connected_clients", "blocked_clients", "cpu_usage", "fragmentation_ratio"]:
                self.history[metric].append(self.current_metrics.get(metric, 0))
            
            # Limita la lunghezza della storia (mantiene 24 ore con check ogni minuto)
            max_history = 24 * 60
            if len(self.history["timestamps"]) > max_history:
                self.history["timestamps"] = self.history["timestamps"][-max_history:]
                for metric in self.history.keys():
                    if metric != "timestamps" and len(self.history[metric]) > max_history:
                        self.history[metric] = self.history[metric][-max_history:]
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento della storia: {e}")
    
    async def generate_report(self):
        """Genera un report dello stato di Redis"""
        try:
            # Crea il nome del file con data e ora
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = os.path.join(self.report_dir, f"redis_report_{timestamp}.json")
            
            # Ottiene informazioni aggiuntive
            slow_commands = await self.check_slow_commands()
            keyspace = await self.get_keyspace_info()
            memory_optimization = await self.optimize_memory()
            
            # Prepara il report
            report = {
                "timestamp": datetime.now().isoformat(),
                "metrics": self.current_metrics,
                "active_alerts": {k: {"count": v["count"], "value": v["current_value"]} 
                                  for k, v in self.active_alerts.items()},
                "slow_commands": slow_commands,
                "keyspace": {k: v for k, v in keyspace.items()},
                "memory_optimization": memory_optimization["suggestions"]
            }
            
            # Salva il report
            with open(report_file, "w") as f:
                json.dump(report, f, indent=2)
            
            logger.info(f"Report generato: {report_file}")
            
            # Genera grafici
            await self._generate_graphs(timestamp)
            
            return report_file
        except Exception as e:
            logger.error(f"Errore nella generazione del report: {e}")
            return None
    
    async def _generate_graphs(self, timestamp: str):
        """
        Genera grafici delle metriche
        
        Args:
            timestamp: Timestamp per il nome del file
        """
        try:
            # Verifica che ci siano abbastanza dati
            if len(self.history["timestamps"]) < 2:
                logger.warning("Dati insufficienti per generare grafici")
                return
            
            # Crea le date per l'asse x
            dates = self.history["timestamps"]
            x = range(len(dates))
            
            # Crea un grafico per le metriche principali
            plt.figure(figsize=(12, 8))
            
            # 1. Memoria
            plt.subplot(3, 2, 1)
            memory_mb = [m / (1024 * 1024) for m in self.history["memory_usage"]]
            plt.plot(x, memory_mb)
            plt.title("Memoria utilizzata (MB)")
            plt.grid(True)
            
            # 2. Latenza
            plt.subplot(3, 2, 2)
            plt.plot(x, self.history["latency"])
            plt.title("Latenza (ms)")
            plt.grid(True)
            
            # 3. Chiavi scadute
            plt.subplot(3, 2, 3)
            plt.plot(x, self.history["expired_keys"])
            plt.title("Chiavi scadute")
            plt.grid(True)
            
            # 4. Chiavi espulse
            plt.subplot(3, 2, 4)
            plt.plot(x, self.history["evicted_keys"])
            plt.title("Chiavi espulse")
            plt.grid(True)
            
            # 5. Client connessi
            plt.subplot(3, 2, 5)
            plt.plot(x, self.history["connected_clients"])
            plt.title("Client connessi")
            plt.grid(True)
            
            # 6. CPU
            plt.subplot(3, 2, 6)
            plt.plot(x, self.history["cpu_usage"])
            plt.title("Utilizzo CPU")
            plt.grid(True)
            
            plt.tight_layout()
            
            # Salva il grafico
            graph_file = os.path.join(self.graphs_dir, f"redis_metrics_{timestamp}.png")
            plt.savefig(graph_file)
            plt.close()
            
            logger.info(f"Grafico generato: {graph_file}")
        except Exception as e:
            logger.error(f"Errore nella generazione dei grafici: {e}")

async def main():
    """Funzione principale"""
    parser = argparse.ArgumentParser(description="Redis Monitor - Monitor avanzato per Redis")
    parser.add_argument("--url", default="redis://localhost:6379/0", help="URL di connessione Redis")
    parser.add_argument("--interval", type=int, default=60, help="Intervallo di controllo in secondi")
    parser.add_argument("--memory-threshold", type=int, default=80, help="Soglia di utilizzo memoria (%)")
    parser.add_argument("--latency-threshold", type=int, default=100, help="Soglia di latenza (ms)")
    parser.add_argument("--report-dir", default="logs/redis_reports", help="Directory per i report")
    
    args = parser.parse_args()
    
    # Configurazione
    config = {
        "redis_url": args.url,
        "memory_percent_threshold": args.memory_threshold,
        "latency_ms_threshold": args.latency_threshold,
        "report_dir": args.report_dir
    }
    
    # Crea le directory
    os.makedirs("logs", exist_ok=True)
    os.makedirs(args.report_dir, exist_ok=True)
    
    # Crea il monitor
    monitor = RedisMonitor(config)
    
    try:
        # Avvia il monitoraggio
        await monitor.start_monitoring(args.interval)
    except KeyboardInterrupt:
        # Gestisce l'interruzione da tastiera
        logger.info("Monitoraggio interrotto dall'utente")
    finally:
        # Chiude la connessione
        await monitor.disconnect()

if __name__ == "__main__":
    asyncio.run(main()) 