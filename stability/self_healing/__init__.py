"""
M4Bot - Modulo Self-Healing

Questo modulo implementa funzionalità di auto-guarigione per garantire che
tutti i servizi M4Bot rimangano operativi anche in caso di errori o guasti.

Componenti principali:
- Sistema di self-healing: monitora e ripristina automaticamente i servizi
- Chaos testing: introduce deliberatamente guasti per testare la resilienza
- Rilevamento anomalie: identifica comportamenti anomali prima che causino problemi
"""

from .self_healing_system import get_self_healing_system, SelfHealingSystem

__all__ = [
    'get_self_healing_system',
    'SelfHealingSystem'
] 