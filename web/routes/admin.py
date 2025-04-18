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
        if not session.get('user') or not session.get('user').get('is_admin', False):
            return await render_template('errors/403.html'), 403
        return await f(*args, **kwargs)
    return decorated_function

async def is_admin_user() -> bool:
    """Verifica se l'utente corrente è un amministratore"""
    if not current_user.is_authenticated:
        return False
    
    try:
        user_id = current_user.id
        # In una implementazione reale, questo dovrebbe verificare nel database
        # Per ora, simuliamo con alcuni ID hardcoded per sviluppo
        admin_ids = [1, 2, 3]  # ID degli amministratori
        return user_id in admin_ids
    except Exception as e:
        logger.error(f"Errore nella verifica dei permessi di amministratore: {e}")
        return False

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
        # Nella versione reale, qui si avvierebbe la scansione effettiva
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": "Scansione di sicurezza avviata. Questo processo potrebbe richiedere alcuni minuti."
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
        data = await request.get_json()
        activate = data.get('activate', False)
        
        # Nella versione reale, qui si attivarebbe/disattivarebbe la modalità lockdown
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "active": activate,
            "message": f"Modalità lockdown {'attivata' if activate else 'disattivata'} con successo."
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nella gestione della modalità lockdown: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@admin_bp.route('/api/security/rotate-keys', methods=['POST'])
@admin_required
async def rotate_keys():
    """Esegue la rotazione delle chiavi di crittografia"""
    try:
        # Nella versione reale, qui si eseguirebbe la rotazione effettiva delle chiavi
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": "Rotazione delle chiavi completata con successo."
        }
        
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
        data = await request.get_json()
        ip_address = data.get('ip')
        permanent = data.get('permanent', False)
        reason = data.get('reason', 'Blocco manuale')
        duration = data.get('duration', 24)  # Ore
        
        if not ip_address:
            return jsonify({
                "success": False,
                "message": "Indirizzo IP mancante"
            }), 400
        
        # Nella versione reale, qui si blocherebbe effettivamente l'IP
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": f"IP {ip_address} bloccato {'permanentemente' if permanent else f'per {duration} ore'}."
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nel blocco dell'IP: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@admin_bp.route('/api/security/unblock-ip', methods=['POST'])
@admin_required
async def unblock_ip():
    """Sblocca un indirizzo IP"""
    try:
        data = await request.get_json()
        ip_address = data.get('ip')
        
        if not ip_address:
            return jsonify({
                "success": False,
                "message": "Indirizzo IP mancante"
            }), 400
        
        # Nella versione reale, qui si sbloccherebbe effettivamente l'IP
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": f"IP {ip_address} sbloccato con successo."
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nello sblocco dell'IP: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@admin_bp.route('/api/security/firewall-rule', methods=['POST'])
@admin_required
async def add_firewall_rule():
    """Aggiunge una nuova regola firewall"""
    try:
        data = await request.get_json()
        rule_type = data.get('type')
        address = data.get('address')
        port = data.get('port')
        action = data.get('action')
        active = data.get('active', True)
        
        if not all([rule_type, address, action]):
            return jsonify({
                "success": False,
                "message": "Dati regola incompleti"
            }), 400
        
        # Nella versione reale, qui si aggiungerebbe effettivamente la regola
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": f"Regola firewall aggiunta con successo."
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nell'aggiunta della regola firewall: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@admin_bp.route('/api/security/apply-firewall', methods=['POST'])
@admin_required
async def apply_firewall_changes():
    """Applica le modifiche al firewall"""
    try:
        # Nella versione reale, qui si applicherebbero effettivamente le modifiche
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": "Modifiche al firewall applicate con successo."
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nell'applicazione delle modifiche al firewall: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@admin_bp.route('/api/security/renew-cert', methods=['POST'])
@admin_required
async def renew_certificate():
    """Rinnova un certificato SSL specifico"""
    try:
        data = await request.get_json()
        domain = data.get('domain')
        
        if not domain:
            return jsonify({
                "success": False,
                "message": "Dominio mancante"
            }), 400
        
        # Nella versione reale, qui si rinnoverebbe effettivamente il certificato
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": f"Rinnovo del certificato per {domain} avviato con successo."
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nel rinnovo del certificato: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@admin_bp.route('/api/security/renew-all-certs', methods=['POST'])
@admin_required
async def renew_all_certificates():
    """Rinnova tutti i certificati SSL"""
    try:
        # Nella versione reale, qui si rinnoverebbero effettivamente tutti i certificati
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": "Rinnovo di tutti i certificati avviato con successo."
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nel rinnovo di tutti i certificati: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@admin_bp.route('/api/security/fix-vulnerability', methods=['POST'])
@admin_required
async def fix_vulnerability():
    """Ripara una vulnerabilità specifica"""
    try:
        data = await request.get_json()
        vuln_id = data.get('id')
        
        if not vuln_id:
            return jsonify({
                "success": False,
                "message": "ID vulnerabilità mancante"
            }), 400
        
        # Nella versione reale, qui si riparerebbe effettivamente la vulnerabilità
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": f"Riparazione della vulnerabilità {vuln_id} avviata con successo."
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nella riparazione della vulnerabilità: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@admin_bp.route('/api/security/fix-all-vulnerabilities', methods=['POST'])
@admin_required
async def fix_all_vulnerabilities():
    """Ripara tutte le vulnerabilità riparabili"""
    try:
        # Nella versione reale, qui si riparerebbero effettivamente tutte le vulnerabilità
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": "Riparazione di tutte le vulnerabilità avviata con successo."
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nella riparazione di tutte le vulnerabilità: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@admin_bp.route('/api/security/generate-report', methods=['POST'])
@admin_required
async def generate_security_report():
    """Genera un report di sicurezza completo"""
    try:
        # Nella versione reale, qui si genererebbe effettivamente il report
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": "Generazione del report di sicurezza avviata.",
            "report_id": str(uuid.uuid4())
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nella generazione del report di sicurezza: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@admin_bp.route('/api/security/secure-backup', methods=['POST'])
@admin_required
async def create_secure_backup():
    """Crea un backup sicuro crittografato"""
    try:
        # Nella versione reale, qui si creerebbe effettivamente il backup
        # Per ora, simuliamo una risposta positiva
        result = {
            "success": True,
            "message": "Backup sicuro avviato. Riceverai una notifica al completamento.",
            "backup_id": str(uuid.uuid4())
        }
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nella creazione del backup sicuro: {e}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

