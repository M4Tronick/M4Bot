#!/usr/bin/env python3
"""
M4Bot - Script di Monitoraggio Sistema

Questo script esegue il monitoraggio delle risorse di sistema e dei servizi M4Bot,
raccogliendo metriche e generando report. Può essere eseguito come servizio di background
o manualmente per controlli immediati.

Uso:
    python monitor_system.py --config PATH/TO/CONFIG [--duration SECONDS] [--export PATH/TO/FILE]
"""

import os
import sys
import json
import time
import logging
import argparse
import asyncio
from datetime import datetime
from pathlib import Path

# Aggiungi la directory principale al path
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dir)

# Importa i moduli necessari
from stability.monitoring import get_system_monitor
from stability.self_healing import get_self_healing_system

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('m4bot.scripts.monitor_system')

async def run_monitoring(config_path: str = None, duration: int = None, export_path: str = None):
    """
    Esegue il monitoraggio del sistema.
    
    Args:
        config_path: Percorso del file di configurazione
        duration: Durata del monitoraggio in secondi (None = infinito)
        export_path: Percorso dove esportare i risultati
    """
    logger.info("Avvio monitoraggio sistema")
    
    # Inizializza il monitor
    monitor = get_system_monitor(config_path)
    
    try:
        # Avvia la raccolta dati
        await monitor.start_collection()
        logger.info("Raccolta dati avviata")
        
        # Se specificata una durata finita
        if duration is not None:
            logger.info(f"Esecuzione programmata per {duration} secondi")
            await asyncio.sleep(duration)
            
            # Ferma la raccolta
            await monitor.stop_collection()
            logger.info("Raccolta dati terminata")
            
            # Esporta i risultati se richiesto
            if export_path:
                data = {
                    "timestamp": time.time(),
                    "metrics": monitor.get_all_metrics(),
                    "system_status": monitor.get_system_status()
                }
                
                # Assicura che la directory esista
                export_dir = os.path.dirname(export_path)
                if export_dir and not os.path.exists(export_dir):
                    os.makedirs(export_dir)
                
                with open(export_path, 'w') as f:
                    json.dump(data, f, indent=2)
                
                logger.info(f"Metriche esportate in {export_path}")
                
        else:
            # Esecuzione infinita, attendi fino a interrupt
            logger.info("Monitoraggio in esecuzione. Premi Ctrl+C per terminare.")
            while True:
                await asyncio.sleep(1)
                
    except KeyboardInterrupt:
        logger.info("Interruzione da tastiera, arresto in corso...")
    except Exception as e:
        logger.error(f"Errore durante il monitoraggio: {e}")
    finally:
        # Assicurati che la raccolta sia fermata
        try:
            await monitor.stop_collection()
            logger.info("Raccolta dati terminata")
        except:
            pass

async def run_with_self_healing(config_path: str = None):
    """
    Esegue il monitoraggio insieme al sistema di self-healing.
    
    Args:
        config_path: Percorso del file di configurazione
    """
    # Inizializza il monitor
    monitor = get_system_monitor(config_path)
    
    # Inizializza il sistema di self-healing
    healing_system = get_self_healing_system()
    
    try:
        # Avvia entrambi i sistemi
        await asyncio.gather(
            monitor.start_collection(),
            healing_system.start()
        )
        
        logger.info("Monitoraggio e self-healing avviati. Premi Ctrl+C per terminare.")
        
        # Esecuzione infinita, attendi fino a interrupt
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Interruzione da tastiera, arresto in corso...")
    except Exception as e:
        logger.error(f"Errore durante l'esecuzione: {e}")
    finally:
        # Assicurati che entrambi i sistemi siano fermati
        await asyncio.gather(
            monitor.stop_collection(),
            healing_system.stop()
        )
        logger.info("Sistemi arrestati")

def get_default_export_path() -> str:
    """Genera un percorso predefinito per l'esportazione."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    reports_dir = Path(parent_dir) / "logs" / "reports"
    reports_dir.mkdir(exist_ok=True, parents=True)
    return str(reports_dir / f"system_metrics_{timestamp}.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="M4Bot System Monitoring Tool")
    parser.add_argument("--config", type=str, help="Percorso del file di configurazione")
    parser.add_argument("--duration", type=int, help="Durata del monitoraggio in secondi")
    parser.add_argument("--export", type=str, help="Percorso dove esportare i risultati")
    parser.add_argument("--with-healing", action="store_true", help="Avvia anche il sistema di self-healing")
    
    args = parser.parse_args()
    
    # Se non specificato, usa un percorso predefinito per l'export
    if args.duration is not None and not args.export:
        args.export = get_default_export_path()
    
    # Esegui il monitoraggio
    if args.with_healing:
        asyncio.run(run_with_self_healing(args.config))
    else:
        asyncio.run(run_monitoring(args.config, args.duration, args.export)) 