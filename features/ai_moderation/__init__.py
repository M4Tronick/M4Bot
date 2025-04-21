"""
M4Bot - Sistema di Moderazione AI

Questo pacchetto implementa un sistema avanzato di moderazione basato su intelligenza artificiale
per la chat di Kick.com e altri canali supportati. Il sistema è in grado di rilevare:

- Linguaggio tossico e offensivo
- Spam e messaggi ripetitivi
- Link malevoli e phishing
- Contenuti inappropriati
- Raid e comportamenti coordinati

La moderazione può essere configurata per diversi livelli di sensibilità e azioni automatiche.
"""

from .moderator import AIModerator
from .filters import ToxicityFilter, SpamFilter, LinkFilter, ContentFilter
from .actions import ModeratorAction, ActionType
from .models import ModeratedMessage, ModerationType

__all__ = [
    'AIModerator',
    'ToxicityFilter',
    'SpamFilter',
    'LinkFilter',
    'ContentFilter',
    'ModeratorAction',
    'ActionType',
    'ModeratedMessage',
    'ModerationType',
    'setup_moderation'
]

async def setup_moderation(app=None, db_pool=None, config=None):
    """
    Configura e inizializza il sistema di moderazione AI.
    
    Args:
        app: L'applicazione Quart/Flask (opzionale)
        db_pool: Pool di connessione al database (opzionale)
        config: Configurazione personalizzata (opzionale)
        
    Returns:
        AIModerator: L'istanza del moderatore AI configurata
    """
    # Verrà implementato completamente quando creeremo gli altri moduli
    from .moderator import AIModerator
    
    # Crea l'istanza del moderatore
    moderator = AIModerator(db_pool=db_pool, config=config)
    
    # Se è fornita l'app, registra il moderatore
    if app is not None:
        app.ai_moderator = moderator
        
    # Inizializza il moderatore
    await moderator.initialize()
    
    return moderator 