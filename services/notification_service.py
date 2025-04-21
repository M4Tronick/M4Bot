#!/usr/bin/env python3
"""
Sistema di notifiche multi-canale per M4Bot

Questo modulo implementa un sistema di notifiche completo che supporta l'invio di avvisi e messaggi
attraverso diversi canali: Telegram, Discord, Email, push web, ecc.
Offre una API unificata per l'invio di notifiche e gestisce le preferenze degli utenti.
"""

import os
import sys
import json
import time
import asyncio
import logging
import smtplib
import aiohttp
import uuid
from typing import Dict, List, Any, Optional, Union
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Imposta il percorso per i moduli
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from security.crypto import CryptoManager

# Configurazione logger
logger = logging.getLogger('m4bot.notification')

# Definizioni dei tipi di notifiche
class NotificationType(Enum):
    STREAM_START = 'stream_start'          # Inizio diretta
    STREAM_END = 'stream_end'              # Fine diretta
    NEW_FOLLOWER = 'new_follower'          # Nuovo follower
    NEW_SUBSCRIPTION = 'new_subscription'  # Nuova iscrizione
    DONATION = 'donation'                  # Donazione ricevuta
    SYSTEM_ALERT = 'system_alert'          # Avviso di sistema (errore, ecc.)
    SCHEDULED_EVENT = 'scheduled_event'    # Evento programmato
    CUSTOM = 'custom'                      # Notifica personalizzata

# Canali di notifica supportati
class NotificationChannel(Enum):
    EMAIL = 'email'            # Notifiche via email
    TELEGRAM = 'telegram'      # Telegram bot
    DISCORD = 'discord'        # Webhook Discord
    PUSH = 'push'              # Push browser
    SMS = 'sms'                # SMS (opzionale)
    APP = 'app'                # Notifica in-app
    WEBHOOK = 'webhook'        # Webhook generico HTTP

# Livelli di priorità
class NotificationPriority(Enum):
    LOW = 'low'
    NORMAL = 'normal'
    HIGH = 'high'
    URGENT = 'urgent'

