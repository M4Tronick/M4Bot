#!/usr/bin/env python3
"""
M4Bot - Security Enhancements Module

Questo modulo implementa funzionalità di sicurezza avanzate per proteggere l'infrastruttura
di M4Bot da minacce esterne e garantire la stabilità del servizio:

1. Protezione contro attacchi DDoS
2. Sistema di rilevamento intrusioni (IDS)
3. Monitoraggio firewall avanzato
4. Protezione SSH con chiavi e 2FA
5. Gestione automatica dei certificati SSL/TLS
6. Scansione vulnerabilità
7. Sandbox per esecuzione sicura
8. Backup crittografati

Questo modulo si integra con il WAF esistente e altre componenti di sicurezza
"""

import os
import sys
import json
import time
import logging
import subprocess
import ipaddress
import hashlib
import socket
import asyncio
import datetime
import ssl
import re
from typing import Dict, List, Set, Tuple, Any, Optional, Callable, Union
from functools import wraps
from pathlib import Path

# Importazioni di moduli esterni con gestione delle eccezioni
try:
    import requests
    import aiohttp
    import cryptography
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    import pyotp
    import qrcode
    from PIL import Image
except ImportError as e:
    print(f"Errore: modulo mancante - {e}")
    print("Esegui: pip install requests aiohttp cryptography pyotp qrcode pillow")
    sys.exit(1)

# Configurazione del logging
logger = logging.getLogger("m4bot.security.enhancements")
logger.setLevel(logging.INFO)

# Constants
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "security_config.json")
DEFAULT_CONFIG = {
    "ddos_protection": {
        "enabled": True,
        "rate_threshold": 100,  # richieste al secondo
        "burst_threshold": 30,   # richieste in burst
        "block_duration": 300,   # durata del blocco in secondi
        "whitelist": ["127.0.0.1"]
    },
    "intrusion_detection": {
        "enabled": True,
        "log_suspicious": True,
        "auto_block": True,
        "notify_admin": True,
        "scan_interval": 300     # intervallo di scansione in secondi
    },
    "firewall": {
        "enabled": True,
        "default_policy": "DROP",
        "allowed_ports": [22, 80, 443, 8000, 8080],
        "custom_rules": []
    },
    "ssh_protection": {
        "enabled": True,
        "max_tries": 3,
        "use_key_only": True,
        "use_2fa": True,
        "allowed_users": ["admin", "m4bot"]
    },
    "ssl_tls": {
        "enabled": True,
        "auto_renew": True,
        "min_version": "TLSv1.2",
        "preferred_ciphers": "HIGH:!aNULL:!MD5:!RC4",
        "hsts_enabled": True,
        "ocsp_stapling": True
    },
    "vuln_scanner": {
        "enabled": True,
        "scan_interval": 86400,  # scansione giornaliera (in secondi)
        "auto_patch": False,     # richiede approvazione manuale
        "scan_depth": "standard" # standard, deep, quick
    },
    "sandbox": {
        "enabled": True,
        "resource_limits": {
            "cpu": 50,           # percentuale massima CPU
            "memory": 512,       # MB di RAM massima
            "disk": 1024,        # MB di spazio disco massimo
            "time": 30           # secondi massimi di esecuzione
        }
    },
    "backup": {
        "enabled": True,
        "encrypted": True,
        "interval": 86400,       # backup giornaliero (in secondi)
        "retention": 30,         # giorni di conservazione
        "locations": ["local", "remote"],
        "remote_url": ""         # URL per backup remoto
    }
}

