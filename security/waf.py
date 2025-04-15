#!/usr/bin/env python3
"""
M4Bot - Web Application Firewall (WAF)

Questo modulo implementa un sistema di protezione perimetrale per 
l'applicazione web contro attacchi comuni come:
- SQL Injection
- Cross-Site Scripting (XSS)
- Cross-Site Request Forgery (CSRF)
- Command Injection
- Path Traversal

Implementa anche limitazione di frequenza (rate limiting), 
filtraggio di IP malevoli e monitoraggio avanzato degli attacchi.
"""

import re
import time
import ipaddress
import logging
import os
import json
import hashlib
from typing import Dict, List, Set, Tuple, Optional, Any, Union, Callable
from functools import wraps
from datetime import datetime, timedelta

import aiohttp
import asyncio
from quart import request, abort, g, current_app, Response
from quart.ctx import _AppCtxGlobals

# Configurazione del logging
logger = logging.getLogger('m4bot.security.waf')

# Database in-memory degli IP bloccati e delle sessioni sospette 
# (in produzione usare Redis o altro database persistente)
blocked_ips: Set[str] = set()
ip_request_count: Dict[str, Dict[str, int]] = {}  # {ip: {timestamp: count}}
suspicious_activity: Dict[str, List[Dict[str, Any]]] = {}  # {ip: [{timestamp, activity, severity}]}
temporary_blocks: Dict[str, datetime] = {}  # {ip: expiry_time}
whitelist_ips: Set[str] = set()

# Regole di sicurezza
xss_patterns = [
    r'<script.*?>',
    r'javascript:',
    r'onerror\s*=',
    r'onclick\s*=',
    r'onload\s*=',
    r'eval\s*\(',
    r'document\.cookie',
    r'document\.location',
    r'alert\s*\('
]

sqli_patterns = [
    r'(?i)(SELECT|INSERT|UPDATE|DELETE|DROP|UNION).*FROM',
    r'(?i)(ALTER|CREATE|TRUNCATE) TABLE',
    r'--',
    r'(?i)\/\*.*\*\/',
    r'(?i)EXEC\s*\(',
    r'(?i)INTO\s+(OUTFILE|DUMPFILE)',
    r'(?i)BENCHMARK\s*\(',
    r'(?i)SLEEP\s*\('
]

path_traversal_patterns = [
    r'\.\./',
    r'\.\.\\',
    r'%2e%2e%2f',
    r'%252e%252e%252f',
    r'/etc/passwd',
    r'C:\\Windows\\system32',
    r'cmd\.exe',
    r'command\.com'
]

command_injection_patterns = [
    r'(?i);\s*(ping|ls|dir|cat|rm|wget|curl|bash|cmd)',
    r'(?i)\|\s*(ping|ls|dir|cat|rm|wget|curl|bash|cmd)',
    r'(?i)`.*`',
    r'(?i)\$\(.*\)',
    r'(?i)&&\s*\w+'
]

# Configurazione predefinita
default_config = {
    'enabled': True,
    'log_only_mode': False,  # In modalità log-only registra ma non blocca
    'rate_limits': {
        'global': 1000,      # Richieste massime al minuto globalmente
        'per_ip': 100,       # Richieste massime al minuto per IP
        'per_endpoint': {    # Richieste massime al minuto per endpoint specifico
            '/api/': 200,
            '/login': 10,
            '/register': 5,
            '/reset_password': 5
        }
    },
    'block_duration': 30,    # Durata blocco temporaneo in minuti
    'max_violations': 5,     # Numero massimo di violazioni prima del blocco
    'scan_request': {
        'headers': True,     # Analizza headers
        'cookies': True,     # Analizza cookies
        'query': True,       # Analizza parametri query string
        'body': True,        # Analizza body
        'url': True          # Analizza URL
    },
    'rules': {
        'xss': True,         # Controllo XSS
        'sqli': True,        # Controllo SQL Injection
        'csrf': True,        # Protezione CSRF
        'path_traversal': True, # Controllo Path Traversal
        'command_injection': True, # Controllo Command Injection
        'ip_blacklist': True, # Blocco IP da blacklist
        'content_type': True # Verifica coerenza Content-Type
    },
    'whitelist': {
        'ips': [],           # IP da non controllare mai (es. admin)
        'paths': ['/static/', '/favicon.ico'], # Percorsi da escludere
        'endpoints': []      # Endpoint specifici da escludere
    },
    'headers': {
        'security': True,    # Aggiunge header di sicurezza
        'server': 'M4Bot-Server' # Maschera versione server
    }
}

