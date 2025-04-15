"""
Plugin per la moderazione automatica dei contenuti tramite intelligenza artificiale
"""

import os
import json
import logging
import asyncio
import aiohttp
import re
import time
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template, current_app

# Logger
logger = logging.getLogger(__name__)

# Path per i file della moderazione
MODERATION_DIR = "data/moderation"
MODERATION_CONFIG_FILE = os.path.join(MODERATION_DIR, "config.json")
MODERATION_RULES_FILE = os.path.join(MODERATION_DIR, "rules.json")
MODERATION_LOG_FILE = os.path.join(MODERATION_DIR, "moderation_log.json")

# Blueprint
moderation_blueprint = Blueprint('ai_moderation', __name__)

class ModerationManager:
    """Gestore della moderazione AI"""
    
    def __init__(self, app):
        """
        Inizializza il gestore della moderazione
        
        Args:
            app: L'applicazione Flask/Quart
        """
        self.app = app
        self.config = {}
        self.rules = []
        self.banned_words = set()
        self.custom_patterns = []
        self.moderation_log = []
        self.session = None
        self.is_running = False
        
        # Crea le directory necessarie
        os.makedirs(MODERATION_DIR, exist_ok=True)
        
        # Carica la configurazione e le regole
        self._load_config()
        self._load_rules()
        self._load_log()
        
        # Crea la sessione HTTP
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._create_session())
        
        logger.info("Gestore della moderazione AI inizializzato")
    
    def _load_config(self):
        """Carica la configurazione della moderazione"""
        if os.path.exists(MODERATION_CONFIG_FILE):
            try:
                with open(MODERATION_CONFIG_FILE, 'r') as f:
                    self.config = json.load(f)
                logger.info("Configurazione della moderazione caricata")
            except Exception as e:
                logger.error(f"Errore nel caricamento della configurazione: {e}")
                self.config = self._get_default_config()
        else:
            self.config = self._get_default_config()
            self._save_config()
    
    def _get_default_config(self):
        """Restituisce la configurazione predefinita"""
        return {
            "enabled": True,
            "service": "local",  # local, openai, perspective, custom
            "sensitivity": "medium",  # low, medium, high
            "auto_moderation": True,
            "moderation_actions": {
                "spam": ["delete"],
                "offensive": ["delete", "warn"],
                "hate_speech": ["delete", "timeout"],
                "harassment": ["delete", "timeout"],
                "sexual": ["delete", "ban"],
                "self_harm": ["delete", "report"],
                "violence": ["delete", "report"]
            },
            "openai": {
                "api_key": "",
                "model": "text-moderation-latest"
            },
            "perspective": {
                "api_key": ""
            },
            "custom": {
                "endpoint": "",
                "api_key": ""
            },
            "language_detection": True,
            "supported_languages": ["it", "en", "es", "fr", "de"],
            "learning_mode": False,
            "learn_from_mods": True
        }
    
    def _save_config(self):
        """Salva la configurazione della moderazione"""
        try:
            with open(MODERATION_CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.debug("Configurazione della moderazione salvata")
        except Exception as e:
            logger.error(f"Errore nel salvataggio della configurazione: {e}")
    
    def _load_rules(self):
        """Carica le regole di moderazione"""
        if os.path.exists(MODERATION_RULES_FILE):
            try:
                with open(MODERATION_RULES_FILE, 'r') as f:
                    rules_data = json.load(f)
                    
                    # Estrai le regole
                    self.rules = rules_data.get("rules", [])
                    
                    # Estrai le parole bandite
                    banned_words = rules_data.get("banned_words", [])
                    self.banned_words = set(banned_words)
                    
                    # Estrai i pattern personalizzati
                    self.custom_patterns = rules_data.get("custom_patterns", [])
                    
                    # Compila i pattern personalizzati
                    for pattern in self.custom_patterns:
                        if "compiled" not in pattern:
                            try:
                                pattern["compiled"] = re.compile(pattern["pattern"], re.IGNORECASE if pattern.get("case_insensitive", True) else 0)
                            except:
                                pattern["compiled"] = None
                
                logger.info(f"Regole di moderazione caricate: {len(self.rules)} regole, {len(self.banned_words)} parole bandite, {len(self.custom_patterns)} pattern")
            except Exception as e:
                logger.error(f"Errore nel caricamento delle regole: {e}")
                self._init_default_rules()
        else:
            self._init_default_rules()
    
    def _init_default_rules(self):
        """Inizializza le regole predefinite"""
        self.rules = [
            {
                "id": "spam",
                "name": "Spam",
                "description": "Messaggi ripetitivi, pubblicità o link non richiesti",
                "threshold": 0.7
            },
            {
                "id": "offensive",
                "name": "Linguaggio offensivo",
                "description": "Parolacce e linguaggio offensivo generico",
                "threshold": 0.8
            },
            {
                "id": "hate_speech",
                "name": "Incitamento all'odio",
                "description": "Contenuti che incitano all'odio contro gruppi protetti",
                "threshold": 0.7
            },
            {
                "id": "harassment",
                "name": "Molestie",
                "description": "Contenuti mirati a molestare o intimidire altri utenti",
                "threshold": 0.7
            },
            {
                "id": "sexual",
                "name": "Contenuti sessuali",
                "description": "Contenuti sessualmente espliciti o inappropriati",
                "threshold": 0.7
            },
            {
                "id": "self_harm",
                "name": "Autolesionismo",
                "description": "Contenuti che promuovono l'autolesionismo o il suicidio",
                "threshold": 0.6
            },
            {
                "id": "violence",
                "name": "Violenza",
                "description": "Contenuti che promuovono o glorificano la violenza",
                "threshold": 0.7
            }
        ]
        
        # Parole bandite predefinite (lista vuota, da personalizzare)
        self.banned_words = set()
        
        # Pattern personalizzati predefiniti
        self.custom_patterns = [
            {
                "id": "excessive_caps",
                "name": "Uso eccessivo di maiuscole",
                "pattern": r"^[A-Z]{10,}$|^[A-Z0-9\s]{20,}$",
                "case_insensitive": False,
                "category": "spam",
                "compiled": None
            },
            {
                "id": "excessive_emojis",
                "name": "Uso eccessivo di emoji",
                "pattern": r"(\p{Emoji_Presentation}|\p{Extended_Pictographic}){10,}",
                "case_insensitive": True,
                "category": "spam",
                "compiled": None
            },
            {
                "id": "url_spam",
                "name": "Spam di URL",
                "pattern": r"(https?:\/\/[^\s]{2,}|www\.[^\s]{2,})\s*(https?:\/\/[^\s]{2,}|www\.[^\s]{2,})",
                "case_insensitive": True,
                "category": "spam",
                "compiled": None
            }
        ]
        
        # Compila i pattern personalizzati
        for pattern in self.custom_patterns:
            try:
                pattern["compiled"] = re.compile(pattern["pattern"], re.IGNORECASE if pattern.get("case_insensitive", True) else 0)
            except:
                pattern["compiled"] = None
        
        # Salva le regole
        self._save_rules()
    
    def _save_rules(self):
        """Salva le regole di moderazione"""
        try:
            # Prepara i dati da salvare
            rules_data = {
                "rules": self.rules,
                "banned_words": list(self.banned_words),
                "custom_patterns": [{k: v for k, v in pattern.items() if k != "compiled"} for pattern in self.custom_patterns]
            }
            
            with open(MODERATION_RULES_FILE, 'w') as f:
                json.dump(rules_data, f, indent=2)
            
            logger.debug("Regole di moderazione salvate")
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle regole: {e}")
    
    def _load_log(self):
        """Carica il log della moderazione"""
        if os.path.exists(MODERATION_LOG_FILE):
            try:
                with open(MODERATION_LOG_FILE, 'r') as f:
                    self.moderation_log = json.load(f)
                
                # Limita il log a 1000 voci
                if len(self.moderation_log) > 1000:
                    self.moderation_log = self.moderation_log[-1000:]
                
                logger.info(f"Log della moderazione caricato: {len(self.moderation_log)} voci")
            except Exception as e:
                logger.error(f"Errore nel caricamento del log: {e}")
                self.moderation_log = []
        else:
            self.moderation_log = []
    
    def _save_log(self):
        """Salva il log della moderazione"""
        try:
            with open(MODERATION_LOG_FILE, 'w') as f:
                json.dump(self.moderation_log, f, indent=2)
            logger.debug("Log della moderazione salvato")
        except Exception as e:
            logger.error(f"Errore nel salvataggio del log: {e}")
    
    async def _create_session(self):
        """Crea la sessione HTTP"""
        try:
            self.session = aiohttp.ClientSession()
            self.is_running = True
            logger.debug("Sessione HTTP creata")
        except Exception as e:
            logger.error(f"Errore nella creazione della sessione HTTP: {e}")
    
    async def close(self):
        """Chiude il gestore della moderazione"""
        try:
            if self.session:
                await self.session.close()
                self.session = None
            
            self.is_running = False
            logger.info("Gestore della moderazione chiuso")
        except Exception as e:
            logger.error(f"Errore nella chiusura del gestore della moderazione: {e}")
    
    async def moderate_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Modera un messaggio
        
        Args:
            message: Il messaggio da moderare
            
        Returns:
            Dict[str, Any]: Risultato della moderazione
        """
        # Verifica se la moderazione è abilitata
        if not self.config.get("enabled", True):
            return {"flagged": False, "categories": {}, "message": message}
        
        try:
            # Estrai il testo del messaggio
            content = message.get("content", "")
            
            # Se il messaggio è vuoto, non fare nulla
            if not content:
                return {"flagged": False, "categories": {}, "message": message}
            
            # Verifica le parole bandite
            banned_word_matches = self._check_banned_words(content)
            
            # Verifica i pattern personalizzati
            pattern_matches = self._check_custom_patterns(content)
            
            # Prepara il risultato iniziale
            result = {
                "flagged": False,
                "categories": {},
                "matches": [],
                "message": message,
                "timestamp": datetime.now().timestamp()
            }
            
            # Aggiungi le corrispondenze trovate
            if banned_word_matches:
                result["flagged"] = True
                result["matches"].extend([{"type": "banned_word", "word": word} for word in banned_word_matches])
                
                # Aggiungi le categorie corrispondenti
                for word in banned_word_matches:
                    # Associa la parola bandita alla categoria offensive di default
                    if "offensive" not in result["categories"]:
                        result["categories"]["offensive"] = 1.0
            
            # Aggiungi i pattern corrispondenti
            if pattern_matches:
                result["flagged"] = True
                result["matches"].extend([{
                    "type": "pattern",
                    "pattern_id": match["id"],
                    "pattern_name": match["name"],
                    "category": match["category"]
                } for match in pattern_matches])
                
                # Aggiungi le categorie corrispondenti
                for match in pattern_matches:
                    category = match.get("category", "spam")
                    if category not in result["categories"]:
                        result["categories"][category] = 1.0
            
            # Se non ci sono corrispondenze locali, usa il servizio di moderazione configurato
            if not result["flagged"] and self.config.get("service") != "local":
                service_result = await self._moderate_with_service(content)
                
                # Aggiorna il risultato
                if service_result.get("flagged", False):
                    result["flagged"] = True
                    result["categories"].update(service_result.get("categories", {}))
                    result["service_response"] = service_result.get("response")
            
            # Registra la moderazione nel log
            if result["flagged"]:
                self._log_moderation(result)
            
            return result
        except Exception as e:
            logger.error(f"Errore nella moderazione del messaggio: {e}")
            return {"flagged": False, "categories": {}, "message": message}
    
    def _check_banned_words(self, content: str) -> List[str]:
        """
        Verifica se il contenuto contiene parole bandite
        
        Args:
            content: Il contenuto da verificare
            
        Returns:
            List[str]: Le parole bandite trovate
        """
        if not self.banned_words:
            return []
        
        # Converti il contenuto in minuscolo
        content_lower = content.lower()
        
        # Dividi il contenuto in parole
        words = re.findall(r'\b\w+\b', content_lower)
        
        # Verifica le parole bandite
        matches = []
        for word in words:
            if word in self.banned_words:
                matches.append(word)
        
        return matches
    
    def _check_custom_patterns(self, content: str) -> List[Dict[str, Any]]:
        """
        Verifica se il contenuto corrisponde a pattern personalizzati
        
        Args:
            content: Il contenuto da verificare
            
        Returns:
            List[Dict[str, Any]]: I pattern corrispondenti
        """
        if not self.custom_patterns:
            return []
        
        matches = []
        for pattern in self.custom_patterns:
            if pattern.get("compiled") and pattern["compiled"].search(content):
                matches.append(pattern)
        
        return matches
    
    async def _moderate_with_service(self, content: str) -> Dict[str, Any]:
        """
        Modera il contenuto utilizzando un servizio esterno
        
        Args:
            content: Il contenuto da moderare
            
        Returns:
            Dict[str, Any]: Risultato della moderazione
        """
        service = self.config.get("service")
        
        if service == "openai":
            return await self._moderate_with_openai(content)
        elif service == "perspective":
            return await self._moderate_with_perspective(content)
        elif service == "custom":
            return await self._moderate_with_custom(content)
        else:
            return {"flagged": False, "categories": {}}
    
    async def _moderate_with_openai(self, content: str) -> Dict[str, Any]:
        """
        Modera il contenuto utilizzando l'API di moderazione di OpenAI
        
        Args:
            content: Il contenuto da moderare
            
        Returns:
            Dict[str, Any]: Risultato della moderazione
        """
        api_key = self.config.get("openai", {}).get("api_key")
        model = self.config.get("openai", {}).get("model", "text-moderation-latest")
        
        if not api_key or not self.session:
            return {"flagged": False, "categories": {}}
        
        try:
            # Prepara la richiesta
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}"
            }
            
            data = {
                "input": content,
                "model": model
            }
            
            # Effettua la richiesta
            async with self.session.post(
                "https://api.openai.com/v1/moderations",
                headers=headers,
                json=data
            ) as response:
                if response.status != 200:
                    logger.error(f"Errore nella moderazione con OpenAI: {await response.text()}")
                    return {"flagged": False, "categories": {}}
                
                # Analizza la risposta
                response_data = await response.json()
                result = response_data.get("results", [{}])[0]
                
                # Mappa le categorie
                categories = {}
                category_scores = result.get("category_scores", {})
                
                # Mappa tra categorie OpenAI e categorie interne
                category_map = {
                    "harassment": "harassment",
                    "harassment/threatening": "harassment",
                    "hate": "hate_speech",
                    "hate/threatening": "hate_speech",
                    "self-harm": "self_harm",
                    "self-harm/intent": "self_harm",
                    "self-harm/instructions": "self_harm",
                    "sexual": "sexual",
                    "sexual/minors": "sexual",
                    "violence": "violence",
                    "violence/graphic": "violence"
                }
                
                # Mappa le categorie
                for openai_category, score in category_scores.items():
                    internal_category = category_map.get(openai_category)
                    if internal_category:
                        if internal_category in categories:
                            categories[internal_category] = max(categories[internal_category], score)
                        else:
                            categories[internal_category] = score
                
                # Verifica se il messaggio è stato flaggato
                flagged = result.get("flagged", False)
                
                # Aggiungi la risposta completa
                response = {
                    "flagged": flagged,
                    "categories": categories,
                    "response": response_data
                }
                
                return response
        except Exception as e:
            logger.error(f"Errore nella moderazione con OpenAI: {e}")
            return {"flagged": False, "categories": {}}
    
    async def _moderate_with_perspective(self, content: str) -> Dict[str, Any]:
        """
        Modera il contenuto utilizzando l'API Perspective
        
        Args:
            content: Il contenuto da moderare
            
        Returns:
            Dict[str, Any]: Risultato della moderazione
        """
        api_key = self.config.get("perspective", {}).get("api_key")
        
        if not api_key or not self.session:
            return {"flagged": False, "categories": {}}
        
        try:
            # Prepara la richiesta
            url = f"https://commentanalyzer.googleapis.com/v1alpha1/comments:analyze?key={api_key}"
            
            data = {
                "comment": {"text": content},
                "languages": ["it", "en"],
                "requestedAttributes": {
                    "TOXICITY": {},
                    "SEVERE_TOXICITY": {},
                    "IDENTITY_ATTACK": {},
                    "INSULT": {},
                    "PROFANITY": {},
                    "THREAT": {},
                    "SEXUALLY_EXPLICIT": {}
                }
            }
            
            # Effettua la richiesta
            async with self.session.post(url, json=data) as response:
                if response.status != 200:
                    logger.error(f"Errore nella moderazione con Perspective: {await response.text()}")
                    return {"flagged": False, "categories": {}}
                
                # Analizza la risposta
                response_data = await response.json()
                attribute_scores = response_data.get("attributeScores", {})
                
                # Mappa le categorie
                categories = {}
                
                # Mappa tra attributi Perspective e categorie interne
                attribute_map = {
                    "TOXICITY": "offensive",
                    "SEVERE_TOXICITY": "offensive",
                    "IDENTITY_ATTACK": "hate_speech",
                    "INSULT": "harassment",
                    "PROFANITY": "offensive",
                    "THREAT": "violence",
                    "SEXUALLY_EXPLICIT": "sexual"
                }
                
                # Mappa le categorie e calcola se il messaggio è flaggato
                flagged = False
                for attribute, score_data in attribute_scores.items():
                    score = score_data.get("summaryScore", {}).get("value", 0)
                    internal_category = attribute_map.get(attribute)
                    
                    if internal_category:
                        if internal_category in categories:
                            categories[internal_category] = max(categories[internal_category], score)
                        else:
                            categories[internal_category] = score
                        
                        # Verifica se il punteggio supera la soglia per la categoria
                        threshold = self._get_threshold_for_category(internal_category)
                        if score >= threshold:
                            flagged = True
                
                # Aggiungi la risposta completa
                response = {
                    "flagged": flagged,
                    "categories": categories,
                    "response": response_data
                }
                
                return response
        except Exception as e:
            logger.error(f"Errore nella moderazione con Perspective: {e}")
            return {"flagged": False, "categories": {}}
    
    async def _moderate_with_custom(self, content: str) -> Dict[str, Any]:
        """
        Modera il contenuto utilizzando un endpoint personalizzato
        
        Args:
            content: Il contenuto da moderare
            
        Returns:
            Dict[str, Any]: Risultato della moderazione
        """
        endpoint = self.config.get("custom", {}).get("endpoint")
        api_key = self.config.get("custom", {}).get("api_key")
        
        if not endpoint or not self.session:
            return {"flagged": False, "categories": {}}
        
        try:
            # Prepara la richiesta
            headers = {}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            data = {
                "text": content
            }
            
            # Effettua la richiesta
            async with self.session.post(endpoint, headers=headers, json=data) as response:
                if response.status != 200:
                    logger.error(f"Errore nella moderazione con endpoint personalizzato: {await response.text()}")
                    return {"flagged": False, "categories": {}}
                
                # Analizza la risposta
                response_data = await response.json()
                
                # Estrai il risultato
                flagged = response_data.get("flagged", False)
                categories = response_data.get("categories", {})
                
                # Aggiungi la risposta completa
                response = {
                    "flagged": flagged,
                    "categories": categories,
                    "response": response_data
                }
                
                return response
        except Exception as e:
            logger.error(f"Errore nella moderazione con endpoint personalizzato: {e}")
            return {"flagged": False, "categories": {}}
    
    def _get_threshold_for_category(self, category: str) -> float:
        """
        Ottiene la soglia per una categoria
        
        Args:
            category: La categoria
            
        Returns:
            float: La soglia
        """
        # Trova la regola corrispondente
        for rule in self.rules:
            if rule.get("id") == category:
                threshold = rule.get("threshold", 0.7)
                
                # Aggiusta la soglia in base alla sensibilità
                sensitivity = self.config.get("sensitivity", "medium")
                if sensitivity == "low":
                    threshold += 0.1
                elif sensitivity == "high":
                    threshold -= 0.1
                
                # Limita la soglia tra 0 e 1
                return max(0.0, min(1.0, threshold))
        
        # Soglia predefinita
        return 0.7
    
    def _log_moderation(self, result: Dict[str, Any]) -> None:
        """
        Registra un'azione di moderazione nel log
        
        Args:
            result: Il risultato della moderazione
        """
        try:
            # Crea una copia delle informazioni rilevanti
            log_entry = {
                "timestamp": result.get("timestamp", datetime.now().timestamp()),
                "flagged": result.get("flagged", False),
                "categories": result.get("categories", {}),
                "message": {
                    "content": result.get("message", {}).get("content", ""),
                    "author": result.get("message", {}).get("author", {}).get("username", "unknown"),
                    "platform": result.get("message", {}).get("platform", "unknown")
                }
            }
            
            # Aggiungi l'azione al log
            self.moderation_log.append(log_entry)
            
            # Limita il log a 1000 voci
            if len(self.moderation_log) > 1000:
                self.moderation_log = self.moderation_log[-1000:]
            
            # Salva il log
            self._save_log()
        except Exception as e:
            logger.error(f"Errore nella registrazione dell'azione di moderazione: {e}")
    
    async def add_banned_word(self, word: str) -> Dict[str, Any]:
        """
        Aggiunge una parola alla lista delle parole bandite
        
        Args:
            word: La parola da aggiungere
            
        Returns:
            Dict[str, Any]: Risultato dell'operazione
        """
        try:
            # Aggiungi la parola alla lista
            self.banned_words.add(word.lower())
            
            # Salva le regole
            self._save_rules()
            
            return {"success": True, "word": word}
        except Exception as e:
            logger.error(f"Errore nell'aggiunta della parola bandita: {e}")
            return {"success": False, "error": str(e)}
    
    async def remove_banned_word(self, word: str) -> Dict[str, Any]:
        """
        Rimuove una parola dalla lista delle parole bandite
        
        Args:
            word: La parola da rimuovere
            
        Returns:
            Dict[str, Any]: Risultato dell'operazione
        """
        try:
            # Rimuovi la parola dalla lista
            if word.lower() in self.banned_words:
                self.banned_words.remove(word.lower())
                
                # Salva le regole
                self._save_rules()
                
                return {"success": True, "word": word}
            else:
                return {"success": False, "error": "Parola non trovata"}
        except Exception as e:
            logger.error(f"Errore nella rimozione della parola bandita: {e}")
            return {"success": False, "error": str(e)}
    
    async def add_custom_pattern(self, pattern: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggiunge un pattern personalizzato
        
        Args:
            pattern: Il pattern da aggiungere
            
        Returns:
            Dict[str, Any]: Risultato dell'operazione
        """
        try:
            # Verifica che i campi necessari siano presenti
            if not pattern.get("id") or not pattern.get("pattern"):
                return {"success": False, "error": "ID e pattern sono obbligatori"}
            
            # Verifica che l'ID non sia già in uso
            for p in self.custom_patterns:
                if p.get("id") == pattern.get("id"):
                    return {"success": False, "error": "ID già in uso"}
            
            # Compila il pattern
            try:
                compiled = re.compile(pattern["pattern"], re.IGNORECASE if pattern.get("case_insensitive", True) else 0)
                pattern["compiled"] = compiled
            except:
                return {"success": False, "error": "Pattern non valido"}
            
            # Aggiungi il pattern
            self.custom_patterns.append(pattern)
            
            # Salva le regole
            self._save_rules()
            
            return {"success": True, "pattern": {k: v for k, v in pattern.items() if k != "compiled"}}
        except Exception as e:
            logger.error(f"Errore nell'aggiunta del pattern personalizzato: {e}")
            return {"success": False, "error": str(e)}
    
    async def remove_custom_pattern(self, pattern_id: str) -> Dict[str, Any]:
        """
        Rimuove un pattern personalizzato
        
        Args:
            pattern_id: L'ID del pattern da rimuovere
            
        Returns:
            Dict[str, Any]: Risultato dell'operazione
        """
        try:
            # Trova il pattern
            for i, pattern in enumerate(self.custom_patterns):
                if pattern.get("id") == pattern_id:
                    # Rimuovi il pattern
                    del self.custom_patterns[i]
                    
                    # Salva le regole
                    self._save_rules()
                    
                    return {"success": True, "pattern_id": pattern_id}
            
            return {"success": False, "error": "Pattern non trovato"}
        except Exception as e:
            logger.error(f"Errore nella rimozione del pattern personalizzato: {e}")
            return {"success": False, "error": str(e)}
    
    async def update_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Aggiorna la configurazione della moderazione
        
        Args:
            config: La nuova configurazione
            
        Returns:
            Dict[str, Any]: Risultato dell'operazione
        """
        try:
            # Aggiorna la configurazione
            self.config.update(config)
            
            # Salva la configurazione
            self._save_config()
            
            return {"success": True, "config": self.config}
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento della configurazione: {e}")
            return {"success": False, "error": str(e)}

def setup(app):
    """
    Configura il plugin di moderazione AI
    
    Args:
        app: L'applicazione Flask/Quart
    """
    # Inizializza il gestore della moderazione
    app.moderation_manager = ModerationManager(app)
    
    # Registra il blueprint
    app.register_blueprint(moderation_blueprint, url_prefix='/moderation')
    
    # Definisci le route
    @moderation_blueprint.route('/', methods=['GET'])
    async def moderation_page():
        """Pagina principale della moderazione"""
        config = app.moderation_manager.config
        rules = app.moderation_manager.rules
        banned_words = list(app.moderation_manager.banned_words)
        custom_patterns = [{k: v for k, v in pattern.items() if k != "compiled"} for pattern in app.moderation_manager.custom_patterns]
        
        return await render_template(
            'moderation.html',
            config=config,
            rules=rules,
            banned_words=banned_words,
            custom_patterns=custom_patterns
        )
    
    @moderation_blueprint.route('/api/config', methods=['GET'])
    async def get_config():
        """API per ottenere la configurazione della moderazione"""
        return jsonify(app.moderation_manager.config)
    
    @moderation_blueprint.route('/api/config', methods=['POST'])
    async def update_config():
        """API per aggiornare la configurazione della moderazione"""
        data = await request.json
        result = await app.moderation_manager.update_config(data)
        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @moderation_blueprint.route('/api/rules', methods=['GET'])
    async def get_rules():
        """API per ottenere le regole di moderazione"""
        return jsonify(app.moderation_manager.rules)
    
    @moderation_blueprint.route('/api/banned_words', methods=['GET'])
    async def get_banned_words():
        """API per ottenere le parole bandite"""
        return jsonify(list(app.moderation_manager.banned_words))
    
    @moderation_blueprint.route('/api/banned_words', methods=['POST'])
    async def add_banned_word():
        """API per aggiungere una parola bandita"""
        data = await request.json
        word = data.get("word")
        if not word:
            return jsonify({"success": False, "error": "Parola non specificata"}), 400
        
        result = await app.moderation_manager.add_banned_word(word)
        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @moderation_blueprint.route('/api/banned_words/<word>', methods=['DELETE'])
    async def remove_banned_word(word):
        """API per rimuovere una parola bandita"""
        result = await app.moderation_manager.remove_banned_word(word)
        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @moderation_blueprint.route('/api/custom_patterns', methods=['GET'])
    async def get_custom_patterns():
        """API per ottenere i pattern personalizzati"""
        # Rimuovi il campo compiled
        patterns = [{k: v for k, v in pattern.items() if k != "compiled"} for pattern in app.moderation_manager.custom_patterns]
        return jsonify(patterns)
    
    @moderation_blueprint.route('/api/custom_patterns', methods=['POST'])
    async def add_custom_pattern():
        """API per aggiungere un pattern personalizzato"""
        data = await request.json
        result = await app.moderation_manager.add_custom_pattern(data)
        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @moderation_blueprint.route('/api/custom_patterns/<pattern_id>', methods=['DELETE'])
    async def remove_custom_pattern(pattern_id):
        """API per rimuovere un pattern personalizzato"""
        result = await app.moderation_manager.remove_custom_pattern(pattern_id)
        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @moderation_blueprint.route('/api/log', methods=['GET'])
    async def get_log():
        """API per ottenere il log della moderazione"""
        return jsonify(app.moderation_manager.moderation_log)
    
    @moderation_blueprint.route('/api/test', methods=['POST'])
    async def test_moderation():
        """API per testare la moderazione di un messaggio"""
        data = await request.json
        text = data.get("text")
        if not text:
            return jsonify({"success": False, "error": "Testo non specificato"}), 400
        
        # Crea un messaggio di test
        message = {
            "content": text,
            "author": {
                "username": "test_user",
                "id": "test_user_id"
            },
            "platform": "test"
        }
        
        # Modera il messaggio
        result = await app.moderation_manager.moderate_message(message)
        
        # Rimuovi alcuni campi dal risultato
        if "message" in result:
            del result["message"]
        
        return jsonify({
            "success": True,
            "moderation_result": result
        })
    
    # Aggiungi la gestione dei messaggi in arrivo per moderarli
    if hasattr(app, 'message_handler'):
        app.message_handler.register_handler(handle_message_moderation, priority=10)
    
    # Aggiungi un gestore di chiusura per chiudere il gestore della moderazione
    @app.teardown_appcontext
    async def shutdown_moderation(exception=None):
        if hasattr(app, 'moderation_manager'):
            await app.moderation_manager.close()
    
    logger.info("Plugin di moderazione AI configurato")

async def handle_message_moderation(message, app):
    """
    Gestore dei messaggi per la moderazione
    
    Args:
        message: Il messaggio da moderare
        app: L'applicazione Flask/Quart
        
    Returns:
        bool: True se il messaggio è stato gestito (moderato), False altrimenti
    """
    if not hasattr(app, 'moderation_manager'):
        return False
    
    try:
        # Modera il messaggio
        result = await app.moderation_manager.moderate_message(message)
        
        # Se il messaggio è stato flaggato ed è abilitata la moderazione automatica
        if result.get("flagged", False) and app.moderation_manager.config.get("auto_moderation", True):
            # Esegui le azioni di moderazione
            await _execute_moderation_actions(result, app)
            
            # Il messaggio è stato gestito
            return True
        
        # Il messaggio non è stato moderato
        return False
    except Exception as e:
        logger.error(f"Errore nella gestione del messaggio per la moderazione: {e}")
        return False

async def _execute_moderation_actions(moderation_result, app):
    """
    Esegue le azioni di moderazione per un messaggio flaggato
    
    Args:
        moderation_result: Il risultato della moderazione
        app: L'applicazione Flask/Quart
    """
    try:
        # Ottieni il messaggio e le categorie
        message = moderation_result.get("message", {})
        categories = moderation_result.get("categories", {})
        
        # Ottieni la piattaforma e il moderatore appropriato
        platform = message.get("platform")
        
        # Ottieni le azioni configurate
        moderation_actions = app.moderation_manager.config.get("moderation_actions", {})
        
        # Azioni da eseguire
        actions_to_execute = set()
        
        # Determina le azioni da eseguire in base alle categorie
        for category, score in categories.items():
            # Verifica se il punteggio supera la soglia
            threshold = app.moderation_manager._get_threshold_for_category(category)
            if score >= threshold and category in moderation_actions:
                # Aggiungi le azioni per questa categoria
                for action in moderation_actions.get(category, []):
                    actions_to_execute.add(action)
        
        # Esegui le azioni
        for action in actions_to_execute:
            if action == "delete" and hasattr(app, f"{platform}_connector"):
                # Elimina il messaggio
                await getattr(app, f"{platform}_connector").delete_message(message)
            
            elif action == "warn" and hasattr(app, f"{platform}_connector"):
                # Avvisa l'utente
                warning_message = f"Attenzione: il tuo messaggio è stato flaggato per contenuti inappropriati."
                await getattr(app, f"{platform}_connector").send_warning(message.get("author", {}).get("id"), warning_message)
            
            elif action == "timeout" and hasattr(app, f"{platform}_connector"):
                # Timeout per l'utente
                await getattr(app, f"{platform}_connector").timeout_user(message.get("author", {}).get("id"), 300)  # 5 minuti
            
            elif action == "ban" and hasattr(app, f"{platform}_connector"):
                # Ban per l'utente
                await getattr(app, f"{platform}_connector").ban_user(message.get("author", {}).get("id"), "Violazione delle regole: contenuti inappropriati")
            
            elif action == "report" and hasattr(app, f"{platform}_connector"):
                # Segnala il messaggio alla piattaforma
                await getattr(app, f"{platform}_connector").report_message(message)
            
            # Altre azioni...
    except Exception as e:
        logger.error(f"Errore nell'esecuzione delle azioni di moderazione: {e}") 