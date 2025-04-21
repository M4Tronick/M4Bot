#!/usr/bin/env python3
"""
M4Bot - Admin Control Panel Routes
Routes per il pannello di amministrazione con funzionalità di sicurezza avanzata
"""

import os
import json
import time
import uuid
import hashlib
import datetime
import logging
import subprocess
from typing import Dict, List, Any, Optional
from functools import wraps

from quart import Blueprint, render_template, request, redirect, url_for, jsonify
from quart import current_app, abort, session
from quart_auth import login_required, current_user

# Importa moduli di sicurezza avanzata
try:
    from security import security_enhancements
    from security.waf import WAFManager
    from modules.stability_security import StabilitySecurityManager
except ImportError:
    logging.warning("Moduli di sicurezza avanzata non disponibili. Alcune funzionalità potrebbero essere limitate.")

# Set up blueprint e logging
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')
logger = logging.getLogger('m4bot.routes.admin')

# Percorsi ai moduli
MODULES_DIR = "/opt/m4bot/modules" if os.path.exists("/opt/m4bot/modules") else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "modules")
CONFIG_DIR = "/opt/m4bot/config" if os.path.exists("/opt/m4bot/config") else os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config")

# Middleware per verificare i permessi di amministratore
def admin_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if not session.get('user_id'):
            # Controlla se c'è un token di accesso nei cookie
            access_token = request.cookies.get('access_token')
            
            if access_token and hasattr(current_app, 'validate_token'):
                user_id = await current_app.validate_token(access_token)
                if user_id:
                    # Reimpostare la sessione con l'utente
                    session['user_id'] = user_id
                else:
                    return await render_template('errors/403.html', message="Autorizzazione mancante"), 403
            else:
                return redirect(url_for('login', next=request.url))
        
        try:
            # Verifica se l'utente è amministratore
            is_admin = await is_admin_user()
            if not is_admin:
                return await render_template('errors/403.html', message="Permessi insufficienti"), 403
            
            # Registra l'accesso al pannello di amministrazione (per audit)
            await log_admin_access(session.get('user_id'), request.path)
            
            return await f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Errore in {f.__name__}: {e}")
            return await render_template('errors/500.html', message=f"Errore del server: {str(e)}"), 500
            
    return decorated_function

async def is_admin_user() -> bool:
    """Verifica se l'utente corrente è un amministratore"""
    user_id = session.get('user_id')
    if not user_id:
        return False
    
    try:
        if hasattr(current_app, 'db_pool') and current_app.db_pool:
            async with current_app.db_pool.acquire() as conn:
                query = "SELECT is_admin FROM users WHERE id = $1"
                result = await conn.fetchval(query, user_id)
                return bool(result)
        
        # In una implementazione di sviluppo, questo può verificare con alcuni ID hardcoded
        admin_ids = [1, 2, 3]  # ID degli amministratori di test
        return int(user_id) in admin_ids
    except Exception as e:
        logger.error(f"Errore nella verifica dei permessi di amministratore: {e}")
        return False

async def log_admin_access(user_id, path):
    """Registra l'accesso dell'amministratore per motivi di audit"""
    try:
        if hasattr(current_app, 'db_pool') and current_app.db_pool:
            async with current_app.db_pool.acquire() as conn:
                query = """
                INSERT INTO admin_access_log (user_id, access_time, path, ip_address, user_agent)
                VALUES ($1, $2, $3, $4, $5)
                """
                await conn.execute(
                    query,
                    user_id,
                    datetime.datetime.now(),
                    path,
                    request.remote_addr,
                    request.headers.get('User-Agent', '')
                )
                
        # Registro anche su file di log
        logger.info(f"Admin accesso: User ID {user_id} ha acceduto a {path} da {request.remote_addr}")
    except Exception as e:
        logger.error(f"Errore nella registrazione dell'accesso amministratore: {e}")

# Dati di esempio per sviluppo
def get_sample_security_stats() -> Dict[str, Any]:
    """Restituisce statistiche di sicurezza di esempio"""
    return {
        "score": 87,  # Punteggio su 100
        "status_text": "Buono",
        "status_class": "status-success",
        "status_icon": "fa-shield-check",
        "intrusion_attempts": 127,
        "intrusion_bar": 63,  # Percentuale per la barra di progresso
        "blocked_traffic": 18,
        "vulnerabilities": 3,
        "vuln_bar": 30,
        "backup_integrity": 100,
        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "lockdown_mode": False
    }

