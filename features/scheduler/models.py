#!/usr/bin/env python3
"""
Modelli dati per il sistema di pianificazione di M4Bot.

Questo modulo definisce le strutture dati utilizzate per rappresentare
eventi pianificati, pattern di ricorrenza e sincronizzazione calendario.
"""

import time
from enum import Enum
from typing import Dict, List, Any, Optional, Set, Union
from dataclasses import dataclass, field

class EventType(Enum):
    """Tipi di eventi supportati."""
    STREAM = "stream"           # Streaming programmato
    SOCIAL_POST = "social_post" # Post su social media
    REMINDER = "reminder"       # Promemoria generico
    GIVEAWAY = "giveaway"       # Giveaway automatico
    CHANNEL_UPDATE = "channel_update"  # Aggiornamento info canale
    AUTOMATION = "automation"   # Automazione comandata
    MEETING = "meeting"         # Incontro/appuntamento
    OTHER = "other"             # Altro tipo

class EventStatus(Enum):
    """Stati possibili di un evento pianificato."""
    PENDING = "pending"         # In attesa di iniziare
    ACTIVE = "active"           # In corso
    COMPLETED = "completed"     # Completato
    CANCELLED = "cancelled"     # Annullato
    FAILED = "failed"           # Fallito

class RecurrencePattern(Enum):
    """Pattern di ricorrenza per eventi ripetitivi."""
    DAILY = "daily"             # Ogni giorno
    WEEKLY = "weekly"           # Ogni settimana
    MONTHLY = "monthly"         # Ogni mese
    CUSTOM = "custom"           # Pattern personalizzato (espressione cron)

class NotificationType(Enum):
    """Tipi di notifiche per gli eventi pianificati."""
    EMAIL = "email"             # Notifica via email
    TELEGRAM = "telegram"       # Notifica Telegram
    DISCORD = "discord"         # Notifica Discord
    PUSH = "push"               # Notifica push browser
    SMS = "sms"                 # Notifica SMS
    APP = "app"                 # Notifica in-app
    WEBHOOK = "webhook"         # Webhook HTTP

@dataclass
class ScheduledEvent:
    """Rappresenta un evento pianificato."""
    id: str                                # ID univoco
    channel_id: str                        # ID del canale
    title: str                             # Titolo dell'evento
    type: EventType                        # Tipo di evento
    status: EventStatus                    # Stato corrente
    start_time: float                      # Timestamp di inizio
    created_by: str                        # Creatore dell'evento
    created_at: float                      # Timestamp creazione
    description: str = ""                  # Descrizione
    end_time: Optional[float] = None       # Timestamp di fine (opzionale)
    location: Optional[str] = None         # Posizione (URL, luogo, ecc.)
    color: Optional[str] = None            # Colore per visualizzazione
    metadata: Dict[str, Any] = field(default_factory=dict)  # Metadati aggiuntivi
    reminders: List[Dict[str, Any]] = field(default_factory=list)  # Promemoria
    recurrence: Optional[Dict[str, Any]] = None  # Info ricorrenza
    last_updated: Optional[float] = None   # Timestamp ultimo aggiornamento
    external_id: Optional[str] = None      # ID in sistema esterno (Google Calendar, ecc.)
    
    def is_recurring(self) -> bool:
        """Verifica se l'evento è ricorrente."""
        return self.recurrence is not None
    
    def next_occurrence(self, after_time: Optional[float] = None) -> Optional[float]:
        """
        Calcola il prossimo timestamp di occorrenza dell'evento.
        
        Args:
            after_time: Timestamp dopo cui calcolare la prossima occorrenza
            
        Returns:
            float: Timestamp della prossima occorrenza o None
        """
        if not self.is_recurring():
            # Evento non ricorrente
            if after_time is None or self.start_time > after_time:
                return self.start_time
            return None
        
        # Per implementare completamente questa funzione,
        # è necessario un sistema più complesso di calcolo delle ricorrenze
        # basato sul pattern specificato
        
        # Placeholder per implementazione futura
        return self.start_time

@dataclass
class EventReminder:
    """Rappresenta un promemoria per un evento."""
    id: str                                # ID univoco
    event_id: str                          # ID dell'evento
    time_before: int                       # Secondi prima dell'evento
    type: NotificationType                 # Tipo di notifica
    recipients: List[str]                  # Destinatari
    message: Optional[str] = None          # Messaggio personalizzato
    sent: bool = False                     # Se il promemoria è stato inviato
    sent_at: Optional[float] = None        # Timestamp di invio

@dataclass
class RecurringEventInstance:
    """Rappresenta un'istanza di un evento ricorrente."""
    id: str                                # ID univoco
    parent_event_id: str                   # ID dell'evento padre
    start_time: float                      # Timestamp di inizio specifico
    end_time: Optional[float] = None       # Timestamp di fine specifico
    status: EventStatus = EventStatus.PENDING  # Stato
    metadata: Dict[str, Any] = field(default_factory=dict)  # Metadati specifici
    created_at: float = field(default_factory=time.time)    # Timestamp creazione

@dataclass
class CalendarIntegration:
    """Rappresenta un'integrazione con un calendario esterno."""
    id: str                                # ID univoco
    channel_id: str                        # ID del canale
    provider: str                          # Provider (google, ical, ecc.)
    name: str                              # Nome descrittivo
    credentials: Dict[str, Any]            # Credenziali (crittografate)
    sync_enabled: bool = True              # Se la sincronizzazione è attiva
    last_sync: Optional[float] = None      # Timestamp ultima sincronizzazione
    sync_direction: str = "both"           # Direzione sync (import, export, both)
    event_types: List[str] = field(default_factory=list)  # Tipi di eventi da sincronizzare 