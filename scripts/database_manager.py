#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import argparse
import datetime
import subprocess
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from typing import Optional, List, Dict, Any, Tuple

# Configurazione logger
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("db_manager")

class DatabaseManager:
    """Gestisce operazioni avanzate sul database PostgreSQL."""
    
    def __init__(self, db_url: Optional[str] = None, 
                 host: str = 'localhost', 
                 port: int = 5432,
                 user: str = 'postgres',
                 password: str = '',
                 database: str = 'postgres'):
        """
        Inizializza il gestore del database.
        
        Args:
            db_url: URL di connessione completo (precedenza su parametri singoli)
            host: Host del database
            port: Porta del database
            user: Nome utente
            password: Password
            database: Nome del database
        """
        self.db_url = db_url
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.database = database
        self.conn = None
        self.cursor = None
    
    def connect(self, admin_mode: bool = False) -> bool:
        """
        Stabilisce una connessione al database.
        
        Args:
            admin_mode: Se True, si connette al database postgres per amministrazione
            
        Returns:
            bool: True se la connessione è stata stabilita
        """
        try:
            if self.db_url:
                # Usa l'URL di connessione completo se fornito
                self.conn = psycopg2.connect(self.db_url)
            else:
                # Costruisci la connessione dai parametri
                connect_db = 'postgres' if admin_mode else self.database
                self.conn = psycopg2.connect(
                    host=self.host,
                    port=self.port,
                    user=self.user,
                    password=self.password,
                    database=connect_db
                )
            
            # Abilita autocommit per amministrazione
            if admin_mode:
                self.conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            
            self.cursor = self.conn.cursor()
            logger.info(f"Connessione al database {'postgres' if admin_mode else self.database} stabilita")
            return True
        except Exception as e:
            logger.error(f"Errore nella connessione al database: {e}")
            return False
    
    def disconnect(self) -> None:
        """Chiude la connessione al database."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
            logger.info("Connessione al database chiusa")
    
    def create_database(self, db_name: str) -> bool:
        """
        Crea un nuovo database.
        
        Args:
            db_name: Nome del database da creare
            
        Returns:
            bool: True se il database è stato creato
        """
        if not self.connect(admin_mode=True):
            return False
        
        try:
            # Verifica se il database esiste già
            self.cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
            )
            exists = self.cursor.fetchone()
            
            if not exists:
                # Crea il database
                self.cursor.execute(
                    sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(
                        sql.Identifier(db_name)
                    )
                )
                logger.info(f"Database {db_name} creato")
                return True
            else:
                logger.warning(f"Il database {db_name} esiste già")
                return False
        except Exception as e:
            logger.error(f"Errore nella creazione del database {db_name}: {e}")
            return False
        finally:
            self.disconnect()
    
    def create_user(self, username: str, password: str) -> bool:
        """
        Crea un nuovo utente PostgreSQL.
        
        Args:
            username: Nome utente
            password: Password
            
        Returns:
            bool: True se l'utente è stato creato
        """
        if not self.connect(admin_mode=True):
            return False
        
        try:
            # Verifica se l'utente esiste già
            self.cursor.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (username,)
            )
            exists = self.cursor.fetchone()
            
            if not exists:
                # Crea l'utente
                self.cursor.execute(
                    sql.SQL("CREATE USER {} WITH ENCRYPTED PASSWORD %s").format(
                        sql.Identifier(username)
                    ), (password,)
                )
                logger.info(f"Utente {username} creato")
                return True
            else:
                logger.warning(f"L'utente {username} esiste già")
                return False
        except Exception as e:
            logger.error(f"Errore nella creazione dell'utente {username}: {e}")
            return False
        finally:
            self.disconnect()
    
    def grant_privileges(self, db_name: str, username: str, privileges: List[str] = None) -> bool:
        """
        Concede privilegi su un database a un utente.
        
        Args:
            db_name: Nome del database
            username: Nome utente
            privileges: Lista dei privilegi da concedere
            
        Returns:
            bool: True se i privilegi sono stati concessi
        """
        if not privileges:
            privileges = ["ALL"]
        
        if not self.connect(admin_mode=True):
            return False
        
        try:
            privs = " ".join(privileges)
            self.cursor.execute(
                sql.SQL("GRANT {} ON DATABASE {} TO {}").format(
                    sql.SQL(privs),
                    sql.Identifier(db_name),
                    sql.Identifier(username)
                )
            )
            
            # Connettiti al database specifico per concedere privilegi su schemi e tabelle
            self.disconnect()
            
            # Riconnettiti al database specifico
            orig_database = self.database
            self.database = db_name
            if not self.connect():
                logger.error(f"Impossibile connettersi al database {db_name}")
                self.database = orig_database
                return False
            
            # Concedi privilegi su schema e tabelle esistenti
            self.cursor.execute(
                sql.SQL("GRANT ALL ON SCHEMA public TO {}").format(
                    sql.Identifier(username)
                )
            )
            
            self.cursor.execute(
                sql.SQL("GRANT ALL ON ALL TABLES IN SCHEMA public TO {}").format(
                    sql.Identifier(username)
                )
            )
            
            self.cursor.execute(
                sql.SQL("GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO {}").format(
                    sql.Identifier(username)
                )
            )
            
            # Configura privilegi default per tabelle future
            self.cursor.execute(
                sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO {}").format(
                    sql.Identifier(username)
                )
            )
            
            self.cursor.execute(
                sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO {}").format(
                    sql.Identifier(username)
                )
            )
            
            self.conn.commit()
            
            logger.info(f"Privilegi {privs} concessi a {username} su {db_name}")
            
            # Ripristina database originale
            self.database = orig_database
            return True
        except Exception as e:
            logger.error(f"Errore nella concessione dei privilegi: {e}")
            return False
        finally:
            self.disconnect()
    
    def create_backup(self, output_file: Optional[str] = None) -> Tuple[bool, str]:
        """
        Crea un backup del database.
        
        Args:
            output_file: Percorso del file di backup
            
        Returns:
            Tuple[bool, str]: (successo, percorso del file)
        """
        # Genera nome file se non fornito
        if not output_file:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = os.path.expanduser('~/.m4bot/backups/database')
            os.makedirs(backup_dir, exist_ok=True)
            output_file = os.path.join(backup_dir, f"{self.database}_{timestamp}.sql")
        
        try:
            # Costruisci comando pg_dump
            cmd = [
                "pg_dump",
                "-h", self.host,
                "-p", str(self.port),
                "-U", self.user,
                "-F", "c",  # Custom format
                "-b",  # Include large objects
                "-v",  # Verbose
                "-f", output_file,
                self.database
            ]
            
            # Imposta variabile d'ambiente per la password
            env = os.environ.copy()
            env["PGPASSWORD"] = self.password
            
            # Esegui pg_dump
            result = subprocess.run(
                cmd, 
                env=env, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"Backup del database {self.database} creato: {output_file}")
                return True, output_file
            else:
                logger.error(f"Errore nell'esecuzione di pg_dump: {result.stderr}")
                return False, ""
        except Exception as e:
            logger.error(f"Errore nella creazione del backup: {e}")
            return False, ""
    
    def restore_backup(self, backup_file: str, target_db: Optional[str] = None) -> bool:
        """
        Ripristina un backup del database.
        
        Args:
            backup_file: Percorso del file di backup
            target_db: Database di destinazione (opzionale)
            
        Returns:
            bool: True se il ripristino è avvenuto con successo
        """
        if not os.path.exists(backup_file):
            logger.error(f"File di backup {backup_file} non trovato")
            return False
        
        # Usa il database attuale se non specificato
        db_name = target_db or self.database
        
        try:
            # Verifica che il database esista
            if not self.connect(admin_mode=True):
                return False
            
            self.cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
            )
            exists = self.cursor.fetchone()
            
            if not exists:
                logger.error(f"Database {db_name} non esiste.")
                self.disconnect()
                return False
            
            self.disconnect()
            
            # Costruisci comando pg_restore
            cmd = [
                "pg_restore",
                "-h", self.host,
                "-p", str(self.port),
                "-U", self.user,
                "-d", db_name,
                "-v",  # Verbose
                "--clean",  # Pulisce prima del ripristino
                "--if-exists",  # Usa if exists nelle istruzioni DROP
                backup_file
            ]
            
            # Imposta variabile d'ambiente per la password
            env = os.environ.copy()
            env["PGPASSWORD"] = self.password
            
            # Esegui pg_restore
            result = subprocess.run(
                cmd, 
                env=env, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"Backup {backup_file} ripristinato nel database {db_name}")
                return True
            else:
                logger.warning(f"pg_restore completato con avvisi: {result.stderr}")
                return True  # Consideriamo comunque successo
        except Exception as e:
            logger.error(f"Errore nel ripristino del backup: {e}")
            return False
    
    def create_schema(self, schema_name: str) -> bool:
        """
        Crea un nuovo schema nel database.
        
        Args:
            schema_name: Nome dello schema
            
        Returns:
            bool: True se lo schema è stato creato
        """
        if not self.connect():
            return False
        
        try:
            # Verifica se lo schema esiste già
            self.cursor.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", 
                (schema_name,)
            )
            exists = self.cursor.fetchone()
            
            if not exists:
                # Crea lo schema
                self.cursor.execute(
                    sql.SQL("CREATE SCHEMA {}").format(
                        sql.Identifier(schema_name)
                    )
                )
                self.conn.commit()
                logger.info(f"Schema {schema_name} creato")
                return True
            else:
                logger.warning(f"Lo schema {schema_name} esiste già")
                return False
        except Exception as e:
            logger.error(f"Errore nella creazione dello schema {schema_name}: {e}")
            self.conn.rollback()
            return False
        finally:
            self.disconnect()
    
    def optimize_database(self) -> bool:
        """
        Esegue operazioni di ottimizzazione sul database.
        
        Returns:
            bool: True se le ottimizzazioni sono state completate
        """
        if not self.connect():
            return False
        
        try:
            # VACUUM ANALYZE per ottimizzare l'esecuzione delle query
            logger.info(f"Avvio VACUUM ANALYZE sul database {self.database}")
            old_isolation_level = self.conn.isolation_level
            self.conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            self.cursor.execute("VACUUM ANALYZE")
            
            # Ottimizza gli indici
            logger.info("Ricostruzione indici")
            self.cursor.execute(
                """
                SELECT 'REINDEX INDEX ' || string_agg(indexrelid::regclass::text, ', ')
                FROM pg_stat_user_indexes 
                WHERE idx_scan = 0 AND idx_tup_read = 0 AND idx_tup_fetch = 0
                """
            )
            result = self.cursor.fetchone()
            
            if result and result[0]:
                reindex_cmd = result[0]
                self.cursor.execute(reindex_cmd)
                logger.info("Indici inutilizzati ricostruiti")
            
            # Ripristina il livello di isolamento
            self.conn.set_isolation_level(old_isolation_level)
            
            logger.info(f"Ottimizzazione del database {self.database} completata")
            return True
        except Exception as e:
            logger.error(f"Errore nell'ottimizzazione del database: {e}")
            return False
        finally:
            self.disconnect()
    
    def get_database_size(self) -> Tuple[bool, str]:
        """
        Ottiene la dimensione del database.
        
        Returns:
            Tuple[bool, str]: (successo, dimensione formattata)
        """
        if not self.connect():
            return False, ""
        
        try:
            self.cursor.execute(
                "SELECT pg_size_pretty(pg_database_size(%s))", 
                (self.database,)
            )
            size = self.cursor.fetchone()[0]
            logger.info(f"Dimensione del database {self.database}: {size}")
            return True, size
        except Exception as e:
            logger.error(f"Errore nel recupero della dimensione del database: {e}")
            return False, ""
        finally:
            self.disconnect()
    
    def get_table_sizes(self) -> Tuple[bool, Dict[str, str]]:
        """
        Ottiene le dimensioni delle tabelle nel database.
        
        Returns:
            Tuple[bool, Dict[str, str]]: (successo, dizionario tabella -> dimensione)
        """
        if not self.connect():
            return False, {}
        
        try:
            self.cursor.execute(
                """
                SELECT 
                    table_name, 
                    pg_size_pretty(pg_total_relation_size('"' || table_schema || '"."' || table_name || '"')) as size
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY pg_total_relation_size('"' || table_schema || '"."' || table_name || '"') DESC
                """
            )
            results = self.cursor.fetchall()
            
            table_sizes = {row[0]: row[1] for row in results}
            logger.info(f"Dimensioni delle tabelle recuperate ({len(table_sizes)} tabelle)")
            return True, table_sizes
        except Exception as e:
            logger.error(f"Errore nel recupero delle dimensioni delle tabelle: {e}")
            return False, {}
        finally:
            self.disconnect()
    
    def execute_sql_file(self, sql_file: str) -> bool:
        """
        Esegue un file SQL sul database.
        
        Args:
            sql_file: Percorso del file SQL
            
        Returns:
            bool: True se l'esecuzione è completata con successo
        """
        if not os.path.exists(sql_file):
            logger.error(f"File SQL {sql_file} non trovato")
            return False
        
        try:
            # Costruisci comando psql
            cmd = [
                "psql",
                "-h", self.host,
                "-p", str(self.port),
                "-U", self.user,
                "-d", self.database,
                "-f", sql_file
            ]
            
            # Imposta variabile d'ambiente per la password
            env = os.environ.copy()
            env["PGPASSWORD"] = self.password
            
            # Esegui psql
            result = subprocess.run(
                cmd, 
                env=env, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0:
                logger.info(f"File SQL {sql_file} eseguito con successo")
                return True
            else:
                logger.error(f"Errore nell'esecuzione del file SQL: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"Errore nell'esecuzione del file SQL: {e}")
            return False

# Funzioni per l'interfaccia a riga di comando
def backup_command(args):
    """Gestisce il comando di backup."""
    db_manager = DatabaseManager(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database
    )
    
    success, backup_file = db_manager.create_backup(args.output)
    
    if success:
        print(f"Backup creato: {backup_file}")
        return 0
    else:
        print("Errore nella creazione del backup")
        return 1

def restore_command(args):
    """Gestisce il comando di ripristino."""
    db_manager = DatabaseManager(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database
    )
    
    if db_manager.restore_backup(args.backup_file, args.target_db):
        print(f"Backup {args.backup_file} ripristinato")
        return 0
    else:
        print("Errore nel ripristino del backup")
        return 1

def optimize_command(args):
    """Gestisce il comando di ottimizzazione."""
    db_manager = DatabaseManager(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database
    )
    
    if db_manager.optimize_database():
        print(f"Database {args.database} ottimizzato")
        return 0
    else:
        print("Errore nell'ottimizzazione del database")
        return 1

def create_db_command(args):
    """Gestisce il comando di creazione del database."""
    db_manager = DatabaseManager(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password
    )
    
    if db_manager.create_database(args.name):
        print(f"Database {args.name} creato")
        
        if args.grant:
            if db_manager.grant_privileges(args.name, args.grant):
                print(f"Privilegi concessi a {args.grant}")
            else:
                print(f"Errore nella concessione dei privilegi a {args.grant}")
        
        return 0
    else:
        print(f"Errore nella creazione del database {args.name}")
        return 1

def create_user_command(args):
    """Gestisce il comando di creazione dell'utente."""
    db_manager = DatabaseManager(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password
    )
    
    if db_manager.create_user(args.username, args.password):
        print(f"Utente {args.username} creato")
        return 0
    else:
        print(f"Errore nella creazione dell'utente {args.username}")
        return 1

