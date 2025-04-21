#!/usr/bin/env python3
"""
Sistema di gestione premi per M4Bot.

Questo modulo gestisce la creazione, assegnazione e riscatto dei premi
per i giveaway e altri sistemi di ricompensa.
"""

import time
import uuid
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import asdict

# Importazioni locali
from .models import Prize, PrizeType

# Logger
logger = logging.getLogger('m4bot.rewards.prizes')

class PrizeSystem:
    """
    Classe che gestisce il sistema di premi.
    """
    
    def __init__(self, db_pool=None, config: Dict[str, Any] = None):
        """
        Inizializza il sistema di premi.
        
        Args:
            db_pool: Pool di connessioni al database
            config: Configurazione personalizzata
        """
        self.db_pool = db_pool
        self.config = config or {}
        
        # Cache dei premi per migliorare le prestazioni
        # prize_id -> Prize
        self.prize_cache = {}
        
        logger.info("Sistema di premi inizializzato")
    
    async def create_prize(self, data: Dict[str, Any]) -> Optional[str]:
        """
        Crea un nuovo premio.
        
        Args:
            data: Dati del premio
            
        Returns:
            str: ID del premio creato, o None in caso di errore
        """
        if not self.db_pool:
            logger.error("Nessun pool di database fornito per la creazione del premio")
            return None
        
        try:
            # Valida i dati di input
            name = data.get('name')
            if not name:
                logger.error("Nome del premio mancante")
                return None
            
            # Determina il tipo di premio
            type_str = data.get('type', 'OTHER')
            try:
                prize_type = PrizeType(type_str)
            except ValueError:
                logger.warning(f"Tipo di premio non valido: {type_str}, usando 'OTHER'")
                prize_type = PrizeType.OTHER
            
            # Crea ID univoco
            prize_id = str(uuid.uuid4())
            
            # Crea l'oggetto premio
            prize = Prize(
                id=prize_id,
                name=name,
                description=data.get('description', ''),
                type=prize_type,
                value=data.get('value'),
                quantity=data.get('quantity', 1),
                image_url=data.get('image_url'),
                redemption_instructions=data.get('redemption_instructions', ''),
                created_at=time.time(),
                created_by=data.get('created_by', 'system'),
                is_active=data.get('is_active', True)
            )
            
            # Salva nel database
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO prizes
                    (id, name, description, type, value, quantity, image_url, 
                     redemption_instructions, created_at, created_by, is_active)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                    """,
                    prize.id, prize.name, prize.description, prize.type.value,
                    prize.value, prize.quantity, prize.image_url,
                    prize.redemption_instructions, prize.created_at,
                    prize.created_by, prize.is_active
                )
            
            # Aggiungi alla cache
            self.prize_cache[prize.id] = prize
            
            logger.info(f"Premio '{prize.name}' creato con ID {prize.id}")
            return prize.id
        
        except Exception as e:
            logger.error(f"Errore nella creazione del premio: {e}")
            return None
    
    async def get_prize(self, prize_id: str) -> Optional[Prize]:
        """
        Ottiene i dettagli di un premio.
        
        Args:
            prize_id: ID del premio
            
        Returns:
            Prize: Oggetto premio o None
        """
        # Controlla prima in cache
        if prize_id in self.prize_cache:
            return self.prize_cache[prize_id]
        
        # Altrimenti cerca nel database
        if not self.db_pool:
            return None
        
        try:
            async with self.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM prizes WHERE id = $1",
                    prize_id
                )
                
                if not row:
                    return None
                
                # Crea l'oggetto premio
                prize = Prize(
                    id=row['id'],
                    name=row['name'],
                    description=row['description'],
                    type=PrizeType(row['type']),
                    value=row['value'],
                    quantity=row['quantity'],
                    image_url=row['image_url'],
                    redemption_instructions=row['redemption_instructions'],
                    created_at=row['created_at'],
                    created_by=row['created_by'],
                    is_active=row['is_active']
                )
                
                # Aggiungi alla cache
                self.prize_cache[prize.id] = prize
                
                return prize
        
        except Exception as e:
            logger.error(f"Errore nel recupero del premio {prize_id}: {e}")
            return None
    
    async def update_prize(self, prize_id: str, data: Dict[str, Any]) -> bool:
        """
        Aggiorna un premio esistente.
        
        Args:
            prize_id: ID del premio
            data: Dati aggiornati
            
        Returns:
            bool: True se l'aggiornamento è riuscito
        """
        if not self.db_pool:
            return False
        
        try:
            # Ottieni il premio corrente
            prize = await self.get_prize(prize_id)
            if not prize:
                logger.warning(f"Premio {prize_id} non trovato per l'aggiornamento")
                return False
            
            # Aggiorna i campi modificabili
            update_fields = {}
            
            if 'name' in data:
                update_fields['name'] = data['name']
            
            if 'description' in data:
                update_fields['description'] = data['description']
            
            if 'value' in data:
                update_fields['value'] = data['value']
            
            if 'quantity' in data:
                update_fields['quantity'] = data['quantity']
            
            if 'image_url' in data:
                update_fields['image_url'] = data['image_url']
            
            if 'redemption_instructions' in data:
                update_fields['redemption_instructions'] = data['redemption_instructions']
            
            if 'is_active' in data:
                update_fields['is_active'] = data['is_active']
            
            if 'type' in data:
                try:
                    # Verifica che il tipo sia valido
                    prize_type = PrizeType(data['type'])
                    update_fields['type'] = prize_type.value
                except ValueError:
                    logger.warning(f"Tipo di premio non valido: {data['type']}, ignorato")
            
            if not update_fields:
                logger.warning("Nessun campo valido da aggiornare")
                return False
            
            # Crea la query di aggiornamento
            query_parts = []
            params = []
            
            for i, (key, value) in enumerate(update_fields.items(), start=1):
                query_parts.append(f"{key} = ${i}")
                params.append(value)
            
            # Aggiungi l'ID come ultimo parametro
            params.append(prize_id)
            
            query = f"""
                UPDATE prizes
                SET {', '.join(query_parts)}
                WHERE id = ${len(params)}
            """
            
            # Esegui l'aggiornamento
            async with self.db_pool.acquire() as conn:
                await conn.execute(query, *params)
            
            # Aggiorna o invalida la cache
            if prize_id in self.prize_cache:
                del self.prize_cache[prize_id]
            
            logger.info(f"Premio {prize_id} aggiornato con successo")
            return True
        
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento del premio {prize_id}: {e}")
            return False
    
    async def delete_prize(self, prize_id: str) -> bool:
        """
        Elimina un premio dal sistema.
        
        Args:
            prize_id: ID del premio
            
        Returns:
            bool: True se l'eliminazione è riuscita
        """
        if not self.db_pool:
            return False
        
        try:
            # Verifica se il premio esiste
            prize = await self.get_prize(prize_id)
            if not prize:
                logger.warning(f"Premio {prize_id} non trovato per l'eliminazione")
                return False
            
            # Verifica se ci sono assegnazioni attive
            async with self.db_pool.acquire() as conn:
                assignments = await conn.fetch(
                    "SELECT * FROM prize_assignments WHERE prize_id = $1",
                    prize_id
                )
                
                if assignments:
                    logger.warning(f"Impossibile eliminare il premio {prize_id}: ci sono {len(assignments)} assegnazioni")
                    return False
                
                # Elimina il premio
                await conn.execute(
                    "DELETE FROM prizes WHERE id = $1",
                    prize_id
                )
            
            # Rimuovi dalla cache
            if prize_id in self.prize_cache:
                del self.prize_cache[prize_id]
            
            logger.info(f"Premio {prize_id} eliminato con successo")
            return True
        
        except Exception as e:
            logger.error(f"Errore nell'eliminazione del premio {prize_id}: {e}")
            return False
    
    async def assign_prize(self, prize_id: str, user_id: str, giveaway_id: Optional[str] = None) -> bool:
        """
        Assegna un premio a un utente.
        
        Args:
            prize_id: ID del premio
            user_id: ID dell'utente
            giveaway_id: ID del giveaway (opzionale)
            
        Returns:
            bool: True se l'assegnazione è riuscita
        """
        if not self.db_pool:
            return False
        
        try:
            # Verifica se il premio esiste e ha disponibilità
            prize = await self.get_prize(prize_id)
            if not prize:
                logger.warning(f"Premio {prize_id} non trovato per l'assegnazione")
                return False
            
            # Controlla se la quantità è sufficiente
            async with self.db_pool.acquire() as conn:
                # Conta le assegnazioni già effettuate
                assigned_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM prize_assignments WHERE prize_id = $1",
                    prize_id
                )
                
                if assigned_count >= prize.quantity:
                    logger.warning(f"Premio {prize_id} non disponibile: assegnate {assigned_count}/{prize.quantity} unità")
                    return False
                
                # Crea un ID univoco per l'assegnazione
                assignment_id = str(uuid.uuid4())
                
                # Crea l'assegnazione
                await conn.execute(
                    """
                    INSERT INTO prize_assignments
                    (id, prize_id, user_id, giveaway_id, assigned_at, claimed, claimed_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    assignment_id, prize_id, user_id, giveaway_id, time.time(), False, None
                )
            
            logger.info(f"Premio {prize_id} assegnato all'utente {user_id}")
            return True
        
        except Exception as e:
            logger.error(f"Errore nell'assegnazione del premio {prize_id} all'utente {user_id}: {e}")
            return False
    
    async def claim_prize(self, assignment_id: str) -> bool:
        """
        Segna un premio come riscattato.
        
        Args:
            assignment_id: ID dell'assegnazione
            
        Returns:
            bool: True se l'operazione è riuscita
        """
        if not self.db_pool:
            return False
        
        try:
            async with self.db_pool.acquire() as conn:
                # Verifica se l'assegnazione esiste
                assignment = await conn.fetchrow(
                    "SELECT * FROM prize_assignments WHERE id = $1",
                    assignment_id
                )
                
                if not assignment:
                    logger.warning(f"Assegnazione {assignment_id} non trovata")
                    return False
                
                # Verifica se è già stata riscattata
                if assignment['claimed']:
                    logger.warning(f"Premio già riscattato: {assignment_id}")
                    return False
                
                # Aggiorna lo stato
                await conn.execute(
                    """
                    UPDATE prize_assignments
                    SET claimed = true, claimed_at = $1
                    WHERE id = $2
                    """,
                    time.time(), assignment_id
                )
            
            logger.info(f"Premio riscattato: {assignment_id}")
            return True
        
        except Exception as e:
            logger.error(f"Errore nel riscatto del premio {assignment_id}: {e}")
            return False
    
    async def get_user_prizes(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Ottiene tutti i premi assegnati a un utente.
        
        Args:
            user_id: ID dell'utente
            
        Returns:
            List[Dict]: Lista dei premi assegnati
        """
        if not self.db_pool:
            return []
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT pa.*, p.name, p.description, p.type, p.value, p.image_url, p.redemption_instructions
                    FROM prize_assignments pa
                    JOIN prizes p ON pa.prize_id = p.id
                    WHERE pa.user_id = $1
                    ORDER BY pa.assigned_at DESC
                    """,
                    user_id
                )
                
                # Converti le righe in dizionari
                prizes = []
                for row in rows:
                    prize_data = dict(row)
                    
                    # Aggiungi info sul giveaway se presente
                    if prize_data['giveaway_id']:
                        giveaway = await conn.fetchrow(
                            "SELECT title FROM giveaways WHERE id = $1",
                            prize_data['giveaway_id']
                        )
                        if giveaway:
                            prize_data['giveaway_title'] = giveaway['title']
                    
                    prizes.append(prize_data)
                
                return prizes
        
        except Exception as e:
            logger.error(f"Errore nel recupero dei premi dell'utente {user_id}: {e}")
            return []
    
    async def get_prize_assignments(self, prize_id: str) -> List[Dict[str, Any]]:
        """
        Ottiene tutte le assegnazioni di un premio.
        
        Args:
            prize_id: ID del premio
            
        Returns:
            List[Dict]: Lista delle assegnazioni
        """
        if not self.db_pool:
            return []
        
        try:
            async with self.db_pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT pa.*, u.username
                    FROM prize_assignments pa
                    JOIN users u ON pa.user_id = u.id
                    WHERE pa.prize_id = $1
                    ORDER BY pa.assigned_at DESC
                    """,
                    prize_id
                )
                
                return [dict(row) for row in rows]
        
        except Exception as e:
            logger.error(f"Errore nel recupero delle assegnazioni del premio {prize_id}: {e}")
            return []
    
    async def get_all_prizes(self, active_only: bool = False) -> List[Dict[str, Any]]:
        """
        Ottiene tutti i premi disponibili nel sistema.
        
        Args:
            active_only: Se True, restituisce solo i premi attivi
            
        Returns:
            List[Dict]: Lista dei premi
        """
        if not self.db_pool:
            return []
        
        try:
            async with self.db_pool.acquire() as conn:
                query = "SELECT * FROM prizes"
                if active_only:
                    query += " WHERE is_active = true"
                query += " ORDER BY created_at DESC"
                
                rows = await conn.fetch(query)
                
                # Converti le righe in dizionari
                prizes = []
                for row in rows:
                    prize_data = dict(row)
                    
                    # Aggiungi info sulle disponibilità
                    assigned_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM prize_assignments WHERE prize_id = $1",
                        row['id']
                    )
                    
                    prize_data['available'] = max(0, row['quantity'] - assigned_count)
                    prize_data['assigned'] = assigned_count
                    
                    prizes.append(prize_data)
                
                return prizes
        
        except Exception as e:
            logger.error(f"Errore nel recupero di tutti i premi: {e}")
            return [] 