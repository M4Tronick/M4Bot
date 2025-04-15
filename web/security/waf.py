"""
Web Application Firewall (WAF) per M4Bot

Questo modulo implementa un middleware di protezione per l'applicazione web,
fornendo difese contro attacchi comuni come SQL injection, XSS e CSRF.
"""

import re
import json
import logging
import ipaddress
import functools
from typing import Dict, List, Set, Tuple, Any, Optional, Union, Callable
from datetime import datetime, timedelta
from quart import request, Response, current_app, abort
from werkzeug.datastructures import Headers

# Configurazione logger
logger = logging.getLogger('m4bot.security.waf')

# Cache per le richieste (rate limiting)
request_cache = {}

# Lista di IP bannati
banned_ips = set()

# Regole di sicurezza predefinite
DEFAULT_RULES = {
    # XSS patterns
    'xss_patterns': [
        r'<script.*?>',
        r'<iframe.*?>',
        r'javascript:',
        r'onload=',
        r'onerror=',
        r'onclick=',
        r'onmouseover=',
        r'eval\s*\(',
        r'document\.cookie',
        r'document\.write',
    ],
    
    # SQL Injection patterns
    'sql_patterns': [
        r'(?i)(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER)\s+.*FROM',
        r'(?i)UNION\s+SELECT',
        r'(?i)(--|\#)$',
        r'(?i)\/\*.*\*\/',
        r"(?i)'\s*OR\s*'1'='1",
        r'(?i);\s*DROP\s+TABLE',
    ],
    
    # Traversal attacks
    'path_patterns': [
        r'\.\./',
        r'\.\.\\',
        r'~/',
        r'/etc/passwd',
        r'/bin/bash',
        r'cmd\.exe',
    ],
    
    # Blocca UA sospetti
    'blocked_ua': [
        r'sqlmap',
        r'nikto',
        r'nessus',
        r'dirbuster',
        r'nmap',
        r'burpsuite',
        r'w3af',
        r'masscan',
        r'wget',
        r'curl',
        r'testing',
    ],
    
    # Metodi HTTP consentiti
    'allowed_methods': ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS', 'HEAD'],
    
    # Dimensioni massime
    'max_url_length': 2000,
    'max_body_size': 10 * 1024 * 1024,  # 10 MB
    
    # Lista di IP consentiti per funzioni di amministrazione
    'admin_whitelist': [],
    
    # Rate limiting
    'rate_limit': {
        'enabled': True,
        'requests': 100,        # richieste
        'per_seconds': 60,      # per intervallo di tempo
        'block_duration': 300,  # durata blocco in secondi
    },
    
    # Geofencing (blocca paesi specifici)
    'geofencing': {
        'enabled': False,
        'mode': 'blacklist',     # blacklist o whitelist
        'countries': [],         # codici ISO a 2 caratteri
    },
}