@dataclass
class NotificationTemplate:
    """Template per le notifiche."""
    id: str
    type: NotificationType
    title: str
    body: str
    icon: Optional[str] = None
    image: Optional[str] = None
    action_url: Optional[str] = None
    variables: List[str] = field(default_factory=list)  # Variabili nel template
    
    def format(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Formatta il template con i dati specificati."""
        title = self.title
        body = self.body
        
        for var in self.variables:
            if var in data:
                placeholder = f"{{{var}}}"
                title = title.replace(placeholder, str(data[var]))
                body = body.replace(placeholder, str(data[var]))
        
        result = {
            "title": title,
            "body": body
        }
        
        if self.icon:
            result["icon"] = self.icon
        if self.image:
            result["image"] = self.image
        if self.action_url:
            # Formatta anche l'URL di azione se contiene variabili
            action_url = self.action_url
            for var in self.variables:
                if var in data:
                    placeholder = f"{{{var}}}"
                    action_url = action_url.replace(placeholder, str(data[var]))
            result["action_url"] = action_url
            
        return result

@dataclass
class NotificationPreference:
    """Preferenze di notifica di un utente."""
    user_id: str
    channels: Dict[NotificationType, List[NotificationChannel]] = field(default_factory=dict)
    enabled: bool = True
    quiet_hours_start: Optional[int] = None  # Ora in formato 24h (0-23)
    quiet_hours_end: Optional[int] = None
    telegram_chat_id: Optional[str] = None
    email: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    push_subscription: Optional[Dict[str, Any]] = None
    webhook_url: Optional[str] = None
    phone_number: Optional[str] = None

@dataclass
class Notification:
    """Rappresentazione di una notifica."""
    id: str
    type: NotificationType
    title: str
    body: str
    created_at: str
    priority: NotificationPriority = NotificationPriority.NORMAL
    icon: Optional[str] = None  # URL icona
    image: Optional[str] = None  # URL immagine
    action_url: Optional[str] = None  # URL di azione al click
    sender: Optional[str] = None  # ID/nome mittente
    recipients: List[str] = field(default_factory=list)  # Lista ID destinatari
    data: Dict[str, Any] = field(default_factory=dict)  # Dati aggiuntivi
    sent: bool = False
    sent_at: Optional[str] = None
    channels: List[NotificationChannel] = field(default_factory=list)  # Canali su cui è stata inviata

class NotificationService:
    """Servizio centrale per la gestione delle notifiche."""
    
    def __init__(self, db_pool=None, config: Dict[str, Any] = None):
        """Inizializza il servizio di notifiche.
        
        Args:
            db_pool: Pool di connessioni al database
            config: Configurazione del servizio
        """
        self.db_pool = db_pool
        self.config = config or {}
        self.templates: Dict[str, NotificationTemplate] = {}
        self.delivery_services: Dict[NotificationChannel, Any] = {}
        
        # Inizializza i servizi di consegna delle notifiche
        self._init_delivery_services()
        
        # Carica i template predefiniti
        self._load_default_templates()
        
        # Crea una sessione aiohttp per le richieste HTTP
        self.session = None
        
        logger.info("Servizio di notifiche inizializzato")
    
    async def start(self):
        """Avvia il servizio di notifiche."""
        self.session = aiohttp.ClientSession()
        logger.info("Servizio di notifiche avviato")
    
    async def stop(self):
        """Ferma il servizio di notifiche."""
        if self.session:
            await self.session.close()
            self.session = None
        logger.info("Servizio di notifiche fermato")
    
    def _init_delivery_services(self):
        """Inizializza i servizi di consegna delle notifiche."""
        # Email
        self.delivery_services[NotificationChannel.EMAIL] = EmailNotificationService(
            smtp_host=self.config.get('smtp_host', 'smtp.gmail.com'),
            smtp_port=self.config.get('smtp_port', 587),
            smtp_user=self.config.get('smtp_user', ''),
            smtp_password=self.config.get('smtp_password', ''),
            from_email=self.config.get('from_email', 'noreply@m4bot.it'),
            from_name=self.config.get('from_name', 'M4Bot')
        )
        
        # Telegram
        self.delivery_services[NotificationChannel.TELEGRAM] = TelegramNotificationService(
            bot_token=self.config.get('telegram_bot_token', '')
        )
        
        # Discord
        self.delivery_services[NotificationChannel.DISCORD] = DiscordNotificationService()
        
        # Push
        self.delivery_services[NotificationChannel.PUSH] = PushNotificationService(
            vapid_public_key=self.config.get('vapid_public_key', ''),
            vapid_private_key=self.config.get('vapid_private_key', ''),
            vapid_sub=self.config.get('vapid_sub', 'mailto:admin@m4bot.it')
        )
        
        # Altri servizi...
        
        logger.debug(f"Inizializzati {len(self.delivery_services)} servizi di consegna notifiche")
    
    def _load_default_templates(self):
        """Carica i template predefiniti per le notifiche."""
        # Template per inizio stream
        self.templates['stream_start'] = NotificationTemplate(
            id='stream_start',
            type=NotificationType.STREAM_START,
            title='🔴 {channel_name} è in diretta!',
            body='{channel_name} ha iniziato una diretta: "{title}". Clicca per guardare!',
            action_url='https://kick.com/{channel_name}',
            variables=['channel_name', 'title']
        )
        
        # Template per fine stream
        self.templates['stream_end'] = NotificationTemplate(
            id='stream_end',
            type=NotificationType.STREAM_END,
            title='⚫ Diretta di {channel_name} terminata',
            body='La diretta di {channel_name} è terminata. Durata: {duration}',
            variables=['channel_name', 'duration']
        )
        
        # Template per nuovo follower
        self.templates['new_follower'] = NotificationTemplate(
            id='new_follower',
            type=NotificationType.NEW_FOLLOWER,
            title='👋 Nuovo follower!',
            body='{follower_name} ha iniziato a seguirti!',
            variables=['follower_name']
        )
        
        # Template per nuova iscrizione
        self.templates['new_subscription'] = NotificationTemplate(
            id='new_subscription',
            type=NotificationType.NEW_SUBSCRIPTION,
            title='🎉 Nuova iscrizione!',
            body='{subscriber_name} si è iscritto al canale! (Tier {tier})',
            variables=['subscriber_name', 'tier']
        )
        
        # Template per donazione
        self.templates['donation'] = NotificationTemplate(
            id='donation',
            type=NotificationType.DONATION,
            title='💰 Nuova donazione!',
            body='{donor_name} ha donato {amount} {currency}!',
            variables=['donor_name', 'amount', 'currency']
        )
        
        # Template per avviso di sistema
        self.templates['system_alert'] = NotificationTemplate(
            id='system_alert',
            type=NotificationType.SYSTEM_ALERT,
            title='⚠️ Avviso di sistema',
            body='{message}',
            variables=['message', 'severity']
        )
        
        # Template per evento programmato
        self.templates['scheduled_event'] = NotificationTemplate(
            id='scheduled_event',
            type=NotificationType.SCHEDULED_EVENT,
            title='📅 Promemoria: {event_name}',
            body='Evento in programma: {event_name}\nData: {event_date}\nDescrizione: {event_description}',
            variables=['event_name', 'event_date', 'event_description']
        )
        
        logger.debug(f"Caricati {len(self.templates)} template di notifica predefiniti")
    
    async def add_template(self, template: NotificationTemplate) -> bool:
        """Aggiunge un nuovo template per le notifiche."""
        if not template.id:
            template.id = str(uuid.uuid4())
        
        self.templates[template.id] = template
        
        # Salva il template nel database
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO notification_templates (id, type, title, body, icon, image, action_url, variables)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (id) DO UPDATE SET
                        type = $2,
                        title = $3,
                        body = $4,
                        icon = $5,
                        image = $6,
                        action_url = $7,
                        variables = $8
                    """,
                    template.id,
                    template.type.value,
                    template.title,
                    template.body,
                    template.icon,
                    template.image,
                    template.action_url,
                    json.dumps(template.variables)
                )
        
        return True
    
    async def get_template(self, template_id: str) -> Optional[NotificationTemplate]:
        """Ottiene un template per ID."""
        if template_id in self.templates:
            return self.templates[template_id]
        
        # Cerca nel database
        if self.db_pool:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM notification_templates WHERE id = $1",
                    template_id
                )
                
                if row:
                    template = NotificationTemplate(
                        id=row['id'],
                        type=NotificationType(row['type']),
                        title=row['title'],
                        body=row['body'],
                        icon=row['icon'],
                        image=row['image'],
                        action_url=row['action_url'],
                        variables=json.loads(row['variables'])
                    )
                    
                    # Aggiungilo alla cache
                    self.templates[template.id] = template
                    
                    return template
        
        return None
    
    async def get_user_preferences(self, user_id: str) -> NotificationPreference:
        """Ottiene le preferenze di notifica dell'utente."""
        if not self.db_pool:
            # Preferenze predefinite
            return NotificationPreference(user_id=user_id)
        
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM notification_preferences WHERE user_id = $1",
                user_id
            )
            
            if not row:
                # Nessuna preferenza trovata, crea quelle predefinite
                return NotificationPreference(user_id=user_id)
            
            # Canali preferiti per tipo di notifica
            channels = {}
            for type_name, type_value in NotificationType.__members__.items():
                channels_col = f"channels_{type_name.lower()}"
                if channels_col in row and row[channels_col]:
                    channels[type_value] = [
                        NotificationChannel(ch) for ch in row[channels_col].split(',')
                    ]
            
            # Costruisci l'oggetto preferenze
            return NotificationPreference(
                user_id=user_id,
                channels=channels,
                enabled=row['enabled'],
                quiet_hours_start=row['quiet_hours_start'],
                quiet_hours_end=row['quiet_hours_end'],
                telegram_chat_id=row['telegram_chat_id'],
                email=row['email'],
                discord_webhook_url=row.get('discord_webhook_url'),
                push_subscription=json.loads(row['push_subscription']) if row['push_subscription'] else None,
                webhook_url=row.get('webhook_url'),
                phone_number=row.get('phone_number')
            )
    
    async def update_user_preferences(self, preferences: NotificationPreference) -> bool:
        """Aggiorna le preferenze di notifica dell'utente."""
        if not self.db_pool:
            logger.warning("Impossibile aggiornare preferenze: nessuna connessione al database")
            return False
        
        async with self.db_pool.acquire() as conn:
            # Prepara i dati per l'aggiornamento
            update_data = {
                "user_id": preferences.user_id,
                "enabled": preferences.enabled,
                "quiet_hours_start": preferences.quiet_hours_start,
                "quiet_hours_end": preferences.quiet_hours_end,
                "telegram_chat_id": preferences.telegram_chat_id,
                "email": preferences.email,
                "discord_webhook_url": preferences.discord_webhook_url,
                "push_subscription": json.dumps(preferences.push_subscription) if preferences.push_subscription else None,
                "webhook_url": preferences.webhook_url,
                "phone_number": preferences.phone_number
            }
            
            # Aggiungi i canali per ogni tipo di notifica
            for type_name, type_value in NotificationType.__members__.items():
                if type_value in preferences.channels:
                    channels_str = ','.join([ch.value for ch in preferences.channels[type_value]])
                    update_data[f"channels_{type_name.lower()}"] = channels_str
                else:
                    update_data[f"channels_{type_name.lower()}"] = None
            
            # Costruisci query dinamica
            columns = list(update_data.keys())
            values = list(update_data.values())
            placeholders = [f"${i+1}" for i in range(len(values))]
            
            # Query per INSERT o UPDATE
            query = f"""
                INSERT INTO notification_preferences ({', '.join(columns)})
                VALUES ({', '.join(placeholders)})
                ON CONFLICT (user_id) DO UPDATE SET
                {', '.join([f"{col} = excluded.{col}" for col in columns if col != 'user_id'])}
            """
            
            await conn.execute(query, *values)
            return True
    
    async def send_notification(self, 
                               type_or_template_id: Union[NotificationType, str],
                               recipients: List[str], 
                               data: Dict[str, Any] = None,
                               priority: NotificationPriority = NotificationPriority.NORMAL,
                               channels: List[NotificationChannel] = None) -> str:
        """Invia una notifica a uno o più utenti.
        
        Args:
            type_or_template_id: Tipo di notifica o ID del template
            recipients: Lista di ID utenti destinatari
            data: Dati per il template
            priority: Priorità della notifica
            channels: Canali specifici da utilizzare (opzionale)
            
        Returns:
            ID della notifica inviata
        """
        data = data or {}
        
        # Determina il tipo e il template
        notification_type = None
        template = None
        
        if isinstance(type_or_template_id, NotificationType):
            notification_type = type_or_template_id
            template_id = notification_type.value
            template = await self.get_template(template_id)
        else:
            template = await self.get_template(type_or_template_id)
            if template:
                notification_type = template.type
        
        if not template:
            logger.error(f"Template non trovato: {type_or_template_id}")
            raise ValueError(f"Template non trovato: {type_or_template_id}")
        
        # Formatta il template con i dati
        formatted = template.format(data)
        
        # Crea la notifica
        notification_id = str(uuid.uuid4())
        notification = Notification(
            id=notification_id,
            type=notification_type,
            title=formatted["title"],
            body=formatted["body"],
            created_at=datetime.now().isoformat(),
            priority=priority,
            icon=formatted.get("icon"),
            image=formatted.get("image"),
            action_url=formatted.get("action_url"),
            sender="system",
            recipients=recipients,
            data=data
        )
        
        # Avvia il processo di invio in background
        asyncio.create_task(self._process_notification(notification, channels))
        
        return notification_id
    
    async def _process_notification(self, notification: Notification, 
                                  specified_channels: List[NotificationChannel] = None) -> bool:
        """Processa e invia la notifica attraverso i canali appropriati."""
        try:
            # Salva la notifica nel database
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO notifications 
                        (id, type, title, body, created_at, priority, icon, image, action_url, 
                        sender, recipients, data)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        """,
                        notification.id,
                        notification.type.value,
                        notification.title,
                        notification.body,
                        notification.created_at,
                        notification.priority.value,
                        notification.icon,
                        notification.image,
                        notification.action_url,
                        notification.sender,
                        json.dumps(notification.recipients),
                        json.dumps(notification.data)
                    )
            
            # Processa ogni destinatario
            for recipient_id in notification.recipients:
                # Ottieni le preferenze dell'utente
                preferences = await self.get_user_preferences(recipient_id)
                
                # Verifica se le notifiche sono abilitate
                if not preferences.enabled:
                    logger.debug(f"Notifiche disabilitate per l'utente {recipient_id}")
                    continue
                
                # Verifica quiet hours
                if preferences.quiet_hours_start is not None and preferences.quiet_hours_end is not None:
                    current_hour = datetime.now().hour
                    if preferences.quiet_hours_start <= current_hour < preferences.quiet_hours_end:
                        logger.debug(f"Notifica non inviata durante quiet hours per l'utente {recipient_id}")
                        continue
                
                # Determina i canali da utilizzare
                channels_to_use = []
                
                if specified_channels:
                    # Usa i canali specificati, se disponibili
                    channels_to_use = specified_channels
                elif notification.type in preferences.channels:
                    # Usa i canali preferiti per questo tipo di notifica
                    channels_to_use = preferences.channels[notification.type]
                else:
                    # Canali predefiniti in base alla priorità
                    if notification.priority == NotificationPriority.LOW:
                        channels_to_use = [NotificationChannel.APP]
                    elif notification.priority == NotificationPriority.NORMAL:
                        channels_to_use = [NotificationChannel.APP, NotificationChannel.PUSH]
                    elif notification.priority == NotificationPriority.HIGH:
                        channels_to_use = [NotificationChannel.APP, NotificationChannel.PUSH, NotificationChannel.EMAIL]
                    elif notification.priority == NotificationPriority.URGENT:
                        channels_to_use = [NotificationChannel.APP, NotificationChannel.PUSH, 
                                         NotificationChannel.EMAIL, NotificationChannel.TELEGRAM]
                
                # Invia la notifica sui canali selezionati
                for channel in channels_to_use:
                    if channel in self.delivery_services:
                        delivery_service = self.delivery_services[channel]
                        try:
                            # Determina l'indirizzo in base al canale
                            address = None
                            if channel == NotificationChannel.EMAIL and preferences.email:
                                address = preferences.email
                            elif channel == NotificationChannel.TELEGRAM and preferences.telegram_chat_id:
                                address = preferences.telegram_chat_id
                            elif channel == NotificationChannel.DISCORD and preferences.discord_webhook_url:
                                address = preferences.discord_webhook_url
                            elif channel == NotificationChannel.PUSH and preferences.push_subscription:
                                address = preferences.push_subscription
                            elif channel == NotificationChannel.WEBHOOK and preferences.webhook_url:
                                address = preferences.webhook_url
                            elif channel == NotificationChannel.SMS and preferences.phone_number:
                                address = preferences.phone_number
                            
                            if address:
                                success = await delivery_service.send(notification, recipient_id, address)
                                if success:
                                    # Aggiungi il canale alla lista dei canali su cui è stata inviata
                                    notification.channels.append(channel)
                                    logger.debug(f"Notifica inviata a {recipient_id} via {channel.value}")
                            else:
                                logger.debug(f"Indirizzo mancante per il canale {channel.value} dell'utente {recipient_id}")
                        except Exception as e:
                            logger.error(f"Errore nell'invio della notifica a {recipient_id} via {channel.value}: {e}")
                    else:
                        logger.warning(f"Servizio di consegna non disponibile per il canale {channel.value}")
            
            # Aggiorna la notifica come inviata
            notification.sent = True
            notification.sent_at = datetime.now().isoformat()
            
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    channels_json = json.dumps([ch.value for ch in notification.channels])
                    await conn.execute(
                        """
                        UPDATE notifications 
                        SET sent = true, sent_at = $1, channels = $2
                        WHERE id = $3
                        """,
                        notification.sent_at,
                        channels_json,
                        notification.id
                    )
            
            return True
            
        except Exception as e:
            logger.error(f"Errore nel processamento della notifica {notification.id}: {e}")
            return False
    
    async def get_user_notifications(self, user_id: str, limit: int = 50, 
                                   offset: int = 0, include_read: bool = False) -> List[Notification]:
        """Ottiene le notifiche per un utente specifico."""
        if not self.db_pool:
            return []
        
        async with self.db_pool.acquire() as conn:
            # Costruisci la query
            query = """
                SELECT * FROM notifications 
                WHERE $1 = ANY(recipients)
            """
            
            if not include_read:
                query += " AND NOT $1 = ANY(read_by)"
            
            query += " ORDER BY created_at DESC LIMIT $2 OFFSET $3"
            
            rows = await conn.fetch(query, user_id, limit, offset)
            
            notifications = []
            for row in rows:
                notification = Notification(
                    id=row['id'],
                    type=NotificationType(row['type']),
                    title=row['title'],
                    body=row['body'],
                    created_at=row['created_at'].isoformat() if isinstance(row['created_at'], datetime) else row['created_at'],
                    priority=NotificationPriority(row['priority']),
                    icon=row['icon'],
                    image=row['image'],
                    action_url=row['action_url'],
                    sender=row['sender'],
                    recipients=json.loads(row['recipients']),
                    data=json.loads(row['data']),
                    sent=row['sent'],
                    sent_at=row['sent_at'].isoformat() if row['sent_at'] else None,
                    channels=[NotificationChannel(ch) for ch in json.loads(row['channels'])] if row['channels'] else []
                )
                notifications.append(notification)
            
            return notifications
    
    async def mark_notification_read(self, notification_id: str, user_id: str) -> bool:
        """Segna una notifica come letta per un utente."""
        if not self.db_pool:
            return False
        
        async with self.db_pool.acquire() as conn:
            # Verifica che la notifica esista
            notification = await conn.fetchrow(
                "SELECT * FROM notifications WHERE id = $1 AND $2 = ANY(recipients)",
                notification_id, user_id
            )
            
            if not notification:
                return False
            
            # Aggiorna il campo read_by
            read_by = notification['read_by'] or []
            if user_id not in read_by:
                read_by.append(user_id)
                
                await conn.execute(
                    "UPDATE notifications SET read_by = $1 WHERE id = $2",
                    read_by, notification_id
                )
            
            return True

# Servizi di consegna delle notifiche

class EmailNotificationService:
    """Servizio per invio notifiche via email."""
    
    def __init__(self, smtp_host: str, smtp_port: int, smtp_user: str, 
                smtp_password: str, from_email: str, from_name: str):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.smtp_user = smtp_user
        self.smtp_password = smtp_password
        self.from_email = from_email
        self.from_name = from_name
        
        # Decripta la password se necessario
        if self.smtp_password and hasattr(CryptoManager, 'decrypt'):
            try:
                self.smtp_password = CryptoManager.decrypt(self.smtp_password, 'email_service')
            except Exception as e:
                logger.error(f"Errore nella decrittografia della password SMTP: {e}")
    
    async def send(self, notification: Notification, recipient_id: str, email_address: str) -> bool:
        """Invia una notifica via email."""
        try:
            # Crea il messaggio
            msg = MIMEMultipart('alternative')
            msg['Subject'] = notification.title
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = email_address
            
            # Corpo testo semplice
            text_body = notification.body
            msg.attach(MIMEText(text_body, 'plain'))
            
            # Corpo HTML
            html_body = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
                    .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                    .header {{ background-color: #4a86e8; color: white; padding: 10px 20px; text-align: center; }}
                    .content {{ padding: 20px; background-color: #f7f7f7; }}
                    .footer {{ font-size: 12px; color: #777; text-align: center; margin-top: 20px; }}
                    .button {{ display: inline-block; background-color: #4a86e8; color: white; padding: 10px 20px; 
                              text-decoration: none; border-radius: 4px; margin-top: 15px; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>{notification.title}</h1>
                    </div>
                    <div class="content">
                        <p>{notification.body.replace('\n', '<br>')}</p>
                        
                        {f'<img src="{notification.image}" style="max-width: 100%; margin: 15px 0;" />' if notification.image else ''}
                        
                        {f'<p><a href="{notification.action_url}" class="button">Apri</a></p>' if notification.action_url else ''}
                    </div>
                    <div class="footer">
                        <p>Questa notifica ti è stata inviata da M4Bot. Per gestire le tue preferenze di notifica, 
                        visita le impostazioni del tuo account.</p>
                    </div>
                </div>
            </body>
            </html>
            """
            msg.attach(MIMEText(html_body, 'html'))
            
            # Invia l'email
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_email, msg, email_address)
            
            return True
        except Exception as e:
            logger.error(f"Errore nell'invio dell'email a {email_address}: {e}")
            return False
    
    def _send_email(self, msg, email_address):
        """Funzione di supporto per inviare email (eseguita in un thread separato)."""
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)

