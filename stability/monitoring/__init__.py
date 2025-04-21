"""
M4Bot - Modulo di Monitoraggio

Questo modulo implementa funzionalità di monitoraggio avanzato per il sistema M4Bot,
tracciando metriche di performance, stato delle risorse, e salute generale del sistema.

Componenti principali:
- SystemMonitor: monitora risorse di sistema e performance
- MetricsCollector: raccoglie e analizza metriche di applicazione
- ServiceMonitor: verifica la disponibilità di servizi interni ed esterni
"""

from .system_monitor import get_system_monitor, SystemMonitor, MetricType

__all__ = [
    'get_system_monitor',
    'SystemMonitor',
    'MetricType'
] 