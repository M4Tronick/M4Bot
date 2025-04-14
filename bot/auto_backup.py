import os
import time
import asyncio
import logging
import subprocess
import aiofiles
import aiohttp
import shutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/auto_backup.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("AutoBackup")

class AutoBackup:
    """Sistema di backup automatico per il database di M4Bot"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Inizializza il sistema di backup automatico
        
        Args:
            config: Configurazione del sistema di backup
        """
        self.config = config
        self.backup_dir = config.get("backup_dir", "backups")
        self.max_backups = config.get("max_backups", 10)
        self.backup_interval = config.get("backup_interval", 86400)  # 24 ore
        self.db_name = config.get("db_name", "m4bot_db")
        self.db_user = config.get("db_user", "m4bot_user")
        self.db_password = config.get("db_password", "")
        self.db_host = config.get("db_host", "localhost")
        
        # Crea le directory necessarie
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs("logs", exist_ok=True)
        
        # Task di backup
        self.backup_task = None
        
        logger.info(f"Sistema di backup automatico inizializzato (directory: {self.backup_dir})")
    
    async def start_backup_scheduler(self):
        """Avvia lo scheduler di backup"""
        self.backup_task = asyncio.create_task(self._backup_loop())
        logger.info(f"Scheduler di backup avviato (intervallo: {self.backup_interval} secondi)")
    
    async def stop_backup_scheduler(self):
        """Ferma lo scheduler di backup"""
        if self.backup_task:
            self.backup_task.cancel()
            try:
                await self.backup_task
            except asyncio.CancelledError:
                pass
            self.backup_task = None
            logger.info("Scheduler di backup fermato")
    
    async def _backup_loop(self):
        """Loop principale di backup"""
        while True:
            try:
                # Esegui il backup
                success = await self._create_backup()
                
                if success:
                    # Mantieni solo il numero massimo di backup
                    await self._cleanup_old_backups()
                
            except Exception as e:
                logger.error(f"Errore durante il backup automatico: {e}")
            
            # Attendi prima del prossimo backup
            await asyncio.sleep(self.backup_interval)
    
    async def _create_backup(self) -> bool:
        """
        Crea un backup del database
        
        Returns:
            bool: True se il backup è stato creato con successo, False altrimenti
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(self.backup_dir, f"db_backup_{timestamp}.sql")
            
            logger.info(f"Inizio backup del database in {backup_file}")
            
            # Imposta la variabile d'ambiente per la password
            env = os.environ.copy()
            if self.db_password:
                env["PGPASSWORD"] = self.db_password
            
            # Comando per eseguire pg_dump
            cmd = [
                "pg_dump",
                "-h", self.db_host,
                "-U", self.db_user,
                "-d", self.db_name,
                "-f", backup_file
            ]
            
            # Esegui pg_dump come processo esterno
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                size_bytes = os.path.getsize(backup_file)
                size_mb = size_bytes / (1024 * 1024)
                
                logger.info(f"Backup completato con successo: {backup_file} ({size_mb:.2f} MB)")
                
                # Crea anche un backup compresso per ridurre lo spazio
                compressed_file = f"{backup_file}.gz"
                await self._compress_file(backup_file, compressed_file)
                
                # Rimuovi il file non compresso se la compressione è riuscita
                if os.path.exists(compressed_file):
                    os.remove(backup_file)
                    logger.info(f"File compresso creato: {compressed_file}")
                
                # Registra il backup nel file di registro
                await self._record_backup(timestamp, compressed_file if os.path.exists(compressed_file) else backup_file, size_mb)
                
                return True
            else:
                logger.error(f"Errore durante il backup: {stderr.decode()}")
                return False
        
        except Exception as e:
            logger.error(f"Errore durante la creazione del backup: {e}")
            return False
    
    async def _compress_file(self, source_file: str, target_file: str) -> bool:
        """
        Comprime un file utilizzando gzip
        
        Args:
            source_file: Il file da comprimere
            target_file: Il file di destinazione
            
        Returns:
            bool: True se la compressione è riuscita, False altrimenti
        """
        try:
            cmd = ["gzip", "-c", source_file]
            
            # Esegui gzip come processo esterno
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode == 0:
                # Scrivi l'output di gzip nel file di destinazione
                async with aiofiles.open(target_file, "wb") as f:
                    await f.write(stdout)
                return True
            else:
                logger.error(f"Errore durante la compressione: {stderr.decode()}")
                return False
        
        except Exception as e:
            logger.error(f"Errore durante la compressione del file: {e}")
            return False
    
    async def _record_backup(self, timestamp: str, file_path: str, size_mb: float):
        """
        Registra il backup nel file di registro
        
        Args:
            timestamp: Data e ora del backup
            file_path: Percorso del file di backup
            size_mb: Dimensione del backup in MB
        """
        log_file = os.path.join(self.backup_dir, "backup_history.log")
        
        try:
            async with aiofiles.open(log_file, "a") as f:
                await f.write(f"{timestamp}\t{file_path}\t{size_mb:.2f} MB\n")
        except Exception as e:
            logger.error(f"Errore durante la registrazione del backup: {e}")
    
    async def _cleanup_old_backups(self):
        """Rimuove i backup più vecchi per mantenere solo il numero massimo di backup"""
        try:
            # Ottieni la lista dei file di backup
            backup_files = []
            for file in os.listdir(self.backup_dir):
                if file.startswith("db_backup_") and (file.endswith(".sql") or file.endswith(".sql.gz")):
                    file_path = os.path.join(self.backup_dir, file)
                    backup_files.append((file_path, os.path.getmtime(file_path)))
            
            # Ordina per data di modifica (dal più vecchio al più recente)
            backup_files.sort(key=lambda x: x[1])
            
            # Rimuovi i backup in eccesso
            excess_count = len(backup_files) - self.max_backups
            if excess_count > 0:
                for i in range(excess_count):
                    file_to_remove = backup_files[i][0]
                    os.remove(file_to_remove)
                    logger.info(f"Rimosso backup vecchio: {file_to_remove}")
        
        except Exception as e:
            logger.error(f"Errore durante la pulizia dei backup vecchi: {e}")
    
    async def create_backup_now(self) -> bool:
        """
        Crea un backup immediatamente
        
        Returns:
            bool: True se il backup è stato creato con successo, False altrimenti
        """
        logger.info("Avvio backup manuale")
        return await self._create_backup()
    
    async def upload_backup_to_remote(self, backup_file: str) -> bool:
        """
        Carica un backup su un server remoto
        
        Args:
            backup_file: Il file di backup da caricare
            
        Returns:
            bool: True se il caricamento è riuscito, False altrimenti
        """
        if not os.path.exists(backup_file):
            logger.error(f"File di backup non trovato: {backup_file}")
            return False
        
        # Verifica se è configurato un server remoto
        remote_url = self.config.get("remote_backup_url")
        remote_key = self.config.get("remote_backup_key")
        
        if not remote_url or not remote_key:
            logger.warning("Backup remoto non configurato")
            return False
        
        try:
            # Leggi il file di backup
            async with aiofiles.open(backup_file, "rb") as f:
                file_data = await f.read()
            
            # Carica il file sul server remoto
            async with aiohttp.ClientSession() as session:
                headers = {"X-API-Key": remote_key}
                form_data = aiohttp.FormData()
                form_data.add_field(
                    "backup_file",
                    file_data,
                    filename=os.path.basename(backup_file)
                )
                
                async with session.post(remote_url, data=form_data, headers=headers) as response:
                    if response.status == 200:
                        logger.info(f"Backup caricato con successo su server remoto: {backup_file}")
                        return True
                    else:
                        logger.error(f"Errore durante il caricamento del backup: {response.status}")
                        return False
        
        except Exception as e:
            logger.error(f"Errore durante il caricamento del backup: {e}")
            return False

# Funzione per creare un'istanza del sistema di backup automatico
def create_auto_backup(config: Dict[str, Any]) -> AutoBackup:
    """
    Crea un'istanza del sistema di backup automatico
    
    Args:
        config: Configurazione del sistema di backup
        
    Returns:
        AutoBackup: Istanza del sistema di backup automatico
    """
    return AutoBackup(config) 