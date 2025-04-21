#!/usr/bin/env python3
"""
M4Bot - Framework di Test Avanzato

Questo modulo implementa un framework di test avanzato con:
- Test funzionali automatizzati
- Test di integrazione
- Test di carico e scalabilità
- Fuzzing per sicurezza
- Test basati su modelli (Model-based testing)
- Monitoraggio continuo della qualità
"""

import os
import sys
import time
import json
import random
import logging
import asyncio
import inspect
import unittest
import concurrent.futures
from typing import Dict, List, Any, Optional, Tuple, Set, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

# Importazioni per test Web
import aiohttp
import requests

# Configurazione logging
logger = logging.getLogger('m4bot.stability.testing')

# Percorso radice del progetto
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

class TestType(Enum):
    """Tipi di test supportati."""
    UNIT = 'unit'
    INTEGRATION = 'integration'
    FUNCTIONAL = 'functional'
    PERFORMANCE = 'performance'
    SECURITY = 'security'
    MODEL_BASED = 'model_based'
    UI = 'ui'
    API = 'api'
    FUZZ = 'fuzz'

class TestPriority(Enum):
    """Priorità dei test."""
    CRITICAL = 'critical'
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'

class TestResult(Enum):
    """Possibili risultati di un test."""
    PASS = 'pass'
    FAIL = 'fail'
    ERROR = 'error'
    SKIP = 'skip'
    FLAKY = 'flaky'  # Test che passa a volte e fallisce altre

@dataclass
class TestCase:
    """Rappresenta un caso di test."""
    id: str
    name: str
    description: str
    type: TestType
    priority: TestPriority = TestPriority.MEDIUM
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    setup: Optional[Callable] = None
    teardown: Optional[Callable] = None
    timeout: int = 60  # Timeout in secondi
    enabled: bool = True
    function: Optional[Callable] = None
    
    # Campi per risultati
    result: TestResult = TestResult.SKIP
    duration: float = 0.0
    error_message: str = ""
    last_run: Optional[float] = None
    retries: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte il caso di test in un dizionario."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'type': self.type.value,
            'priority': self.priority.value,
            'tags': self.tags,
            'dependencies': self.dependencies,
            'timeout': self.timeout,
            'enabled': self.enabled,
            'result': self.result.value,
            'duration': self.duration,
            'error_message': self.error_message,
            'last_run': self.last_run,
            'retries': self.retries
        }

@dataclass
class TestSuite:
    """Rappresenta una suite di test."""
    id: str
    name: str
    description: str
    test_cases: List[TestCase] = field(default_factory=list)
    setup: Optional[Callable] = None
    teardown: Optional[Callable] = None
    parallel: bool = False
    
    # Statistiche
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    errors: int = 0
    flaky: int = 0
    total_duration: float = 0.0
    
    def add_test_case(self, test_case: TestCase) -> None:
        """Aggiunge un caso di test alla suite."""
        self.test_cases.append(test_case)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte la suite di test in un dizionario."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'test_cases': [tc.to_dict() for tc in self.test_cases],
            'parallel': self.parallel,
            'statistics': {
                'passed': self.passed,
                'failed': self.failed,
                'skipped': self.skipped,
                'errors': self.errors,
                'flaky': self.flaky,
                'total_duration': self.total_duration,
                'total': len(self.test_cases)
            }
        }

