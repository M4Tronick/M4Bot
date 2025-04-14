import os
import sys
import json
import time
import logging
import asyncio
import aiohttp
import aiofiles
import subprocess
import shutil
import hashlib
from datetime import datetime
from typing import Dict, List, Optional, Any

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/updater.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("Updater")

class AutoUpdater:
    """Sistema di aggiornamento automatico per M4Bot"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Inizializza il sistema di aggiornamento automatico
        
        Args:
            config: Configurazione del sistema di aggiornamento
        """
        self.config = config
        self.update_url = config.get("update_url", "https://api.m4bot.it/updates")
        self.update_interval = config.get("update_interval", 86400)  # 24 ore
        self.auto_update = config.get("auto_update", False)
        self.current_version = config.get("version", "1.0.0")
        self.update_channel = config.get("update_channel", "stable")
        self.update_key = config.get("update_key", "")
        self.temp_dir = config.get("temp_dir", "temp")
        self.backup_dir = config.get("backup_dir", "backups")
        
        # Directory di installazione
        self.install_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        
        # Crea le directory necessarie
        os.makedirs(self.temp_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs("logs", exist_ok=True)
        
        # Task di aggiornamento
        self.update_task = None
        
        # Flag per l'aggiornamento in corso
        self.updating = False
        
        # Informazioni sull'ultimo aggiornamento
        self.last_update_check = 0
        self.last_update_info = None
        
        logger.info(f"Sistema di aggiornamento automatico inizializzato (versione: {self.current_version})")
    
    async def start_update_checker(self):
        """Avvia il controllo periodico degli aggiornamenti"""
        if self.update_task:
            logger.warning("Il controllo degli aggiornamenti è già in esecuzione")
            return
        
        self.update_task = asyncio.create_task(self._update_loop())
        logger.info(f"Controllo degli aggiornamenti avviato (intervallo: {self.update_interval} secondi)")
    
    async def stop_update_checker(self):
        """Ferma il controllo periodico degli aggiornamenti"""
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
            self.update_task = None
            logger.info("Controllo degli aggiornamenti fermato")
    
    async def _update_loop(self):
        """Loop principale per il controllo degli aggiornamenti"""
        try:
            # Controlla subito all'avvio
            await self.check_for_updates()
            
            while True:
                # Attendi il prossimo controllo
                await asyncio.sleep(self.update_interval)
                
                # Controlla gli aggiornamenti
                update_available = await self.check_for_updates()
                
                # Se c'è un aggiornamento e l'aggiornamento automatico è abilitato, aggiorna
                if update_available and self.auto_update and not self.updating:
                    logger.info("Aggiornamento automatico in corso...")
                    await self.update()
                
        except asyncio.CancelledError:
            # Task annullato
            logger.info("Controllo degli aggiornamenti annullato")
        
        except Exception as e:
            logger.error(f"Errore nel controllo degli aggiornamenti: {e}")
    
    async def check_for_updates(self) -> bool:
        """
        Controlla se ci sono aggiornamenti disponibili
        
        Returns:
            bool: True se c'è un aggiornamento disponibile, False altrimenti
        """
        try:
            # Evita controlli troppo frequenti
            current_time = time.time()
            if current_time - self.last_update_check < 60:  # Minimo 1 minuto tra i controlli
                logger.debug("Controllo degli aggiornamenti ignorato (troppo frequente)")
                return False
            
            self.last_update_check = current_time
            
            # Prepara i dati per la richiesta
            data = {
                "version": self.current_version,
                "channel": self.update_channel,
                "platform": sys.platform,
                "python_version": sys.version
            }
            
            # Aggiungi la chiave di aggiornamento se disponibile
            headers = {}
            if self.update_key:
                headers["X-Update-Key"] = self.update_key
            
            # Esegui la richiesta
            async with aiohttp.ClientSession() as session:
                async with session.post(self.update_url, json=data, headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Errore nella richiesta di aggiornamento: {response.status}")
                        return False
                    
                    # Leggi la risposta
                    update_info = await response.json()
                    
                    # Verifica se c'è un aggiornamento disponibile
                    if "version" in update_info and self._is_newer_version(update_info["version"]):
                        self.last_update_info = update_info
                        logger.info(f"Aggiornamento disponibile: {update_info['version']}")
                        return True
                    
                    logger.info("Nessun aggiornamento disponibile")
                    return False
                
        except Exception as e:
            logger.error(f"Errore nel controllo degli aggiornamenti: {e}")
            return False
    
    def _is_newer_version(self, version: str) -> bool:
        """
        Verifica se una versione è più recente della versione corrente
        
        Args:
            version: Versione da confrontare
            
        Returns:
            bool: True se la versione è più recente, False altrimenti
        """
        # Converti le versioni in tuple di interi
        def parse_version(v):
            return tuple(map(int, v.split('.')))
        
        try:
            current = parse_version(self.current_version)
            new = parse_version(version)
            
            return new > current
        
        except Exception as e:
            logger.error(f"Errore nel confronto delle versioni: {e}")
            return False
    
    async def update(self) -> bool:
        """
        Esegue l'aggiornamento del sistema
        
        Returns:
            bool: True se l'aggiornamento è riuscito, False altrimenti
        """
        if self.updating:
            logger.warning("Un aggiornamento è già in corso")
            return False
        
        if not self.last_update_info:
            logger.warning("Nessuna informazione di aggiornamento disponibile")
            return False
        
        self.updating = True
        
        try:
            # Estrai le informazioni di aggiornamento
            version = self.last_update_info.get("version")
            download_url = self.last_update_info.get("download_url")
            checksum = self.last_update_info.get("checksum")
            
            if not download_url:
                logger.error("URL di download non disponibile")
                self.updating = False
                return False
            
            # Crea il nome del file di aggiornamento
            update_file = os.path.join(self.temp_dir, f"update_{version}.zip")
            
            # Scarica l'aggiornamento
            logger.info(f"Download dell'aggiornamento in corso: {version}")
            if not await self._download_update(download_url, update_file):
                self.updating = False
                return False
            
            # Verifica il checksum se disponibile
            if checksum and not self._verify_checksum(update_file, checksum):
                logger.error("Verifica del checksum fallita")
                os.remove(update_file)
                self.updating = False
                return False
            
            # Crea un backup prima dell'aggiornamento
            logger.info("Creazione del backup in corso...")
            backup_file = os.path.join(self.backup_dir, f"backup_{self.current_version}_{int(time.time())}.zip")
            if not await self._create_backup(backup_file):
                logger.error("Creazione del backup fallita, aggiornamento annullato")
                self.updating = False
                return False
            
            # Estrai e installa l'aggiornamento
            logger.info("Installazione dell'aggiornamento in corso...")
            if not await self._install_update(update_file):
                logger.error("Installazione dell'aggiornamento fallita")
                self.updating = False
                return False
            
            # Aggiorna la versione corrente
            self.current_version = version
            
            # Salva la nuova versione nel file di configurazione
            await self._update_version_in_config()
            
            # Aggiornamento completato
            logger.info(f"Aggiornamento completato: {version}")
            self.updating = False
            return True
            
        except Exception as e:
            logger.error(f"Errore durante l'aggiornamento: {e}")
            self.updating = False
            return False
    
    async def _download_update(self, url: str, destination: str) -> bool:
        """
        Scarica un aggiornamento
        
        Args:
            url: URL dell'aggiornamento
            destination: Percorso di destinazione
            
        Returns:
            bool: True se il download è riuscito, False altrimenti
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Errore nel download dell'aggiornamento: {response.status}")
                        return False
                    
                    # Leggi il contenuto della risposta
                    content = await response.read()
                    
                    # Scrivi il file
                    async with aiofiles.open(destination, "wb") as f:
                        await f.write(content)
                    
                    return True
                
        except Exception as e:
            logger.error(f"Errore nel download dell'aggiornamento: {e}")
            return False
    
    def _verify_checksum(self, file_path: str, expected_checksum: str) -> bool:
        """
        Verifica il checksum di un file
        
        Args:
            file_path: Percorso del file
            expected_checksum: Checksum atteso
            
        Returns:
            bool: True se il checksum è corretto, False altrimenti
        """
        try:
            # Calcola il checksum SHA-256
            sha256 = hashlib.sha256()
            
            with open(file_path, "rb") as f:
                # Leggi il file a blocchi
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256.update(chunk)
            
            # Confronta i checksum
            calculated_checksum = sha256.hexdigest()
            
            if calculated_checksum.lower() != expected_checksum.lower():
                logger.error(f"Checksum non corrispondente: atteso {expected_checksum}, calcolato {calculated_checksum}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Errore nella verifica del checksum: {e}")
            return False
    
    async def _create_backup(self, backup_file: str) -> bool:
        """
        Crea un backup del sistema
        
        Args:
            backup_file: Percorso del file di backup
            
        Returns:
            bool: True se il backup è riuscito, False altrimenti
        """
        try:
            # Crea una lista di file e directory da escludere dal backup
            exclude = [
                self.temp_dir,
                self.backup_dir,
                ".git",
                "__pycache__",
                "*.pyc",
                "*.pyo",
                "*.pyd",
                "logs/*"
            ]
            
            # Crea il comando 7zip o zip (in base alla disponibilità)
            if shutil.which("7z"):
                cmd = ["7z", "a", backup_file, ".", f"-x!{self.temp_dir}/*", f"-x!{self.backup_dir}/*"]
                for item in exclude:
                    cmd.append(f"-xr!{item}")
            else:
                cmd = ["zip", "-r", backup_file, "."]
                for item in exclude:
                    cmd.append(f"-x '{item}'")
            
            # Esegui il comando
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.install_dir
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                logger.error(f"Errore nella creazione del backup: {stderr.decode()}")
                return False
            
            logger.info(f"Backup creato con successo: {backup_file}")
            return True
            
        except Exception as e:
            logger.error(f"Errore nella creazione del backup: {e}")
            return False
    
    async def _install_update(self, update_file: str) -> bool:
        """
        Installa un aggiornamento
        
        Args:
            update_file: Percorso del file di aggiornamento
            
        Returns:
            bool: True se l'installazione è riuscita, False altrimenti
        """
        try:
            # Crea una directory temporanea per l'estrazione
            extract_dir = os.path.join(self.temp_dir, "update_extract")
            os.makedirs(extract_dir, exist_ok=True)
            
            # Estrai l'aggiornamento
            if shutil.which("7z"):
                cmd = ["7z", "x", update_file, f"-o{extract_dir}", "-y"]
            else:
                cmd = ["unzip", "-o", update_file, "-d", extract_dir]
            
            # Esegui il comando
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                logger.error(f"Errore nell'estrazione dell'aggiornamento: {stderr.decode()}")
                return False
            
            # Copia i file aggiornati
            logger.info("Copia dei file aggiornati in corso...")
            
            # Trova la directory principale nell'archivio
            main_dir = extract_dir
            for item in os.listdir(extract_dir):
                item_path = os.path.join(extract_dir, item)
                if os.path.isdir(item_path) and "m4bot" in item.lower():
                    main_dir = item_path
                    break
            
            # Esegui lo script di aggiornamento se presente
            update_script = os.path.join(main_dir, "update.py")
            if os.path.exists(update_script):
                logger.info("Esecuzione dello script di aggiornamento...")
                cmd = [sys.executable, update_script]
                
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=main_dir
                )
                
                stdout, stderr = await proc.communicate()
                
                if proc.returncode != 0:
                    logger.error(f"Errore nell'esecuzione dello script di aggiornamento: {stderr.decode()}")
                    return False
            
            # Copia tutti i file nella directory di installazione
            def copy_recursively(src, dst):
                for item in os.listdir(src):
                    s = os.path.join(src, item)
                    d = os.path.join(dst, item)
                    
                    # Skip alcuni file speciali
                    if item in ["update.py", "backups", "temp", "logs"]:
                        continue
                    
                    # Copia ricorsiva
                    if os.path.isdir(s):
                        os.makedirs(d, exist_ok=True)
                        copy_recursively(s, d)
                    else:
                        shutil.copy2(s, d)
            
            # Copia i file
            copy_recursively(main_dir, self.install_dir)
            
            # Pulisci la directory temporanea
            shutil.rmtree(extract_dir, ignore_errors=True)
            
            # Installazione completata
            logger.info("Installazione dell'aggiornamento completata")
            return True
            
        except Exception as e:
            logger.error(f"Errore nell'installazione dell'aggiornamento: {e}")
            return False
    
    async def _update_version_in_config(self):
        """Aggiorna la versione nel file di configurazione"""
        try:
            config_file = os.path.join(self.install_dir, "bot", "config.py")
            
            if not os.path.exists(config_file):
                logger.warning("File di configurazione non trovato")
                return
            
            # Leggi il file di configurazione
            async with aiofiles.open(config_file, "r") as f:
                content = await f.read()
            
            # Aggiorna la versione
            new_content = ""
            for line in content.split("\n"):
                if "VERSION = " in line:
                    new_content += f'VERSION = "{self.current_version}"\n'
                else:
                    new_content += line + "\n"
            
            # Scrivi il file di configurazione
            async with aiofiles.open(config_file, "w") as f:
                await f.write(new_content)
            
            logger.info(f"Versione aggiornata in config.py: {self.current_version}")
            
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento della versione nel file di configurazione: {e}")
    
    def get_update_info(self) -> Dict[str, Any]:
        """
        Ottiene le informazioni sull'ultimo aggiornamento disponibile
        
        Returns:
            Dict: Informazioni sull'aggiornamento
        """
        if not self.last_update_info:
            return {
                "available": False,
                "current_version": self.current_version
            }
        
        return {
            "available": True,
            "current_version": self.current_version,
            "new_version": self.last_update_info.get("version"),
            "release_date": self.last_update_info.get("release_date"),
            "description": self.last_update_info.get("description"),
            "changelog": self.last_update_info.get("changelog")
        }
    
    async def restore_backup(self, backup_file: str) -> bool:
        """
        Ripristina un backup
        
        Args:
            backup_file: Percorso del file di backup
            
        Returns:
            bool: True se il ripristino è riuscito, False altrimenti
        """
        if self.updating:
            logger.warning("Un aggiornamento è già in corso")
            return False
        
        self.updating = True
        
        try:
            # Crea una directory temporanea per l'estrazione
            extract_dir = os.path.join(self.temp_dir, "backup_extract")
            os.makedirs(extract_dir, exist_ok=True)
            
            # Estrai il backup
            if shutil.which("7z"):
                cmd = ["7z", "x", backup_file, f"-o{extract_dir}", "-y"]
            else:
                cmd = ["unzip", "-o", backup_file, "-d", extract_dir]
            
            # Esegui il comando
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                logger.error(f"Errore nell'estrazione del backup: {stderr.decode()}")
                self.updating = False
                return False
            
            # Copia i file ripristinati
            logger.info("Ripristino dei file in corso...")
            
            # Trova la directory principale nel backup
            main_dir = extract_dir
            for item in os.listdir(extract_dir):
                item_path = os.path.join(extract_dir, item)
                if os.path.isdir(item_path) and "m4bot" in item.lower():
                    main_dir = item_path
                    break
            
            # Copia tutti i file nella directory di installazione
            def copy_recursively(src, dst):
                for item in os.listdir(src):
                    s = os.path.join(src, item)
                    d = os.path.join(dst, item)
                    
                    # Skip alcuni file speciali
                    if item in ["backups", "temp", "logs"]:
                        continue
                    
                    # Copia ricorsiva
                    if os.path.isdir(s):
                        os.makedirs(d, exist_ok=True)
                        copy_recursively(s, d)
                    else:
                        shutil.copy2(s, d)
            
            # Copia i file
            copy_recursively(main_dir, self.install_dir)
            
            # Pulisci la directory temporanea
            shutil.rmtree(extract_dir, ignore_errors=True)
            
            # Leggi la versione dal file di configurazione ripristinato
            config_file = os.path.join(self.install_dir, "bot", "config.py")
            
            if os.path.exists(config_file):
                async with aiofiles.open(config_file, "r") as f:
                    content = await f.read()
                
                # Estrai la versione
                for line in content.split("\n"):
                    if "VERSION = " in line:
                        version_match = line.strip().split("=")[1].strip()
                        if version_match:
                            self.current_version = version_match.strip('"\'')
                            break
            
            # Ripristino completato
            logger.info(f"Ripristino completato: {self.current_version}")
            self.updating = False
            return True
            
        except Exception as e:
            logger.error(f"Errore nel ripristino del backup: {e}")
            self.updating = False
            return False
    
    def get_available_backups(self) -> List[Dict[str, Any]]:
        """
        Ottiene la lista dei backup disponibili
        
        Returns:
            List: Lista dei backup disponibili
        """
        backups = []
        
        try:
            for item in os.listdir(self.backup_dir):
                if item.startswith("backup_") and item.endswith(".zip"):
                    file_path = os.path.join(self.backup_dir, item)
                    file_info = os.stat(file_path)
                    
                    # Estrai la versione e la data dal nome del file
                    parts = item.replace("backup_", "").replace(".zip", "").split("_")
                    version = parts[0] if len(parts) > 0 else "unknown"
                    timestamp = int(parts[1]) if len(parts) > 1 else 0
                    
                    backups.append({
                        "file": file_path,
                        "version": version,
                        "timestamp": timestamp,
                        "date": datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                        "size": file_info.st_size
                    })
            
            # Ordina i backup per data (dal più recente al più vecchio)
            backups.sort(key=lambda x: x["timestamp"], reverse=True)
            
            return backups
            
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dei backup disponibili: {e}")
            return []

# Funzione per creare un'istanza del sistema di aggiornamento automatico
def create_auto_updater(config: Dict[str, Any]) -> AutoUpdater:
    """
    Crea un'istanza del sistema di aggiornamento automatico
    
    Args:
        config: Configurazione del sistema di aggiornamento
        
    Returns:
        AutoUpdater: Istanza del sistema di aggiornamento automatico
    """
    return AutoUpdater(config)