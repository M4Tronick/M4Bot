import os
import json
import logging
import asyncio
import aiohttp
import aiofiles
from typing import Dict, List, Optional, Any, Callable

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/telegram_connector.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("TelegramConnector")

class TelegramConnector:
    """Connettore per Telegram che gestisce l'integrazione con i bot Telegram"""
    
    def __init__(self, config: Dict[str, Any], message_callback: Optional[Callable] = None):
        """
        Inizializza il connettore Telegram
        
        Args:
            config: Configurazione del connettore
            message_callback: Callback per gestire i messaggi ricevuti da Telegram
        """
        # Inizializza le variabili
        self.config = config
        self.token = config.get("telegram_token", "")
        self.chat_ids = config.get("telegram_chat_ids", [])
        self.command_prefix = config.get("telegram_command_prefix", "/")
        self.message_callback = message_callback
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        
        # Ultimo update_id ricevuto
        self.last_update_id = 0
        
        # Client HTTP
        self.session = None
        
        # Flag per indicare se il bot è in esecuzione
        self.is_running = False
        
        # Task di polling
        self.polling_task = None
        
        # Registro dei messaggi sincronizzati per evitare duplicati
        self.synced_messages = {}
        
        # Crea le directory necessarie
        os.makedirs("logs", exist_ok=True)
        
        logger.info("Connettore Telegram inizializzato")
    
    async def start(self):
        """Avvia il bot Telegram"""
        if not self.token:
            logger.error("Token Telegram non configurato")
            return False
        
        try:
            # Crea la sessione HTTP
            self.session = aiohttp.ClientSession()
            
            # Verifica che il token sia valido
            me = await self.get_me()
            if not me:
                logger.error("Impossibile connettersi all'API Telegram. Verifica il token.")
                await self.session.close()
                self.session = None
                return False
            
            logger.info(f"Bot Telegram connesso come {me.get('username', 'Unknown')}")
            
            # Avvia il task di polling
            self.is_running = True
            self.polling_task = asyncio.create_task(self._polling_loop())
            
            return True
        except Exception as e:
            logger.error(f"Errore nell'avvio del bot Telegram: {e}")
            if self.session:
                await self.session.close()
                self.session = None
            return False
    
    async def stop(self):
        """Ferma il bot Telegram"""
        if self.is_running:
            try:
                self.is_running = False
                
                if self.polling_task:
                    self.polling_task.cancel()
                    try:
                        await self.polling_task
                    except asyncio.CancelledError:
                        pass
                    self.polling_task = None
                
                if self.session:
                    await self.session.close()
                    self.session = None
                
                logger.info("Bot Telegram disconnesso")
                return True
            except Exception as e:
                logger.error(f"Errore nella chiusura del bot Telegram: {e}")
                return False
        return True
    
    async def _polling_loop(self):
        """Loop di polling per ricevere aggiornamenti da Telegram"""
        try:
            while self.is_running:
                try:
                    updates = await self.get_updates()
                    
                    if updates:
                        for update in updates:
                            await self._process_update(update)
                    
                    # Pausa breve tra le richieste di polling
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    # Il task è stato cancellato, esci dal loop
                    break
                except Exception as e:
                    logger.error(f"Errore nel polling: {e}")
                    # Pausa più lunga in caso di errore
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            # Task cancellato
            pass
        finally:
            logger.info("Polling loop terminato")
    
    async def _process_update(self, update: Dict[str, Any]):
        """
        Processa un aggiornamento ricevuto da Telegram
        
        Args:
            update: Aggiornamento da processare
        """
        update_id = update.get("update_id", 0)
        
        # Aggiorna l'ultimo update_id
        if update_id > self.last_update_id:
            self.last_update_id = update_id
        
        # Processa messaggi
        if "message" in update:
            await self._process_message(update["message"])
        
        # Processa callback query (per i pulsanti inline)
        elif "callback_query" in update:
            await self._process_callback_query(update["callback_query"])
    
    async def _process_message(self, message: Dict[str, Any]):
        """
        Processa un messaggio ricevuto da Telegram
        
        Args:
            message: Messaggio da processare
        """
        # Estrai le informazioni principali
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "")
        user = message.get("from", {})
        message_id = message.get("message_id")
        
        # Se il chat_id non è autorizzato e la whitelist è attiva, ignora
        if self.chat_ids and str(chat_id) not in [str(cid) for cid in self.chat_ids]:
            return
        
        # Verifica se è un comando
        is_command = text.startswith(self.command_prefix)
        
        # Crea un ID univoco per il messaggio
        unique_id = f"telegram_{message_id}"
        
        # Verifica se il messaggio è già stato sincronizzato
        if unique_id in self.synced_messages:
            return
        
        # Aggiunge il messaggio al registro dei messaggi sincronizzati
        self.synced_messages[unique_id] = {
            "timestamp": message.get("date", 0),
            "platform": "telegram",
            "chat_id": str(chat_id)
        }
        
        # Mantieni solo gli ultimi 1000 messaggi nel registro
        if len(self.synced_messages) > 1000:
            # Ordina per timestamp e rimuovi i più vecchi
            sorted_messages = sorted(
                self.synced_messages.items(),
                key=lambda x: x[1]["timestamp"]
            )
            self.synced_messages = dict(sorted_messages[500:])
        
        # Formatta il messaggio per la sincronizzazione
        formatted_message = {
            "id": unique_id,
            "platform": "telegram",
            "channel_id": str(chat_id),
            "channel_name": message.get("chat", {}).get("title", str(chat_id)),
            "author": {
                "id": str(user.get("id")),
                "username": user.get("username", ""),
                "display_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
                "is_mod": False  # In Telegram i moderatori sono definiti diversamente
            },
            "content": text,
            "timestamp": message.get("date", 0),
            "attachments": []  # Implementare se necessario
        }
        
        # Se è un comando, gestiscilo
        if is_command:
            # Per ora, invia solo al callback
            pass
        
        # Invia il messaggio al callback se presente
        if self.message_callback:
            try:
                await self.message_callback(formatted_message)
            except Exception as e:
                logger.error(f"Errore nel callback del messaggio: {e}")
    
    async def _process_callback_query(self, callback_query: Dict[str, Any]):
        """
        Processa una callback query ricevuta da Telegram (pulsanti inline)
        
        Args:
            callback_query: Callback query da processare
        """
        # Implementare se necessario
        pass
    
    async def get_updates(self) -> List[Dict[str, Any]]:
        """
        Ottiene gli aggiornamenti dal server Telegram
        
        Returns:
            List[Dict[str, Any]]: Lista di aggiornamenti
        """
        if not self.session:
            return []
        
        params = {
            "offset": self.last_update_id + 1,
            "timeout": 30
        }
        
        try:
            async with self.session.get(f"{self.base_url}/getUpdates", params=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella richiesta getUpdates: {error_text}")
                    return []
                
                data = await response.json()
                
                if data.get("ok", False):
                    return data.get("result", [])
                else:
                    logger.error(f"Errore nella risposta getUpdates: {data.get('description', 'Unknown error')}")
                    return []
        except Exception as e:
            logger.error(f"Eccezione nella richiesta getUpdates: {e}")
            return []
    
    async def get_me(self) -> Dict[str, Any]:
        """
        Ottiene informazioni sul bot
        
        Returns:
            Dict[str, Any]: Informazioni sul bot
        """
        if not self.session:
            return {}
        
        try:
            async with self.session.get(f"{self.base_url}/getMe") as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nella richiesta getMe: {error_text}")
                    return {}
                
                data = await response.json()
                
                if data.get("ok", False):
                    return data.get("result", {})
                else:
                    logger.error(f"Errore nella risposta getMe: {data.get('description', 'Unknown error')}")
                    return {}
        except Exception as e:
            logger.error(f"Eccezione nella richiesta getMe: {e}")
            return {}
    
    async def send_message(self, chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
        """
        Invia un messaggio a una chat Telegram
        
        Args:
            chat_id: ID della chat
            text: Testo da inviare
            parse_mode: Modalità di parsing del testo (HTML o Markdown)
            
        Returns:
            bool: True se l'invio è riuscito, False altrimenti
        """
        if not self.session:
            return False
        
        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        
        try:
            async with self.session.post(f"{self.base_url}/sendMessage", json=params) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Errore nell'invio del messaggio: {error_text}")
                    return False
                
                data = await response.json()
                
                if data.get("ok", False):
                    return True
                else:
                    logger.error(f"Errore nella risposta sendMessage: {data.get('description', 'Unknown error')}")
                    return False
        except Exception as e:
            logger.error(f"Eccezione nell'invio del messaggio: {e}")
            return False
    
    async def broadcast_message(self, text: str, parse_mode: str = "HTML") -> Dict[str, bool]:
        """
        Invia un messaggio a tutte le chat configurate
        
        Args:
            text: Testo da inviare
            parse_mode: Modalità di parsing del testo (HTML o Markdown)
            
        Returns:
            Dict[str, bool]: Dizionario con gli ID delle chat e l'esito dell'invio
        """
        results = {}
        
        for chat_id in self.chat_ids:
            result = await self.send_message(chat_id, text, parse_mode)
            results[str(chat_id)] = result
        
        return results
    
    async def sync_message_to_telegram(self, message: Dict[str, Any]) -> bool:
        """
        Sincronizza un messaggio da un'altra piattaforma a Telegram
        
        Args:
            message: Il messaggio da sincronizzare
            
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
                "channel_id": message.get("channel_id", "")
            }
            
            # Mantieni solo gli ultimi 1000 messaggi nel registro
            if len(self.synced_messages) > 1000:
                # Ordina per timestamp e rimuovi i più vecchi
                sorted_messages = sorted(
                    self.synced_messages.items(),
                    key=lambda x: x[1]["timestamp"]
                )
                self.synced_messages = dict(sorted_messages[500:])
            
            # Verifica se ci sono chat configurate
            if not self.chat_ids or not self.is_running:
                return False
            
            # Formatta il messaggio per Telegram
            platform = message.get("platform", "unknown")
            author_name = message.get("author", {}).get("display_name", "Utente")
            content = message.get("content", "")
            
            formatted_content = f"[{platform.upper()}] {author_name}: {content}"
            
            # Invia il messaggio a tutte le chat configurate
            results = await self.broadcast_message(formatted_content)
            
            # Se almeno una chat ha ricevuto il messaggio, considera l'operazione riuscita
            return any(results.values())
            
        except Exception as e:
            logger.error(f"Errore nella sincronizzazione del messaggio a Telegram: {e}")
            return False
    
    async def is_connected(self) -> bool:
        """
        Verifica se il bot è connesso a Telegram
        
        Returns:
            bool: True se il bot è connesso, False altrimenti
        """
        return self.is_running and self.session is not None

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