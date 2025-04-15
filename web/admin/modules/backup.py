"""
Modulo per la gestione dei backup e della loro rotazione.
Implementa la creazione, ripristino e gestione di backup pianificati.
"""

import os
import asyncio
import datetime
import logging
import json
import shutil
import tarfile
import gzip
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, Tuple

import asyncpg

logger = logging.getLogger('backup')

class RotationPolicy:
    """Gestisce le politiche di rotazione dei backup."""
    
    def __init__(self, max_daily: int = 7, max_weekly: int = 4, max_monthly: int = 12):
        self.max_daily = max_daily
        self.max_weekly = max_weekly
        self.max_monthly = max_monthly
    
    async def apply_rotation(self, db_pool: asyncpg.Pool, backup_dir: str):
        """Applica la politica di rotazione ai backup esistenti."""
        try:
            # Applica rotazione backup giornalieri
            await self._rotate_backups(db_pool, backup_dir, 'daily', self.max_daily)
            
            # Applica rotazione backup settimanali
            await self._rotate_backups(db_pool, backup_dir, 'weekly', self.max_weekly)
            
            # Applica rotazione backup mensili
            await self._rotate_backups(db_pool, backup_dir, 'monthly', self.max_monthly)
            
            logger.info("Rotazione dei backup completata")
        except Exception as e:
            logger.error(f"Errore nella rotazione dei backup: {e}")
    
    async def _rotate_backups(self, db_pool: asyncpg.Pool, backup_dir: str, 
                            frequency: str, max_count: int):
        """Rotazione dei backup di una specifica frequenza."""
        try:
            async with db_pool.acquire() as conn:
                # Ottieni i backup da ruotare
                backups = await conn.fetch("""
                    SELECT id, filename
                    FROM backups
                    WHERE frequency = $1 AND is_active = true
                    ORDER BY created_at DESC
                """, frequency)
                
                # Se ci sono più backup del massimo, elimina i più vecchi
                if len(backups) > max_count:
                    for backup in backups[max_count:]:
                        # Disattiva il backup nel database
                        await conn.execute("""
                            UPDATE backups
                            SET is_active = false, notes = COALESCE(notes, '') || ' Rimosso da rotazione automatica.'
                            WHERE id = $1
                        """, backup['id'])
                        
                        # Elimina il file fisico se esiste
                        file_path = os.path.join(backup_dir, backup['filename'])
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logger.info(f"Rimosso backup {backup['filename']} dalla rotazione {frequency}")
        except Exception as e:
            logger.error(f"Errore nella rotazione dei backup {frequency}: {e}")

