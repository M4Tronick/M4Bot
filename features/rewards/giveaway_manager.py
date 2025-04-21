#!/usr/bin/env python3
"""
Gestore principale del sistema di giveaway per M4Bot.

Questo modulo gestisce la creazione, esecuzione e controllo dei giveaway
e coordina la selezione dei vincitori, l'invio delle notifiche e il tracciamento dei premi.
"""

import os
import sys
import json
import asyncio
import logging
import time
import random
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set, Union, Tuple
from dataclasses import asdict

# Importa i moduli locali
from .models import Giveaway, Prize, Entry, Winner, GiveawayStatus
from .validators import ParticipationValidator
from .prize_system import PrizeSystem

# Configura il logger
logger = logging.getLogger('m4bot.rewards.giveaway')

class GiveawayManager:
    """
    Classe principale che gestisce il sistema di giveaway.
    """
    
    def __init__(self, db_pool=None, config: Dict[str, Any] = None, notification_service=None):
        """
        Inizializza il gestore di giveaway.
        
        Args:
            db_pool: Pool di connessioni al database
            config: Configurazione personalizzata
            notification_service: Servizio di notifiche per gli avvisi
        """
        self.db_pool = db_pool
        self.config = config or {}
        self.notification_service = notification_service
        
        # Dizionario di giveaway attivi
        # giveaway_id -> Giveaway
        self.active_giveaways: Dict[str, Giveaway] = {}
        
        # Gestione premi
        self.prize_system = PrizeSystem(db_pool, config)
        
        # Validatori per i requisiti di partecipazione
        self.validators = ParticipationValidator(db_pool, config)
        
        # Task in background per la gestione dei giveaway
        self.background_tasks = set()
        self.running = False
        
        # Intervallo di controllo per giveaway temporizzati (secondi)
        self.check_interval = self.config.get('giveaway_check_interval', 15)
        
        logger.info("Gestore giveaway inizializzato")
    
    async def initialize(self):
        """Inizializza il gestore di giveaway."""
        # Carica i giveaway attivi dal database
        await self._load_active_giveaways()
        
        # Avvia il task di controllo periodico
        self.running = True
        task = asyncio.create_task(self._periodic_check())
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
        
        logger.info(f"Gestore giveaway avviato con {len(self.active_giveaways)} giveaway attivi")
    
    async def shutdown(self):
        """Spegni il gestore di giveaway in modo sicuro."""
        self.running = False
        
        # Attendi che tutti i task in background terminino
        if self.background_tasks:
            logger.info(f"In attesa che {len(self.background_tasks)} task terminino...")
            await asyncio.gather(*self.background_tasks, return_exceptions=True)
        
        logger.info("Gestore giveaway spento correttamente")
    
    async def _load_active_giveaways(self):
        """Carica i giveaway attivi dal database."""
        if not self.db_pool:
            logger.warning("Nessun pool di database fornito, impossibile caricare giveaway")
            return
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM giveaways 
                    WHERE status IN ('active', 'pending')
                    """
                )
                
                for row in rows:
                    # Converti la riga in un dizionario
                    giveaway_data = dict(row)
                    
                    # Carica i requisiti
                    requirements = await conn.fetch(
                        "SELECT * FROM giveaway_requirements WHERE giveaway_id = $1",
                        giveaway_data['id']
                    )
                    giveaway_data['requirements'] = [dict(req) for req in requirements]
                    
                    # Crea l'oggetto Giveaway
                    giveaway = Giveaway(
                        id=giveaway_data['id'],
                        channel_id=giveaway_data['channel_id'],
                        title=giveaway_data['title'],
                        description=giveaway_data['description'],
                        prize_id=giveaway_data['prize_id'],
                        status=GiveawayStatus(giveaway_data['status']),
                        start_time=giveaway_data['start_time'],
                        end_time=giveaway_data['end_time'],
                        max_winners=giveaway_data['max_winners'],
                        requirements=giveaway_data['requirements'],
                        created_by=giveaway_data['created_by'],
                        created_at=giveaway_data['created_at'],
                        updated_at=giveaway_data['updated_at']
                    )
                    
                    # Aggiungi alla lista di giveaway attivi
                    self.active_giveaways[giveaway.id] = giveaway
                
                logger.info(f"Caricati {len(self.active_giveaways)} giveaway attivi dal database")
        
        except Exception as e:
            logger.error(f"Errore nel caricamento dei giveaway attivi: {e}")
    
    async def _periodic_check(self):
        """Task periodico per controllare lo stato dei giveaway temporizzati."""
        logger.info("Avviato task periodico per controllo giveaway")
        
        while self.running:
            try:
                await self._check_giveaway_timers()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Errore nel controllo periodico dei giveaway: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _check_giveaway_timers(self):
        """Controlla i timer dei giveaway e aggiorna i loro stati."""
        current_time = time.time()
        giveaways_to_start = []
        giveaways_to_end = []
        
        # Controlla tutti i giveaway attivi
        for giveaway_id, giveaway in list(self.active_giveaways.items()):
            # Controlla se è ora di avviare un giveaway in stato 'pending'
            if giveaway.status == GiveawayStatus.PENDING and giveaway.start_time <= current_time:
                giveaways_to_start.append(giveaway)
            
            # Controlla se è ora di terminare un giveaway in stato 'active'
            elif giveaway.status == GiveawayStatus.ACTIVE and giveaway.end_time and giveaway.end_time <= current_time:
                giveaways_to_end.append(giveaway)
        
        # Avvia i giveaway pronti
        for giveaway in giveaways_to_start:
            await self.start_giveaway(giveaway.id)
        
        # Termina i giveaway scaduti
        for giveaway in giveaways_to_end:
            await self.end_giveaway(giveaway.id)
    
    async def create_giveaway(self, channel_id: str, data: Dict[str, Any]) -> Optional[str]:
        """
        Crea un nuovo giveaway.
        
        Args:
            channel_id: ID del canale
            data: Dati del giveaway
            
        Returns:
            str: ID del giveaway creato, o None in caso di errore
        """
        if not self.db_pool:
            logger.error("Nessun pool di database fornito per la creazione del giveaway")
            return None
        
        try:
            # Valida i dati di input
            title = data.get('title')
            if not title:
                logger.error("Titolo del giveaway mancante")
                return None
            
            # Crea un ID univoco
            giveaway_id = str(uuid.uuid4())
            
            # Determina gli orari di inizio e fine
            current_time = time.time()
            start_time = data.get('start_time', current_time)
            end_time = data.get('end_time')
            
            # Se start_time è nel futuro, imposta lo stato come 'pending'
            status = GiveawayStatus.PENDING if start_time > current_time else GiveawayStatus.ACTIVE
            
            # Creatore del giveaway
            created_by = data.get('created_by', 'system')
            
            # Verifica premio
            prize_id = data.get('prize_id')
            if prize_id:
                # Verifica che il premio esista
                prize = await self.prize_system.get_prize(prize_id)
                if not prize:
                    logger.error(f"Premio con ID {prize_id} non trovato")
                    return None
            
            # Prepara i dati del giveaway
            giveaway = Giveaway(
                id=giveaway_id,
                channel_id=channel_id,
                title=title,
                description=data.get('description', ''),
                prize_id=prize_id,
                status=status,
                start_time=start_time,
                end_time=end_time,
                max_winners=data.get('max_winners', 1),
                requirements=data.get('requirements', []),
                created_by=created_by,
                created_at=current_time,
                updated_at=current_time
            )
            
            # Salva nel database
            async with self.db_pool.acquire() as conn:
                # Inizia una transazione
                async with conn.transaction():
                    # Inserisci il giveaway
                    await conn.execute(
                        """
                        INSERT INTO giveaways
                        (id, channel_id, title, description, prize_id, status, 
                         start_time, end_time, max_winners, created_by, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        """,
                        giveaway.id, giveaway.channel_id, giveaway.title, giveaway.description,
                        giveaway.prize_id, giveaway.status.value, giveaway.start_time, giveaway.end_time,
                        giveaway.max_winners, giveaway.created_by, giveaway.created_at, giveaway.updated_at
                    )
                    
                    # Inserisci i requisiti
                    for req in giveaway.requirements:
                        await conn.execute(
                            """
                            INSERT INTO giveaway_requirements
                            (giveaway_id, type, value, description)
                            VALUES ($1, $2, $3, $4)
                            """,
                            giveaway.id, req.get('type'), req.get('value'), req.get('description', '')
                        )
            
            # Aggiungi ai giveaway attivi
            self.active_giveaways[giveaway.id] = giveaway
            
            # Se lo stato è ACTIVE, annuncia il giveaway
            if giveaway.status == GiveawayStatus.ACTIVE:
                await self._announce_giveaway(giveaway)
            
            logger.info(f"Giveaway '{giveaway.title}' creato con ID {giveaway.id}")
            return giveaway.id
        
        except Exception as e:
            logger.error(f"Errore nella creazione del giveaway: {e}")
            return None
    
    async def start_giveaway(self, giveaway_id: str) -> bool:
        """
        Avvia un giveaway in stato 'pending'.
        
        Args:
            giveaway_id: ID del giveaway
            
        Returns:
            bool: True se l'operazione è riuscita
        """
        if giveaway_id not in self.active_giveaways:
            logger.warning(f"Giveaway {giveaway_id} non trovato tra quelli attivi")
            return False
        
        giveaway = self.active_giveaways[giveaway_id]
        
        if giveaway.status != GiveawayStatus.PENDING:
            logger.warning(f"Impossibile avviare giveaway {giveaway_id}: stato non valido {giveaway.status.value}")
            return False
        
        try:
            # Aggiorna lo stato
            giveaway.status = GiveawayStatus.ACTIVE
            giveaway.updated_at = time.time()
            
            # Aggiorna nel database
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE giveaways
                        SET status = $1, updated_at = $2
                        WHERE id = $3
                        """,
                        giveaway.status.value, giveaway.updated_at, giveaway.id
                    )
            
            # Annuncia il giveaway
            await self._announce_giveaway(giveaway)
            
            logger.info(f"Giveaway '{giveaway.title}' ({giveaway.id}) avviato")
            return True
        
        except Exception as e:
            logger.error(f"Errore nell'avvio del giveaway {giveaway_id}: {e}")
            return False
    
    async def end_giveaway(self, giveaway_id: str, force: bool = False) -> bool:
        """
        Termina un giveaway e seleziona i vincitori.
        
        Args:
            giveaway_id: ID del giveaway
            force: Forza la chiusura anche se non è ancora scaduto
            
        Returns:
            bool: True se l'operazione è riuscita
        """
        if giveaway_id not in self.active_giveaways:
            logger.warning(f"Giveaway {giveaway_id} non trovato tra quelli attivi")
            return False
        
        giveaway = self.active_giveaways[giveaway_id]
        
        if giveaway.status != GiveawayStatus.ACTIVE:
            logger.warning(f"Impossibile terminare giveaway {giveaway_id}: stato non valido {giveaway.status.value}")
            return False
        
        try:
            # Verifica se può essere terminato
            current_time = time.time()
            if not force and giveaway.end_time and giveaway.end_time > current_time:
                logger.warning(f"Giveaway {giveaway_id} non può essere terminato: non è ancora scaduto")
                return False
            
            # Ottieni le partecipazioni
            entries = await self._get_entries(giveaway_id)
            if not entries:
                logger.warning(f"Nessuna partecipazione per il giveaway {giveaway_id}")
            
            # Seleziona i vincitori
            winners = await self._select_winners(giveaway, entries)
            if winners:
                # Aggiorna lo stato del premio se presente
                if giveaway.prize_id:
                    for winner in winners:
                        await self.prize_system.assign_prize(
                            prize_id=giveaway.prize_id,
                            user_id=winner.user_id,
                            giveaway_id=giveaway.id
                        )
                
                # Notifica i vincitori
                await self._notify_winners(giveaway, winners)
            
            # Aggiorna lo stato
            giveaway.status = GiveawayStatus.COMPLETED
            giveaway.updated_at = current_time
            
            # Aggiorna nel database
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    async with conn.transaction():
                        # Aggiorna lo stato del giveaway
                        await conn.execute(
                            """
                            UPDATE giveaways
                            SET status = $1, updated_at = $2
                            WHERE id = $3
                            """,
                            giveaway.status.value, giveaway.updated_at, giveaway.id
                        )
                        
                        # Registra i vincitori
                        for winner in winners:
                            await conn.execute(
                                """
                                INSERT INTO giveaway_winners
                                (giveaway_id, user_id, entry_id, selected_at)
                                VALUES ($1, $2, $3, $4)
                                """,
                                giveaway.id, winner.user_id, winner.entry_id, winner.selected_at
                            )
            
            # Rimuovi dai giveaway attivi
            self.active_giveaways.pop(giveaway_id, None)
            
            logger.info(f"Giveaway '{giveaway.title}' ({giveaway.id}) terminato con {len(winners)} vincitori")
            return True
        
        except Exception as e:
            logger.error(f"Errore nella chiusura del giveaway {giveaway_id}: {e}")
            return False
    
    async def enter_giveaway(self, giveaway_id: str, user_id: str, username: str) -> Dict[str, Any]:
        """
        Registra la partecipazione di un utente a un giveaway.
        
        Args:
            giveaway_id: ID del giveaway
            user_id: ID dell'utente
            username: Nome utente
            
        Returns:
            Dict: Risultato dell'operazione con stato ed eventuale messaggio
        """
        if giveaway_id not in self.active_giveaways:
            return {"success": False, "message": "Giveaway non trovato o non attivo"}
        
        giveaway = self.active_giveaways[giveaway_id]
        
        if giveaway.status != GiveawayStatus.ACTIVE:
            return {"success": False, "message": f"Il giveaway non è attivo (stato: {giveaway.status.value})"}
        
        try:
            # Controlla se l'utente ha già partecipato
            already_entered = await self._check_user_entry(giveaway_id, user_id)
            if already_entered:
                return {"success": False, "message": "Hai già partecipato a questo giveaway"}
            
            # Verifica i requisiti di partecipazione
            if giveaway.requirements:
                validation = await self.validators.validate_requirements(
                    user_id=user_id,
                    channel_id=giveaway.channel_id,
                    requirements=giveaway.requirements
                )
                
                if not validation['valid']:
                    return {
                        "success": False, 
                        "message": f"Non soddisfi i requisiti: {validation['reason']}"
                    }
            
            # Registra la partecipazione
            entry_id = str(uuid.uuid4())
            entry_time = time.time()
            
            if self.db_pool:
                async with self.db_pool.acquire() as conn:
                    await conn.execute(
                        """
                        INSERT INTO giveaway_entries
                        (id, giveaway_id, user_id, username, entry_time)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        entry_id, giveaway_id, user_id, username, entry_time
                    )
            
            logger.info(f"Utente {username} ({user_id}) ha partecipato al giveaway {giveaway_id}")
            return {"success": True, "message": f"Hai partecipato al giveaway '{giveaway.title}'"}
        
        except Exception as e:
            logger.error(f"Errore nella registrazione della partecipazione al giveaway {giveaway_id}: {e}")
            return {"success": False, "message": "Si è verificato un errore durante la registrazione"}
    
    async def _check_user_entry(self, giveaway_id: str, user_id: str) -> bool:
        """
        Controlla se un utente ha già partecipato a un giveaway.
        
        Args:
            giveaway_id: ID del giveaway
            user_id: ID dell'utente
            
        Returns:
            bool: True se l'utente ha già partecipato
        """
        if not self.db_pool:
            return False
        
        try:
            async with self.db_pool.acquire() as conn:
                entry = await conn.fetchrow(
                    """
                    SELECT id FROM giveaway_entries
                    WHERE giveaway_id = $1 AND user_id = $2
                    """,
                    giveaway_id, user_id
                )
                
                return entry is not None
        
        except Exception as e:
            logger.error(f"Errore nella verifica della partecipazione dell'utente {user_id}: {e}")
            return False
    
    async def _get_entries(self, giveaway_id: str) -> List[Entry]:
        """
        Ottiene tutte le partecipazioni per un giveaway.
        
        Args:
            giveaway_id: ID del giveaway
            
        Returns:
            List[Entry]: Lista delle partecipazioni
        """
        entries = []
        
        if not self.db_pool:
            return entries
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM giveaway_entries
                    WHERE giveaway_id = $1
                    """,
                    giveaway_id
                )
                
                for row in rows:
                    entry = Entry(
                        id=row['id'],
                        giveaway_id=row['giveaway_id'],
                        user_id=row['user_id'],
                        username=row['username'],
                        entry_time=row['entry_time']
                    )
                    entries.append(entry)
                
                logger.debug(f"Recuperate {len(entries)} partecipazioni per il giveaway {giveaway_id}")
                return entries
        
        except Exception as e:
            logger.error(f"Errore nel recupero delle partecipazioni per il giveaway {giveaway_id}: {e}")
            return entries
    
    async def _select_winners(self, giveaway: Giveaway, entries: List[Entry]) -> List[Winner]:
        """
        Seleziona casualmente i vincitori tra le partecipazioni.
        
        Args:
            giveaway: Oggetto Giveaway
            entries: Lista delle partecipazioni
            
        Returns:
            List[Winner]: Lista dei vincitori
        """
        winners = []
        
        if not entries:
            logger.warning(f"Nessuna partecipazione per selezionare vincitori del giveaway {giveaway.id}")
            return winners
        
        try:
            # Numero di vincitori da selezionare
            num_winners = min(giveaway.max_winners, len(entries))
            
            # Selezione casuale
            selected_entries = random.sample(entries, num_winners)
            
            # Crea gli oggetti vincitore
            current_time = time.time()
            for entry in selected_entries:
                winner = Winner(
                    giveaway_id=giveaway.id,
                    user_id=entry.user_id,
                    username=entry.username,
                    entry_id=entry.id,
                    selected_at=current_time
                )
                winners.append(winner)
            
            logger.info(f"Selezionati {len(winners)} vincitori per il giveaway {giveaway.id}")
            return winners
        
        except Exception as e:
            logger.error(f"Errore nella selezione dei vincitori per il giveaway {giveaway.id}: {e}")
            return winners
    
    async def _announce_giveaway(self, giveaway: Giveaway):
        """
        Annuncia un nuovo giveaway nel canale.
        
        Args:
            giveaway: Oggetto Giveaway
        """
        if not self.notification_service:
            logger.warning("Nessun servizio di notifica disponibile per annunciare il giveaway")
            return
        
        try:
            # Crea un messaggio di annuncio
            message = f"🎉 NUOVO GIVEAWAY: {giveaway.title} 🎉"
            
            # Aggiunge descrizione se presente
            if giveaway.description:
                message += f"\n{giveaway.description}"
            
            # Aggiunge dettagli premio se presente
            if giveaway.prize_id:
                prize = await self.prize_system.get_prize(giveaway.prize_id)
                if prize:
                    message += f"\nPREMIO: {prize.name}"
                    if prize.value:
                        message += f" (Valore: {prize.value})"
            
            # Aggiunge istruzioni per partecipare
            message += "\nPer partecipare, digita !enter in chat."
            
            # Aggiunge tempo rimanente se ha una scadenza
            if giveaway.end_time:
                remaining = int(giveaway.end_time - time.time())
                hours, remainder = divmod(remaining, 3600)
                minutes, seconds = divmod(remainder, 60)
                time_str = ""
                if hours > 0:
                    time_str += f"{hours}h "
                if minutes > 0 or hours > 0:
                    time_str += f"{minutes}m "
                time_str += f"{seconds}s"
                message += f"\nTermina tra: {time_str}"
            
            # Aggiunge requisiti se presenti
            if giveaway.requirements:
                req_messages = []
                for req in giveaway.requirements:
                    req_type = req.get('type', '')
                    req_value = req.get('value', '')
                    
                    if req_type == 'follower':
                        req_messages.append("Devi essere un follower")
                    elif req_type == 'subscriber':
                        req_messages.append("Devi essere un iscritto")
                    elif req_type == 'points' and req_value:
                        req_messages.append(f"Devi avere almeno {req_value} punti canale")
                    elif req_type == 'watch_time' and req_value:
                        hours = int(req_value) // 3600
                        req_messages.append(f"Devi aver guardato il canale per almeno {hours} ore")
                
                if req_messages:
                    message += "\nRequisiti: " + ", ".join(req_messages)
            
            # Invia la notifica
            await self.notification_service.send_notification(
                type_or_template_id="giveaway_start",
                recipients=[giveaway.channel_id],
                data={
                    "giveaway_id": giveaway.id,
                    "giveaway_title": giveaway.title,
                    "message": message,
                    "channel_name": giveaway.channel_id  # Questo dovrebbe essere il nome del canale
                }
            )
            
            logger.info(f"Giveaway {giveaway.id} annunciato nel canale {giveaway.channel_id}")
        
        except Exception as e:
            logger.error(f"Errore nell'annuncio del giveaway {giveaway.id}: {e}")
    
    async def _notify_winners(self, giveaway: Giveaway, winners: List[Winner]):
        """
        Notifica i vincitori di un giveaway.
        
        Args:
            giveaway: Oggetto Giveaway
            winners: Lista dei vincitori
        """
        if not self.notification_service:
            logger.warning("Nessun servizio di notifica disponibile per annunciare i vincitori")
            return
        
        try:
            # Prepara il messaggio per il canale
            winner_names = [w.username for w in winners]
            winner_message = "🎉 VINCITORI DEL GIVEAWAY 🎉\n"
            winner_message += f"Giveaway: {giveaway.title}\n"
            winner_message += "Congratulazioni a: " + ", ".join(winner_names)
            
            # Dettagli premio se presente
            if giveaway.prize_id:
                prize = await self.prize_system.get_prize(giveaway.prize_id)
                if prize:
                    winner_message += f"\nPREMIO: {prize.name}"
            
            # Invia la notifica al canale
            await self.notification_service.send_notification(
                type_or_template_id="giveaway_winners",
                recipients=[giveaway.channel_id],
                data={
                    "giveaway_id": giveaway.id,
                    "giveaway_title": giveaway.title,
                    "winners": winner_names,
                    "message": winner_message,
                    "channel_name": giveaway.channel_id  # Questo dovrebbe essere il nome del canale
                }
            )
            
            # Invia notifiche individuali ai vincitori
            for winner in winners:
                user_message = f"🎉 Congratulazioni! Hai vinto il giveaway '{giveaway.title}'!"
                
                # Dettagli premio se presente
                if giveaway.prize_id:
                    prize = await self.prize_system.get_prize(giveaway.prize_id)
                    if prize:
                        user_message += f"\nPREMIO: {prize.name}"
                        user_message += f"\nIstruzioni per riscattare: {prize.redemption_instructions}"
                
                # Invia notifica personale
                await self.notification_service.send_notification(
                    type_or_template_id="giveaway_win_personal",
                    recipients=[winner.user_id],
                    data={
                        "giveaway_id": giveaway.id,
                        "giveaway_title": giveaway.title,
                        "message": user_message,
                        "winner_username": winner.username
                    }
                )
            
            logger.info(f"Vincitori del giveaway {giveaway.id} notificati")
        
        except Exception as e:
            logger.error(f"Errore nella notifica dei vincitori del giveaway {giveaway.id}: {e}")
    
    async def get_giveaway(self, giveaway_id: str) -> Optional[Dict[str, Any]]:
        """
        Ottiene i dettagli di un giveaway.
        
        Args:
            giveaway_id: ID del giveaway
            
        Returns:
            Dict: Dettagli del giveaway o None
        """
        # Controlla prima in memoria
        if giveaway_id in self.active_giveaways:
            giveaway = self.active_giveaways[giveaway_id]
            return asdict(giveaway)
        
        # Altrimenti cerca nel database
        if not self.db_pool:
            return None
        
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM giveaways WHERE id = $1",
                    giveaway_id
                )
                
                if not row:
                    return None
                
                # Converti in dizionario
                giveaway_data = dict(row)
                
                # Ottieni i requisiti
                requirements = await conn.fetch(
                    "SELECT * FROM giveaway_requirements WHERE giveaway_id = $1",
                    giveaway_id
                )
                giveaway_data['requirements'] = [dict(req) for req in requirements]
                
                # Ottieni i vincitori se il giveaway è completato
                if giveaway_data['status'] == GiveawayStatus.COMPLETED.value:
                    winners = await conn.fetch(
                        """
                        SELECT gw.user_id, ge.username, gw.selected_at
                        FROM giveaway_winners gw
                        JOIN giveaway_entries ge ON gw.entry_id = ge.id
                        WHERE gw.giveaway_id = $1
                        """,
                        giveaway_id
                    )
                    giveaway_data['winners'] = [dict(w) for w in winners]
                
                return giveaway_data
        
        except Exception as e:
            logger.error(f"Errore nel recupero del giveaway {giveaway_id}: {e}")
            return None
    
    async def get_channel_giveaways(self, channel_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Ottiene i giveaway di un canale, con filtro opzionale per stato.
        
        Args:
            channel_id: ID del canale
            status: Stato per filtrare (opzionale)
            
        Returns:
            List[Dict]: Lista dei giveaway
        """
        if not self.db_pool:
            return []
        
        try:
            async with self.db_pool.acquire() as conn:
                query = "SELECT * FROM giveaways WHERE channel_id = $1"
                params = [channel_id]
                
                if status:
                    query += " AND status = $2"
                    params.append(status)
                
                query += " ORDER BY created_at DESC"
                
                rows = await conn.fetch(query, *params)
                return [dict(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Errore nel recupero dei giveaway del canale {channel_id}: {e}")
            return [] 