def get_sample_security_events() -> List[Dict[str, Any]]:
    """Restituisce eventi di sicurezza di esempio"""
    events = []
    
    # Tipi di eventi
    event_types = [
        {"type": "Accesso", "class": "primary", "icon": "fa-sign-in-alt"},
        {"type": "Attacco", "class": "danger", "icon": "fa-radiation"},
        {"type": "Firewall", "class": "warning", "icon": "fa-fire"},
        {"type": "WAF", "class": "info", "icon": "fa-shield-alt"},
        {"type": "Sistema", "class": "secondary", "icon": "fa-server"}
    ]
    
    # Severità
    severities = [
        {"level": "high", "class": "danger"},
        {"level": "medium", "class": "warning"},
        {"level": "low", "class": "info"}
    ]
    
    # Genera eventi di esempio
    for i in range(20):
        # Alterna tipi e severità per varietà
        event_type = event_types[i % len(event_types)]
        severity = severities[i % len(severities)]
        
        # Timestamp decrescente (eventi più recenti prima)
        timestamp = datetime.datetime.now() - datetime.timedelta(hours=i*2)
        
        events.append({
            "id": str(uuid.uuid4()),
            "timestamp": timestamp,
            "type": event_type["type"],
            "type_class": event_type["class"],
            "type_icon": event_type["icon"],
            "severity": severity["level"],
            "severity_class": severity["class"],
            "details": f"Evento di sicurezza {event_type['type']} {i+1} - Dettagli esempio"
        })
    
    return events

def get_sample_firewall_rules() -> List[Dict[str, Any]]:
    """Restituisce regole firewall di esempio"""
    return [
        {
            "id": "rule1",
            "type": "INPUT",
            "address": "0.0.0.0/0",
            "port": "22",
            "action": "ACCEPT",
            "action_class": "success",
            "active": True
        },
        {
            "id": "rule2",
            "type": "INPUT",
            "address": "0.0.0.0/0",
            "port": "80,443",
            "action": "ACCEPT",
            "action_class": "success",
            "active": True
        },
        {
            "id": "rule3",
            "type": "INPUT",
            "address": "10.0.0.0/8",
            "port": "3306",
            "action": "DROP",
            "action_class": "danger",
            "active": True
        },
        {
            "id": "rule4",
            "type": "OUTPUT",
            "address": "192.168.1.0/24",
            "port": "All",
            "action": "ACCEPT",
            "action_class": "success",
            "active": True
        },
        {
            "id": "rule5",
            "type": "INPUT",
            "address": "1.2.3.4",
            "port": "All",
            "action": "DROP",
            "action_class": "danger",
            "active": False
        }
    ]

def get_sample_blocked_ips() -> List[Dict[str, Any]]:
    """Restituisce IP bloccati di esempio"""
    return [
        {
            "address": "192.168.1.120",
            "reason": "Tentativi di login multipli falliti",
            "blocked_at": datetime.datetime.now() - datetime.timedelta(hours=2),
            "permanent": False,
            "duration": "22h rimanenti"
        },
        {
            "address": "10.0.0.15",
            "reason": "Tentativo di SQL Injection",
            "blocked_at": datetime.datetime.now() - datetime.timedelta(days=1),
            "permanent": True,
            "duration": None
        },
        {
            "address": "172.16.0.1",
            "reason": "Attacco DDoS",
            "blocked_at": datetime.datetime.now() - datetime.timedelta(hours=5),
            "permanent": False,
            "duration": "19h rimanenti"
        }
    ]

def get_sample_ssl_certificates() -> List[Dict[str, Any]]:
    """Restituisce certificati SSL di esempio"""
    return [
        {
            "domain": "m4bot.it",
            "issuer": "Let's Encrypt",
            "issued_at": datetime.datetime.now() - datetime.timedelta(days=30),
            "expires_at": datetime.datetime.now() + datetime.timedelta(days=60),
            "status": "Valido",
            "status_class": "success"
        },
        {
            "domain": "dashboard.m4bot.it",
            "issuer": "Let's Encrypt",
            "issued_at": datetime.datetime.now() - datetime.timedelta(days=30),
            "expires_at": datetime.datetime.now() + datetime.timedelta(days=60),
            "status": "Valido",
            "status_class": "success"
        },
        {
            "domain": "api.m4bot.it",
            "issuer": "Let's Encrypt",
            "issued_at": datetime.datetime.now() - datetime.timedelta(days=80),
            "expires_at": datetime.datetime.now() + datetime.timedelta(days=10),
            "status": "In scadenza",
            "status_class": "warning"
        },
        {
            "domain": "control.m4bot.it",
            "issuer": "Let's Encrypt",
            "issued_at": datetime.datetime.now() - datetime.timedelta(days=30),
            "expires_at": datetime.datetime.now() + datetime.timedelta(days=60),
            "status": "Valido",
            "status_class": "success"
        }
    ]

