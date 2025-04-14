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
from typing import Dict, List, Optional, Any, Callable

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/webhook_handler.log"),
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
        
        # Cache dei webhook con errori
        self.error_cache = {}
        
        # Crea le directory necessarie
        os.makedirs("logs", exist_ok=True)
        
        logger.info(f"Gestore di webhook inizializzato ({len(self.webhooks)} webhook configurati)")
    
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