class WAFMiddleware:
    """Middleware che implementa funzionalità WAF per Quart/Flask."""
    
    def __init__(self, app=None, config: Optional[Dict] = None):
        self.app = app
        self.config = DEFAULT_RULES.copy()
        if config:
            self.config.update(config)
        
        self.xss_regex = self._compile_patterns(self.config['xss_patterns'])
        self.sql_regex = self._compile_patterns(self.config['sql_patterns'])
        self.path_regex = self._compile_patterns(self.config['path_patterns'])
        self.ua_regex = self._compile_patterns(self.config['blocked_ua'])
        
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Inizializza il middleware con l'app."""
        self.app = app
        
        # Registra il middleware
        app.before_request(self.before_request)
        app.after_request(self.after_request)
        
        # Aggiorna il logging
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        
        # Aggiunge configurazioni all'app
        app.config.setdefault('WAF_ENABLED', True)
        app.config.setdefault('WAF_CONFIG', self.config)
        
        logger.info("WAF middleware inizializzato")
    
    def _compile_patterns(self, patterns: List[str]):
        """Compila i pattern regex per migliorare le prestazioni."""
        return [re.compile(pattern) for pattern in patterns]
    
    def check_rate_limit(self, client_ip: str) -> Tuple[bool, str]:
        """Verifica il rate limiting per un IP."""
        if not self.config['rate_limit']['enabled']:
            return True, ""
        
        now = datetime.now()
        rate_config = self.config['rate_limit']
        
        # Controlla se l'IP è già bannato
        if client_ip in banned_ips:
            return False, "IP temporaneamente bannato per eccesso di richieste"
        
        # Elimina richieste vecchie
        if client_ip in request_cache:
            request_cache[client_ip] = [
                ts for ts in request_cache[client_ip]
                if now - ts < timedelta(seconds=rate_config['per_seconds'])
            ]
        else:
            request_cache[client_ip] = []
        
        # Aggiungi la richiesta corrente
        request_cache[client_ip].append(now)
        
        # Verifica limite
        if len(request_cache[client_ip]) > rate_config['requests']:
            # Blocca l'IP temporaneamente
            banned_ips.add(client_ip)
            
            # Sblocco automatico dopo il tempo configurato
            @current_app.task
            async def unban_ip():
                await asyncio.sleep(rate_config['block_duration'])
                banned_ips.discard(client_ip)
            
            unban_ip()
            
            logger.warning(f"Rate limit superato per IP {client_ip}, bannato temporaneamente")
            return False, "Rate limit superato"
        
        return True, ""
    
    def check_method(self) -> Tuple[bool, str]:
        """Verifica il metodo HTTP."""
        method = request.method
        if method not in self.config['allowed_methods']:
            return False, f"Metodo HTTP non consentito: {method}"
        return True, ""
    
    def check_xss(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Verifica potenziali attacchi XSS."""
        # Converti i dati in una stringa JSON per ispezione
        data_str = json.dumps(data).lower()
        
        for pattern in self.xss_regex:
            if pattern.search(data_str):
                return False, "Potenziale attacco XSS rilevato"
        
        return True, ""
    
    def check_sqli(self, data: Dict[str, Any]) -> Tuple[bool, str]:
        """Verifica potenziali attacchi SQL Injection."""
        # Converti i dati in una stringa JSON per ispezione
        data_str = json.dumps(data).lower()
        
        for pattern in self.sql_regex:
            if pattern.search(data_str):
                return False, "Potenziale SQL Injection rilevato"
        
        return True, ""
    
    def check_path_traversal(self, path: str) -> Tuple[bool, str]:
        """Verifica attacchi di path traversal."""
        for pattern in self.path_regex:
            if pattern.search(path):
                return False, "Potenziale attacco di Path Traversal rilevato"
        
        return True, ""
    
    def check_user_agent(self, user_agent: str) -> Tuple[bool, str]:
        """Verifica User Agent sospetti."""
        if not user_agent:
            return False, "User-Agent mancante"
        
        for pattern in self.ua_regex:
            if pattern.search(user_agent.lower()):
                return False, "User-Agent sospetto rilevato"
        
        return True, ""
    
    def check_admin_access(self, client_ip: str, path: str) -> Tuple[bool, str]:
        """Verifica accesso a funzioni di amministrazione."""
        if not path.startswith('/admin'):
            return True, ""
        
        whitelist = self.config['admin_whitelist']
        if whitelist and client_ip not in whitelist:
            return False, "Accesso amministrativo non autorizzato"
        
        return True, ""
    
    def log_attack(self, client_ip: str, reason: str, data: Dict[str, Any]):
        """Registra informazioni su un potenziale attacco."""
        logger.warning(f"Attacco rilevato - IP: {client_ip}, Motivo: {reason}, Path: {request.path}, UA: {request.headers.get('User-Agent', 'N/A')}")
        
        # Qui potremmo integrare con un sistema di alerting
        # o registrare l'evento in un database
    
    async def before_request(self):
        """Hook eseguito prima di ogni richiesta."""
        if not current_app.config.get('WAF_ENABLED', True):
            return
        
        # Ottieni IP del client
        client_ip = request.remote_addr
        
        # Controlla dimensione URL
        if len(request.url) > self.config['max_url_length']:
            self.log_attack(client_ip, "URL troppo lungo", {})
            return abort(414)
        
        # Controlla rate limit
        rate_allowed, rate_message = self.check_rate_limit(client_ip)
        if not rate_allowed:
            self.log_attack(client_ip, rate_message, {})
            return abort(429)
        
        # Controlla metodo HTTP
        method_allowed, method_message = self.check_method()
        if not method_allowed:
            self.log_attack(client_ip, method_message, {})
            return abort(405)
        
        # Controlla User-Agent
        ua_allowed, ua_message = self.check_user_agent(request.headers.get('User-Agent', ''))
        if not ua_allowed:
            self.log_attack(client_ip, ua_message, {})
            return abort(403)
        
        # Controlla accesso admin
        admin_allowed, admin_message = self.check_admin_access(client_ip, request.path)
        if not admin_allowed:
            self.log_attack(client_ip, admin_message, {})
            return abort(403)
        
        # Controlla path traversal
        path_allowed, path_message = self.check_path_traversal(request.path)
        if not path_allowed:
            self.log_attack(client_ip, path_message, {})
            return abort(403)
        
        # Controlla parametri della query
        for key, value in request.args.items():
            # Controlla XSS
            xss_allowed, xss_message = self.check_xss({key: value})
            if not xss_allowed:
                self.log_attack(client_ip, xss_message, {key: value})
                return abort(403)
            
            # Controlla SQLi
            sql_allowed, sql_message = self.check_sqli({key: value})
            if not sql_allowed:
                self.log_attack(client_ip, sql_message, {key: value})
                return abort(403)
        
        # Se è una richiesta con body, verifica anche il body
        if request.method in ['POST', 'PUT'] and request.is_json:
            # Controlla dimensione del body
            content_length = request.content_length or 0
            if content_length > self.config['max_body_size']:
                self.log_attack(client_ip, "Body troppo grande", {})
                return abort(413)
            
            try:
                # Per verificare il body, dobbiamo leggerlo e poi ripristinarlo
                # Questo è un po' complicato con Quart, ma è possibile
                body_data = await request.get_json()
                
                # Controlla XSS
                xss_allowed, xss_message = self.check_xss(body_data)
                if not xss_allowed:
                    self.log_attack(client_ip, xss_message, body_data)
                    return abort(403)
                
                # Controlla SQLi
                sql_allowed, sql_message = self.check_sqli(body_data)
                if not sql_allowed:
                    self.log_attack(client_ip, sql_message, body_data)
                    return abort(403)
            except Exception as e:
                logger.warning(f"Errore nell'analisi del JSON: {str(e)}")
                return abort(400)
    
    def after_request(self, response: Response) -> Response:
        """Hook eseguito dopo ogni richiesta."""
        if not current_app.config.get('WAF_ENABLED', True):
            return response
        
        # Aggiungi header di sicurezza
        response.headers.update({
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'SAMEORIGIN',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Content-Security-Policy': "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' https://cdn.jsdelivr.net; img-src 'self' data:; font-src 'self' https://cdn.jsdelivr.net; connect-src 'self'",
            'Referrer-Policy': 'strict-origin-when-cross-origin',
            'Permissions-Policy': 'accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()',
        })
        
        return response

def enable_waf(app, config=None):
    """Helper per attivare il WAF nell'app."""
    waf = WAFMiddleware(app, config)
    return waf

# Funzione per proteggere specifiche route
def protect_route(min_seconds_between=1, 
                  max_requests_per_minute=60, 
                  additional_checks=None):
    """
    Decorator per proteggere specifiche route con regole WAF personalizzate.
    
    Args:
        min_seconds_between: Tempo minimo tra richieste (anti-brute force)
        max_requests_per_minute: Richieste massime al minuto
        additional_checks: Funzione per controlli aggiuntivi
    """
    last_request_time = {}
    request_count = {}
    
    def decorator(f):
        @functools.wraps(f)
        async def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            now = datetime.now()
            
            # Controllo tempo minimo tra richieste
            if client_ip in last_request_time:
                time_diff = (now - last_request_time[client_ip]).total_seconds()
                if time_diff < min_seconds_between:
                    logger.warning(f"Richieste troppo frequenti da {client_ip} - {time_diff}s")
                    return abort(429)
            
            # Aggiorna timestamp ultima richiesta
            last_request_time[client_ip] = now
            
            # Controllo richieste per minuto
            minute_key = f"{client_ip}:{now.strftime('%Y-%m-%d %H:%M')}"
            request_count[minute_key] = request_count.get(minute_key, 0) + 1
            
            if request_count[minute_key] > max_requests_per_minute:
                logger.warning(f"Troppe richieste da {client_ip} - {request_count[minute_key]}")
                return abort(429)
            
            # Controlli aggiuntivi
            if additional_checks:
                result = additional_checks(request)
                if result is not True:
                    return result
            
            # Esegui la funzione originale
            return await f(*args, **kwargs)
        
        return decorated_function
    
    return decorator 