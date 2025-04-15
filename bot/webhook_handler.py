import os
import json
import logging
import asyncio
import aiohttp
import hmac
import hashlib
import base64
import time
import jwt
import re
import ipaddress
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/webhooks/webhook_handler.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("WebhookHandler")

class WebhookHandler:
    """Gestore di webhook personalizzati per M4Bot"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Inizializza il gestore di webhook
        
        Args:
            config: Configurazione del gestore
        """
        self.config = config
        self.webhooks = config.get("webhooks", [])
        self.default_headers = config.get("default_headers", {})
        self.max_retries = config.get("webhook_max_retries", 3)
        self.retry_delay = config.get("webhook_retry_delay", 5)
        self.timeout = config.get("webhook_timeout", 10)
        
        # Configurazione sicurezza
        self.security_config = config.get("security", {})
        
        # Whitelist IP (se vuoto, accetta tutte le IP)
        self.ip_whitelist = self.security_config.get("ip_whitelist", [])
        # Blacklist IP
        self.ip_blacklist = self.security_config.get("ip_blacklist", [])
        # Limite di richieste
        self.rate_limit = self.security_config.get("rate_limit", {
            "enabled": True,
            "max_requests": 100,      # Richieste massime
            "time_window": 60,        # Finestra temporale in secondi
            "block_duration": 300     # Durata del blocco in secondi
        })
        
        # Cache per rate limiting
        self.rate_limit_cache = {}
        # Cache dei webhook con errori
        self.error_cache = {}
        # Cache per verifica delle firme (anti-replay)
        self.signature_cache = {}
        
        # Crea le directory necessarie
        os.makedirs("logs/webhooks", exist_ok=True)
        
        logger.info(f"Gestore di webhook inizializzato ({len(self.webhooks)} webhook configurati)")
    
    async def receive_webhook(self, webhook_id: str, source_ip: str, headers: Dict[str, str], 
                             request_data: Any) -> Dict[str, Any]:
        """
        Riceve e processa un webhook in arrivo
        
        Args:
            webhook_id: ID del webhook
            source_ip: IP di origine della richiesta
            headers: Headers della richiesta
            request_data: Dati della richiesta
            
        Returns:
            Dict: Risultato dell'elaborazione
        """
        # Controlla se l'IP è nella blacklist
        if self._is_ip_blacklisted(source_ip):
            logger.warning(f"Richiesta webhook rifiutata: IP {source_ip} nella blacklist")
            return {
                "status": "error",
                "error": "ip_blacklisted",
                "message": "IP non autorizzato"
            }
        
        # Controlla se la whitelist è attiva e l'IP è autorizzato
        if self.ip_whitelist and not self._is_ip_whitelisted(source_ip):
            logger.warning(f"Richiesta webhook rifiutata: IP {source_ip} non nella whitelist")
            return {
                "status": "error",
                "error": "ip_not_whitelisted",
                "message": "IP non nella whitelist"
            }
        
        # Controllo rate limiting
        if self.rate_limit.get("enabled", True):
            if self._is_rate_limited(source_ip):
                logger.warning(f"Richiesta webhook rifiutata: Rate limit superato per IP {source_ip}")
                return {
                    "status": "error",
                    "error": "rate_limit_exceeded",
                    "message": "Troppe richieste, riprova più tardi"
                }
            self._track_request(source_ip)
        
        # Trova il webhook corrispondente
        webhook = next((w for w in self.webhooks if w.get("id") == webhook_id), None)
        
        if not webhook:
            logger.error(f"Webhook ID '{webhook_id}' non trovato")
            return {
                "status": "error",
                "error": "webhook_not_found",
                "message": "Webhook non trovato"
            }
        
        # Verifica firma se richiesta
        if webhook.get("verify_signature", False):
            signature_status = self._verify_webhook_signature(webhook, headers, request_data)
            if signature_status != "valid":
                logger.warning(f"Firma webhook non valida: {signature_status}")
                return {
                    "status": "error",
                    "error": f"invalid_signature_{signature_status}",
                    "message": "Firma non valida"
                }
        
        # Controllo anti-replay se abilitato
        if webhook.get("anti_replay", True):
            if self._is_replay_attack(webhook_id, headers, request_data):
                logger.warning(f"Possibile attacco replay rilevato per webhook '{webhook_id}'")
                return {
                    "status": "error",
                    "error": "replay_attack",
                    "message": "Possibile attacco replay"
                }
        
        # Controlla timestamp se presente
        if webhook.get("check_timestamp", True) and "X-Timestamp" in headers:
            try:
                timestamp = int(headers["X-Timestamp"])
                now = int(time.time())
                # Verifica che il timestamp non sia più vecchio di 5 minuti o nel futuro
                if timestamp < (now - 300) or timestamp > (now + 60):
                    logger.warning(f"Timestamp non valido: {timestamp}, ora: {now}")
                    return {
                        "status": "error",
                        "error": "invalid_timestamp",
                        "message": "Timestamp non valido"
                    }
            except (ValueError, TypeError):
                logger.warning(f"Timestamp non valido nel formato: {headers.get('X-Timestamp')}")
                return {
                    "status": "error",
                    "error": "invalid_timestamp_format",
                    "message": "Formato timestamp non valido"
                }
        
        # Convalida i dati in arrivo
        if not self._validate_webhook_data(webhook, request_data):
            logger.warning(f"Dati webhook non validi per '{webhook_id}'")
            return {
                "status": "error",
                "error": "invalid_data",
                "message": "Dati non validi"
            }
        
        # Processo i dati del webhook
        try:
            processed_data = self._process_webhook_data(webhook, request_data)
            
            # Registra l'evento
            logger.info(f"Webhook '{webhook_id}' ricevuto ed elaborato correttamente")
            
            # Registra dati dettagliati a scopo di audit
            self._log_webhook_event(webhook_id, source_ip, headers, request_data, processed_data)
            
            return {
                "status": "success",
                "processed": processed_data
            }
        except Exception as e:
            logger.error(f"Errore nell'elaborazione del webhook '{webhook_id}': {e}")
            return {
                "status": "error",
                "error": "processing_error",
                "message": str(e)
            }
    
    def _is_ip_blacklisted(self, ip: str) -> bool:
        """
        Verifica se un IP è nella blacklist
        
        Args:
            ip: Indirizzo IP da verificare
            
        Returns:
            bool: True se l'IP è nella blacklist, False altrimenti
        """
        try:
            client_ip = ipaddress.ip_address(ip)
            
            # Controlla IP esatti
            if ip in self.ip_blacklist:
                return True
            
            # Controlla subnet CIDR
            for block in self.ip_blacklist:
                if '/' in block:  # È un blocco CIDR
                    try:
                        network = ipaddress.ip_network(block, strict=False)
                        if client_ip in network:
                            return True
                    except ValueError:
                        continue
            
            return False
        except ValueError:
            logger.error(f"Formato IP non valido: {ip}")
            return True  # Per sicurezza, rifiuta IP non validi
    
    def _is_ip_whitelisted(self, ip: str) -> bool:
        """
        Verifica se un IP è nella whitelist
        
        Args:
            ip: Indirizzo IP da verificare
            
        Returns:
            bool: True se l'IP è nella whitelist, False altrimenti
        """
        # Se la whitelist è vuota, tutti gli IP sono permessi
        if not self.ip_whitelist:
            return True
        
        try:
            client_ip = ipaddress.ip_address(ip)
            
            # Controlla IP esatti
            if ip in self.ip_whitelist:
                return True
            
            # Controlla subnet CIDR
            for block in self.ip_whitelist:
                if '/' in block:  # È un blocco CIDR
                    try:
                        network = ipaddress.ip_network(block, strict=False)
                        if client_ip in network:
                            return True
                    except ValueError:
                        continue
            
            return False
        except ValueError:
            logger.error(f"Formato IP non valido: {ip}")
            return False
    
    def _is_rate_limited(self, ip: str) -> bool:
        """
        Verifica se un IP ha superato il rate limit
        
        Args:
            ip: Indirizzo IP da verificare
            
        Returns:
            bool: True se l'IP è rate limited, False altrimenti
        """
        now = time.time()
        
        # Pulisci vecchie entry
        self._clean_rate_limit_cache(now)
        
        if ip not in self.rate_limit_cache:
            return False
        
        ip_data = self.rate_limit_cache[ip]
        
        # Se è bloccato, controlla se il blocco è scaduto
        if ip_data.get("blocked_until", 0) > now:
            return True
        
        # Controlla il numero di richieste nella finestra temporale
        time_window = self.rate_limit["time_window"]
        max_requests = self.rate_limit["max_requests"]
        
        # Conta solo le richieste all'interno della finestra temporale
        recent_requests = [ts for ts in ip_data["requests"] if ts > (now - time_window)]
        
        if len(recent_requests) >= max_requests:
            # Supera il limite, blocca l'IP
            block_duration = self.rate_limit["block_duration"]
            self.rate_limit_cache[ip]["blocked_until"] = now + block_duration
            logger.warning(f"IP {ip} bloccato per {block_duration} secondi per rate limit")
            return True
        
        return False
    
    def _track_request(self, ip: str):
        """
        Registra una richiesta per il rate limiting
        
        Args:
            ip: Indirizzo IP
        """
        now = time.time()
        
        if ip not in self.rate_limit_cache:
            self.rate_limit_cache[ip] = {
                "requests": [now],
                "blocked_until": 0
            }
        else:
            self.rate_limit_cache[ip]["requests"].append(now)
    
    def _clean_rate_limit_cache(self, now: float):
        """
        Pulisce la cache del rate limiting
        
        Args:
            now: Timestamp corrente
        """
        time_window = self.rate_limit["time_window"]
        cutoff = now - (2 * time_window)
        
        # Rimuovi richieste vecchie e IP non più bloccati
        for ip in list(self.rate_limit_cache.keys()):
            # Rimuovi richieste vecchie
            self.rate_limit_cache[ip]["requests"] = [
                ts for ts in self.rate_limit_cache[ip]["requests"] if ts > cutoff
            ]
            
            # Se non ci sono più richieste e l'IP non è bloccato, rimuovilo dalla cache
            if not self.rate_limit_cache[ip]["requests"] and self.rate_limit_cache[ip]["blocked_until"] <= now:
                del self.rate_limit_cache[ip]
    
    def _verify_webhook_signature(self, webhook: Dict[str, Any], headers: Dict[str, str], 
                                 data: Any) -> str:
        """
        Verifica la firma del webhook
        
        Args:
            webhook: Configurazione del webhook
            headers: Headers della richiesta
            data: Dati della richiesta
            
        Returns:
            str: Stato della verifica ('valid', 'missing', 'invalid')
        """
        if not webhook.get("verify_signature", False):
            return "valid"
        
        auth_type = webhook.get("auth_type", "none")
        auth_params = webhook.get("auth_params", {})
        
        if auth_type == "hmac":
            # Nome header e segreto
            header_name = auth_params.get("header_name", "X-Signature")
            secret = auth_params.get("secret", "")
            algorithm = auth_params.get("algorithm", "sha256")
            
            if not header_name or not secret:
                logger.error("Configurazione HMAC incompleta")
                return "config_error"
            
            # Ottieni la firma dagli header
            signature = headers.get(header_name)
            if not signature:
                logger.warning(f"Header firma {header_name} mancante")
                return "missing"
            
            # Calcola la firma attesa
            expected_signature = self._generate_hmac_signature(
                json.dumps(data) if isinstance(data, dict) else str(data),
                secret,
                algorithm
            )
            
            # Confronta le firme (confronto sicuro)
            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("Firma HMAC non valida")
                return "invalid"
            
            return "valid"
            
        elif auth_type == "jwt":
            # Nome header e segreto
            header_name = auth_params.get("header_name", "Authorization")
            secret = auth_params.get("secret", "")
            algorithm = auth_params.get("algorithm", "HS256")
            
            if not header_name or not secret:
                logger.error("Configurazione JWT incompleta")
                return "config_error"
            
            # Ottieni il token dagli header (formato: "Bearer <token>")
            auth_header = headers.get(header_name, "")
            token_match = re.match(r"Bearer\s+(.+)", auth_header)
            
            if not token_match:
                logger.warning(f"Header JWT {header_name} mancante o malformato")
                return "missing"
            
            token = token_match.group(1)
            
            try:
                # Decodifica e verifica il token
                payload = jwt.decode(token, secret, algorithms=[algorithm])
                
                # Verifica che il token non sia scaduto
                exp = payload.get("exp", 0)
                if exp < time.time():
                    logger.warning("Token JWT scaduto")
                    return "expired"
                
                return "valid"
            except jwt.InvalidTokenError as e:
                logger.warning(f"Token JWT non valido: {e}")
                return "invalid"
            
        return "not_supported"
    
    def _is_replay_attack(self, webhook_id: str, headers: Dict[str, str], data: Any) -> bool:
        """
        Verifica se è un attacco replay
        
        Args:
            webhook_id: ID del webhook
            headers: Headers della richiesta
            data: Dati della richiesta
            
        Returns:
            bool: True se è un attacco replay, False altrimenti
        """
        # Cerca un ID univoco nella richiesta
        nonce = headers.get("X-Nonce")
        request_id = headers.get("X-Request-ID")
        
        # Se non c'è un ID univoco, usa una combinazione di valori
        if not nonce and not request_id:
            # Usa una combinazione di timestamp e hash dei dati
            timestamp = headers.get("X-Timestamp", str(int(time.time())))
            data_hash = hashlib.sha256(
                json.dumps(data).encode() if isinstance(data, dict) else str(data).encode()
            ).hexdigest()
            combined_id = f"{webhook_id}:{timestamp}:{data_hash}"
        else:
            combined_id = f"{webhook_id}:{nonce or request_id}"
        
        # Verifica se questa richiesta è già stata vista
        if combined_id in self.signature_cache:
            logger.warning(f"Richiesta duplicata rilevata: {combined_id}")
            return True
        
        # Salva l'ID nella cache
        now = time.time()
        self.signature_cache[combined_id] = now
        
        # Pulisci vecchie entry dalla cache (più di 1 ora)
        for key in list(self.signature_cache.keys()):
            if now - self.signature_cache[key] > 3600:
                del self.signature_cache[key]
        
        return False
    
    def _validate_webhook_data(self, webhook: Dict[str, Any], data: Any) -> bool:
        """
        Convalida i dati del webhook
        
        Args:
            webhook: Configurazione del webhook
            data: Dati da convalidare
            
        Returns:
            bool: True se i dati sono validi, False altrimenti
        """
        schema = webhook.get("schema")
        
        # Se non c'è uno schema, accetta qualsiasi dato
        if not schema:
            return True
        
        # Convalida di base per il tipo
        expected_type = schema.get("type")
        if expected_type == "object" and not isinstance(data, dict):
            logger.warning(f"Tipo dati non valido: atteso dict, ricevuto {type(data).__name__}")
            return False
        elif expected_type == "array" and not isinstance(data, list):
            logger.warning(f"Tipo dati non valido: atteso list, ricevuto {type(data).__name__}")
            return False
        
        # Per oggetti, convalida le proprietà richieste
        if expected_type == "object" and isinstance(data, dict):
            required_props = schema.get("required", [])
            for prop in required_props:
                if prop not in data:
                    logger.warning(f"Proprietà richiesta mancante: {prop}")
                    return False
            
            # Convalida formati specifici
            properties = schema.get("properties", {})
            for prop, prop_schema in properties.items():
                if prop in data:
                    prop_type = prop_schema.get("type")
                    prop_format = prop_schema.get("format")
                    
                    # Convalida tipo
                    if prop_type == "string" and not isinstance(data[prop], str):
                        logger.warning(f"Tipo proprietà non valido per {prop}: atteso string")
                        return False
                    elif prop_type == "number" and not isinstance(data[prop], (int, float)):
                        logger.warning(f"Tipo proprietà non valido per {prop}: atteso number")
                        return False
                    elif prop_type == "integer" and not isinstance(data[prop], int):
                        logger.warning(f"Tipo proprietà non valido per {prop}: atteso integer")
                        return False
                    elif prop_type == "boolean" and not isinstance(data[prop], bool):
                        logger.warning(f"Tipo proprietà non valido per {prop}: atteso boolean")
                        return False
                    
                    # Convalida formato
                    if prop_format and prop_type == "string" and isinstance(data[prop], str):
                        if prop_format == "email" and not self._is_valid_email(data[prop]):
                            logger.warning(f"Formato email non valido per {prop}")
                            return False
                        elif prop_format == "uri" and not self._is_valid_uri(data[prop]):
                            logger.warning(f"Formato URI non valido per {prop}")
                            return False
        
        return True
    
    def _is_valid_email(self, email: str) -> bool:
        """Verifica se una stringa è un'email valida"""
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(email_pattern, email))
    
    def _is_valid_uri(self, uri: str) -> bool:
        """Verifica se una stringa è un URI valido"""
        uri_pattern = r'^(https?|ftp)://[^\s/$.?#].[^\s]*$'
        return bool(re.match(uri_pattern, uri))
    
    def _process_webhook_data(self, webhook: Dict[str, Any], data: Any) -> Dict[str, Any]:
        """
        Elabora i dati del webhook
        
        Args:
            webhook: Configurazione del webhook
            data: Dati da elaborare
            
        Returns:
            Dict: Dati elaborati
        """
        # Questa funzione può essere estesa per trasformare i dati
        # Per ora, restituisce semplicemente i dati originali
        result = {
            "webhook_id": webhook.get("id"),
            "processed_at": datetime.now().isoformat(),
            "data": data
        }
        
        return result
    
    def _log_webhook_event(self, webhook_id: str, source_ip: str, headers: Dict[str, str], 
                          request_data: Any, processed_data: Dict[str, Any]):
        """
        Registra un evento webhook a scopo di audit
        
        Args:
            webhook_id: ID del webhook
            source_ip: IP di origine
            headers: Headers della richiesta
            request_data: Dati della richiesta
            processed_data: Dati elaborati
        """
        try:
            # Registra solo le informazioni essenziali per ragioni di privacy
            log_data = {
                "webhook_id": webhook_id,
                "timestamp": datetime.now().isoformat(),
                "source_ip": source_ip,
                "headers": {k: v for k, v in headers.items() if k.lower() not in 
                            ["authorization", "cookie", "x-signature"]},
                "request_size": len(json.dumps(request_data)) if request_data else 0,
                "processed": True
            }
            
            # Registra su file in formato JSON
            log_file = f"logs/webhooks/audit_{datetime.now().strftime('%Y-%m-%d')}.log"
            with open(log_file, "a") as f:
                f.write(json.dumps(log_data) + "\n")
                
        except Exception as e:
            logger.error(f"Errore nella registrazione dell'evento webhook: {e}")

    async def send_event(self, event_type: str, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invia un evento a tutti i webhook configurati per quel tipo di evento
        
        Args:
            event_type: Tipo di evento
            event_data: Dati dell'evento
            
        Returns:
            Dict: Risultati dell'invio dell'evento
        """
        results = {
            "success": [],
            "failed": []
        }
        
        # Cerca i webhook configurati per questo tipo di evento
        matching_webhooks = [w for w in self.webhooks if event_type in w.get("event_types", [])]
        
        if not matching_webhooks:
            logger.debug(f"Nessun webhook configurato per l'evento '{event_type}'")
            return results
        
        # Prepara i dati dell'evento
        payload = {
            "event_type": event_type,
            "timestamp": int(time.time()),
            "data": event_data
        }
        
        # Invia l'evento a tutti i webhook configurati
        for webhook in matching_webhooks:
            webhook_id = webhook.get("id", "unknown")
            
            # Skip se il webhook è disabilitato
            if not webhook.get("enabled", True):
                logger.debug(f"Webhook '{webhook_id}' disabilitato, skip")
                continue
            
            # Verifica se il webhook ha avuto troppi errori recenti
            if self._should_skip_webhook(webhook_id):
                logger.warning(f"Webhook '{webhook_id}' con troppi errori recenti, skip")
                results["failed"].append({
                    "webhook_id": webhook_id,
                    "reason": "too_many_errors"
                })
                continue
            
            # Invia l'evento al webhook
            success, error = await self._send_to_webhook(webhook, payload)
            
            if success:
                results["success"].append({
                    "webhook_id": webhook_id
                })
            else:
                results["failed"].append({
                    "webhook_id": webhook_id,
                    "reason": error
                })
        
        logger.info(f"Evento '{event_type}' inviato a {len(results['success'])} webhook con successo, fallito per {len(results['failed'])} webhook")
        return results
    
    async def _send_to_webhook(self, webhook: Dict[str, Any], payload: Dict[str, Any]) -> tuple:
        """
        Invia un payload a un singolo webhook
        
        Args:
            webhook: Configurazione del webhook
            payload: Payload da inviare
            
        Returns:
            tuple: (success, error_message)
        """
        webhook_id = webhook.get("id", "unknown")
        url = webhook.get("url")
        method = webhook.get("method", "POST")
        content_type = webhook.get("content_type", "application/json")
        auth_type = webhook.get("auth_type", "none")
        auth_params = webhook.get("auth_params", {})
        headers = {**self.default_headers, **webhook.get("headers", {})}
        template = webhook.get("template")
        
        # Verifica che l'URL sia disponibile
        if not url:
            logger.error(f"URL mancante per il webhook '{webhook_id}'")
            self._track_webhook_error(webhook_id)
            return False, "missing_url"
        
        try:
            # Prepara i dati da inviare
            if template:
                # Applica il template ai dati
                data = self._apply_template(template, payload)
            else:
                # Usa i dati grezzi
                data = payload
            
            # Imposta il content type
            headers["Content-Type"] = content_type
            
            # Gestisci l'autenticazione
            if auth_type == "basic":
                username = auth_params.get("username", "")
                password = auth_params.get("password", "")
                auth = aiohttp.BasicAuth(username, password)
            elif auth_type == "bearer":
                token = auth_params.get("token", "")
                headers["Authorization"] = f"Bearer {token}"
                auth = None
            elif auth_type == "api_key":
                key_name = auth_params.get("key_name", "X-API-Key")
                key_value = auth_params.get("key_value", "")
                headers[key_name] = key_value
                auth = None
            elif auth_type == "hmac":
                secret = auth_params.get("secret", "")
                algorithm = auth_params.get("algorithm", "sha256")
                header_name = auth_params.get("header_name", "X-Signature")
                
                # Calcola la firma HMAC
                payload_str = json.dumps(data)
                signature = self._generate_hmac_signature(payload_str, secret, algorithm)
                headers[header_name] = signature
                auth = None
            elif auth_type == "jwt":
                secret = auth_params.get("secret", "")
                algorithm = auth_params.get("algorithm", "HS256")
                expiration = auth_params.get("expiration", 60)  # 60 secondi
                
                # Genera il token JWT
                token = self._generate_jwt_token(secret, algorithm, expiration)
                headers["Authorization"] = f"Bearer {token}"
                auth = None
            else:
                # Nessuna autenticazione
                auth = None
            
            # Converti i dati in base al content type
            if content_type == "application/x-www-form-urlencoded":
                send_data = data
            else:
                send_data = json.dumps(data) if content_type == "application/json" else data
            
            # Invia la richiesta
            for retry in range(self.max_retries):
                try:
                    async with aiohttp.ClientSession() as session:
                        if method == "GET":
                            async with session.get(url, params=data, headers=headers, auth=auth, timeout=self.timeout) as response:
                                # Verifica il codice di risposta
                                if response.status < 200 or response.status >= 300:
                                    logger.warning(f"Webhook '{webhook_id}' ha risposto con {response.status}, retry {retry+1}/{self.max_retries}")
                                    
                                    # Attendi prima di riprovare
                                    if retry < self.max_retries - 1:
                                        await asyncio.sleep(self.retry_delay * (2 ** retry))
                                        continue
                                    
                                    self._track_webhook_error(webhook_id)
                                    return False, f"http_error_{response.status}"
                                
                                logger.info(f"Webhook '{webhook_id}' inviato con successo")
                                return True, None
                        else:
                            async with session.request(method, url, data=send_data, headers=headers, auth=auth, timeout=self.timeout) as response:
                                # Verifica il codice di risposta
                                if response.status < 200 or response.status >= 300:
                                    logger.warning(f"Webhook '{webhook_id}' ha risposto con {response.status}, retry {retry+1}/{self.max_retries}")
                                    
                                    # Attendi prima di riprovare
                                    if retry < self.max_retries - 1:
                                        await asyncio.sleep(self.retry_delay * (2 ** retry))
                                        continue
                                    
                                    self._track_webhook_error(webhook_id)
                                    return False, f"http_error_{response.status}"
                                
                                logger.info(f"Webhook '{webhook_id}' inviato con successo")
                                return True, None
                
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout per il webhook '{webhook_id}', retry {retry+1}/{self.max_retries}")
                    
                    # Attendi prima di riprovare
                    if retry < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (2 ** retry))
                        continue
                    
                    self._track_webhook_error(webhook_id)
                    return False, "timeout"
                
                except Exception as e:
                    logger.error(f"Errore nell'invio del webhook '{webhook_id}': {e}")
                    
                    # Attendi prima di riprovare
                    if retry < self.max_retries - 1:
                        await asyncio.sleep(self.retry_delay * (2 ** retry))
                        continue
                    
                    self._track_webhook_error(webhook_id)
                    return False, str(e)
            
            # Tutti i tentativi falliti
            self._track_webhook_error(webhook_id)
            return False, "max_retries_exceeded"
            
        except Exception as e:
            logger.error(f"Errore nella preparazione del webhook '{webhook_id}': {e}")
            self._track_webhook_error(webhook_id)
            return False, str(e)
    
    def _apply_template(self, template: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Applica un template ai dati dell'evento
        
        Args:
            template: Template da applicare
            payload: Dati dell'evento
            
        Returns:
            Dict: Dati formattati secondo il template
        """
        # Funzione ricorsiva per applicare il template
        def apply_recursive(template_part, payload):
            if isinstance(template_part, dict):
                result = {}
                for key, value in template_part.items():
                    # Sostituisci le variabili nei nomi delle chiavi
                    key = self._replace_variables(key, payload)
                    result[key] = apply_recursive(value, payload)
                return result
            elif isinstance(template_part, list):
                return [apply_recursive(item, payload) for item in template_part]
            elif isinstance(template_part, str):
                return self._replace_variables(template_part, payload)
            else:
                return template_part
        
        return apply_recursive(template, payload)
    
    def _replace_variables(self, text: str, payload: Dict[str, Any]) -> str:
        """
        Sostituisce le variabili in un testo con i valori corrispondenti
        
        Args:
            text: Testo con variabili
            payload: Dati dell'evento
            
        Returns:
            str: Testo con variabili sostituite
        """
        if not isinstance(text, str):
            return text
        
        # Cerca le variabili nel formato {{var}}
        import re
        matches = re.findall(r'\{\{([^}]+)\}\}', text)
        
        for match in matches:
            # Estrai il percorso della variabile
            path = match.strip().split('.')
            
            # Cerca il valore nei dati dell'evento
            value = payload
            for key in path:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    value = ""
                    break
            
            # Sostituisci la variabile con il valore
            text = text.replace(f"{{{{{match}}}}}", str(value))
        
        return text
    
    def _track_webhook_error(self, webhook_id: str):
        """
        Tiene traccia degli errori dei webhook
        
        Args:
            webhook_id: ID del webhook
        """
        now = time.time()
        
        if webhook_id not in self.error_cache:
            self.error_cache[webhook_id] = {
                "count": 1,
                "first_error": now,
                "last_error": now
            }
        else:
            self.error_cache[webhook_id]["count"] += 1
            self.error_cache[webhook_id]["last_error"] = now
            
            # Elimina gli errori vecchi (più di 1 ora)
            if now - self.error_cache[webhook_id]["first_error"] > 3600:
                self.error_cache[webhook_id] = {
                    "count": 1,
                    "first_error": now,
                    "last_error": now
                }
    
    def _should_skip_webhook(self, webhook_id: str) -> bool:
        """
        Verifica se un webhook dovrebbe essere ignorato a causa di troppi errori
        
        Args:
            webhook_id: ID del webhook
            
        Returns:
            bool: True se il webhook dovrebbe essere ignorato, False altrimenti
        """
        if webhook_id not in self.error_cache:
            return False
        
        now = time.time()
        error_info = self.error_cache[webhook_id]
        
        # Ignora i webhook con più di 5 errori negli ultimi 10 minuti
        if error_info["count"] >= 5 and now - error_info["first_error"] <= 600:
            return True
        
        return False
    
    def _generate_hmac_signature(self, payload: str, secret: str, algorithm: str) -> str:
        """
        Genera una firma HMAC per un payload
        
        Args:
            payload: Payload da firmare
            secret: Secret per la firma
            algorithm: Algoritmo di hashing
            
        Returns:
            str: Firma HMAC
        """
        # Converti il secret in bytes
        secret_bytes = secret.encode('utf-8')
        payload_bytes = payload.encode('utf-8')
        
        # Scegli l'algoritmo di hashing
        if algorithm == "sha256":
            h = hmac.new(secret_bytes, payload_bytes, hashlib.sha256)
        elif algorithm == "sha1":
            h = hmac.new(secret_bytes, payload_bytes, hashlib.sha1)
        elif algorithm == "md5":
            h = hmac.new(secret_bytes, payload_bytes, hashlib.md5)
        else:
            # Default a SHA-256
            h = hmac.new(secret_bytes, payload_bytes, hashlib.sha256)
        
        # Restituisci la firma in formato esadecimale
        return h.hexdigest()
    
    def _generate_jwt_token(self, secret: str, algorithm: str, expiration: int) -> str:
        """
        Genera un token JWT
        
        Args:
            secret: Secret per la firma
            algorithm: Algoritmo di firma
            expiration: Tempo di scadenza in secondi
            
        Returns:
            str: Token JWT
        """
        now = int(time.time())
        
        # Crea il payload
        payload = {
            "iat": now,
            "exp": now + expiration,
            "iss": "m4bot"
        }
        
        # Genera il token
        token = jwt.encode(payload, secret, algorithm=algorithm)
        
        return token
    
    def add_webhook(self, webhook: Dict[str, Any]) -> bool:
        """
        Aggiunge un nuovo webhook
        
        Args:
            webhook: Configurazione del webhook
            
        Returns:
            bool: True se il webhook è stato aggiunto con successo, False altrimenti
        """
        # Verifica che il webhook abbia un ID
        if "id" not in webhook:
            logger.error("Impossibile aggiungere webhook senza ID")
            return False
        
        # Verifica che il webhook abbia un URL
        if "url" not in webhook:
            logger.error(f"Impossibile aggiungere webhook '{webhook['id']}' senza URL")
            return False
        
        # Verifica che il webhook abbia almeno un tipo di evento
        if "event_types" not in webhook or not webhook["event_types"]:
            logger.error(f"Impossibile aggiungere webhook '{webhook['id']}' senza tipi di evento")
            return False
        
        # Verifica che il webhook non esista già
        for existing_webhook in self.webhooks:
            if existing_webhook.get("id") == webhook["id"]:
                logger.error(f"Webhook con ID '{webhook['id']}' già esistente")
                return False
        
        # Aggiungi il webhook
        self.webhooks.append(webhook)
        logger.info(f"Webhook '{webhook['id']}' aggiunto con successo")
        return True
    
    def remove_webhook(self, webhook_id: str) -> bool:
        """
        Rimuove un webhook
        
        Args:
            webhook_id: ID del webhook da rimuovere
            
        Returns:
            bool: True se il webhook è stato rimosso con successo, False altrimenti
        """
        # Cerca il webhook
        for i, webhook in enumerate(self.webhooks):
            if webhook.get("id") == webhook_id:
                # Rimuovi il webhook
                self.webhooks.pop(i)
                logger.info(f"Webhook '{webhook_id}' rimosso con successo")
                return True
        
        logger.error(f"Webhook '{webhook_id}' non trovato")
        return False
    
    def update_webhook(self, webhook_id: str, webhook: Dict[str, Any]) -> bool:
        """
        Aggiorna un webhook esistente
        
        Args:
            webhook_id: ID del webhook da aggiornare
            webhook: Nuova configurazione del webhook
            
        Returns:
            bool: True se il webhook è stato aggiornato con successo, False altrimenti
        """
        # Verifica che il webhook abbia un URL
        if "url" not in webhook:
            logger.error(f"Impossibile aggiornare webhook '{webhook_id}' senza URL")
            return False
        
        # Verifica che il webhook abbia almeno un tipo di evento
        if "event_types" not in webhook or not webhook["event_types"]:
            logger.error(f"Impossibile aggiornare webhook '{webhook_id}' senza tipi di evento")
            return False
        
        # Cerca il webhook
        for i, existing_webhook in enumerate(self.webhooks):
            if existing_webhook.get("id") == webhook_id:
                # Aggiorna il webhook
                webhook["id"] = webhook_id  # Assicura che l'ID rimanga lo stesso
                self.webhooks[i] = webhook
                logger.info(f"Webhook '{webhook_id}' aggiornato con successo")
                return True
        
        logger.error(f"Webhook '{webhook_id}' non trovato")
        return False
    
    def get_webhook(self, webhook_id: str) -> Optional[Dict[str, Any]]:
        """
        Ottiene un webhook
        
        Args:
            webhook_id: ID del webhook
            
        Returns:
            Optional[Dict]: Configurazione del webhook o None se non trovato
        """
        # Cerca il webhook
        for webhook in self.webhooks:
            if webhook.get("id") == webhook_id:
                return webhook
        
        return None
    
    def get_webhooks(self) -> List[Dict[str, Any]]:
        """
        Ottiene tutti i webhook
        
        Returns:
            List: Lista dei webhook
        """
        return self.webhooks.copy()
    
    def test_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """
        Testa un webhook
        
        Args:
            webhook_id: ID del webhook
            
        Returns:
            Dict: Risultato del test
        """
        # Crea un evento di test
        test_event = {
            "event_type": "test",
            "timestamp": int(time.time()),
            "data": {
                "message": "Questo è un evento di test",
                "source": "M4Bot Webhook Handler"
            }
        }
        
        # Trova il webhook
        webhook = self.get_webhook(webhook_id)
        if not webhook:
            return {
                "success": False,
                "error": f"Webhook '{webhook_id}' non trovato"
            }
        
        # Crea una copia del webhook per il test
        test_webhook = webhook.copy()
        test_webhook["event_types"] = ["test"]
        
        # Crea una lista temporanea con solo il webhook di test
        original_webhooks = self.webhooks
        self.webhooks = [test_webhook]
        
        # Invia l'evento di test
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self.send_event("test", test_event["data"]))
        
        # Ripristina la lista originale di webhook
        self.webhooks = original_webhooks
        
        if result["success"]:
            return {
                "success": True,
                "message": f"Webhook '{webhook_id}' testato con successo"
            }
        else:
            return {
                "success": False,
                "error": f"Errore nel test del webhook '{webhook_id}': {result['failed'][0]['reason'] if result['failed'] else 'unknown error'}"
            }

# Funzione per creare un'istanza del gestore di webhook
def create_webhook_handler(config: Dict[str, Any]) -> WebhookHandler:
    """
    Crea un'istanza del gestore di webhook
    
    Args:
        config: Configurazione del gestore
        
    Returns:
        WebhookHandler: Istanza del gestore di webhook
    """
    return WebhookHandler(config) 