class TelegramNotificationService:
    """Servizio per invio notifiche via Telegram."""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.api_url = f"https://api.telegram.org/bot{bot_token}"
        self.session = None
        
        # Decripta il token se necessario
        if self.bot_token and hasattr(CryptoManager, 'decrypt'):
            try:
                self.bot_token = CryptoManager.decrypt(self.bot_token, 'telegram_service')
                self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
            except Exception as e:
                logger.error(f"Errore nella decrittografia del token Telegram: {e}")
    
    async def send(self, notification: Notification, recipient_id: str, chat_id: str) -> bool:
        """Invia una notifica via Telegram."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Prepara i dati del messaggio
            message_text = f"*{notification.title}*\n\n{notification.body}"
            
            # Aggiungi pulsante se c'è un URL di azione
            keyboard = None
            if notification.action_url:
                keyboard = {
                    "inline_keyboard": [
                        [
                            {
                                "text": "Apri",
                                "url": notification.action_url
                            }
                        ]
                    ]
                }
            
            # Parametri della richiesta
            params = {
                "chat_id": chat_id,
                "text": message_text,
                "parse_mode": "Markdown"
            }
            
            if keyboard:
                params["reply_markup"] = json.dumps(keyboard)
            
            # Prima prova a inviare un messaggio di testo
            async with self.session.post(f"{self.api_url}/sendMessage", json=params) as response:
                if response.status == 200:
                    return True
                
                # Se c'è un'immagine, prova a inviarla
                if notification.image and response.status != 200:
                    image_params = {
                        "chat_id": chat_id,
                        "photo": notification.image,
                        "caption": message_text,
                        "parse_mode": "Markdown"
                    }
                    
                    if keyboard:
                        image_params["reply_markup"] = json.dumps(keyboard)
                    
                    async with self.session.post(f"{self.api_url}/sendPhoto", json=image_params) as img_response:
                        return img_response.status == 200
                
                return False
        except Exception as e:
            logger.error(f"Errore nell'invio del messaggio Telegram a {chat_id}: {e}")
            return False

class DiscordNotificationService:
    """Servizio per invio notifiche via Discord."""
    
    def __init__(self):
        self.session = None
    
    async def send(self, notification: Notification, recipient_id: str, webhook_url: str) -> bool:
        """Invia una notifica via webhook Discord."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()
            
            # Crea l'embed
            embed = {
                "title": notification.title,
                "description": notification.body,
                "color": self._get_color_for_priority(notification.priority),
                "timestamp": notification.created_at
            }
            
            # Aggiungi immagine se presente
            if notification.image:
                embed["image"] = {"url": notification.image}
            
            # Aggiungi icona se presente
            if notification.icon:
                embed["thumbnail"] = {"url": notification.icon}
            
            # Aggiungi pulsante/URL se presente
            if notification.action_url:
                embed["url"] = notification.action_url
            
            # Contenuto del messaggio
            payload = {
                "embeds": [embed],
                "username": "M4Bot Notifications"
            }
            
            # Invia la notifica
            async with self.session.post(webhook_url, json=payload) as response:
                return response.status >= 200 and response.status < 300
                
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica Discord: {e}")
            return False
    
    def _get_color_for_priority(self, priority: NotificationPriority) -> int:
        """Restituisce il colore dell'embed in base alla priorità."""
        if priority == NotificationPriority.LOW:
            return 0x7289da  # Blu
        elif priority == NotificationPriority.NORMAL:
            return 0x43b581  # Verde
        elif priority == NotificationPriority.HIGH:
            return 0xfaa61a  # Arancione
        elif priority == NotificationPriority.URGENT:
            return 0xf04747  # Rosso
        return 0x7289da  # Default blu

