#!/usr/bin/env python3
"""
Azioni di moderazione per il sistema AI di M4Bot.

Questo modulo definisce le classi che eseguono azioni di moderazione automatica
come eliminazione messaggi, timeout, ban e avvisi.
"""

import time
import asyncio
import logging
from typing import Dict, List, Any, Optional, Union

# Importazioni locali
from .models import ModeratedMessage, ModeratorAction, ActionType

# Logger
logger = logging.getLogger('m4bot.ai_moderation.actions')

class ModeratorActionExecutor:
    """
    Esecutore delle azioni di moderazione.
    Questa classe gestisce l'esecuzione delle azioni determinate dal moderatore.
    """
    
    def __init__(self, api_client=None, db_pool=None):
        """
        Inizializza l'esecutore delle azioni.
        
        Args:
            api_client: Client API per interagire con Kick.com o altre piattaforme
            db_pool: Pool di connessioni al database
        """
        self.api_client = api_client
        self.db_pool = db_pool
        
        # Mappatura tra tipi di azioni e metodi di esecuzione
        self.action_handlers = {
            ActionType.DELETE: self.delete_message,
            ActionType.TIMEOUT: self.timeout_user,
            ActionType.BAN: self.ban_user,
            ActionType.WARNING: self.warn_user,
            ActionType.REVIEW: self.flag_for_review
        }
        
        logger.info("Esecutore azioni di moderazione inizializzato")
    
    async def execute(self, action: ModeratorAction) -> bool:
        """
        Esegue un'azione di moderazione.
        
        Args:
            action: Azione da eseguire
            
        Returns:
            bool: True se l'azione è stata eseguita con successo
        """
        if action.type == ActionType.NONE:
            # Nessuna azione richiesta
            return True
            
        if action.executed:
            # Azione già eseguita
            logger.debug(f"Azione {action.type.value} già eseguita per il messaggio {action.message_id}")
            return True
            
        # Ottieni il gestore dell'azione
        handler = self.action_handlers.get(action.type)
        if not handler:
            logger.error(f"Nessun gestore trovato per l'azione {action.type.value}")
            return False
            
        try:
            # Esegui l'azione
            success = await handler(action)
            
            if success:
                # Aggiorna lo stato dell'azione
                action.executed = True
                action.executed_at = time.time()
                
                # Registra l'azione nel database
                await self._log_action(action)
                
                logger.info(f"Azione {action.type.value} eseguita per l'utente {action.user_id} nel canale {action.channel_id}")
            
            return success
        
        except Exception as e:
            logger.error(f"Errore nell'esecuzione dell'azione {action.type.value}: {e}")
            return False
    
    async def delete_message(self, action: ModeratorAction) -> bool:
        """
        Elimina un messaggio.
        
        Args:
            action: Azione di moderazione
            
        Returns:
            bool: True se l'operazione è riuscita
        """
        if not self.api_client:
            logger.warning("Nessun API client disponibile per eliminare il messaggio")
            return False
            
        try:
            # Chiama l'API per eliminare il messaggio
            result = await self.api_client.delete_message(
                channel_id=action.channel_id,
                message_id=action.message_id
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Errore nell'eliminazione del messaggio {action.message_id}: {e}")
            return False
    
    async def timeout_user(self, action: ModeratorAction) -> bool:
        """
        Mette in timeout un utente.
        
        Args:
            action: Azione di moderazione
            
        Returns:
            bool: True se l'operazione è riuscita
        """
        if not self.api_client:
            logger.warning("Nessun API client disponibile per il timeout")
            return False
            
        try:
            # Determina la durata del timeout
            duration = action.timeout_duration
            
            # Chiama l'API per il timeout
            result = await self.api_client.timeout_user(
                channel_id=action.channel_id,
                user_id=action.user_id,
                duration=duration,
                reason=action.reason
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Errore nel timeout dell'utente {action.user_id}: {e}")
            return False
    
    async def ban_user(self, action: ModeratorAction) -> bool:
        """
        Banna un utente dal canale.
        
        Args:
            action: Azione di moderazione
            
        Returns:
            bool: True se l'operazione è riuscita
        """
        if not self.api_client:
            logger.warning("Nessun API client disponibile per il ban")
            return False
            
        try:
            # Chiama l'API per bannare l'utente
            result = await self.api_client.ban_user(
                channel_id=action.channel_id,
                user_id=action.user_id,
                reason=action.reason
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Errore nel ban dell'utente {action.user_id}: {e}")
            return False
    
    async def warn_user(self, action: ModeratorAction) -> bool:
        """
        Invia un avviso all'utente.
        
        Args:
            action: Azione di moderazione
            
        Returns:
            bool: True se l'operazione è riuscita
        """
        if not self.api_client:
            logger.warning("Nessun API client disponibile per l'avviso")
            return False
            
        try:
            # Crea il messaggio di avviso
            warning_message = f"[AVVISO AUTOMATICO] {action.reason}"
            
            # Chiama l'API per inviare un messaggio privato o pubblico
            result = await self.api_client.send_channel_message(
                channel_id=action.channel_id,
                message=f"@{action.user_id} {warning_message}"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Errore nell'invio dell'avviso all'utente {action.user_id}: {e}")
            return False
    
    async def flag_for_review(self, action: ModeratorAction) -> bool:
        """
        Segnala un messaggio per la revisione da parte di un moderatore umano.
        
        Args:
            action: Azione di moderazione
            
        Returns:
            bool: True se l'operazione è riuscita
        """
        try:
            # Registra la segnalazione nel database
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO moderation_review_queue 
                        (message_id, user_id, channel_id, content, reason, created_at, status)
                        VALUES ($1, $2, $3, $4, $5, $6, 'pending')
                        """,
                        action.message_id,
                        action.user_id,
                        action.channel_id,
                        action.details.get('content', ''),
                        action.reason,
                        time.time()
                    )
            
            # Notifica i moderatori (implementazione specifica dipende dal sistema)
            # await self._notify_moderators(action)
            
            return True
        
        except Exception as e:
            logger.error(f"Errore nella segnalazione per revisione: {e}")
            return False
    
    async def _log_action(self, action: ModeratorAction):
        """
        Registra un'azione di moderazione nel database.
        
        Args:
            action: Azione di moderazione eseguita
        """
        if not self.db_pool:
            return
            
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO moderation_actions 
                    (message_id, user_id, channel_id, action_type, reason, 
                     details, executed_at, executor)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, 'ai_moderator')
                    """,
                    action.message_id,
                    action.user_id,
                    action.channel_id,
                    action.type.value,
                    action.reason,
                    action.details,
                    action.executed_at
                )
        except Exception as e:
            logger.error(f"Errore nella registrazione dell'azione di moderazione: {e}")
    
    async def _notify_moderators(self, action: ModeratorAction):
        """
        Notifica i moderatori umani di un'azione che richiede revisione.
        
        Args:
            action: Azione di moderazione
        """
        # Da implementare in base al sistema di notifica
        # Questa è solo una funzione placeholder
        pass 