#!/usr/bin/env python3
"""
Filtri di moderazione per il sistema AI di M4Bot.

Questo modulo contiene i vari filtri utilizzati dal moderatore AI per verificare
la presenza di contenuti inappropriati, linguaggio offensivo, spam, e link pericolosi.
"""

import re
import time
import json
import asyncio
import aiohttp
import logging
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass
from collections import defaultdict, deque

# Importazioni locali
from .models import ModerationType, ModeratedMessage

# Logger
logger = logging.getLogger('m4bot.ai_moderation.filters')

@dataclass
class FilterResult:
    """Risultato dell'analisi di un filtro di moderazione."""
    is_violation: bool = False
    type: Optional[ModerationType] = None
    severity: str = "low"  # low, medium, high
    details: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.details is None:
            self.details = {}

class ToxicityFilter:
    """
    Filtro per rilevare linguaggio tossico e offensivo nei messaggi.
    Utilizza modelli NLP per identificare vari tipi di linguaggio problematico.
    """
    
    def __init__(self, threshold: float = 0.8, languages: List[str] = None):
        """
        Inizializza il filtro di tossicità.
        
        Args:
            threshold: Soglia di confidenza per considerare un messaggio tossico
            languages: Lingue supportate (iso codes)
        """
        self.threshold = threshold
        self.languages = languages or ['it', 'en']
        
        # Dizionario di parole offensive per rilevazione rapida
        self.offensive_words = {
            'it': set(),  # Sarà popolato con parole offensive in italiano
            'en': set()   # Sarà popolato con parole offensive in inglese
        }
        
        # Carica i dizionari di parole offensive
        self._load_offensive_words()
        
        logger.info(f"Filtro tossicità inizializzato con soglia {threshold}")
    
    def _load_offensive_words(self):
        """Carica i dizionari di parole offensive per il rilevamento rapido."""
        # Parole offensive in italiano (esempi)
        italian_words = [
            "cazzo", "vaffanculo", "stronzo", "merda", "troia", "puttana", 
            "bastardo", "minchia", "coglione"
        ]
        
        # Parole offensive in inglese (esempi)
        english_words = [
            "fuck", "shit", "bitch", "asshole", "cunt", "dick",
            "whore", "slut", "retard", "faggot"
        ]
        
        self.offensive_words['it'] = set(italian_words)
        self.offensive_words['en'] = set(english_words)
        
        logger.debug(f"Caricate {len(italian_words)} parole offensive in italiano e {len(english_words)} in inglese")
    
    async def check(self, text: str) -> FilterResult:
        """
        Controlla se un testo contiene linguaggio tossico.
        
        Args:
            text: Testo da analizzare
            
        Returns:
            FilterResult: Risultato dell'analisi
        """
        # Inizializza il risultato
        result = FilterResult(
            is_violation=False,
            type=ModerationType.TOXICITY,
            severity="low",
            details={}
        )
        
        # Controllo rapido basato su dizionario
        text_lower = text.lower()
        
        # Cerca parole offensive in tutte le lingue supportate
        detected_words = []
        for lang, words in self.offensive_words.items():
            for word in words:
                if re.search(r'\b' + re.escape(word) + r'\b', text_lower):
                    detected_words.append(word)
        
        if detected_words:
            # Rilevamento positivo con dizionario
            result.is_violation = True
            result.severity = "medium"  # Default per rilevamento basato su dizionario
            result.details = {
                "method": "dictionary",
                "detected_words": detected_words,
                "confidence": 0.9  # Confidenza arbitraria per rilevamento su dizionario
            }
            return result
        
        # Implementazione di verifica con API TensorFlow o altro servizio AI
        # Questo è un placeholder per l'implementazione reale che userebbe un modello AI
        toxicity_score = await self._analyze_toxicity_with_model(text)
        
        if toxicity_score >= self.threshold:
            result.is_violation = True
            
            # Determina la gravità in base al punteggio
            if toxicity_score >= 0.9:
                result.severity = "high"
            elif toxicity_score >= 0.7:
                result.severity = "medium"
            else:
                result.severity = "low"
                
            result.details = {
                "method": "ai_model",
                "score": toxicity_score,
                "threshold": self.threshold
            }
        
        return result
    
    async def _analyze_toxicity_with_model(self, text: str) -> float:
        """
        Analizza un testo con un modello AI per il rilevamento di tossicità.
        
        Args:
            text: Testo da analizzare
            
        Returns:
            float: Punteggio di tossicità (0.0-1.0)
        """
        # Qui dovrebbe esserci l'integrazione con un servizio reale come:
        # - Perspective API di Google
        # - Un modello TensorFlow/PyTorch locale
        # - Un servizio di terze parti
        
        # Per ora, simula un'analisi basata su euristiche semplici
        toxicity_score = 0.0
        
        # Controlla la presenza di caratteri ripetuti (es. !!!!!!, AAAAA)
        if re.search(r'([!?.])\1{3,}', text) or re.search(r'([A-Z])\1{3,}', text):
            toxicity_score += 0.3
        
        # Controlla l'uso eccessivo di maiuscole
        uppercase_ratio = sum(1 for c in text if c.isupper()) / max(1, len(text))
        if uppercase_ratio > 0.5 and len(text) > 5:
            toxicity_score += 0.3
        
        # Limitiamo il punteggio massimo per questo simulatore a 0.7
        # Un modello reale fornirebbe punteggi più accurati
        return min(0.7, toxicity_score)