class PushNotificationService:
    """Servizio per invio notifiche push web."""
    
    def __init__(self, vapid_public_key: str = None, vapid_private_key: str = None, vapid_sub: str = None):
        self.vapid_public_key = vapid_public_key
        self.vapid_private_key = vapid_private_key
        self.vapid_sub = vapid_sub
        self.webpush = None
        
        # Importa pywebpush solo quando necessario
        try:
            from pywebpush import webpush
            self.webpush = webpush
        except ImportError:
            logger.warning("pywebpush non installato. Notifiche push disabilitate.")
    
    async def send(self, notification: Notification, recipient_id: str, subscription_info: Dict[str, Any]) -> bool:
        """Invia una notifica push web."""
        if not self.webpush:
            logger.error("Servizio push non disponibile: libreria pywebpush mancante")
            return False
        
        try:
            # Prepara i dati della notifica
            data = {
                "title": notification.title,
                "body": notification.body,
                "icon": notification.icon,
                "image": notification.image,
                "timestamp": notification.created_at,
                "tag": f"m4bot-{notification.id}",
                "data": {
                    "url": notification.action_url
                }
            }
            
            # Invia la notifica push
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._send_push, subscription_info, data)
            
            return True
        except Exception as e:
            logger.error(f"Errore nell'invio della notifica push: {e}")
            return False
    
    def _send_push(self, subscription_info, data):
        """Funzione di supporto per inviare notifiche push (eseguita in un thread separato)."""
        self.webpush(
            subscription_info=subscription_info,
            data=json.dumps(data),
            vapid_private_key=self.vapid_private_key,
            vapid_claims={
                "sub": self.vapid_sub,
                "exp": int(time.time()) + 86400  # 24 ore
            }
        )

