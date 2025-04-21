import os
import json
import logging
import aiofiles
import langdetect
import cld3
from typing import Dict, List, Optional, Any

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/translation.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("TranslationManager")

class TranslationManager:
    """Gestore delle traduzioni per M4Bot con supporto per file di lingua separati"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Inizializza il gestore delle traduzioni
        
        Args:
            config: Configurazione del gestore
        """
        self.config = config
        self.default_language = config.get("default_language", "it")
        self.languages_dir = config.get("languages_dir", "languages")
        self.available_languages = config.get("available_languages", ["it", "en", "es", "fr", "de"])
        self.translations = {}
        self.user_languages = {}
        
        # Crea la directory delle lingue
        os.makedirs(self.languages_dir, exist_ok=True)
        os.makedirs("logs", exist_ok=True)
        
        logger.info(f"Gestore traduzioni inizializzato (lingua predefinita: {self.default_language})")
    
    async def load_translations(self):
        """Carica tutte le traduzioni disponibili"""
        for lang_code in self.available_languages:
            await self._load_language_file(lang_code)
        
        logger.info(f"Caricate {len(self.translations)} lingue")
    
    async def _load_language_file(self, lang_code: str):
        """
        Carica un file di lingua
        
        Args:
            lang_code: Codice della lingua da caricare
        """
        file_path = os.path.join(self.languages_dir, f"{lang_code}.json")
        
        try:
            # Verifica se il file esiste
            if not os.path.exists(file_path):
                # Crea un file vuoto se non esiste
                await self._create_empty_language_file(lang_code)
            
            # Carica il file
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
                self.translations[lang_code] = json.loads(content)
                
                logger.info(f"Lingua caricata: {lang_code} ({len(self.translations[lang_code])} traduzioni)")
        
        except Exception as e:
            logger.error(f"Errore nel caricamento della lingua {lang_code}: {e}")
            self.translations[lang_code] = {}
    
    async def _create_empty_language_file(self, lang_code: str):
        """
        Crea un file di lingua vuoto
        
        Args:
            lang_code: Codice della lingua da creare
        """
        file_path = os.path.join(self.languages_dir, f"{lang_code}.json")
        
        try:
            empty_translations = {}
            
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(empty_translations, indent=2, ensure_ascii=False))
                
            logger.info(f"Creato file di lingua vuoto: {lang_code}")
        
        except Exception as e:
            logger.error(f"Errore nella creazione del file di lingua {lang_code}: {e}")
    
    async def save_translations(self, lang_code: str = None):
        """
        Salva le traduzioni su file
        
        Args:
            lang_code: Codice della lingua da salvare (se None, salva tutte le lingue)
        """
        try:
            if lang_code:
                # Salva solo la lingua specificata
                if lang_code in self.translations:
                    await self._save_language_file(lang_code)
            else:
                # Salva tutte le lingue
                for code in self.translations:
                    await self._save_language_file(code)
            
            logger.info("Traduzioni salvate con successo")
            return True
        
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle traduzioni: {e}")
            return False
    
    async def _save_language_file(self, lang_code: str):
        """
        Salva un file di lingua
        
        Args:
            lang_code: Codice della lingua da salvare
        """
        file_path = os.path.join(self.languages_dir, f"{lang_code}.json")
        
        try:
            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(self.translations[lang_code], indent=2, ensure_ascii=False))
                
            logger.info(f"Lingua salvata: {lang_code} ({len(self.translations[lang_code])} traduzioni)")
        
        except Exception as e:
            logger.error(f"Errore nel salvataggio della lingua {lang_code}: {e}")
    
    def get_text(self, key: str, lang_code: str = None, **kwargs) -> str:
        """
        Ottiene una traduzione
        
        Args:
            key: Chiave della traduzione
            lang_code: Lingua desiderata (se None, usa la lingua predefinita)
            **kwargs: Parametri da sostituire nella traduzione
            
        Returns:
            str: Testo tradotto
        """
        # Lingua richiesta o predefinita
        lang = lang_code or self.default_language
        
        # Se la lingua non è disponibile, usa quella predefinita
        if lang not in self.translations:
            lang = self.default_language
        
        # Ottieni la traduzione
        translations = self.translations.get(lang, {})
        text = translations.get(key)
        
        # Se la traduzione non esiste, usa la chiave e aggiunge la traduzione mancante
        if text is None:
            # Usa la traduzione in lingua predefinita se disponibile
            if lang != self.default_language and key in self.translations.get(self.default_language, {}):
                text = self.translations[self.default_language][key]
            else:
                text = key
                
                # Aggiungi la traduzione mancante alla lingua predefinita
                if key not in self.translations.get(self.default_language, {}):
                    if self.default_language not in self.translations:
                        self.translations[self.default_language] = {}
                    
                    self.translations[self.default_language][key] = key
        
        # Sostituisci i parametri
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception as e:
                logger.error(f"Errore nella formattazione della traduzione '{key}': {e}")
                return text
        
        return text
    
    def set_text(self, key: str, text: str, lang_code: str) -> bool:
        """
        Imposta una traduzione
        
        Args:
            key: Chiave della traduzione
            text: Testo tradotto
            lang_code: Lingua della traduzione
            
        Returns:
            bool: True se la traduzione è stata impostata con successo, False altrimenti
        """
        try:
            # Verifica se la lingua è disponibile
            if lang_code not in self.available_languages:
                logger.warning(f"Lingua non disponibile: {lang_code}")
                return False
            
            # Crea il dizionario della lingua se non esiste
            if lang_code not in self.translations:
                self.translations[lang_code] = {}
            
            # Imposta la traduzione
            self.translations[lang_code][key] = text
            
            logger.info(f"Traduzione impostata: {key} ({lang_code})")
            return True
        
        except Exception as e:
            logger.error(f"Errore nell'impostazione della traduzione: {e}")
            return False
    
    async def detect_language(self, text: str) -> str:
        """
        Rileva la lingua di un testo
        
        Args:
            text: Testo da analizzare
            
        Returns:
            str: Codice della lingua rilevata
        """
        try:
            # Usa due diversi rilevatori per una maggiore accuratezza
            langdetect_result = langdetect.detect(text)
            cld3_result = cld3.get_language(text)
            
            # Se cld3 è sicuro, usa il suo risultato
            if cld3_result.is_reliable and cld3_result.probability > 0.8:
                detected = cld3_result.language
            else:
                detected = langdetect_result
            
            # Verifica se la lingua è supportata
            if detected in self.available_languages:
                return detected
            else:
                return self.default_language
        
        except Exception as e:
            logger.error(f"Errore nel rilevamento della lingua: {e}")
            return self.default_language
    
    def set_user_language(self, user_id: str, lang_code: str) -> bool:
        """
        Imposta la lingua preferita di un utente
        
        Args:
            user_id: ID dell'utente
            lang_code: Codice della lingua
            
        Returns:
            bool: True se la lingua è stata impostata con successo, False altrimenti
        """
        try:
            # Verifica se la lingua è disponibile
            if lang_code not in self.available_languages:
                logger.warning(f"Lingua non disponibile: {lang_code}")
                return False
            
            # Imposta la lingua dell'utente
            self.user_languages[user_id] = lang_code
            
            logger.info(f"Lingua impostata per l'utente {user_id}: {lang_code}")
            return True
        
        except Exception as e:
            logger.error(f"Errore nell'impostazione della lingua dell'utente: {e}")
            return False
    
    def get_user_language(self, user_id: str) -> str:
        """
        Ottiene la lingua preferita di un utente
        
        Args:
            user_id: ID dell'utente
            
        Returns:
            str: Codice della lingua dell'utente
        """
        return self.user_languages.get(user_id, self.default_language)
    
    async def add_language(self, lang_code: str, lang_name: str) -> bool:
        """
        Aggiunge una nuova lingua
        
        Args:
            lang_code: Codice della lingua
            lang_name: Nome della lingua
            
        Returns:
            bool: True se la lingua è stata aggiunta con successo, False altrimenti
        """
        try:
            # Verifica se la lingua è già disponibile
            if lang_code in self.available_languages:
                logger.warning(f"Lingua già disponibile: {lang_code}")
                return False
            
            # Aggiungi la lingua
            self.available_languages.append(lang_code)
            
            # Crea il file di lingua
            await self._create_empty_language_file(lang_code)
            
            # Aggiungi il nome della lingua alle traduzioni
            self.translations[lang_code] = {"language_name": lang_name}
            await self._save_language_file(lang_code)
            
            logger.info(f"Lingua aggiunta: {lang_code} ({lang_name})")
            return True
        
        except Exception as e:
            logger.error(f"Errore nell'aggiunta della lingua: {e}")
            return False
    
    def get_available_languages(self) -> List[Dict[str, str]]:
        """
        Ottiene la lista delle lingue disponibili
        
        Returns:
            List: Lista delle lingue disponibili
        """
        result = []
        
        for lang_code in self.available_languages:
            lang_name = self.translations.get(lang_code, {}).get("language_name", lang_code)
            result.append({
                "code": lang_code,
                "name": lang_name
            })
        
        return result
    
    def get_missing_translations(self, lang_code: str) -> List[str]:
        """
        Ottiene la lista delle traduzioni mancanti
        
        Args:
            lang_code: Codice della lingua
            
        Returns:
            List: Lista delle chiavi mancanti
        """
        # Verifica se la lingua è disponibile
        if lang_code not in self.translations:
            return []
        
        # Ottieni tutte le chiavi dalla lingua predefinita
        default_keys = set(self.translations.get(self.default_language, {}).keys())
        
        # Ottieni le chiavi della lingua specificata
        lang_keys = set(self.translations[lang_code].keys())
        
        # Restituisci le chiavi mancanti
        return list(default_keys - lang_keys)
    
    def get_translation_stats(self) -> Dict[str, Any]:
        """
        Ottiene le statistiche delle traduzioni
        
        Returns:
            Dict: Statistiche delle traduzioni
        """
        stats = {}
        
        # Ottieni tutte le chiavi dalla lingua predefinita
        default_keys = set(self.translations.get(self.default_language, {}).keys())
        total_keys = len(default_keys)
        
        for lang_code in self.available_languages:
            # Ottieni le chiavi della lingua
            lang_keys = set(self.translations.get(lang_code, {}).keys())
            translated = len(lang_keys.intersection(default_keys))
            
            # Calcola la percentuale di completamento
            percentage = 100.0 * translated / total_keys if total_keys > 0 else 0.0
            
            stats[lang_code] = {
                "total": total_keys,
                "translated": translated,
                "missing": total_keys - translated,
                "percentage": round(percentage, 2)
            }
        
        return stats

# Funzione per creare un'istanza del gestore delle traduzioni
def create_translation_manager(config: Dict[str, Any]) -> TranslationManager:
    """
    Crea un'istanza del gestore delle traduzioni
    
    Args:
        config: Configurazione del gestore
        
    Returns:
        TranslationManager: Istanza del gestore delle traduzioni
    """
    return TranslationManager(config) 