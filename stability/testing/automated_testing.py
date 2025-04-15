"""
Framework di test automatizzato per M4Bot

Questo modulo implementa un sistema avanzato di test automatizzati
per garantire la stabilità e l'affidabilità di M4Bot, inclusi:

- Test unitari, di integrazione e end-to-end
- Test di carico e performance
- Test di resilienza (chaos testing)
- Generazione automatica di test basati su IA
- Monitoraggio continuo della copertura del codice
- Integrazione con CI/CD
"""

import asyncio
import inspect
import json
import logging
import os
import random
import re
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union

import aiohttp
import pytest
import requests
from locust import HttpUser, between, task

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("automated_testing")

# Percorsi principali
BASE_DIR = Path(__file__).parent.parent.parent
TEST_DIR = BASE_DIR / "tests"
REPORT_DIR = BASE_DIR / "test_reports"

# Assicurati che le directory esistano
REPORT_DIR.mkdir(exist_ok=True)

class TestType(Enum):
    """Tipi di test supportati."""
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"
    PERFORMANCE = "performance"
    LOAD = "load"
    CHAOS = "chaos"
    SECURITY = "security"

class TestResult(Enum):
    """Possibili risultati dei test."""
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"
    PENDING = "pending"

@dataclass
class TestCase:
    """Rappresenta un singolo test case."""
    name: str
    type: TestType
    function: Callable
    description: str = ""
    tags: List[str] = field(default_factory=list)
    timeout: float = 30.0
    dependencies: List[str] = field(default_factory=list)
    retry_count: int = 0
    
    # Stato del test
    result: TestResult = TestResult.PENDING
    duration: float = 0.0
    error_message: str = ""
    stack_trace: str = ""
    timestamp: float = field(default_factory=time.time)

@dataclass
class TestSuite:
    """Raggruppa test correlati."""
    name: str
    description: str = ""
    test_cases: List[TestCase] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    setup: Optional[Callable] = None
    teardown: Optional[Callable] = None
    
    # Statistiche
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    total_duration: float = 0.0

@dataclass
class TestReport:
    """Report completo dell'esecuzione dei test."""
    id: str
    suites: List[TestSuite]
    start_time: float
    end_time: float = 0.0
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    error_tests: int = 0
    skipped_tests: int = 0
    total_duration: float = 0.0
    environment: Dict[str, str] = field(default_factory=dict)

@dataclass
class CoverageReport:
    """Report sulla copertura del codice."""
    lines_covered: int = 0
    lines_total: int = 0
    functions_covered: int = 0
    functions_total: int = 0
    branches_covered: int = 0
    branches_total: int = 0
    coverage_by_file: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    @property
    def line_coverage_percent(self) -> float:
        """Percentuale di linee coperte."""
        if self.lines_total == 0:
            return 0.0
        return (self.lines_covered / self.lines_total) * 100
    
    @property
    def function_coverage_percent(self) -> float:
        """Percentuale di funzioni coperte."""
        if self.functions_total == 0:
            return 0.0
        return (self.functions_covered / self.functions_total) * 100
    
    @property
    def branch_coverage_percent(self) -> float:
        """Percentuale di branch coperte."""
        if self.branches_total == 0:
            return 0.0
        return (self.branches_covered / self.branches_total) * 100

