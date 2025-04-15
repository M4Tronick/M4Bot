"""
Test di carico automatizzato per M4Bot

Questo modulo fornisce strumenti per eseguire test di carico sull'applicazione web,
simulando migliaia di utenti connessi, per verificare la stabilità e le prestazioni del sistema.
"""

import os
import sys
import time
import json
import random
import asyncio
import argparse
import statistics
import aiohttp
import logging
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass, asdict, field
import matplotlib.pyplot as plt
import numpy as np

# Configurazione logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("load_test.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('load_test')

@dataclass
class LoadTestConfig:
    """Configurazione per un test di carico."""
    base_url: str  # URL base dell'applicazione
    target_endpoints: List[str]  # Endpoint da testare
    users: int = 100  # Numero di utenti simultanei
    requests_per_user: int = 10  # Numero di richieste per utente
    ramp_up_time: int = 10  # Tempo (in secondi) per raggiungere il carico massimo
    test_duration: int = 60  # Durata totale del test (in secondi)
    think_time_min: float = 0.1  # Tempo minimo di riflessione tra le richieste (in secondi)
    think_time_max: float = 1.0  # Tempo massimo di riflessione tra le richieste (in secondi)
    login_required: bool = False  # Se è necessario autenticarsi
    login_endpoint: str = "/login"  # Endpoint per il login
    credentials: Dict[str, str] = field(default_factory=dict)  # Credenziali per il login
    request_timeout: int = 30  # Timeout per le richieste (in secondi)
    headers: Dict[str, str] = field(default_factory=dict)  # Header HTTP aggiuntivi
    verify_ssl: bool = True  # Verifica certificati SSL
    use_websocket: bool = False  # Se testare anche WebSocket
    websocket_endpoint: str = "/ws"  # Endpoint WebSocket
    websocket_duration: int = 30  # Durata connessione WebSocket (in secondi)
    test_name: str = ""  # Nome del test
    output_dir: str = "results"  # Directory per i risultati

@dataclass
class RequestResult:
    """Risultato di una singola richiesta."""
    endpoint: str
    method: str
    status_code: int
    response_time: float  # Tempo di risposta in millisecondi
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    user_id: int = 0
    request_id: int = 0
    request_data: Dict[str, Any] = field(default_factory=dict)
    response_data: Optional[Dict[str, Any]] = None

@dataclass
class TestResults:
    """Risultati di un test di carico completo."""
    config: LoadTestConfig
    requests: List[RequestResult] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    errors: List[str] = field(default_factory=list)
    
    # Statistiche aggregate
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    min_response_time: float = float('inf')
    max_response_time: float = 0
    avg_response_time: float = 0
    median_response_time: float = 0
    p95_response_time: float = 0  # 95° percentile
    p99_response_time: float = 0  # 99° percentile
    requests_per_second: float = 0
    
    def calculate_statistics(self):
        """Calcola statistiche aggregate dai risultati."""
        if not self.requests:
            return
        
        self.total_requests = len(self.requests)
        self.successful_requests = sum(1 for r in self.requests if 200 <= r.status_code < 400)
        self.failed_requests = self.total_requests - self.successful_requests
        
        # Calcola statistiche sui tempi di risposta
        response_times = [r.response_time for r in self.requests if r.error is None]
        if response_times:
            self.min_response_time = min(response_times)
            self.max_response_time = max(response_times)
            self.avg_response_time = sum(response_times) / len(response_times)
            self.median_response_time = statistics.median(response_times)
            
            # Calcola percentili
            response_times.sort()
            self.p95_response_time = response_times[int(len(response_times) * 0.95)]
            self.p99_response_time = response_times[int(len(response_times) * 0.99)]
        
        # Calcola richieste al secondo
        if self.end_time and self.start_time:
            test_duration = self.end_time - self.start_time
            if test_duration > 0:
                self.requests_per_second = self.total_requests / test_duration
    
    def save_to_file(self, filename: str = None):
        """Salva i risultati del test su file."""
        if filename is None:
            # Genera nome file basato su data e ora
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            test_name = self.config.test_name or "load_test"
            filename = f"{test_name}_{timestamp}.json"
        
        # Assicurati che la directory esista
        os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
        
        # Converti in dizionario seriale
        results_dict = {
            "config": asdict(self.config),
            "summary": {
                "start_time": datetime.fromtimestamp(self.start_time).isoformat(),
                "end_time": datetime.fromtimestamp(self.end_time).isoformat() if self.end_time else None,
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "min_response_time": self.min_response_time,
                "max_response_time": self.max_response_time,
                "avg_response_time": self.avg_response_time,
                "median_response_time": self.median_response_time,
                "p95_response_time": self.p95_response_time,
                "p99_response_time": self.p99_response_time,
                "requests_per_second": self.requests_per_second
            },
            "errors": self.errors,
            "requests": [asdict(r) for r in self.requests[:1000]]  # Limita per dimensioni file
        }
        
        with open(filename, 'w') as f:
            json.dump(results_dict, f, indent=2)
        
        logger.info(f"Risultati salvati su {filename}")
        return filename