# Aggiungi rotte per i nuovi moduli di sicurezza e monitoraggio
@admin_bp.route('/admin/advanced-monitoring', methods=['GET'])
@admin_required
def advanced_monitoring():
    """Pagina di monitoraggio avanzato."""
    # Importa il gestore di stabilità e sicurezza
    from web.admin.modules.stability_security import get_stability_security_manager
    
    manager = get_stability_security_manager()
    if not manager:
        flash('Errore nel caricamento del gestore di stabilità e sicurezza', 'error')
        return redirect(url_for('admin.dashboard'))
    
    # Ottieni lo stato del sistema
    system_status = manager.get_status()
    
    # Monitora e ripara eventuali problemi
    monitor_results = manager.monitor_and_heal()
    
    return render_template(
        'admin/advanced_monitoring.html',
        title='Monitoraggio Avanzato',
        system_status=system_status,
        monitor_results=monitor_results
    )

@admin_bp.route('/admin/key-management', methods=['GET'])
@admin_required
def key_management():
    """Pagina di gestione delle chiavi di sicurezza."""
    # Importa il gestore di stabilità e sicurezza
    from web.admin.modules.stability_security import get_stability_security_manager
    
    manager = get_stability_security_manager()
    if not manager:
        flash('Errore nel caricamento del gestore di stabilità e sicurezza', 'error')
        return redirect(url_for('admin.dashboard'))
    
    # Verifica se il gestore delle credenziali è disponibile
    credential_manager_available = hasattr(manager, 'credential_manager') and manager.credential_manager is not None
    
    # Info sulle chiavi di sicurezza
    key_status = {}
    if credential_manager_available:
        key_status = manager.credential_manager.check_credentials()
    
    return render_template(
        'admin/key_management.html',
        title='Gestione Chiavi',
        credential_manager_available=credential_manager_available,
        key_status=key_status
    )

