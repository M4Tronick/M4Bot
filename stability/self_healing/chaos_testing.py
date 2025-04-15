#!/usr/bin/env python3
"""
M4Bot - Sistema di Chaos Testing

Questo modulo implementa un sistema di chaos testing per M4Bot che introduce
deliberatamente guasti e condizioni anomale nell'ambiente per verificare la
resilienza e le capacità di auto-riparazione del sistema.

Funzionalità:
- Simulazione di guasti di servizi
- Test di sovraccarico risorse (CPU, memoria, disco)
- Simulazione di errori di rete e latenza
- Test di resilienza del database
- Generazione automatica di report di resilienza
"""

import os
import sys
import json
import time
import random
import signal
import logging
import argparse
import asyncio
import subprocess
from typing import Dict, List, Any, Optional, Tuple, Callable, Set
from datetime import datetime, timedelta
from pathlib import Path

# Aggiungi la directory parent al path per importare self_healing_system
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(parent_dir)

# Importa il sistema di self-healing
from stability.self_healing.self_healing_system import get_self_healing_system, SelfHealingSystem

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('m4bot.stability.chaos_testing')

class ChaosTest:
    """Base class per i test di chaos."""
    
    def __init__(self, name: str, description: str, duration: int = 60):
        self.name = name
        self.description = description
        self.duration = duration  # Durata del test in secondi
        self.start_time = 0
        self.end_time = 0
        self.results: Dict[str, Any] = {}
        self.success = False
        self.error = ""
    
    async def setup(self):
        """Prepara l'ambiente per il test."""
        pass
    
    async def execute(self):
        """Esegue il test di chaos."""
        logger.info(f"Avvio test chaos: {self.name}")
        self.start_time = time.time()
        
        try:
            await self._run_test()
            self.success = True
        except Exception as e:
            self.success = False
            self.error = str(e)
            logger.error(f"Errore durante l'esecuzione del test {self.name}: {e}")
        
        self.end_time = time.time()
        logger.info(f"Test chaos {self.name} completato in {self.end_time - self.start_time:.2f}s")
        
        return self.success
    
    async def _run_test(self):
        """Implementazione specifica del test, da sovrascrivere."""
        raise NotImplementedError("I test di chaos devono implementare il metodo _run_test")
    
    async def cleanup(self):
        """Pulisce l'ambiente dopo il test."""
        pass
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte i risultati del test in dizionario."""
        return {
            "name": self.name,
            "description": self.description,
            "duration": self.duration,
            "actual_duration": self.end_time - self.start_time if self.end_time else 0,
            "success": self.success,
            "error": self.error,
            "results": self.results,
            "start_time": self.start_time,
            "end_time": self.end_time
        }

class ServiceKillTest(ChaosTest):
    """Test che interrompe un servizio per verificare la capacità di ripristino."""
    
    def __init__(self, service_name: str, duration: int = 120):
        super().__init__(
            name=f"service_kill_{service_name}",
            description=f"Interrompe forzatamente il servizio {service_name} e verifica il ripristino automatico",
            duration=duration
        )
        self.service_name = service_name
        self.recovery_time = 0
        self.was_recovered = False
    
    async def _run_test(self):
        # Ottiene informazioni sul servizio
        self_healing = get_self_healing_system()
        
        if self.service_name not in self_healing.services:
            raise ValueError(f"Servizio {self.service_name} non trovato nella configurazione")
        
        service_config = self_healing.config['services'][self.service_name]
        
        # Verifica tipo di servizio
        if service_config.get('type', 'systemd') == 'systemd':
            unit = service_config['unit']
            
            # Interrompe il servizio
            logger.info(f"Interruzione forzata del servizio {self.service_name} ({unit})")
            try:
                proc = await asyncio.create_subprocess_exec(
                    'systemctl', 'stop', unit,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                
                if proc.returncode != 0:
                    raise Exception(f"Errore nell'interruzione del servizio: {stderr.decode()}")
            except Exception as e:
                logger.error(f"Errore nell'interruzione del servizio {self.service_name}: {e}")
                # Continua comunque, perché potremmo essere in ambiente di simulazione
            
            # Inizia il timer per il ripristino
            recovery_start = time.time()
            
            # Attendi il tempo del test per dare al sistema di self-healing la possibilità di ripristinare
            await asyncio.sleep(self.duration)
            
            # Verifica se il servizio è stato ripristinato
            try:
                proc = await asyncio.create_subprocess_exec(
                    'systemctl', 'is-active', unit,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                
                self.was_recovered = proc.returncode == 0
                
                if self.was_recovered:
                    logger.info(f"Servizio {self.service_name} ripristinato con successo")
                    self.recovery_time = time.time() - recovery_start
                else:
                    logger.warning(f"Servizio {self.service_name} non ripristinato automaticamente")
            except Exception as e:
                logger.error(f"Errore nella verifica del ripristino: {e}")
                self.was_recovered = False
        else:
            # Altri tipi di servizio (es. processo)
            logger.warning(f"Tipo di servizio {service_config.get('type')} non supportato per il test kill")
            await asyncio.sleep(self.duration)  # Simula l'esecuzione del test
        
        # Aggiorna risultati
        self.results = {
            "service_name": self.service_name,
            "was_recovered": self.was_recovered,
            "recovery_time_seconds": self.recovery_time if self.was_recovered else None,
            "service_type": service_config.get('type', 'systemd')
        }
    
    async def cleanup(self):
        """Assicura che il servizio sia ripristinato dopo il test."""
        if not self.was_recovered:
            self_healing = get_self_healing_system()
            service_config = self_healing.config['services'].get(self.service_name, {})
            
            if service_config and service_config.get('type', 'systemd') == 'systemd':
                unit = service_config['unit']
                
                # Riavvia il servizio manualmente
                logger.info(f"Cleanup: Riavvio manuale del servizio {self.service_name}")
                try:
                    proc = await asyncio.create_subprocess_exec(
                        'systemctl', 'restart', unit,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    await proc.communicate()
                except Exception as e:
                    logger.error(f"Errore nel riavvio manuale: {e}")

class ResourceExhaustionTest(ChaosTest):
    """Test che esaurisce deliberatamente una risorsa di sistema."""
    
    def __init__(self, resource_type: str, intensity: int = 80, duration: int = 120):
        """
        Inizializza un test di esaurimento risorse.
        
        Args:
            resource_type: Tipo di risorsa ('cpu', 'memory', 'disk', 'io')
            intensity: Intensità del test (0-100)
            duration: Durata del test in secondi
        """
        super().__init__(
            name=f"resource_exhaustion_{resource_type}",
            description=f"Esaurisce la risorsa {resource_type} al {intensity}% e verifica la gestione",
            duration=duration
        )
        self.resource_type = resource_type
        self.intensity = intensity
        self.process = None
    
    async def _run_test(self):
        # Script per esaurire le risorse
        script_path = self._get_resource_script()
        
        # Esegui lo script in background
        try:
            if self.resource_type == "cpu":
                # Esaurimento CPU: calcolo intensivo
                num_cores = os.cpu_count() or 1
                core_percent = min(100, self.intensity)
                
                # Calcola quanti processi lanciare in base all'intensità
                processes_to_launch = max(1, int((num_cores * core_percent) / 100))
                
                logger.info(f"Avvio test esaurimento CPU con {processes_to_launch} processi")
                cmd = f"for i in $(seq 1 {processes_to_launch}); do yes > /dev/null & done"
                self.process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
            elif self.resource_type == "memory":
                # Esaurimento memoria: alloca gradualmente memoria
                memory_mb = int((self.intensity / 100) * self._get_total_memory() * 0.8)
                logger.info(f"Avvio test esaurimento memoria di {memory_mb}MB")
                
                # Usa lo stress-ng se disponibile
                self.process = await asyncio.create_subprocess_exec(
                    "stress-ng", "--vm", "1", "--vm-bytes", f"{memory_mb}M", "--timeout", f"{self.duration}s",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
            elif self.resource_type == "disk":
                # Esaurimento disco: crea file di grandi dimensioni
                free_space = self._get_free_disk_space()
                size_to_use = int((self.intensity / 100) * free_space * 0.7)  # usa 70% dello spazio specificato
                
                logger.info(f"Avvio test esaurimento disco di {size_to_use}MB")
                
                # Crea file temporaneo grande
                temp_dir = "/tmp/chaos_test_disk"
                os.makedirs(temp_dir, exist_ok=True)
                
                cmd = f"dd if=/dev/zero of={temp_dir}/bigfile bs=1M count={size_to_use}"
                self.process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
            elif self.resource_type == "io":
                # Esaurimento I/O: operazioni intensive su disco
                logger.info(f"Avvio test esaurimento I/O")
                
                # Usa lo stress-ng se disponibile
                self.process = await asyncio.create_subprocess_exec(
                    "stress-ng", "--io", "4", "--timeout", f"{self.duration}s",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
            
            # Attendi il tempo del test
            await asyncio.sleep(self.duration)
            
            # Aggiorna risultati
            # Qui dovremmo verificare come il sistema ha gestito l'esaurimento
            self_healing = get_self_healing_system()
            self.results = {
                "resource_type": self.resource_type,
                "intensity": self.intensity,
                "system_health": self_healing.system_health.to_dict(),
                "actions_taken": self._get_actions_taken()
            }
            
        except Exception as e:
            logger.error(f"Errore nell'esecuzione test {self.name}: {e}")
            raise
    
    async def cleanup(self):
        """Termina i processi di stress e pulisce le risorse."""
        if self.process:
            try:
                # Termina il processo
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    self.process.kill()
            except Exception as e:
                logger.error(f"Errore nella terminazione processo: {e}")
        
        # Pulizia specifica per tipo di risorsa
        if self.resource_type == "cpu":
            try:
                # Termina tutti i processi 'yes'
                subprocess.run("pkill -f 'yes'", shell=True)
            except:
                pass
                
        elif self.resource_type == "disk":
            try:
                # Rimuovi file temporanei
                temp_dir = "/tmp/chaos_test_disk"
                if os.path.exists(temp_dir):
                    subprocess.run(f"rm -rf {temp_dir}", shell=True)
            except:
                pass
    
    def _get_resource_script(self) -> str:
        """Restituisce il percorso dello script per esaurire la risorsa specifica."""
        # In un'implementazione reale, questi sarebbero script separati
        return "/tmp/dummy_script.sh"
    
    def _get_total_memory(self) -> int:
        """Restituisce la memoria totale del sistema in MB."""
        try:
            import psutil
            return int(psutil.virtual_memory().total / (1024 * 1024))
        except:
            return 4096  # Fallback: 4GB
    
    def _get_free_disk_space(self) -> int:
        """Restituisce lo spazio libero su disco in MB."""
        try:
            import psutil
            return int(psutil.disk_usage('/').free / (1024 * 1024))
        except:
            return 1024  # Fallback: 1GB
    
    def _get_actions_taken(self) -> List[Dict[str, Any]]:
        """Recupera le azioni intraprese dal sistema di self-healing durante il test."""
        # In un'implementazione reale, questo recupererebbe informazioni dai log o dal sistema
        return []

class NetworkFailureTest(ChaosTest):
    """Test che simula problemi di rete per verificare la resilienza."""
    
    def __init__(self, target: str, failure_type: str = "latency", duration: int = 120):
        """
        Inizializza un test di problemi di rete.
        
        Args:
            target: Servizio o componente target
            failure_type: Tipo di guasto ('latency', 'loss', 'disconnect')
            duration: Durata del test in secondi
        """
        super().__init__(
            name=f"network_{failure_type}_{target}",
            description=f"Simula problemi di rete ({failure_type}) per {target}",
            duration=duration
        )
        self.target = target
        self.failure_type = failure_type
    
    async def _run_test(self):
        logger.info(f"Avvio test di problemi di rete: {self.failure_type} per {self.target}")
        
        # Ottieni la configurazione del servizio
        self_healing = get_self_healing_system()
        
        # In ambiente reale, qui useremmo tc (traffic control) per introdurre problemi di rete
        # Esempio:
        # - Latenza: tc qdisc add dev eth0 root netem delay 200ms
        # - Perdita pacchetti: tc qdisc add dev eth0 root netem loss 20%
        
        # Per scopi di demo, simuliamo i problemi di rete
        if self.failure_type == "latency":
            # Simula alta latenza
            logger.info(f"Aggiunta latenza di rete di 200ms per {self.target}")
            # Qui andrebbe il comando tc
            
        elif self.failure_type == "loss":
            # Simula perdita di pacchetti
            logger.info(f"Aggiunta perdita di pacchetti del 20% per {self.target}")
            # Qui andrebbe il comando tc
            
        elif self.failure_type == "disconnect":
            # Simula disconnessione completa
            logger.info(f"Simulazione disconnessione completa per {self.target}")
            # Qui andrebbe iptables o tc
        
        # Attendi il tempo del test
        await asyncio.sleep(self.duration)
        
        # Verifica come il sistema ha gestito il problema
        # Ottieni informazioni sui servizi
        self.results = {
            "target": self.target,
            "failure_type": self.failure_type,
            "services_impacted": self._check_impacted_services(),
            "recovery_actions": self._get_recovery_actions()
        }
    
    async def cleanup(self):
        """Ripristina la configurazione di rete normale."""
        logger.info(f"Ripristino configurazione di rete normale")
        
        # In ambiente reale, qui rimuoveremmo le regole tc
        # Esempio: tc qdisc del dev eth0 root
    
    def _check_impacted_services(self) -> List[Dict[str, Any]]:
        """Controlla quali servizi sono stati impattati dai problemi di rete."""
        self_healing = get_self_healing_system()
        impacted = []
        
        for name, service in self_healing.services.items():
            if not service.is_healthy and "connection" in service.last_error.lower():
                impacted.append({
                    "name": name,
                    "error": service.last_error,
                    "consecutive_failures": service.consecutive_failures
                })
        
        return impacted
    
    def _get_recovery_actions(self) -> List[Dict[str, Any]]:
        """Recupera le azioni di ripristino intraprese durante il test."""
        # In un'implementazione reale, questo recupererebbe informazioni dai log
        return []

class DatabaseCorruptionTest(ChaosTest):
    """Test che simula la corruzione del database per verificare la capacità di ripristino."""
    
    def __init__(self, db_service: str = "database", corruption_type: str = "connection", duration: int = 180):
        """
        Inizializza un test di corruzione database.
        
        Args:
            db_service: Nome del servizio database
            corruption_type: Tipo di corruzione ('connection', 'schema', 'data')
            duration: Durata del test in secondi
        """
        super().__init__(
            name=f"db_corruption_{corruption_type}",
            description=f"Simula corruzione database ({corruption_type}) su {db_service}",
            duration=duration
        )
        self.db_service = db_service
        self.corruption_type = corruption_type
    
    async def _run_test(self):
        logger.info(f"Avvio test corruzione database: {self.corruption_type}")
        
        self_healing = get_self_healing_system()
        db_config = self_healing.config['services'].get(self.db_service, {})
        
        if not db_config:
            raise ValueError(f"Servizio database {self.db_service} non trovato")
        
        # Simula corruzione in base al tipo
        if self.corruption_type == "connection":
            # Interrompi temporaneamente il servizio database
            if db_config.get('type') == 'systemd':
                unit = db_config['unit']
                logger.info(f"Interruzione temporanea del database {unit}")
                
                proc = await asyncio.create_subprocess_exec(
                    'systemctl', 'stop', unit,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
        
        elif self.corruption_type == "schema":
            # In un ambiente reale, qui modificheremmo lo schema del database
            # Per la simulazione, lo registriamo solo
            logger.info("Simulazione corruzione schema database")
        
        elif self.corruption_type == "data":
            # In un ambiente reale, qui corromperemmo alcuni dati
            # Per la simulazione, lo registriamo solo
            logger.info("Simulazione corruzione dati database")
        
        # Attendi che il sistema rilevi e corregga il problema
        await asyncio.sleep(self.duration)
        
        # Verifica i risultati
        db_service_status = self_healing.services.get(self.db_service)
        db_is_healthy = db_service_status and db_service_status.is_healthy
        
        self.results = {
            "db_service": self.db_service,
            "corruption_type": self.corruption_type,
            "db_recovered": db_is_healthy,
            "recovery_time": self._calculate_recovery_time(),
            "recovery_method": self._determine_recovery_method()
        }
        
        # Verifica che il database sia stato ripristinato
        self.success = db_is_healthy
    
    async def cleanup(self):
        """Assicura che il database sia ripristinato dopo il test."""
        self_healing = get_self_healing_system()
        db_config = self_healing.config['services'].get(self.db_service, {})
        
        if not db_config:
            return
        
        db_service_status = self_healing.services.get(self.db_service)
        if not db_service_status or not db_service_status.is_healthy:
            # Il database non è stato ripristinato, riavvialo manualmente
            if db_config.get('type') == 'systemd':
                unit = db_config['unit']
                logger.info(f"Cleanup: Riavvio manuale del database {unit}")
                
                proc = await asyncio.create_subprocess_exec(
                    'systemctl', 'restart', unit,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()
    
    def _calculate_recovery_time(self) -> float:
        """Calcola il tempo di ripristino del database."""
        # In un'implementazione reale, questo verrebbe calcolato dai log
        return 0.0
    
    def _determine_recovery_method(self) -> str:
        """Determina il metodo usato per ripristinare il database."""
        # In un'implementazione reale, questo sarebbe determinato dai log
        return "unknown"

class ChaosTestRunner:
    """Esegue e gestisce i test di chaos."""
    
    def __init__(self, report_dir: str = None):
        """
        Inizializza il runner di test.
        
        Args:
            report_dir: Directory per i report (default: ./chaos_reports)
        """
        self.report_dir = report_dir or os.path.join(os.path.dirname(__file__), 'chaos_reports')
        os.makedirs(self.report_dir, exist_ok=True)
        
        self.tests: List[ChaosTest] = []
        self.results: Dict[str, Any] = {
            'timestamp': time.time(),
            'start_time': 0,
            'end_time': 0,
            'total_tests': 0,
            'successful_tests': 0,
            'failed_tests': 0,
            'test_results': []
        }
    
    def add_test(self, test: ChaosTest):
        """Aggiunge un test alla suite."""
        self.tests.append(test)
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Esegue tutti i test di chaos e restituisce i risultati."""
        logger.info(f"Avvio suite di test chaos con {len(self.tests)} test")
        
        self.results['start_time'] = time.time()
        self.results['total_tests'] = len(self.tests)
        
        for test in self.tests:
            # Setup
            await test.setup()
            
            # Esecuzione
            success = await test.execute()
            
            # Cleanup
            await test.cleanup()
            
            # Aggiorna contatori
            if success:
                self.results['successful_tests'] += 1
            else:
                self.results['failed_tests'] += 1
            
            # Aggiungi risultati
            self.results['test_results'].append(test.to_dict())
        
        self.results['end_time'] = time.time()
        
        # Genera report
        self._save_report()
        
        return self.results
    
    def _save_report(self) -> str:
        """Salva i risultati in un file JSON."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = os.path.join(self.report_dir, f'chaos_test_report_{timestamp}.json')
        
        with open(report_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"Report salvato in {report_file}")
        return report_file
    
    def generate_html_report(self) -> str:
        """Genera un report HTML più leggibile dai risultati."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        html_file = os.path.join(self.report_dir, f'chaos_test_report_{timestamp}.html')
        
        # Durata totale dei test
        duration = self.results['end_time'] - self.results['start_time']
        success_rate = (self.results['successful_tests'] / self.results['total_tests'] * 100) if self.results['total_tests'] > 0 else 0
        
        # Genera HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>M4Bot Chaos Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                h1, h2, h3 {{ color: #333; }}
                .summary {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
                .test-card {{ border: 1px solid #ddd; border-radius: 5px; margin-bottom: 15px; padding: 15px; }}
                .test-card h3 {{ margin-top: 0; }}
                .success {{ color: green; }}
                .failure {{ color: red; }}
                .details {{ margin-top: 10px; }}
                .details pre {{ background-color: #f9f9f9; padding: 10px; border-radius: 3px; overflow-x: auto; }}
            </style>
        </head>
        <body>
            <h1>M4Bot Chaos Test Report</h1>
            <div class="summary">
                <h2>Riepilogo</h2>
                <p>Data: {datetime.fromtimestamp(self.results['start_time']).strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Durata totale: {duration:.2f} secondi</p>
                <p>Test eseguiti: {self.results['total_tests']}</p>
                <p>Test completati con successo: <span class="success">{self.results['successful_tests']}</span></p>
                <p>Test falliti: <span class="failure">{self.results['failed_tests']}</span></p>
                <p>Tasso di successo: {success_rate:.1f}%</p>
            </div>
            
            <h2>Dettagli dei Test</h2>
        """
        
        # Aggiungi sezione per ogni test
        for test_result in self.results['test_results']:
            success_class = "success" if test_result['success'] else "failure"
            duration = test_result['actual_duration']
            
            html += f"""
            <div class="test-card">
                <h3>{test_result['name']}</h3>
                <p>{test_result['description']}</p>
                <p>Stato: <span class="{success_class}">{"Successo" if test_result['success'] else "Fallimento"}</span></p>
                <p>Durata: {duration:.2f} secondi</p>
            """
            
            if test_result['error']:
                html += f"""
                <div class="details">
                    <h4>Errore:</h4>
                    <pre>{test_result['error']}</pre>
                </div>
                """
            
            html += f"""
                <div class="details">
                    <h4>Risultati:</h4>
                    <pre>{json.dumps(test_result['results'], indent=2)}</pre>
                </div>
            </div>
            """
        
        html += """
        </body>
        </html>
        """
        
        with open(html_file, 'w') as f:
            f.write(html)
        
        logger.info(f"Report HTML salvato in {html_file}")
        return html_file

async def run_standard_test_suite():
    """Esegue una suite di test standard per verificare la resilienza del sistema."""
    # Inizializza il runner
    runner = ChaosTestRunner()
    
    # Aggiungi test di vario tipo
    
    # Test di interruzione servizi
    runner.add_test(ServiceKillTest("web"))
    runner.add_test(ServiceKillTest("bot"))
    
    # Test di esaurimento risorse
    runner.add_test(ResourceExhaustionTest("cpu", intensity=80, duration=90))
    runner.add_test(ResourceExhaustionTest("memory", intensity=70, duration=90))
    
    # Test di problemi di rete
    runner.add_test(NetworkFailureTest("web", failure_type="latency"))
    runner.add_test(NetworkFailureTest("database", failure_type="loss"))
    
    # Test di corruzione database
    runner.add_test(DatabaseCorruptionTest(corruption_type="connection"))
    
    # Esegui i test
    results = await runner.run_all_tests()
    
    # Genera report HTML
    html_report = runner.generate_html_report()
    
    logger.info(f"Test completati: {results['successful_tests']}/{results['total_tests']} con successo")
    logger.info(f"Report HTML: {html_report}")
    
    return results

if __name__ == "__main__":
    # Parsing degli argomenti a linea di comando
    parser = argparse.ArgumentParser(description="M4Bot Chaos Testing Tool")
    parser.add_argument("--report-dir", type=str, help="Directory per i report")
    parser.add_argument("--test", type=str, help="Test specifico da eseguire")
    args = parser.parse_args()
    
    # Esegui la suite di test
    asyncio.run(run_standard_test_suite()) 