# Classe principale per la gestione della sicurezza avanzata
class SecurityEnhancer:
    def __init__(self, config_path: str = CONFIG_PATH):
        """Inizializza il sistema di sicurezza avanzata"""
        self.config = self._load_config(config_path)
        self.ddos_tracker = {}  # {ip: [timestamp1, timestamp2, ...]}
        self.blocked_ips = set()
        self.temp_blocks = {}   # {ip: expire_time}
        self.ids_events = []    # eventi di intrusione rilevati
        self.scan_results = {}  # risultati delle scansioni
        self.initialized = False
        self._encryption_key = None
        
        # Carica o genera la chiave di crittografia
        self._load_or_generate_key()
        
    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Carica la configurazione o crea il file di default"""
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    return config
            except Exception as e:
                logger.error(f"Errore nel caricamento del file di configurazione: {e}")
        
        # Crea il file di configurazione predefinito
        try:
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            with open(config_path, 'w') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            logger.info(f"Creato nuovo file di configurazione in {config_path}")
            return DEFAULT_CONFIG.copy()
        except Exception as e:
            logger.error(f"Impossibile creare il file di configurazione: {e}")
            return DEFAULT_CONFIG.copy()
    
    def _load_or_generate_key(self) -> None:
        """Carica o genera una chiave di crittografia per le operazioni sicure"""
        key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".security_key")
        
        if os.path.exists(key_path):
            try:
                with open(key_path, 'rb') as f:
                    self._encryption_key = f.read()
                logger.info("Chiave di crittografia caricata")
            except Exception as e:
                logger.error(f"Errore nel caricamento della chiave: {e}")
                self._generate_new_key(key_path)
        else:
            logger.info("Chiave di crittografia non trovata, generazione in corso...")
            self._generate_new_key(key_path)
    
    def _generate_new_key(self, key_path: str) -> None:
        """Genera una nuova chiave di crittografia"""
        try:
            self._encryption_key = Fernet.generate_key()
            
            # Salva la chiave in modo sicuro
            os.makedirs(os.path.dirname(key_path), exist_ok=True)
            with open(key_path, 'wb') as f:
                f.write(self._encryption_key)
            
            # Imposta permessi appropriati
            os.chmod(key_path, 0o600)  # Solo il proprietario può leggere/scrivere
            
            logger.info("Nuova chiave di crittografia generata")
        except Exception as e:
            logger.error(f"Errore nella generazione della chiave: {e}")
            # Genera una chiave in memoria anche se non possiamo salvarla
            self._encryption_key = Fernet.generate_key()
    
    def encrypt_data(self, data: Union[str, bytes]) -> bytes:
        """Crittografa dati sensibili"""
        if not self._encryption_key:
            raise ValueError("Chiave di crittografia non disponibile")
        
        f = Fernet(self._encryption_key)
        if isinstance(data, str):
            return f.encrypt(data.encode('utf-8'))
        return f.encrypt(data)
    
    def decrypt_data(self, encrypted_data: bytes) -> bytes:
        """Decrittografa dati sensibili"""
        if not self._encryption_key:
            raise ValueError("Chiave di crittografia non disponibile")
        
        f = Fernet(self._encryption_key)
        return f.decrypt(encrypted_data)
    
    def initialize(self) -> bool:
        """Inizializza tutti i sistemi di sicurezza"""
        if self.initialized:
            return True
            
        success = True
        logger.info("Inizializzazione dei sistemi di sicurezza avanzata...")
        
        try:
            # Inizializza i vari moduli di protezione
            if self.config["ddos_protection"]["enabled"]:
                self._setup_ddos_protection()
            
            if self.config["intrusion_detection"]["enabled"]:
                self._setup_intrusion_detection()
            
            if self.config["firewall"]["enabled"]:
                self._setup_firewall()
            
            if self.config["ssh_protection"]["enabled"]:
                self._setup_ssh_protection()
            
            if self.config["ssl_tls"]["enabled"]:
                self._setup_ssl_tls()
            
            if self.config["vuln_scanner"]["enabled"]:
                self._setup_vulnerability_scanner()
            
            if self.config["sandbox"]["enabled"]:
                self._setup_sandbox()
            
            if self.config["backup"]["enabled"]:
                self._setup_backup()
            
            self.initialized = True
            logger.info("Inizializzazione dei sistemi di sicurezza completata")
            
        except Exception as e:
            logger.error(f"Errore durante l'inizializzazione: {e}")
            success = False
        
        return success
    
    # Implementazione dei sistemi di protezione
    def _setup_ddos_protection(self) -> None:
        """Configura la protezione DDoS"""
        logger.info("Configurazione protezione DDoS...")
        
        # Aggiunge IP in whitelist
        for ip in self.config["ddos_protection"]["whitelist"]:
            self.add_to_whitelist(ip)
        
        # Qui si potrebbero configurare regole iptables/firewall server
        if self._is_linux():
            try:
                # Configura fail2ban per protezione base
                self._run_command("systemctl status fail2ban")
                logger.info("fail2ban attivo per protezione di base")
            except:
                logger.warning("fail2ban non disponibile, considerare l'installazione")
    
    def _setup_intrusion_detection(self) -> None:
        """Configura il sistema di rilevamento intrusioni"""
        logger.info("Configurazione sistema IDS...")
        
        # Qui possiamo configurare regole di rilevamento specifiche
        if self._is_linux():
            try:
                # Verifica se OSSEC o altri IDS sono installati
                self._run_command("systemctl status ossec")
                logger.info("OSSEC HIDS attivo")
            except:
                logger.warning("OSSEC non disponibile, utilizzando rilevamento interno")
    
    def _setup_firewall(self) -> None:
        """Configura il firewall"""
        logger.info("Configurazione firewall...")
        
        if self._is_linux():
            try:
                # Configura UFW se disponibile
                self._run_command("ufw status")
                
                # Apri porte necessarie
                for port in self.config["firewall"]["allowed_ports"]:
                    self._run_command(f"ufw allow {port}/tcp")
                
                logger.info("Firewall UFW configurato")
            except:
                logger.warning("UFW non disponibile, considerare la configurazione manuale")
    
    def _setup_ssh_protection(self) -> None:
        """Configura la protezione SSH"""
        logger.info("Configurazione protezione SSH...")
        
        if self._is_linux():
            sshd_config = "/etc/ssh/sshd_config"
            if os.path.exists(sshd_config):
                # Backup della configurazione originale
                backup_path = f"{sshd_config}.bak"
                if not os.path.exists(backup_path):
                    self._run_command(f"cp {sshd_config} {backup_path}")
                
                # Modifica configurazione
                ssh_settings = [
                    "PermitRootLogin no",
                    "PasswordAuthentication no" if self.config["ssh_protection"]["use_key_only"] else "",
                    "MaxAuthTries 3",
                    "ClientAliveInterval 300",
                    "ClientAliveCountMax 0"
                ]
                
                # Applica configurazione
                for setting in ssh_settings:
                    if setting:
                        self._modify_ssh_config(sshd_config, setting)
                
                logger.info("Configurazione SSH protetta applicata")
            else:
                logger.warning("File di configurazione SSH non trovato")
    
    def _setup_ssl_tls(self) -> None:
        """Configura SSL/TLS"""
        logger.info("Configurazione SSL/TLS...")
        
        if self._is_linux():
            try:
                # Verifica presenza di certbot per Let's Encrypt
                self._run_command("certbot --version")
                logger.info("Certbot disponibile per gestione certificati")
                
                # Verifica stato certificati
                self._check_ssl_certificates()
            except:
                logger.warning("Certbot non disponibile, considerare l'installazione")
    
    def _setup_vulnerability_scanner(self) -> None:
        """Configura lo scanner di vulnerabilità"""
        logger.info("Configurazione scanner vulnerabilità...")
        
        # Implementare la logica per scansione regolare
        self.scan_results = {
            "last_scan": None,
            "vulnerabilities": []
        }
    
    def _setup_sandbox(self) -> None:
        """Configura l'ambiente sandbox"""
        logger.info("Configurazione ambiente sandbox...")
        
        # Qui possiamo configurare container o ambienti isolati
        if self._is_linux():
            try:
                # Verifica Docker o altri sistemi di container
                self._run_command("docker --version")
                logger.info("Docker disponibile per ambienti sandbox")
            except:
                logger.warning("Docker non disponibile, considerare l'installazione")
    
    def _setup_backup(self) -> None:
        """Configura il sistema di backup crittografato"""
        logger.info("Configurazione sistema di backup...")
        
        # Crea directory di backup
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        logger.info(f"Directory per backup configurata: {backup_dir}")
    
    # Modifiche alla configurazione SSH
    def _modify_ssh_config(self, config_file: str, setting: str) -> None:
        """Modifica il file di configurazione SSH"""
        key = setting.split()[0]
        
        try:
            with open(config_file, 'r') as f:
                lines = f.readlines()
            
            # Cerca se l'impostazione esiste già
            found = False
            for i, line in enumerate(lines):
                if line.strip() and line.strip()[0] != '#' and line.strip().startswith(key):
                    lines[i] = f"{setting}\n"
                    found = True
                    break
            
            # Aggiungi l'impostazione se non esiste
            if not found:
                lines.append(f"{setting}\n")
            
            # Scrivi la configurazione aggiornata
            with open(config_file, 'w') as f:
                f.writelines(lines)
                
        except Exception as e:
            logger.error(f"Errore nella modifica della configurazione SSH: {e}")
    
    # Verifica certificati SSL
    def _check_ssl_certificates(self) -> None:
        """Verifica lo stato dei certificati SSL"""
        try:
            result = self._run_command("certbot certificates")
            
            # Analizza il risultato per trovare certificati in scadenza
            if "No certificates found" in result:
                logger.warning("Nessun certificato trovato")
            else:
                # Processa l'output per trovare le date di scadenza
                expiry_match = re.findall(r"Expiry Date: (\d{4}-\d{2}-\d{2})", result)
                
                if expiry_match:
                    # Converte le date in oggetti datetime
                    for expiry_str in expiry_match:
                        expiry_date = datetime.datetime.strptime(expiry_str, "%Y-%m-%d")
                        days_left = (expiry_date - datetime.datetime.now()).days
                        
                        if days_left < 30:
                            logger.warning(f"Certificato in scadenza tra {days_left} giorni")
                            
                            # Se il rinnovo automatico è abilitato
                            if self.config["ssl_tls"]["auto_renew"] and days_left < 15:
                                logger.info("Avvio rinnovo automatico certificati")
                                self._run_command("certbot renew")
        except Exception as e:
            logger.error(f"Errore nella verifica dei certificati: {e}")
    
    # Utilità per l'esecuzione di comandi
    def _run_command(self, command: str) -> str:
        """Esegue un comando di sistema"""
        try:
            process = subprocess.Popen(
                command.split(), 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE
            )
            stdout, stderr = process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Errore nell'esecuzione del comando {command}: {stderr.decode()}")
                raise Exception(stderr.decode())
                
            return stdout.decode()
        except Exception as e:
            logger.error(f"Impossibile eseguire il comando {command}: {e}")
            raise
    
    def _is_linux(self) -> bool:
        """Verifica se il sistema operativo è Linux"""
        return sys.platform.startswith("linux")
    
    # API pubblica
    def add_to_whitelist(self, ip: str) -> bool:
        """Aggiunge un IP alla whitelist"""
        try:
            # Valida l'IP
            ipaddress.ip_address(ip)
            self.config["ddos_protection"]["whitelist"].append(ip)
            return True
        except ValueError:
            logger.error(f"Indirizzo IP non valido: {ip}")
            return False
    
    def check_ip(self, ip: str, request_info: Optional[Dict[str, Any]] = None) -> bool:
        """
        Verifica se un IP è autorizzato o potenzialmente malevolo
        Ritorna True se l'IP è sicuro, False altrimenti
        """
        # Controlla se l'IP è in whitelist
        if ip in self.config["ddos_protection"]["whitelist"]:
            return True
        
        # Controlla se l'IP è bloccato permanentemente
        if ip in self.blocked_ips:
            return False
        
        # Controlla blocchi temporanei
        if ip in self.temp_blocks and self.temp_blocks[ip] > time.time():
            return False
        
        # Rimuovi blocchi temporanei scaduti
        if ip in self.temp_blocks and self.temp_blocks[ip] <= time.time():
            del self.temp_blocks[ip]
        
        # Controlla protezione DDoS
        if self.config["ddos_protection"]["enabled"]:
            # Inizializza cronologia richieste se non esiste
            if ip not in self.ddos_tracker:
                self.ddos_tracker[ip] = []
            
            # Aggiungi timestamp corrente
            current_time = time.time()
            self.ddos_tracker[ip].append(current_time)
            
            # Rimuovi timestamp vecchi (>60 secondi)
            self.ddos_tracker[ip] = [ts for ts in self.ddos_tracker[ip] 
                                    if current_time - ts <= 60]
            
            # Verifica rate limit
            requests_per_minute = len(self.ddos_tracker[ip])
            if requests_per_minute > self.config["ddos_protection"]["rate_threshold"]:
                logger.warning(f"Potenziale attacco DDoS da {ip}: {requests_per_minute} req/min")
                
                # Blocca temporaneamente
                self.temp_blocks[ip] = current_time + self.config["ddos_protection"]["block_duration"]
                
                # Aggiungi all'elenco eventi IDS
                if self.config["intrusion_detection"]["enabled"]:
                    self.ids_events.append({
                        "timestamp": datetime.datetime.now().isoformat(),
                        "ip": ip,
                        "type": "DDoS",
                        "details": f"{requests_per_minute} requests/minute",
                        "severity": "high"
                    })
                
                return False
        
        # Aggiungi qui altre verifiche di sicurezza
        
        return True
    
    def block_ip(self, ip: str, permanent: bool = False, duration: int = 300) -> bool:
        """Blocca un IP"""
        try:
            # Valida l'IP
            ipaddress.ip_address(ip)
            
            if permanent:
                self.blocked_ips.add(ip)
                logger.info(f"IP {ip} bloccato permanentemente")
                
                # Se siamo su Linux, aggiungi alle regole iptables
                if self._is_linux():
                    try:
                        self._run_command(f"iptables -A INPUT -s {ip} -j DROP")
                    except Exception as e:
                        logger.error(f"Impossibile aggiungere regola iptables: {e}")
            else:
                self.temp_blocks[ip] = time.time() + duration
                logger.info(f"IP {ip} bloccato temporaneamente per {duration} secondi")
            
            return True
        except ValueError:
            logger.error(f"Indirizzo IP non valido: {ip}")
            return False
    
    def unblock_ip(self, ip: str) -> bool:
        """Sblocca un IP"""
        try:
            # Valida l'IP
            ipaddress.ip_address(ip)
            
            if ip in self.blocked_ips:
                self.blocked_ips.remove(ip)
                
                # Se siamo su Linux, rimuovi dalle regole iptables
                if self._is_linux():
                    try:
                        self._run_command(f"iptables -D INPUT -s {ip} -j DROP")
                    except Exception as e:
                        logger.error(f"Impossibile rimuovere regola iptables: {e}")
            
            if ip in self.temp_blocks:
                del self.temp_blocks[ip]
            
            logger.info(f"IP {ip} sbloccato")
            return True
        except ValueError:
            logger.error(f"Indirizzo IP non valido: {ip}")
            return False
    
    def scan_for_vulnerabilities(self) -> Dict[str, Any]:
        """Esegue una scansione vulnerabilità del sistema"""
        logger.info("Avvio scansione vulnerabilità...")
        vulns = []
        
        # Implementa qui la logica di scansione
        # In una versione reale, qui potremmo richiamare nmap, OpenVAS, ecc.
        
        # Esempio di vulnerabilità rilevata
        vulns.append({
            "severity": "medium",
            "name": "OpenSSH version",
            "description": "La versione di OpenSSH potrebbe essere obsoleta",
            "remediation": "Aggiornare OpenSSH all'ultima versione stabile"
        })
        
        # Aggiorna i risultati
        self.scan_results = {
            "last_scan": datetime.datetime.now().isoformat(),
            "vulnerabilities": vulns
        }
        
        logger.info(f"Scansione completata: trovate {len(vulns)} vulnerabilità")
        return self.scan_results
    
    def create_encrypted_backup(self, data: bytes, filename: str) -> str:
        """Crea un backup crittografato dei dati"""
        encrypted_data = self.encrypt_data(data)
        
        # Imposta percorso del backup
        backup_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(backup_dir, f"{filename}_{timestamp}.enc")
        
        # Salva il backup
        with open(backup_path, "wb") as f:
            f.write(encrypted_data)
        
        logger.info(f"Backup crittografato creato: {backup_path}")
        return backup_path
    
    def restore_from_backup(self, backup_path: str) -> bytes:
        """Ripristina i dati da un backup crittografato"""
        if not os.path.exists(backup_path):
            raise FileNotFoundError(f"Backup non trovato: {backup_path}")
        
        try:
            with open(backup_path, "rb") as f:
                encrypted_data = f.read()
            
            decrypted_data = self.decrypt_data(encrypted_data)
            logger.info(f"Dati ripristinati dal backup: {backup_path}")
            return decrypted_data
        except Exception as e:
            logger.error(f"Errore nel ripristino del backup: {e}")
            raise
    
    def generate_2fa_code(self, user: str) -> Tuple[str, str]:
        """Genera un codice 2FA e un URL QR"""
        # Genera una chiave segreta
        secret = pyotp.random_base32()
        
        # Crea un URL TOTP
        totp = pyotp.TOTP(secret)
        provisioning_url = totp.provisioning_uri(
            name=user,
            issuer_name="M4Bot Admin"
        )
        
        return secret, provisioning_url
    
    def verify_2fa_code(self, secret: str, code: str) -> bool:
        """Verifica un codice 2FA"""
        totp = pyotp.TOTP(secret)
        return totp.verify(code)
    
    def get_security_status(self) -> Dict[str, Any]:
        """Ottiene lo stato attuale della sicurezza"""
        return {
            "initialized": self.initialized,
            "ddos_protection": self.config["ddos_protection"]["enabled"],
            "intrusion_detection": self.config["intrusion_detection"]["enabled"],
            "firewall": self.config["firewall"]["enabled"],
            "ssh_protection": self.config["ssh_protection"]["enabled"],
            "ssl_tls": self.config["ssl_tls"]["enabled"],
            "vuln_scanner": self.config["vuln_scanner"]["enabled"],
            "sandbox": self.config["sandbox"]["enabled"],
            "backup": self.config["backup"]["enabled"],
            "blocked_ips": len(self.blocked_ips),
            "temporary_blocks": len(self.temp_blocks),
            "ids_events": len(self.ids_events),
            "last_scan": self.scan_results.get("last_scan")
        }

