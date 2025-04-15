"""
Modulo per la gestione degli utenti nel pannello di amministrazione.
Implementa le funzionalità di gestione utenti, ruoli e permessi.
"""

import os
import datetime
import logging
import secrets
import json
import base64
import hashlib
from typing import Dict, List, Optional, Tuple, Union, Any

import asyncpg
import aioredis
import bcrypt
from quart import current_app, g

logger = logging.getLogger('user_management')

class UserManager:
    """Gestisce gli utenti, i ruoli e i permessi."""
    
    def __init__(self, db_pool: asyncpg.Pool, redis_pool: aioredis.ConnectionPool):
        self.db_pool = db_pool
        self.redis_pool = redis_pool
        self.permissions_cache = {}
        self.roles_cache = {}
        self.cache_ttl = 3600  # 1 ora
    
    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Ottiene un utente tramite il suo ID."""
        try:
            async with self.db_pool.acquire() as conn:
                user = await conn.fetchrow("""
                    SELECT u.id, u.username, u.email, u.first_name, u.last_name, 
                           u.is_active, u.created_at, u.updated_at, u.last_login,
                           u.is_superuser, u.is_system, u.failed_login_attempts,
                           u.failed_login_timestamp
                    FROM users u
                    WHERE u.id = $1
                """, user_id)
                
                if not user:
                    return None
                
                user_data = dict(user)
                
                # Ottieni i ruoli dell'utente
                roles = await conn.fetch("""
                    SELECT r.id, r.name, r.description
                    FROM roles r
                    JOIN user_roles ur ON r.id = ur.role_id
                    WHERE ur.user_id = $1
                """, user_id)
                
                user_data['roles'] = [dict(role) for role in roles]
                
                # Ottieni i permessi diretti dell'utente
                permissions = await conn.fetch("""
                    SELECT p.id, p.name, p.description
                    FROM permissions p
                    JOIN user_permissions up ON p.id = up.permission_id
                    WHERE up.user_id = $1
                """, user_id)
                
                user_data['permissions'] = [dict(perm) for perm in permissions]
                
                return user_data
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dell'utente {user_id}: {e}")
            return None
    
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Ottiene un utente tramite il suo nome utente."""
        try:
            async with self.db_pool.acquire() as conn:
                user = await conn.fetchrow("""
                    SELECT id FROM users
                    WHERE username = $1
                """, username)
                
                if not user:
                    return None
                
                return await self.get_user_by_id(user['id'])
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dell'utente {username}: {e}")
            return None
    
    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Ottiene un utente tramite la sua email."""
        try:
            async with self.db_pool.acquire() as conn:
                user = await conn.fetchrow("""
                    SELECT id FROM users
                    WHERE email = $1
                """, email)
                
                if not user:
                    return None
                
                return await self.get_user_by_id(user['id'])
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dell'utente con email {email}: {e}")
            return None
    
    async def get_users(self, limit: int = 100, offset: int = 0, 
                       search: str = None, active_only: bool = True) -> List[Dict[str, Any]]:
        """Ottiene un elenco di utenti."""
        try:
            query = """
                SELECT u.id, u.username, u.email, u.first_name, u.last_name, 
                       u.is_active, u.created_at, u.last_login,
                       u.is_superuser, u.is_system
                FROM users u
                WHERE 1=1
            """
            
            params = []
            param_idx = 1
            
            if active_only:
                query += f" AND u.is_active = ${param_idx}"
                params.append(True)
                param_idx += 1
            
            if search:
                query += f" AND (u.username ILIKE ${param_idx} OR u.email ILIKE ${param_idx} OR " \
                         f"u.first_name ILIKE ${param_idx} OR u.last_name ILIKE ${param_idx})"
                params.append(f'%{search}%')
                param_idx += 1
            
            query += " ORDER BY u.username LIMIT $" + str(param_idx) + " OFFSET $" + str(param_idx + 1)
            params.extend([limit, offset])
            
            async with self.db_pool.acquire() as conn:
                users = await conn.fetch(query, *params)
                
                result = []
                for user in users:
                    user_data = dict(user)
                    
                    # Ottieni i ruoli dell'utente
                    roles = await conn.fetch("""
                        SELECT r.id, r.name
                        FROM roles r
                        JOIN user_roles ur ON r.id = ur.role_id
                        WHERE ur.user_id = $1
                    """, user['id'])
                    
                    user_data['roles'] = [{'id': role['id'], 'name': role['name']} for role in roles]
                    result.append(user_data)
                
                return result
        except Exception as e:
            logger.error(f"Errore nell'ottenimento degli utenti: {e}")
            return []
    
    async def count_users(self, search: str = None, active_only: bool = True) -> int:
        """Conta il numero totale di utenti che corrispondono ai criteri."""
        try:
            query = """
                SELECT COUNT(*) FROM users u
                WHERE 1=1
            """
            
            params = []
            param_idx = 1
            
            if active_only:
                query += f" AND u.is_active = ${param_idx}"
                params.append(True)
                param_idx += 1
            
            if search:
                query += f" AND (u.username ILIKE ${param_idx} OR u.email ILIKE ${param_idx} OR " \
                         f"u.first_name ILIKE ${param_idx} OR u.last_name ILIKE ${param_idx})"
                params.append(f'%{search}%')
                param_idx += 1
            
            async with self.db_pool.acquire() as conn:
                count = await conn.fetchval(query, *params)
                return count
        except Exception as e:
            logger.error(f"Errore nel conteggio degli utenti: {e}")
            return 0
    
    async def create_user(self, user_data: Dict[str, Any], password: str = None) -> Optional[int]:
        """Crea un nuovo utente."""
        try:
            required_fields = ['username', 'email']
            for field in required_fields:
                if field not in user_data:
                    logger.error(f"Campo obbligatorio mancante: {field}")
                    return None
            
            # Genera una password casuale se non fornita
            if not password:
                password = secrets.token_urlsafe(12)
            
            # Hash della password
            password_hash = self._hash_password(password)
            
            async with self.db_pool.acquire() as conn:
                # Verifica se l'utente esiste già
                existing_user = await conn.fetchrow("""
                    SELECT id FROM users
                    WHERE username = $1 OR email = $2
                """, user_data.get('username'), user_data.get('email'))
                
                if existing_user:
                    logger.error(f"Un utente con lo stesso username o email esiste già")
                    return None
                
                # Crea l'utente
                user_id = await conn.fetchval("""
                    INSERT INTO users (
                        username, email, first_name, last_name, password_hash,
                        is_active, is_superuser, is_system
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                """, user_data.get('username'), user_data.get('email'),
                   user_data.get('first_name', ''), user_data.get('last_name', ''),
                   password_hash, user_data.get('is_active', True),
                   user_data.get('is_superuser', False), user_data.get('is_system', False))
                
                # Assegna i ruoli se specificati
                if 'roles' in user_data and user_data['roles']:
                    for role_id in user_data['roles']:
                        await conn.execute("""
                            INSERT INTO user_roles (user_id, role_id)
                            VALUES ($1, $2)
                        """, user_id, role_id)
                
                # Assegna i permessi diretti se specificati
                if 'permissions' in user_data and user_data['permissions']:
                    for perm_id in user_data['permissions']:
                        await conn.execute("""
                            INSERT INTO user_permissions (user_id, permission_id)
                            VALUES ($1, $2)
                        """, user_id, perm_id)
                
                # Invalida la cache dei permessi
                await self._invalidate_permissions_cache(user_id)
                
                return user_id
        except Exception as e:
            logger.error(f"Errore nella creazione dell'utente: {e}")
            return None
    
    async def update_user(self, user_id: int, user_data: Dict[str, Any]) -> bool:
        """Aggiorna un utente esistente."""
        try:
            # Prepara i campi da aggiornare
            fields_to_update = []
            params = []
            param_idx = 1
            
            updatable_fields = [
                'email', 'first_name', 'last_name', 'is_active',
                'is_superuser', 'is_system'
            ]
            
            for field in updatable_fields:
                if field in user_data:
                    fields_to_update.append(f"{field} = ${param_idx}")
                    params.append(user_data[field])
                    param_idx += 1
            
            # Se non ci sono campi da aggiornare, esci
            if not fields_to_update:
                return True
            
            fields_str = ", ".join(fields_to_update)
            fields_str += f", updated_at = ${param_idx}"
            params.append(datetime.datetime.now())
            param_idx += 1
            
            params.append(user_id)  # Per la condizione WHERE
            
            async with self.db_pool.acquire() as conn:
                # Aggiorna l'utente
                await conn.execute(f"""
                    UPDATE users
                    SET {fields_str}
                    WHERE id = ${param_idx}
                """, *params)
                
                # Aggiorna i ruoli se specificati
                if 'roles' in user_data:
                    # Rimuovi tutti i ruoli esistenti
                    await conn.execute("""
                        DELETE FROM user_roles
                        WHERE user_id = $1
                    """, user_id)
                    
                    # Aggiungi i nuovi ruoli
                    for role_id in user_data['roles']:
                        await conn.execute("""
                            INSERT INTO user_roles (user_id, role_id)
                            VALUES ($1, $2)
                        """, user_id, role_id)
                
                # Aggiorna i permessi se specificati
                if 'permissions' in user_data:
                    # Rimuovi tutti i permessi esistenti
                    await conn.execute("""
                        DELETE FROM user_permissions
                        WHERE user_id = $1
                    """, user_id)
                    
                    # Aggiungi i nuovi permessi
                    for perm_id in user_data['permissions']:
                        await conn.execute("""
                            INSERT INTO user_permissions (user_id, permission_id)
                            VALUES ($1, $2)
                        """, user_id, perm_id)
                
                # Invalida la cache dei permessi
                await self._invalidate_permissions_cache(user_id)
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento dell'utente {user_id}: {e}")
            return False
    
    async def delete_user(self, user_id: int) -> bool:
        """Elimina un utente."""
        try:
            async with self.db_pool.acquire() as conn:
                # Verifica se l'utente è di sistema
                is_system = await conn.fetchval("""
                    SELECT is_system FROM users
                    WHERE id = $1
                """, user_id)
                
                if is_system:
                    logger.error(f"Impossibile eliminare l'utente di sistema {user_id}")
                    return False
                
                # Elimina l'utente (con eliminazione a cascata di relazioni)
                await conn.execute("""
                    DELETE FROM users
                    WHERE id = $1
                """, user_id)
                
                # Invalida la cache dei permessi
                await self._invalidate_permissions_cache(user_id)
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'eliminazione dell'utente {user_id}: {e}")
            return False
    
    async def change_password(self, user_id: int, new_password: str) -> bool:
        """Cambia la password di un utente."""
        try:
            password_hash = self._hash_password(new_password)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE users
                    SET password_hash = $1, updated_at = $2,
                        failed_login_attempts = 0, failed_login_timestamp = NULL
                    WHERE id = $3
                """, password_hash, datetime.datetime.now(), user_id)
                
                return True
        except Exception as e:
            logger.error(f"Errore nel cambio password per l'utente {user_id}: {e}")
            return False
    
    async def verify_password(self, user_id: int, password: str) -> bool:
        """Verifica la password di un utente."""
        try:
            async with self.db_pool.acquire() as conn:
                password_hash = await conn.fetchval("""
                    SELECT password_hash FROM users
                    WHERE id = $1
                """, user_id)
                
                if not password_hash:
                    return False
                
                return self._verify_password(password, password_hash)
        except Exception as e:
            logger.error(f"Errore nella verifica della password per l'utente {user_id}: {e}")
            return False
    
    async def authenticate_user(self, username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Autentica un utente e gestisce i tentativi falliti."""
        try:
            async with self.db_pool.acquire() as conn:
                user = await conn.fetchrow("""
                    SELECT id, username, email, password_hash, is_active,
                           failed_login_attempts, failed_login_timestamp
                    FROM users
                    WHERE username = $1 OR email = $1
                """, username)
                
                if not user:
                    return False, None
                
                # Verifica se l'account è bloccato per troppi tentativi
                max_attempts = 5
                lockout_duration = 15  # minuti
                
                if user['failed_login_attempts'] >= max_attempts and user['failed_login_timestamp']:
                    lockout_time = user['failed_login_timestamp'] + datetime.timedelta(minutes=lockout_duration)
                    if datetime.datetime.now() < lockout_time:
                        logger.warning(f"Account bloccato per l'utente {username} - troppi tentativi falliti")
                        return False, None
                
                # Verifica password
                if not self._verify_password(password, user['password_hash']):
                    # Incrementa il contatore dei tentativi falliti
                    await conn.execute("""
                        UPDATE users
                        SET failed_login_attempts = failed_login_attempts + 1,
                            failed_login_timestamp = $1
                        WHERE id = $2
                    """, datetime.datetime.now(), user['id'])
                    
                    return False, None
                
                # Autenticazione riuscita, resetta i tentativi falliti
                await conn.execute("""
                    UPDATE users
                    SET last_login = $1,
                        failed_login_attempts = 0,
                        failed_login_timestamp = NULL
                    WHERE id = $2
                """, datetime.datetime.now(), user['id'])
                
                # Ottieni i dettagli dell'utente
                user_data = await self.get_user_by_id(user['id'])
                
                return True, user_data
        except Exception as e:
            logger.error(f"Errore nell'autenticazione dell'utente {username}: {e}")
            return False, None
    
    async def get_user_permissions(self, user_id: int) -> List[str]:
        """Ottiene tutti i permessi di un utente, inclusi quelli ereditati dai ruoli."""
        # Prova prima dalla cache
        cache_key = f"user:{user_id}:permissions"
        permissions = await self._get_from_cache(cache_key)
        
        if permissions is not None:
            return permissions
        
        try:
            async with self.db_pool.acquire() as conn:
                # Verifica se l'utente è superuser
                is_superuser = await conn.fetchval("""
                    SELECT is_superuser FROM users
                    WHERE id = $1
                """, user_id)
                
                if is_superuser:
                    # I superuser hanno tutti i permessi
                    all_perms = await conn.fetch("SELECT name FROM permissions")
                    permissions = [p['name'] for p in all_perms]
                else:
                    # Ottieni i permessi diretti dell'utente
                    direct_perms = await conn.fetch("""
                        SELECT p.name
                        FROM permissions p
                        JOIN user_permissions up ON p.id = up.permission_id
                        WHERE up.user_id = $1
                    """, user_id)
                    
                    # Ottieni i permessi dai ruoli dell'utente
                    role_perms = await conn.fetch("""
                        SELECT p.name
                        FROM permissions p
                        JOIN role_permissions rp ON p.id = rp.permission_id
                        JOIN user_roles ur ON rp.role_id = ur.role_id
                        WHERE ur.user_id = $1
                    """, user_id)
                    
                    # Combina i permessi
                    permissions = list(set([p['name'] for p in direct_perms] + [p['name'] for p in role_perms]))
                
                # Salva nella cache
                await self._set_in_cache(cache_key, permissions, self.cache_ttl)
                
                return permissions
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dei permessi per l'utente {user_id}: {e}")
            return []
    
    async def check_permission(self, user_id: int, permission: str) -> bool:
        """Verifica se un utente ha un determinato permesso."""
        permissions = await self.get_user_permissions(user_id)
        return permission in permissions
    
    async def get_roles(self) -> List[Dict[str, Any]]:
        """Ottiene tutti i ruoli disponibili."""
        try:
            async with self.db_pool.acquire() as conn:
                roles = await conn.fetch("""
                    SELECT id, name, description, is_system, created_at
                    FROM roles
                    ORDER BY name
                """)
                
                return [dict(role) for role in roles]
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dei ruoli: {e}")
            return []
    
    async def get_role(self, role_id: int) -> Optional[Dict[str, Any]]:
        """Ottiene un ruolo tramite il suo ID."""
        try:
            async with self.db_pool.acquire() as conn:
                role = await conn.fetchrow("""
                    SELECT id, name, description, is_system, created_at, updated_at
                    FROM roles
                    WHERE id = $1
                """, role_id)
                
                if not role:
                    return None
                
                role_data = dict(role)
                
                # Ottieni i permessi associati al ruolo
                permissions = await conn.fetch("""
                    SELECT p.id, p.name, p.description
                    FROM permissions p
                    JOIN role_permissions rp ON p.id = rp.permission_id
                    WHERE rp.role_id = $1
                """, role_id)
                
                role_data['permissions'] = [dict(perm) for perm in permissions]
                
                return role_data
        except Exception as e:
            logger.error(f"Errore nell'ottenimento del ruolo {role_id}: {e}")
            return None
    
    async def create_role(self, role_data: Dict[str, Any]) -> Optional[int]:
        """Crea un nuovo ruolo."""
        try:
            if 'name' not in role_data:
                logger.error("Nome del ruolo mancante")
                return None
            
            async with self.db_pool.acquire() as conn:
                # Verifica se il ruolo esiste già
                existing_role = await conn.fetchval("""
                    SELECT id FROM roles
                    WHERE name = $1
                """, role_data.get('name'))
                
                if existing_role:
                    logger.error(f"Un ruolo con lo stesso nome esiste già")
                    return None
                
                # Crea il ruolo
                role_id = await conn.fetchval("""
                    INSERT INTO roles (name, description, is_system)
                    VALUES ($1, $2, $3)
                    RETURNING id
                """, role_data.get('name'), role_data.get('description', ''),
                   role_data.get('is_system', False))
                
                # Assegna i permessi se specificati
                if 'permissions' in role_data and role_data['permissions']:
                    for perm_id in role_data['permissions']:
                        await conn.execute("""
                            INSERT INTO role_permissions (role_id, permission_id)
                            VALUES ($1, $2)
                        """, role_id, perm_id)
                
                # Invalida la cache dei permessi per tutti gli utenti con questo ruolo
                await self._invalidate_role_permissions(role_id)
                
                return role_id
        except Exception as e:
            logger.error(f"Errore nella creazione del ruolo: {e}")
            return None
    
    async def update_role(self, role_id: int, role_data: Dict[str, Any]) -> bool:
        """Aggiorna un ruolo esistente."""
        try:
            # Prepara i campi da aggiornare
            fields_to_update = []
            params = []
            param_idx = 1
            
            updatable_fields = ['name', 'description', 'is_system']
            
            for field in updatable_fields:
                if field in role_data:
                    fields_to_update.append(f"{field} = ${param_idx}")
                    params.append(role_data[field])
                    param_idx += 1
            
            # Se non ci sono campi da aggiornare, esci
            if not fields_to_update:
                return True
            
            fields_str = ", ".join(fields_to_update)
            fields_str += f", updated_at = ${param_idx}"
            params.append(datetime.datetime.now())
            param_idx += 1
            
            params.append(role_id)  # Per la condizione WHERE
            
            async with self.db_pool.acquire() as conn:
                # Aggiorna il ruolo
                await conn.execute(f"""
                    UPDATE roles
                    SET {fields_str}
                    WHERE id = ${param_idx}
                """, *params)
                
                # Aggiorna i permessi se specificati
                if 'permissions' in role_data:
                    # Rimuovi tutti i permessi esistenti
                    await conn.execute("""
                        DELETE FROM role_permissions
                        WHERE role_id = $1
                    """, role_id)
                    
                    # Aggiungi i nuovi permessi
                    for perm_id in role_data['permissions']:
                        await conn.execute("""
                            INSERT INTO role_permissions (role_id, permission_id)
                            VALUES ($1, $2)
                        """, role_id, perm_id)
                
                # Invalida la cache dei permessi per tutti gli utenti con questo ruolo
                await self._invalidate_role_permissions(role_id)
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento del ruolo {role_id}: {e}")
            return False
    
    async def delete_role(self, role_id: int) -> bool:
        """Elimina un ruolo."""
        try:
            async with self.db_pool.acquire() as conn:
                # Verifica se il ruolo è di sistema
                is_system = await conn.fetchval("""
                    SELECT is_system FROM roles
                    WHERE id = $1
                """, role_id)
                
                if is_system:
                    logger.error(f"Impossibile eliminare il ruolo di sistema {role_id}")
                    return False
                
                # Ottieni gli utenti con questo ruolo per invalidare la cache
                users = await conn.fetch("""
                    SELECT user_id FROM user_roles
                    WHERE role_id = $1
                """, role_id)
                
                # Elimina il ruolo (con eliminazione a cascata di relazioni)
                await conn.execute("""
                    DELETE FROM roles
                    WHERE id = $1
                """, role_id)
                
                # Invalida la cache dei permessi per tutti gli utenti con questo ruolo
                for user in users:
                    await self._invalidate_permissions_cache(user['user_id'])
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'eliminazione del ruolo {role_id}: {e}")
            return False
    
    async def get_permissions(self) -> List[Dict[str, Any]]:
        """Ottiene tutti i permessi disponibili."""
        try:
            async with self.db_pool.acquire() as conn:
                permissions = await conn.fetch("""
                    SELECT id, name, description, category, created_at
                    FROM permissions
                    ORDER BY category, name
                """)
                
                return [dict(perm) for perm in permissions]
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dei permessi: {e}")
            return []
    
    async def get_permission(self, permission_id: int) -> Optional[Dict[str, Any]]:
        """Ottiene un permesso tramite il suo ID."""
        try:
            async with self.db_pool.acquire() as conn:
                permission = await conn.fetchrow("""
                    SELECT id, name, description, category, created_at, updated_at
                    FROM permissions
                    WHERE id = $1
                """, permission_id)
                
                if not permission:
                    return None
                
                return dict(permission)
        except Exception as e:
            logger.error(f"Errore nell'ottenimento del permesso {permission_id}: {e}")
            return None
    
    async def create_permission(self, perm_data: Dict[str, Any]) -> Optional[int]:
        """Crea un nuovo permesso."""
        try:
            if 'name' not in perm_data:
                logger.error("Nome del permesso mancante")
                return None
            
            async with self.db_pool.acquire() as conn:
                # Verifica se il permesso esiste già
                existing_perm = await conn.fetchval("""
                    SELECT id FROM permissions
                    WHERE name = $1
                """, perm_data.get('name'))
                
                if existing_perm:
                    logger.error(f"Un permesso con lo stesso nome esiste già")
                    return None
                
                # Crea il permesso
                perm_id = await conn.fetchval("""
                    INSERT INTO permissions (name, description, category)
                    VALUES ($1, $2, $3)
                    RETURNING id
                """, perm_data.get('name'), perm_data.get('description', ''),
                   perm_data.get('category', 'general'))
                
                return perm_id
        except Exception as e:
            logger.error(f"Errore nella creazione del permesso: {e}")
            return None
    
    async def update_permission(self, perm_id: int, perm_data: Dict[str, Any]) -> bool:
        """Aggiorna un permesso esistente."""
        try:
            # Prepara i campi da aggiornare
            fields_to_update = []
            params = []
            param_idx = 1
            
            updatable_fields = ['name', 'description', 'category']
            
            for field in updatable_fields:
                if field in perm_data:
                    fields_to_update.append(f"{field} = ${param_idx}")
                    params.append(perm_data[field])
                    param_idx += 1
            
            # Se non ci sono campi da aggiornare, esci
            if not fields_to_update:
                return True
            
            fields_str = ", ".join(fields_to_update)
            fields_str += f", updated_at = ${param_idx}"
            params.append(datetime.datetime.now())
            param_idx += 1
            
            params.append(perm_id)  # Per la condizione WHERE
            
            async with self.db_pool.acquire() as conn:
                # Aggiorna il permesso
                await conn.execute(f"""
                    UPDATE permissions
                    SET {fields_str}
                    WHERE id = ${param_idx}
                """, *params)
                
                # Invalida la cache dei permessi per tutti gli utenti
                await self._invalidate_all_permissions_cache()
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento del permesso {perm_id}: {e}")
            return False
    
    async def delete_permission(self, perm_id: int) -> bool:
        """Elimina un permesso."""
        try:
            async with self.db_pool.acquire() as conn:
                # Elimina il permesso (con eliminazione a cascata di relazioni)
                await conn.execute("""
                    DELETE FROM permissions
                    WHERE id = $1
                """, perm_id)
                
                # Invalida la cache dei permessi per tutti gli utenti
                await self._invalidate_all_permissions_cache()
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'eliminazione del permesso {perm_id}: {e}")
            return False
    
    async def get_user_activity(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Ottiene la cronologia delle attività di un utente."""
        try:
            async with self.db_pool.acquire() as conn:
                activities = await conn.fetch("""
                    SELECT id, action, details, ip_address, user_agent, timestamp
                    FROM user_activity_log
                    WHERE user_id = $1
                    ORDER BY timestamp DESC
                    LIMIT $2
                """, user_id, limit)
                
                return [dict(activity) for activity in activities]
        except Exception as e:
            logger.error(f"Errore nell'ottenimento della cronologia delle attività per l'utente {user_id}: {e}")
            return []
    
    async def log_user_activity(self, user_id: int, action: str, details: Dict[str, Any] = None,
                               ip_address: str = None, user_agent: str = None) -> bool:
        """Registra un'attività dell'utente."""
        try:
            details_json = json.dumps(details) if details else None
            
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO user_activity_log 
                    (user_id, action, details, ip_address, user_agent)
                    VALUES ($1, $2, $3, $4, $5)
                """, user_id, action, details_json, ip_address, user_agent)
                
                return True
        except Exception as e:
            logger.error(f"Errore nella registrazione dell'attività per l'utente {user_id}: {e}")
            return False
    
    async def create_session(self, user_id: int, ip_address: str = None, 
                            user_agent: str = None) -> Optional[str]:
        """Crea una nuova sessione per un utente."""
        try:
            # Genera un token di sessione sicuro
            session_token = secrets.token_urlsafe(32)
            
            # Creazione dell'hash del token
            token_hash = hashlib.sha256(session_token.encode()).hexdigest()
            
            # Data di scadenza (30 giorni)
            expires_at = datetime.datetime.now() + datetime.timedelta(days=30)
            
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO user_sessions
                    (user_id, token_hash, ip_address, user_agent, expires_at)
                    VALUES ($1, $2, $3, $4, $5)
                """, user_id, token_hash, ip_address, user_agent, expires_at)
            
            # Salva in Redis per accesso rapido
            session_data = {
                'user_id': user_id,
                'created_at': datetime.datetime.now().isoformat(),
                'expires_at': expires_at.isoformat()
            }
            
            async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                await redis.set(f"session:{token_hash}", json.dumps(session_data))
                await redis.expire(f"session:{token_hash}", 30 * 24 * 60 * 60)  # 30 giorni
            
            return session_token
        except Exception as e:
            logger.error(f"Errore nella creazione della sessione per l'utente {user_id}: {e}")
            return None
    
    async def validate_session(self, session_token: str) -> Tuple[bool, Optional[int]]:
        """Valida un token di sessione e restituisce l'ID utente."""
        try:
            # Calcola l'hash del token
            token_hash = hashlib.sha256(session_token.encode()).hexdigest()
            
            # Controlla prima in Redis per prestazioni
            async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                session_data_json = await redis.get(f"session:{token_hash}")
                
                if session_data_json:
                    session_data = json.loads(session_data_json)
                    expires_at = datetime.datetime.fromisoformat(session_data['expires_at'])
                    
                    if datetime.datetime.now() > expires_at:
                        # Sessione scaduta
                        await redis.delete(f"session:{token_hash}")
                        return False, None
                    
                    return True, session_data['user_id']
            
            # Se non trovato in Redis, controlla nel database
            async with self.db_pool.acquire() as conn:
                session = await conn.fetchrow("""
                    SELECT user_id, expires_at
                    FROM user_sessions
                    WHERE token_hash = $1 AND is_active = true
                """, token_hash)
                
                if not session:
                    return False, None
                
                if datetime.datetime.now() > session['expires_at']:
                    # Sessione scaduta
                    await conn.execute("""
                        UPDATE user_sessions
                        SET is_active = false
                        WHERE token_hash = $1
                    """, token_hash)
                    return False, None
                
                # Aggiorna la sessione in Redis
                session_data = {
                    'user_id': session['user_id'],
                    'created_at': datetime.datetime.now().isoformat(),
                    'expires_at': session['expires_at'].isoformat()
                }
                
                async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                    await redis.set(f"session:{token_hash}", json.dumps(session_data))
                    await redis.expire(f"session:{token_hash}", 30 * 24 * 60 * 60)  # 30 giorni
                
                return True, session['user_id']
        except Exception as e:
            logger.error(f"Errore nella validazione della sessione: {e}")
            return False, None
    
    async def revoke_session(self, session_token: str) -> bool:
        """Revoca una sessione utente."""
        try:
            # Calcola l'hash del token
            token_hash = hashlib.sha256(session_token.encode()).hexdigest()
            
            # Rimuovi la sessione da Redis
            async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                await redis.delete(f"session:{token_hash}")
            
            # Rimuovi la sessione dal database
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE user_sessions
                    SET is_active = false
                    WHERE token_hash = $1
                """, token_hash)
            
            return True
        except Exception as e:
            logger.error(f"Errore nella revoca della sessione: {e}")
            return False
    
    async def revoke_all_user_sessions(self, user_id: int) -> bool:
        """Revoca tutte le sessioni di un utente."""
        try:
            async with self.db_pool.acquire() as conn:
                # Ottieni tutti i token di sessione dell'utente
                sessions = await conn.fetch("""
                    SELECT token_hash FROM user_sessions
                    WHERE user_id = $1 AND is_active = true
                """, user_id)
                
                # Disattiva le sessioni nel database
                await conn.execute("""
                    UPDATE user_sessions
                    SET is_active = false
                    WHERE user_id = $1 AND is_active = true
                """, user_id)
                
                # Rimuovi le sessioni da Redis
                if sessions:
                    async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                        for session in sessions:
                            await redis.delete(f"session:{session['token_hash']}")
            
            return True
        except Exception as e:
            logger.error(f"Errore nella revoca di tutte le sessioni per l'utente {user_id}: {e}")
            return False
    
    # Metodi privati di utilità
    
    def _hash_password(self, password: str) -> str:
        """Hash della password con bcrypt."""
        # Genera salt e hash della password
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode(), salt)
        return hashed.decode()
    
    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """Verifica una password contro un hash."""
        try:
            return bcrypt.checkpw(password.encode(), stored_hash.encode())
        except Exception:
            return False
    
    async def _get_from_cache(self, key: str) -> Any:
        """Ottiene un valore dalla cache Redis."""
        try:
            async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                value = await redis.get(key)
                
                if value:
                    return json.loads(value)
                
                return None
        except Exception as e:
            logger.error(f"Errore nell'ottenimento del valore dalla cache: {e}")
            return None
    
    async def _set_in_cache(self, key: str, value: Any, ttl: int = None) -> bool:
        """Salva un valore nella cache Redis."""
        try:
            async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                await redis.set(key, json.dumps(value))
                
                if ttl:
                    await redis.expire(key, ttl)
                
                return True
        except Exception as e:
            logger.error(f"Errore nel salvataggio del valore nella cache: {e}")
            return False
    
    async def _invalidate_permissions_cache(self, user_id: int) -> bool:
        """Invalida la cache dei permessi per un utente specifico."""
        try:
            async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                await redis.delete(f"user:{user_id}:permissions")
                return True
        except Exception as e:
            logger.error(f"Errore nell'invalidazione della cache dei permessi: {e}")
            return False
    
    async def _invalidate_role_permissions(self, role_id: int) -> bool:
        """Invalida la cache dei permessi per tutti gli utenti con un ruolo specifico."""
        try:
            async with self.db_pool.acquire() as conn:
                users = await conn.fetch("""
                    SELECT user_id FROM user_roles
                    WHERE role_id = $1
                """, role_id)
                
                if users:
                    async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                        for user in users:
                            await redis.delete(f"user:{user['user_id']}:permissions")
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'invalidazione della cache dei permessi per il ruolo {role_id}: {e}")
            return False
    
    async def _invalidate_all_permissions_cache(self) -> bool:
        """Invalida la cache dei permessi per tutti gli utenti."""
        try:
            # Trova tutti i pattern di chiavi della cache dei permessi
            async with aioredis.Redis(connection_pool=self.redis_pool) as redis:
                pattern = "user:*:permissions"
                cursor = b'0'
                while cursor:
                    cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=100)
                    
                    if keys:
                        await redis.delete(*keys)
                    
                    if cursor == b'0':
                        break
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'invalidazione di tutta la cache dei permessi: {e}")
            return False 