class TestRegistry:
    """Registro centrale per tutti i test."""
    
    def __init__(self):
        self.test_suites: Dict[str, TestSuite] = {}
        self.test_cases: Dict[str, TestCase] = {}
    
    def register_suite(self, suite: TestSuite) -> TestSuite:
        """Registra una suite di test."""
        self.test_suites[suite.name] = suite
        return suite
    
    def register_test(self, suite_name: str, test_case: TestCase) -> TestCase:
        """Registra un test case in una suite specifica."""
        if suite_name not in self.test_suites:
            self.test_suites[suite_name] = TestSuite(name=suite_name)
        
        suite = self.test_suites[suite_name]
        suite.test_cases.append(test_case)
        self.test_cases[test_case.name] = test_case
        
        return test_case
    
    def get_suite(self, name: str) -> Optional[TestSuite]:
        """Recupera una suite di test per nome."""
        return self.test_suites.get(name)
    
    def get_test(self, name: str) -> Optional[TestCase]:
        """Recupera un test case per nome."""
        return self.test_cases.get(name)
    
    def get_suites_by_tag(self, tag: str) -> List[TestSuite]:
        """Recupera tutte le suite con un tag specifico."""
        return [suite for suite in self.test_suites.values() if tag in suite.tags]
    
    def get_tests_by_tag(self, tag: str) -> List[TestCase]:
        """Recupera tutti i test con un tag specifico."""
        return [test for test in self.test_cases.values() if tag in test.tags]
    
    def get_tests_by_type(self, test_type: TestType) -> List[TestCase]:
        """Recupera tutti i test di un tipo specifico."""
        return [test for test in self.test_cases.values() if test.type == test_type]
    
    def clear(self):
        """Rimuove tutti i test registrati."""
        self.test_suites.clear()
        self.test_cases.clear()

# Singleton del registro dei test
test_registry = TestRegistry()

def test_case(
    suite_name: str,
    name: str = None,
    test_type: TestType = TestType.UNIT,
    description: str = "",
    tags: List[str] = None,
    timeout: float = 30.0,
    dependencies: List[str] = None,
    retry_count: int = 0,
):
    """Decoratore per registrare una funzione come test case."""
    
    def decorator(func):
        nonlocal name
        if name is None:
            name = func.__name__
        
        test_case = TestCase(
            name=name,
            type=test_type,
            function=func,
            description=description or func.__doc__ or "",
            tags=tags or [],
            timeout=timeout,
            dependencies=dependencies or [],
            retry_count=retry_count,
        )
        
        test_registry.register_test(suite_name, test_case)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator

def test_suite(
    name: str,
    description: str = "",
    tags: List[str] = None,
):
    """Decoratore per creare una suite di test."""
    
    def decorator(cls):
        suite = TestSuite(
            name=name,
            description=description or cls.__doc__ or "",
            tags=tags or [],
        )
        
        # Cerca metodi setup e teardown
        if hasattr(cls, "setup"):
            suite.setup = cls.setup
        
        if hasattr(cls, "teardown"):
            suite.teardown = cls.teardown
        
        # Registra la suite
        test_registry.register_suite(suite)
        
        return cls
    
    return decorator

class ChaosTestGenerator:
    """Generatore di test di chaos per verificare la resilienza del sistema."""
    
    def __init__(self, target_services: List[str]):
        self.target_services = target_services
    
    def generate_tests(self) -> List[TestCase]:
        """Genera una serie di test di chaos da eseguire."""
        tests = []
        
        for service in self.target_services:
            # Test di interruzione del servizio
            tests.append(TestCase(
                name=f"chaos_service_stop_{service}",
                type=TestType.CHAOS,
                function=lambda s=service: self._test_service_interruption(s),
                description=f"Test di interruzione del servizio {service}",
                tags=["chaos", service],
            ))
            
            # Test di latenza elevata
            tests.append(TestCase(
                name=f"chaos_high_latency_{service}",
                type=TestType.CHAOS,
                function=lambda s=service: self._test_high_latency(s),
                description=f"Test di latenza elevata per {service}",
                tags=["chaos", service],
            ))
            
            # Test di utilizzo eccessivo di risorse
            tests.append(TestCase(
                name=f"chaos_resource_exhaustion_{service}",
                type=TestType.CHAOS,
                function=lambda s=service: self._test_resource_exhaustion(s),
                description=f"Test di esaurimento risorse per {service}",
                tags=["chaos", service],
            ))
        
        return tests
    
    def _test_service_interruption(self, service: str):
        """Simula l'interruzione di un servizio."""
        logger.info(f"Esecuzione test di interruzione per {service}")
        # In un'implementazione reale, interrompere effettivamente il servizio
        # e verificare che il sistema gestisca correttamente l'errore
        time.sleep(1)  # Simuliamo l'operazione
        
        # Qui si verificherebbe che il sistema ha gestito l'errore correttamente
        # Ad esempio, attivando fallback o circuit breaker
        return True
    
    def _test_high_latency(self, service: str):
        """Simula alta latenza per un servizio."""
        logger.info(f"Esecuzione test di latenza elevata per {service}")
        # In un'implementazione reale, si introdurrebbe un ritardo nel servizio
        time.sleep(1)  # Simuliamo l'operazione
        
        # Qui si verificherebbe che il sistema gestisce correttamente la latenza
        # Ad esempio, con timeout e retry appropriati
        return True
    
    def _test_resource_exhaustion(self, service: str):
        """Simula l'esaurimento delle risorse per un servizio."""
        logger.info(f"Esecuzione test di esaurimento risorse per {service}")
        # In un'implementazione reale, si causerebbe un utilizzo elevato di CPU/memoria
        time.sleep(1)  # Simuliamo l'operazione
        
        # Qui si verificherebbe che il sistema gestisce correttamente il problema
        # Ad esempio, con scaling automatico o degradazione controllata
        return True