class SpamFilter:
    """
    Filtro per rilevare messaggi di spam e comportamento ripetitivo.
    Tiene traccia dei pattern di messaggi degli utenti.
    """
    
    def __init__(self, max_identical_messages: int = 3, 
                max_messages_per_minute: int = 20,
                time_window: int = 60):
        """
        Inizializza il filtro anti-spam.
        
        Args:
            max_identical_messages: Numero massimo di messaggi identici permessi in una finestra temporale
            max_messages_per_minute: Numero massimo di messaggi permessi al minuto
            time_window: Finestra temporale in secondi per il rilevamento
        """
        self.max_identical_messages = max_identical_messages
        self.max_messages_per_minute = max_messages_per_minute
        self.time_window = time_window
        
        # Struttura dati per tenere traccia dei messaggi per utente e canale
        # {channel_id: {user_id: deque([timestamp1, timestamp2, ...])}}
        self.message_history = defaultdict(lambda: defaultdict(lambda: deque(maxlen=100)))
        
        # Struttura per tenere traccia dei contenuti dei messaggi
        # {channel_id: {user_id: {content_hash: [timestamp1, timestamp2, ...]}}}
        self.content_history = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        
        # Cache per ottimizzazione
        self.violation_cache = {}
        self.cache_expiry = 300  # 5 minuti
        
        logger.info("Filtro anti-spam inizializzato")
    
    def _clean_old_entries(self, channel_id: str, user_id: str):
        """
        Rimuove le voci più vecchie del time_window dalla cronologia.
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente
        """
        current_time = time.time()
        cutoff_time = current_time - self.time_window
        
        # Pulisci la cronologia dei tempi dei messaggi
        while (self.message_history[channel_id][user_id] and 
               self.message_history[channel_id][user_id][0] < cutoff_time):
            self.message_history[channel_id][user_id].popleft()
        
        # Pulisci la cronologia dei contenuti
        for content_hash in list(self.content_history[channel_id][user_id].keys()):
            timestamps = self.content_history[channel_id][user_id][content_hash]
            self.content_history[channel_id][user_id][content_hash] = [
                ts for ts in timestamps if ts >= cutoff_time
            ]
            
            # Rimuovi hash senza timestamp
            if not self.content_history[channel_id][user_id][content_hash]:
                del self.content_history[channel_id][user_id][content_hash]
    
    def _hash_content(self, content: str) -> str:
        """
        Genera un hash semplificato del contenuto per confrontare messaggi simili.
        
        Args:
            content: Contenuto del messaggio
            
        Returns:
            str: Hash del contenuto
        """
        # Normalizza il testo: minuscolo e rimuovi spazi extra
        normalized = re.sub(r'\s+', ' ', content.lower()).strip()
        
        # Per messaggi molto corti, usa direttamente il testo
        if len(normalized) <= 10:
            return normalized
            
        return normalized
    
    async def check(self, content: str, user_id: str, channel_id: str) -> FilterResult:
        """
        Controlla se un messaggio è spam in base al contesto dell'utente e del canale.
        
        Args:
            content: Contenuto del messaggio
            user_id: ID dell'utente
            channel_id: ID del canale
            
        Returns:
            FilterResult: Risultato dell'analisi
        """
        # Inizializza il risultato
        result = FilterResult(
            is_violation=False,
            type=ModerationType.SPAM,
            severity="low",
            details={}
        )
        
        # Ottieni il tempo corrente
        current_time = time.time()
        
        # Pulisci i dati vecchi
        self._clean_old_entries(channel_id, user_id)
        
        # Registra il nuovo messaggio
        self.message_history[channel_id][user_id].append(current_time)
        
        # Verifica frequenza messaggi
        message_count = len(self.message_history[channel_id][user_id])
        if message_count > self.max_messages_per_minute:
            result.is_violation = True
            result.severity = "medium"
            result.details = {
                "type": "frequency",
                "message_count": message_count,
                "time_window": self.time_window,
                "threshold": self.max_messages_per_minute
            }
            return result
            
        # Verifica contenuto ripetitivo
        content_hash = self._hash_content(content)
        self.content_history[channel_id][user_id][content_hash].append(current_time)
        
        identical_count = len(self.content_history[channel_id][user_id][content_hash])
        if identical_count > self.max_identical_messages:
            result.is_violation = True
            result.severity = "medium" if identical_count <= 2 * self.max_identical_messages else "high"
            result.details = {
                "type": "repetition",
                "identical_count": identical_count,
                "threshold": self.max_identical_messages,
                "content": content[:100] + ("..." if len(content) > 100 else "")
            }
            return result
        
        return result


