"""
M4Bot - Pacchetto per il pannello di amministrazione
Contiene i moduli e le funzionalità per il pannello di controllo administrativo
"""

from .app import app as admin_app
from web.routes.admin import init_admin_bp

# Funzione di inizializzazione del modulo
def init_admin(app):
    """Inizializza il modulo admin"""
    init_admin_bp(app)
    return True 