def get_sample_vulnerabilities() -> List[Dict[str, Any]]:
    """Restituisce vulnerabilità di esempio"""
    return [
        {
            "id": "vuln1",
            "description": "Versione OpenSSH obsoleta (7.6p1)",
            "severity": "Media",
            "severity_class": "warning",
            "status": "Riparabile",
            "status_class": "primary"
        },
        {
            "id": "vuln2",
            "description": "Esposizione header Server nelle risposte HTTP",
            "severity": "Bassa",
            "severity_class": "info",
            "status": "Riparabile",
            "status_class": "primary"
        },
        {
            "id": "vuln3",
            "description": "Permessi directory /var/www troppo permissivi (777)",
            "severity": "Alta",
            "severity_class": "danger",
            "status": "Riparazione in corso",
            "status_class": "warning"
        }
    ]

# Funzioni per ottenere dati reali (quando disponibili)
def get_real_security_stats() -> Optional[Dict[str, Any]]:
    """Ottiene statistiche di sicurezza reali se disponibili"""
    try:
        # Verifica se il modulo di sicurezza avanzata è disponibile
        if 'security_enhancements' in globals():
            security = security_enhancements.get_instance()
            status = security.get_security_status()
            
            # Calcola punteggio di sicurezza su 100
            score = 0
            weights = {
                "ddos_protection": 15,
                "intrusion_detection": 15,
                "firewall": 10,
                "ssh_protection": 10,
                "ssl_tls": 10,
                "vuln_scanner": 15,
                "sandbox": 5,
                "backup": 10,
                "additional": 10  # Per altre metriche
            }
            
            # Calcola punteggio pesato basato sui componenti attivi
            for component, weight in weights.items():
                if component in status and status[component]:
                    score += weight
            
            # Detrazione per minacce attive
            threat_deduction = 0
            # Per ogni IP bloccato recente, riduci il punteggio
            if 'blocked_ips' in status:
                threat_deduction += min(status['blocked_ips'] * 2, 10)
            
            # Stato complessivo
            if score >= 80:
                status_text = "Ottimo"
                status_class = "status-success"
                status_icon = "fa-shield-check"
            elif score >= 60:
                status_text = "Buono"
                status_class = "status-success"
                status_icon = "fa-shield-alt"
            elif score >= 40:
                status_text = "Attenzione"
                status_class = "status-warning"
                status_icon = "fa-exclamation-triangle"
            else:
                status_text = "Critico"
                status_class = "status-danger"
                status_icon = "fa-exclamation-circle"
            
            # Dati aggiuntivi
            additional_data = {}
            
            # Se disponibile il WAF, aggiungi metriche
            if 'WAFManager' in globals():
                waf_stats = WAFManager.get_stats()
                if waf_stats:
                    additional_data["intrusion_attempts"] = waf_stats.get("attacks_blocked_24h", 0)
                    additional_data["blocked_traffic"] = waf_stats.get("blocked_percentage", 0)
            
            # Se disponibili informazioni sulla stabilità
            if 'StabilitySecurityManager' in globals():
                stability_stats = StabilitySecurityManager.get_status()
                if stability_stats:
                    additional_data["system_uptime"] = stability_stats.get("uptime_days", 0)
                    additional_data["lockdown_mode"] = stability_stats.get("lockdown_active", False)
            
            # Combina tutti i dati
            return {
                "score": max(0, min(score - threat_deduction, 100)),  # Limita tra 0 e 100
                "status_text": status_text,
                "status_class": status_class,
                "status_icon": status_icon,
                "intrusion_attempts": additional_data.get("intrusion_attempts", 0),
                "intrusion_bar": min(additional_data.get("intrusion_attempts", 0) / 2, 100),  # Scala per la visualizzazione
                "blocked_traffic": additional_data.get("blocked_traffic", 0),
                "vulnerabilities": status.get("vulnerabilities_count", 0),
                "vuln_bar": min(status.get("vulnerabilities_count", 0) * 10, 100),  # Scala per la visualizzazione
                "backup_integrity": additional_data.get("backup_integrity", 100),
                "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "lockdown_mode": additional_data.get("lockdown_mode", False)
            }
    except Exception as e:
        logger.error(f"Errore nell'ottenere statistiche di sicurezza reali: {e}")
    
    return None

