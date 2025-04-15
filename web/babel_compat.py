# Compatibilità per diverse versioni di flask-babel e supporto asincrono per Quart
import asyncio
import os
import logging

logger = logging.getLogger('babel-compat')

try:
    from flask_babel import Babel
    
    # Aggiungi retrocompatibilità se necessario
    if hasattr(Babel, 'select_locale') and not hasattr(Babel, 'localeselector'):
        Babel.localeselector = Babel.select_locale
    elif hasattr(Babel, 'localeselector') and not hasattr(Babel, 'select_locale'):
        Babel.select_locale = Babel.localeselector
        
    # Supporto Quart: Aggiungi un wrapper asincrono per i decoratori di Babel
    original_localeselector = Babel.localeselector
    def async_locale_selector(self, f):
        # Registra la funzione originale
        sync_f = f
        # Se la funzione è async, crea un wrapper
        if asyncio.iscoroutinefunction(f):
            def sync_wrapper(*args, **kwargs):
                loop = asyncio.get_event_loop()
                result = loop.run_until_complete(f(*args, **kwargs))
                logger.debug(f"Locale selezionato: {result}")
                return result
            sync_f = sync_wrapper
        return original_localeselector(self, sync_f)
    
    # Funzione per ricaricare le traduzioni
    def reload_translations(babel_instance):
        if hasattr(babel_instance, '_get_translations_cache'):
            babel_instance._get_translations_cache.clear()
            logger.info("Cache delle traduzioni ripulita")
            return True
        return False
    
    # Applica il patch solo se non è già stato applicato
    if not hasattr(Babel, '_quart_patched'):
        Babel.localeselector = async_locale_selector
        Babel.select_locale = async_locale_selector
        Babel.reload_translations = reload_translations
        Babel._quart_patched = True
        logger.info("Patch Babel per Quart applicato con successo")
        
except ImportError:
    # Stub class in caso di mancata importazione
    class Babel:
        def __init__(self, app=None):
            self.app = app
            self._quart_patched = True
            logger.warning("Utilizzando class Babel di fallback (flask-babel non trovato)")
            
        def init_app(self, app):
            self.app = app
            
        def localeselector(self, f):
            return f
            
        select_locale = localeselector 
        
        def reload_translations(self):
            logger.warning("Impossibile ricaricare traduzioni: flask-babel non disponibile")
            return False 