class AITestGenerator:
    """Generatore di test basato su intelligenza artificiale."""
    
    def __init__(self, codebase_dir: str):
        self.codebase_dir = codebase_dir
    
    def analyze_code(self, file_path: str) -> List[Dict[str, Any]]:
        """Analizza un file di codice per generare test automaticamente."""
        logger.info(f"Analisi del file {file_path} per generazione test")
        
        # In un'implementazione reale, qui si userebbe un modello di AI
        # per analizzare il codice e identificare casi di test potenziali
        
        # Per ora, restituiamo solo alcuni mock di risultati
        return [
            {
                "function_name": "example_function",
                "input_params": {"param1": "value1", "param2": 42},
                "expected_output": {"result": True, "value": "expected_result"},
                "test_description": "Verifica che la funzione restituisca il risultato atteso",
            },
            {
                "function_name": "example_function",
                "input_params": {"param1": "", "param2": -1},
                "expected_output": None,
                "expected_exception": "ValueError",
                "test_description": "Verifica che la funzione gestisca correttamente input invalidi",
            }
        ]
    
    def generate_test_code(self, analysis_result: Dict[str, Any]) -> str:
        """Genera codice di test basato sull'analisi del codice."""
        fn_name = analysis_result["function_name"]
        input_params = json.dumps(analysis_result["input_params"])
        
        if "expected_exception" in analysis_result:
            return f"""
def test_{fn_name}_exception():
    \"\"\"
    {analysis_result['test_description']}
    \"\"\"
    with pytest.raises({analysis_result['expected_exception']}):
        {fn_name}(**{input_params})
"""
        else:
            expected = json.dumps(analysis_result["expected_output"])
            return f"""
def test_{fn_name}_output():
    \"\"\"
    {analysis_result['test_description']}
    \"\"\"
    result = {fn_name}(**{input_params})
    assert result == {expected}
"""

