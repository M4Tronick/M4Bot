"""
Babel compatibility module for Quart and Flask-Babel
Supporta le nuove versioni di Flask-Babel (4.0.0+) con patch per Quart
Aggiunto supporto per VPS Linux e gestione migliore degli errori
"""
import asyncio
import os
import logging
import sys
import platform
import functools

# Configurazione logger
logger = logging.getLogger('babel-compat')
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Determina se siamo in ambiente Linux 
IS_LINUX = platform.system() == 'Linux'
IS_VPS = IS_LINUX and os.path.exists('/proc/vz') or os.path.exists('/proc/1/cgroup') and 'docker' in open('/proc/1/cgroup').read()

logger.info(f"Sistema: {platform.system()}, VPS: {IS_VPS}")

try:
    from flask_babel import Babel as FlaskBabel
    
    class Babel(FlaskBabel):
        """Estensione di Flask-Babel con patch per Quart e supporto VPS"""
        
        def __init__(self, app=None, **kwargs):
            self._quart_patched = False
            self._translation_dirs = None
            self._default_locale = 'it'
            self._default_timezone = 'Europe/Rome'
            
            if app is not None:
                self.init_app(app, **kwargs)
                
            logger.info("Babel inizializzato con compatibilità Quart")
                
        def init_app(self, app, **kwargs):
            """Inizializza l'app con supporto Quart"""
            # Salva i percorsi delle traduzioni dall'app 
            self._translation_dirs = app.config.get('BABEL_TRANSLATION_DIRECTORIES', 'translations')
            self._default_locale = app.config.get('BABEL_DEFAULT_LOCALE', 'it')
            self._default_timezone = app.config.get('BABEL_DEFAULT_TIMEZONE', 'Europe/Rome')
            
            # In Linux, assicurati che i percorsi siano assoluti
            if IS_LINUX and not os.path.isabs(self._translation_dirs):
                app_path = os.path.dirname(os.path.abspath(app.root_path))
                abs_translation_dirs = os.path.join(app_path, self._translation_dirs)
                app.config['BABEL_TRANSLATION_DIRECTORIES'] = abs_translation_dirs
                logger.info(f"Percorso traduzioni convertito in assoluto: {abs_translation_dirs}")
                
            # Verifica che la directory delle traduzioni esista
            translation_paths = app.config.get('BABEL_TRANSLATION_DIRECTORIES', 'translations').split(';')
            for path in translation_paths:
                base_path = path.strip()
                if not os.path.exists(base_path):
                    try:
                        os.makedirs(base_path, exist_ok=True)
                        logger.info(f"Creata directory traduzioni: {base_path}")
                    except Exception as e:
                        logger.warning(f"Impossibile creare directory traduzioni {base_path}: {e}")
            
            # Patch per compatibilità con Flask-Babel 4.0.0+
            try:
                # Chiama il metodo originale di FlaskBabel
                super().init_app(app, **kwargs)
            except Exception as e:
                logger.warning(f"Errore nell'inizializzazione standard di Flask-Babel: {e}")
                # Configurazione fallback per compatibilità
                app.config.setdefault('BABEL_DEFAULT_LOCALE', self._default_locale)
                app.config.setdefault('BABEL_DEFAULT_TIMEZONE', self._default_timezone)
                app.extensions = getattr(app, 'extensions', {})
                app.extensions['babel'] = self
                
            # Applica patch per supportare funzioni async in Quart
            self._patch_for_quart()
            
        def _patch_for_quart(self):
            """Applica patch per compatibilità con Quart"""
            if self._quart_patched:
                return
                
            original_localeselector = self.localeselector
            
            @functools.wraps(original_localeselector)
            def async_locale_selector(self, f):
                # Registra la funzione originale
                sync_f = f
                
                # Se la funzione è async, crea un wrapper
                if asyncio.iscoroutinefunction(f):
                    @functools.wraps(f)
                    def sync_wrapper(*args, **kwargs):
                        try:
                            # Verifica se siamo già in un event loop
                            try:
                                loop = asyncio.get_running_loop()
                                if loop.is_running():
                                    # Se siamo già in un loop, usa run_until_complete con un nuovo evento futuro
                                    future = asyncio.run_coroutine_threadsafe(f(*args, **kwargs), loop)
                                    result = future.result(timeout=5)  # Attendi max 5 secondi
                                    return result
                            except RuntimeError:
                                # Se non siamo in un event loop, ne creiamo uno nuovo
                                loop = asyncio.new_event_loop()
                                result = loop.run_until_complete(f(*args, **kwargs))
                                loop.close()
                                return result
                        except Exception as e:
                            logger.error(f"Errore nel selector asincrono: {e}")
                            # In caso di errore, ritorna il locale predefinito
                            return self._default_locale
                    
                    sync_f = sync_wrapper
                    
                return original_localeselector(self, sync_f)
                
            # Aggiungi metodi di compatibilità
            self.localeselector = async_locale_selector.__get__(self, type(self))
            self.select_locale = self.localeselector
            
            # Metodo per verificare se l'estensione babel è presente
            def ensure_babel_extension(app):
                """Assicura che l'estensione babel sia registrata nell'app"""
                if not hasattr(app, 'extensions'):
                    app.extensions = {}
                if 'babel' not in app.extensions:
                    app.extensions['babel'] = self
                    logger.info("Registrata estensione 'babel' nell'app")
                return True
            
            self.ensure_babel_extension = ensure_babel_extension
            
            # Aggiungi metodo per ricaricare le traduzioni
            def reload_translations(babel_instance):
                if hasattr(babel_instance, '_get_translations_cache'):
                    babel_instance._get_translations_cache.clear()
                    logger.info("Cache delle traduzioni ripulita")
                    return True
                return False
                
            self.reload_translations = reload_translations.__get__(self, type(self))
            
            self._quart_patched = True
            logger.info("Patch Babel per Quart applicato con successo")
            
except ImportError as e:
    logger.warning(f"Impossibile importare Flask-Babel: {e}")
    
    # Stub class in caso di mancata importazione
    class Babel:
        def __init__(self, app=None):
            self.app = app
            self._quart_patched = True
            self._default_locale = 'it'
            self._default_timezone = 'Europe/Rome'
            logger.warning("Utilizzando class Babel di fallback (flask-babel non trovato)")
            
        def init_app(self, app):
            self.app = app
            
            # Configurazione fallback
            app.config.setdefault('BABEL_DEFAULT_LOCALE', self._default_locale)
            app.config.setdefault('BABEL_DEFAULT_TIMEZONE', self._default_timezone)
            
            # Assicurati che l'estensione sia registrata
            if not hasattr(app, 'extensions'):
                app.extensions = {}
            app.extensions['babel'] = self
            logger.info("Registrata estensione 'babel' nell'app (fallback)")
            
        def localeselector(self, f):
            return f
            
        select_locale = localeselector 
        
        def reload_translations(self):
            logger.warning("Impossibile ricaricare traduzioni: flask-babel non disponibile")
            return False
            
        def ensure_babel_extension(self, app):
            if not hasattr(app, 'extensions'):
                app.extensions = {}
            if 'babel' not in app.extensions:
                app.extensions['babel'] = self
            return True 