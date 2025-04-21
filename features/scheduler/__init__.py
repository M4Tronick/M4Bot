"""
M4Bot - Sistema di Pianificazione Contenuti

Questo pacchetto implementa un sistema completo per la pianificazione e gestione
di contenuti e attività per i canali su Kick.com. Il sistema supporta:

- Pianificazione di stream e eventi
- Promemoria automatici e notifiche
- Post programmati sui social media
- Automazione di azioni ricorrenti
- Calendario integrato con visualizzazione web
- Sincronizzazione con servizi esterni (Google Calendar, ecc.)
"""

from .scheduler import ContentScheduler
from .models import ScheduledEvent, EventType, RecurrencePattern
from .calendar_sync import CalendarSync

__all__ = [
    'ContentScheduler',
    'ScheduledEvent',
    'EventType',
    'RecurrencePattern',
    'CalendarSync',
    'setup_scheduler'
]

async def setup_scheduler(app=None, db_pool=None, config=None, notification_service=None):
    """
    Configura e inizializza il sistema di pianificazione contenuti.
    
    Args:
        app: L'applicazione Quart/Flask (opzionale)
        db_pool: Pool di connessione al database (opzionale)
        config: Configurazione personalizzata (opzionale)
        notification_service: Servizio di notifiche per i promemoria (opzionale)
        
    Returns:
        ContentScheduler: L'istanza dello scheduler configurata
    """
    # Importa qui per evitare dipendenze circolari
    from .scheduler import ContentScheduler
    
    # Crea l'istanza dello scheduler
    content_scheduler = ContentScheduler(
        db_pool=db_pool, 
        config=config,
        notification_service=notification_service
    )
    
    # Se è fornita l'app, registra lo scheduler
    if app is not None:
        app.content_scheduler = content_scheduler
        
    # Inizializza lo scheduler
    await content_scheduler.initialize()
    
    return content_scheduler 