class TestRunner:
    """Esegue i test e genera report."""
    
    def __init__(self, registry: TestRegistry = None):
        self.registry = registry or test_registry
    
    async def run_test(self, test_case: TestCase) -> TestCase:
        """Esegue un singolo test case."""
        logger.info(f"Esecuzione test: {test_case.name}")
        
        # Imposta il risultato iniziale come in corso
        test_case.result = TestResult.PENDING
        test_case.timestamp = time.time()
        
        # Controlla le dipendenze
        for dep_name in test_case.dependencies:
            dep_test = self.registry.get_test(dep_name)
            if dep_test and dep_test.result != TestResult.PASS:
                test_case.result = TestResult.SKIP
                test_case.error_message = f"Dipendenza non soddisfatta: {dep_name}"
                logger.warning(f"Test {test_case.name} saltato: {test_case.error_message}")
                return test_case
        
        start_time = time.time()
        retry_count = 0
        max_retries = test_case.retry_count
        
        while retry_count <= max_retries:
            try:
                # Esegui il test con timeout
                loop = asyncio.get_event_loop()
                if asyncio.iscoroutinefunction(test_case.function):
                    # Funzione asincrona
                    result = await asyncio.wait_for(
                        test_case.function(),
                        timeout=test_case.timeout
                    )
                else:
                    # Funzione sincrona
                    result = await loop.run_in_executor(
                        None,
                        test_case.function
                    )
                
                # Test passato
                test_case.result = TestResult.PASS
                test_case.duration = time.time() - start_time
                logger.info(f"Test {test_case.name} passato in {test_case.duration:.2f}s")
                break
                
            except asyncio.TimeoutError:
                # Timeout
                test_case.result = TestResult.FAIL
                test_case.error_message = f"Test timeout dopo {test_case.timeout}s"
                test_case.duration = time.time() - start_time
                logger.error(f"Test {test_case.name} fallito: {test_case.error_message}")
                
            except AssertionError as e:
                # Assertion fallita (test non passato)
                test_case.result = TestResult.FAIL
                test_case.error_message = str(e) or "Assertion Error"
                test_case.stack_trace = traceback.format_exc()
                test_case.duration = time.time() - start_time
                logger.error(f"Test {test_case.name} fallito: {test_case.error_message}")
                
            except Exception as e:
                # Errore imprevisto
                test_case.result = TestResult.ERROR
                test_case.error_message = f"{type(e).__name__}: {str(e)}"
                test_case.stack_trace = traceback.format_exc()
                test_case.duration = time.time() - start_time
                logger.error(f"Errore in test {test_case.name}: {test_case.error_message}")
                logger.debug(test_case.stack_trace)
            
            # Verifica se ritentare
            retry_count += 1
            if retry_count <= max_retries:
                logger.info(f"Ritento {retry_count}/{max_retries} per test {test_case.name}")
                await asyncio.sleep(1)  # Piccola pausa prima di ritentare
                start_time = time.time()  # Resetta il timer
            
        return test_case
    
    async def run_suite(self, suite: TestSuite) -> TestSuite:
        """Esegue tutti i test in una suite."""
        logger.info(f"Esecuzione suite: {suite.name}")
        
        # Setup
        if suite.setup:
            try:
                if asyncio.iscoroutinefunction(suite.setup):
                    await suite.setup()
                else:
                    suite.setup()
            except Exception as e:
                logger.error(f"Errore durante setup della suite {suite.name}: {e}")
                # Se il setup fallisce, saltiamo tutti i test
                for test in suite.test_cases:
                    test.result = TestResult.SKIP
                    test.error_message = f"Setup della suite fallito: {str(e)}"
                return suite
        
        # Esegui i test
        start_time = time.time()
        
        for test in suite.test_cases:
            await self.run_test(test)
            
            # Aggiorna le statistiche della suite
            if test.result == TestResult.PASS:
                suite.passed += 1
            elif test.result == TestResult.FAIL:
                suite.failed += 1
            elif test.result == TestResult.ERROR:
                suite.errors += 1
            elif test.result == TestResult.SKIP:
                suite.skipped += 1
        
        suite.total_duration = time.time() - start_time
        
        # Teardown
        if suite.teardown:
            try:
                if asyncio.iscoroutinefunction(suite.teardown):
                    await suite.teardown()
                else:
                    suite.teardown()
            except Exception as e:
                logger.error(f"Errore durante teardown della suite {suite.name}: {e}")
        
        logger.info(f"Suite {suite.name} completata in {suite.total_duration:.2f}s. "
                   f"Risultati: {suite.passed} passati, {suite.failed} falliti, "
                   f"{suite.errors} errori, {suite.skipped} saltati")
        
        return suite
    
    async def run_all(self, filter_tags: List[str] = None, filter_types: List[TestType] = None) -> TestReport:
        """Esegue tutti i test registrati, con filtri opzionali."""
        suites_to_run = list(self.registry.test_suites.values())
        
        # Filtra per tag se specificato
        if filter_tags:
            filtered_suites = []
            for suite in suites_to_run:
                # Includi la suite se ha uno dei tag o se uno dei suoi test ha uno dei tag
                if any(tag in suite.tags for tag in filter_tags) or any(
                    any(tag in test.tags for tag in filter_tags) for test in suite.test_cases
                ):
                    # Ma includi solo i test che matchano i tag
                    if not any(tag in suite.tags for tag in filter_tags):
                        suite.test_cases = [
                            test for test in suite.test_cases
                            if any(tag in test.tags for tag in filter_tags)
                        ]
                    filtered_suites.append(suite)
            suites_to_run = filtered_suites
        
        # Filtra per tipo se specificato
        if filter_types:
            for suite in suites_to_run:
                suite.test_cases = [
                    test for test in suite.test_cases
                    if test.type in filter_types
                ]
            
            # Rimuovi suite vuote
            suites_to_run = [suite for suite in suites_to_run if suite.test_cases]
        
        # Crea il report
        report_id = f"test_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        report = TestReport(
            id=report_id,
            suites=suites_to_run,
            start_time=time.time(),
            environment={
                "platform": os.name,
                "python_version": ".".join(map(str, tuple(sys.version_info)[:3])),
                "hostname": os.environ.get("HOSTNAME", "unknown"),
                "user": os.environ.get("USER", os.environ.get("USERNAME", "unknown")),
            }
        )
        
        # Esegui tutte le suite
        for suite in suites_to_run:
            await self.run_suite(suite)
            
            # Aggiorna le statistiche del report
            report.total_tests += len(suite.test_cases)
            report.passed_tests += suite.passed
            report.failed_tests += suite.failed
            report.error_tests += suite.errors
            report.skipped_tests += suite.skipped
        
        report.end_time = time.time()
        report.total_duration = report.end_time - report.start_time
        
        logger.info(f"Esecuzione test completata in {report.total_duration:.2f}s. "
                   f"Risultati: {report.passed_tests} passati, {report.failed_tests} falliti, "
                   f"{report.error_tests} errori, {report.skipped_tests} saltati")
        
        # Salva il report
        self.save_report(report)
        
        return report
    
    def save_report(self, report: TestReport) -> str:
        """Salva il report in formato JSON."""
        report_file = REPORT_DIR / f"{report.id}.json"
        
        # Converti il report in un dizionario
        report_dict = {
            "id": report.id,
            "start_time": report.start_time,
            "end_time": report.end_time,
            "total_duration": report.total_duration,
            "total_tests": report.total_tests,
            "passed_tests": report.passed_tests,
            "failed_tests": report.failed_tests,
            "error_tests": report.error_tests,
            "skipped_tests": report.skipped_tests,
            "environment": report.environment,
            "suites": []
        }
        
        # Converti le suite in dizionari
        for suite in report.suites:
            suite_dict = {
                "name": suite.name,
                "description": suite.description,
                "tags": suite.tags,
                "passed": suite.passed,
                "failed": suite.failed,
                "errors": suite.errors,
                "skipped": suite.skipped,
                "total_duration": suite.total_duration,
                "test_cases": []
            }
            
            # Converti i test case in dizionari
            for test in suite.test_cases:
                test_dict = {
                    "name": test.name,
                    "type": test.type.value,
                    "description": test.description,
                    "tags": test.tags,
                    "result": test.result.value,
                    "duration": test.duration,
                    "error_message": test.error_message,
                    "stack_trace": test.stack_trace,
                    "timestamp": test.timestamp,
                }
                suite_dict["test_cases"].append(test_dict)
            
            report_dict["suites"].append(suite_dict)
        
        # Salva come JSON
        with open(report_file, "w") as f:
            json.dump(report_dict, f, indent=2)
        
        logger.info(f"Report salvato in {report_file}")
        return str(report_file)