class TestDecorators:
    """Decoratori per i test."""
    
    @staticmethod
    def test_case(id: str, name: str, description: str, test_type: TestType, 
                  priority: TestPriority = TestPriority.MEDIUM, 
                  tags: List[str] = None, dependencies: List[str] = None,
                  timeout: int = 60):
        """Decoratore per funzioni di test."""
        if tags is None:
            tags = []
        if dependencies is None:
            dependencies = []
        
        def decorator(func):
            func._test_metadata = {
                'id': id,
                'name': name,
                'description': description,
                'type': test_type,
                'priority': priority,
                'tags': tags,
                'dependencies': dependencies,
                'timeout': timeout
            }
            return func
        return decorator
    
    @staticmethod
    def setup(func):
        """Decoratore per funzioni di setup."""
        func._is_setup = True
        return func
    
    @staticmethod
    def teardown(func):
        """Decoratore per funzioni di teardown."""
        func._is_teardown = True
        return func
    
    @staticmethod
    def parametrize(params):
        """Decoratore per test parametrizzati."""
        def decorator(func):
            func._parametrize = params
            return func
        return decorator
    
    @staticmethod
    def flaky(max_retries: int = 3, min_passes: int = 1):
        """Decoratore per test instabili che possono richiedere più tentativi."""
        def decorator(func):
            func._flaky = {
                'max_retries': max_retries,
                'min_passes': min_passes
            }
            return func
        return decorator
    
    @staticmethod
    def skip(reason: str = ""):
        """Decoratore per saltare test."""
        def decorator(func):
            func._skip = True
            func._skip_reason = reason
            return func
        return decorator

