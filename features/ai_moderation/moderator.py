#!/usr/bin/env python3
"""
Sistema di moderazione AI principale per M4Bot

Questo modulo implementa il sistema di moderazione basato su intelligenza artificiale
che analizza i messaggi in chat e prende azioni automatiche in base alle regole configurate.
"""

import os
import sys
import json
import asyncio
import logging
import time
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from dataclasses import dataclass, field
import aiohttp
import re

# Importa i moduli locali
from .filters import ToxicityFilter, SpamFilter, LinkFilter, ContentFilter
from .actions import ModeratorAction, ActionType
from .models import ModeratedMessage, ModerationType

# Configurazione logger
logger = logging.getLogger('m4bot.ai_moderation')

class AIModerator:
    """
    Classe principale per la moderazione AI.
    Coordina l'analisi dei messaggi e l'esecuzione delle azioni appropriate.
    """
    
    def __init__(self, db_pool=None, config: Dict[str, Any] = None):
        """
        Inizializza il moderatore AI.
        
        Args:
            db_pool: Pool di connessioni al database
            config: Configurazione personalizzata
        """
        self.db_pool = db_pool
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)
        self.session = None
        
        # Dizionario di canali con configurazioni specifiche
        # channel_id -> config
        self.channel_configs: Dict[str, Dict[str, Any]] = {}
        
        # Cache delle decisioni recenti per evitare moderazioni duplicate
        # message_id -> decision
        self.decision_cache: Dict[str, ModeratorAction] = {}
        self.cache_size = self.config.get('cache_size', 1000)
        
        # Contatori statistiche
        self.stats = {
            'processed_messages': 0,
            'flagged_messages': 0,
            'actions_taken': 0
        }
        
        # Inizializza i filtri
        self._init_filters()
        
        logger.info("Moderatore AI inizializzato")
    
    def _init_filters(self):
        """Inizializza i filtri di moderazione."""
        # Filtro per linguaggio tossico
        self.toxicity_filter = ToxicityFilter(
            threshold=self.config.get('toxicity_threshold', 0.8),
            languages=self.config.get('languages', ['it', 'en'])
        )
        
        # Filtro anti-spam
        self.spam_filter = SpamFilter(
            max_identical_messages=self.config.get('max_identical_messages', 3),
            time_window=self.config.get('spam_time_window', 60),
            max_messages_per_minute=self.config.get('max_messages_per_minute', 20)
        )
        
        # Filtro link
        self.link_filter = LinkFilter(
            check_safe_browsing=self.config.get('check_safe_browsing', False),
            allowed_domains=self.config.get('allowed_domains', []),
            safe_browsing_api_key=self.config.get('safe_browsing_api_key', '')
        )
        
        # Filtro contenuti
        self.content_filter = ContentFilter(
            banned_words=self.config.get('banned_words', []),
            banned_phrases=self.config.get('banned_phrases', []),
            sensitive_topics=self.config.get('sensitive_topics', [])
        )
        
        logger.debug(f"Filtri di moderazione inizializzati: {len(self.config.get('banned_words', []))} parole bannate")
    
    async def initialize(self):
        """Inizializza il moderatore caricando configurazioni e preparando le risorse."""
        self.session = aiohttp.ClientSession()
        
        # Carica le configurazioni dei canali dal database
        if self.db_pool:
            await self._load_channel_configs()
        
        logger.info("Moderatore AI completamente inizializzato")
    
    async def shutdown(self):
        """Rilascia le risorse e chiude le connessioni."""
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info("Moderatore AI spento correttamente")
    
    async def _load_channel_configs(self):
        """Carica le configurazioni di moderazione per tutti i canali."""
        if not self.db_pool:
            logger.warning("Nessun pool database fornito, impossibile caricare configurazioni canale")
            return
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT channel_id, moderation_settings 
                    FROM channel_settings 
                    WHERE moderation_settings IS NOT NULL
                    """
                )
                
                for row in rows:
                    channel_id = str(row['channel_id'])
                    settings = json.loads(row['moderation_settings'])
                    self.channel_configs[channel_id] = settings
                
                logger.info(f"Caricate {len(self.channel_configs)} configurazioni di canale per la moderazione")
        
        except Exception as e:
            logger.error(f"Errore nel caricamento delle configurazioni dei canali: {e}")
    
    async def update_channel_config(self, channel_id: str, config: Dict[str, Any]) -> bool:
        """
        Aggiorna la configurazione di moderazione per un canale specifico.
        
        Args:
            channel_id: ID del canale
            config: Nuova configurazione
            
        Returns:
            bool: True se l'aggiornamento è riuscito
        """
        # Aggiorna in memoria
        self.channel_configs[channel_id] = config
        
        # Aggiorna nel database
        if self.db_pool:
            try:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO channel_settings (channel_id, moderation_settings)
                        VALUES ($1, $2)
                        ON CONFLICT (channel_id) 
                        DO UPDATE SET moderation_settings = $2
                        """,
                        channel_id, json.dumps(config)
                    )
                return True
            except Exception as e:
                logger.error(f"Errore nell'aggiornamento configurazione canale {channel_id}: {e}")
                return False
        
        return True
    
    def get_channel_config(self, channel_id: str) -> Dict[str, Any]:
        """
        Ottiene la configurazione di moderazione per un canale specifico.
        
        Args:
            channel_id: ID del canale
            
        Returns:
            Dict: Configurazione del canale o configurazione predefinita
        """
        return self.channel_configs.get(channel_id, self.config)
    
    async def moderate_message(self, message: Dict[str, Any]) -> Optional[ModeratorAction]:
        """
        Modera un messaggio e determina l'azione da intraprendere.
        
        Args:
            message: Messaggio da moderare con tutti i metadati necessari
            
        Returns:
            ModeratorAction: Azione da intraprendere, o None se nessuna azione è necessaria
        """
        if not self.enabled:
            return None
        
        # Estrai le informazioni necessarie
        channel_id = str(message.get('channel_id', ''))
        user_id = str(message.get('user_id', ''))
        username = message.get('username', '')
        content = message.get('content', '')
        message_id = message.get('id', '')
        
        # Incrementa contatore messaggi processati
        self.stats['processed_messages'] += 1
        
        # Verifica se il messaggio ha un ID e se è già stato moderato
        if message_id and message_id in self.decision_cache:
            return self.decision_cache[message_id]
        
        # Ottieni la configurazione specifica del canale
        config = self.get_channel_config(channel_id)
        
        # Controlla se la moderazione è abilitata per questo canale
        if not config.get('enabled', True):
            return None
        
        # Lista dei risultati di moderazione per ciascun filtro
        results = []
        
        # Verifica linguaggio tossico
        if config.get('check_toxicity', True):
            toxicity_result = await self.toxicity_filter.check(content)
            if toxicity_result.is_violation:
                results.append(toxicity_result)
        
        # Verifica spam
        if config.get('check_spam', True):
            spam_result = await self.spam_filter.check(content, user_id, channel_id)
            if spam_result.is_violation:
                results.append(spam_result)
        
        # Verifica link
        if config.get('check_links', True):
            link_result = await self.link_filter.check(content)
            if link_result.is_violation:
                results.append(link_result)
        
        # Verifica contenuto
        if config.get('check_content', True):
            content_result = await self.content_filter.check(content)
            if content_result.is_violation:
                results.append(content_result)
        
        # Se non ci sono violazioni, il messaggio è OK
        if not results:
            return None
        
        # Incrementa contatore messaggi segnalati
        self.stats['flagged_messages'] += 1
        
        # Valuta l'azione da intraprendere in base al risultato più grave
        results.sort(key=lambda x: x.severity, reverse=True)
        worst_result = results[0]
        
        # Crea l'oggetto messaggio moderato
        moderated_message = ModeratedMessage(
            id=message_id,
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            content=content,
            type=worst_result.type,
            severity=worst_result.severity,
            violation_details=worst_result.details,
            timestamp=time.time()
        )
        
        # Determina l'azione in base alla gravità e configurazione
        action = self._determine_action(moderated_message, config)
        
        # Se è stata determinata un'azione
        if action:
            # Incrementa contatore azioni
            self.stats['actions_taken'] += 1
            
            # Salva la decisione in cache
            if message_id:
                self.decision_cache[message_id] = action
                # Controlla dimensione cache e rimuovi elementi più vecchi se necessario
                if len(self.decision_cache) > self.cache_size:
                    oldest_key = next(iter(self.decision_cache))
                    self.decision_cache.pop(oldest_key)
            
            # Registra l'azione nel database
            await self._log_moderation_action(moderated_message, action)
        
        return action
    
    def _determine_action(self, message: ModeratedMessage, config: Dict[str, Any]) -> Optional[ModeratorAction]:
        """
        Determina l'azione da intraprendere in base al tipo e alla gravità della violazione.
        
        Args:
            message: Messaggio moderato
            config: Configurazione del canale
            
        Returns:
            ModeratorAction: Azione da intraprendere, o None se nessuna azione è necessaria
        """
        # Mappa delle azioni basate su tipo e gravità
        action_map = config.get('action_map', {
            ModerationType.TOXICITY.value: {
                'low': ActionType.NONE,
                'medium': ActionType.DELETE,
                'high': ActionType.TIMEOUT
            },
            ModerationType.SPAM.value: {
                'low': ActionType.NONE,
                'medium': ActionType.DELETE,
                'high': ActionType.TIMEOUT
            },
            ModerationType.DANGEROUS_LINK.value: {
                'low': ActionType.DELETE,
                'medium': ActionType.DELETE,
                'high': ActionType.BAN
            },
            ModerationType.BANNED_CONTENT.value: {
                'low': ActionType.DELETE,
                'medium': ActionType.TIMEOUT,
                'high': ActionType.BAN
            }
        })
        
        # Ottieni l'azione raccomandata
        mod_type = message.type.value
        severity = message.severity
        
        if mod_type in action_map and severity in action_map[mod_type]:
            action_type = ActionType(action_map[mod_type][severity])
        else:
            # Azione predefinita se non mappata
            action_type = ActionType.NONE
        
        # Se l'azione è NONE, non fare nulla
        if action_type == ActionType.NONE:
            return None
        
        # Crea l'azione
        action = ModeratorAction(
            type=action_type,
            message_id=message.id,
            user_id=message.user_id,
            channel_id=message.channel_id,
            reason=f"Moderazione automatica: {message.type.name} ({severity})",
            details=message.violation_details,
            timeout_duration=config.get('timeout_duration', 300)  # 5 minuti predefiniti
        )
        
        return action
    
    async def _log_moderation_action(self, message: ModeratedMessage, action: ModeratorAction):
        """
        Registra un'azione di moderazione nel database.
        
        Args:
            message: Messaggio moderato
            action: Azione intrapresa
        """
        if not self.db_pool:
            return
        
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO moderation_logs 
                    (message_id, channel_id, user_id, username, content, violation_type, 
                     severity, action_type, reason, details, timestamp)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    message.id,
                    message.channel_id,
                    message.user_id,
                    message.username,
                    message.content,
                    message.type.value,
                    message.severity,
                    action.type.value,
                    action.reason,
                    json.dumps(action.details),
                    message.timestamp
                )
        except Exception as e:
            logger.error(f"Errore nella registrazione dell'azione di moderazione: {e}")
    
    async def get_moderation_logs(self, channel_id: str, 
                                 limit: int = 100, 
                                 offset: int = 0,
                                 user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Ottiene i log di moderazione per un canale.
        
        Args:
            channel_id: ID del canale
            limit: Limite di risultati
            offset: Offset per la paginazione
            user_id: Filtra per ID utente specifico (opzionale)
            
        Returns:
            List: Log di moderazione
        """
        if not self.db_pool:
            return []
        
        try:
            async with self.db_pool.acquire() as conn:
                query = """
                    SELECT * FROM moderation_logs 
                    WHERE channel_id = $1
                """
                params = [channel_id]
                
                if user_id:
                    query += " AND user_id = $2"
                    params.append(user_id)
                
                query += " ORDER BY timestamp DESC LIMIT $%d OFFSET $%d" % (
                    len(params) + 1, len(params) + 2
                )
                params.extend([limit, offset])
                
                rows = await conn.fetch(query, *params)
                return [dict(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Errore nel recupero dei log di moderazione: {e}")
            return []
    
    def get_user_violation_stats(self, channel_id: str, user_id: str) -> Dict[str, int]:
        """
        Ottiene statistiche sulle violazioni di un utente specifico.
        Questa funzione può essere chiamata per valutare azioni più severe per recidivi.
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente
            
        Returns:
            Dict: Statistiche sulle violazioni
        """
        # Questa è solo un'implementazione temporanea
        # In futuro, questo leggerà le statistiche dal database
        return {
            'toxicity_violations': 0,
            'spam_violations': 0,
            'link_violations': 0,
            'content_violations': 0,
            'total_violations': 0,
            'last_violation_timestamp': 0
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Ottiene le statistiche del moderatore AI.
        
        Returns:
            Dict: Statistiche sul funzionamento
        """
        return {
            'processed_messages': self.stats['processed_messages'],
            'flagged_messages': self.stats['flagged_messages'],
            'actions_taken': self.stats['actions_taken'],
            'flagged_ratio': self.stats['flagged_messages'] / max(1, self.stats['processed_messages']),
            'action_ratio': self.stats['actions_taken'] / max(1, self.stats['flagged_messages'])
        } 