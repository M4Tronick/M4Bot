#!/usr/bin/env python3
"""
Modelli dati per il sistema di moderazione AI di M4Bot.

Questo modulo definisce i modelli di dati utilizzati nel sistema di moderazione,
inclusi tipi di moderazione, azioni, e rappresentazioni di messaggi moderati.
"""

import time
from enum import Enum
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

class ModerationType(Enum):
    """Tipi di violazioni rilevate dalla moderazione."""
    TOXICITY = "toxicity"                  # Linguaggio tossico/offensive
    SPAM = "spam"                          # Messaggi spam/ripetitivi
    DANGEROUS_LINK = "dangerous_link"      # Link pericolosi/phishing
    BANNED_CONTENT = "banned_content"      # Contenuti vietati/parole bannate
    RAID = "raid"                          # Attacco coordinato
    IMPERSONATION = "impersonation"        # Finto streamer/moderatore
    DOXXING = "doxxing"                    # Informazioni personali
    HATE_SPEECH = "hate_speech"            # Incitamento all'odio
    HARASSMENT = "harassment"              # Molestie verso altri utenti
    NSFW = "nsfw"                          # Contenuto per adulti
    OTHER = "other"                        # Altre violazioni

class ActionType(Enum):
    """Tipi di azioni che il moderatore può intraprendere."""
    NONE = "none"              # Nessuna azione
    DELETE = "delete"          # Elimina il messaggio
    TIMEOUT = "timeout"        # Metti in timeout l'utente
    BAN = "ban"                # Banna l'utente
    WARNING = "warning"        # Avvisa l'utente
    REVIEW = "review"          # Segnala per revisione umana

@dataclass
class ModeratedMessage:
    """Rappresentazione di un messaggio che è stato moderato."""
    id: str                                # ID univoco del messaggio
    channel_id: str                        # ID del canale
    user_id: str                           # ID dell'utente
    username: str                          # Nome utente
    content: str                           # Contenuto del messaggio
    type: ModerationType                   # Tipo di violazione
    severity: str                          # Gravità: "low", "medium", "high"
    violation_details: Optional[Dict[str, Any]] = None  # Dettagli della violazione
    timestamp: float = field(default_factory=time.time)  # Timestamp

@dataclass
class ModeratorAction:
    """Rappresentazione di un'azione intrapresa dal moderatore."""
    type: ActionType                       # Tipo di azione
    message_id: str                        # ID del messaggio
    user_id: str                           # ID dell'utente
    channel_id: str                        # ID del canale
    reason: str                            # Motivo dell'azione
    details: Optional[Dict[str, Any]] = None  # Dettagli aggiuntivi
    timeout_duration: int = 300            # Durata timeout in secondi (default: 5 min)
    executed: bool = False                 # Se l'azione è stata eseguita
    executed_at: Optional[float] = None    # Timestamp dell'esecuzione

@dataclass
class ModerationRule:
    """Regola di moderazione configurabile per un canale."""
    id: str                                # ID univoco della regola
    channel_id: str                        # ID del canale
    name: str                              # Nome della regola
    description: str                       # Descrizione
    enabled: bool = True                   # Se la regola è attiva
    conditions: List[Dict[str, Any]] = field(default_factory=list)  # Condizioni
    actions: List[Dict[str, Any]] = field(default_factory=list)     # Azioni
    priority: int = 0                      # Priorità (ordine di esecuzione)

@dataclass
class ModerationLog:
    """Log di un'azione di moderazione."""
    id: str                                # ID univoco del log
    channel_id: str                        # ID del canale
    message_id: str                        # ID del messaggio
    user_id: str                           # ID dell'utente
    moderator_id: str                      # ID del moderatore (system per AI)
    action_type: ActionType                # Tipo di azione
    moderation_type: ModerationType        # Tipo di moderazione
    reason: str                            # Motivo
    timestamp: float                       # Timestamp
    details: Optional[Dict[str, Any]] = None  # Dettagli 