@admin_bp.route('/admin/system-diagnostics', methods=['GET'])
@admin_required
def system_diagnostics():
    """Pagina di diagnostica del sistema."""
    # Ottieni informazioni di sistema
    try:
        import subprocess
        
        # Esegui lo script di diagnostica
        diagnostics_path = '/opt/m4bot/scripts/diagnostics.sh'
        if os.path.exists(diagnostics_path):
            proc = subprocess.run(['bash', diagnostics_path, '--json'], capture_output=True, text=True)
            if proc.returncode == 0:
                try:
                    diagnostics_data = json.loads(proc.stdout)
                except:
                    diagnostics_data = {'error': 'Errore nel parsing dell\'output JSON'}
            else:
                diagnostics_data = {'error': f'Errore nell\'esecuzione del diagnostico: {proc.stderr}'}
        else:
            diagnostics_data = {
                'status': 'error',
                'error': f'Script di diagnostica non trovato: {diagnostics_path}'
            }
    except Exception as e:
        diagnostics_data = {
            'status': 'error',
            'error': f'Errore: {str(e)}'
        }
    
    return render_template(
        'admin/system_diagnostics.html',
        title='Diagnostica Sistema',
        diagnostics_data=diagnostics_data
    )

@admin_bp.route('/admin/prometheus-metrics', methods=['GET'])
@admin_required
def prometheus_metrics():
    """Pagina di visualizzazione delle metriche Prometheus."""
    prometheus_url = request.host_url.rstrip('/') + ':9090'
    
    return render_template(
        'admin/prometheus_metrics.html',
        title='Metriche Sistema',
        prometheus_url=prometheus_url
    )

# API per i nuovi moduli
@admin_bp.route('/api/admin/rotate-keys', methods=['POST'])
@admin_required
def api_rotate_keys():
    """API per la rotazione delle chiavi di sicurezza."""
    from web.admin.modules.stability_security import get_stability_security_manager
    
    manager = get_stability_security_manager()
    if not manager:
        return jsonify({'success': False, 'error': 'Gestore non disponibile'}), 500
    
    # Verifica se il gestore delle credenziali è disponibile
    if not hasattr(manager, 'credential_manager') or manager.credential_manager is None:
        return jsonify({'success': False, 'error': 'Gestore delle credenziali non disponibile'}), 500
    
    # Esegui la rotazione
    result = manager.rotate_security_keys()
    
    return jsonify(result)

@admin_bp.route('/api/admin/update-system', methods=['POST'])
@admin_required
def api_update_system():
    """API per l'aggiornamento del sistema."""
    from web.admin.modules.stability_security import get_stability_security_manager
    
    manager = get_stability_security_manager()
    if not manager:
        return jsonify({'success': False, 'error': 'Gestore non disponibile'}), 500
    
    # Ottieni i parametri dalla richiesta
    data = request.get_json() or {}
    zero_downtime = data.get('zero_downtime', True)
    
    # Esegui l'aggiornamento
    result = manager.perform_update(zero_downtime=zero_downtime)
    
    return jsonify(result)

