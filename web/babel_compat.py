# Compatibilità per diverse versioni di flask-babel
try:
    from flask_babel import Babel
    
    # Aggiungi retrocompatibilità se necessario
    if hasattr(Babel, 'select_locale') and not hasattr(Babel, 'localeselector'):
        Babel.localeselector = Babel.select_locale
    elif hasattr(Babel, 'localeselector') and not hasattr(Babel, 'select_locale'):
        Babel.select_locale = Babel.localeselector
except ImportError:
    # Stub class in caso di mancata importazione
    class Babel:
        def __init__(self, app=None):
            self.app = app
            
        def init_app(self, app):
            self.app = app
            
        def localeselector(self, f):
            return f
            
        select_locale = localeselector 