class LoadTester:
    """Esegue test di carico utilizzando aiohttp."""
    
    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.results = TestResults(config=config)
        self.session = None
        self.request_id_counter = 0
        self.active_users = 0
        self.stop_event = asyncio.Event()
    
    async def start_test(self) -> TestResults:
        """Avvia il test di carico."""
        logger.info(f"Avvio test di carico: {self.config.users} utenti, "
                   f"{self.config.requests_per_user} richieste per utente")
        
        self.results.start_time = time.time()
        
        # Crea connettore per sessione aiohttp
        connector = aiohttp.TCPConnector(
            limit=self.config.users * 2,  # Limite connessioni
            ssl=self.config.verify_ssl,
            ttl_dns_cache=300  # Cache DNS
        )
        
        # Timeout per le richieste
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
        
        # Crea sessione HTTP
        async with aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.config.headers
        ) as self.session:
            # Crea task per ogni utente
            user_tasks = []
            for user_id in range(self.config.users):
                # Calcola ritardo per il ramp-up graduale
                if self.config.ramp_up_time > 0:
                    delay = (user_id / self.config.users) * self.config.ramp_up_time
                else:
                    delay = 0
                
                # Crea e avvia task
                task = asyncio.create_task(
                    self.user_task(user_id, delay)
                )
                user_tasks.append(task)
            
            # Monitor del test
            monitor_task = asyncio.create_task(self.monitor_test())
            
            # Imposta timeout per durata totale del test
            end_timer = asyncio.create_task(self.end_timer())
            
            # Attendi il completamento di tutti i task
            await asyncio.gather(end_timer, monitor_task, *user_tasks, return_exceptions=True)
        
        # Completa i risultati
        self.results.end_time = time.time()
        self.results.calculate_statistics()
        
        logger.info(f"Test completato in {self.results.end_time - self.results.start_time:.2f} secondi")
        logger.info(f"Richieste totali: {self.results.total_requests}")
        logger.info(f"Richieste riuscite: {self.results.successful_requests}")
        logger.info(f"Richieste fallite: {self.results.failed_requests}")
        logger.info(f"Tempo medio di risposta: {self.results.avg_response_time:.2f} ms")
        logger.info(f"Richieste al secondo: {self.results.requests_per_second:.2f}")
        
        return self.results
    
    async def end_timer(self):
        """Timer per terminare il test dopo la durata configurata."""
        await asyncio.sleep(self.config.test_duration)
        logger.info(f"Durata test ({self.config.test_duration}s) raggiunta, arresto in corso...")
        self.stop_event.set()
    
    async def monitor_test(self):
        """Task di monitoraggio che fornisce aggiornamenti periodici sullo stato del test."""
        start_time = time.time()
        last_count = 0
        
        while not self.stop_event.is_set():
            await asyncio.sleep(5.0)  # Aggiorna ogni 5 secondi
            
            current_count = len(self.results.requests)
            elapsed = time.time() - start_time
            new_requests = current_count - last_count
            
            if elapsed > 0:
                rate = new_requests / 5.0  # Richieste negli ultimi 5 secondi
                logger.info(f"Stato: {current_count} richieste, {self.active_users} utenti attivi, "
                           f"{rate:.2f} richieste/sec (ultimi 5s)")
            
            last_count = current_count
    
    async def user_task(self, user_id: int, start_delay: float):
        """Simula un singolo utente che esegue richieste."""
        try:
            # Attendi il ritardo iniziale per il ramp-up
            if start_delay > 0:
                await asyncio.sleep(start_delay)
            
            # Incrementa contatore utenti attivi
            self.active_users += 1
            
            # Login se richiesto
            session_cookies = None
            if self.config.login_required:
                session_cookies = await self.perform_login(user_id)
            
            # Esegui richieste
            for req_num in range(self.config.requests_per_user):
                # Verifica se il test deve terminare
                if self.stop_event.is_set():
                    break
                
                # Scegli un endpoint casuale tra quelli configurati
                endpoint = random.choice(self.config.target_endpoints)
                
                # Esegui la richiesta
                await self.make_request(endpoint, user_id, req_num, cookies=session_cookies)
                
                # Tempo di riflessione tra le richieste
                think_time = random.uniform(
                    self.config.think_time_min,
                    self.config.think_time_max
                )
                await asyncio.sleep(think_time)
            
            # Test WebSocket se abilitato
            if self.config.use_websocket and not self.stop_event.is_set():
                await self.test_websocket(user_id, session_cookies)
            
        except Exception as e:
            logger.error(f"Errore nel task utente {user_id}: {str(e)}")
            self.results.errors.append(f"User {user_id}: {str(e)}")
        finally:
            # Decrementa contatore utenti attivi
            self.active_users -= 1
    
    async def perform_login(self, user_id: int) -> Dict[str, str]:
        """Esegue il login e restituisce i cookie di sessione."""
        # Se sono fornite credenziali multiple, usa quelle per l'utente corrente
        credentials = {}
        if isinstance(self.config.credentials, list) and len(self.config.credentials) > 0:
            # Seleziona le credenziali in base all'ID utente, ciclando se necessario
            cred_index = user_id % len(self.config.credentials)
            credentials = self.config.credentials[cred_index]
        else:
            # Usa le stesse credenziali per tutti
            credentials = self.config.credentials
        
        login_url = f"{self.config.base_url}{self.config.login_endpoint}"
        
        try:
            start_time = time.time()
            async with self.session.post(login_url, data=credentials) as response:
                response_time = (time.time() - start_time) * 1000  # in millisecondi
                
                # Incrementa contatore ID richieste
                self.request_id_counter += 1
                
                # Registra il risultato
                result = RequestResult(
                    endpoint=self.config.login_endpoint,
                    method="POST",
                    status_code=response.status,
                    response_time=response_time,
                    user_id=user_id,
                    request_id=self.request_id_counter,
                    request_data={"username": credentials.get("username", "[masked]")}
                )
                
                if response.status != 200:
                    result.error = f"Login fallito: HTTP {response.status}"
                    logger.warning(f"Login fallito per utente {user_id}: HTTP {response.status}")
                
                self.results.requests.append(result)
                
                # Estrai cookies per le richieste successive
                cookies = {}
                for cookie_name, cookie in response.cookies.items():
                    cookies[cookie_name] = cookie.value
                
                return cookies
                
        except Exception as e:
            logger.error(f"Errore durante il login per utente {user_id}: {str(e)}")
            # Registra errore e continua
            self.request_id_counter += 1
            result = RequestResult(
                endpoint=self.config.login_endpoint,
                method="POST",
                status_code=0,
                response_time=0,
                error=str(e),
                user_id=user_id,
                request_id=self.request_id_counter
            )
            self.results.requests.append(result)
            return {}
    
    async def make_request(self, endpoint: str, user_id: int, req_num: int, 
                          cookies: Dict[str, str] = None) -> RequestResult:
        """Esegue una singola richiesta HTTP."""
        url = f"{self.config.base_url}{endpoint}"
        method = "GET"  # Per semplicità usiamo solo GET, ma può essere esteso
        
        try:
            start_time = time.time()
            
            # Aggiunge cookies se presenti
            request_kwargs = {}
            if cookies:
                request_kwargs['cookies'] = cookies
            
            async with self.session.request(method, url, **request_kwargs) as response:
                response_time = (time.time() - start_time) * 1000  # in millisecondi
                
                # Incrementa contatore ID richieste
                self.request_id_counter += 1
                
                # Prova a leggere la risposta come JSON
                response_data = None
                try:
                    if response.content_type == 'application/json':
                        response_data = await response.json()
                except Exception:
                    # Ignora errori nel parsing JSON
                    pass
                
                # Crea oggetto risultato
                result = RequestResult(
                    endpoint=endpoint,
                    method=method,
                    status_code=response.status,
                    response_time=response_time,
                    user_id=user_id,
                    request_id=self.request_id_counter,
                    response_data=response_data
                )
                
                # Registra errori
                if response.status >= 400:
                    result.error = f"HTTP Error {response.status}"
                
                # Aggiungi ai risultati
                self.results.requests.append(result)
                return result
                
        except Exception as e:
            # Gestisci timeout e altri errori
            self.request_id_counter += 1
            result = RequestResult(
                endpoint=endpoint,
                method=method,
                status_code=0,
                response_time=0,
                error=str(e),
                user_id=user_id,
                request_id=self.request_id_counter
            )
            self.results.requests.append(result)
            return result
    
    async def test_websocket(self, user_id: int, cookies: Dict[str, str] = None):
        """Testa la connessione WebSocket."""
        ws_url = f"{self.config.base_url.replace('http', 'ws')}{self.config.websocket_endpoint}"
        
        try:
            start_time = time.time()
            
            # Prepara headers con cookie se necessario
            headers = {}
            if cookies:
                cookie_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                headers['Cookie'] = cookie_str
            
            # Connetti al WebSocket
            async with self.session.ws_connect(ws_url, headers=headers) as ws:
                logger.debug(f"WebSocket connesso per utente {user_id}")
                
                # Incrementa contatore ID richieste
                self.request_id_counter += 1
                
                # Inizia a ricevere messaggi in un task separato
                receive_task = asyncio.create_task(self.ws_receive_loop(ws, user_id))
                
                # Invia alcuni messaggi di ping
                for i in range(5):
                    if self.stop_event.is_set():
                        break
                    
                    await ws.send_json({
                        "type": "ping",
                        "data": {
                            "message": f"Ping {i} from user {user_id}",
                            "timestamp": time.time()
                        }
                    })
                    
                    await asyncio.sleep(1)
                
                # Attendi per la durata configurata o fino all'arresto del test
                ws_end_time = time.time() + self.config.websocket_duration
                while time.time() < ws_end_time and not self.stop_event.is_set():
                    await asyncio.sleep(1)
                
                # Termina il task di ricezione
                receive_task.cancel()
                try:
                    await receive_task
                except asyncio.CancelledError:
                    pass
                
                # Registra il risultato
                ws_duration = time.time() - start_time
                result = RequestResult(
                    endpoint=self.config.websocket_endpoint,
                    method="WS",
                    status_code=101,  # WebSocket successful upgrade
                    response_time=ws_duration * 1000,  # in millisecondi
                    user_id=user_id,
                    request_id=self.request_id_counter
                )
                self.results.requests.append(result)
                
        except Exception as e:
            logger.error(f"Errore WebSocket per utente {user_id}: {str(e)}")
            
            # Registra errore
            self.request_id_counter += 1
            result = RequestResult(
                endpoint=self.config.websocket_endpoint,
                method="WS",
                status_code=0,
                response_time=0,
                error=str(e),
                user_id=user_id,
                request_id=self.request_id_counter
            )
            self.results.requests.append(result)
    
    async def ws_receive_loop(self, ws, user_id: int):
        """Loop per ricevere messaggi WebSocket."""
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    logger.debug(f"Utente {user_id} ricevuto WebSocket: {msg.data[:100]}...")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    logger.error(f"Errore WebSocket per utente {user_id}: {ws.exception()}")
                    break
        except asyncio.CancelledError:
            # Normale durante la chiusura
            pass
        except Exception as e:
            logger.error(f"Errore nel loop di ricezione WebSocket per utente {user_id}: {str(e)}")

