import os
import json
import logging
import asyncio
import aiohttp
import aiofiles
import hmac
import hashlib
import base64
from typing import Dict, List, Optional, Any, Callable, Union

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/whatsapp_connector.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("WhatsAppConnector")

class WhatsAppConnector:
    """Connettore per WhatsApp che gestisce l'integrazione con l'API WhatsApp Business"""
    
    def __init__(self, config: Dict[str, Any], message_callback: Optional[Callable] = None):
        """
        Inizializza il connettore WhatsApp
        
        Args:
            config: Configurazione del connettore
            message_callback: Callback per gestire i messaggi ricevuti da WhatsApp
        """
        # Inizializza le variabili
        self.config = config
        self.api_version = config.get("whatsapp_api_version", "v16.0")
        self.phone_number_id = config.get("whatsapp_phone_number_id", "")
        self.token = config.get("whatsapp_token", "")
        self.verify_token = config.get("whatsapp_verify_token", "")
        self.message_callback = message_callback
        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"
        self.message_templates = config.get("whatsapp_message_templates", {})
        
        # Client HTTP
        self.session = None
        
        # Flag per indicare se il bot è in esecuzione
        self.is_running = False
        
        # Registro dei messaggi sincronizzati per evitare duplicati
        self.synced_messages = {}
        
        # Crea le directory necessarie
        os.makedirs("logs", exist_ok=True)
        
        logger.info("Connettore WhatsApp inizializzato")
    
    async def start(self):
        """Avvia il connettore WhatsApp"""
        if not self.token or not self.phone_number_id:
            logger.error("Token WhatsApp o Phone Number ID non configurati")
            return False
        
        try:
            # Crea la sessione HTTP
            self.session = aiohttp.ClientSession()
            
            # Verifica che il token sia valido
            status = await self.check_token()
            if not status:
                logger.error("Impossibile connettersi all'API WhatsApp. Verifica il token.")
                await self.session.close()
                self.session = None
                return False
            
            self.is_running = True
            logger.info("Connettore WhatsApp avviato")
            return True
        except Exception as e:
            logger.error(f"Errore nell'avvio del connettore WhatsApp: {e}")
            if self.session:
                await self.session.close()
                self.session = None
            return False
    
    async def stop(self):
        """Ferma il connettore WhatsApp"""
        if self.is_running:
            try:
                self.is_running = False
                
                if self.session:
                    await self.session.close()
                    self.session = None
                
                logger.info("Connettore WhatsApp fermato")
                return True
            except Exception as e:
                logger.error(f"Errore nella chiusura del connettore WhatsApp: {e}")
                return False
        return True
    
    async def check_token(self) -> bool:
        """
        Verifica che il token sia valido
        
        Returns:
            bool: True se il token è valido, False altrimenti
        """
        if not self.session:
            return False
        
        try:
            # Semplice richiesta per verificare che il token sia valido
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            # Ottiene la lista dei template disponibili
            async with self.session.get(
                f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/message_templates",
                headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella verifica del token: {error_text}")
                    return False
                
                data = await response.json()
                return True
        except Exception as e:
            logger.error(f"Eccezione nella verifica del token: {e}")
            return False
    
    def verify_webhook(self, query_params: Dict[str, Any]) -> bool:
        """
        Verifica la richiesta di webhook di WhatsApp
        
        Args:
            query_params: Parametri della query
            
        Returns:
            bool: True se la verifica è riuscita, False altrimenti
        """
        mode = query_params.get("hub.mode")
        token = query_params.get("hub.verify_token")
        challenge = query_params.get("hub.challenge")
        
        if mode == "subscribe" and token == self.verify_token:
            return True
        
        return False
    
    async def process_webhook(self, request_data: Dict[str, Any]) -> bool:
        """
        Processa i dati ricevuti dal webhook di WhatsApp
        
        Args:
            request_data: Dati della richiesta
            
        Returns:
            bool: True se il processamento è riuscito, False altrimenti
        """
        try:
            # Verifica se è un messaggio di WhatsApp
            if "entry" not in request_data:
                return False
            
            for entry in request_data.get("entry", []):
                if "changes" not in entry:
                    continue
                
                for change in entry.get("changes", []):
                    if change.get("field") != "messages":
                        continue
                    
                    value = change.get("value", {})
                    
                    if "messages" not in value:
                        continue
                    
                    for message in value.get("messages", []):
                        await self._process_message(message, value)
            
            return True
        except Exception as e:
            logger.error(f"Errore nel processamento del webhook: {e}")
            return False
    
    async def _process_message(self, message: Dict[str, Any], metadata: Dict[str, Any]):
        """
        Processa un messaggio ricevuto da WhatsApp
        
        Args:
            message: Messaggio da processare
            metadata: Metadati del messaggio
        """
        try:
            # Estrai le informazioni principali
            message_id = message.get("id", "")
            from_number = message.get("from", "")
            timestamp = message.get("timestamp", 0)
            
            # Verifica se il messaggio è già stato sincronizzato
            unique_id = f"whatsapp_{message_id}"
            if unique_id in self.synced_messages:
                return
            
            # Aggiunge il messaggio al registro dei messaggi sincronizzati
            self.synced_messages[unique_id] = {
                "timestamp": timestamp,
                "platform": "whatsapp",
                "from": from_number
            }
            
            # Mantieni solo gli ultimi 1000 messaggi nel registro
            if len(self.synced_messages) > 1000:
                # Ordina per timestamp e rimuovi i più vecchi
                sorted_messages = sorted(
                    self.synced_messages.items(),
                    key=lambda x: x[1]["timestamp"]
                )
                self.synced_messages = dict(sorted_messages[500:])
            
            # Determina il tipo di messaggio
            content = ""
            message_type = ""
            
            if "text" in message:
                message_type = "text"
                content = message["text"].get("body", "")
            elif "image" in message:
                message_type = "image"
                content = "[Immagine]"
            elif "audio" in message:
                message_type = "audio"
                content = "[Audio]"
            elif "video" in message:
                message_type = "video"
                content = "[Video]"
            elif "document" in message:
                message_type = "document"
                content = "[Documento]"
            elif "location" in message:
                message_type = "location"
                content = "[Posizione]"
            elif "sticker" in message:
                message_type = "sticker"
                content = "[Sticker]"
            elif "reaction" in message:
                message_type = "reaction"
                content = f"[Reazione: {message['reaction'].get('emoji', '')}]"
            elif "button" in message:
                message_type = "button"
                content = f"[Pulsante: {message['button'].get('text', '')}]"
            elif "interactive" in message:
                message_type = "interactive"
                content = f"[Interattivo: {message['interactive'].get('type', '')}]"
            else:
                message_type = "unknown"
                content = "[Messaggio sconosciuto]"
            
            # Ottieni informazioni sul contatto
            contact_name = from_number
            if "contacts" in metadata:
                for contact in metadata.get("contacts", []):
                    if "profile" in contact and "name" in contact["profile"]:
                        contact_name = contact["profile"]["name"]
                        break
            
            # Formatta il messaggio per la sincronizzazione
            formatted_message = {
                "id": unique_id,
                "platform": "whatsapp",
                "channel_id": self.phone_number_id,
                "channel_name": "WhatsApp",
                "author": {
                    "id": from_number,
                    "username": from_number,
                    "display_name": contact_name,
                    "is_mod": False
                },
                "content": content,
                "timestamp": timestamp,
                "message_type": message_type,
                "raw_message": message
            }
            
            # Invia il messaggio al callback se presente
            if self.message_callback:
                try:
                    await self.message_callback(formatted_message)
                except Exception as e:
                    logger.error(f"Errore nel callback del messaggio: {e}")
        except Exception as e:
            logger.error(f"Errore nel processamento del messaggio: {e}")
    
    async def send_message(self, to: str, text: str, preview_url: bool = False) -> bool:
        """
        Invia un messaggio di testo a un numero WhatsApp
        
        Args:
            to: Numero di telefono del destinatario
            text: Testo da inviare
            preview_url: Se generare l'anteprima dei link
            
        Returns:
            bool: True se l'invio è riuscito, False altrimenti
        """
        if not self.session or not self.is_running:
            return False
        
        try:
            # Prepara l'header con il token
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            # Prepara il payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {
                    "body": text,
                    "preview_url": preview_url
                }
            }
            
            # Invia il messaggio
            async with self.session.post(
                f"{self.base_url}/messages",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nell'invio del messaggio: {error_text}")
                    return False
                
                data = await response.json()
                return True
        except Exception as e:
            logger.error(f"Eccezione nell'invio del messaggio: {e}")
            return False
    
    async def send_template(self, to: str, template_name: str, language: str = "it", 
                           components: Optional[List[Dict[str, Any]]] = None) -> bool:
        """
        Invia un messaggio template a un numero WhatsApp
        
        Args:
            to: Numero di telefono del destinatario
            template_name: Nome del template
            language: Codice lingua del template
            components: Componenti del template (parametri)
            
        Returns:
            bool: True se l'invio è riuscito, False altrimenti
        """
        if not self.session or not self.is_running:
            return False
        
        try:
            # Prepara l'header con il token
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            # Prepara il payload
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {
                        "code": language
                    }
                }
            }
            
            # Aggiungi i componenti se presenti
            if components:
                payload["template"]["components"] = components
            
            # Invia il messaggio
            async with self.session.post(
                f"{self.base_url}/messages",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nell'invio del template: {error_text}")
                    return False
                
                data = await response.json()
                return True
        except Exception as e:
            logger.error(f"Eccezione nell'invio del template: {e}")
            return False
    
    async def sync_message_to_whatsapp(self, message: Dict[str, Any], to: str) -> bool:
        """
        Sincronizza un messaggio da un'altra piattaforma a WhatsApp
        
        Args:
            message: Il messaggio da sincronizzare
            to: Numero di telefono del destinatario
            
        Returns:
            bool: True se il messaggio è stato sincronizzato con successo, False altrimenti
        """
        try:
            # Verifica se il messaggio è già stato sincronizzato
            message_id = message.get("id", "")
            if message_id in self.synced_messages:
                return True
            
            # Aggiunge il messaggio al registro dei messaggi sincronizzati
            self.synced_messages[message_id] = {
                "timestamp": message.get("timestamp", 0),
                "platform": message.get("platform", "unknown"),
                "to": to
            }
            
            # Mantieni solo gli ultimi 1000 messaggi nel registro
            if len(self.synced_messages) > 1000:
                # Ordina per timestamp e rimuovi i più vecchi
                sorted_messages = sorted(
                    self.synced_messages.items(),
                    key=lambda x: x[1]["timestamp"]
                )
                self.synced_messages = dict(sorted_messages[500:])
            
            # Verifica se il connettore è in esecuzione
            if not self.is_running:
                return False
            
            # Formatta il messaggio per WhatsApp
            platform = message.get("platform", "unknown")
            author_name = message.get("author", {}).get("display_name", "Utente")
            content = message.get("content", "")
            
            formatted_content = f"[{platform.upper()}] {author_name}: {content}"
            
            # Invia il messaggio
            return await self.send_message(to, formatted_content)
            
        except Exception as e:
            logger.error(f"Errore nella sincronizzazione del messaggio a WhatsApp: {e}")
            return False
    
    async def mark_message_as_read(self, message_id: str) -> bool:
        """
        Marca un messaggio come letto
        
        Args:
            message_id: ID del messaggio
            
        Returns:
            bool: True se l'operazione è riuscita, False altrimenti
        """
        if not self.session or not self.is_running:
            return False
        
        try:
            # Prepara l'header con il token
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            
            # Prepara il payload
            payload = {
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id
            }
            
            # Invia la richiesta
            async with self.session.post(
                f"{self.base_url}/messages",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella marcatura del messaggio come letto: {error_text}")
                    return False
                
                data = await response.json()
                return True
        except Exception as e:
            logger.error(f"Eccezione nella marcatura del messaggio come letto: {e}")
            return False
    
    async def is_connected(self) -> bool:
        """
        Verifica se il connettore è connesso a WhatsApp
        
        Returns:
            bool: True se il connettore è connesso, False altrimenti
        """
        if not self.is_running or not self.session:
            return False
        
        # Verifica che il token sia ancora valido
        return await self.check_token()

# Funzione per creare un'istanza del connettore WhatsApp
def create_whatsapp_connector(config: Dict[str, Any], message_callback: Optional[Callable] = None) -> WhatsAppConnector:
    """
    Crea un'istanza del connettore WhatsApp
    
    Args:
        config: Configurazione del connettore
        message_callback: Callback per gestire i messaggi ricevuti da WhatsApp
        
    Returns:
        WhatsAppConnector: Istanza del connettore WhatsApp
    """
    return WhatsAppConnector(config, message_callback) 