# Funzione di inizializzazione per il sistema di notifiche
async def init_notification_service(app=None, db_pool=None, config=None):
    """Inizializza e restituisce il servizio di notifiche."""
    logger.info("Inizializzazione del servizio di notifiche...")
    
    # Crea il servizio
    notification_service = NotificationService(db_pool, config)
    await notification_service.start()
    
    # Aggiungi il servizio all'app se fornita
    if app:
        app.notification_service = notification_service
        logger.info("Servizio di notifiche registrato nell'app")
    
    return notification_service

# Esempio di uso
if __name__ == "__main__":
    async def main():
        # Configura il logger
        logging.basicConfig(level=logging.INFO)
        
        # Configurazione di esempio
        config = {
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_user": "your-email@gmail.com",
            "smtp_password": "your-app-password",
            "from_email": "notifications@m4bot.it",
            "from_name": "M4Bot Notifications",
            "telegram_bot_token": "your-telegram-bot-token"
        }
        
        # Inizializza il servizio
        notification_service = await init_notification_service(config=config)
        
        # Esempio di invio notifica
        notification_id = await notification_service.send_notification(
            NotificationType.STREAM_START,
            ["user1", "user2"],
            {
                "channel_name": "M4CodeBot",
                "title": "Sessione di coding in live!"
            },
            NotificationPriority.HIGH
        )
        
        print(f"Notifica inviata con ID: {notification_id}")
        
        # Aspetta che le notifiche vengano inviate
        await asyncio.sleep(5)
        
        # Ferma il servizio
        await notification_service.stop()
    
    # Esegui l'esempio
    asyncio.run(main()) 