class LinkFilter:
    """
    Filtro per rilevare e verificare link potenzialmente pericolosi.
    Può controllare Domini vietati o sconosciuti, URL di phishing, e altro.
    """
    
    def __init__(self, check_safe_browsing: bool = False, 
                allowed_domains: List[str] = None,
                safe_browsing_api_key: str = None):
        """
        Inizializza il filtro per i link.
        
        Args:
            check_safe_browsing: Se verificare i link con Google Safe Browsing API
            allowed_domains: Lista di domini sempre permessi
            safe_browsing_api_key: Chiave API per Google Safe Browsing
        """
        self.check_safe_browsing = check_safe_browsing
        self.safe_browsing_api_key = safe_browsing_api_key
        
        # Domini che sono sempre permessi
        self.allowed_domains = set(allowed_domains or [
            "kick.com", "twitch.tv", "youtube.com", "youtu.be", 
            "twitter.com", "facebook.com", "instagram.com"
        ])
        
        # Domini noti per essere pericolosi
        self.dangerous_domains = set([
            # Esempi di domini dannosi
            "example-malware.com", "phishing-example.com"
        ])
        
        # Cache dei risultati di controllo per evitare richieste ripetute
        self.check_cache = {}
        self.cache_expiry = 3600  # 1 ora
        
        # Regex per estrarre URL
        self.url_pattern = re.compile(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            re.IGNORECASE
        )
        
        logger.info(f"Filtro link inizializzato con {len(self.allowed_domains)} domini permessi")
    
    def _extract_domain(self, url: str) -> str:
        """
        Estrae il dominio da un URL.
        
        Args:
            url: URL completo
            
        Returns:
            str: Dominio estratto
        """
        # Rimuovi protocollo
        domain = url.lower()
        if "://" in domain:
            domain = domain.split("://")[1]
        
        # Rimuovi percorso, query, etc.
        if "/" in domain:
            domain = domain.split("/")[0]
        
        # Rimuovi porta
        if ":" in domain:
            domain = domain.split(":")[0]
        
        return domain
    
    async def check(self, content: str) -> FilterResult:
        """
        Controlla se un messaggio contiene link potenzialmente pericolosi.
        
        Args:
            content: Contenuto del messaggio
            
        Returns:
            FilterResult: Risultato dell'analisi
        """
        # Inizializza il risultato
        result = FilterResult(
            is_violation=False,
            type=ModerationType.DANGEROUS_LINK,
            severity="low",
            details={}
        )
        
        # Trova tutte le URL nel messaggio
        urls = self.url_pattern.findall(content)
        if not urls:
            return result
        
        # Controlla ogni URL trovato
        dangerous_urls = []
        domains = []
        
        for url in urls:
            domain = self._extract_domain(url)
            domains.append(domain)
            
            # Se il dominio è nella whitelist, saltalo
            if any(domain.endswith(allowed) for allowed in self.allowed_domains):
                continue
            
            # Se il dominio è nella blacklist, segnalalo
            if domain in self.dangerous_domains:
                dangerous_urls.append({
                    "url": url,
                    "domain": domain,
                    "reason": "blacklisted_domain"
                })
                continue
            
            # Controlla se l'URL è in cache
            cache_key = url.lower()
            if cache_key in self.check_cache:
                cache_entry = self.check_cache[cache_key]
                # Verifica se la cache è ancora valida
                if cache_entry["expiry"] > time.time():
                    if cache_entry["is_dangerous"]:
                        dangerous_urls.append({
                            "url": url,
                            "domain": domain,
                            "reason": cache_entry["reason"]
                        })
                    continue
            
            # Se è abilitato Safe Browsing e abbiamo una chiave API
            if self.check_safe_browsing and self.safe_browsing_api_key:
                is_dangerous, reason = await self._check_safe_browsing(url)
                
                # Aggiorna la cache
                self.check_cache[cache_key] = {
                    "is_dangerous": is_dangerous,
                    "reason": reason,
                    "expiry": time.time() + self.cache_expiry
                }
                
                if is_dangerous:
                    dangerous_urls.append({
                        "url": url,
                        "domain": domain,
                        "reason": reason
                    })
        
        # Se abbiamo trovato URL pericolosi
        if dangerous_urls:
            result.is_violation = True
            result.severity = "high"  # I link pericolosi sono considerati high severity
            result.details = {
                "dangerous_urls": dangerous_urls,
                "all_domains": domains
            }
        
        return result
    
    async def _check_safe_browsing(self, url: str) -> Tuple[bool, str]:
        """
        Controlla un URL con Google Safe Browsing API.
        
        Args:
            url: URL da controllare
            
        Returns:
            Tuple[bool, str]: (è_pericoloso, motivo)
        """
        # Questo è un placeholder per la reale implementazione
        # In un'implementazione reale, dovresti fare una richiesta all'API Safe Browsing
        
        # Simula un controllo per ora
        if "phishing" in url or "malware" in url:
            return True, "simulated_threat"
            
        # In una implementazione reale, faresti qualcosa come:
        """
        try:
            async with aiohttp.ClientSession() as session:
                api_url = f"https://safebrowsing.googleapis.com/v4/threatMatches:find?key={self.safe_browsing_api_key}"
                payload = {
                    "client": {
                        "clientId": "m4bot",
                        "clientVersion": "1.0.0"
                    },
                    "threatInfo": {
                        "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
                        "platformTypes": ["ANY_PLATFORM"],
                        "threatEntryTypes": ["URL"],
                        "threatEntries": [{"url": url}]
                    }
                }
                
                async with session.post(api_url, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "matches" in data and data["matches"]:
                            threat_type = data["matches"][0]["threatType"]
                            return True, threat_type
        except Exception as e:
            logger.error(f"Errore nella verifica Safe Browsing: {e}")
        """
        
        return False, ""


