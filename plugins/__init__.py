"""
Plugins per M4Bot - Estensioni di funzionalità
"""

# Importazioni dei plugin
from .polls import setup as setup_polls
from .timers import setup as setup_timers
from .ai_moderation import setup as setup_ai_moderation
from .content_scheduler import setup as setup_content_scheduler
from .loyalty_system import setup as setup_loyalty_system

# Mappa dei plugin disponibili
AVAILABLE_PLUGINS = {
    "polls": {
        "name": "Sistema di Sondaggi Multipiattaforma",
        "description": "Crea e gestisci sondaggi su tutte le piattaforme integrate",
        "setup": setup_polls
    },
    "timers": {
        "name": "Timer e Countdown per Streaming",
        "description": "Crea e gestisci timer e countdown per le tue dirette",
        "setup": setup_timers
    },
    "ai_moderation": {
        "name": "Moderazione AI Avanzata",
        "description": "Sistema di moderazione automatica basato su AI",
        "setup": setup_ai_moderation
    },
    "content_scheduler": {
        "name": "Programmazione Contenuti",
        "description": "Pianifica e programma post e messaggi su tutte le piattaforme",
        "setup": setup_content_scheduler
    },
    "loyalty_system": {
        "name": "Sistema Loyalty con Punti e Livelli",
        "description": "Gestisci un sistema di punti e livelli per i tuoi spettatori",
        "setup": setup_loyalty_system
    }
}

def setup_plugins(app):
    """
    Configura tutti i plugin disponibili nell'applicazione
    
    Args:
        app: L'applicazione Flask/Quart
    """
    for plugin_id, plugin_info in AVAILABLE_PLUGINS.items():
        try:
            # Verifica se il plugin è abilitato nella configurazione
            if app.config.get(f"ENABLE_{plugin_id.upper()}", True):
                # Inizializza il plugin
                plugin_info["setup"](app)
                app.logger.info(f"Plugin {plugin_info['name']} inizializzato con successo")
            else:
                app.logger.info(f"Plugin {plugin_info['name']} disabilitato in configurazione")
        except Exception as e:
            app.logger.error(f"Errore nell'inizializzazione del plugin {plugin_info['name']}: {e}") 