class TestRunner:
    """Esegue suite di test e casi di test."""
    
    def __init__(self, report_dir: str = None):
        """
        Inizializza il test runner.
        
        Args:
            report_dir: Directory dove salvare i report di test
        """
        self.suites: List[TestSuite] = []
        self.report_dir = report_dir or os.path.join(PROJECT_ROOT, 'test_reports')
        self.start_time = 0.0
        self.end_time = 0.0
        self.current_suite = None
        
        # Crea directory report se non esiste
        os.makedirs(self.report_dir, exist_ok=True)
    
    def load_from_module(self, module) -> TestSuite:
        """
        Carica test da un modulo Python.
        
        Args:
            module: Modulo Python contenente i test
            
        Returns:
            TestSuite caricata dal modulo
        """
        module_name = module.__name__.split('.')[-1]
        suite = TestSuite(
            id=f"suite_{module_name}",
            name=module_name,
            description=module.__doc__ or f"Test suite per {module_name}"
        )
        
        # Cerca funzioni di setup/teardown a livello di modulo
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj):
                if hasattr(obj, '_is_setup'):
                    suite.setup = obj
                elif hasattr(obj, '_is_teardown'):
                    suite.teardown = obj
        
        # Cerca test case
        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and hasattr(obj, '_test_metadata'):
                metadata = obj._test_metadata
                
                test_case = TestCase(
                    id=metadata['id'],
                    name=metadata['name'],
                    description=metadata['description'],
                    type=metadata['type'],
                    priority=metadata['priority'],
                    tags=metadata['tags'],
                    dependencies=metadata['dependencies'],
                    timeout=metadata['timeout'],
                    function=obj
                )
                
                # Gestione test parametrizzati
                if hasattr(obj, '_parametrize'):
                    self._add_parametrized_tests(suite, test_case, obj._parametrize)
                else:
                    suite.add_test_case(test_case)
        
        self.suites.append(suite)
        return suite
    
    def _add_parametrized_tests(self, suite: TestSuite, base_test: TestCase, params: List[Dict[str, Any]]):
        """Aggiunge test parametrizzati."""
        for i, param_set in enumerate(params):
            # Crea una copia del test di base
            test_copy = TestCase(
                id=f"{base_test.id}_param{i}",
                name=f"{base_test.name} (Param Set {i+1})",
                description=base_test.description,
                type=base_test.type,
                priority=base_test.priority,
                tags=base_test.tags.copy(),
                dependencies=base_test.dependencies.copy(),
                timeout=base_test.timeout,
                function=base_test.function
            )
            
            # Aggiungi parametro al test
            test_copy._params = param_set
            
            suite.add_test_case(test_copy)
    
    def load_from_directory(self, directory: str) -> List[TestSuite]:
        """
        Carica test da tutti i file Python in una directory.
        
        Args:
            directory: Percorso della directory da cui caricare i test
            
        Returns:
            Lista di TestSuite caricate
        """
        loaded_suites = []
        
        # Verifica che la directory esista
        if not os.path.exists(directory):
            logger.error(f"Directory non trovata: {directory}")
            return loaded_suites
        
        # Aggiungi directory al sys.path per l'importazione
        sys.path.insert(0, os.path.dirname(directory))
        
        # Cerca tutti i file Python nella directory
        for filename in os.listdir(directory):
            if filename.startswith('test_') and filename.endswith('.py'):
                module_name = filename[:-3]  # Rimuovi estensione .py
                
                try:
                    # Importa modulo
                    module = __import__(module_name)
                    suite = self.load_from_module(module)
                    loaded_suites.append(suite)
                except Exception as e:
                    logger.error(f"Errore nel caricamento del modulo {module_name}: {e}")
        
        # Ripristina sys.path
        sys.path.pop(0)
        
        return loaded_suites
    
    async def run_suite(self, suite: TestSuite) -> None:
        """
        Esegue una suite di test.
        
        Args:
            suite: TestSuite da eseguire
        """
        logger.info(f"Esecuzione suite di test: {suite.name}")
        self.current_suite = suite
        
        suite_start_time = time.time()
        
        # Reset contatori
        suite.passed = 0
        suite.failed = 0
        suite.skipped = 0
        suite.errors = 0
        suite.flaky = 0
        
        # Esegui setup della suite
        if suite.setup:
            try:
                await self._run_callable(suite.setup)
            except Exception as e:
                logger.error(f"Errore nel setup della suite {suite.name}: {e}")
                for test_case in suite.test_cases:
                    test_case.result = TestResult.ERROR
                    test_case.error_message = f"Errore nel setup della suite: {str(e)}"
                    suite.errors += 1
                return
        
        # Esegui test in parallelo o in sequenza
        try:
            if suite.parallel:
                # Esecuzione parallela con asyncio.gather
                tasks = [self.run_test_case(test_case) for test_case in suite.test_cases if test_case.enabled]
                await asyncio.gather(*tasks)
            else:
                # Esecuzione sequenziale
                for test_case in suite.test_cases:
                    if test_case.enabled:
                        await self.run_test_case(test_case)
        finally:
            # Esegui teardown della suite
            if suite.teardown:
                try:
                    await self._run_callable(suite.teardown)
                except Exception as e:
                    logger.error(f"Errore nel teardown della suite {suite.name}: {e}")
        
        # Calcola statistiche
        suite.total_duration = time.time() - suite_start_time
        
        # Aggiorna contatori
        for test_case in suite.test_cases:
            if test_case.result == TestResult.PASS:
                suite.passed += 1
            elif test_case.result == TestResult.FAIL:
                suite.failed += 1
            elif test_case.result == TestResult.ERROR:
                suite.errors += 1
            elif test_case.result == TestResult.SKIP:
                suite.skipped += 1
            elif test_case.result == TestResult.FLAKY:
                suite.flaky += 1
        
        logger.info(f"Suite di test {suite.name} completata in {suite.total_duration:.2f}s: "
                   f"{suite.passed} passed, {suite.failed} failed, {suite.errors} errors, "
                   f"{suite.skipped} skipped, {suite.flaky} flaky")
    
    async def run_test_case(self, test_case: TestCase) -> None:
        """
        Esegue un caso di test.
        
        Args:
            test_case: TestCase da eseguire
        """
        if not test_case.enabled:
            test_case.result = TestResult.SKIP
            test_case.error_message = "Test disabilitato"
            return
        
        # Controlla se il test deve essere saltato
        if test_case.function and hasattr(test_case.function, '_skip'):
            test_case.result = TestResult.SKIP
            test_case.error_message = getattr(test_case.function, '_skip_reason', "Test saltato")
            return
        
        # Controlla dipendenze
        for dep_id in test_case.dependencies:
            dep_satisfied = False
            
            if self.current_suite:
                for tc in self.current_suite.test_cases:
                    if tc.id == dep_id:
                        if tc.result != TestResult.PASS:
                            test_case.result = TestResult.SKIP
                            test_case.error_message = f"Dipendenza non soddisfatta: {dep_id}"
                            return
                        dep_satisfied = True
                        break
            
            if not dep_satisfied:
                logger.warning(f"Dipendenza {dep_id} non trovata per il test {test_case.id}")
        
        # Messaggio inizio test
        logger.info(f"Esecuzione test: {test_case.name} ({test_case.id})")
        
        test_case.last_run = time.time()
        start_time = time.time()
        
        # Esegui setup del test
        if test_case.setup:
            try:
                await self._run_callable(test_case.setup)
            except Exception as e:
                test_case.result = TestResult.ERROR
                test_case.error_message = f"Errore nel setup: {str(e)}"
                test_case.duration = time.time() - start_time
                return
        
        # Controlla se il test è marcato come flaky
        is_flaky = hasattr(test_case.function, '_flaky')
        max_retries = getattr(test_case.function, '_flaky', {}).get('max_retries', 3) if is_flaky else 1
        min_passes = getattr(test_case.function, '_flaky', {}).get('min_passes', 1) if is_flaky else 1
        
        # Esegui il test con timeout
        pass_count = 0
        last_error = None
        
        for retry in range(max_retries):
            test_case.retries = retry
            
            try:
                # Imposta timeout
                result = await asyncio.wait_for(
                    self._run_callable(test_case.function),
                    timeout=test_case.timeout
                )
                
                # Se il test non solleva eccezioni, è passato
                pass_count += 1
                if pass_count >= min_passes:
                    break
            except asyncio.TimeoutError:
                last_error = "Timeout raggiunto"
            except AssertionError as e:
                last_error = f"Fallimento assert: {str(e)}"
            except Exception as e:
                last_error = f"Errore: {str(e)}"
        
        # Esegui teardown del test
        if test_case.teardown:
            try:
                await self._run_callable(test_case.teardown)
            except Exception as e:
                logger.error(f"Errore nel teardown del test {test_case.id}: {e}")
        
        # Determina risultato finale
        test_case.duration = time.time() - start_time
        
        if pass_count >= min_passes:
            if is_flaky and pass_count < max_retries:
                test_case.result = TestResult.FLAKY
            else:
                test_case.result = TestResult.PASS
        else:
            if last_error.startswith("Fallimento assert:"):
                test_case.result = TestResult.FAIL
            else:
                test_case.result = TestResult.ERROR
            test_case.error_message = last_error
        
        # Log del risultato
        result_str = f"PASS ({pass_count}/{max_retries})" if test_case.result in (TestResult.PASS, TestResult.FLAKY) else test_case.result.value.upper()
        logger.info(f"Test {test_case.id} completato in {test_case.duration:.2f}s: {result_str}")
        if test_case.error_message:
            logger.error(f"  Errore: {test_case.error_message}")
    
    async def _run_callable(self, func: Callable) -> Any:
        """
        Esegue una funzione, che può essere sincrona o asincrona.
        
        Args:
            func: Funzione da eseguire
            
        Returns:
            Risultato della funzione
        """
        if asyncio.iscoroutinefunction(func):
            # Funzione asincrona
            return await func()
        else:
            # Funzione sincrona, eseguita in un executor
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, func)
    
    async def run_all_suites(self) -> Dict[str, Any]:
        """
        Esegue tutte le suite di test.
        
        Returns:
            Dizionario con i risultati dei test
        """
        self.start_time = time.time()
        
        for suite in self.suites:
            await self.run_suite(suite)
        
        self.end_time = time.time()
        
        # Genera report
        results = self.generate_report()
        
        return results
    
    def generate_report(self) -> Dict[str, Any]:
        """
        Genera un report dei risultati dei test.
        
        Returns:
            Dizionario con i risultati dei test
        """
        total_passed = sum(suite.passed for suite in self.suites)
        total_failed = sum(suite.failed for suite in self.suites)
        total_errors = sum(suite.errors for suite in self.suites)
        total_skipped = sum(suite.skipped for suite in self.suites)
        total_flaky = sum(suite.flaky for suite in self.suites)
        total_duration = self.end_time - self.start_time
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'duration': total_duration,
            'summary': {
                'total_suites': len(self.suites),
                'total_tests': sum(len(suite.test_cases) for suite in self.suites),
                'passed': total_passed,
                'failed': total_failed,
                'errors': total_errors,
                'skipped': total_skipped,
                'flaky': total_flaky
            },
            'suites': [suite.to_dict() for suite in self.suites]
        }
        
        # Salva report JSON
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = os.path.join(self.report_dir, f"test_report_{timestamp}.json")
        
        with open(report_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Report salvato in {report_path}")
        
        return results

# Funzioni di utilità per asserzioni
class TestAssertions:
    """Funzioni di asserzione per i test."""
    
    @staticmethod
    def assert_true(condition, message=None):
        """Verifica che la condizione sia True."""
        assert condition, message or "La condizione dovrebbe essere True"
    
    @staticmethod
    def assert_false(condition, message=None):
        """Verifica che la condizione sia False."""
        assert not condition, message or "La condizione dovrebbe essere False"
    
    @staticmethod
    def assert_equal(actual, expected, message=None):
        """Verifica che due valori siano uguali."""
        assert actual == expected, message or f"I valori dovrebbero essere uguali: {actual} != {expected}"
    
    @staticmethod
    def assert_not_equal(actual, expected, message=None):
        """Verifica che due valori non siano uguali."""
        assert actual != expected, message or f"I valori non dovrebbero essere uguali: {actual} == {expected}"
    
    @staticmethod
    def assert_greater(actual, expected, message=None):
        """Verifica che actual sia maggiore di expected."""
        assert actual > expected, message or f"{actual} dovrebbe essere maggiore di {expected}"
    
    @staticmethod
    def assert_less(actual, expected, message=None):
        """Verifica che actual sia minore di expected."""
        assert actual < expected, message or f"{actual} dovrebbe essere minore di {expected}"
    
    @staticmethod
    def assert_in(item, container, message=None):
        """Verifica che item sia in container."""
        assert item in container, message or f"{item} dovrebbe essere in {container}"
    
    @staticmethod
    def assert_not_in(item, container, message=None):
        """Verifica che item non sia in container."""
        assert item not in container, message or f"{item} non dovrebbe essere in {container}"
    
    @staticmethod
    def assert_is_none(obj, message=None):
        """Verifica che obj sia None."""
        assert obj is None, message or f"{obj} dovrebbe essere None"
    
    @staticmethod
    def assert_is_not_none(obj, message=None):
        """Verifica che obj non sia None."""
        assert obj is not None, message or f"Il valore non dovrebbe essere None"
    
    @staticmethod
    def assert_raises(exception_type, function, *args, **kwargs):
        """Verifica che la funzione sollevi un'eccezione del tipo specificato."""
        try:
            function(*args, **kwargs)
            assert False, f"La funzione dovrebbe sollevare {exception_type.__name__}"
        except exception_type:
            return True
        except Exception as e:
            assert False, f"La funzione dovrebbe sollevare {exception_type.__name__}, ma ha sollevato {type(e).__name__}"

class FuzzingGenerator:
    """Generatore di dati casuali per fuzzing."""
    
    @staticmethod
    def random_string(min_length=1, max_length=100, charset=None):
        """Genera una stringa casuale."""
        if charset is None:
            charset = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        length = random.randint(min_length, max_length)
        return ''.join(random.choice(charset) for _ in range(length))
    
    @staticmethod
    def random_integer(min_value=-1000000, max_value=1000000):
        """Genera un intero casuale."""
        return random.randint(min_value, max_value)
    
    @staticmethod
    def random_float(min_value=-1000000.0, max_value=1000000.0):
        """Genera un float casuale."""
        return random.uniform(min_value, max_value)
    
    @staticmethod
    def random_boolean():
        """Genera un booleano casuale."""
        return random.choice([True, False])
    
    @staticmethod
    def random_bytes(min_length=1, max_length=1000):
        """Genera bytes casuali."""
        length = random.randint(min_length, max_length)
        return bytes(random.getrandbits(8) for _ in range(length))
    
    @staticmethod
    def random_choice(choices):
        """Sceglie un elemento casuale da una lista."""
        return random.choice(choices)
    
    @staticmethod
    def random_dict(keys=None, min_length=1, max_length=10):
        """Genera un dizionario casuale."""
        if keys is None:
            keys = [FuzzingGenerator.random_string(1, 10) for _ in range(random.randint(min_length, max_length))]
        
        result = {}
        for key in keys:
            value_type = random.choice(['string', 'int', 'float', 'bool', 'none'])
            
            if value_type == 'string':
                result[key] = FuzzingGenerator.random_string()
            elif value_type == 'int':
                result[key] = FuzzingGenerator.random_integer()
            elif value_type == 'float':
                result[key] = FuzzingGenerator.random_float()
            elif value_type == 'bool':
                result[key] = FuzzingGenerator.random_boolean()
            elif value_type == 'none':
                result[key] = None
        
        return result
    
    @staticmethod
    def random_list(min_length=0, max_length=10):
        """Genera una lista casuale."""
        length = random.randint(min_length, max_length)
        result = []
        
        for _ in range(length):
            value_type = random.choice(['string', 'int', 'float', 'bool', 'none'])
            
            if value_type == 'string':
                result.append(FuzzingGenerator.random_string())
            elif value_type == 'int':
                result.append(FuzzingGenerator.random_integer())
            elif value_type == 'float':
                result.append(FuzzingGenerator.random_float())
            elif value_type == 'bool':
                result.append(FuzzingGenerator.random_boolean())
            elif value_type == 'none':
                result.append(None)
        
        return result
    
    @staticmethod
    def sql_injection_strings():
        """Restituisce stringhe comuni di SQL injection per test di sicurezza."""
        return [
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "1'; SELECT * FROM users; --",
            "' UNION SELECT username, password FROM users; --",
            "1' OR '1' = '1",
            "' OR 1=1--",
            "admin'--",
            "' OR ''='",
            "1=1",
            "1' or '1' = '1",
            "' or 1=1#",
            "' or 1=1/*",
            "') or ('a'='a",
            "hi' or 1=1 --"
        ]
    
    @staticmethod
    def xss_strings():
        """Restituisce stringhe comuni di XSS per test di sicurezza."""
        return [
            "<script>alert('XSS')</script>",
            "<img src='x' onerror='alert(\"XSS\")'>",
            "<body onload='alert(\"XSS\")'>",
            "javascript:alert('XSS')",
            "<svg onload='alert(\"XSS\")'>",
            "\"><script>alert('XSS')</script>",
            "'><script>alert('XSS')</script>",
            "><script>alert('XSS')</script>",
            "</script><script>alert('XSS')</script>",
            "' onerror='alert(\"XSS\")'",
            "\";alert('XSS');//",
            "<ScRiPt>alert('XSS')</ScRiPt>",
            "<img src=x onerror=alert('XSS')>",
            "<input onfocus=alert('XSS') autofocus>"
        ]
    
    @staticmethod
    def special_chars():
        """Restituisce caratteri speciali per test."""
        return [
            "",
            " ",
            "\0",
            "\n",
            "\r",
            "\t",
            "\b",
            "\f",
            "\v",
            "\u0000",
            "\u200b",
            "\ufeff",
            "\\",
            "/",
            ".",
            ",",
            ";",
            ":",
            "'",
            "\"",
            "`",
            "-",
            "_",
            "=",
            "+",
            "*",
            "&",
            "^",
            "%",
            "$",
            "#",
            "@",
            "!",
            "~",
            "|",
            "?",
            "<",
            ">",
            "(",
            ")",
            "[",
            "]",
            "{",
            "}"
        ]

class ModelBasedTesting:
    """Classe per supportare testing basato su modelli."""
    
    def __init__(self, model_file=None):
        """
        Inizializza il sistema di test basato su modelli.
        
        Args:
            model_file: Percorso al file di definizione del modello
        """
        self.states = {}
        self.transitions = []
        self.current_state = None
        self.initial_state = None
        
        if model_file:
            self.load_model(model_file)
    
    def load_model(self, model_file):
        """
        Carica un modello da file JSON.
        
        Args:
            model_file: Percorso al file di definizione del modello
        """
        try:
            with open(model_file, 'r') as f:
                model_data = json.load(f)
                
                # Carica stati
                self.states = model_data.get('states', {})
                
                # Carica transizioni
                self.transitions = model_data.get('transitions', [])
                
                # Stato iniziale
                self.initial_state = model_data.get('initial_state')
                self.current_state = self.initial_state
        except Exception as e:
            logger.error(f"Errore nel caricamento del modello: {e}")
    
    def reset(self):
        """Resetta il modello allo stato iniziale."""
        self.current_state = self.initial_state
    
    def add_state(self, name, properties=None):
        """
        Aggiunge uno stato al modello.
        
        Args:
            name: Nome dello stato
            properties: Dizionario con proprietà dello stato
        """
        self.states[name] = properties or {}
        
        # Se è il primo stato, imposta come iniziale
        if not self.initial_state:
            self.initial_state = name
            self.current_state = name
    
    def add_transition(self, from_state, to_state, action, guard=None):
        """
        Aggiunge una transizione al modello.
        
        Args:
            from_state: Stato di partenza
            to_state: Stato di arrivo
            action: Funzione da eseguire durante la transizione
            guard: Funzione che determina se la transizione è possibile
        """
        self.transitions.append({
            'from': from_state,
            'to': to_state,
            'action': action,
            'guard': guard
        })
    
    def get_valid_transitions(self):
        """
        Restituisce le transizioni valide dallo stato corrente.
        
        Returns:
            Lista di transizioni valide
        """
        valid = []
        
        for transition in self.transitions:
            if transition['from'] == self.current_state:
                if transition['guard'] is None or transition['guard']():
                    valid.append(transition)
        
        return valid
    
    async def execute_random_step(self):
        """
        Esegue un passo casuale tra le transizioni valide.
        
        Returns:
            True se il passo è stato eseguito, False altrimenti
        """
        valid_transitions = self.get_valid_transitions()
        
        if not valid_transitions:
            return False
        
        transition = random.choice(valid_transitions)
        
        # Esegui azione
        action = transition['action']
        if asyncio.iscoroutinefunction(action):
            await action()
        else:
            action()
        
        # Aggiorna stato
        self.current_state = transition['to']
        
        return True
    
    async def execute_random_path(self, max_steps=10):
        """
        Esegue un percorso casuale nel modello.
        
        Args:
            max_steps: Numero massimo di passi
            
        Returns:
            Lista di stati visitati
        """
        self.reset()
        visited_states = [self.current_state]
        
        for _ in range(max_steps):
            if not await self.execute_random_step():
                break
            
            visited_states.append(self.current_state)
        
        return visited_states

# Classe test per API REST
class ApiTestCase:
    """Classe helper per test di API REST."""
    
    def __init__(self, base_url, headers=None):
        """
        Inizializza il test case per API.
        
        Args:
            base_url: URL base per le API
            headers: Headers HTTP predefiniti
        """
        self.base_url = base_url.rstrip('/')
        self.headers = headers or {}
        self.session = None
    
    async def setup(self):
        """Setup per test API."""
        self.session = aiohttp.ClientSession(headers=self.headers)
    
    async def teardown(self):
        """Teardown per test API."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def get(self, endpoint, params=None, expected_status=200):
        """
        Esegue una richiesta GET.
        
        Args:
            endpoint: Endpoint da chiamare
            params: Parametri query string
            expected_status: Codice stato atteso
            
        Returns:
            Tuple con (success, response_data, status_code)
        """
        if not self.session:
            await self.setup()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            async with self.session.get(url, params=params) as response:
                data = await response.json()
                success = response.status == expected_status
                return success, data, response.status
        except Exception as e:
            return False, {'error': str(e)}, 0
    
    async def post(self, endpoint, json_data=None, data=None, expected_status=200):
        """
        Esegue una richiesta POST.
        
        Args:
            endpoint: Endpoint da chiamare
            json_data: Dati JSON
            data: Dati form
            expected_status: Codice stato atteso
            
        Returns:
            Tuple con (success, response_data, status_code)
        """
        if not self.session:
            await self.setup()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            async with self.session.post(url, json=json_data, data=data) as response:
                try:
                    data = await response.json()
                except:
                    data = await response.text()
                
                success = response.status == expected_status
                return success, data, response.status
        except Exception as e:
            return False, {'error': str(e)}, 0
    
    async def put(self, endpoint, json_data=None, data=None, expected_status=200):
        """Esegue una richiesta PUT."""
        if not self.session:
            await self.setup()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            async with self.session.put(url, json=json_data, data=data) as response:
                try:
                    data = await response.json()
                except:
                    data = await response.text()
                
                success = response.status == expected_status
                return success, data, response.status
        except Exception as e:
            return False, {'error': str(e)}, 0
    
    async def delete(self, endpoint, expected_status=200):
        """Esegue una richiesta DELETE."""
        if not self.session:
            await self.setup()
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            async with self.session.delete(url) as response:
                try:
                    data = await response.json()
                except:
                    data = await response.text()
                
                success = response.status == expected_status
                return success, data, response.status
        except Exception as e:
            return False, {'error': str(e)}, 0

# Funzione principale
async def main():
    """Funzione principale per esecuzione test."""
    # Configura logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(os.path.join(PROJECT_ROOT, 'logs', 'test_framework.log'))
        ]
    )
    
    # Percorso directory test
    test_dir = os.path.join(PROJECT_ROOT, 'stability', 'testing', 'tests')
    os.makedirs(test_dir, exist_ok=True)
    
    # Percorso report
    report_dir = os.path.join(PROJECT_ROOT, 'stability', 'testing', 'reports')
    os.makedirs(report_dir, exist_ok=True)
    
    # Crea runner
    runner = TestRunner(report_dir=report_dir)
    
    # Carica test
    if os.path.exists(test_dir) and os.listdir(test_dir):
        suites = runner.load_from_directory(test_dir)
        if suites:
            logger.info(f"Caricate {len(suites)} suite di test")
            
            # Esegui test
            results = await runner.run_all_suites()
            
            # Mostra riepilogo
            summary = results['summary']
            logger.info(f"Test completati in {results['duration']:.2f}s")
            logger.info(f"Totale test: {summary['total_tests']}")
            logger.info(f"Passati: {summary['passed']}")
            logger.info(f"Falliti: {summary['failed']}")
            logger.info(f"Errori: {summary['errors']}")
            logger.info(f"Saltati: {summary['skipped']}")
            logger.info(f"Instabili: {summary['flaky']}")
        else:
            logger.warning("Nessuna suite di test trovata")
    else:
        logger.warning(f"Directory test non trovata o vuota: {test_dir}")

if __name__ == "__main__":
    asyncio.run(main()) 