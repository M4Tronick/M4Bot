"""
M4Bot - Sistema di Giveaway e Premi

Questo pacchetto implementa un sistema completo per la gestione di giveaway, premi e concorsi
per i canali su Kick.com. Il sistema supporta:

- Giveaway temporizzati e manuali
- Requisiti personalizzabili per partecipazione (punti, iscrizione, etc.)
- Selezione casuale dei vincitori con verifica di idoneità
- Notifiche automatiche in chat e multi-canale
- Tracciamento dei premi e dei vincitori
- Statistiche e reportistica
"""

from .giveaway_manager import GiveawayManager
from .prize_system import PrizeSystem
from .models import Giveaway, Prize, Entry, Winner
from .validators import ParticipationValidator, RequirementValidator

__all__ = [
    'GiveawayManager',
    'PrizeSystem',
    'Giveaway',
    'Prize',
    'Entry',
    'Winner',
    'ParticipationValidator',
    'RequirementValidator',
    'setup_rewards'
]

async def setup_rewards(app=None, db_pool=None, config=None, notification_service=None):
    """
    Configura e inizializza il sistema di giveaway e premi.
    
    Args:
        app: L'applicazione Quart/Flask (opzionale)
        db_pool: Pool di connessione al database (opzionale)
        config: Configurazione personalizzata (opzionale)
        notification_service: Servizio di notifiche per gli avvisi (opzionale)
        
    Returns:
        GiveawayManager: L'istanza del manager di giveaway configurata
    """
    # Importa qui per evitare dipendenze circolari
    from .giveaway_manager import GiveawayManager
    
    # Crea l'istanza del manager
    giveaway_manager = GiveawayManager(
        db_pool=db_pool, 
        config=config,
        notification_service=notification_service
    )
    
    # Se è fornita l'app, registra il manager
    if app is not None:
        app.giveaway_manager = giveaway_manager
        
    # Inizializza il manager
    await giveaway_manager.initialize()
    
    return giveaway_manager 