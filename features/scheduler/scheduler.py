#!/usr/bin/env python3
"""
Classe principale del sistema di pianificazione per M4Bot.

Questo modulo gestisce la creazione, aggiornamento ed esecuzione di eventi pianificati
come stream, post social, promemoria e automazioni.
"""

import os
import sys
import json
import asyncio
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Union, Tuple
from dataclasses import asdict

# Importazioni locali
from .models import ScheduledEvent, EventType, EventStatus, RecurrencePattern, EventReminder

# Logger
logger = logging.getLogger('m4bot.scheduler')

class ContentScheduler:
    """
    Classe principale che gestisce il sistema di pianificazione.
    """
    
    def __init__(self, db_pool=None, config: Dict[str, Any] = None, notification_service=None):
        """
        Inizializza lo scheduler.
        
        Args:
            db_pool: Pool di connessioni al database
            config: Configurazione personalizzata
            notification_service: Servizio di notifiche per i promemoria
        """
        self.db_pool = db_pool
        self.config = config or {}
        self.notification_service = notification_service
        
        # Eventi pianificati da verificare (eventi non ancora iniziati)
        # event_id -> ScheduledEvent
        self.pending_events: Dict[str, ScheduledEvent] = {}
        
        # Eventi attivi (eventi in corso)
        # event_id -> ScheduledEvent
        self.active_events: Dict[str, ScheduledEvent] = {}
        
        # Promemoria da inviare
        # (event_id, reminder_id) -> EventReminder
        self.pending_reminders: Dict[Tuple[str, str], EventReminder] = {}
        
        # Task in background per il monitoraggio degli eventi
        self.background_tasks = set()
        self.running = False
        
        # Intervallo di controllo per gli eventi (secondi)
        self.check_interval = self.config.get('scheduler_check_interval', 15)
        
        # Callback per tipi di eventi specifici
        # event_type -> callable
        self.event_handlers: Dict[EventType, callable] = {}
        
        logger.info("Scheduler di contenuti inizializzato")
    
    async def initialize(self):
        """Inizializza lo scheduler."""
        # Carica gli eventi e i promemoria pendenti dal database
        await self._load_pending_events()
        await self._load_pending_reminders()
        
        # Avvia il task di controllo periodico
        self.running = True
        task = asyncio.create_task(self._periodic_check())
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
        
        logger.info(f"Scheduler avviato con {len(self.pending_events)} eventi pendenti")
    
    async def shutdown(self):
        """Spegni lo scheduler in modo sicuro."""
        self.running = False
        
        # Attendi che tutti i task in background terminino
        if self.background_tasks:
            logger.info(f"In attesa che {len(self.background_tasks)} task terminino...")
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        logger.info("Scheduler spento correttamente")
    
    def register_handler(self, event_type: EventType, handler: callable):
        """
        Registra un handler per un tipo di evento specifico.
        
        Args:
            event_type: Tipo di evento
            handler: Funzione da chiamare quando l'evento viene eseguito
        """
        self.event_handlers[event_type] = handler
        logger.info(f"Handler registrato per eventi di tipo {event_type.value}")
    
    async def _load_pending_events(self):
        """Carica gli eventi pendenti dal database."""
        if not self.db_pool:
            logger.warning("Nessun pool di database fornito, impossibile caricare eventi")
            return
        
        try:
            async with self.db_pool.acquire() as conn:
                # Ottieni gli eventi non ancora iniziati o in corso
                rows = await conn.fetch(
                    """
                    SELECT * FROM scheduled_events
                    WHERE status IN ('pending', 'active') AND start_time > $1
                    ORDER BY start_time
                    """,
                    time.time() - 3600  # Include eventi iniziati nell'ultima ora
                )
                
                for row in rows:
                    # Converti la riga in dizionario
                    event_data = dict(row)
                    
                    # Converti JSON in dizionario per i campi complessi
                    if 'metadata' in event_data and event_data['metadata']:
                        event_data['metadata'] = json.loads(event_data['metadata'])
                    else:
                        event_data['metadata'] = {}
                    
                    if 'reminders' in event_data and event_data['reminders']:
                        event_data['reminders'] = json.loads(event_data['reminders'])
                    else:
                        event_data['reminders'] = []
                    
                    if 'recurrence' in event_data and event_data['recurrence']:
                        event_data['recurrence'] = json.loads(event_data['recurrence'])
                    
                    # Crea l'oggetto evento
                    event = ScheduledEvent(
                        id=event_data['id'],
                        channel_id=event_data['channel_id'],
                        title=event_data['title'],
                        type=EventType(event_data['type']),
                        status=EventStatus(event_data['status']),
                        start_time=event_data['start_time'],
                        end_time=event_data.get('end_time'),
                        created_by=event_data['created_by'],
                        created_at=event_data['created_at'],
                        description=event_data.get('description', ''),
                        location=event_data.get('location'),
                        color=event_data.get('color'),
                        metadata=event_data['metadata'],
                        reminders=event_data['reminders'],
                        recurrence=event_data['recurrence'],
                        last_updated=event_data.get('last_updated'),
                        external_id=event_data.get('external_id')
                    )
                    
                    # Aggiungi all'elenco appropriato
                    if event.status == EventStatus.PENDING:
                        self.pending_events[event.id] = event
                    elif event.status == EventStatus.ACTIVE:
                        self.active_events[event.id] = event
                
                logger.info(f"Caricati {len(self.pending_events)} eventi pendenti e {len(self.active_events)} eventi attivi")
        
        except Exception as e:
            logger.error(f"Errore nel caricamento degli eventi pendenti: {e}")
    
    async def _load_pending_reminders(self):
        """Carica i promemoria pendenti dal database."""
        if not self.db_pool:
            logger.warning("Nessun pool di database fornito, impossibile caricare promemoria")
            return
        
        try:
            async with self.db_pool.acquire() as conn:
                # Ottieni i promemoria non ancora inviati
                rows = await conn.fetch(
                    """
                    SELECT * FROM event_reminders
                    WHERE sent = false
                    ORDER BY event_id, time_before DESC
                    """
                )
                
                for row in rows:
                    reminder_data = dict(row)
                    
                    # Converti JSON in liste per i destinatari
                    if 'recipients' in reminder_data and reminder_data['recipients']:
                        recipients = json.loads(reminder_data['recipients'])
                    else:
                        recipients = []
                    
                    # Crea l'oggetto promemoria
                    reminder = EventReminder(
                        id=reminder_data['id'],
                        event_id=reminder_data['event_id'],
                        time_before=reminder_data['time_before'],
                        type=reminder_data['type'],
                        recipients=recipients,
                        message=reminder_data.get('message'),
                        sent=reminder_data['sent'],
                        sent_at=reminder_data.get('sent_at')
                    )
                    
                    # Aggiungi alla lista dei promemoria pendenti
                    self.pending_reminders[(reminder.event_id, reminder.id)] = reminder
                
                logger.info(f"Caricati {len(self.pending_reminders)} promemoria pendenti")
        
        except Exception as e:
            logger.error(f"Errore nel caricamento dei promemoria pendenti: {e}")
    
    async def _periodic_check(self):
        """Task periodico per controllare gli eventi pianificati."""
        logger.info("Avviato task periodico per controllo eventi")
        
        while self.running:
            try:
                # Verifica eventi da avviare
                await self._check_events_to_start()
                
                # Verifica eventi da completare
                await self._check_events_to_complete()
                
                # Verifica promemoria da inviare
                await self._check_reminders_to_send()
                
                # Genera eventi ricorrenti se necessario
                await self._generate_recurring_events()
                
                # Attendi il prossimo ciclo
                await asyncio.sleep(self.check_interval)
            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Errore nel controllo periodico degli eventi: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_events_to_start(self):
        """Controlla se ci sono eventi da avviare."""
        current_time = time.time()
        events_to_start = []
        
        # Cerca eventi da avviare
        for event_id, event in list(self.pending_events.items()):
            if event.start_time <= current_time:
                events_to_start.append(event)
        
        # Avvia gli eventi
        for event in events_to_start:
            await self.start_event(event.id)
    
    async def _check_events_to_complete(self):
        """Controlla se ci sono eventi da completare."""
        current_time = time.time()
        events_to_complete = []
        
        # Cerca eventi da completare
        for event_id, event in list(self.active_events.items()):
            if event.end_time and event.end_time <= current_time:
                events_to_complete.append(event)
        
        # Completa gli eventi
        for event in events_to_complete:
            await self.complete_event(event.id)
    
    async def _check_reminders_to_send(self):
        """Controlla se ci sono promemoria da inviare."""
        current_time = time.time()
        reminders_to_send = []
        
        # Cerca promemoria da inviare
        for (event_id, reminder_id), reminder in list(self.pending_reminders.items()):
            # Ottieni l'evento associato
            event = self.pending_events.get(event_id) or self.active_events.get(event_id)
            
            if not event:
                # Evento non trovato, rimuovi il promemoria
                logger.warning(f"Promemoria {reminder_id} associato a un evento non trovato: {event_id}")
                self.pending_reminders.pop((event_id, reminder_id), None)
                continue
            
            # Calcola quando il promemoria deve essere inviato
            reminder_time = event.start_time - reminder.time_before
            
            if reminder_time <= current_time:
                reminders_to_send.append((event, reminder))
        
        # Invia i promemoria
        for event, reminder in reminders_to_send:
            await self._send_reminder(event, reminder)
    
    async def _generate_recurring_events(self):
        """Genera nuove istanze di eventi ricorrenti."""
        current_time = time.time()
        
        # Cerca eventi ricorrenti
        for event_id, event in list(self.pending_events.items()):
            if not event.is_recurring():
                continue
            
            # Verifica se è necessario generare nuove istanze
            recurrence = event.recurrence
            if not recurrence:
                continue
            
            # Ottieni il pattern di ricorrenza
            pattern_type = recurrence.get('pattern')
            if not pattern_type:
                continue
            
            try:
                pattern = RecurrencePattern(pattern_type)
            except ValueError:
                logger.warning(f"Pattern di ricorrenza non valido per evento {event_id}: {pattern_type}")
                continue
            
            # Verifica se abbiamo già generato tutte le istanze necessarie
            max_instances = recurrence.get('max_instances')
            if max_instances:
                # Conta le istanze già generate
                if self.db_pool:
                    async with self.db_pool.acquire() as conn:
                        count = await conn.fetchval(
                            """
                            SELECT COUNT(*) FROM recurring_event_instances
                            WHERE parent_event_id = $1
                            """,
                            event_id
                        )
                        
                        if count >= max_instances:
                            # Già generate tutte le istanze richieste
                            continue
            
            # Controlla la data di fine della ricorrenza
            until = recurrence.get('until')
            if until and until < current_time:
                # La ricorrenza è terminata
                continue
            
            # Calcola quando dovrebbe avvenire la prossima istanza
            next_start = self._calculate_next_instance(event, current_time)
            
            if next_start and next_start - current_time <= 86400 * 7:  # Genera istanze per la prossima settimana
                # Genera una nuova istanza
                await self._create_recurring_instance(event, next_start)
        
    def _calculate_next_instance(self, event: ScheduledEvent, after_time: float) -> Optional[float]:
        """
        Calcola quando dovrebbe verificarsi la prossima istanza di un evento ricorrente.
        
        Args:
            event: Evento ricorrente
            after_time: Timestamp dopo cui calcolare la prossima istanza
            
        Returns:
            float: Timestamp della prossima istanza o None se non ci sono più istanze
        """
        if not event.is_recurring() or not event.recurrence:
            return None
        
        recurrence = event.recurrence
        pattern_type = recurrence.get('pattern')
        
        try:
            pattern = RecurrencePattern(pattern_type)
        except ValueError:
            logger.warning(f"Pattern di ricorrenza non valido: {pattern_type}")
            return None
        
        # Ottieni la data di riferimento
        reference_time = event.start_time
        
        # Calcola la prossima istanza in base al pattern
        if pattern == RecurrencePattern.DAILY:
            # Calcola quanti giorni sono passati
            days_passed = (after_time - reference_time) / 86400
            days_to_add = int(days_passed) + 1
            
            # Calcola il nuovo timestamp
            next_time = reference_time + (days_to_add * 86400)
            return next_time
            
        elif pattern == RecurrencePattern.WEEKLY:
            # Calcola quante settimane sono passate
            weeks_passed = (after_time - reference_time) / (86400 * 7)
            weeks_to_add = int(weeks_passed) + 1
            
            # Calcola il nuovo timestamp
            next_time = reference_time + (weeks_to_add * 86400 * 7)
            return next_time
            
        elif pattern == RecurrencePattern.MONTHLY:
            # Questo è più complesso e richiederebbe una libreria di date
            # Per semplicità, approssimiamo a 30 giorni
            months_passed = (after_time - reference_time) / (86400 * 30)
            months_to_add = int(months_passed) + 1
            
            # Calcola il nuovo timestamp
            next_time = reference_time + (months_to_add * 86400 * 30)
            return next_time
            
        elif pattern == RecurrencePattern.CUSTOM:
            # Per implementare un pattern personalizzato (cron)
            # sarebbe necessaria una libreria esterna
            logger.warning("Pattern di ricorrenza personalizzato non supportato")
            return None
        
        return None
    
    async def _create_recurring_instance(self, parent_event: ScheduledEvent, start_time: float) -> Optional[str]:
        """
        Crea una nuova istanza di un evento ricorrente.
        
        Args:
            parent_event: Evento padre ricorrente
            start_time: Timestamp di inizio della nuova istanza
            
        Returns:
            str: ID della nuova istanza creata o None in caso di errore
        """
        if not self.db_pool:
            return None
        
        try:
            # Calcola la durata dell'evento originale
            duration = 0
            if parent_event.end_time:
                duration = parent_event.end_time - parent_event.start_time
            
            # Calcola il timestamp di fine
            end_time = None
            if duration > 0:
                end_time = start_time + duration
            
            # Crea ID univoco
            instance_id = str(uuid.uuid4())
            
            # Registra l'istanza nel database
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO recurring_event_instances
                    (id, parent_event_id, start_time, end_time, status, created_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    instance_id, parent_event.id, start_time, end_time,
                    EventStatus.PENDING.value, time.time()
                )
            
            logger.info(f"Creata nuova istanza {instance_id} dell'evento ricorrente {parent_event.id}")
            
            # Crea anche un evento regolare basato su questa istanza
            event_data = {
                'title': parent_event.title,
                'description': parent_event.description,
                'start_time': start_time,
                'end_time': end_time,
                'type': parent_event.type.value,
                'metadata': parent_event.metadata,
                'location': parent_event.location,
                'color': parent_event.color,
                'reminders': parent_event.reminders,
                'recurring_instance_id': instance_id
            }
            
            await self.create_event(parent_event.channel_id, event_data)
            
            return instance_id
        
        except Exception as e:
            logger.error(f"Errore nella creazione dell'istanza ricorrente: {e}")
            return None
    
    async def _send_reminder(self, event: ScheduledEvent, reminder: EventReminder):
        """
        Invia un promemoria per un evento.
        
        Args:
            event: Evento associato al promemoria
            reminder: Promemoria da inviare
        """
        if not self.notification_service:
            logger.warning("Nessun servizio di notifica disponibile per inviare il promemoria")
            
            # Anche senza servizio di notifica, segna come inviato
            reminder.sent = True
            reminder.sent_at = time.time()
            self.pending_reminders.pop((event.id, reminder.id), None)
            
            # Aggiorna nel database
            if self.db_pool:
                try:
                    async with self.db_pool.acquire() as conn:
                        await conn.execute(
                            """
                            UPDATE event_reminders
                            SET sent = true, sent_at = $1
                            WHERE id = $2
                            """,
                            reminder.sent_at, reminder.id
                        )
                except Exception as e:
                    logger.error(f"Errore nell'aggiornamento dello stato del promemoria: {e}")
            
            return
        
        try:
            # Prepara il messaggio
            message = reminder.message or f"Promemoria: {event.title}"
            
            # Aggiungi dettagli dell'evento
            event_time = datetime.fromtimestamp(event.start_time).strftime("%H:%M")
            event_date = datetime.fromtimestamp(event.start_time).strftime("%d/%m/%Y")
            
            if not reminder.message:
                # Se non c'è un messaggio personalizzato, crea uno standard
                message = f"📅 PROMEMORIA: {event.title}\n"
                message += f"Data: {event_date}\n"
                message += f"Ora: {event_time}\n"
                
                if event.location:
                    message += f"Dove: {event.location}\n"
                    
                if event.description:
                    message += f"\n{event.description}"
            
            # Invia la notifica
            await self.notification_service.send_notification(
                type_or_template_id="event_reminder",
                recipients=reminder.recipients,
                data={
                    "event_id": event.id,
                    "event_title": event.title,
                    "event_type": event.type.value,
                    "event_time": event_time,
                    "event_date": event_date,
                    "message": message,
                    "channel_id": event.channel_id
                }
            )
            
            # Aggiorna lo stato del promemoria
            reminder.sent = True
            reminder.sent_at = time.time()
            
            # Rimuovi dai promemoria pendenti
            self.pending_reminders.pop((event.id, reminder.id), None)
            
            # Aggiorna nel database
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE event_reminders
                        SET sent = true, sent_at = $1
                        WHERE id = $2
                        """,
                        reminder.sent_at, reminder.id
                    )
            
            logger.info(f"Promemoria inviato per evento {event.id}: {event.title}")
        
        except Exception as e:
            logger.error(f"Errore nell'invio del promemoria: {e}")
    
    async def create_event(self, channel_id: str, data: Dict[str, Any]) -> Optional[str]:
        """
        Crea un nuovo evento pianificato.
        
        Args:
            channel_id: ID del canale
            data: Dati dell'evento
            
        Returns:
            str: ID dell'evento creato, o None in caso di errore
        """
        if not self.db_pool:
            logger.error("Nessun pool di database fornito per la creazione dell'evento")
            return None
        
        try:
            # Valida i dati di input
            title = data.get('title')
            if not title:
                logger.error("Titolo dell'evento mancante")
                return None
                
            start_time = data.get('start_time')
            if not start_time:
                logger.error("Ora di inizio dell'evento mancante")
                return None
            
            # Determina il tipo di evento
            type_str = data.get('type', 'OTHER')
            try:
                event_type = EventType(type_str)
            except ValueError:
                logger.warning(f"Tipo di evento non valido: {type_str}, usando 'OTHER'")
                event_type = EventType.OTHER
            
            # Crea ID univoco
            event_id = str(uuid.uuid4())
            
            # Crea l'oggetto evento
            event = ScheduledEvent(
                id=event_id,
                channel_id=channel_id,
                title=title,
                type=event_type,
                status=EventStatus.PENDING,
                start_time=start_time,
                end_time=data.get('end_time'),
                created_by=data.get('created_by', 'system'),
                created_at=time.time(),
                description=data.get('description', ''),
                location=data.get('location'),
                color=data.get('color'),
                metadata=data.get('metadata', {}),
                reminders=data.get('reminders', []),
                recurrence=data.get('recurrence'),
                external_id=data.get('external_id')
            )
            
            # Salva nel database
            async with self.db_pool.acquire() as conn:
                # Inizia una transazione
                async with conn.transaction():
                    # Inserisci l'evento
                    await conn.execute(
                        """
                        INSERT INTO scheduled_events
                        (id, channel_id, title, type, status, start_time, end_time,
                         created_by, created_at, description, location, color,
                         metadata, reminders, recurrence, external_id)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                        """,
                        event.id, event.channel_id, event.title, event.type.value,
                        event.status.value, event.start_time, event.end_time,
                        event.created_by, event.created_at, event.description,
                        event.location, event.color,
                        json.dumps(event.metadata) if event.metadata else None,
                        json.dumps(event.reminders) if event.reminders else None,
                        json.dumps(event.recurrence) if event.recurrence else None,
                        event.external_id
                    )
                    
                    # Crea i promemoria
                    for reminder_data in event.reminders:
                        reminder_id = str(uuid.uuid4())
                        
                        await conn.execute(
                            """
                            INSERT INTO event_reminders
                            (id, event_id, time_before, type, recipients, message, sent)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            """,
                            reminder_id, event.id,
                            reminder_data.get('time_before', 900),  # Default 15 minuti
                            reminder_data.get('type', 'app'),
                            json.dumps(reminder_data.get('recipients', [])),
                            reminder_data.get('message'),
                            False
                        )
                        
                        # Crea oggetto promemoria in memoria
                        reminder = EventReminder(
                            id=reminder_id,
                            event_id=event.id,
                            time_before=reminder_data.get('time_before', 900),
                            type=reminder_data.get('type', 'app'),
                            recipients=reminder_data.get('recipients', []),
                            message=reminder_data.get('message'),
                            sent=False
                        )
                        
                        # Aggiungi ai promemoria pendenti
                        self.pending_reminders[(event.id, reminder_id)] = reminder
            
            # Aggiungi agli eventi pendenti
            self.pending_events[event.id] = event
            
            logger.info(f"Evento '{event.title}' creato con ID {event.id}")
            return event.id
        
        except Exception as e:
            logger.error(f"Errore nella creazione dell'evento: {e}")
            return None
    
    async def update_event(self, event_id: str, data: Dict[str, Any]) -> bool:
        """
        Aggiorna un evento esistente.
        
        Args:
            event_id: ID dell'evento
            data: Dati aggiornati
            
        Returns:
            bool: True se l'aggiornamento è riuscito
        """
        # Controlla se l'evento esiste
        event = self.pending_events.get(event_id) or self.active_events.get(event_id)
        if not event:
            logger.warning(f"Evento {event_id} non trovato per l'aggiornamento")
            return False
        
        if not self.db_pool:
            return False
            
        try:
            # Prepara i campi da aggiornare
            update_fields = {}
            
            for field in ['title', 'description', 'start_time', 'end_time', 
                         'location', 'color', 'external_id']:
                if field in data:
                    update_fields[field] = data[field]
            
            # Campi JSON
            if 'metadata' in data:
                update_fields['metadata'] = json.dumps(data['metadata'])
            
            if 'reminders' in data:
                update_fields['reminders'] = json.dumps(data['reminders'])
            
            if 'recurrence' in data:
                update_fields['recurrence'] = json.dumps(data['recurrence'])
            
            # Aggiorna timestamp
            update_fields['last_updated'] = time.time()
            
            # Cambia stato se specificato
            new_status = None
            if 'status' in data:
                try:
                    new_status = EventStatus(data['status'])
                    update_fields['status'] = new_status.value
                except ValueError:
                    logger.warning(f"Stato evento non valido: {data['status']}")
            
            # Aggiorna tipo se specificato
            if 'type' in data:
                try:
                    new_type = EventType(data['type'])
                    update_fields['type'] = new_type.value
                except ValueError:
                    logger.warning(f"Tipo evento non valido: {data['type']}")
            
            # Costruisci la query di aggiornamento
            if not update_fields:
                logger.warning("Nessun campo valido da aggiornare")
                return False
            
            # Crea query dinamica
            set_clauses = []
            params = []
            
            for i, (key, value) in enumerate(update_fields.items(), start=1):
                set_clauses.append(f"{key} = ${i}")
                params.append(value)
            
            # Aggiungi ID come ultimo parametro
            params.append(event_id)
            
            query = f"""
                UPDATE scheduled_events
                SET {', '.join(set_clauses)}
                WHERE id = ${len(params)}
            """
            
            # Esegui l'aggiornamento
            async with self.db_pool.acquire() as conn:
                await conn.execute(query, *params)
            
            # Aggiorna l'evento in memoria
            if 'title' in data:
                event.title = data['title']
            if 'description' in data:
                event.description = data['description']
            if 'start_time' in data:
                event.start_time = data['start_time']
            if 'end_time' in data:
                event.end_time = data['end_time']
            if 'location' in data:
                event.location = data['location']
            if 'color' in data:
                event.color = data['color']
            if 'metadata' in data:
                event.metadata = data['metadata']
            if 'external_id' in data:
                event.external_id = data['external_id']
            
            event.last_updated = update_fields['last_updated']
            
            # Gestisci i reminders aggiornati
            if 'reminders' in data:
                # TODO: Implementare l'aggiornamento dei promemoria
                pass
            
            # Gestisci il cambio di stato
            if new_status:
                # Sposta l'evento nella lista appropriata
                if new_status == EventStatus.PENDING:
                    self.pending_events[event_id] = event
                    self.active_events.pop(event_id, None)
                    event.status = EventStatus.PENDING
                elif new_status == EventStatus.ACTIVE:
                    self.active_events[event_id] = event
                    self.pending_events.pop(event_id, None)
                    event.status = EventStatus.ACTIVE
                elif new_status in [EventStatus.COMPLETED, EventStatus.CANCELLED, EventStatus.FAILED]:
                    self.pending_events.pop(event_id, None)
                    self.active_events.pop(event_id, None)
                    event.status = new_status
            
            logger.info(f"Evento {event_id} aggiornato con successo")
            return True
        
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento dell'evento {event_id}: {e}")
            return False
    
    async def delete_event(self, event_id: str) -> bool:
        """
        Elimina un evento pianificato.
        
        Args:
            event_id: ID dell'evento
            
        Returns:
            bool: True se l'eliminazione è riuscita
        """
        # Rimuovi l'evento dalle liste in memoria
        self.pending_events.pop(event_id, None)
        self.active_events.pop(event_id, None)
        
        # Rimuovi i promemoria associati
        reminders_to_remove = []
        for (e_id, r_id) in self.pending_reminders.keys():
            if e_id == event_id:
                reminders_to_remove.append((e_id, r_id))
        
        for key in reminders_to_remove:
            self.pending_reminders.pop(key, None)
        
        if not self.db_pool:
            return False
            
        try:
            async with self.db_pool.acquire() as conn:
                # Elimina l'evento e tutti i dati associati
                async with conn.transaction():
                    # Elimina i promemoria
                    await conn.execute(
                        "DELETE FROM event_reminders WHERE event_id = $1",
                        event_id
                    )
                    
                    # Elimina le istanze ricorrenti
                    await conn.execute(
                        "DELETE FROM recurring_event_instances WHERE parent_event_id = $1",
                        event_id
                    )
                    
                    # Elimina l'evento
                    await conn.execute(
                        "DELETE FROM scheduled_events WHERE id = $1",
                        event_id
                    )
            
            logger.info(f"Evento {event_id} eliminato con successo")
            return True
        
        except Exception as e:
            logger.error(f"Errore nell'eliminazione dell'evento {event_id}: {e}")
            return False
    
    async def start_event(self, event_id: str) -> bool:
        """
        Avvia un evento pianificato, eseguendo le azioni associate.
        
        Args:
            event_id: ID dell'evento
            
        Returns:
            bool: True se l'avvio è riuscito
        """
        # Verifica se l'evento esiste
        if event_id not in self.pending_events:
            logger.warning(f"Evento {event_id} non trovato tra quelli pendenti")
            return False
        
        event = self.pending_events[event_id]
        
        try:
            # Aggiorna lo stato dell'evento
            event.status = EventStatus.ACTIVE
            
            # Sposta l'evento nella lista degli attivi
            self.active_events[event_id] = event
            self.pending_events.pop(event_id)
            
            # Aggiorna nel database
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE scheduled_events
                        SET status = $1, last_updated = $2
                        WHERE id = $3
                        """,
                        event.status.value, time.time(), event.id
                    )
            
            # Esegui le azioni associate al tipo di evento
            handler = self.event_handlers.get(event.type)
            if handler:
                # Esegui l'handler in un task separato
                task = asyncio.create_task(handler(event))
                self.background_tasks.add(task)
                task.add_done_callback(self.background_tasks.discard)
            
            # Notifica l'inizio dell'evento
            if self.notification_service:
                await self.notification_service.send_notification(
                    type_or_template_id="event_started",
                    recipients=[event.channel_id],
                    data={
                        "event_id": event.id,
                        "event_title": event.title,
                        "event_type": event.type.value,
                        "channel_id": event.channel_id
                    }
                )
            
            logger.info(f"Evento {event_id} avviato con successo")
            return True
        
        except Exception as e:
            logger.error(f"Errore nell'avvio dell'evento {event_id}: {e}")
            return False
    
    async def complete_event(self, event_id: str) -> bool:
        """
        Completa un evento attivo.
        
        Args:
            event_id: ID dell'evento
            
        Returns:
            bool: True se il completamento è riuscito
        """
        # Verifica se l'evento esiste
        if event_id not in self.active_events:
            logger.warning(f"Evento {event_id} non trovato tra quelli attivi")
            return False
        
        event = self.active_events[event_id]
        
        try:
            # Aggiorna lo stato dell'evento
            event.status = EventStatus.COMPLETED
            
            # Rimuovi l'evento dalla lista degli attivi
            self.active_events.pop(event_id)
            
            # Aggiorna nel database
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE scheduled_events
                        SET status = $1, last_updated = $2
                        WHERE id = $3
                        """,
                        event.status.value, time.time(), event.id
                    )
            
            # Notifica il completamento dell'evento
            if self.notification_service:
                await self.notification_service.send_notification(
                    type_or_template_id="event_completed",
                    recipients=[event.channel_id],
                    data={
                        "event_id": event.id,
                        "event_title": event.title,
                        "event_type": event.type.value,
                        "channel_id": event.channel_id
                    }
                )
            
            logger.info(f"Evento {event_id} completato con successo")
            return True
        
        except Exception as e:
            logger.error(f"Errore nel completamento dell'evento {event_id}: {e}")
            return False
    
    async def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Ottiene i dettagli di un evento.
        
        Args:
            event_id: ID dell'evento
            
        Returns:
            Dict: Dettagli dell'evento o None se non trovato
        """
        # Controlla prima in memoria
        event = self.pending_events.get(event_id) or self.active_events.get(event_id)
        if event:
            return asdict(event)
        
        # Altrimenti cerca nel database
        if not self.db_pool:
            return None
        
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM scheduled_events WHERE id = $1",
                    event_id
                )
                
                if not row:
                    return None
                
                # Converti in dizionario
                event_data = dict(row)
                
                # Converti campi JSON
                if event_data.get('metadata'):
                    event_data['metadata'] = json.loads(event_data['metadata'])
                else:
                    event_data['metadata'] = {}
                
                if event_data.get('reminders'):
                    event_data['reminders'] = json.loads(event_data['reminders'])
                else:
                    event_data['reminders'] = []
                
                if event_data.get('recurrence'):
                    event_data['recurrence'] = json.loads(event_data['recurrence'])
                
                return event_data
        
        except Exception as e:
            logger.error(f"Errore nel recupero dell'evento {event_id}: {e}")
            return None
    
    async def get_channel_events(self, channel_id: str, 
                              start_time: Optional[float] = None,
                              end_time: Optional[float] = None,
                              status: Optional[str] = None,
                              type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Ottiene gli eventi di un canale con filtri opzionali.
        
        Args:
            channel_id: ID del canale
            start_time: Filtra eventi dopo questo timestamp (opzionale)
            end_time: Filtra eventi prima di questo timestamp (opzionale)
            status: Filtra per stato (opzionale)
            type: Filtra per tipo (opzionale)
            
        Returns:
            List[Dict]: Lista degli eventi
        """
        if not self.db_pool:
            return []
        
        try:
            # Costruisci la query con i parametri di filtro
            query = "SELECT * FROM scheduled_events WHERE channel_id = $1"
            params = [channel_id]
            
            if start_time is not None:
                query += f" AND start_time >= ${len(params) + 1}"
                params.append(start_time)
            
            if end_time is not None:
                query += f" AND start_time <= ${len(params) + 1}"
                params.append(end_time)
            
            if status:
                query += f" AND status = ${len(params) + 1}"
                params.append(status)
            
            if type:
                query += f" AND type = ${len(params) + 1}"
                params.append(type)
            
            query += " ORDER BY start_time"
            
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(query, *params)
                
                events = []
                for row in rows:
                    event_data = dict(row)
                    
                    # Converti campi JSON
                    if event_data.get('metadata'):
                        event_data['metadata'] = json.loads(event_data['metadata'])
                    else:
                        event_data['metadata'] = {}
                    
                    if event_data.get('reminders'):
                        event_data['reminders'] = json.loads(event_data['reminders'])
                    else:
                        event_data['reminders'] = []
                    
                    if event_data.get('recurrence'):
                        event_data['recurrence'] = json.loads(event_data['recurrence'])
                    
                    events.append(event_data)
                
                return events
        
        except Exception as e:
            logger.error(f"Errore nel recupero degli eventi del canale {channel_id}: {e}")
            return [] 