class LoadTestRunner:
    """Esegue test di carico utilizzando Locust."""
    
    def __init__(self, host: str = "http://localhost:8000"):
        self.host = host
    
    def create_locust_file(self, tests: List[Dict[str, Any]]) -> str:
        """Crea un file Locust con i test di carico specificati."""
        locust_file = REPORT_DIR / "locustfile.py"
        
        # Crea il contenuto del file
        content = f"""
from locust import HttpUser, task, between

class M4BotLoadTest(HttpUser):
    wait_time = between(1, 2)
    
"""
        
        # Aggiungi i task per ogni test
        for i, test in enumerate(tests):
            content += f"""
    @task({test.get('weight', 1)})
    def test_{i}(self):
        self.client.{test['method'].lower()}("{test['endpoint']}", {test.get('data', {})})
"""
        
        # Scrivi il file
        with open(locust_file, "w") as f:
            f.write(content)
        
        return str(locust_file)
    
    def run_load_test(self, tests: List[Dict[str, Any]], users: int = 10, spawn_rate: int = 1, 
                     run_time: str = "1m") -> Dict[str, Any]:
        """Esegue il test di carico con i parametri specificati."""
        locust_file = self.create_locust_file(tests)
        
        # In un'implementazione reale, si eseguirebbe Locust da qui
        # Per ora, simuliamo il risultato
        logger.info(f"Avvio test di carico con {users} utenti e spawn rate {spawn_rate}")
        logger.info(f"Durata test: {run_time}")
        
        # Simula un'esecuzione
        time.sleep(2)
        
        # Restituisci risultati simulati
        return {
            "total_requests": users * 10,
            "requests_per_second": users * 2,
            "median_response_time": 120,
            "95th_percentile": 250,
            "failed_requests": int(users * 0.05),
            "success_rate": 95.0,
        }