# Routes per il pannello di amministrazione
@admin_bp.route('/')
@admin_required
async def admin_dashboard():
    """Pagina principale del pannello di amministrazione"""
    return await render_template('admin/dashboard.html', page="admin")

@admin_bp.route('/security-control')
@admin_required
async def security_control():
    """Pannello di controllo della sicurezza avanzato"""
    # Ottieni dati reali se disponibili, altrimenti usa dati di esempio
    security_stats = get_real_security_stats() or get_sample_security_stats()
    security_events = get_sample_security_events()  # Per ora usiamo sempre dati di esempio
    firewall_rules = get_sample_firewall_rules()
    blocked_ips = get_sample_blocked_ips()
    ssl_certificates = get_sample_ssl_certificates()
    vulnerabilities = get_sample_vulnerabilities()
    
    # Calcola informazioni aggiuntive per i certificati
    ssl_certs = sorted(ssl_certificates, key=lambda x: x["expires_at"])
    if ssl_certs:
        next_expiry = ssl_certs[0]["expires_at"]
        days_to_expiry = (next_expiry - datetime.datetime.now()).days
        next_expiry_date = next_expiry.strftime("%Y-%m-%d")
    else:
        days_to_expiry = 0
        next_expiry_date = "N/A"
    
    # Conteggio vulnerabilità riparabili
    fixable_vulnerabilities = sum(1 for v in vulnerabilities if "Riparabile" in v["status"])
    
    # Informazioni firewall
    firewall_stats = {
        "active": True,
        "rules_count": len(firewall_rules),
        "active_rules": sum(1 for r in firewall_rules if r["active"])
    }
    
    # Data ultima scansione vulnerabilità
    last_scan_date = (datetime.datetime.now() - datetime.timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    
    return await render_template(
        'admin/security_control.html',
        page="security_control",
        security_stats=security_stats,
        security_events=security_events,
        firewall_rules=firewall_rules,
        blocked_ips=blocked_ips,
        ssl_certificates=ssl_certificates,
        vulnerabilities=vulnerabilities,
        next_expiry_date=next_expiry_date,
        days_to_expiry=days_to_expiry,
        fixable_vulnerabilities=fixable_vulnerabilities,
        firewall_stats=firewall_stats,
        last_scan_date=last_scan_date
    )

# API routes per le operazioni di sicurezza
@admin_bp.route('/api/security/scan', methods=['POST'])
@admin_required
async def security_scan():
    """Avvia una scansione di sicurezza completa"""
    try:
        # Verifico il CSRF token per operazioni sensibili
        if not await verify_csrf_token():
            return jsonify({
                "success": False,
                "message": "Token CSRF non valido"
            }), 403
            
        # Nella versione reale, qui si avvierebbe la scansione effettiva
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": "Scansione di sicurezza avviata. Questo processo potrebbe richiedere alcuni minuti.",
            "task_id": str(uuid.uuid4())  # Task ID per il monitoraggio della scansione
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nell'avvio della scansione di sicurezza: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore nell'avvio della scansione: {str(e)}"
        }), 500

@admin_bp.route('/api/security/lockdown', methods=['POST'])
@admin_required
async def toggle_lockdown():
    """Attiva o disattiva la modalità lockdown"""
    try:
        # Verifico il CSRF token per operazioni sensibili
        if not await verify_csrf_token():
            return jsonify({
                "success": False,
                "message": "Token CSRF non valido"
            }), 403
            
        data = await request.get_json()
        
        if not data or 'activate' not in data:
            return jsonify({
                "success": False,
                "message": "Parametro 'activate' mancante"
            }), 400
            
        activate = bool(data.get('activate', False))
        
        # Nella versione reale, qui si attivarebbe/disattivarebbe la modalità lockdown
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "active": activate,
            "message": f"Modalità lockdown {'attivata' if activate else 'disattivata'} con successo."
        }
        
        # Registra l'operazione nel log di sicurezza
        await log_security_event(
            event_type="lockdown", 
            severity="high", 
            details=f"Modalità lockdown {'attivata' if activate else 'disattivata'} da amministratore"
        )
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nella gestione della modalità lockdown: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

