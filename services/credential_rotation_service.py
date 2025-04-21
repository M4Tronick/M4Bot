#!/usr/bin/env python3
"""
Servizio di rotazione delle credenziali.
Questo servizio esegue periodicamente la rotazione delle credenziali
e invia notifiche per le rotazioni imminenti.
"""

import os
import sys
import time
import logging
import asyncio
import schedule
import datetime
from pathlib import Path

# Aggiungi la directory principale al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importa il modulo di rotazione delle credenziali
from security.credential_rotation import CredentialRotationManager

# Configurazione del logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/security/credential_rotation_service.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("CredentialRotationService")

class CredentialRotationService:
    """Servizio che gestisce la rotazione periodica delle credenziali."""
    
    def __init__(self, config_path: str = None, notification_channel = None):
        """
        Inizializza il servizio di rotazione.
        
        Args:
            config_path: Percorso del file di configurazione
            notification_channel: Canale per le notifiche (opzionale)
        """
        self.config_path = config_path or "config/security/credential_rotation.json"
        self.manager = CredentialRotationManager(self.config_path)
        self.notification_channel = notification_channel
        self.running = False
        logger.info("Servizio di rotazione credenziali inizializzato")
    
    async def send_notification(self, message: str, level: str = "info"):
        """
        Invia una notifica.
        
        Args:
            message: Messaggio da inviare
            level: Livello di importanza (info, warning, error)
        """
        # Logga il messaggio
        if level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)
        else:
            logger.info(message)
        
        # Se esiste un canale di notifica, invia il messaggio
        if self.notification_channel:
            try:
                await self.notification_channel.send(message, level)
            except Exception as e:
                logger.error(f"Errore nell'invio della notifica: {e}")
    
    async def check_and_send_notifications(self):
        """Verifica le rotazioni imminenti e invia notifiche."""
        try:
            # Ottieni i giorni di anticipo dalla configurazione
            days_before = self.manager.config.get("notification_days_before", 3)
            
            # Verifica le rotazioni imminenti
            upcoming = self.manager.check_upcoming_rotations(days_before)
            
            if upcoming:
                # Invia notifiche per le rotazioni imminenti
                for cred in upcoming:
                    message = (f"⚠️ Rotazione credenziale imminente: {cred['name']} ({cred['service']}) "
                              f"prevista per {cred['scheduled_date']} "
                              f"(tra {cred['days_until_rotation']} giorni)")
                    await self.send_notification(message, "warning")
            
            # Verifica anche le rotazioni in ritardo
            pending = self.manager.check_pending_rotations()
            
            if pending:
                # Invia notifiche per le rotazioni in ritardo
                for cred in pending:
                    days_overdue = cred.get('days_overdue', 0)
                    if days_overdue > 0:
                        message = (f"🚨 Rotazione credenziale in ritardo: {cred['name']} ({cred['service']}) "
                                  f"prevista per {cred['scheduled_date']} "
                                  f"({days_overdue} giorni di ritardo)")
                        await self.send_notification(message, "error")
            
            return True
        except Exception as e:
            logger.error(f"Errore nella verifica delle rotazioni imminenti: {e}")
            return False
    
    async def perform_scheduled_rotation(self):
        """Esegue la rotazione programmata delle credenziali."""
        try:
            logger.info("Avvio rotazione programmata delle credenziali")
            
            # Esegui la rotazione
            await self.manager.start_scheduled_rotation()
            
            # Esegui la pulizia dei backup
            removed = self.manager.cleanup_old_backups()
            if removed > 0:
                logger.info(f"Rimossi {removed} backup obsoleti")
            
            return True
        except Exception as e:
            logger.error(f"Errore nella rotazione programmata: {e}")
            await self.send_notification(
                f"Errore nella rotazione programmata delle credenziali: {str(e)}", "error")
            return False
    
    async def run_daily_job(self):
        """Esegue il job giornaliero."""
        await self.check_and_send_notifications()
        await self.perform_scheduled_rotation()
    
    def start(self):
        """Avvia il servizio di rotazione."""
        if self.running:
            logger.warning("Il servizio è già in esecuzione")
            return
        
        self.running = True
        logger.info("Avvio del servizio di rotazione credenziali")
        
        # Pianifica l'esecuzione giornaliera
        schedule.every().day.at("02:00").do(lambda: asyncio.run(self.run_daily_job()))
        
        # Pianifica controllo delle notifiche ogni 6 ore
        schedule.every(6).hours.do(lambda: asyncio.run(self.check_and_send_notifications()))
        
        try:
            # Esegui immediatamente il controllo delle notifiche
            asyncio.run(self.check_and_send_notifications())
            
            # Loop principale
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # Controlla ogni minuto
        except KeyboardInterrupt:
            logger.info("Interruzione del servizio richiesta dall'utente")
            self.running = False
        except Exception as e:
            logger.error(f"Errore nel servizio di rotazione: {e}")
            self.running = False
    
    def stop(self):
        """Ferma il servizio."""
        logger.info("Arresto del servizio di rotazione credenziali")
        self.running = False

async def main():
    """Funzione principale."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Servizio di rotazione delle credenziali")
    parser.add_argument("--config", help="Percorso del file di configurazione")
    parser.add_argument("--run-once", action="store_true", 
                        help="Esegui una singola rotazione e termina")
    parser.add_argument("--notify-only", action="store_true",
                        help="Controlla solo le notifiche senza eseguire rotazioni")
    
    args = parser.parse_args()
    
    service = CredentialRotationService(args.config)
    
    if args.run_once:
        # Esegui una singola rotazione
        if args.notify_only:
            await service.check_and_send_notifications()
        else:
            await service.run_daily_job()
    else:
        # Avvia il servizio in modalità continua
        service.start()

if __name__ == "__main__":
    asyncio.run(main()) 