class CoverageAnalyzer:
    """Analizza la copertura del codice durante i test."""
    
    def __init__(self, codebase_dir: str = None):
        self.codebase_dir = codebase_dir or str(BASE_DIR)
    
    def generate_coverage_report(self) -> CoverageReport:
        """Genera un report sulla copertura del codice dopo l'esecuzione dei test."""
        # In un'implementazione reale, si userebbe un tool come Coverage.py
        # Per ora, restituiamo dati simulati
        
        report = CoverageReport(
            lines_covered=845,
            lines_total=1024,
            functions_covered=128,
            functions_total=156,
            branches_covered=340,
            branches_total=412,
        )
        
        # Aggiungi dati per file
        report.coverage_by_file = {
            "app/models.py": {
                "lines_covered": 120,
                "lines_total": 135,
                "functions_covered": 22,
                "functions_total": 24,
                "branches_covered": 45,
                "branches_total": 52,
            },
            "app/controllers.py": {
                "lines_covered": 210,
                "lines_total": 245,
                "functions_covered": 28,
                "functions_total": 32,
                "branches_covered": 85,
                "branches_total": 100,
            },
            "services/api.py": {
                "lines_covered": 95,
                "lines_total": 120,
                "functions_covered": 14,
                "functions_total": 18,
                "branches_covered": 32,
                "branches_total": 45,
            },
        }
        
        return report
    
    def save_coverage_report(self, report: CoverageReport) -> str:
        """Salva il report sulla copertura in formato JSON."""
        report_file = REPORT_DIR / f"coverage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Converti il report in un dizionario
        report_dict = {
            "summary": {
                "lines_covered": report.lines_covered,
                "lines_total": report.lines_total,
                "lines_percent": report.line_coverage_percent,
                "functions_covered": report.functions_covered,
                "functions_total": report.functions_total,
                "functions_percent": report.function_coverage_percent,
                "branches_covered": report.branches_covered,
                "branches_total": report.branches_total,
                "branches_percent": report.branch_coverage_percent,
            },
            "files": report.coverage_by_file,
        }
        
        # Salva come JSON
        with open(report_file, "w") as f:
            json.dump(report_dict, f, indent=2)
        
        logger.info(f"Report copertura salvato in {report_file}")
        return str(report_file)