class BackupManager:
    """Gestisce i backup del sistema."""
    
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.base_dir = os.environ.get('BACKUP_BASE_DIR', '/var/backups/m4bot')
        self.pg_user = os.environ.get('POSTGRES_USER', 'postgres')
        self.pg_password = os.environ.get('POSTGRES_PASSWORD', '')
        self.pg_host = os.environ.get('POSTGRES_HOST', 'localhost')
        self.pg_port = os.environ.get('POSTGRES_PORT', '5432')
        self.pg_database = os.environ.get('POSTGRES_DB', 'm4bot')
        self.rotation_policy = RotationPolicy()
        self.scheduled_tasks = {}
    
    async def start_scheduled_backups(self):
        """Avvia i backup pianificati."""
        # Carica le schedule dal database
        await self._load_schedules()
        
        # Avvia i task per ogni schedule
        for schedule_id, schedule in self.scheduled_tasks.items():
            asyncio.create_task(self._run_scheduled_backup(schedule))
        
        logger.info(f"Avviati {len(self.scheduled_tasks)} task di backup pianificati")
    
    async def _load_schedules(self):
        """Carica le schedule di backup dal database."""
        try:
            async with self.db_pool.acquire() as conn:
                schedules = await conn.fetch("""
                    SELECT id, name, backup_type, frequency, time_of_day, 
                           day_of_week, day_of_month, is_active, description
                    FROM backup_schedules
                    WHERE is_active = true
                """)
                
                for schedule in schedules:
                    self.scheduled_tasks[schedule['id']] = dict(schedule)
                    
                logger.info(f"Caricate {len(schedules)} schedule di backup")
        except Exception as e:
            logger.error(f"Errore nel caricamento delle schedule di backup: {e}")
    
    async def _run_scheduled_backup(self, schedule: Dict[str, Any]):
        """Esegue un backup pianificato periodicamente."""
        while True:
            try:
                # Calcola il tempo fino al prossimo backup
                next_run = self._calculate_next_run(schedule)
                
                # Attendi fino al prossimo backup
                await asyncio.sleep(next_run)
                
                # Esegui il backup
                logger.info(f"Esecuzione backup pianificato: {schedule['name']}")
                backup_id = await self.create_backup(
                    backup_type=schedule['backup_type'],
                    description=f"Backup automatico: {schedule['name']}",
                    frequency=schedule['frequency']
                )
                
                if backup_id:
                    logger.info(f"Backup pianificato {schedule['name']} completato con ID {backup_id}")
                else:
                    logger.error(f"Errore nell'esecuzione del backup pianificato {schedule['name']}")
                    
                # Applica la politica di rotazione
                await self.rotation_policy.apply_rotation(self.db_pool, self.base_dir)
            except Exception as e:
                logger.error(f"Errore nel task di backup pianificato {schedule['name']}: {e}")
                # Attendi 5 minuti in caso di errore
                await asyncio.sleep(300)
    
    def _calculate_next_run(self, schedule: Dict[str, Any]) -> int:
        """Calcola i secondi fino al prossimo backup pianificato."""
        now = datetime.datetime.now()
        time_parts = schedule['time_of_day'].split(':')
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        
        # Imposta la data obiettivo
        target_date = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        frequency = schedule['frequency']
        if frequency == 'daily':
            # Se l'orario è già passato, imposta per domani
            if target_date <= now:
                target_date += datetime.timedelta(days=1)
        elif frequency == 'weekly':
            # Giorno della settimana (0 = lunedì, 6 = domenica)
            day_of_week = schedule['day_of_week']
            days_ahead = day_of_week - now.weekday()
            if days_ahead <= 0 or (days_ahead == 0 and target_date <= now):
                days_ahead += 7
            target_date = now.replace(hour=hour, minute=minute, second=0, microsecond=0) + datetime.timedelta(days=days_ahead)
        elif frequency == 'monthly':
            # Giorno del mese
            day_of_month = min(schedule['day_of_month'], 28)  # Limita a 28 per evitare problemi
            # Se il giorno è già passato, imposta per il prossimo mese
            if now.day > day_of_month or (now.day == day_of_month and target_date <= now):
                if now.month == 12:
                    target_date = target_date.replace(year=now.year + 1, month=1, day=day_of_month)
                else:
                    target_date = target_date.replace(month=now.month + 1, day=day_of_month)
            else:
                target_date = target_date.replace(day=day_of_month)
        
        # Calcola i secondi fino all'esecuzione
        seconds_until_run = (target_date - now).total_seconds()
        return max(0, seconds_until_run)  # Evita valori negativi
    
    async def create_backup(self, backup_type: str, description: str = None, 
                          user_id: int = None, frequency: str = 'manual') -> Optional[int]:
        """Crea un nuovo backup del sistema."""
        try:
            # Crea la directory di backup se non esiste
            os.makedirs(self.base_dir, exist_ok=True)
            
            # Crea un nome di file univoco
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"backup_{backup_type}_{timestamp}.tar.gz"
            file_path = os.path.join(self.base_dir, filename)
            
            # Esegui il backup in base al tipo
            success, file_size = await self._perform_backup(backup_type, file_path)
            
            if not success:
                logger.error(f"Errore nell'esecuzione del backup di tipo {backup_type}")
                return None
                
            # Registra il backup nel database
            async with self.db_pool.acquire() as conn:
                backup_id = await conn.fetchval("""
                    INSERT INTO backups 
                    (backup_type, filename, file_path, file_size, description, created_by, frequency)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                """, backup_type, filename, file_path, file_size, 
                description, user_id, frequency)
                
                return backup_id
        except Exception as e:
            logger.error(f"Errore nella creazione del backup: {e}")
            # Se c'è stato un errore, elimina il file di backup se esiste
            if 'file_path' in locals() and os.path.exists(file_path):
                os.remove(file_path)
            return None
    
    async def _perform_backup(self, backup_type: str, file_path: str) -> Tuple[bool, int]:
        """Esegue il backup effettivo."""
        if backup_type == 'database':
            return await self._backup_database(file_path)
        elif backup_type == 'config':
            return await self._backup_config(file_path)
        elif backup_type == 'full':
            return await self._backup_full(file_path)
        else:
            logger.error(f"Tipo di backup non supportato: {backup_type}")
            return False, 0
    
    async def _backup_database(self, file_path: str) -> Tuple[bool, int]:
        """Esegue il backup del database."""
        try:
            # Crea una directory temporanea
            with tempfile.TemporaryDirectory() as temp_dir:
                # Nome del file di dump
                dump_file = os.path.join(temp_dir, 'database.sql')
                
                # Comando pg_dump
                cmd = [
                    'pg_dump',
                    f'--host={self.pg_host}',
                    f'--port={self.pg_port}',
                    f'--username={self.pg_user}',
                    f'--dbname={self.pg_database}',
                    '--format=plain',
                    f'--file={dump_file}'
                ]
                
                # Imposta la variabile d'ambiente per la password
                env = os.environ.copy()
                env['PGPASSWORD'] = self.pg_password
                
                # Esegui pg_dump
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    logger.error(f"Errore nel dump del database: {stderr.decode()}")
                    return False, 0
                
                # Crea l'archivio con il dump del database
                with tarfile.open(file_path, 'w:gz') as tar:
                    tar.add(dump_file, arcname=os.path.basename(dump_file))
                
            # Dimensione del file di backup
            file_size = os.path.getsize(file_path)
            
            return True, file_size
        except Exception as e:
            logger.error(f"Errore nel backup del database: {e}")
            return False, 0
    
    async def _backup_config(self, file_path: str) -> Tuple[bool, int]:
        """Esegue il backup dei file di configurazione."""
        try:
            # Crea una directory temporanea
            with tempfile.TemporaryDirectory() as temp_dir:
                # Elenco dei file e directory di configurazione da backup
                config_paths = [
                    '/etc/m4bot',
                    os.path.join(os.getcwd(), '.env'),
                    os.path.join(os.getcwd(), 'config')
                ]
                
                # Crea l'archivio
                with tarfile.open(file_path, 'w:gz') as tar:
                    for path in config_paths:
                        if os.path.exists(path):
                            # Se è una directory, aggiungi ricorsivamente
                            if os.path.isdir(path):
                                for root, dirs, files in os.walk(path):
                                    for file in files:
                                        file_path_full = os.path.join(root, file)
                                        arcname = os.path.relpath(file_path_full, os.path.dirname(path))
                                        tar.add(file_path_full, arcname=arcname)
                            else:
                                # Se è un file, aggiungilo direttamente
                                tar.add(path, arcname=os.path.basename(path))
            
            # Dimensione del file di backup
            file_size = os.path.getsize(file_path)
            
            return True, file_size
        except Exception as e:
            logger.error(f"Errore nel backup della configurazione: {e}")
            return False, 0
    
    async def _backup_full(self, file_path: str) -> Tuple[bool, int]:
        """Esegue un backup completo (DB + config + dati utente)."""
        try:
            # Crea una directory temporanea
            with tempfile.TemporaryDirectory() as temp_dir:
                # Backup del database
                db_file = os.path.join(temp_dir, 'database.sql')
                
                # Comando pg_dump
                cmd = [
                    'pg_dump',
                    f'--host={self.pg_host}',
                    f'--port={self.pg_port}',
                    f'--username={self.pg_user}',
                    f'--dbname={self.pg_database}',
                    '--format=plain',
                    f'--file={db_file}'
                ]
                
                # Imposta la variabile d'ambiente per la password
                env = os.environ.copy()
                env['PGPASSWORD'] = self.pg_password
                
                # Esegui pg_dump
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    logger.error(f"Errore nel dump del database: {stderr.decode()}")
                    return False, 0
                
                # Elenco dei path da includere nel backup completo
                backup_paths = [
                    '/etc/m4bot',
                    os.path.join(os.getcwd(), '.env'),
                    os.path.join(os.getcwd(), 'config'),
                    os.path.join(os.getcwd(), 'data'),
                    os.path.join(os.getcwd(), 'web', 'static', 'uploads')
                ]
                
                # Crea l'archivio
                with tarfile.open(file_path, 'w:gz') as tar:
                    # Aggiungi il dump del database
                    tar.add(db_file, arcname='database.sql')
                    
                    # Aggiungi gli altri file e directory
                    for path in backup_paths:
                        if os.path.exists(path):
                            # Se è una directory, aggiungi ricorsivamente
                            if os.path.isdir(path):
                                for root, dirs, files in os.walk(path):
                                    for file in files:
                                        file_path_full = os.path.join(root, file)
                                        arcname = os.path.join('files', os.path.relpath(file_path_full, os.getcwd()))
                                        tar.add(file_path_full, arcname=arcname)
                            else:
                                # Se è un file, aggiungilo direttamente
                                arcname = os.path.join('files', os.path.basename(path))
                                tar.add(path, arcname=arcname)
            
            # Dimensione del file di backup
            file_size = os.path.getsize(file_path)
            
            return True, file_size
        except Exception as e:
            logger.error(f"Errore nel backup completo: {e}")
            return False, 0
    
    async def restore_backup(self, backup_id: int, user_id: int = None) -> bool:
        """Ripristina un backup."""
        try:
            # Ottieni informazioni sul backup
            async with self.db_pool.acquire() as conn:
                backup = await conn.fetchrow("""
                    SELECT id, backup_type, filename, file_path, is_active
                    FROM backups
                    WHERE id = $1
                """, backup_id)
                
                if not backup or not backup['is_active']:
                    logger.error(f"Backup {backup_id} non trovato o non attivo")
                    return False
                
                file_path = backup['file_path']
                backup_type = backup['backup_type']
                
                # Verifica che il file esista
                if not os.path.exists(file_path):
                    logger.error(f"File di backup non trovato: {file_path}")
                    
                    # Registra il tentativo di ripristino fallito
                    await conn.execute("""
                        INSERT INTO restore_logs (backup_id, user_id, status, message)
                        VALUES ($1, $2, $3, $4)
                    """, backup_id, user_id, 'failed', "File di backup non trovato")
                    
                    return False
                
                # Esegui il ripristino in base al tipo di backup
                success, message = await self._perform_restore(backup_type, file_path)
                
                # Registra il ripristino nel database
                await conn.execute("""
                    INSERT INTO restore_logs (backup_id, user_id, status, message)
                    VALUES ($1, $2, $3, $4)
                """, backup_id, user_id, 'success' if success else 'failed', message)
                
                return success
        except Exception as e:
            logger.error(f"Errore nel ripristino del backup {backup_id}: {e}")
            
            # Registra il tentativo di ripristino fallito
            try:
                async with self.db_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO restore_logs (backup_id, user_id, status, message)
                        VALUES ($1, $2, $3, $4)
                    """, backup_id, user_id, 'failed', str(e))
            except:
                pass
                
            return False
    
    async def _perform_restore(self, backup_type: str, file_path: str) -> Tuple[bool, str]:
        """Esegue il ripristino effettivo."""
        if backup_type == 'database':
            return await self._restore_database(file_path)
        elif backup_type == 'config':
            return await self._restore_config(file_path)
        elif backup_type == 'full':
            return await self._restore_full(file_path)
        else:
            message = f"Tipo di backup non supportato: {backup_type}"
            logger.error(message)
            return False, message
    
    async def _restore_database(self, file_path: str) -> Tuple[bool, str]:
        """Ripristina il database da un backup."""
        try:
            # Crea una directory temporanea
            with tempfile.TemporaryDirectory() as temp_dir:
                # Estrai l'archivio
                with tarfile.open(file_path, 'r:gz') as tar:
                    tar.extractall(path=temp_dir)
                
                # Ottieni il file SQL
                sql_files = [f for f in os.listdir(temp_dir) if f.endswith('.sql')]
                if not sql_files:
                    return False, "Nessun file SQL trovato nell'archivio"
                
                sql_file = os.path.join(temp_dir, sql_files[0])
                
                # Comando psql per il ripristino
                cmd = [
                    'psql',
                    f'--host={self.pg_host}',
                    f'--port={self.pg_port}',
                    f'--username={self.pg_user}',
                    f'--dbname={self.pg_database}',
                    '-f', sql_file
                ]
                
                # Imposta la variabile d'ambiente per la password
                env = os.environ.copy()
                env['PGPASSWORD'] = self.pg_password
                
                # Esegui psql
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = f"Errore nel ripristino del database: {stderr.decode()}"
                    logger.error(error_message)
                    return False, error_message
                
                return True, "Database ripristinato con successo"
        except Exception as e:
            error_message = f"Errore nel ripristino del database: {str(e)}"
            logger.error(error_message)
            return False, error_message
    
    async def _restore_config(self, file_path: str) -> Tuple[bool, str]:
        """Ripristina i file di configurazione da un backup."""
        try:
            # Crea una directory temporanea
            with tempfile.TemporaryDirectory() as temp_dir:
                # Estrai l'archivio
                with tarfile.open(file_path, 'r:gz') as tar:
                    tar.extractall(path=temp_dir)
                
                # Directory di destinazione delle configurazioni
                config_dir = os.path.join(os.getcwd(), 'config')
                
                # Copia i file di configurazione
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        src_path = os.path.join(root, file)
                        rel_path = os.path.relpath(src_path, temp_dir)
                        
                        # Determina la destinazione in base al percorso del file
                        if rel_path.startswith('etc/'):
                            # File di sistema
                            dest_path = os.path.join('/', rel_path)
                            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                            shutil.copy2(src_path, dest_path)
                        else:
                            # File dell'applicazione
                            dest_path = os.path.join(os.getcwd(), rel_path)
                            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                            shutil.copy2(src_path, dest_path)
                
                return True, "File di configurazione ripristinati con successo"
        except Exception as e:
            error_message = f"Errore nel ripristino della configurazione: {str(e)}"
            logger.error(error_message)
            return False, error_message
    
    async def _restore_full(self, file_path: str) -> Tuple[bool, str]:
        """Ripristina un backup completo."""
        try:
            # Crea una directory temporanea
            with tempfile.TemporaryDirectory() as temp_dir:
                # Estrai l'archivio
                with tarfile.open(file_path, 'r:gz') as tar:
                    tar.extractall(path=temp_dir)
                
                # Ripristina database
                sql_file = os.path.join(temp_dir, 'database.sql')
                if os.path.exists(sql_file):
                    # Comando psql per il ripristino
                    cmd = [
                        'psql',
                        f'--host={self.pg_host}',
                        f'--port={self.pg_port}',
                        f'--username={self.pg_user}',
                        f'--dbname={self.pg_database}',
                        '-f', sql_file
                    ]
                    
                    # Imposta la variabile d'ambiente per la password
                    env = os.environ.copy()
                    env['PGPASSWORD'] = self.pg_password
                    
                    # Esegui psql
                    process = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        env=env
                    )
                    
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode != 0:
                        error_message = f"Errore nel ripristino del database: {stderr.decode()}"
                        logger.error(error_message)
                        return False, error_message
                
                # Ripristina i file
                files_dir = os.path.join(temp_dir, 'files')
                if os.path.exists(files_dir):
                    for root, dirs, files in os.walk(files_dir):
                        for file in files:
                            src_path = os.path.join(root, file)
                            rel_path = os.path.relpath(src_path, files_dir)
                            
                            # Determina la destinazione
                            if rel_path.startswith('etc/'):
                                # File di sistema
                                dest_path = os.path.join('/', rel_path)
                            else:
                                # File dell'applicazione
                                dest_path = os.path.join(os.getcwd(), rel_path)
                            
                            # Crea la directory di destinazione se non esiste
                            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                            
                            # Copia il file
                            shutil.copy2(src_path, dest_path)
                
                return True, "Backup completo ripristinato con successo"
        except Exception as e:
            error_message = f"Errore nel ripristino completo: {str(e)}"
            logger.error(error_message)
            return False, error_message
    
    async def get_all_backups(self) -> List[Dict[str, Any]]:
        """Ottiene l'elenco di tutti i backup."""
        try:
            async with self.db_pool.acquire() as conn:
                backups = await conn.fetch("""
                    SELECT b.id, b.backup_type, b.filename, b.file_size, 
                           b.description, b.created_at, b.is_active, b.frequency,
                           u.username as created_by_username
                    FROM backups b
                    LEFT JOIN users u ON b.created_by = u.id
                    ORDER BY b.created_at DESC
                """)
                
                return [dict(backup) for backup in backups]
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dei backup: {e}")
            return []
    
    async def get_backup_schedules(self) -> List[Dict[str, Any]]:
        """Ottiene l'elenco delle schedule di backup."""
        try:
            async with self.db_pool.acquire() as conn:
                schedules = await conn.fetch("""
                    SELECT id, name, backup_type, frequency, time_of_day, 
                           day_of_week, day_of_month, is_active, description,
                           created_at, updated_at
                    FROM backup_schedules
                    ORDER BY name
                """)
                
                return [dict(schedule) for schedule in schedules]
        except Exception as e:
            logger.error(f"Errore nell'ottenimento delle schedule di backup: {e}")
            return []
    
    async def get_recent_backups(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Ottiene i backup più recenti."""
        try:
            async with self.db_pool.acquire() as conn:
                backups = await conn.fetch("""
                    SELECT b.id, b.backup_type, b.filename, b.file_size, 
                           b.description, b.created_at, b.frequency,
                           u.username as created_by_username
                    FROM backups b
                    LEFT JOIN users u ON b.created_by = u.id
                    WHERE b.is_active = true
                    ORDER BY b.created_at DESC
                    LIMIT $1
                """, limit)
                
                return [dict(backup) for backup in backups]
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dei backup recenti: {e}")
            return []
    
    async def create_backup_schedule(self, schedule_data: Dict[str, Any]) -> Optional[int]:
        """Crea una nuova schedule di backup."""
        try:
            # Validazione dei dati
            if not all(k in schedule_data for k in ['name', 'backup_type', 'frequency', 'time_of_day']):
                logger.error("Dati della schedule mancanti o incompleti")
                return None
                
            # Aggiungi giorni specifici per le frequenze appropriate
            if schedule_data['frequency'] == 'weekly' and 'day_of_week' not in schedule_data:
                schedule_data['day_of_week'] = 0  # Lunedì
                
            if schedule_data['frequency'] == 'monthly' and 'day_of_month' not in schedule_data:
                schedule_data['day_of_month'] = 1  # Primo giorno del mese
                
            async with self.db_pool.acquire() as conn:
                # Verifica se la schedule esiste già
                existing = await conn.fetchval("""
                    SELECT id FROM backup_schedules
                    WHERE name = $1
                """, schedule_data['name'])
                
                if existing:
                    logger.warning(f"Una schedule con il nome {schedule_data['name']} esiste già")
                    return None
                
                # Crea la schedule
                schedule_id = await conn.fetchval("""
                    INSERT INTO backup_schedules 
                    (name, backup_type, frequency, time_of_day, day_of_week, 
                     day_of_month, is_active, description)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING id
                """, schedule_data['name'], schedule_data['backup_type'],
                schedule_data['frequency'], schedule_data['time_of_day'],
                schedule_data.get('day_of_week'), schedule_data.get('day_of_month'),
                schedule_data.get('is_active', True), schedule_data.get('description', ''))
                
                # Aggiungi alla cache e avvia il task
                self.scheduled_tasks[schedule_id] = dict(schedule_data)
                self.scheduled_tasks[schedule_id]['id'] = schedule_id
                
                # Avvia il task
                asyncio.create_task(self._run_scheduled_backup(self.scheduled_tasks[schedule_id]))
                
                return schedule_id
        except Exception as e:
            logger.error(f"Errore nella creazione della schedule di backup: {e}")
            return None
    
    async def update_backup_schedule(self, schedule_id: int, schedule_data: Dict[str, Any]) -> bool:
        """Aggiorna una schedule di backup esistente."""
        try:
            # Validazione dei dati
            if not any(k in schedule_data for k in ['name', 'backup_type', 'frequency', 'time_of_day', 'is_active']):
                logger.error("Nessun dato da aggiornare")
                return False
                
            fields_to_update = []
            params = []
            param_idx = 1
            
            updatable_fields = {
                'name': 'name', 
                'backup_type': 'backup_type', 
                'frequency': 'frequency',
                'time_of_day': 'time_of_day',
                'day_of_week': 'day_of_week',
                'day_of_month': 'day_of_month',
                'is_active': 'is_active',
                'description': 'description'
            }
            
            for field, db_field in updatable_fields.items():
                if field in schedule_data:
                    fields_to_update.append(f"{db_field} = ${param_idx}")
                    params.append(schedule_data[field])
                    param_idx += 1
            
            if not fields_to_update:
                logger.warning("Nessun campo da aggiornare")
                return False
                
            # Aggiungi updated_at e schedule_id
            fields_str = ", ".join(fields_to_update)
            fields_str += f", updated_at = ${param_idx}"
            params.append(datetime.datetime.now())
            param_idx += 1
            
            params.append(schedule_id)
            
            async with self.db_pool.acquire() as conn:
                # Verifica se la schedule esiste
                existing = await conn.fetchval("""
                    SELECT id FROM backup_schedules
                    WHERE id = $1
                """, schedule_id)
                
                if not existing:
                    logger.warning(f"Schedule con ID {schedule_id} non trovata")
                    return False
                
                # Aggiorna la schedule
                await conn.execute(f"""
                    UPDATE backup_schedules
                    SET {fields_str}
                    WHERE id = ${param_idx}
                """, *params)
                
                # Ricarica la schedule dal database
                updated_schedule = await conn.fetchrow("""
                    SELECT id, name, backup_type, frequency, time_of_day, 
                           day_of_week, day_of_month, is_active, description
                    FROM backup_schedules
                    WHERE id = $1
                """, schedule_id)
                
                # Aggiorna la cache
                if schedule_id in self.scheduled_tasks:
                    # Rimuovi il task esistente (verrà ricreato al prossimo riavvio o aggiornamento)
                    self.scheduled_tasks[schedule_id] = dict(updated_schedule)
                
                return True
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento della schedule {schedule_id}: {e}")
            return False
    
    async def delete_backup_schedule(self, schedule_id: int) -> bool:
        """Elimina una schedule di backup."""
        try:
            async with self.db_pool.acquire() as conn:
                # Verifica se la schedule esiste
                existing = await conn.fetchval("""
                    SELECT id FROM backup_schedules
                    WHERE id = $1
                """, schedule_id)
                
                if not existing:
                    logger.warning(f"Schedule con ID {schedule_id} non trovata")
                    return False
                
                # Elimina la schedule
                await conn.execute("""
                    DELETE FROM backup_schedules
                    WHERE id = $1
                """, schedule_id)
                
                # Rimuovi dalla cache
                if schedule_id in self.scheduled_tasks:
                    del self.scheduled_tasks[schedule_id]
                    
                return True
        except Exception as e:
            logger.error(f"Errore nell'eliminazione della schedule {schedule_id}: {e}")
            return False 