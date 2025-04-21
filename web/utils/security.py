"""
Utilità di sicurezza per M4Bot.

Questo modulo fornisce funzioni per migliorare la sicurezza dell'applicazione,
inclusi controlli sulla sicurezza delle password, CSRF, e altre protezioni.
"""

import re
import hashlib
import secrets
import logging
import ipaddress
from typing import Dict, List, Set, Tuple, Any, Optional, Union
from datetime import datetime, timedelta

# Configurazione del logging
logger = logging.getLogger('m4bot.security')

# Configurazione base
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_AGE_DAYS = 90  # Giorni dopo i quali chiedere di cambiare password
MAX_FAILED_ATTEMPTS = 5  # Tentativi di login falliti prima di bloccare l'account
ACCOUNT_LOCKOUT_DURATION = 30  # Minuti di blocco account dopo troppi tentativi falliti
PASSWORD_HISTORY_SIZE = 5  # Numero di password precedenti da memorizzare (per evitare riutilizzo)

# Liste di password deboli/comuni da evitare
COMMON_PASSWORDS = set([
    "password", "123456", "123456789", "qwerty", "abc123", "football", 
    "1234567", "welcome", "1234567890", "admin", "password1"
])

def generate_csrf_token() -> str:
    """
    Genera un token CSRF sicuro.
    
    Returns:
        str: Token CSRF
    """
    return secrets.token_hex(32)

def check_password_strength(password: str) -> Tuple[bool, str, int]:
    """
    Controlla la forza di una password.
    
    Args:
        password: La password da controllare
        
    Returns:
        Tuple[bool, str, int]: (è_sicura, messaggio, punteggio)
    """
    # Controlla lunghezza minima
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"La password deve essere di almeno {PASSWORD_MIN_LENGTH} caratteri", 0
    
    # Controlla se è una password comune
    if password.lower() in COMMON_PASSWORDS:
        return False, "La password è troppo comune e facile da indovinare", 0
    
    # Controlla complessità
    score = 0
    checks = {
        'length': len(password) >= PASSWORD_MIN_LENGTH,
        'uppercase': bool(re.search(r'[A-Z]', password)),
        'lowercase': bool(re.search(r'[a-z]', password)),
        'digits': bool(re.search(r'[0-9]', password)),
        'special': bool(re.search(r'[^A-Za-z0-9]', password))
    }
    
    # Calcola punteggio
    if checks['length']:
        score += 1
    if checks['uppercase']:
        score += 1
    if checks['lowercase']:
        score += 1
    if checks['digits']:
        score += 1
    if checks['special']:
        score += 1
    
    # Verifica criterio minimo: lunghezza e almeno 3 dei 4 tipi di caratteri
    min_types = sum([checks['uppercase'], checks['lowercase'], checks['digits'], checks['special']])
    is_secure = checks['length'] and min_types >= 3
    
    # Prepara messaggio di feedback
    if score <= 2:
        feedback = "Password molto debole"
    elif score == 3:
        feedback = "Password debole"
    elif score == 4:
        feedback = "Password media"
    else:
        feedback = "Password forte"
    
    if not is_secure:
        feedback += ". Deve contenere almeno un carattere maiuscolo, uno minuscolo e un numero o simbolo."
    
    return is_secure, feedback, score

def is_password_expired(last_password_change: datetime) -> bool:
    """
    Verifica se una password è scaduta.
    
    Args:
        last_password_change: Data dell'ultimo cambio password
        
    Returns:
        bool: True se la password è scaduta
    """
    if not last_password_change:
        return True
        
    expiry_date = last_password_change + timedelta(days=PASSWORD_MAX_AGE_DAYS)
    return datetime.now() > expiry_date

