"""
Modulo per la gestione delle notifiche e avvisi.
Implementa il sistema di notifica per eventi critici, warning e informativi.
"""

import os
import asyncio
import datetime
import logging
import json
import hashlib
import secrets
from typing import Dict, List, Optional, Union, Any

import aiohttp
import asyncpg
import aioredis
import aiosmtplib
from email.message import EmailMessage

logger = logging.getLogger('notifications')

class ChannelManager:
    """Gestisce i canali di notifica (email, Telegram, Discord, ecc.)."""
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.channels = {}
    
    async def load_channels(self):
        """Carica i canali di notifica dal database."""
        try:
            async with self.db_pool.acquire() as conn:
                channels = await conn.fetch("""
                    SELECT id, name, type, config, is_active, created_at, updated_at
                    FROM notification_channels
                    WHERE is_active = true
                """)
                
                for channel in channels:
                    self.channels[channel['id']] = {
                        'name': channel['name'],
                        'type': channel['type'],
                        'config': json.loads(channel['config']),
                        'created_at': channel['created_at'],
                        'updated_at': channel['updated_at']
                    }
                
                logger.info(f"Caricati {len(self.channels)} canali di notifica")
        except Exception as e:
            logger.error(f"Errore durante il caricamento dei canali di notifica: {e}")
    
    async def get_channels(self, channel_type: str = None) -> List[Dict[str, Any]]:
        """Ottiene tutti i canali di notifica, opzionalmente filtrati per tipo."""
        if not self.channels:
            await self.load_channels()
            
        if channel_type:
            return [
                {'id': k, **v} for k, v in self.channels.items() 
                if v['type'] == channel_type
            ]
        else:
            return [{'id': k, **v} for k, v in self.channels.items()]
    
    async def get_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Ottiene un canale di notifica specifico."""
        if not self.channels:
            await self.load_channels()
            
        if channel_id in self.channels:
            return {'id': channel_id, **self.channels[channel_id]}
        return None
    
    async def create_channel(self, channel_data: Dict[str, Any]) -> Optional[int]:
        """Crea un nuovo canale di notifica."""
        try:
            # Validazione dei dati
            if 'name' not in channel_data or 'type' not in channel_data:
                logger.error("Nome o tipo del canale mancante")
                return None
                
            if 'config' not in channel_data:
                channel_data['config'] = {}
                
            async with self.db_pool.acquire() as conn:
                # Verifica se il canale esiste già
                existing = await conn.fetchval("""
                    SELECT id FROM notification_channels
                    WHERE name = $1
                """, channel_data['name'])
                
                if existing:
                    logger.warning(f"Un canale con il nome {channel_data['name']} esiste già")
                    return None
                
                # Crea il canale
                channel_id = await conn.fetchval("""
                    INSERT INTO notification_channels 
                    (name, type, config, is_active)
                    VALUES ($1, $2, $3, $4)
                    RETURNING id
                """, channel_data['name'], channel_data['type'], 
                json.dumps(channel_data['config']), 
                channel_data.get('is_active', True))
                
                # Aggiorna la cache locale
                self.channels[channel_id] = {
                    'name': channel_data['name'],
                    'type': channel_data['type'],
                    'config': channel_data['config'],
                    'created_at': datetime.datetime.now(),
                    'updated_at': datetime.datetime.now()
                }
                
                return channel_id
        except Exception as e:
            logger.error(f"Errore nella creazione del canale di notifica: {e}")
            return None
    
    async def update_channel(self, channel_id: int, channel_data: Dict[str, Any]) -> bool:
        """Aggiorna un canale di notifica esistente."""
        try:
            if channel_id not in self.channels:
                logger.warning(f"Canale con ID {channel_id} non trovato")
                return False
                
            fields_to_update = []
            params = []
            param_idx = 1
            
            updatable_fields = {'name': 'name', 'type': 'type', 'is_active': 'is_active'}
            
            for field, db_field in updatable_fields.items():
                if field in channel_data:
                    fields_to_update.append(f"{db_field} = ${param_idx}")
                    params.append(channel_data[field])
                    param_idx += 1
            
            # Gestione speciale per config (JSON)
            if 'config' in channel_data:
                fields_to_update.append(f"config = ${param_idx}")
                params.append(json.dumps(channel_data['config']))
                param_idx += 1
            
            if not fields_to_update:
                logger.warning("Nessun campo da aggiornare")
                return False
                
            # Aggiungi updated_at e channel_id
            fields_str = ", ".join(fields_to_update)
            fields_str += f", updated_at = ${param_idx}"
            params.append(datetime.datetime.now())
            param_idx += 1
            
            params.append(channel_id)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute(f"""
                    UPDATE notification_channels
                    SET {fields_str}
                    WHERE id = ${param_idx}
                """, *params)
                
                # Aggiorna la cache
                channel = self.channels[channel_id]
                for field in updatable_fields:
                    if field in channel_data:
                        channel[updatable_fields[field]] = channel_data[field]
                
                if 'config' in channel_data:
                    channel['config'] = channel_data['config']
                    
                channel['updated_at'] = datetime.datetime.now()
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento del canale {channel_id}: {e}")
            return False
    
    async def delete_channel(self, channel_id: int) -> bool:
        """Elimina un canale di notifica."""
        try:
            if channel_id not in self.channels:
                logger.warning(f"Canale con ID {channel_id} non trovato")
                return False
                
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM notification_channels
                    WHERE id = $1
                """, channel_id)
                
                # Rimuovi dalla cache
                if channel_id in self.channels:
                    del self.channels[channel_id]
                    
                return True
        except Exception as e:
            logger.error(f"Errore nell'eliminazione del canale {channel_id}: {e}")
            return False
    
    async def send_notification(self, channel_id: int, subject: str, message: str, 
                              data: Dict[str, Any] = None) -> bool:
        """Invia una notifica attraverso un canale specifico."""
        try:
            channel = await self.get_channel(channel_id)
            if not channel:
                logger.warning(f"Canale con ID {channel_id} non trovato")
                return False
                
            if channel['type'] == 'email':
                return await self._send_email_notification(channel, subject, message, data)
            elif channel['type'] == 'telegram':
                return await self._send_telegram_notification(channel, subject, message, data)
            elif channel['type'] == 'discord':
                return await self._send_discord_notification(channel, subject, message, data)
            elif channel['type'] == 'webhook':
                return await self._send_webhook_notification(channel, subject, message, data)
            else:
                logger.warning(f"Tipo di canale non supportato: {channel['type']}")
                return False
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica tramite il canale {channel_id}: {e}")
            return False
    
    async def _send_email_notification(self, channel: Dict[str, Any], subject: str, 
                                     message: str, data: Dict[str, Any] = None) -> bool:
        """Invia una notifica via email."""
        try:
            config = channel['config']
            if not config or not all(k in config for k in ['smtp_server', 'smtp_port', 'username', 'password', 'from_email']):
                logger.error(f"Configurazione email mancante o incompleta per il canale {channel['id']}")
                return False
                
            # Crea il messaggio email
            email_msg = EmailMessage()
            email_msg['From'] = config['from_email']
            email_msg['To'] = config.get('to_email', config['from_email'])
            email_msg['Subject'] = subject
            
            # Imposta il contenuto
            email_msg.set_content(message)
            
            # Invia l'email
            await aiosmtplib.send(
                email_msg,
                hostname=config['smtp_server'],
                port=config['smtp_port'],
                username=config['username'],
                password=config['password'],
                use_tls=config.get('use_tls', True)
            )
            
            return True
        except Exception as e:
            logger.error(f"Errore nell'invio dell'email: {e}")
            return False
    
    async def _send_telegram_notification(self, channel: Dict[str, Any], subject: str, 
                                        message: str, data: Dict[str, Any] = None) -> bool:
        """Invia una notifica via Telegram."""
        try:
            config = channel['config']
            if not config or not all(k in config for k in ['bot_token', 'chat_id']):
                logger.error(f"Configurazione Telegram mancante o incompleta per il canale {channel['id']}")
                return False
                
            # Prepara il messaggio
            text = f"*{subject}*\n\n{message}"
            
            # Invia il messaggio
            url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
            payload = {
                'chat_id': config['chat_id'],
                'text': text,
                'parse_mode': 'Markdown'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Errore nell'invio del messaggio Telegram: {response.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica Telegram: {e}")
            return False
    
    async def _send_discord_notification(self, channel: Dict[str, Any], subject: str, 
                                       message: str, data: Dict[str, Any] = None) -> bool:
        """Invia una notifica via Discord webhook."""
        try:
            config = channel['config']
            if not config or 'webhook_url' not in config:
                logger.error(f"Configurazione Discord mancante o incompleta per il canale {channel['id']}")
                return False
                
            # Prepara il payload
            payload = {
                'content': f"**{subject}**\n{message}"
            }
            
            # Se ci sono embed, aggiungili
            if data and 'embeds' in data:
                payload['embeds'] = data['embeds']
            
            async with aiohttp.ClientSession() as session:
                async with session.post(config['webhook_url'], json=payload) as response:
                    if response.status in [200, 204]:
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Errore nell'invio del messaggio Discord: {response.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica Discord: {e}")
            return False
    
    async def _send_webhook_notification(self, channel: Dict[str, Any], subject: str, 
                                       message: str, data: Dict[str, Any] = None) -> bool:
        """Invia una notifica via webhook generico."""
        try:
            config = channel['config']
            if not config or 'webhook_url' not in config:
                logger.error(f"Configurazione webhook mancante o incompleta per il canale {channel['id']}")
                return False
                
            # Prepara il payload
            payload = {
                'subject': subject,
                'message': message,
                'timestamp': datetime.datetime.now().isoformat()
            }
            
            # Aggiungi dati aggiuntivi se presenti
            if data:
                payload['data'] = data
                
            headers = {}
            if 'headers' in config:
                headers = config['headers']
                
            async with aiohttp.ClientSession() as session:
                async with session.post(config['webhook_url'], json=payload, headers=headers) as response:
                    if response.status in [200, 201, 202, 204]:
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Errore nell'invio del webhook: {response.status} - {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica webhook: {e}")
            return False

class AlertPolicy:
    """Gestisce le politiche di avviso per determinare quando e come inviare notifiche."""
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.policies = {}
    
    async def load_policies(self):
        """Carica le politiche di avviso dal database."""
        try:
            async with self.db_pool.acquire() as conn:
                policies = await conn.fetch("""
                    SELECT id, name, description, alert_type, severity_filter, 
                           cooldown_minutes, is_active, created_at, updated_at, 
                           notification_channels, conditions
                    FROM alert_policies
                    WHERE is_active = true
                """)
                
                for policy in policies:
                    self.policies[policy['id']] = {
                        'name': policy['name'],
                        'description': policy['description'],
                        'alert_type': policy['alert_type'],
                        'severity_filter': policy['severity_filter'],
                        'cooldown_minutes': policy['cooldown_minutes'],
                        'notification_channels': json.loads(policy['notification_channels']),
                        'conditions': json.loads(policy['conditions']),
                        'created_at': policy['created_at'],
                        'updated_at': policy['updated_at']
                    }
                
                logger.info(f"Caricate {len(self.policies)} politiche di avviso")
        except Exception as e:
            logger.error(f"Errore durante il caricamento delle politiche di avviso: {e}")
    
    async def get_policies(self, alert_type: str = None) -> List[Dict[str, Any]]:
        """Ottiene tutte le politiche di avviso, opzionalmente filtrate per tipo."""
        if not self.policies:
            await self.load_policies()
            
        if alert_type:
            return [
                {'id': k, **v} for k, v in self.policies.items() 
                if v['alert_type'] == alert_type
            ]
        else:
            return [{'id': k, **v} for k, v in self.policies.items()]
    
    async def get_policy(self, policy_id: int) -> Optional[Dict[str, Any]]:
        """Ottiene una politica di avviso specifica."""
        if not self.policies:
            await self.load_policies()
            
        if policy_id in self.policies:
            return {'id': policy_id, **self.policies[policy_id]}
        return None
    
    async def create_policy(self, policy_data: Dict[str, Any]) -> Optional[int]:
        """Crea una nuova politica di avviso."""
        try:
            # Validazione dei dati
            if not all(k in policy_data for k in ['name', 'alert_type', 'severity_filter']):
                logger.error("Dati della politica mancanti o incompleti")
                return None
                
            if 'notification_channels' not in policy_data:
                policy_data['notification_channels'] = []
                
            if 'conditions' not in policy_data:
                policy_data['conditions'] = {}
                
            async with self.db_pool.acquire() as conn:
                # Verifica se la politica esiste già
                existing = await conn.fetchval("""
                    SELECT id FROM alert_policies
                    WHERE name = $1
                """, policy_data['name'])
                
                if existing:
                    logger.warning(f"Una politica con il nome {policy_data['name']} esiste già")
                    return None
                
                # Crea la politica
                policy_id = await conn.fetchval("""
                    INSERT INTO alert_policies 
                    (name, description, alert_type, severity_filter, cooldown_minutes, 
                     is_active, notification_channels, conditions)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                """, policy_data['name'], policy_data.get('description', ''),
                policy_data['alert_type'], policy_data['severity_filter'],
                policy_data.get('cooldown_minutes', 15),
                policy_data.get('is_active', True),
                json.dumps(policy_data['notification_channels']),
                json.dumps(policy_data['conditions']))
                
                # Aggiorna la cache locale
                self.policies[policy_id] = {
                    'name': policy_data['name'],
                    'description': policy_data.get('description', ''),
                    'alert_type': policy_data['alert_type'],
                    'severity_filter': policy_data['severity_filter'],
                    'cooldown_minutes': policy_data.get('cooldown_minutes', 15),
                    'notification_channels': policy_data['notification_channels'],
                    'conditions': policy_data['conditions'],
                    'created_at': datetime.datetime.now(),
                    'updated_at': datetime.datetime.now()
                }
                
                return policy_id
        except Exception as e:
            logger.error(f"Errore nella creazione della politica di avviso: {e}")
            return None
    
    async def update_policy(self, policy_id: int, policy_data: Dict[str, Any]) -> bool:
        """Aggiorna una politica di avviso esistente."""
        try:
            if policy_id not in self.policies:
                logger.warning(f"Politica con ID {policy_id} non trovata")
                return False
                
            fields_to_update = []
            params = []
            param_idx = 1
            
            updatable_fields = {
                'name': 'name', 
                'description': 'description', 
                'alert_type': 'alert_type',
                'severity_filter': 'severity_filter',
                'cooldown_minutes': 'cooldown_minutes',
                'is_active': 'is_active'
            }
            
            for field, db_field in updatable_fields.items():
                if field in policy_data:
                    fields_to_update.append(f"{db_field} = ${param_idx}")
                    params.append(policy_data[field])
                    param_idx += 1
            
            # Gestione speciale per campi JSON
            json_fields = {
                'notification_channels': 'notification_channels',
                'conditions': 'conditions'
            }
            
            for field, db_field in json_fields.items():
                if field in policy_data:
                    fields_to_update.append(f"{db_field} = ${param_idx}")
                    params.append(json.dumps(policy_data[field]))
                    param_idx += 1
            
            if not fields_to_update:
                logger.warning("Nessun campo da aggiornare")
                return False
                
            # Aggiungi updated_at e policy_id
            fields_str = ", ".join(fields_to_update)
            fields_str += f", updated_at = ${param_idx}"
            params.append(datetime.datetime.now())
            param_idx += 1
            
            params.append(policy_id)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute(f"""
                    UPDATE alert_policies
                    SET {fields_str}
                    WHERE id = ${param_idx}
                """, *params)
                
                # Aggiorna la cache
                policy = self.policies[policy_id]
                for field in updatable_fields:
                    if field in policy_data:
                        policy[field] = policy_data[field]
                
                for field in json_fields:
                    if field in policy_data:
                        policy[field] = policy_data[field]
                        
                policy['updated_at'] = datetime.datetime.now()
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento della politica {policy_id}: {e}")
            return False
    
    async def delete_policy(self, policy_id: int) -> bool:
        """Elimina una politica di avviso."""
        try:
            if policy_id not in self.policies:
                logger.warning(f"Politica con ID {policy_id} non trovata")
                return False
                
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    DELETE FROM alert_policies
                    WHERE id = $1
                """, policy_id)
                
                # Rimuovi dalla cache
                if policy_id in self.policies:
                    del self.policies[policy_id]
                    
                return True
        except Exception as e:
            logger.error(f"Errore nell'eliminazione della politica {policy_id}: {e}")
            return False
    
    async def should_alert(self, alert_type: str, severity: str, 
                         component: str = None, data: Dict[str, Any] = None) -> List[int]:
        """
        Determina se inviare un avviso in base alle politiche configurate.
        Restituisce un elenco di ID dei canali di notifica da utilizzare.
        """
        if not self.policies:
            await self.load_policies()
            
        matching_channels = []
        
        for policy_id, policy in self.policies.items():
            # Verifica il tipo di avviso
            if policy['alert_type'] != alert_type and policy['alert_type'] != 'all':
                continue
                
            # Verifica la severità
            if severity not in policy['severity_filter']:
                continue
                
            # Verifica il componente se specificato
            if component and 'component' in policy['conditions']:
                if policy['conditions']['component'] != component and policy['conditions']['component'] != '*':
                    continue
                    
            # Verifica altre condizioni personalizzate
            if data and 'custom' in policy['conditions']:
                # Logica per valutare condizioni personalizzate complesse
                # Questo è solo un esempio semplificato
                all_match = True
                for key, value in policy['conditions']['custom'].items():
                    if key not in data or data[key] != value:
                        all_match = False
                        break
                        
                if not all_match:
                    continue
            
            # Aggiungi i canali di notifica di questa politica
            matching_channels.extend(policy['notification_channels'])
            
        # Rimuovi duplicati
        return list(set(matching_channels))

class NotificationManager:
    """Manager principale per il sistema di notifiche."""
    
    def __init__(self, db_pool: asyncpg.Pool, redis_pool: aioredis.ConnectionPool):
        self.db_pool = db_pool
        self.redis_pool = redis_pool
        self.channel_manager = ChannelManager(db_pool)
        self.alert_policy = AlertPolicy(db_pool)
        self.webhook_tokens = {}
    
    async def initialize(self):
        """Inizializza il manager, caricando le configurazioni necessarie."""
        # Carica i canali di notifica
        await self.channel_manager.load_channels()
        
        # Carica le politiche di avviso
        await self.alert_policy.load_policies()
        
        # Carica i token webhook
        await self._load_webhook_tokens()
        
        logger.info("NotificationManager inizializzato")
    
    async def _load_webhook_tokens(self):
        """Carica i token webhook dal database."""
        try:
            async with self.db_pool.acquire() as conn:
                tokens = await conn.fetch("""
                    SELECT token, service_name, description, is_active, created_at
                    FROM webhook_tokens
                    WHERE is_active = true
                """)
                
                for token_record in tokens:
                    self.webhook_tokens[token_record['token']] = {
                        'service_name': token_record['service_name'],
                        'description': token_record['description'],
                        'created_at': token_record['created_at']
                    }
                
                logger.info(f"Caricati {len(self.webhook_tokens)} token webhook")
        except Exception as e:
            logger.error(f"Errore durante il caricamento dei token webhook: {e}")
    
    async def create_webhook_token(self, service_name: str, description: str = None) -> Optional[str]:
        """Crea un nuovo token webhook per un servizio."""
        try:
            # Genera un token casuale
            token = secrets.token_hex(16)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO webhook_tokens (token, service_name, description, is_active)
                    VALUES ($1, $2, $3, $4)
                """, token, service_name, description, True)
                
                # Aggiungi alla cache locale
                self.webhook_tokens[token] = {
                    'service_name': service_name,
                    'description': description,
                    'created_at': datetime.datetime.now()
                }
                
                return token
        except Exception as e:
            logger.error(f"Errore nella creazione del token webhook: {e}")
            return None
    
    async def revoke_webhook_token(self, token: str) -> bool:
        """Revoca un token webhook esistente."""
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.execute("""
                    UPDATE webhook_tokens
                    SET is_active = false
                    WHERE token = $1
                """, token)
                
                # Rimuovi dalla cache locale
                if token in self.webhook_tokens:
                    del self.webhook_tokens[token]
                    
                return True
        except Exception as e:
            logger.error(f"Errore nella revoca del token webhook: {e}")
            return False
    
    async def validate_webhook_token(self, token: str) -> bool:
        """Verifica se un token webhook è valido."""
        if not self.webhook_tokens:
            await self._load_webhook_tokens()
            
        return token in self.webhook_tokens
    
    async def log_webhook_event(self, token: str, source: str, event_type: str, 
                              severity: str, payload: Dict[str, Any]) -> Optional[int]:
        """Registra un evento webhook nel database."""
        try:
            async with self.db_pool.acquire() as conn:
                event_id = await conn.fetchval("""
                    INSERT INTO webhook_events (token, source, event_type, severity, payload)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                """, token, source, event_type, severity, json.dumps(payload))
                
                return event_id
        except Exception as e:
            logger.error(f"Errore nella registrazione dell'evento webhook: {e}")
            return None
    
    async def get_webhook_events(self, limit: int = 100, 
                               source: str = None, severity: str = None) -> List[Dict[str, Any]]:
        """Ottiene gli eventi webhook registrati."""
        try:
            query = """
                SELECT id, token, source, event_type, severity, payload, created_at
                FROM webhook_events
                WHERE 1=1
            """
            
            params = []
            param_idx = 1
            
            if source:
                query += f" AND source = ${param_idx}"
                params.append(source)
                param_idx += 1
                
            if severity:
                query += f" AND severity = ${param_idx}"
                params.append(severity)
                param_idx += 1
                
            query += " ORDER BY created_at DESC LIMIT $" + str(param_idx)
            params.append(limit)
            
            async with self.db_pool.acquire() as conn:
                events = await conn.fetch(query, *params)
                
                return [dict(event) for event in events]
        except Exception as e:
            logger.error(f"Errore nell'ottenimento degli eventi webhook: {e}")
            return []
    
    async def send_alert(self, alert_type: str, severity: str, message: str, 
                        subject: str = None, component: str = None, 
                        data: Dict[str, Any] = None) -> bool:
        """Invia un avviso in base alla politica configurata."""
        try:
            # Registra l'avviso nel database
            alert_id = await self._create_alert(
                alert_type=alert_type,
                severity=severity,
                message=message,
                subject=subject,
                component=component,
                data=data
            )
            
            if not alert_id:
                logger.error("Impossibile creare l'avviso nel database")
                return False
                
            # Determina i canali da notificare
            channel_ids = await self.alert_policy.should_alert(
                alert_type=alert_type,
                severity=severity,
                component=component,
                data=data
            )
            
            if not channel_ids:
                logger.info(f"Nessun canale abbinato per l'avviso {alert_id}")
                return True  # Non è un errore, solo nessun canale configurato
                
            # Invia le notifiche attraverso i canali
            success = True
            for channel_id in channel_ids:
                result = await self.channel_manager.send_notification(
                    channel_id=channel_id,
                    subject=subject or f"Avviso: {component or alert_type}",
                    message=message,
                    data=data
                )
                
                # Registra la notifica inviata
                await self._log_notification(alert_id, channel_id, result)
                
                if not result:
                    success = False
                    
            return success
        except Exception as e:
            logger.error(f"Errore nell'invio dell'avviso: {e}")
            return False
    
    async def send_system_alert(self, component: str, status: str, message: str) -> bool:
        """Invia un avviso di sistema."""
        severity = self._map_status_to_severity(status)
        
        return await self.send_alert(
            alert_type='system',
            severity=severity,
            message=message,
            subject=f"Avviso sistema: {component}",
            component=component,
            data={'status': status}
        )
    
    async def send_service_alert(self, service_id: int, service_name: str, 
                               status: str, message: str) -> bool:
        """Invia un avviso di servizio."""
        severity = self._map_status_to_severity(status)
        
        return await self.send_alert(
            alert_type='service',
            severity=severity,
            message=message,
            subject=f"Servizio {service_name}",
            component='service',
            data={
                'service_id': service_id,
                'service_name': service_name,
                'status': status
            }
        )
    
    async def process_alert(self, event_id: int) -> bool:
        """Processa un evento webhook e genera avvisi se necessario."""
        try:
            async with self.db_pool.acquire() as conn:
                event = await conn.fetchrow("""
                    SELECT token, source, event_type, severity, payload
                    FROM webhook_events
                    WHERE id = $1
                """, event_id)
                
                if not event:
                    logger.warning(f"Evento webhook {event_id} non trovato")
                    return False
                    
                # Ottieni info sul servizio dal token
                token_info = self.webhook_tokens.get(event['token'])
                if not token_info:
                    logger.warning(f"Token webhook non valido per l'evento {event_id}")
                    return False
                    
                # Crea il messaggio di avviso
                service_name = token_info['service_name']
                payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
                
                message = payload.get('message', f"Evento da {service_name}: {event['event_type']}")
                
                # Invia l'avviso
                return await self.send_alert(
                    alert_type='webhook',
                    severity=event['severity'],
                    message=message,
                    subject=f"Webhook {service_name}",
                    component='webhook',
                    data={
                        'source': event['source'],
                        'event_type': event['event_type'],
                        'service_name': service_name,
                        'payload': payload
                    }
                )
        except Exception as e:
            logger.error(f"Errore nel processamento dell'evento webhook {event_id}: {e}")
            return False
    
    async def get_recent_alerts(self, limit: int = 10, resolved: bool = None) -> List[Dict[str, Any]]:
        """Ottieni gli avvisi recenti."""
        try:
            query = """
                SELECT id, alert_type, severity, subject, message, component, data,
                       created_at, resolved_at
                FROM alerts
                WHERE 1=1
            """
            
            params = []
            param_idx = 1
            
            if resolved is not None:
                if resolved:
                    query += f" AND resolved_at IS NOT NULL"
                else:
                    query += f" AND resolved_at IS NULL"
                    
            query += " ORDER BY created_at DESC LIMIT $" + str(param_idx)
            params.append(limit)
            
            async with self.db_pool.acquire() as conn:
                alerts = await conn.fetch(query, *params)
                
                return [dict(alert) for alert in alerts]
        except Exception as e:
            logger.error(f"Errore nell'ottenimento degli avvisi recenti: {e}")
            return []
    
    async def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Ottieni gli avvisi attivi (non risolti)."""
        return await self.get_recent_alerts(limit=100, resolved=False)
    
    async def resolve_alert(self, alert_id: int, resolution_note: str = None) -> bool:
        """Risolvi un avviso."""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE alerts
                    SET resolved_at = $1, resolution_note = $2
                    WHERE id = $3
                """, datetime.datetime.now(), resolution_note, alert_id)
                
                return True
        except Exception as e:
            logger.error(f"Errore nella risoluzione dell'avviso {alert_id}: {e}")
            return False
    
    async def _create_alert(self, alert_type: str, severity: str, message: str, 
                          subject: str = None, component: str = None, 
                          data: Dict[str, Any] = None) -> Optional[int]:
        """Crea un avviso nel database."""
        try:
            async with self.db_pool.acquire() as conn:
                alert_id = await conn.fetchval("""
                    INSERT INTO alerts 
                    (alert_type, severity, subject, message, component, data)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id
                """, alert_type, severity, subject, message, component, 
                json.dumps(data) if data else None)
                
                return alert_id
        except Exception as e:
            logger.error(f"Errore nella creazione dell'avviso: {e}")
            return None
    
    async def _log_notification(self, alert_id: int, channel_id: int, success: bool) -> bool:
        """Registra una notifica inviata."""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO alert_notifications 
                    (alert_id, channel_id, success)
                    VALUES ($1, $2, $3)
                """, alert_id, channel_id, success)
                
                return True
        except Exception as e:
            logger.error(f"Errore nella registrazione della notifica: {e}")
            return False
    
    def _map_status_to_severity(self, status: str) -> str:
        """Converte uno stato di monitoraggio in un livello di severità."""
        status_map = {
            'critical': 'critical',
            'error': 'critical',
            'warning': 'warning',
            'ok': 'info',
            'success': 'info',
            'info': 'info'
        }
        
        return status_map.get(status.lower(), 'info') 