# Carica configurazione da file
def load_config() -> Dict[str, Any]:
    """Carica la configurazione del WAF"""
    config_path = os.path.join(os.path.dirname(__file__), 'waf_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                logger.info("Configurazione WAF caricata con successo")
                return config
        except Exception as e:
            logger.error(f"Errore nel caricamento configurazione WAF: {e}")
    
    logger.warning("Utilizzando la configurazione WAF predefinita")
    return default_config

# Utilità per rilevare i pattern
def detect_patterns(text: str, patterns: List[str]) -> Tuple[bool, Optional[str]]:
    """Verifica se il testo contiene uno dei pattern specificati"""
    if text is None:
        return False, None
        
    for pattern in patterns:
        matches = re.search(pattern, text)
        if matches:
            return True, matches.group(0)
    return False, None

# Ispeziona la richiesta per attacchi potenziali
async def inspect_request(cfg: Dict[str, Any]) -> Tuple[bool, str, int]:
    """
    Analizza la richiesta in arrivo per identificare potenziali attacchi
    
    Returns:
        Tuple[bool, str, int]: (è_sicura, messaggio, livello_severità)
    """
    # Prepara i dati della richiesta
    data_to_check = {}
    ip = request.remote_addr
    
    # Controlla se è nella whitelist
    if ip in whitelist_ips:
        return True, "IP in whitelist", 0
    
    # Verifica blacklist e blocchi temporanei
    if ip in blocked_ips:
        return False, "IP in blacklist permanente", 10
    
    if ip in temporary_blocks and temporary_blocks[ip] > datetime.now():
        remaining = int((temporary_blocks[ip] - datetime.now()).total_seconds() / 60)
        return False, f"IP temporaneamente bloccato per altri {remaining} minuti", 8
    
    # Controlla se il percorso è escluso
    path = request.path
    for wl_path in cfg['whitelist']['paths']:
        if path.startswith(wl_path):
            return True, f"Percorso in whitelist: {wl_path}", 0
    
    # Raccolta dati da analizzare
    if cfg['scan_request']['headers']:
        data_to_check['headers'] = str(dict(request.headers))
    
    if cfg['scan_request']['url']:
        data_to_check['url'] = request.url
    
    if cfg['scan_request']['query'] and request.args:
        data_to_check['query'] = str(dict(request.args))
    
    # Analisi corpo richiesta per metodi POST, PUT, etc.
    if cfg['scan_request']['body'] and request.method in ['POST', 'PUT', 'PATCH']:
        try:
            if request.content_type and 'application/json' in request.content_type:
                # Lettura del corpo JSON
                try:
                    body_data = await request.get_json()
                    data_to_check['body'] = json.dumps(body_data)
                except:
                    # Se non possiamo analizzare come JSON, proviamo come testo
                    body_data = await request.get_data(as_text=True)
                    data_to_check['body'] = body_data
            elif request.content_type and 'application/x-www-form-urlencoded' in request.content_type:
                # Lettura del corpo form
                form_data = await request.form
                data_to_check['body'] = str(dict(form_data))
            else:
                # Altri content-type, prova a leggere come testo
                body_data = await request.get_data(as_text=True)
                if body_data:
                    data_to_check['body'] = body_data
        except Exception as e:
            logger.warning(f"Impossibile analizzare il corpo della richiesta: {e}")
    
    # Controllo Cookie
    if cfg['scan_request']['cookies'] and request.cookies:
        data_to_check['cookies'] = str(dict(request.cookies))
    
    # Applicazione dei controlli
    violations = []
    severity = 0
    
    # Controlla XSS
    if cfg['rules']['xss']:
        for key, value in data_to_check.items():
            detected, match = detect_patterns(value, xss_patterns)
            if detected:
                violations.append(f"Potenziale XSS rilevato in {key}: {match}")
                severity = max(severity, 7)
    
    # Controlla SQLi
    if cfg['rules']['sqli']:
        for key, value in data_to_check.items():
            detected, match = detect_patterns(value, sqli_patterns)
            if detected:
                violations.append(f"Potenziale SQL Injection rilevato in {key}: {match}")
                severity = max(severity, 9)
    
    # Controlla Path Traversal
    if cfg['rules']['path_traversal']:
        for key, value in data_to_check.items():
            detected, match = detect_patterns(value, path_traversal_patterns)
            if detected:
                violations.append(f"Potenziale Path Traversal rilevato in {key}: {match}")
                severity = max(severity, 8)
    
    # Controlla Command Injection
    if cfg['rules']['command_injection']:
        for key, value in data_to_check.items():
            detected, match = detect_patterns(value, command_injection_patterns)
            if detected:
                violations.append(f"Potenziale Command Injection rilevato in {key}: {match}")
                severity = max(severity, 9)
    
    # Controllo CSRF
    if cfg['rules']['csrf'] and request.method in ['POST', 'PUT', 'DELETE', 'PATCH']:
        csrf_token = request.headers.get('X-CSRF-Token')
        session_csrf = g.get('csrf_token') if hasattr(g, 'csrf_token') else None
        
        if not csrf_token or (session_csrf and csrf_token != session_csrf):
            violations.append("Token CSRF mancante o non valido")
            severity = max(severity, 6)
    
    # Controllo Content-Type
    if cfg['rules']['content_type'] and request.method in ['POST', 'PUT', 'PATCH']:
        content_type = request.headers.get('Content-Type', '')
        if not content_type:
            violations.append("Content-Type header mancante per richiesta con corpo")
            severity = max(severity, 4)
    
    # Determina il risultato finale
    if violations:
        violation_msg = "; ".join(violations)
        # Registra la violazione per questo IP
        if ip not in suspicious_activity:
            suspicious_activity[ip] = []
        
        suspicious_activity[ip].append({
            'timestamp': datetime.now().isoformat(),
            'activity': violation_msg,
            'severity': severity,
            'path': request.path,
            'method': request.method
        })
        
        # Verifica se l'IP dovrebbe essere bloccato
        ip_violations = len(suspicious_activity.get(ip, []))
        if ip_violations >= cfg['max_violations']:
            temporary_blocks[ip] = datetime.now() + timedelta(minutes=cfg['block_duration'])
            logger.warning(f"IP {ip} bloccato temporaneamente per {cfg['block_duration']} minuti dopo {ip_violations} violazioni")
        
        return False, violation_msg, severity
    
    return True, "Nessuna violazione rilevata", 0

# Gestione del rate limiting
def check_rate_limits(cfg: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Controlla i limiti di frequenza per le richieste
    
    Returns:
        Tuple[bool, str]: (entro_limiti, messaggio)
    """
    ip = request.remote_addr
    current_time = int(time.time())
    minute_timestamp = current_time - (current_time % 60)  # Arrotonda al minuto
    
    # Inizializza contatore per questo IP se non esiste
    if ip not in ip_request_count:
        ip_request_count[ip] = {}
    
    # Pulisci contatori vecchi (mantieni solo l'ultimo minuto)
    ip_request_count[ip] = {ts: count for ts, count in ip_request_count[ip].items() 
                          if ts >= minute_timestamp - 60}
    
    # Incrementa contatore per questo minuto
    if minute_timestamp not in ip_request_count[ip]:
        ip_request_count[ip][minute_timestamp] = 0
    ip_request_count[ip][minute_timestamp] += 1
    
    # Controlla limiti per IP
    current_ip_rate = sum(ip_request_count[ip].values())
    if current_ip_rate > cfg['rate_limits']['per_ip']:
        return False, f"Rate limit per IP superato: {current_ip_rate}/{cfg['rate_limits']['per_ip']} richieste"
    
    # Controlla limiti per endpoint specifici
    path = request.path
    for endpoint, limit in cfg['rate_limits']['per_endpoint'].items():
        if path.startswith(endpoint):
            # Contiamo solo le richieste per questo endpoint
            endpoint_requests = 0
            # Qui potremmo implementare un conteggio più preciso per endpoint
            # Per ora utilizziamo lo stesso contatore dell'IP come approssimazione
            endpoint_requests = current_ip_rate
            
            if endpoint_requests > limit:
                return False, f"Rate limit per endpoint {endpoint} superato: {endpoint_requests}/{limit} richieste"
    
    # Tutti i controlli superati
    return True, "Rate limits rispettati"

# Aggiunta di header di sicurezza
def add_security_headers(response: Response) -> Response:
    """Aggiunge header di sicurezza alla risposta HTTP"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' cdn.jsdelivr.net; style-src 'self' cdn.jsdelivr.net; img-src 'self' data:; font-src 'self' cdn.jsdelivr.net;"
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    
    # Rimuovi header che potrebbero rivelare informazioni
    if 'Server' in response.headers:
        response.headers['Server'] = 'M4Bot-Server'
    if 'X-Powered-By' in response.headers:
        del response.headers['X-Powered-By']
        
    return response

# Sistema di logging e monitoraggio
def log_security_event(severity: int, message: str, details: Dict[str, Any] = None):
    """Registra un evento di sicurezza con la severità specificata"""
    log_methods = {
        0: logger.debug,
        1: logger.debug,
        2: logger.debug,
        3: logger.info,
        4: logger.info,
        5: logger.warning,
        6: logger.warning,
        7: logger.warning,
        8: logger.error,
        9: logger.error,
        10: logger.critical
    }
    
    log_func = log_methods.get(severity, logger.info)
    if details:
        log_func(f"{message} - {json.dumps(details)}")
    else:
        log_func(message)
    
    # Qui si potrebbe anche inviare l'evento a un sistema di monitoraggio esterno
    # come Datadog, New Relic, o un SIEM

# Funzione principale del WAF
async def waf_middleware():
    """Middleware principale del WAF che esegue tutti i controlli"""
    # Carica configurazione
    cfg = load_config()
    
    # Skip se WAF disabilitato
    if not cfg['enabled']:
        return
    
    # Skip per path in whitelist
    path = request.path
    for wl_path in cfg['whitelist']['paths']:
        if path.startswith(wl_path):
            return
    
    # Inizializza whitelist IP se non già fatto
    global whitelist_ips
    if not whitelist_ips and cfg['whitelist']['ips']:
        whitelist_ips = set(cfg['whitelist']['ips'])
    
    # Controlla rate limiting
    within_limits, rate_msg = check_rate_limits(cfg)
    if not within_limits:
        log_security_event(6, f"Rate limit exceeded: {rate_msg}", {
            'ip': request.remote_addr,
            'path': request.path,
            'method': request.method
        })
        
        if not cfg['log_only_mode']:
            # In modalità produzione, blocca la richiesta
            abort(429, rate_msg)
    
    # Ispeziona la richiesta per rilevare attacchi
    is_safe, message, severity = await inspect_request(cfg)
    if not is_safe:
        log_security_event(severity, f"Security violation: {message}", {
            'ip': request.remote_addr,
            'path': request.path,
            'method': request.method,
            'headers': dict(request.headers)
        })
        
        if not cfg['log_only_mode'] and severity >= 5:
            # In modalità produzione e con severità sufficiente, blocca la richiesta
            abort(403, "Richiesta bloccata per motivi di sicurezza")

# Dopo-middleware per aggiungere header di sicurezza
def after_request_middleware(response: Response) -> Response:
    """Middleware da eseguire dopo ogni richiesta per aggiungere header di sicurezza"""
    cfg = load_config()
    
    if cfg['enabled'] and cfg['headers']['security']:
        return add_security_headers(response)
    
    return response

# Decoratore per proteggere specifiche route
def protect_route(min_severity: int = 5, rate_limit: int = None):
    """
    Decoratore per proteggere una specifica route con il WAF
    e impostare limiti personalizzati
    
    Args:
        min_severity: Severità minima per bloccare la richiesta (0-10)
        rate_limit: Limite di richieste al minuto per questa route
    """
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            # Carica configurazione
            cfg = load_config()
            
            if cfg['enabled']:
                # Controllo rate limit specifico
                if rate_limit is not None:
                    ip = request.remote_addr
                    current_time = int(time.time())
                    minute_timestamp = current_time - (current_time % 60)
                    
                    if ip not in ip_request_count:
                        ip_request_count[ip] = {}
                    
                    if minute_timestamp not in ip_request_count[ip]:
                        ip_request_count[ip][minute_timestamp] = 0
                    
                    ip_request_count[ip][minute_timestamp] += 1
                    
                    current_route_rate = ip_request_count[ip][minute_timestamp]
                    if current_route_rate > rate_limit:
                        log_security_event(6, f"Route rate limit exceeded: {current_route_rate}/{rate_limit}", {
                            'ip': request.remote_addr,
                            'path': request.path
                        })
                        
                        if not cfg['log_only_mode']:
                            abort(429, "Troppe richieste per questa risorsa")
                
                # Ispeziona la richiesta
                is_safe, message, severity = await inspect_request(cfg)
                
                if not is_safe and severity >= min_severity:
                    log_security_event(severity, f"Protected route violation: {message}", {
                        'ip': request.remote_addr,
                        'path': request.path
                    })
                    
                    if not cfg['log_only_mode']:
                        abort(403, "Accesso negato")
            
            # Continua con la route originale
            return await f(*args, **kwargs)
        return decorated_function
    return decorator

# Inizializzazione del WAF
def init_waf(app):
    """Inizializza il WAF nell'applicazione Flask/Quart"""
    # Registra il middleware
    @app.before_request
    async def before_request():
        await waf_middleware()
    
    # Registra l'after-middleware
    @app.after_request
    def after_request(response):
        return after_request_middleware(response)
    
    # Logga inizializzazione
    logger.info("Web Application Firewall (WAF) inizializzato")
    
    return app

# Funzioni amministrative

def block_ip(ip: str, permanent: bool = False, duration_minutes: int = 30):
    """Blocca un indirizzo IP"""
    try:
        # Valida l'IP
        ipaddress.ip_address(ip)
        
        if permanent:
            blocked_ips.add(ip)
            log_security_event(8, f"IP {ip} bloccato permanentemente")
        else:
            temporary_blocks[ip] = datetime.now() + timedelta(minutes=duration_minutes)
            log_security_event(6, f"IP {ip} bloccato temporaneamente per {duration_minutes} minuti")
        
        return True, f"IP {ip} bloccato"
    except ValueError:
        return False, f"Indirizzo IP non valido: {ip}"

def unblock_ip(ip: str):
    """Sblocca un indirizzo IP"""
    try:
        # Valida l'IP
        ipaddress.ip_address(ip)
        
        if ip in blocked_ips:
            blocked_ips.remove(ip)
            log_security_event(5, f"IP {ip} rimosso dalla blacklist permanente")
        
        if ip in temporary_blocks:
            del temporary_blocks[ip]
            log_security_event(5, f"IP {ip} rimosso dai blocchi temporanei")
        
        return True, f"IP {ip} sbloccato"
    except ValueError:
        return False, f"Indirizzo IP non valido: {ip}"

def whitelist_ip(ip: str):
    """Aggiunge un IP alla whitelist"""
    try:
        # Valida l'IP
        ipaddress.ip_address(ip)
        
        whitelist_ips.add(ip)
        log_security_event(5, f"IP {ip} aggiunto alla whitelist")
        
        return True, f"IP {ip} aggiunto alla whitelist"
    except ValueError:
        return False, f"Indirizzo IP non valido: {ip}"

def get_security_stats():
    """Restituisce statistiche sulla sicurezza"""
    stats = {
        'blocked_ips': len(blocked_ips),
        'temporary_blocks': len(temporary_blocks),
        'whitelisted_ips': len(whitelist_ips),
        'recent_violations': sum(len(activities) for activities in suspicious_activity.values()),
        'top_offenders': []
    }
    
    # Ottieni i 10 IP con più violazioni
    ip_violations = [(ip, len(activities)) for ip, activities in suspicious_activity.items()]
    ip_violations.sort(key=lambda x: x[1], reverse=True)
    stats['top_offenders'] = ip_violations[:10]
    
    return stats

def purge_expired_data():
    """Pulisce dati scaduti da blocchi temporanei e attività sospette"""
    now = datetime.now()
    
    # Rimuovi blocchi temporanei scaduti
    expired_blocks = [ip for ip, expires in temporary_blocks.items() if expires < now]
    for ip in expired_blocks:
        del temporary_blocks[ip]
    
    # Rimuovi dati di attività sospette più vecchi di 7 giorni
    cutoff = now - timedelta(days=7)
    for ip in list(suspicious_activity.keys()):
        suspicious_activity[ip] = [
            activity for activity in suspicious_activity[ip] 
            if datetime.fromisoformat(activity['timestamp']) > cutoff
        ]
        
        # Rimuovi l'IP se non ha più attività
        if not suspicious_activity[ip]:
            del suspicious_activity[ip]
    
    # Rimuovi contatori di richieste vecchi
    for ip in list(ip_request_count.keys()):
        current_time = int(time.time())
        ip_request_count[ip] = {
            ts: count for ts, count in ip_request_count[ip].items() 
            if ts >= current_time - 300  # Mantieni solo ultimi 5 minuti
        }
        
        # Rimuovi l'IP se non ha più contatori
        if not ip_request_count[ip]:
            del ip_request_count[ip]
    
    return {
        'expired_blocks_removed': len(expired_blocks),
        'ips_tracked': len(suspicious_activity),
        'request_counters': len(ip_request_count)
    }

# Esecuzione pulizia periodica
async def periodic_cleanup():
    """Esegue la pulizia periodica dei dati di sicurezza"""
    while True:
        purge_results = purge_expired_data()
        logger.debug(f"Pulizia periodica WAF completata: {purge_results}")
        await asyncio.sleep(300)  # Esegui ogni 5 minuti

def start_cleanup_task():
    """Avvia il task di pulizia in background"""
    asyncio.create_task(periodic_cleanup())

# Classe principale per il WAF
class WAFManager:
    """Classe per gestire il Web Application Firewall"""
    
    @staticmethod
    def init_app(app):
        """Inizializza il WAF nell'applicazione"""
        return init_waf(app)
    
    @staticmethod
    def protect(min_severity=5, rate_limit=None):
        """Decoratore per proteggere una route"""
        return protect_route(min_severity, rate_limit)
    
    @staticmethod
    def block_ip(ip, permanent=False, duration=30):
        """Blocca un IP"""
        return block_ip(ip, permanent, duration)
    
    @staticmethod
    def unblock_ip(ip):
        """Sblocca un IP"""
        return unblock_ip(ip)
    
    @staticmethod
    def whitelist_ip(ip):
        """Aggiunge un IP alla whitelist"""
        return whitelist_ip(ip)
    
    @staticmethod
    def get_stats():
        """Ottiene statistiche sulla sicurezza"""
        return get_security_stats()
    
    @staticmethod
    def cleanup():
        """Esegue la pulizia dei dati scaduti"""
        return purge_expired_data()
    
    @staticmethod
    def start_background_tasks():
        """Avvia i task in background"""
        start_cleanup_task()

# Inizializzazione al caricamento del modulo
def initialize():
    """Inizializza il WAF al caricamento del modulo"""
    logger.info("M4Bot Web Application Firewall (WAF) - Modulo caricato")

# Esegui l'inizializzazione
initialize() 