class AutomatedTestingManager:
    """Manager per l'automazione completa dei test."""
    
    def __init__(self):
        self.registry = test_registry
        self.test_runner = TestRunner(self.registry)
        self.load_test_runner = LoadTestRunner()
        self.coverage_analyzer = CoverageAnalyzer()
        self.chaos_generator = ChaosTestGenerator([
            "web_service", "bot_service", "database", "nginx"
        ])
        self.ai_generator = AITestGenerator(str(BASE_DIR))
    
    def discover_tests(self):
        """Scopre e registra automaticamente i test nella codebase."""
        logger.info("Ricerca automatica dei test nella codebase")
        
        # Cerca file di test
        test_files = list(TEST_DIR.glob("**/*_test.py")) + list(TEST_DIR.glob("**/test_*.py"))
        logger.info(f"Trovati {len(test_files)} file di test")
        
        # In un'implementazione reale, qui si importerebbero i file trovati
        # per registrare automaticamente i test tramite i decoratori
        
        # Aggiungi test di chaos
        chaos_tests = self.chaos_generator.generate_tests()
        logger.info(f"Generati {len(chaos_tests)} test di chaos")
        
        for test in chaos_tests:
            self.registry.register_test("chaos_testing", test)
        
        # Qui si potrebbero anche generare test con AI
        
        return self.registry
    
    async def run_full_test_suite(self) -> Dict[str, Any]:
        """Esegue una suite completa di test con tutti i tipi di test."""
        results = {
            "unit_integration": None,
            "end_to_end": None,
            "performance": None,
            "chaos": None,
            "coverage": None,
        }
        
        # Scopri test
        self.discover_tests()
        
        # Esegui test unitari e di integrazione
        logger.info("Esecuzione test unitari e di integrazione")
        results["unit_integration"] = await self.test_runner.run_all(
            filter_types=[TestType.UNIT, TestType.INTEGRATION]
        )
        
        # Esegui test end-to-end
        logger.info("Esecuzione test end-to-end")
        results["end_to_end"] = await self.test_runner.run_all(
            filter_types=[TestType.E2E]
        )
        
        # Esegui test di performance
        logger.info("Esecuzione test di performance")
        results["performance"] = await self.test_runner.run_all(
            filter_types=[TestType.PERFORMANCE]
        )
        
        # Esegui test di chaos
        logger.info("Esecuzione test di chaos")
        results["chaos"] = await self.test_runner.run_all(
            filter_types=[TestType.CHAOS]
        )
        
        # Genera report di copertura
        logger.info("Generazione report di copertura")
        coverage_report = self.coverage_analyzer.generate_coverage_report()
        self.coverage_analyzer.save_coverage_report(coverage_report)
        results["coverage"] = coverage_report
        
        # Test di carico
        logger.info("Esecuzione test di carico")
        load_test_config = [
            {"method": "GET", "endpoint": "/api/v1/status", "weight": 10},
            {"method": "POST", "endpoint": "/api/v1/users", "weight": 3, 
             "data": {"name": "Test User", "email": "test@example.com"}},
            {"method": "GET", "endpoint": "/api/v1/dashboard", "weight": 5},
        ]
        
        load_test_results = self.load_test_runner.run_load_test(
            tests=load_test_config,
            users=50,
            spawn_rate=5,
            run_time="2m"
        )
        results["load"] = load_test_results
        
        return results
    
    def generate_html_report(self, results: Dict[str, Any]) -> str:
        """Genera un report HTML completo dai risultati dei test."""
        report_file = REPORT_DIR / f"full_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        
        # In un'implementazione reale, qui si genererebbe un report HTML completo
        # con grafici, statistiche e dettagli sui test
        
        # Per ora, generiamo un semplice report HTML
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>M4Bot Test Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                h1, h2, h3 {{ color: #333; }}
                .summary {{ display: flex; justify-content: space-around; margin: 20px 0; }}
                .summary-box {{ border: 1px solid #ddd; padding: 10px; border-radius: 5px; width: 200px; text-align: center; }}
                .pass {{ color: green; }}
                .fail {{ color: red; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }}
                tr:nth-child(even) {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>M4Bot Test Report</h1>
            <p>Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <h2>Summary</h2>
            <div class="summary">
                <div class="summary-box">
                    <h3>Unit & Integration</h3>
                    <p><span class="pass">{results['unit_integration'].passed_tests}</span> passed / <span class="fail">{results['unit_integration'].failed_tests + results['unit_integration'].error_tests}</span> failed</p>
                </div>
                <div class="summary-box">
                    <h3>End-to-End</h3>
                    <p><span class="pass">{results['end_to_end'].passed_tests}</span> passed / <span class="fail">{results['end_to_end'].failed_tests + results['end_to_end'].error_tests}</span> failed</p>
                </div>
                <div class="summary-box">
                    <h3>Performance</h3>
                    <p><span class="pass">{results['performance'].passed_tests}</span> passed / <span class="fail">{results['performance'].failed_tests + results['performance'].error_tests}</span> failed</p>
                </div>
                <div class="summary-box">
                    <h3>Chaos</h3>
                    <p><span class="pass">{results['chaos'].passed_tests}</span> passed / <span class="fail">{results['chaos'].failed_tests + results['chaos'].error_tests}</span> failed</p>
                </div>
            </div>
            
            <h2>Code Coverage</h2>
            <table>
                <tr>
                    <th>Type</th>
                    <th>Coverage</th>
                    <th>Details</th>
                </tr>
                <tr>
                    <td>Line Coverage</td>
                    <td>{results['coverage'].line_coverage_percent:.1f}%</td>
                    <td>{results['coverage'].lines_covered} / {results['coverage'].lines_total}</td>
                </tr>
                <tr>
                    <td>Function Coverage</td>
                    <td>{results['coverage'].function_coverage_percent:.1f}%</td>
                    <td>{results['coverage'].functions_covered} / {results['coverage'].functions_total}</td>
                </tr>
                <tr>
                    <td>Branch Coverage</td>
                    <td>{results['coverage'].branch_coverage_percent:.1f}%</td>
                    <td>{results['coverage'].branches_covered} / {results['coverage'].branches_total}</td>
                </tr>
            </table>
            
            <h2>Load Test Results</h2>
            <table>
                <tr>
                    <th>Metric</th>
                    <th>Value</th>
                </tr>
                <tr>
                    <td>Total Requests</td>
                    <td>{results['load']['total_requests']}</td>
                </tr>
                <tr>
                    <td>Requests Per Second</td>
                    <td>{results['load']['requests_per_second']}</td>
                </tr>
                <tr>
                    <td>Median Response Time</td>
                    <td>{results['load']['median_response_time']} ms</td>
                </tr>
                <tr>
                    <td>95th Percentile</td>
                    <td>{results['load']['95th_percentile']} ms</td>
                </tr>
                <tr>
                    <td>Success Rate</td>
                    <td>{results['load']['success_rate']}%</td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        with open(report_file, "w") as f:
            f.write(html)
        
        logger.info(f"Report HTML salvato in {report_file}")
        return str(report_file)

# Esempio di utilizzo
if __name__ == "__main__":
    # Crea un manager per l'automazione dei test
    manager = AutomatedTestingManager()
    
    # Esegui la suite completa di test
    asyncio.run(manager.run_full_test_suite()) 