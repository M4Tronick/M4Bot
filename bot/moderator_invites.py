import os
import json
import logging
import asyncio
import time
import uuid
import secrets
import string
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Tuple

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/moderator_invites.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("ModeratorInvites")

class ModeratorInviteManager:
    """Gestore degli inviti per i moderatori"""
    
    def __init__(self, db_pool):
        """
        Inizializza il gestore degli inviti
        
        Args:
            db_pool: Pool di connessioni al database
        """
        self.db_pool = db_pool
        
        # Durata degli inviti in giorni
        self.invite_expiry_days = 7
        
        # Crea le directory necessarie
        os.makedirs("logs", exist_ok=True)
        
        logger.info("Gestore inviti moderatori inizializzato")
        
    async def initialize(self):
        """Inizializza le tabelle necessarie nel database"""
        if not self.db_pool:
            logger.error("Nessun pool di database disponibile")
            return False
            
        try:
            async with self.db_pool.acquire() as conn:
                # Tabella inviti moderatori
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS moderator_invites (
                        id SERIAL PRIMARY KEY,
                        channel_id INTEGER REFERENCES channels(id),
                        invited_by INTEGER REFERENCES users(id),
                        invite_code VARCHAR(64) UNIQUE NOT NULL,
                        email VARCHAR(255) NOT NULL,
                        permissions JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
                        status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined', 'expired', 'revoked'))
                    )
                ''')
                
                # Tabella moderatori del canale
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS channel_moderators (
                        id SERIAL PRIMARY KEY,
                        channel_id INTEGER REFERENCES channels(id),
                        user_id INTEGER REFERENCES users(id),
                        permissions JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                        status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'blocked')),
                        invite_id INTEGER REFERENCES moderator_invites(id),
                        UNIQUE(channel_id, user_id)
                    )
                ''')
                
                # Indici per migliorare le performance
                await conn.execute('CREATE INDEX IF NOT EXISTS idx_moderator_invites_channel_id ON moderator_invites(channel_id)')
                await conn.execute('CREATE INDEX IF NOT EXISTS idx_moderator_invites_email ON moderator_invites(email)')
                await conn.execute('CREATE INDEX IF NOT EXISTS idx_moderator_invites_status ON moderator_invites(status)')
                await conn.execute('CREATE INDEX IF NOT EXISTS idx_channel_moderators_channel_id ON channel_moderators(channel_id)')
                await conn.execute('CREATE INDEX IF NOT EXISTS idx_channel_moderators_user_id ON channel_moderators(user_id)')
                
                logger.info("Tabelle per il sistema di inviti moderatori inizializzate")
                return True
        except Exception as e:
            logger.error(f"Errore nell'inizializzazione delle tabelle: {e}")
            return False
            
    def _generate_invite_code(self, length: int = 20) -> str:
        """
        Genera un codice di invito univoco
        
        Args:
            length: Lunghezza del codice di invito
            
        Returns:
            str: Codice di invito generato
        """
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
            
    async def create_invite(self, channel_id: int, invited_by: int, email: str, 
                          permissions: Dict[str, bool]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Crea un nuovo invito per un moderatore
        
        Args:
            channel_id: ID del canale
            invited_by: ID dell'utente che ha creato l'invito
            email: Email del moderatore invitato
            permissions: Permessi da assegnare al moderatore
            
        Returns:
            Tuple[bool, Optional[str], Optional[str]]: (Successo, Codice invito, Errore)
        """
        if not self.db_pool:
            return False, None, "Nessun pool di database disponibile"
            
        try:
            async with self.db_pool.acquire() as conn:
                # Verifica che l'utente che fa l'invito sia il proprietario del canale
                is_owner = await conn.fetchval(
                    'SELECT COUNT(*) FROM channels WHERE id = $1 AND owner_id = $2',
                    channel_id, invited_by
                )
                
                if not is_owner:
                    # Verifica se l'utente è un moderatore con permessi per invitare altri moderatori
                    can_invite = await conn.fetchval(
                        '''
                        SELECT (permissions->>'can_invite_moderators')::boolean 
                        FROM channel_moderators 
                        WHERE channel_id = $1 AND user_id = $2 AND status = 'active'
                        ''',
                        channel_id, invited_by
                    )
                    
                    if not can_invite:
                        return False, None, "Non hai i permessi per invitare moderatori"
                
                # Genera un codice di invito univoco
                invite_code = self._generate_invite_code()
                
                # Data di scadenza dell'invito
                expires_at = datetime.now() + timedelta(days=self.invite_expiry_days)
                
                # Verifica se esiste già un invito pendente per questa email su questo canale
                existing_invite = await conn.fetchrow(
                    '''
                    SELECT id, invite_code, status FROM moderator_invites 
                    WHERE channel_id = $1 AND email = $2 AND status = 'pending' AND expires_at > NOW()
                    ''',
                    channel_id, email
                )
                
                if existing_invite:
                    # Restituisci il codice esistente
                    return True, existing_invite['invite_code'], None
                
                # Crea un nuovo invito
                await conn.execute(
                    '''
                    INSERT INTO moderator_invites 
                    (channel_id, invited_by, invite_code, email, permissions, expires_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ''',
                    channel_id, invited_by, invite_code, email.lower(), json.dumps(permissions), expires_at
                )
                
                logger.info(f"Nuovo invito moderatore creato per il canale {channel_id}, email: {email}")
                return True, invite_code, None
                
        except Exception as e:
            logger.error(f"Errore nella creazione dell'invito: {e}")
            return False, None, f"Errore interno: {str(e)}"
            
    async def get_invite_details(self, invite_code: str) -> Optional[Dict[str, Any]]:
        """
        Ottiene i dettagli di un invito
        
        Args:
            invite_code: Codice di invito
            
        Returns:
            Dict[str, Any] | None: Dettagli dell'invito o None se non trovato
        """
        if not self.db_pool:
            return None
            
        try:
            async with self.db_pool.acquire() as conn:
                invite = await conn.fetchrow(
                    '''
                    SELECT i.*, c.name as channel_name, u.username as invited_by_username
                    FROM moderator_invites i
                    JOIN channels c ON i.channel_id = c.id
                    JOIN users u ON i.invited_by = u.id
                    WHERE i.invite_code = $1
                    ''',
                    invite_code
                )
                
                if not invite:
                    return None
                    
                # Converti in dizionario
                invite_dict = dict(invite)
                
                # Converti le date in stringhe per la serializzazione JSON
                for key in ['created_at', 'expires_at']:
                    if key in invite_dict and invite_dict[key]:
                        invite_dict[key] = invite_dict[key].isoformat()
                        
                # Carica il JSON delle permissions
                if 'permissions' in invite_dict and invite_dict['permissions']:
                    invite_dict['permissions'] = json.loads(invite_dict['permissions'])
                    
                return invite_dict
                
        except Exception as e:
            logger.error(f"Errore nell'ottenere i dettagli dell'invito: {e}")
            return None
            
    async def accept_invite(self, invite_code: str, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Accetta un invito e aggiunge l'utente come moderatore del canale
        
        Args:
            invite_code: Codice di invito
            user_id: ID dell'utente che accetta l'invito
            
        Returns:
            Tuple[bool, Optional[str]]: (Successo, Errore)
        """
        if not self.db_pool:
            return False, "Nessun pool di database disponibile"
            
        try:
            async with self.db_pool.acquire() as conn:
                # Inizia una transazione
                async with conn.transaction():
                    # Ottieni i dettagli dell'invito
                    invite = await conn.fetchrow(
                        '''
                        SELECT * FROM moderator_invites 
                        WHERE invite_code = $1 AND status = 'pending' AND expires_at > NOW()
                        ''',
                        invite_code
                    )
                    
                    if not invite:
                        return False, "Invito non valido o scaduto"
                    
                    # Ottieni l'email dell'utente per verificare che corrisponda all'invito
                    user_email = await conn.fetchval(
                        'SELECT email FROM users WHERE id = $1',
                        user_id
                    )
                    
                    if not user_email or user_email.lower() != invite['email'].lower():
                        return False, "L'email dell'utente non corrisponde a quella dell'invito"
                    
                    # Verifica se l'utente è già un moderatore di questo canale
                    existing_mod = await conn.fetchval(
                        '''
                        SELECT id FROM channel_moderators 
                        WHERE channel_id = $1 AND user_id = $2
                        ''',
                        invite['channel_id'], user_id
                    )
                    
                    if existing_mod:
                        # Aggiorna lo stato del moderatore se è inattivo
                        await conn.execute(
                            '''
                            UPDATE channel_moderators 
                            SET permissions = $1, status = 'active', updated_at = NOW(), invite_id = $2
                            WHERE channel_id = $3 AND user_id = $4
                            ''',
                            invite['permissions'], invite['id'], invite['channel_id'], user_id
                        )
                    else:
                        # Aggiungi l'utente come moderatore del canale
                        await conn.execute(
                            '''
                            INSERT INTO channel_moderators 
                            (channel_id, user_id, permissions, invite_id)
                            VALUES ($1, $2, $3, $4)
                            ''',
                            invite['channel_id'], user_id, invite['permissions'], invite['id']
                        )
                    
                    # Aggiorna lo stato dell'invito
                    await conn.execute(
                        '''
                        UPDATE moderator_invites 
                        SET status = 'accepted'
                        WHERE id = $1
                        ''',
                        invite['id']
                    )
                    
                    logger.info(f"Invito {invite_code} accettato dall'utente {user_id}")
                    return True, None
                    
        except Exception as e:
            logger.error(f"Errore nell'accettazione dell'invito: {e}")
            return False, f"Errore interno: {str(e)}"
            
    async def decline_invite(self, invite_code: str, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Rifiuta un invito
        
        Args:
            invite_code: Codice di invito
            user_id: ID dell'utente che rifiuta l'invito
            
        Returns:
            Tuple[bool, Optional[str]]: (Successo, Errore)
        """
        if not self.db_pool:
            return False, "Nessun pool di database disponibile"
            
        try:
            async with self.db_pool.acquire() as conn:
                # Ottieni i dettagli dell'invito
                invite = await conn.fetchrow(
                    '''
                    SELECT * FROM moderator_invites 
                    WHERE invite_code = $1 AND status = 'pending' AND expires_at > NOW()
                    ''',
                    invite_code
                )
                
                if not invite:
                    return False, "Invito non valido o scaduto"
                
                # Ottieni l'email dell'utente per verificare che corrisponda all'invito
                user_email = await conn.fetchval(
                    'SELECT email FROM users WHERE id = $1',
                    user_id
                )
                
                if not user_email or user_email.lower() != invite['email'].lower():
                    return False, "L'email dell'utente non corrisponde a quella dell'invito"
                
                # Aggiorna lo stato dell'invito
                await conn.execute(
                    '''
                    UPDATE moderator_invites 
                    SET status = 'declined'
                    WHERE id = $1
                    ''',
                    invite['id']
                )
                
                logger.info(f"Invito {invite_code} rifiutato dall'utente {user_id}")
                return True, None
                
        except Exception as e:
            logger.error(f"Errore nel rifiuto dell'invito: {e}")
            return False, f"Errore interno: {str(e)}"
            
    async def revoke_invite(self, invite_code: str, user_id: int) -> Tuple[bool, Optional[str]]:
        """
        Revoca un invito pendente
        
        Args:
            invite_code: Codice di invito
            user_id: ID dell'utente che revoca l'invito (deve essere il creatore o il proprietario del canale)
            
        Returns:
            Tuple[bool, Optional[str]]: (Successo, Errore)
        """
        if not self.db_pool:
            return False, "Nessun pool di database disponibile"
            
        try:
            async with self.db_pool.acquire() as conn:
                # Ottieni i dettagli dell'invito
                invite = await conn.fetchrow(
                    '''
                    SELECT i.*, c.owner_id
                    FROM moderator_invites i
                    JOIN channels c ON i.channel_id = c.id
                    WHERE i.invite_code = $1 AND i.status = 'pending'
                    ''',
                    invite_code
                )
                
                if not invite:
                    return False, "Invito non valido o già utilizzato"
                
                # Verifica che l'utente abbia i permessi per revocare l'invito
                if invite['invited_by'] != user_id and invite['owner_id'] != user_id:
                    # Verifica se l'utente è un moderatore con permessi per invitare altri moderatori
                    can_invite = await conn.fetchval(
                        '''
                        SELECT (permissions->>'can_invite_moderators')::boolean 
                        FROM channel_moderators 
                        WHERE channel_id = $1 AND user_id = $2 AND status = 'active'
                        ''',
                        invite['channel_id'], user_id
                    )
                    
                    if not can_invite:
                        return False, "Non hai i permessi per revocare questo invito"
                
                # Aggiorna lo stato dell'invito
                await conn.execute(
                    '''
                    UPDATE moderator_invites 
                    SET status = 'revoked'
                    WHERE id = $1
                    ''',
                    invite['id']
                )
                
                logger.info(f"Invito {invite_code} revocato dall'utente {user_id}")
                return True, None
                
        except Exception as e:
            logger.error(f"Errore nella revoca dell'invito: {e}")
            return False, f"Errore interno: {str(e)}"
            
    async def list_channel_invites(self, channel_id: int, user_id: int, status: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Elenca gli inviti di un canale
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente che richiede la lista (deve essere il proprietario o un moderatore del canale)
            status: Stato degli inviti da filtrare (pending, accepted, declined, expired, revoked)
            
        Returns:
            Tuple[List[Dict[str, Any]], Optional[str]]: (Lista inviti, Errore)
        """
        if not self.db_pool:
            return [], "Nessun pool di database disponibile"
            
        try:
            async with self.db_pool.acquire() as conn:
                # Verifica che l'utente abbia i permessi per vedere gli inviti
                is_owner = await conn.fetchval(
                    'SELECT COUNT(*) FROM channels WHERE id = $1 AND owner_id = $2',
                    channel_id, user_id
                )
                
                if not is_owner:
                    # Verifica se l'utente è un moderatore con permessi per gestire gli inviti
                    can_manage = await conn.fetchval(
                        '''
                        SELECT (permissions->>'can_invite_moderators')::boolean OR (permissions->>'can_manage_moderators')::boolean
                        FROM channel_moderators 
                        WHERE channel_id = $1 AND user_id = $2 AND status = 'active'
                        ''',
                        channel_id, user_id
                    )
                    
                    if not can_manage:
                        return [], "Non hai i permessi per vedere gli inviti di questo canale"
                
                # Costruisci la query in base allo stato richiesto
                query = '''
                SELECT i.*, u.username as invited_by_username
                FROM moderator_invites i
                JOIN users u ON i.invited_by = u.id
                WHERE i.channel_id = $1
                '''
                params = [channel_id]
                
                if status:
                    query += " AND i.status = $2"
                    params.append(status)
                
                query += " ORDER BY i.created_at DESC"
                
                # Esegui la query
                rows = await conn.fetch(query, *params)
                
                # Converti i risultati in dizionari
                invites = []
                for row in rows:
                    invite_dict = dict(row)
                    
                    # Converti le date in stringhe per la serializzazione JSON
                    for key in ['created_at', 'expires_at']:
                        if key in invite_dict and invite_dict[key]:
                            invite_dict[key] = invite_dict[key].isoformat()
                            
                    # Carica il JSON delle permissions
                    if 'permissions' in invite_dict and invite_dict['permissions']:
                        invite_dict['permissions'] = json.loads(invite_dict['permissions'])
                        
                    invites.append(invite_dict)
                    
                return invites, None
                
        except Exception as e:
            logger.error(f"Errore nell'elenco degli inviti: {e}")
            return [], f"Errore interno: {str(e)}"
            
    async def list_channel_moderators(self, channel_id: int, user_id: int) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Elenca i moderatori di un canale
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente che richiede la lista (deve essere il proprietario o un moderatore del canale)
            
        Returns:
            Tuple[List[Dict[str, Any]], Optional[str]]: (Lista moderatori, Errore)
        """
        if not self.db_pool:
            return [], "Nessun pool di database disponibile"
            
        try:
            async with self.db_pool.acquire() as conn:
                # Verifica che l'utente abbia i permessi per vedere i moderatori
                is_owner = await conn.fetchval(
                    'SELECT COUNT(*) FROM channels WHERE id = $1 AND owner_id = $2',
                    channel_id, user_id
                )
                
                # Ottieni i dettagli del canale
                channel = await conn.fetchrow(
                    'SELECT owner_id, name FROM channels WHERE id = $1',
                    channel_id
                )
                
                if not channel:
                    return [], "Canale non trovato"
                
                if not is_owner:
                    # Verifica se l'utente è un moderatore attivo del canale
                    is_mod = await conn.fetchval(
                        '''
                        SELECT COUNT(*) FROM channel_moderators 
                        WHERE channel_id = $1 AND user_id = $2 AND status = 'active'
                        ''',
                        channel_id, user_id
                    )
                    
                    if not is_mod:
                        return [], "Non hai i permessi per vedere i moderatori di questo canale"
                
                # Ottieni la lista dei moderatori
                rows = await conn.fetch(
                    '''
                    SELECT m.*, u.username, u.email, 
                           CASE WHEN u.id = $2 THEN TRUE ELSE FALSE END as is_self,
                           CASE WHEN u.id = c.owner_id THEN TRUE ELSE FALSE END as is_owner
                    FROM channel_moderators m
                    JOIN users u ON m.user_id = u.id
                    JOIN channels c ON m.channel_id = c.id
                    WHERE m.channel_id = $1
                    ORDER BY is_owner DESC, m.created_at ASC
                    ''',
                    channel_id, channel['owner_id']
                )
                
                # Converti i risultati in dizionari
                moderators = []
                for row in rows:
                    mod_dict = dict(row)
                    
                    # Converti le date in stringhe per la serializzazione JSON
                    for key in ['created_at', 'updated_at']:
                        if key in mod_dict and mod_dict[key]:
                            mod_dict[key] = mod_dict[key].isoformat()
                            
                    # Carica il JSON delle permissions
                    if 'permissions' in mod_dict and mod_dict['permissions']:
                        mod_dict['permissions'] = json.loads(mod_dict['permissions'])
                        
                    # Aggiungi il nome del canale
                    mod_dict['channel_name'] = channel['name']
                        
                    moderators.append(mod_dict)
                    
                return moderators, None
                
        except Exception as e:
            logger.error(f"Errore nell'elenco dei moderatori: {e}")
            return [], f"Errore interno: {str(e)}"
            
    async def update_moderator_permissions(self, channel_id: int, user_id: int, 
                                        moderator_id: int, permissions: Dict[str, bool]) -> Tuple[bool, Optional[str]]:
        """
        Aggiorna i permessi di un moderatore
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente che aggiorna i permessi (deve essere il proprietario del canale)
            moderator_id: ID del moderatore da aggiornare
            permissions: Nuovi permessi da assegnare al moderatore
            
        Returns:
            Tuple[bool, Optional[str]]: (Successo, Errore)
        """
        if not self.db_pool:
            return False, "Nessun pool di database disponibile"
            
        try:
            async with self.db_pool.acquire() as conn:
                # Verifica che l'utente abbia i permessi per aggiornare i moderatori
                is_owner = await conn.fetchval(
                    'SELECT COUNT(*) FROM channels WHERE id = $1 AND owner_id = $2',
                    channel_id, user_id
                )
                
                if not is_owner:
                    # Verifica se l'utente è un moderatore con permessi per gestire altri moderatori
                    can_manage = await conn.fetchval(
                        '''
                        SELECT (permissions->>'can_manage_moderators')::boolean 
                        FROM channel_moderators 
                        WHERE channel_id = $1 AND user_id = $2 AND status = 'active'
                        ''',
                        channel_id, user_id
                    )
                    
                    if not can_manage:
                        return False, "Non hai i permessi per aggiornare i moderatori di questo canale"
                
                # Verifica che il moderatore esista
                moderator = await conn.fetchrow(
                    '''
                    SELECT * FROM channel_moderators 
                    WHERE channel_id = $1 AND user_id = $2
                    ''',
                    channel_id, moderator_id
                )
                
                if not moderator:
                    return False, "Moderatore non trovato"
                
                # Non permettere di aggiornare il proprietario del canale
                is_target_owner = await conn.fetchval(
                    'SELECT COUNT(*) FROM channels WHERE id = $1 AND owner_id = $2',
                    channel_id, moderator_id
                )
                
                if is_target_owner:
                    return False, "Non puoi modificare i permessi del proprietario del canale"
                
                # Non permettere a un moderatore di aggiornare un altro moderatore con più permessi
                if not is_owner and user_id != moderator_id:
                    # Ottieni i permessi di chi fa l'aggiornamento
                    updater_permissions = await conn.fetchval(
                        '''
                        SELECT permissions
                        FROM channel_moderators 
                        WHERE channel_id = $1 AND user_id = $2
                        ''',
                        channel_id, user_id
                    )
                    
                    updater_permissions = json.loads(updater_permissions)
                    target_permissions = json.loads(moderator['permissions'])
                    
                    # Un moderatore non può aumentare i permessi di un altro moderatore
                    # oltre i propri permessi
                    for key, value in permissions.items():
                        if value and (key not in updater_permissions or not updater_permissions[key]):
                            return False, f"Non puoi assegnare il permesso '{key}' che non possiedi"
                
                # Aggiorna i permessi del moderatore
                await conn.execute(
                    '''
                    UPDATE channel_moderators 
                    SET permissions = $1, updated_at = NOW()
                    WHERE channel_id = $2 AND user_id = $3
                    ''',
                    json.dumps(permissions), channel_id, moderator_id
                )
                
                logger.info(f"Permessi del moderatore {moderator_id} aggiornati dall'utente {user_id}")
                return True, None
                
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento dei permessi del moderatore: {e}")
            return False, f"Errore interno: {str(e)}"
            
    async def remove_moderator(self, channel_id: int, user_id: int, moderator_id: int) -> Tuple[bool, Optional[str]]:
        """
        Rimuove un moderatore dal canale
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente che rimuove il moderatore (deve essere il proprietario del canale)
            moderator_id: ID del moderatore da rimuovere
            
        Returns:
            Tuple[bool, Optional[str]]: (Successo, Errore)
        """
        if not self.db_pool:
            return False, "Nessun pool di database disponibile"
            
        try:
            async with self.db_pool.acquire() as conn:
                # Verifica che l'utente abbia i permessi per rimuovere i moderatori
                is_owner = await conn.fetchval(
                    'SELECT COUNT(*) FROM channels WHERE id = $1 AND owner_id = $2',
                    channel_id, user_id
                )
                
                if not is_owner:
                    # Verifica se l'utente è un moderatore con permessi per gestire altri moderatori
                    can_manage = await conn.fetchval(
                        '''
                        SELECT (permissions->>'can_manage_moderators')::boolean 
                        FROM channel_moderators 
                        WHERE channel_id = $1 AND user_id = $2 AND status = 'active'
                        ''',
                        channel_id, user_id
                    )
                    
                    if not can_manage and user_id != moderator_id:
                        return False, "Non hai i permessi per rimuovere i moderatori di questo canale"
                
                # Verifica che il moderatore esista
                moderator = await conn.fetchrow(
                    '''
                    SELECT * FROM channel_moderators 
                    WHERE channel_id = $1 AND user_id = $2
                    ''',
                    channel_id, moderator_id
                )
                
                if not moderator:
                    return False, "Moderatore non trovato"
                
                # Non permettere di rimuovere il proprietario del canale
                is_target_owner = await conn.fetchval(
                    'SELECT COUNT(*) FROM channels WHERE id = $1 AND owner_id = $2',
                    channel_id, moderator_id
                )
                
                if is_target_owner:
                    return False, "Non puoi rimuovere il proprietario del canale"
                
                # Rimuovi il moderatore
                await conn.execute(
                    '''
                    DELETE FROM channel_moderators 
                    WHERE channel_id = $1 AND user_id = $2
                    ''',
                    channel_id, moderator_id
                )
                
                logger.info(f"Moderatore {moderator_id} rimosso dal canale {channel_id} dall'utente {user_id}")
                return True, None
                
        except Exception as e:
            logger.error(f"Errore nella rimozione del moderatore: {e}")
            return False, f"Errore interno: {str(e)}"
            
    async def cleanup_expired_invites(self) -> int:
        """
        Aggiorna lo stato degli inviti scaduti
        
        Returns:
            int: Numero di inviti aggiornati
        """
        if not self.db_pool:
            return 0
            
        try:
            async with self.db_pool.acquire() as conn:
                # Aggiorna gli inviti scaduti
                result = await conn.execute(
                    '''
                    UPDATE moderator_invites 
                    SET status = 'expired'
                    WHERE status = 'pending' AND expires_at < NOW()
                    '''
                )
                
                # Estrai il numero di righe aggiornate
                updated = int(result.split(" ")[1])
                
                if updated > 0:
                    logger.info(f"Aggiornati {updated} inviti scaduti")
                    
                return updated
                
        except Exception as e:
            logger.error(f"Errore nella pulizia degli inviti scaduti: {e}")
            return 0
            
    async def get_user_invites(self, email: str) -> List[Dict[str, Any]]:
        """
        Ottiene tutti gli inviti pendenti per un utente
        
        Args:
            email: Email dell'utente
            
        Returns:
            List[Dict[str, Any]]: Lista degli inviti pendenti
        """
        if not self.db_pool:
            return []
            
        try:
            async with self.db_pool.acquire() as conn:
                # Aggiorna prima gli inviti scaduti
                await self.cleanup_expired_invites()
                
                # Ottieni gli inviti pendenti
                rows = await conn.fetch(
                    '''
                    SELECT i.*, c.name as channel_name, u.username as invited_by_username
                    FROM moderator_invites i
                    JOIN channels c ON i.channel_id = c.id
                    JOIN users u ON i.invited_by = u.id
                    WHERE i.email = $1 AND i.status = 'pending' AND i.expires_at > NOW()
                    ORDER BY i.created_at DESC
                    ''',
                    email.lower()
                )
                
                # Converti i risultati in dizionari
                invites = []
                for row in rows:
                    invite_dict = dict(row)
                    
                    # Converti le date in stringhe per la serializzazione JSON
                    for key in ['created_at', 'expires_at']:
                        if key in invite_dict and invite_dict[key]:
                            invite_dict[key] = invite_dict[key].isoformat()
                            
                    # Carica il JSON delle permissions
                    if 'permissions' in invite_dict and invite_dict['permissions']:
                        invite_dict['permissions'] = json.loads(invite_dict['permissions'])
                        
                    invites.append(invite_dict)
                    
                return invites
                
        except Exception as e:
            logger.error(f"Errore nell'ottenere gli inviti dell'utente: {e}")
            return []
            
    async def get_user_moderated_channels(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Ottiene tutti i canali moderati da un utente
        
        Args:
            user_id: ID dell'utente
            
        Returns:
            List[Dict[str, Any]]: Lista dei canali moderati
        """
        if not self.db_pool:
            return []
            
        try:
            async with self.db_pool.acquire() as conn:
                # Ottieni i canali moderati
                rows = await conn.fetch(
                    '''
                    SELECT m.*, c.name as channel_name, u.username as owner_username
                    FROM channel_moderators m
                    JOIN channels c ON m.channel_id = c.id
                    JOIN users u ON c.owner_id = u.id
                    WHERE m.user_id = $1 AND m.status = 'active'
                    ORDER BY m.created_at DESC
                    ''',
                    user_id
                )
                
                # Converti i risultati in dizionari
                channels = []
                for row in rows:
                    channel_dict = dict(row)
                    
                    # Converti le date in stringhe per la serializzazione JSON
                    for key in ['created_at', 'updated_at']:
                        if key in channel_dict and channel_dict[key]:
                            channel_dict[key] = channel_dict[key].isoformat()
                            
                    # Carica il JSON delle permissions
                    if 'permissions' in channel_dict and channel_dict['permissions']:
                        channel_dict['permissions'] = json.loads(channel_dict['permissions'])
                        
                    channels.append(channel_dict)
                    
                return channels
                
        except Exception as e:
            logger.error(f"Errore nell'ottenere i canali moderati dall'utente: {e}")
            return []

# Singleton per gestire gli inviti ai moderatori
_invite_manager = None

def get_invite_manager(db_pool):
    """
    Ottiene l'istanza del gestore degli inviti
    
    Args:
        db_pool: Pool di connessioni al database
        
    Returns:
        ModeratorInviteManager: Istanza del gestore degli inviti
    """
    global _invite_manager
    if _invite_manager is None:
        _invite_manager = ModeratorInviteManager(db_pool)
    return _invite_manager 