class ContentFilter:
    """
    Filtro per contenuti specifici violano le regole del canale.
    Rileva parole e frasi bannate, temi sensibili, etc.
    """
    
    def __init__(self, banned_words: List[str] = None, 
                banned_phrases: List[str] = None,
                sensitive_topics: List[str] = None):
        """
        Inizializza il filtro per contenuti.
        
        Args:
            banned_words: Lista di parole vietate
            banned_phrases: Lista di frasi vietate
            sensitive_topics: Lista di temi sensibili da rilevare
        """
        self.banned_words = set(banned_words or [])
        self.banned_phrases = banned_phrases or []
        self.sensitive_topics = sensitive_topics or []
        
        # Converte banned words e phrases in minuscolo
        self.banned_words = {word.lower() for word in self.banned_words}
        self.banned_phrases = [phrase.lower() for phrase in self.banned_phrases]
        
        # Compila regex per le frasi vietate (per una ricerca più efficiente)
        self.banned_phrases_regex = []
        for phrase in self.banned_phrases:
            try:
                # Escape caratteri speciali regex e crea pattern per word boundary
                pattern = r'\b' + re.escape(phrase) + r'\b'
                self.banned_phrases_regex.append(re.compile(pattern, re.IGNORECASE))
            except re.error:
                logger.warning(f"Impossibile compilare regex per la frase: {phrase}")
        
        logger.info(f"Filtro contenuti inizializzato con {len(self.banned_words)} parole e {len(self.banned_phrases)} frasi vietate")
    
    async def check(self, content: str) -> FilterResult:
        """
        Controlla se un messaggio contiene contenuti vietati.
        
        Args:
            content: Contenuto del messaggio
            
        Returns:
            FilterResult: Risultato dell'analisi
        """
        # Inizializza il risultato
        result = FilterResult(
            is_violation=False,
            type=ModerationType.BANNED_CONTENT,
            severity="low",
            details={}
        )
        
        # Converti il contenuto in minuscolo per la ricerca
        content_lower = content.lower()
        
        # Controlla parole vietate
        found_words = []
        for word in self.banned_words:
            # Usa regex per verificare word boundaries
            pattern = r'\b' + re.escape(word) + r'\b'
            if re.search(pattern, content_lower):
                found_words.append(word)
        
        # Controlla frasi vietate
        found_phrases = []
        for i, regex in enumerate(self.banned_phrases_regex):
            if regex.search(content_lower):
                found_phrases.append(self.banned_phrases[i])
        
        # Se abbiamo trovato parole o frasi vietate
        if found_words or found_phrases:
            result.is_violation = True
            
            # Determina la severità in base al numero di violazioni
            total_violations = len(found_words) + len(found_phrases)
            if total_violations >= 3:
                result.severity = "high"
            elif total_violations >= 2:
                result.severity = "medium"
            else:
                result.severity = "low"
                
            result.details = {
                "banned_words": found_words,
                "banned_phrases": found_phrases
            }
        
        return result 