def generate_report(results: TestResults, output_file: str = None):
    """Genera un report HTML con grafici dai risultati del test."""
    if output_file is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        test_name = results.config.test_name or "load_test"
        output_file = f"{test_name}_{timestamp}_report.html"
    
    # Assicurati che la directory esista
    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    
    # Crea grafici usando matplotlib
    fig, axs = plt.subplots(2, 2, figsize=(12, 10))
    
    # 1. Grafico dei tempi di risposta nel tempo
    times = [r.timestamp - results.start_time for r in results.requests]
    response_times = [r.response_time for r in results.requests]
    success = [200 <= r.status_code < 400 for r in results.requests]
    
    axs[0, 0].scatter(times, response_times, c=['green' if s else 'red' for s in success], alpha=0.5)
    axs[0, 0].set_title('Tempi di Risposta')
    axs[0, 0].set_xlabel('Tempo (secondi)')
    axs[0, 0].set_ylabel('Tempo di Risposta (ms)')
    
    # 2. Istogramma dei tempi di risposta
    axs[0, 1].hist(response_times, bins=30, alpha=0.7, color='blue')
    axs[0, 1].set_title('Distribuzione Tempi di Risposta')
    axs[0, 1].set_xlabel('Tempo di Risposta (ms)')
    axs[0, 1].set_ylabel('Frequenza')
    
    # 3. Richieste al secondo nel tempo
    if times:
        max_time = max(times) + 1
        time_buckets = np.arange(0, max_time, 1.0)
        requests_per_second = []
        
        for i in range(len(time_buckets) - 1):
            start_time = time_buckets[i]
            end_time = time_buckets[i+1]
            
            count = sum(1 for t in times if start_time <= t < end_time)
            requests_per_second.append(count)
        
        axs[1, 0].plot(time_buckets[:-1], requests_per_second, 'b-')
        axs[1, 0].set_title('Richieste al Secondo')
        axs[1, 0].set_xlabel('Tempo (secondi)')
        axs[1, 0].set_ylabel('Richieste/Secondo')
    
    # 4. Percentuale di richieste per codice di stato
    status_codes = {}
    for r in results.requests:
        if r.status_code in status_codes:
            status_codes[r.status_code] += 1
        else:
            status_codes[r.status_code] = 1
    
    labels = list(status_codes.keys())
    sizes = list(status_codes.values())
    
    axs[1, 1].pie(sizes, labels=labels, autopct='%1.1f%%')
    axs[1, 1].set_title('Distribuzione Codici di Stato')
    
    plt.tight_layout()
    
    # Salva i grafici come immagine incorporabile
    import io
    import base64
    img_data = io.BytesIO()
    plt.savefig(img_data, format='png')
    img_data.seek(0)
    img_b64 = base64.b64encode(img_data.read()).decode()
    plt.close()
    
    # Crea report HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="it">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Report Test di Carico</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            h1, h2 {{ color: #333; }}
            .container {{ max-width: 1200px; margin: 0 auto; }}
            .summary {{ background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
            .charts {{ text-align: center; margin: 20px 0; }}
            table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .success {{ color: green; }}
            .error {{ color: red; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Report Test di Carico</h1>
            
            <div class="summary">
                <h2>Riepilogo</h2>
                <table>
                    <tr>
                        <th>Nome Test</th>
                        <td>{results.config.test_name or 'Test di Carico'}</td>
                    </tr>
                    <tr>
                        <th>URL Base</th>
                        <td>{results.config.base_url}</td>
                    </tr>
                    <tr>
                        <th>Durata Test</th>
                        <td>{results.end_time - results.start_time:.2f} secondi</td>
                    </tr>
                    <tr>
                        <th>Utenti Virtuali</th>
                        <td>{results.config.users}</td>
                    </tr>
                    <tr>
                        <th>Richieste Totali</th>
                        <td>{results.total_requests}</td>
                    </tr>
                    <tr>
                        <th>Richieste Riuscite</th>
                        <td class="success">{results.successful_requests} ({results.successful_requests / max(1, results.total_requests) * 100:.1f}%)</td>
                    </tr>
                    <tr>
                        <th>Richieste Fallite</th>
                        <td class="error">{results.failed_requests} ({results.failed_requests / max(1, results.total_requests) * 100:.1f}%)</td>
                    </tr>
                    <tr>
                        <th>Richieste al Secondo</th>
                        <td>{results.requests_per_second:.2f}</td>
                    </tr>
                    <tr>
                        <th>Tempo di Risposta Medio</th>
                        <td>{results.avg_response_time:.2f} ms</td>
                    </tr>
                    <tr>
                        <th>Tempo di Risposta Minimo</th>
                        <td>{results.min_response_time:.2f} ms</td>
                    </tr>
                    <tr>
                        <th>Tempo di Risposta Massimo</th>
                        <td>{results.max_response_time:.2f} ms</td>
                    </tr>
                    <tr>
                        <th>Tempo di Risposta Mediano</th>
                        <td>{results.median_response_time:.2f} ms</td>
                    </tr>
                    <tr>
                        <th>95° Percentile</th>
                        <td>{results.p95_response_time:.2f} ms</td>
                    </tr>
                    <tr>
                        <th>99° Percentile</th>
                        <td>{results.p99_response_time:.2f} ms</td>
                    </tr>
                </table>
            </div>
            
            <div class="charts">
                <h2>Grafici</h2>
                <img src="data:image/png;base64,{img_b64}" alt="Performance Charts" style="max-width: 100%;">
            </div>
            
            <div class="endpoints">
                <h2>Statistiche per Endpoint</h2>
                <table>
                    <tr>
                        <th>Endpoint</th>
                        <th>Richieste</th>
                        <th>Successi</th>
                        <th>Errori</th>
                        <th>Tempo Medio (ms)</th>
                        <th>Tempo Max (ms)</th>
                    </tr>
    """
    
    # Calcola statistiche per endpoint
    endpoints = {}
    for r in results.requests:
        if r.endpoint not in endpoints:
            endpoints[r.endpoint] = {
                'count': 0,
                'success': 0,
                'error': 0,
                'times': []
            }
        
        endpoints[r.endpoint]['count'] += 1
        if 200 <= r.status_code < 400:
            endpoints[r.endpoint]['success'] += 1
        else:
            endpoints[r.endpoint]['error'] += 1
        
        if r.error is None:
            endpoints[r.endpoint]['times'].append(r.response_time)
    
    for endpoint, data in sorted(endpoints.items()):
        avg_time = sum(data['times']) / max(1, len(data['times']))
        max_time = max(data['times']) if data['times'] else 0
        
        html += f"""
                    <tr>
                        <td>{endpoint}</td>
                        <td>{data['count']}</td>
                        <td class="success">{data['success']}</td>
                        <td class="error">{data['error']}</td>
                        <td>{avg_time:.2f}</td>
                        <td>{max_time:.2f}</td>
                    </tr>
        """
    
    html += """
                </table>
            </div>
            
            <div class="errors">
                <h2>Errori</h2>
    """
    
    if results.errors:
        html += """
                <table>
                    <tr>
                        <th>#</th>
                        <th>Errore</th>
                    </tr>
        """
        
        for i, error in enumerate(results.errors[:100]):  # Limita a 100 errori
            html += f"""
                    <tr>
                        <td>{i+1}</td>
                        <td class="error">{error}</td>
                    </tr>
            """
        
        html += """
                </table>
        """
        
        if len(results.errors) > 100:
            html += f"<p>Mostrati 100 errori su {len(results.errors)} totali.</p>"
    else:
        html += "<p>Nessun errore rilevato.</p>"
    
    html += """
            </div>
        </div>
    </body>
    </html>
    """
    
    # Scrivi il report
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    logger.info(f"Report generato in {output_file}")
    return output_file

async def run_load_test(config: LoadTestConfig) -> Tuple[TestResults, str, str]:
    """
    Esegue un test di carico completo e genera i report.
    
    Args:
        config: Configurazione del test
        
    Returns:
        Tuple[TestResults, str, str]: (risultati, percorso file json, percorso report html)
    """
    # Crea output_dir se non esiste
    os.makedirs(config.output_dir, exist_ok=True)
    
    # Esegui il test
    tester = LoadTester(config)
    results = await tester.start_test()
    
    # Genera timestamp per i file di output
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    test_name = config.test_name or "load_test"
    
    # Salva i risultati
    results_file = os.path.join(config.output_dir, f"{test_name}_{timestamp}.json")
    results.save_to_file(results_file)
    
    # Genera report
    report_file = os.path.join(config.output_dir, f"{test_name}_{timestamp}_report.html")
    generate_report(results, report_file)
    
    return results, results_file, report_file

def main():
    """Funzione principale per esecuzione da linea di comando."""
    parser = argparse.ArgumentParser(description='Esegui test di carico su M4Bot')
    parser.add_argument('--url', required=True, help='URL base dell\'applicazione')
    parser.add_argument('--users', type=int, default=100, help='Numero di utenti virtuali')
    parser.add_argument('--requests', type=int, default=10, help='Richieste per utente')
    parser.add_argument('--duration', type=int, default=60, help='Durata del test in secondi')
    parser.add_argument('--ramp-up', type=int, default=10, help='Tempo di ramp-up in secondi')
    parser.add_argument('--endpoints', nargs='+', default=['/'], help='Endpoint da testare')
    parser.add_argument('--login', action='store_true', help='Esegui login prima del test')
    parser.add_argument('--username', help='Username per il login')
    parser.add_argument('--password', help='Password per il login')
    parser.add_argument('--websocket', action='store_true', help='Testa anche WebSocket')
    parser.add_argument('--ws-endpoint', default='/ws', help='Endpoint WebSocket')
    parser.add_argument('--output', default='results', help='Directory output')
    parser.add_argument('--name', default='', help='Nome del test')
    
    args = parser.parse_args()
    
    # Configura il test
    config = LoadTestConfig(
        base_url=args.url,
        target_endpoints=args.endpoints,
        users=args.users,
        requests_per_user=args.requests,
        test_duration=args.duration,
        ramp_up_time=args.ramp_up,
        login_required=args.login,
        credentials={
            "username": args.username,
            "password": args.password
        } if args.login else {},
        use_websocket=args.websocket,
        websocket_endpoint=args.ws_endpoint,
        output_dir=args.output,
        test_name=args.name
    )
    
    # Esegui il test
    asyncio.run(run_load_test(config))

if __name__ == "__main__":
    main() 