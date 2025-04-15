import os
import json
import logging
import asyncio
import aiohttp
import time
from typing import Dict, List, Optional, Any, Callable, Union

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/telegram_connector.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("TelegramConnector")

class TelegramConnector:
    """Connettore per Telegram che gestisce l'invio di messaggi e notifiche"""
    
    def __init__(self, config: Dict[str, Any], message_callback: Optional[Callable] = None):
        """
        Inizializza il connettore Telegram
        
        Args:
            config: Configurazione del connettore
            message_callback: Callback per gestire i messaggi ricevuti da Telegram
        """
        # Inizializza le variabili
        self.config = config
        self.bot_token = config.get("telegram_bot_token", "")
        self.message_callback = message_callback
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.webhook_url = config.get("telegram_webhook_url", "")
        self.message_templates = config.get("telegram_message_templates", {})
        
        # Client HTTP
        self.session = None
        
        # Flag per indicare se il bot è in esecuzione
        self.is_running = False
        
        # Registro dei messaggi inviati per evitare duplicati
        self.sent_messages = {}
        
        # Crea le directory necessarie
        os.makedirs("logs", exist_ok=True)
        
        logger.info("Connettore Telegram inizializzato")
    
    async def start(self):
        """Avvia il connettore Telegram"""
        if not self.bot_token:
            logger.error("Token Telegram non configurato")
            return False
        
        try:
            # Crea la sessione HTTP
            self.session = aiohttp.ClientSession()
            
            # Verifica che il token sia valido
            status = await self.check_token()
            if not status:
                logger.error("Impossibile connettersi all'API Telegram. Verifica il token.")
                await self.session.close()
                self.session = None
                return False
            
            # Configura il webhook se impostato
            if self.webhook_url:
                await self.set_webhook(self.webhook_url)
            
            self.is_running = True
            logger.info("Connettore Telegram avviato")
            return True
        except Exception as e:
            logger.error(f"Errore nell'avvio del connettore Telegram: {e}")
            if self.session:
                await self.session.close()
                self.session = None
            return False
    
    async def stop(self):
        """Ferma il connettore Telegram"""
        if self.is_running:
            try:
                self.is_running = False
                
                # Rimuovi il webhook se era configurato
                if self.webhook_url:
                    await self.delete_webhook()
                
                if self.session:
                    await self.session.close()
                    self.session = None
                
                logger.info("Connettore Telegram fermato")
                return True
            except Exception as e:
                logger.error(f"Errore nella chiusura del connettore Telegram: {e}")
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
            async with self.session.get(f"{self.base_url}/getMe") as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella verifica del token: {error_text}")
                    return False
                
                data = await response.json()
                if not data.get("ok", False):
                    logger.error(f"Errore nella verifica del token: {data}")
                    return False
                
                return True
        except Exception as e:
            logger.error(f"Eccezione nella verifica del token: {e}")
            return False
    
    async def set_webhook(self, url: str) -> bool:
        """
        Imposta il webhook per ricevere aggiornamenti da Telegram
        
        Args:
            url: URL del webhook
            
        Returns:
            bool: True se l'operazione è riuscita, False altrimenti
        """
        if not self.session or not self.is_running:
            return False
        
        try:
            async with self.session.post(
                f"{self.base_url}/setWebhook",
                json={"url": url}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nell'impostazione del webhook: {error_text}")
                    return False
                
                data = await response.json()
                if not data.get("ok", False):
                    logger.error(f"Errore nell'impostazione del webhook: {data}")
                    return False
                
                logger.info(f"Webhook impostato con successo: {url}")
                return True
        except Exception as e:
            logger.error(f"Eccezione nell'impostazione del webhook: {e}")
            return False
    
    async def delete_webhook(self) -> bool:
        """
        Rimuove il webhook
        
        Returns:
            bool: True se l'operazione è riuscita, False altrimenti
        """
        if not self.session:
            return False
        
        try:
            async with self.session.post(f"{self.base_url}/deleteWebhook") as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella rimozione del webhook: {error_text}")
                    return False
                
                data = await response.json()
                if not data.get("ok", False):
                    logger.error(f"Errore nella rimozione del webhook: {data}")
                    return False
                
                logger.info("Webhook rimosso con successo")
                return True
        except Exception as e:
            logger.error(f"Eccezione nella rimozione del webhook: {e}")
            return False
    
    async def process_webhook(self, update: Dict[str, Any]) -> bool:
        """
        Processa un aggiornamento ricevuto dal webhook
        
        Args:
            update: L'aggiornamento ricevuto da Telegram
            
        Returns:
            bool: True se il processamento è riuscito, False altrimenti
        """
        try:
            # Verifica se è un messaggio
            if "message" in update:
                await self._process_message(update["message"])
            # Verifica se è un callback query (pulsante inline premuto)
            elif "callback_query" in update:
                await self._process_callback_query(update["callback_query"])
            
            return True
        except Exception as e:
            logger.error(f"Errore nel processamento dell'aggiornamento: {e}")
            return False
    
    async def _process_message(self, message: Dict[str, Any]):
        """
        Processa un messaggio ricevuto da Telegram
        
        Args:
            message: Il messaggio da processare
        """
        try:
            # Estrai le informazioni principali
            message_id = message.get("message_id", 0)
            chat = message.get("chat", {})
            chat_id = chat.get("id", 0)
            text = message.get("text", "")
            from_user = message.get("from", {})
            user_id = from_user.get("id", 0)
            username = from_user.get("username", "")
            first_name = from_user.get("first_name", "")
            
            # Formatta il messaggio per il callback
            formatted_message = {
                "id": f"telegram_{message_id}",
                "platform": "telegram",
                "chat_id": chat_id,
                "author": {
                    "id": user_id,
                    "username": username,
                    "display_name": first_name,
                    "is_mod": False
                },
                "content": text,
                "timestamp": int(time.time()),
                "message_type": "text",
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
    
    async def _process_callback_query(self, callback_query: Dict[str, Any]):
        """
        Processa un callback query ricevuto da Telegram
        
        Args:
            callback_query: Il callback query da processare
        """
        try:
            # Estrai le informazioni principali
            query_id = callback_query.get("id", "")
            from_user = callback_query.get("from", {})
            user_id = from_user.get("id", 0)
            username = from_user.get("username", "")
            first_name = from_user.get("first_name", "")
            data = callback_query.get("data", "")
            
            # Rispondi al callback query per evitare l'icona di caricamento
            await self.answer_callback_query(query_id)
            
            # Formatta il callback per il callback
            formatted_callback = {
                "id": f"telegram_callback_{query_id}",
                "platform": "telegram",
                "author": {
                    "id": user_id,
                    "username": username,
                    "display_name": first_name,
                    "is_mod": False
                },
                "data": data,
                "timestamp": int(time.time()),
                "message_type": "callback_query",
                "raw_callback": callback_query
            }
            
            # Invia il callback al callback se presente
            if self.message_callback:
                try:
                    await self.message_callback(formatted_callback)
                except Exception as e:
                    logger.error(f"Errore nel callback del callback query: {e}")
        except Exception as e:
            logger.error(f"Errore nel processamento del callback query: {e}")
    
    async def send_message(self, chat_id: Union[int, str], text: str, parse_mode: str = "HTML", 
                          disable_web_page_preview: bool = False, 
                          reply_markup: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Invia un messaggio a una chat Telegram
        
        Args:
            chat_id: ID della chat
            text: Testo da inviare
            parse_mode: Modalità di parsing del testo (HTML, Markdown)
            disable_web_page_preview: Se disabilitare l'anteprima dei link
            reply_markup: Markup per pulsanti inline o tastiera personalizzata
            
        Returns:
            Optional[Dict[str, Any]]: Risposta di Telegram, o None in caso di errore
        """
        if not self.session or not self.is_running:
            return None
        
        try:
            # Prepara i parametri
            params = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": disable_web_page_preview
            }
            
            # Aggiungi il markup se presente
            if reply_markup:
                params["reply_markup"] = json.dumps(reply_markup)
            
            # Invia il messaggio
            async with self.session.post(
                f"{self.base_url}/sendMessage",
                json=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nell'invio del messaggio: {error_text}")
                    return None
                
                data = await response.json()
                if not data.get("ok", False):
                    logger.error(f"Errore nell'invio del messaggio: {data}")
                    return None
                
                return data.get("result")
        except Exception as e:
            logger.error(f"Eccezione nell'invio del messaggio: {e}")
            return None
    
    async def send_photo(self, chat_id: Union[int, str], photo: str, caption: Optional[str] = None,
                        parse_mode: str = "HTML", 
                        reply_markup: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Invia una foto a una chat Telegram
        
        Args:
            chat_id: ID della chat
            photo: URL della foto o ID del file
            caption: Didascalia della foto
            parse_mode: Modalità di parsing del testo (HTML, Markdown)
            reply_markup: Markup per pulsanti inline o tastiera personalizzata
            
        Returns:
            Optional[Dict[str, Any]]: Risposta di Telegram, o None in caso di errore
        """
        if not self.session or not self.is_running:
            return None
        
        try:
            # Prepara i parametri
            params = {
                "chat_id": chat_id,
                "photo": photo,
                "parse_mode": parse_mode
            }
            
            # Aggiungi la didascalia se presente
            if caption:
                params["caption"] = caption
            
            # Aggiungi il markup se presente
            if reply_markup:
                params["reply_markup"] = json.dumps(reply_markup)
            
            # Invia la foto
            async with self.session.post(
                f"{self.base_url}/sendPhoto",
                json=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nell'invio della foto: {error_text}")
                    return None
                
                data = await response.json()
                if not data.get("ok", False):
                    logger.error(f"Errore nell'invio della foto: {data}")
                    return None
                
                return data.get("result")
        except Exception as e:
            logger.error(f"Eccezione nell'invio della foto: {e}")
            return None
    
    async def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None,
                                  show_alert: bool = False) -> bool:
        """
        Risponde a un callback query
        
        Args:
            callback_query_id: ID del callback query
            text: Testo da mostrare
            show_alert: Se mostrare un alert invece di una notifica
            
        Returns:
            bool: True se l'operazione è riuscita, False altrimenti
        """
        if not self.session or not self.is_running:
            return False
        
        try:
            # Prepara i parametri
            params = {
                "callback_query_id": callback_query_id
            }
            
            # Aggiungi il testo se presente
            if text:
                params["text"] = text
            
            # Imposta se mostrare un alert
            params["show_alert"] = show_alert
            
            # Invia la risposta
            async with self.session.post(
                f"{self.base_url}/answerCallbackQuery",
                json=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella risposta al callback query: {error_text}")
                    return False
                
                data = await response.json()
                if not data.get("ok", False):
                    logger.error(f"Errore nella risposta al callback query: {data}")
                    return False
                
                return True
        except Exception as e:
            logger.error(f"Eccezione nella risposta al callback query: {e}")
            return False
    
    async def edit_message_text(self, chat_id: Optional[Union[int, str]] = None, 
                              message_id: Optional[int] = None,
                              inline_message_id: Optional[str] = None,
                              text: str = "", parse_mode: str = "HTML",
                              disable_web_page_preview: bool = False,
                              reply_markup: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Modifica il testo di un messaggio
        
        Args:
            chat_id: ID della chat (non necessario per messaggi inline)
            message_id: ID del messaggio (non necessario per messaggi inline)
            inline_message_id: ID del messaggio inline (non necessario per messaggi normali)
            text: Nuovo testo
            parse_mode: Modalità di parsing del testo (HTML, Markdown)
            disable_web_page_preview: Se disabilitare l'anteprima dei link
            reply_markup: Nuovo markup per pulsanti inline
            
        Returns:
            Optional[Dict[str, Any]]: Risposta di Telegram, o None in caso di errore
        """
        if not self.session or not self.is_running:
            return None
        
        try:
            # Verifica che almeno uno tra (chat_id, message_id) e inline_message_id sia presente
            if not ((chat_id and message_id) or inline_message_id):
                logger.error("Devi specificare o (chat_id, message_id) o inline_message_id")
                return None
            
            # Prepara i parametri
            params = {
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": disable_web_page_preview
            }
            
            # Aggiungi i parametri per il messaggio normale
            if chat_id and message_id:
                params["chat_id"] = chat_id
                params["message_id"] = message_id
            
            # Aggiungi i parametri per il messaggio inline
            if inline_message_id:
                params["inline_message_id"] = inline_message_id
            
            # Aggiungi il markup se presente
            if reply_markup:
                params["reply_markup"] = json.dumps(reply_markup)
            
            # Modifica il messaggio
            async with self.session.post(
                f"{self.base_url}/editMessageText",
                json=params
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella modifica del messaggio: {error_text}")
                    return None
                
                data = await response.json()
                if not data.get("ok", False):
                    logger.error(f"Errore nella modifica del messaggio: {data}")
                    return None
                
                return data.get("result")
        except Exception as e:
            logger.error(f"Eccezione nella modifica del messaggio: {e}")
            return None
    
    async def send_template(self, chat_id: Union[int, str], template_name: str, 
                          params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Invia un messaggio utilizzando un template
        
        Args:
            chat_id: ID della chat
            template_name: Nome del template
            params: Parametri da sostituire nel template
            
        Returns:
            Optional[Dict[str, Any]]: Risposta di Telegram, o None in caso di errore
        """
        if not self.session or not self.is_running:
            return None
        
        try:
            # Ottieni il template
            template = self.message_templates.get(template_name)
            if not template:
                logger.error(f"Template non trovato: {template_name}")
                return None
            
            # Estrai le informazioni dal template
            text = template.get("text", "")
            parse_mode = template.get("parse_mode", "HTML")
            disable_web_page_preview = template.get("disable_web_page_preview", False)
            reply_markup = template.get("reply_markup")
            
            # Sostituisci i parametri nel testo
            if params:
                for key, value in params.items():
                    text = text.replace(f"{{{key}}}", str(value))
            
            # Invia il messaggio
            return await self.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Eccezione nell'invio del template: {e}")
            return None
    
    async def is_connected(self) -> bool:
        """
        Verifica se il connettore è connesso a Telegram
        
        Returns:
            bool: True se il connettore è connesso, False altrimenti
        """
        if not self.is_running or not self.session:
            return False
        
        # Verifica che il token sia ancora valido
        return await self.check_token()

# Funzione per creare un'istanza del connettore Telegram
def create_telegram_connector(config: Dict[str, Any], message_callback: Optional[Callable] = None) -> TelegramConnector:
    """
    Crea un'istanza del connettore Telegram
    
    Args:
        config: Configurazione del connettore
        message_callback: Callback per gestire i messaggi ricevuti da Telegram
        
    Returns:
        TelegramConnector: Istanza del connettore Telegram
    """
    return TelegramConnector(config, message_callback) 