# Inizializzazione del modulo
def initialize() -> SecurityEnhancer:
    """Inizializza e restituisce l'istanza del SecurityEnhancer"""
    enhancer = SecurityEnhancer()
    enhancer.initialize()
    return enhancer

# Wrapper per protezione route
def protect_route(security_enhancer: SecurityEnhancer):
    """Decorator per proteggere route con controlli di sicurezza"""
    def decorator(f):
        @wraps(f)
        async def decorated_function(*args, **kwargs):
            # Ottiene l'IP del client dalla richiesta
            from quart import request
            client_ip = request.remote_addr
            
            # Verifica l'IP
            if not security_enhancer.check_ip(client_ip, {}):
                # IP bloccato, nega l'accesso
                from quart import abort
                abort(403, "Accesso negato")
            
            # Procedi con la funzione originale
            return await f(*args, **kwargs)
        return decorated_function
    return decorator

# Singola istanza (pattern singleton)
_instance = None

def get_instance():
    """Restituisce l'istanza singleton del SecurityEnhancer"""
    global _instance
    if _instance is None:
        _instance = initialize()
    return _instance

# API di alto livello per sicurezza avanzata
def check_request_security(request) -> bool:
    """Verifica la sicurezza di una richiesta HTTP"""
    enhancer = get_instance()
    return enhancer.check_ip(request.remote_addr)

def make_secure_backup(data, name):
    """Crea un backup sicuro dei dati"""
    enhancer = get_instance()
    return enhancer.create_encrypted_backup(data, name)

if __name__ == "__main__":
    # Configurazione logging per test
    logging.basicConfig(level=logging.INFO)
    
    print("Test del modulo di sicurezza avanzata")
    security = initialize()
    
    # Test di alcune funzionalità
    security.add_to_whitelist("192.168.1.1")
    security.block_ip("10.0.0.1", duration=60)
    
    status = security.get_security_status()
    print(f"Stato sicurezza: {json.dumps(status, indent=2)}")
    
    # Genera codice 2FA di test
    secret, url = security.generate_2fa_code("admin")
    print(f"Chiave 2FA: {secret}")
    print(f"URL provisioning: {url}")
    
    # Genera un codice valido
    totp = pyotp.TOTP(secret)
    code = totp.now()
    print(f"Codice corrente: {code}")
    
    # Verifica il codice
    is_valid = security.verify_2fa_code(secret, code)
    print(f"Codice valido: {is_valid}")
    
    print("Test completato") 