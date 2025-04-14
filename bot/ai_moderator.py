import os
import re
import json
import logging
import asyncio
import aiohttp
import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple, Set

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/ai_moderator.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("AIModeratore")

class AIModeratore:
    """Sistema di moderazione automatica con AI per M4Bot"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Inizializza il sistema di moderazione automatica
        
        Args:
            config: Configurazione del sistema di moderazione
        """
        self.config = config
        self.moderation_threshold = config.get("moderation_threshold", 0.75)
        self.context_response_threshold = config.get("context_response_threshold", 0.65)
        self.api_url = config.get("ai_api_url", "https://api.m4bot.it/ai")
        self.api_key = config.get("ai_api_key", "")
        self.moderation_enabled = config.get("moderation_enabled", True)
        self.auto_response_enabled = config.get("auto_response_enabled", True)
        self.response_cooldown = config.get("response_cooldown", 300)  # 5 minuti
        
        # Cache dei contesti recenti e delle risposte
        self.recent_messages = []
        self.max_context_messages = config.get("max_context_messages", 10)
        self.last_auto_response = datetime.now() - timedelta(seconds=self.response_cooldown)
        
        # Cache delle decisioni di moderazione per evitare controlli duplicati
        self.moderation_cache = {}
        self.moderation_cache_max_size = 1000
        
        # Lista di pattern da ignorare (comandi bot, ecc.)
        self.ignore_patterns = [
            r"^\!",
            r"^\.",
            r"^\$",
            r"^\?",
            r"^\/",
        ]
        
        # Lista di parole chiave associate al bot
        self.bot_keywords = set([
            "m4bot", 
            "bot", 
            "chatbot", 
            "assistente", 
            "@m4bot"
        ])
        
        # Carica le frasi predefinite
        self.load_phrases()
        
        # Crea le directory necessarie
        os.makedirs("logs", exist_ok=True)
        
        logger.info("Sistema di moderazione automatica inizializzato")
    
    def load_phrases(self):
        """Carica le frasi predefinite per le risposte automatiche"""
        try:
            self.greeting_responses = [
                "Ciao! Come posso aiutarti?",
                "Salve! Sono qui per assisterti.",
                "Ehi, grazie per avermi chiamato! Cosa posso fare per te?",
                "Buongiorno! Come posso esserti utile oggi?",
                "Ciao! Sono M4Bot, il tuo assistente personale. Come posso aiutarti?"
            ]
            
            self.faq_responses = {
                "comandi": "Ecco i comandi disponibili: !aiuto, !stato, !info",
                "aiuto": "Ciao! Per ricevere assistenza, usa il comando !aiuto o scrivi la tua domanda in chat.",
                "streaming": "Lo streaming è attualmente attivo. Puoi seguirlo sul canale Twitch di M4Tronick.",
                "orari": "Gli orari di streaming sono disponibili sul canale Discord ufficiale.",
                "social": "Puoi seguire M4Tronick su Twitter, Instagram e YouTube. Cerca 'M4Tronick' su ogni piattaforma.",
                "donazioni": "Se vuoi supportare il canale, puoi fare una donazione attraverso il link disponibile nella descrizione dello streaming.",
                "discord": "Unisciti al server Discord ufficiale! Trovi il link nella descrizione dello streaming.",
                "abbonamento": "Abbonandoti al canale puoi supportare lo streamer e ottenere emoticon e badge esclusivi."
            }
            
            self.fallback_responses = [
                "Mi dispiace, non ho capito la domanda. Puoi ripeterla in modo diverso?",
                "Non sono sicuro di aver compreso correttamente. Potresti specificare meglio?",
                "Scusa, ma non ho informazioni su questo argomento.",
                "Non sono in grado di rispondere a questa domanda al momento.",
                "Potrei non essere il bot migliore per rispondere a questa domanda specifica."
            ]
            
            logger.info("Frasi predefinite caricate con successo")
            
        except Exception as e:
            logger.error(f"Errore nel caricamento delle frasi predefinite: {e}")
    
    async def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Processa un messaggio per moderazione e risposte automatiche
        
        Args:
            message: Il messaggio da processare
            
        Returns:
            Dict: Risultato del processamento con le eventuali azioni da eseguire
        """
        try:
            content = message.get("content", "")
            author = message.get("author", {})
            author_id = author.get("id", "")
            is_mod = author.get("is_mod", False)
            
            # Risultato predefinito (nessuna azione)
            result = {
                "action": "none",
                "moderated": False,
                "auto_response": None,
                "confidence": 0.0
            }
            
            # Skip se l'autore è un moderatore o il messaggio è vuoto
            if is_mod or not content.strip():
                return result
            
            # Skip se il messaggio corrisponde a un pattern da ignorare
            if self._should_ignore_message(content):
                return result
            
            # Aggiungi il messaggio al contesto recente
            self._add_to_recent_messages(message)
            
            # Controlla se il messaggio richiede moderazione
            if self.moderation_enabled:
                moderation_result = await self._check_moderation(content, author_id)
                if moderation_result["moderated"]:
                    result.update(moderation_result)
                    return result
            
            # Controlla se il messaggio menziona il bot e richiede una risposta
            if self.auto_response_enabled:
                response_result = await self._generate_response(content, author_id)
                if response_result["auto_response"]:
                    result.update(response_result)
            
            return result
            
        except Exception as e:
            logger.error(f"Errore nel processamento del messaggio: {e}")
            return {"action": "none", "moderated": False, "auto_response": None, "confidence": 0.0}
    
    def _should_ignore_message(self, content: str) -> bool:
        """
        Verifica se un messaggio dovrebbe essere ignorato
        
        Args:
            content: Contenuto del messaggio
            
        Returns:
            bool: True se il messaggio dovrebbe essere ignorato, False altrimenti
        """
        # Controlla i pattern da ignorare
        for pattern in self.ignore_patterns:
            if re.match(pattern, content.strip()):
                return True
        
        return False
    
    def _add_to_recent_messages(self, message: Dict[str, Any]):
        """
        Aggiunge un messaggio al contesto recente
        
        Args:
            message: Il messaggio da aggiungere
        """
        # Aggiungi il messaggio alla lista dei messaggi recenti
        self.recent_messages.append({
            "content": message.get("content", ""),
            "author": message.get("author", {}).get("display_name", "Utente"),
            "timestamp": message.get("timestamp", datetime.now().timestamp())
        })
        
        # Mantieni solo gli ultimi N messaggi
        if len(self.recent_messages) > self.max_context_messages:
            self.recent_messages = self.recent_messages[-self.max_context_messages:]
    
    async def _check_moderation(self, content: str, author_id: str) -> Dict[str, Any]:
        """
        Controlla se un messaggio richiede moderazione
        
        Args:
            content: Contenuto del messaggio
            author_id: ID dell'autore del messaggio
            
        Returns:
            Dict: Risultato della moderazione
        """
        try:
            # Risultato predefinito
            result = {
                "action": "none",
                "moderated": False,
                "reason": "",
                "confidence": 0.0
            }
            
            # Verifica se il messaggio è già nella cache
            cache_key = f"{author_id}:{content}"
            if cache_key in self.moderation_cache:
                return self.moderation_cache[cache_key]
            
            # Verifica se la cache è troppo grande
            if len(self.moderation_cache) > self.moderation_cache_max_size:
                # Rimuovi metà degli elementi più vecchi
                keys_to_keep = list(self.moderation_cache.keys())[-self.moderation_cache_max_size//2:]
                self.moderation_cache = {k: self.moderation_cache[k] for k in keys_to_keep}
            
            # Prepara i dati per la richiesta API
            data = {
                "text": content,
                "type": "moderation"
            }
            
            # Esegui la richiesta all'API di moderazione
            async with aiohttp.ClientSession() as session:
                headers = {"X-API-Key": self.api_key} if self.api_key else {}
                async with session.post(f"{self.api_url}/moderate", json=data, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Errore nella richiesta di moderazione: {response.status}")
                        return result
                    
                    # Leggi la risposta
                    api_result = await response.json()
                    
                    # Controlla se il messaggio richiede moderazione
                    if api_result.get("moderated", False) and api_result.get("confidence", 0.0) >= self.moderation_threshold:
                        result.update({
                            "action": api_result.get("action", "delete"),
                            "moderated": True,
                            "reason": api_result.get("reason", "Contenuto inappropriato"),
                            "confidence": api_result.get("confidence", 0.0)
                        })
            
            # Salva il risultato nella cache
            self.moderation_cache[cache_key] = result
            
            return result
            
        except Exception as e:
            logger.error(f"Errore nella moderazione: {e}")
            return {"action": "none", "moderated": False, "reason": "", "confidence": 0.0}
    
    async def _generate_response(self, content: str, author_id: str) -> Dict[str, Any]:
        """
        Genera una risposta automatica in base al contesto
        
        Args:
            content: Contenuto del messaggio
            author_id: ID dell'autore del messaggio
            
        Returns:
            Dict: Risultato della generazione della risposta
        """
        try:
            # Risultato predefinito
            result = {
                "action": "none",
                "auto_response": None,
                "confidence": 0.0
            }
            
            # Verifica se il messaggio menziona il bot
            should_respond = self._check_if_should_respond(content)
            
            # Skip se non dovrebbe rispondere o se è in cooldown
            if not should_respond or not self._can_respond_now():
                return result
            
            # Cerca prima nelle risposte predefinite
            response = self._get_predefined_response(content)
            if response:
                result.update({
                    "action": "respond",
                    "auto_response": response,
                    "confidence": 0.9
                })
                self.last_auto_response = datetime.now()
                return result
            
            # Prepara il contesto per la richiesta API
            context = self._prepare_context()
            
            # Prepara i dati per la richiesta API
            data = {
                "text": content,
                "context": context,
                "type": "response"
            }
            
            # Esegui la richiesta all'API di generazione della risposta
            async with aiohttp.ClientSession() as session:
                headers = {"X-API-Key": self.api_key} if self.api_key else {}
                async with session.post(f"{self.api_url}/respond", json=data, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Errore nella richiesta di generazione della risposta: {response.status}")
                        return result
                    
                    # Leggi la risposta
                    api_result = await response.json()
                    
                    # Controlla se la risposta è valida
                    if api_result.get("response") and api_result.get("confidence", 0.0) >= self.context_response_threshold:
                        result.update({
                            "action": "respond",
                            "auto_response": api_result.get("response"),
                            "confidence": api_result.get("confidence", 0.0)
                        })
                        self.last_auto_response = datetime.now()
            
            # Fallback a una risposta generica se non è stata generata una risposta
            if not result["auto_response"]:
                result.update({
                    "action": "respond",
                    "auto_response": random.choice(self.fallback_responses),
                    "confidence": 0.5
                })
                self.last_auto_response = datetime.now()
            
            return result
            
        except Exception as e:
            logger.error(f"Errore nella generazione della risposta: {e}")
            return {"action": "none", "auto_response": None, "confidence": 0.0}
    
    def _check_if_should_respond(self, content: str) -> bool:
        """
        Verifica se il bot dovrebbe rispondere a un messaggio
        
        Args:
            content: Contenuto del messaggio
            
        Returns:
            bool: True se il bot dovrebbe rispondere, False altrimenti
        """
        # Converti il contenuto in minuscolo per confronto case-insensitive
        content_lower = content.lower()
        
        # Verifica se il messaggio contiene parole chiave associate al bot
        for keyword in self.bot_keywords:
            if keyword.lower() in content_lower:
                return True
        
        # Verifica se il messaggio contiene un punto interrogativo (potrebbe essere una domanda)
        if "?" in content and len(content) > 10:
            # Controlla se ci sono abbastanza messaggi di contesto
            if len(self.recent_messages) >= 3:
                return True
        
        return False
    
    def _can_respond_now(self) -> bool:
        """
        Verifica se il bot può rispondere ora (controllo cooldown)
        
        Returns:
            bool: True se il bot può rispondere, False altrimenti
        """
        now = datetime.now()
        time_diff = (now - self.last_auto_response).total_seconds()
        
        return time_diff >= self.response_cooldown
    
    def _get_predefined_response(self, content: str) -> Optional[str]:
        """
        Ottiene una risposta predefinita per un messaggio
        
        Args:
            content: Contenuto del messaggio
            
        Returns:
            Optional[str]: Risposta predefinita o None se non trovata
        """
        # Converti il contenuto in minuscolo per confronto case-insensitive
        content_lower = content.lower()
        
        # Controlla se il messaggio è un saluto
        if any(greeting in content_lower for greeting in ["ciao", "salve", "hey", "buongiorno", "buonasera"]):
            # Verifica se il messaggio contiene una parola chiave associata al bot
            if any(keyword.lower() in content_lower for keyword in self.bot_keywords):
                return random.choice(self.greeting_responses)
        
        # Controlla se il messaggio corrisponde a una FAQ
        for keyword, response in self.faq_responses.items():
            if keyword.lower() in content_lower:
                return response
        
        return None
    
    def _prepare_context(self) -> List[Dict[str, Any]]:
        """
        Prepara il contesto della conversazione per la generazione della risposta
        
        Returns:
            List: Lista dei messaggi di contesto
        """
        # Copia i messaggi recenti per evitare modifiche durante l'elaborazione
        context = self.recent_messages.copy()
        
        # Ordina i messaggi per timestamp
        context.sort(key=lambda x: x.get("timestamp", 0))
        
        return context

# Funzione per creare un'istanza del sistema di moderazione automatica
def create_ai_moderator(config: Dict[str, Any]) -> AIModeratore:
    """
    Crea un'istanza del sistema di moderazione automatica
    
    Args:
        config: Configurazione del sistema di moderazione
        
    Returns:
        AIModeratore: Istanza del sistema di moderazione automatica
    """
    return AIModeratore(config) 