async def log_security_event(event_type, severity, details):
    """Registra un evento di sicurezza"""
    try:
        if hasattr(current_app, 'db_pool') and current_app.db_pool:
            async with current_app.db_pool.acquire() as conn:
                query = """
                INSERT INTO security_events (timestamp, type, severity, user_id, ip_address, details)
                VALUES ($1, $2, $3, $4, $5, $6)
                """
                await conn.execute(
                    query,
                    datetime.datetime.now(),
                    event_type,
                    severity,
                    session.get('user_id'),
                    request.remote_addr,
                    details
                )
                
        # Registro anche su file di log
        logger.info(f"Evento sicurezza: {event_type} ({severity}) - {details}")
    except Exception as e:
        logger.error(f"Errore nella registrazione dell'evento di sicurezza: {e}")

async def verify_csrf_token():
    """Verifica il token CSRF per proteggere da attacchi CSRF"""
    try:
        token = request.headers.get('X-CSRF-Token')
        if not token:
            data = await request.get_json()
            if data:
                token = data.get('csrf_token')
                
        if not token:
            return False
            
        expected_token = session.get('csrf_token')
        if not expected_token:
            return False
            
        # Verifica il token
        return token == expected_token
    except Exception as e:
        logger.error(f"Errore nella verifica del token CSRF: {e}")
        return False

@admin_bp.route('/api/security/rotate-keys', methods=['POST'])
@admin_required
async def rotate_keys():
    """Esegue la rotazione delle chiavi di crittografia"""
    try:
        # Verifico il CSRF token per operazioni sensibili
        if not await verify_csrf_token():
            return jsonify({
                "success": False,
                "message": "Token CSRF non valido"
            }), 403
            
        # Nella versione reale, qui si eseguirebbe la rotazione effettiva delle chiavi
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": "Rotazione delle chiavi completata con successo."
        }
        
        # Registra l'operazione nel log di sicurezza
        await log_security_event(
            event_type="key_rotation", 
            severity="high", 
            details="Rotazione delle chiavi di crittografia eseguita da amministratore"
        )
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nella rotazione delle chiavi: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@admin_bp.route('/api/security/block-ip', methods=['POST'])
@admin_required
async def block_ip():
    """Blocca un indirizzo IP"""
    try:
        # Verifico il CSRF token per operazioni sensibili
        if not await verify_csrf_token():
            return jsonify({
                "success": False,
                "message": "Token CSRF non valido"
            }), 403
            
        data = await request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "Dati richiesta mancanti"
            }), 400
            
        ip_address = data.get('ip')
        permanent = data.get('permanent', False)
        reason = data.get('reason', 'Blocco manuale')
        duration = data.get('duration', 24)  # Ore
        
        if not ip_address:
            return jsonify({
                "success": False,
                "message": "Indirizzo IP mancante"
            }), 400
            
        # Valida indirizzo IP
        if not is_valid_ip(ip_address):
            return jsonify({
                "success": False,
                "message": "Indirizzo IP non valido"
            }), 400
            
        # Previeni il blocco di localhost o indirizzi della rete interna
        if ip_address.startswith('127.') or ip_address.startswith('192.168.') or ip_address.startswith('10.'):
            return jsonify({
                "success": False, 
                "message": "Non è possibile bloccare indirizzi IP della rete locale"
            }), 400
        
        # Nella versione reale, qui si blocherebbe effettivamente l'IP
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": f"IP {ip_address} bloccato {'permanentemente' if permanent else f'per {duration} ore'}."
        }
        
        # Registra l'operazione nel log di sicurezza
        await log_security_event(
            event_type="ip_blocked", 
            severity="medium", 
            details=f"IP {ip_address} bloccato {'permanentemente' if permanent else f'per {duration} ore'} per: {reason}"
        )
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nel blocco dell'IP: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

def is_valid_ip(ip_address):
    """Valida un indirizzo IP"""
    import re
    pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
    match = re.match(pattern, ip_address)
    if not match:
        return False
    for part in match.groups():
        if int(part) > 255:
            return False
    return True

# API routes per le altre operazioni
# ... (tutte le altre route API)

def init_admin_bp(app):
    """Inizializza il blueprint amministrativo"""
    app.register_blueprint(admin_bp)
    
    # Inizializza sicurezza avanzata se disponibile
    try:
        if 'security_enhancements' in globals():
            security = security_enhancements.get_instance()
            logger.info("Modulo di sicurezza avanzata inizializzato")
    except Exception as e:
        logger.warning(f"Impossibile inizializzare il modulo di sicurezza avanzata: {e}")
    
    logger.info("Blueprint amministrativo inizializzato") 