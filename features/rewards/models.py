#!/usr/bin/env python3
"""
Modelli dati per il sistema di giveaway e premi di M4Bot.

Questo modulo definisce le strutture dati utilizzate per rappresentare
giveaway, premi, partecipazioni e vincitori.
"""

import time
from enum import Enum
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

class GiveawayStatus(Enum):
    """Stati possibili di un giveaway."""
    PENDING = "pending"         # In attesa di iniziare
    ACTIVE = "active"           # Attivo e accetta partecipazioni
    COMPLETED = "completed"     # Terminato con vincitori selezionati
    CANCELLED = "cancelled"     # Annullato prima del completamento

class PrizeType(Enum):
    """Tipi di premi supportati."""
    PHYSICAL = "physical"      # Premio fisico (spedizione)
    DIGITAL = "digital"        # Premio digitale (codice/key)
    SUBSCRIPTION = "subscription"  # Abbonamento
    POINTS = "points"          # Punti canale
    OTHER = "other"            # Altro tipo di premio

@dataclass
class Giveaway:
    """Rappresenta un giveaway."""
    id: str                               # ID univoco
    channel_id: str                       # ID del canale
    title: str                            # Titolo
    description: str                      # Descrizione
    status: GiveawayStatus                # Stato attuale
    created_by: str                       # ID/nome creatore
    created_at: float                     # Timestamp creazione
    updated_at: float                     # Timestamp ultimo aggiornamento
    start_time: float                     # Timestamp inizio
    end_time: Optional[float] = None      # Timestamp fine (se temporizzato)
    prize_id: Optional[str] = None        # ID del premio (se presente)
    max_winners: int = 1                  # Numero massimo di vincitori
    requirements: List[Dict[str, Any]] = field(default_factory=list)  # Requisiti partecipazione

@dataclass
class Prize:
    """Rappresenta un premio per giveaway."""
    id: str                               # ID univoco
    name: str                             # Nome del premio
    description: str                      # Descrizione
    type: PrizeType                       # Tipo di premio
    value: Optional[str] = None           # Valore/costo del premio
    quantity: int = 1                     # Quantità disponibile
    image_url: Optional[str] = None       # URL immagine
    redemption_instructions: Optional[str] = None  # Istruzioni per riscattare
    created_at: float = field(default_factory=time.time)  # Timestamp creazione
    created_by: Optional[str] = None      # ID/nome creatore
    is_active: bool = True                # Se il premio è attivo

@dataclass
class Entry:
    """Rappresenta una partecipazione a un giveaway."""
    id: str                               # ID univoco
    giveaway_id: str                      # ID del giveaway
    user_id: str                          # ID dell'utente
    username: str                         # Nome utente
    entry_time: float                     # Timestamp partecipazione

@dataclass
class Winner:
    """Rappresenta un vincitore di un giveaway."""
    giveaway_id: str                      # ID del giveaway
    user_id: str                          # ID dell'utente
    username: str                         # Nome utente
    entry_id: str                         # ID della partecipazione
    selected_at: float                    # Timestamp selezione
    prize_id: Optional[str] = None        # ID del premio vinto
    claimed: bool = False                 # Se il premio è stato riscattato
    claimed_at: Optional[float] = None    # Timestamp riscatto 