def size_command(args):
    """Gestisce il comando per ottenere le dimensioni."""
    db_manager = DatabaseManager(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database
    )
    
    if args.tables:
        success, sizes = db_manager.get_table_sizes()
        if success:
            print(f"Dimensioni delle tabelle nel database {args.database}:")
            for table, size in sizes.items():
                print(f"{table}: {size}")
            return 0
        else:
            print("Errore nel recupero delle dimensioni delle tabelle")
            return 1
    else:
        success, size = db_manager.get_database_size()
        if success:
            print(f"Dimensione del database {args.database}: {size}")
            return 0
        else:
            print("Errore nel recupero della dimensione del database")
            return 1

def execute_command(args):
    """Gestisce il comando per eseguire SQL."""
    db_manager = DatabaseManager(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database
    )
    
    if db_manager.execute_sql_file(args.file):
        print(f"File SQL {args.file} eseguito")
        return 0
    else:
        print(f"Errore nell'esecuzione del file SQL {args.file}")
        return 1

def main():
    """Funzione principale per l'interfaccia a riga di comando."""
    parser = argparse.ArgumentParser(description="Gestore database PostgreSQL per M4Bot")
    
    # Parametri comuni
    parent_parser = argparse.ArgumentParser(add_help=False)
    parent_parser.add_argument('--host', default='localhost', help="Host del database")
    parent_parser.add_argument('--port', type=int, default=5432, help="Porta del database")
    parent_parser.add_argument('--user', default='postgres', help="Nome utente")
    parent_parser.add_argument('--password', default='', help="Password")
    parent_parser.add_argument('--database', default='postgres', help="Nome del database")
    
    # Sottoparsers per i comandi
    subparsers = parser.add_subparsers(dest='command', help='Comando da eseguire')
    
    # Comando backup
    backup_parser = subparsers.add_parser('backup', parents=[parent_parser], help='Crea un backup del database')
    backup_parser.add_argument('--output', help='Percorso file di output (opzionale)')
    
    # Comando restore
    restore_parser = subparsers.add_parser('restore', parents=[parent_parser], help='Ripristina un backup del database')
    restore_parser.add_argument('backup_file', help='Percorso del file di backup')
    restore_parser.add_argument('--target-db', help='Database di destinazione (opzionale)')
    
    # Comando optimize
    optimize_parser = subparsers.add_parser('optimize', parents=[parent_parser], help='Ottimizza il database')
    
    # Comando create-db
    create_db_parser = subparsers.add_parser('create-db', parents=[parent_parser], help='Crea un nuovo database')
    create_db_parser.add_argument('name', help='Nome del database')
    create_db_parser.add_argument('--grant', help='Utente a cui concedere privilegi (opzionale)')
    
    # Comando create-user
    create_user_parser = subparsers.add_parser('create-user', parents=[parent_parser], help='Crea un nuovo utente')
    create_user_parser.add_argument('username', help='Nome utente')
    create_user_parser.add_argument('--password', required=True, help='Password')
    
    # Comando size
    size_parser = subparsers.add_parser('size', parents=[parent_parser], help='Ottieni dimensioni del database')
    size_parser.add_argument('--tables', action='store_true', help='Mostra dimensioni delle tabelle')
    
    # Comando execute
    execute_parser = subparsers.add_parser('execute', parents=[parent_parser], help='Esegue un file SQL')
    execute_parser.add_argument('file', help='Percorso del file SQL')
    
    # Parsing argomenti
    args = parser.parse_args()
    
    # Esegui comando
    if args.command == 'backup':
        return backup_command(args)
    elif args.command == 'restore':
        return restore_command(args)
    elif args.command == 'optimize':
        return optimize_command(args)
    elif args.command == 'create-db':
        return create_db_command(args)
    elif args.command == 'create-user':
        return create_user_command(args)
    elif args.command == 'size':
        return size_command(args)
    elif args.command == 'execute':
        return execute_command(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main()) 