def get_ip_risk_score(ip: str, known_ips: List[str] = None) -> int:
    """
    Calcola un punteggio di rischio per un indirizzo IP.
    
    Args:
        ip: Indirizzo IP da valutare
        known_ips: Lista di IP noti per l'utente
        
    Returns:
        int: Punteggio di rischio (0-100, dove 100 è il rischio massimo)
    """
    try:
        # Validazione IP
        ipaddress.ip_address(ip)
        
        # Punteggio di base
        risk_score = 0
        
        # Controllo IP noti
        if known_ips and ip not in known_ips:
            risk_score += 30
        
        # Controllo località (dovrebbe essere migliorato con un servizio di geolocalizzazione)
        # Per ora è un placeholder, in produzione usare MaxMind GeoIP o simili
        
        # Qui si potrebbero aggiungere controlli su:
        # - Se l'IP è in blacklist di spam/attacchi
        # - Se l'IP è di un VPN/Proxy noto
        # - Se l'IP è da un paese ad alto rischio
        # - Se ci sono stati molti tentativi di login falliti da questo IP
        
        return risk_score
    except ValueError:
        logger.warning(f"IP non valido: {ip}")
        return 100  # IP non valido = rischio massimo

def detect_suspicious_activity(user_id: str, action: str, ip: str, 
                              previous_activities: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """
    Rileva attività sospette confrontando con le attività precedenti.
    
    Args:
        user_id: ID dell'utente
        action: Azione eseguita
        ip: Indirizzo IP
        previous_activities: Lista di attività precedenti
        
    Returns:
        Tuple[bool, str]: (è_sospetto, motivo)
    """
    if not previous_activities:
        return False, ""
        
    # Lista degli IP noti per l'utente
    known_ips = set(activity['ip'] for activity in previous_activities 
                   if activity.get('ip') and activity.get('status') == 'success')
    
    # Controlla se l'IP è nuovo
    ip_is_new = ip not in known_ips
    
    # Calcola punteggio di rischio
    risk_score = get_ip_risk_score(ip, list(known_ips))
    
    # Ottieni l'ultima azione dell'utente
    last_activity = previous_activities[0] if previous_activities else None
    
    # Azioni sensibili che richiedono maggiore attenzione
    sensitive_actions = {'password_change', 'email_change', 'enable_2fa', 'disable_2fa', 
                        'api_key_created', 'admin_login'}
    
    # Controlla se l'azione è sensibile e l'IP è nuovo
    if action in sensitive_actions and ip_is_new and risk_score > 30:
        return True, f"Azione sensibile {action} da IP non riconosciuto"
    
    # Controlla il tempo tra le attività (impossibile essere in due posti contemporaneamente)
    if last_activity and last_activity.get('timestamp'):
        last_time = last_activity.get('timestamp')
        last_ip = last_activity.get('ip')
        
        if last_ip and last_ip != ip:
            time_diff = datetime.now() - last_time
            
            # Se l'attività precedente è stata meno di 5 minuti fa da un IP diverso
            if time_diff.total_seconds() < 300:
                return True, "Cambio IP sospetto in breve tempo"
    
    # Nessuna attività sospetta rilevata
    return False, ""

def get_challenge_for_2fa(user_id: str) -> Dict[str, Any]:
    """
    Genera una sfida per l'autenticazione a due fattori.
    
    Args:
        user_id: ID dell'utente
        
    Returns:
        Dict[str, Any]: Dati della sfida
    """
    # Genera un codice di verifica OTP monouso
    verification_code = ''.join(secrets.choice('0123456789') for _ in range(6))
    
    # Il codice scade dopo 5 minuti
    expiry = datetime.now() + timedelta(minutes=5)
    
    return {
        'type': 'email_otp',  # Tipo di sfida (email, sms, authenticator)
        'verification_code': verification_code,
        'expires_at': expiry,
        'attempts': 0  # Contatore di tentativi
    }

def verify_challenge_response(challenge: Dict[str, Any], response: str) -> bool:
    """
    Verifica la risposta a una sfida 2FA.
    
    Args:
        challenge: Dati della sfida
        response: Risposta dell'utente
        
    Returns:
        bool: True se la risposta è corretta
    """
    # Verifica se la sfida è scaduta
    if challenge.get('expires_at') < datetime.now():
        return False
    
    # Verifica se ci sono troppi tentativi falliti
    if challenge.get('attempts', 0) >= 3:
        return False
    
    # Verifica la risposta in base al tipo di sfida
    if challenge.get('type') == 'email_otp':
        return challenge.get('verification_code') == response
    
    # Altri tipi di sfida possono essere aggiunti qui
    
    return False 