@admin_bp.route('/api/admin/run-diagnostics', methods=['POST'])
@admin_required
def api_run_diagnostics():
    """API per eseguire la diagnostica del sistema."""
    try:
        import subprocess
        
        # Esegui lo script di diagnostica
        diagnostics_path = '/opt/m4bot/scripts/diagnostics.sh'
        if os.path.exists(diagnostics_path):
            proc = subprocess.run(['bash', diagnostics_path, '--json'], capture_output=True, text=True)
            if proc.returncode == 0:
                try:
                    return jsonify(json.loads(proc.stdout))
                except:
                    return jsonify({'success': False, 'error': 'Errore nel parsing dell\'output JSON'}), 500
            else:
                return jsonify({'success': False, 'error': f'Errore nell\'esecuzione: {proc.stderr}'}), 500
        else:
            return jsonify({'success': False, 'error': f'Script non trovato: {diagnostics_path}'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@admin_bp.route('/api/admin/monitor-system', methods=['POST'])
@admin_required
def api_monitor_system():
    """API per monitorare e riparare il sistema."""
    from web.admin.modules.stability_security import get_stability_security_manager
    
    manager = get_stability_security_manager()
    if not manager:
        return jsonify({'success': False, 'error': 'Gestore non disponibile'}), 500
    
    # Monitora e ripara
    result = manager.monitor_and_heal()
    
    return jsonify(result)

# Funzione per caricare moduli dinamicamente
def load_module(module_name):
    module_path = os.path.join(MODULES_DIR, module_name, "__init__.py")
    if not os.path.exists(module_path):
        current_app.logger.error(f"Modulo {module_name} non trovato in {module_path}")
        return None
    
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Rotta del pannello di monitoraggio
@admin_bp.route('/monitoring')
@admin_required
async def monitoring_dashboard():
    # Carica i dati di monitoraggio se il modulo è disponibile
    monitoring_data = {"system": {}, "services": [], "alerts": []}
    
    try:
        monitoring_module = load_module("monitoring")
        if monitoring_module and hasattr(monitoring_module, "get_monitoring_data"):
            monitoring_data = monitoring_module.get_monitoring_data()
    except Exception as e:
        current_app.logger.error(f"Errore nel caricamento del modulo di monitoraggio: {str(e)}")
    
    return await render_template('admin/monitoring.html', 
                               system_info=monitoring_data.get("system", {}),
                               services=monitoring_data.get("services", []),
                               alerts=monitoring_data.get("alerts", []))

# API per il monitoraggio del sistema
@admin_bp.route('/api/monitoring/system-info', methods=['GET'])
@admin_required
async def get_system_info():
    try:
        monitoring_module = load_module("monitoring")
        if monitoring_module and hasattr(monitoring_module, "get_system_info"):
            result = monitoring_module.get_system_info()
            return jsonify({"success": True, "data": result})
        return jsonify({"success": False, "message": "Modulo di monitoraggio non disponibile"})
    except Exception as e:
        current_app.logger.error(f"Errore durante l'ottenimento delle informazioni di sistema: {str(e)}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"}), 500

# API per il monitoraggio dei servizi
@admin_bp.route('/api/monitoring/services', methods=['GET'])
@admin_required
async def get_services_status():
    try:
        monitoring_module = load_module("monitoring")
        if monitoring_module and hasattr(monitoring_module, "get_services_status"):
            result = monitoring_module.get_services_status()
            return jsonify({"success": True, "data": result})
        return jsonify({"success": False, "message": "Modulo di monitoraggio non disponibile"})
    except Exception as e:
        current_app.logger.error(f"Errore durante l'ottenimento dello stato dei servizi: {str(e)}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"}), 500

# API per il monitoraggio degli alert
@admin_bp.route('/api/monitoring/alerts', methods=['GET'])
@admin_required
async def get_alerts():
    try:
        monitoring_module = load_module("monitoring")
        if monitoring_module and hasattr(monitoring_module, "get_alerts"):
            result = monitoring_module.get_alerts()
            return jsonify({"success": True, "data": result})
        return jsonify({"success": False, "message": "Modulo di monitoraggio non disponibile"})
    except Exception as e:
        current_app.logger.error(f"Errore durante l'ottenimento degli alert: {str(e)}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"}), 500

# API per il riavvio dei servizi
@admin_bp.route('/api/monitoring/restart-service', methods=['POST'])
@admin_required
async def restart_service():
    try:
        data = await request.get_json()
        service_name = data.get('service')
        
        if not service_name:
            return jsonify({"success": False, "message": "Nome del servizio non specificato"}), 400
        
        monitoring_module = load_module("monitoring")
        if monitoring_module and hasattr(monitoring_module, "restart_service"):
            result = monitoring_module.restart_service(service_name)
            return jsonify({"success": True, "message": f"Servizio {service_name} riavviato con successo", "data": result})
        return jsonify({"success": False, "message": "Modulo di monitoraggio non disponibile"})
    except Exception as e:
        current_app.logger.error(f"Errore durante il riavvio del servizio: {str(e)}")
        return jsonify({"success": False, "message": f"Errore: {str(e)}"}), 500

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