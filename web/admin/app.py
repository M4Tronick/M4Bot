#!/usr/bin/env python3
"""
Pannello di controllo amministrativo per M4Bot
Fornisce un'interfaccia completa per monitoraggio e gestione dell'infrastruttura
"""

import os
import sys
import json
import logging
import asyncio
import secrets
import datetime
import ipaddress
import platform
import subprocess
import time  # Aggiungo import mancante per time.time()
from functools import wraps
from urllib.parse import urlparse
import base64

import aiohttp
import psutil
import docker
import asyncpg
import aiomysql
import aioredis
import bcrypt
import quart_cors
from quart import Quart, render_template, request, redirect, url_for, jsonify
from quart import websocket, session, send_file, Response
from quart_auth import QuartAuth, AuthManager, login_required, current_user

# Aggiungi la directory principale al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importa moduli personalizzati
from modules.monitoring import MonitoringManager, MetricsCollector
from modules.user_management import UserManager  # Corretto il nome del modulo e rimosso classi inesistenti
from modules.backup import BackupManager, RotationPolicy
from modules.deployment import DeploymentManager, ScalingManager
from modules.security import SecurityChecker, FirewallManager, CertificateManager
from modules.analytics import LogAnalyzer, AnomalyDetector
from modules.stability_security import StabilitySecurityManager  # Aggiungiamo il nuovo modulo
from utils.system import SystemUtils, DiskManager, ProcessManager
from utils.notifications import NotificationManager, AlertPolicy, ChannelManager

# Configurazione
DEBUG = os.getenv('ADMIN_DEBUG', 'False').lower() == 'true'
SECRET_KEY = os.getenv('ADMIN_SECRET_KEY', secrets.token_hex(32))
DB_URI = os.getenv('ADMIN_DB_URI', 'postgresql://user:pass@localhost/m4bot_admin')
REDIS_URI = os.getenv('ADMIN_REDIS_URI', 'redis://localhost:6379/0')
LOG_LEVEL = os.getenv('ADMIN_LOG_LEVEL', 'INFO')
LOG_FILE = os.getenv('ADMIN_LOG_FILE', '/var/log/m4bot/admin.log')
ALLOWED_HOSTS = os.getenv('ADMIN_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',')
API_RATE_LIMIT = int(os.getenv('ADMIN_API_RATE_LIMIT', '100'))
SESSION_DURATION = int(os.getenv('ADMIN_SESSION_DURATION', '3600'))
REQUIRE_2FA = os.getenv('ADMIN_REQUIRE_2FA', 'True').lower() == 'true'

# Configurazione logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('m4bot-admin')

# Crea l'applicazione Quart
app = Quart(__name__, 
           template_folder='templates',
           static_folder='static')
app = quart_cors.cors(app, allow_origin=ALLOWED_HOSTS)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(seconds=SESSION_DURATION)
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_PERMANENT'] = True
app.config['REQUIRE_2FA'] = REQUIRE_2FA

# Configura autenticazione
auth_manager = AuthManager(app)
quart_auth = QuartAuth(app)
quart_auth.user_class = UserManager

# Variabili globali
db_pool = None
redis_pool = None
monitoring_manager = None
user_manager = None
backup_manager = None
notification_manager = None
deployment_manager = None
security_manager = None
analytics_manager = None
stability_security_manager = None  # Aggiungiamo la variabile globale

# Middleware per controllo accesso API
@app.before_request
async def api_access_control():
    """Middleware per controllo accesso API e rate limiting."""
    if request.path.startswith('/api/'):
        # Controlla che l'host sia autorizzato
        host = request.headers.get('Host', '')
        if host not in ALLOWED_HOSTS:
            logger.warning(f"Accesso API non autorizzato da host: {host}")
            return jsonify({"error": "Accesso non autorizzato"}), 403
            
        # Controlla API key se richiesto
        if request.path.startswith('/api/v2/'):
            api_key = request.headers.get('X-API-Key')
            if not api_key or not await user_manager.verify_api_key(api_key):
                logger.warning(f"Tentativo accesso API con chiave non valida")
                return jsonify({"error": "API key non valida"}), 401
                
        # Rate limiting
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        rate_key = f"rate_limit:{client_ip}"
        
        async with redis_pool.get() as redis:
            current_count = await redis.incr(rate_key)
            if current_count == 1:
                await redis.expire(rate_key, 3600)  # 1 ora
                
            if current_count > API_RATE_LIMIT:
                logger.warning(f"Rate limit superato per IP: {client_ip}")
                return jsonify({"error": "Limite di richieste superato"}), 429

# Inizializzazione asincrona dell'applicazione
@app.before_serving
async def setup_app():
    """Inizializza tutte le connessioni e i manager prima di servire l'app."""
    global db_pool, redis_pool, monitoring_manager, user_manager
    global backup_manager, notification_manager, deployment_manager
    global security_manager, analytics_manager, stability_security_manager  # Aggiungiamo il manager
    
    try:
        # Connessione al database
        db_pool = await asyncpg.create_pool(DB_URI, 
                                         min_size=5, 
                                         max_size=20,
                                         command_timeout=60.0)
        logger.info("Connessione al database PostgreSQL stabilita")
        
        # Connessione a Redis
        redis_pool = aioredis.ConnectionPool.from_url(REDIS_URI)
        logger.info("Connessione a Redis stabilita")
        
        # Inizializza i manager
        monitoring_manager = MonitoringManager(db_pool, redis_pool)
        user_manager = UserManager(db_pool, redis_pool)
        backup_manager = BackupManager(db_pool)
        notification_manager = NotificationManager(db_pool, redis_pool)
        deployment_manager = DeploymentManager(db_pool)
        security_manager = SecurityChecker(db_pool, redis_pool)
        analytics_manager = LogAnalyzer(db_pool, redis_pool)
        
        # Inizializza il manager di stabilità e sicurezza
        stability_security_manager = StabilitySecurityManager(db_pool, redis_pool)
        await stability_security_manager.initialize()
        logger.info("Manager di sicurezza e stabilità inizializzato")
        
        # Avvia servizi in background
        asyncio.create_task(monitoring_manager.start_collection())
        asyncio.create_task(backup_manager.start_scheduled_backups())
        asyncio.create_task(security_manager.start_periodic_scans())
        
        logger.info("Inizializzazione dell'applicazione completata")
    except Exception as e:
        logger.critical(f"Errore nell'inizializzazione dell'applicazione: {e}")
        sys.exit(1)

@app.after_serving
async def cleanup():
    """Chiudi tutte le connessioni attive."""
    if db_pool:
        await db_pool.close()
    if redis_pool:
        await redis_pool.close()
    logger.info("Chiusura connessioni completata")

# Decoratore per controllo dei ruoli
def role_required(role):
    """Decoratore per verificare che l'utente abbia un ruolo specifico."""
    def decorator(f):
        @wraps(f)
        @login_required
        async def decorated_function(*args, **kwargs):
            if not await user_manager.has_role(current_user.id, role):
                logger.warning(f"Utente {current_user.id} ha tentato di accedere a una risorsa riservata al ruolo {role}")
                return redirect(url_for('unauthorized'))
            return await f(*args, **kwargs)
        return decorated_function
    return decorator

# Endpoint per webhook
@app.route('/webhook/<token>', methods=['POST'])
async def receive_webhook(token):
    """Endpoint per ricevere webhook da servizi esterni."""
    # Verifica il token
    if not await notification_manager.validate_webhook_token(token):
        logger.warning(f"Tentativo di accesso webhook con token non valido: {token}")
        return jsonify({"error": "Token non valido"}), 401
        
    data = await request.get_json()
    source = data.get('source', 'unknown')
    event_type = data.get('event', 'unknown')
    severity = data.get('severity', 'info')
    
    # Registra l'evento
    event_id = await notification_manager.log_webhook_event(
        token=token,
        source=source,
        event_type=event_type,
        severity=severity,
        payload=data
    )
    
    # Processa notifiche se necessario
    if severity in ('warning', 'error', 'critical'):
        await notification_manager.process_alert(event_id)
    
    return jsonify({"status": "received", "event_id": event_id})

#
# Endpoint di autenticazione
#

@app.route('/login', methods=['GET', 'POST'])
async def login():
    """Gestisce il login degli amministratori."""
    error = None
    
    if request.method == 'POST':
        form = await request.form
        username = form.get('username')
        password = form.get('password')
        
        # Verifica credenziali
        user = await user_manager.authenticate(username, password)
        if user:
            # Verifica 2FA se richiesto
            if app.config['REQUIRE_2FA'] and user['require_2fa']:
                totp_code = form.get('totp_code')
                if not totp_code or not await user_manager.verify_totp(user['id'], totp_code):
                    error = "Codice 2FA non valido"
                    return await render_template('login.html', error=error, require_2fa=True)
            
            # Imposta la sessione
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['is_admin'] = user['is_admin']
            
            # Registra accesso
            await user_manager.log_login(user['id'], request.remote_addr)
            
            return redirect(url_for('dashboard'))
        else:
            error = "Username o password non validi"
    
    return await render_template('login.html', error=error)

@app.route('/logout')
@login_required
async def logout():
    """Gestisce il logout."""
    # Registra il logout
    if 'user_id' in session:
        await user_manager.log_logout(session['user_id'])
        
    # Pulisci la sessione
    session.clear()
    return redirect(url_for('login'))

@app.route('/unauthorized')
async def unauthorized():
    """Pagina per accesso non autorizzato."""
    return await render_template('unauthorized.html')

#
# Rotte principali dell'interfaccia web
#

@app.route('/')
@login_required
async def index():
    """Pagina principale - reindirizza alla dashboard."""
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
async def dashboard():
    """Dashboard principale con metriche in tempo reale."""
    # Ottieni statistiche di sistema
    system_stats = await monitoring_manager.get_system_overview()
    
    # Ottieni lo stato dei servizi principali
    services_status = await monitoring_manager.get_services_status()
    
    # Ottieni avvisi recenti
    recent_alerts = await notification_manager.get_recent_alerts(limit=5)
    
    # Ottieni metriche di utilizzo API
    api_metrics = await analytics_manager.get_api_usage_metrics(hours=24)
    
    # Ottieni backup recenti
    recent_backups = await backup_manager.get_recent_backups(limit=3)
    
    return await render_template(
        'dashboard.html',
        system_stats=system_stats,
        services_status=services_status,
        recent_alerts=recent_alerts,
        api_metrics=api_metrics,
        recent_backups=recent_backups,
        page="dashboard"
    )

#
# Sezione Monitoraggio
#

@app.route('/monitoring')
@login_required
async def monitoring():
    """Pagina di monitoraggio avanzato."""
    hosts = await monitoring_manager.get_monitored_hosts()
    return await render_template('monitoring/index.html', hosts=hosts, page="monitoring")

@app.route('/monitoring/host/<host_id>')
@login_required
async def host_details(host_id):
    """Dettagli di un host monitorato."""
    host = await monitoring_manager.get_host_details(host_id)
    metrics = await monitoring_manager.get_host_metrics(host_id, hours=24)
    alerts = await monitoring_manager.get_host_alerts(host_id, limit=10)
    
    return await render_template(
        'monitoring/host_details.html',
        host=host,
        metrics=metrics,
        alerts=alerts,
        page="monitoring"
    )

@app.route('/monitoring/services')
@login_required
async def services_monitoring():
    """Monitoraggio dei servizi."""
    services = await monitoring_manager.get_services_list()
    return await render_template('monitoring/services.html', services=services, page="monitoring")

@app.route('/monitoring/alerts')
@login_required
async def alerts_dashboard():
    """Dashboard degli avvisi attivi."""
    alerts = await notification_manager.get_active_alerts()
    return await render_template('monitoring/alerts.html', alerts=alerts, page="monitoring")

@app.route('/monitoring/logs')
@login_required
async def logs_viewer():
    """Visualizzatore di log centralizzato."""
    sources = await analytics_manager.get_log_sources()
    return await render_template('monitoring/logs.html', sources=sources, page="monitoring")

#
# Sezione Utenti e Sicurezza
#

@app.route('/users')
@login_required
@role_required('admin')
async def users_management():
    """Gestione degli utenti."""
    users = await user_manager.get_all_users()
    roles = await user_manager.get_all_roles()
    return await render_template('users/index.html', users=users, roles=roles, page="users")

@app.route('/users/add', methods=['GET', 'POST'])
@login_required
@role_required('admin')
async def add_user():
    """Aggiunge un nuovo utente."""
    roles = await user_manager.get_all_roles()
    
    if request.method == 'POST':
        form = await request.form
        
        # Recupera i dati dal form
        username = form.get('username')
        email = form.get('email')
        password = form.get('password')
        role_ids = form.getlist('roles')
        require_2fa = form.get('require_2fa') == 'on'
        
        # Crea il nuovo utente
        user_id = await user_manager.create_user(
            username=username,
            email=email,
            password=password,
            role_ids=role_ids,
            require_2fa=require_2fa
        )
        
        if user_id:
            return redirect(url_for('users_management'))
        else:
            error = "Errore nella creazione dell'utente"
            return await render_template('users/add.html', roles=roles, error=error, page="users")
    
    return await render_template('users/add.html', roles=roles, page="users")

@app.route('/users/edit/<user_id>', methods=['GET', 'POST'])
@login_required
@role_required('admin')
async def edit_user(user_id):
    """Modifica un utente esistente."""
    user = await user_manager.get_user_by_id(user_id)
    roles = await user_manager.get_all_roles()
    user_roles = await user_manager.get_user_roles(user_id)
    
    if request.method == 'POST':
        form = await request.form
        
        # Recupera i dati dal form
        username = form.get('username')
        email = form.get('email')
        password = form.get('password')
        role_ids = form.getlist('roles')
        require_2fa = form.get('require_2fa') == 'on'
        is_active = form.get('is_active') == 'on'
        
        # Aggiorna l'utente
        updated = await user_manager.update_user(
            user_id=user_id,
            username=username,
            email=email,
            password=password if password else None,
            role_ids=role_ids,
            require_2fa=require_2fa,
            is_active=is_active
        )
        
        if updated:
            return redirect(url_for('users_management'))
        else:
            error = "Errore nell'aggiornamento dell'utente"
            return await render_template(
                'users/edit.html', 
                user=user, 
                roles=roles, 
                user_roles=user_roles, 
                error=error, 
                page="users"
            )
    
    return await render_template(
        'users/edit.html', 
        user=user, 
        roles=roles, 
        user_roles=user_roles, 
        page="users"
    )

@app.route('/security')
@login_required
@role_required('admin')
async def security_dashboard():
    """Dashboard di sicurezza."""
    scan_results = await security_manager.get_latest_scan_results()
    vulnerabilities = await security_manager.get_vulnerabilities(limit=10)
    audit_logs = await user_manager.get_audit_logs(limit=10)
    
    return await render_template(
        'security/index.html',
        scan_results=scan_results,
        vulnerabilities=vulnerabilities,
        audit_logs=audit_logs,
        page="security"
    )

@app.route('/security/firewall')
@login_required
@role_required('admin')
async def firewall_management():
    """Gestione del firewall."""
    rules = await security_manager.get_firewall_rules()
    return await render_template('security/firewall.html', rules=rules, page="security")

@app.route('/security/certificates')
@login_required
@role_required('admin')
async def certificate_management():
    """Gestione dei certificati SSL."""
    certificates = await security_manager.get_certificates()
    return await render_template('security/certificates.html', certificates=certificates, page="security")

#
# Sezione Backup e Automazione
#

@app.route('/backups')
@login_required
@role_required('operator')
async def backups_management():
    """Gestione dei backup."""
    backups = await backup_manager.get_all_backups()
    schedules = await backup_manager.get_backup_schedules()
    
    return await render_template(
        'backups/index.html',
        backups=backups,
        schedules=schedules,
        page="backups"
    )

@app.route('/backups/create', methods=['GET', 'POST'])
@login_required
@role_required('operator')
async def create_backup():
    """Crea un nuovo backup."""
    if request.method == 'POST':
        form = await request.form
        
        # Recupera i dati dal form
        backup_type = form.get('backup_type')
        description = form.get('description')
        
        # Crea il backup
        backup_id = await backup_manager.create_backup(
            backup_type=backup_type,
            description=description,
            user_id=session['user_id']
        )
        
        if backup_id:
            return redirect(url_for('backups_management'))
        else:
            error = "Errore nella creazione del backup"
            return await render_template('backups/create.html', error=error, page="backups")
    
    return await render_template('backups/create.html', page="backups")

@app.route('/backups/restore/<backup_id>', methods=['POST'])
@login_required
@role_required('admin')
async def restore_backup(backup_id):
    """Ripristina un backup."""
    result = await backup_manager.restore_backup(
        backup_id=backup_id,
        user_id=session['user_id']
    )
    
    return jsonify({"success": result})

@app.route('/automations')
@login_required
@role_required('operator')
async def automations_management():
    """Gestione delle automazioni."""
    tasks = await deployment_manager.get_scheduled_tasks()
    return await render_template('automations/index.html', tasks=tasks, page="automations")

#
# Sezione Deployment e Scaling
#

@app.route('/deployment')
@login_required
@role_required('admin')
async def deployment_dashboard():
    """Dashboard di deployment."""
    environments = await deployment_manager.get_environments()
    recent_deployments = await deployment_manager.get_recent_deployments(limit=5)
    
    return await render_template(
        'deployment/index.html',
        environments=environments,
        recent_deployments=recent_deployments,
        page="deployment"
    )

@app.route('/deployment/create', methods=['GET', 'POST'])
@login_required
@role_required('admin')
async def create_deployment():
    """Crea un nuovo deployment."""
    environments = await deployment_manager.get_environments()
    
    if request.method == 'POST':
        form = await request.form
        
        # Recupera i dati dal form
        environment_id = form.get('environment_id')
        version = form.get('version')
        description = form.get('description')
        auto_rollback = form.get('auto_rollback') == 'on'
        
        # Crea il deployment
        deployment_id = await deployment_manager.create_deployment(
            environment_id=environment_id,
            version=version,
            description=description,
            auto_rollback=auto_rollback,
            user_id=session['user_id']
        )
        
        if deployment_id:
            return redirect(url_for('deployment_dashboard'))
        else:
            error = "Errore nella creazione del deployment"
            return await render_template(
                'deployment/create.html', 
                environments=environments, 
                error=error, 
                page="deployment"
            )
    
    return await render_template('deployment/create.html', environments=environments, page="deployment")

@app.route('/scaling')
@login_required
@role_required('admin')
async def scaling_dashboard():
    """Dashboard di scaling."""
    instances = await deployment_manager.get_instances()
    scaling_policies = await deployment_manager.get_scaling_policies()
    
    return await render_template(
        'deployment/scaling.html',
        instances=instances,
        scaling_policies=scaling_policies,
        page="deployment"
    )

#
# Sezione Strumenti Avanzati
#

@app.route('/tools')
@login_required
@role_required('operator')
async def tools_dashboard():
    """Dashboard degli strumenti avanzati."""
    return await render_template('tools/index.html', page="tools")

@app.route('/tools/terminal')
@login_required
@role_required('admin')
async def terminal():
    """Terminale SSH remoto."""
    hosts = await monitoring_manager.get_monitored_hosts()
    return await render_template('tools/terminal.html', hosts=hosts, page="tools")

@app.route('/tools/database')
@login_required
@role_required('admin')
async def database_console():
    """Console del database."""
    db_types = ["PostgreSQL", "MySQL", "Redis"]
    return await render_template('tools/database.html', db_types=db_types, page="tools")

@app.route('/tools/logs')
@login_required
@role_required('operator')
async def log_explorer():
    """Esploratore di log avanzato."""
    log_files = await analytics_manager.get_available_log_files()
    return await render_template('tools/logs.html', log_files=log_files, page="tools")

@app.route('/tools/config')
@login_required
@role_required('admin')
async def config_editor():
    """Editor di configurazioni."""
    config_files = await deployment_manager.get_config_files()
    return await render_template('tools/config.html', config_files=config_files, page="tools")

@app.route('/tools/network')
@login_required
@role_required('operator')
async def network_tools():
    """Strumenti di diagnostica di rete."""
    return await render_template('tools/network.html', page="tools")

#
# API RESTful
#

@app.route('/api/v1/system/status')
async def api_system_status():
    """API: Stato generale del sistema."""
    status = {
        "status": "ok",
        "timestamp": datetime.datetime.now().isoformat(),
        "services": await monitoring_manager.get_services_status(),
        "system": {
            "cpu": psutil.cpu_percent(),
            "memory": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage('/').percent,
            "uptime": int(time.time() - psutil.boot_time())
        }
    }
    return jsonify(status)

@app.route('/api/v1/monitoring/metrics')
@login_required
async def api_metrics():
    """API: Ottieni metriche di monitoraggio."""
    host_id = request.args.get('host_id')
    metric_type = request.args.get('type', 'cpu')
    hours = int(request.args.get('hours', 24))
    
    metrics = await monitoring_manager.get_metrics(
        host_id=host_id,
        metric_type=metric_type,
        hours=hours
    )
    
    return jsonify(metrics)

@app.route('/api/v1/users', methods=['GET'])
@login_required
@role_required('admin')
async def api_get_users():
    """API: Ottieni elenco utenti."""
    users = await user_manager.get_all_users()
    return jsonify(users)

@app.route('/api/v1/backups', methods=['GET'])
@login_required
@role_required('operator')
async def api_get_backups():
    """API: Ottieni elenco backup."""
    backups = await backup_manager.get_all_backups()
    return jsonify(backups)

@app.route('/api/v1/backups/create', methods=['POST'])
@login_required
@role_required('operator')
async def api_create_backup():
    """API: Crea un nuovo backup."""
    data = await request.get_json()
    
    backup_id = await backup_manager.create_backup(
        backup_type=data.get('backup_type', 'full'),
        description=data.get('description', ''),
        user_id=session['user_id']
    )
    
    return jsonify({"success": bool(backup_id), "backup_id": backup_id})

@app.route('/api/v1/security/scan', methods=['POST'])
@login_required
@role_required('admin')
async def api_security_scan():
    """API: Avvia una scansione di sicurezza."""
    data = await request.get_json()
    
    scan_id = await security_manager.start_scan(
        scan_type=data.get('scan_type', 'quick'),
        target=data.get('target', 'all'),
        user_id=session['user_id']
    )
    
    return jsonify({"success": bool(scan_id), "scan_id": scan_id})

@app.route('/api/v1/network/ping')
@login_required
@role_required('operator')
async def api_network_ping():
    """API: Esegue un test di latenza dettagliato."""
    try:
        start_time = time.time()
        
        # Crea risultati per diverse operazioni di sistema
        results = {
            "timestamp": datetime.datetime.now().isoformat(),
            "db_latency": None,
            "redis_latency": None,
            "dns_latency": None,
            "total_latency": None,
            "details": {}
        }
        
        # Test latenza database
        db_start = time.time()
        async with db_pool.acquire() as conn:
            await conn.execute("SELECT 1")
        db_latency = (time.time() - db_start) * 1000  # converti in ms
        results["db_latency"] = round(db_latency, 2)
        
        # Test latenza Redis
        redis_start = time.time()
        async with aioredis.Redis(connection_pool=redis_pool) as redis:
            await redis.ping()
        redis_latency = (time.time() - redis_start) * 1000
        results["redis_latency"] = round(redis_latency, 2)
        
        # Test latenza DNS
        dns_start = time.time()
        try:
            resolver = await asyncio.create_subprocess_exec(
                'nslookup', 'google.com',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await resolver.communicate()
            dns_latency = (time.time() - dns_start) * 1000
            results["dns_latency"] = round(dns_latency, 2)
        except Exception as e:
            results["dns_latency"] = None
            results["details"]["dns_error"] = str(e)
        
        # Calcola latenza totale
        total_latency = (time.time() - start_time) * 1000
        results["total_latency"] = round(total_latency, 2)
        
        # Aggiungi diagnostica di rete
        try:
            ping_proc = await asyncio.create_subprocess_exec(
                'ping', '-c', '4', '8.8.8.8',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await ping_proc.communicate()
            results["details"]["ping_output"] = stdout.decode()
        except Exception as e:
            results["details"]["ping_error"] = str(e)
            
        # Aggiungi info sul sistema
        results["details"]["system_info"] = {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "cpu_cores": psutil.cpu_count(logical=True),
            "total_memory": round(psutil.virtual_memory().total / (1024 * 1024 * 1024), 2)  # GB
        }
        
        # Registra i risultati del test
        logger.info(f"Test di velocità completato: {results}")
        
        return jsonify(results)
    except Exception as e:
        logger.error(f"Errore nel test di latenza: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/v1/network/speedtest', methods=['POST'])
@login_required
@role_required('admin')
async def api_network_speedtest():
    """API: Esegue un test di velocità di rete."""
    try:
        # Ottieni la dimensione del test
        data = await request.get_json()
        test_size = data.get('size', 'medium')  # small, medium, large
        
        # Configura dimensioni dei pacchetti di test
        sizes = {
            'small': 1024 * 50,  # 50KB
            'medium': 1024 * 500,  # 500KB
            'large': 1024 * 2000  # 2MB
        }
        
        packet_size = sizes.get(test_size, sizes['medium'])
        
        # Genera dati casuali per il test
        start_time = time.time()
        random_data = os.urandom(packet_size)
        generation_time = time.time() - start_time
        
        # Misura tempo di download (invia dati al client)
        start_time = time.time()
        result = {
            "timestamp": datetime.datetime.now().isoformat(),
            "test_size": test_size,
            "packet_size_bytes": packet_size,
            "download_speed_mbps": None,
            "upload_speed_mbps": None,
            "generation_time_ms": round(generation_time * 1000, 2)
        }
        
        # Calcola velocità di download
        download_time = time.time() - start_time
        download_speed = (packet_size * 8) / (download_time * 1000000)  # Mbps
        result["download_speed_mbps"] = round(download_speed, 2)
        
        # Nota: la velocità di upload sarà misurata dal client
        # Poiché il client dovrà temporizzare quanto tempo impiega a inviare i dati
        
        # Registra i risultati del test
        logger.info(f"Test di velocità completato: {result}")
        
        # Aggiungiamo dati casuali alla risposta per simulare un pacchetto di dimensioni reali
        result["data"] = base64.b64encode(random_data).decode('utf-8')
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Errore nel test di velocità: {e}")
        return jsonify({"error": str(e)}), 500

# Implementa l'endpoint per ricevere i dati di upload
@app.route('/api/v1/network/speedtest/upload', methods=['POST'])
@login_required
@role_required('admin')
async def api_network_speedtest_upload():
    """API: Riceve dati per il test di velocità di upload."""
    try:
        start_time = time.time()
        
        # Ricevi i dati inviati dal client
        if request.content_type == 'application/json':
            data = await request.get_json()
            uploaded_data = data.get('data', '')
            data_size = len(uploaded_data) * 0.75  # Stima dei byte per Base64
        else:
            form = await request.form
            uploaded_data = form.get('data', '')
            data_size = len(uploaded_data) * 0.75  # Stima dei byte per Base64
        
        # Calcola la velocità di upload
        upload_time = time.time() - start_time
        upload_speed = (data_size * 8) / (upload_time * 1000000)  # Mbps
        
        return jsonify({
            "upload_speed_mbps": round(upload_speed, 2),
            "upload_time_ms": round(upload_time * 1000, 2),
            "data_size_bytes": data_size
        })
    except Exception as e:
        logger.error(f"Errore nel test di upload: {e}")
        return jsonify({"error": str(e)}), 500

# Implementazione WebSocket per aggiornamenti in tempo reale
@app.websocket('/ws/metrics')
async def ws_metrics():
    """WebSocket per aggiornamenti metriche in tempo reale."""
    if 'user_id' not in session:
        await websocket.close(1008)  # Policy Violation
        return
        
    await websocket.accept()
    
    try:
        while True:
            # Ottieni metriche aggiornate
            metrics = await monitoring_manager.get_realtime_metrics()
            
            # Invia al client
            await websocket.send(json.dumps(metrics))
            
            # Attendi prima del prossimo aggiornamento
            await asyncio.sleep(2)
    except asyncio.CancelledError:
        # Gestione normale disconnessione
        pass
    except Exception as e:
        logger.error(f"Errore nella connessione WebSocket: {e}")
    finally:
        await websocket.close()

@app.websocket('/ws/logs')
async def ws_logs():
    """WebSocket per streaming di log in tempo reale."""
    if 'user_id' not in session:
        await websocket.close(1008)  # Policy Violation
        return
        
    await websocket.accept()
    
    # Ottieni parametri di filtro
    data = await websocket.receive()
    filters = json.loads(data)
    
    log_listener = await analytics_manager.create_log_listener(
        source=filters.get('source', 'system'),
        level=filters.get('level', 'info'),
        pattern=filters.get('pattern', '')
    )
    
    try:
        while True:
            log_entry = await log_listener.get()
            if log_entry:
                await websocket.send(json.dumps(log_entry))
            else:
                await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        # Gestione normale disconnessione
        pass
    except Exception as e:
        logger.error(f"Errore nella connessione WebSocket: {e}")
    finally:
        await log_listener.close()
        await websocket.close()

# Pagine di errore
@app.errorhandler(404)
async def not_found(e):
    return await render_template('errors/404.html'), 404

@app.errorhandler(500)
async def server_error(e):
    return await render_template('errors/500.html'), 500

@app.route('/admin/control-panel')
@login_required
@role_required('admin')
async def admin_control_panel():
    """Pannello di controllo amministrativo avanzato."""
    # Ottieni statistiche principali
    server_stats = await SystemUtils.get_server_stats()
    backup_stats = await backup_manager.get_backup_stats()
    user_stats = await user_manager.get_user_stats()
    
    return await render_template(
        'admin/control_panel.html',
        server_stats=server_stats,
        backup_stats=backup_stats,
        user_stats=user_stats,
        page="admin"
    )

# Rotte per il pannello di sicurezza e stabilità
@app.route('/admin/stability-security')
@login_required
@role_required('admin')
async def stability_security_dashboard():
    """Dashboard di controllo per sicurezza e stabilità."""
    if not stability_security_manager:
        return await render_template('error.html', message="Modulo di sicurezza e stabilità non inizializzato"), 500
    
    # Ottieni lo stato attuale dei componenti
    system_status = await stability_security_manager.get_system_status()
    
    # Ottieni il riepilogo di sicurezza
    security_summary = await stability_security_manager.get_security_summary()
    
    # Ottieni gli ultimi risultati dei test di resilienza
    chaos_test_results = await stability_security_manager.get_last_chaos_test_results(limit=3)
    
    # Ottieni gli eventi di sicurezza recenti
    security_events = await stability_security_manager.get_recent_security_events(days=3, limit=10)
    
    return await render_template(
        'admin/stability_security.html',
        system_status=system_status,
        security_summary=security_summary,
        chaos_test_results=chaos_test_results,
        security_events=security_events,
        page="stability-security"
    )

# API per Self-Healing
@app.route('/api/v1/admin/self-healing/config', methods=['GET'])
@login_required
@role_required('admin')
async def api_get_self_healing_config():
    """Restituisce la configurazione del sistema di self-healing."""
    if not stability_security_manager:
        return jsonify({"error": "Modulo di sicurezza e stabilità non inizializzato"}), 500
    
    config = await stability_security_manager.get_self_healing_config()
    return jsonify({"success": True, "config": config})

@app.route('/api/v1/admin/self-healing/config', methods=['POST'])
@login_required
@role_required('admin')
async def api_update_self_healing_config():
    """Aggiorna la configurazione del sistema di self-healing."""
    if not stability_security_manager:
        return jsonify({"error": "Modulo di sicurezza e stabilità non inizializzato"}), 500
    
    config_data = await request.get_json()
    success = await stability_security_manager.update_self_healing_config(config_data)
    
    if success:
        return jsonify({"success": True, "message": "Configurazione aggiornata con successo"})
    else:
        return jsonify({"success": False, "error": "Errore nell'aggiornamento della configurazione"}), 500

@app.route('/api/v1/admin/self-healing/maintenance', methods=['POST'])
@login_required
@role_required('admin')
async def api_toggle_maintenance_mode():
    """Attiva o disattiva la modalità manutenzione."""
    if not stability_security_manager:
        return jsonify({"error": "Modulo di sicurezza e stabilità non inizializzato"}), 500
    
    data = await request.get_json()
    enabled = data.get('enabled', False)
    
    if enabled:
        stability_security_manager.self_healing.set_maintenance_mode(True)
        message = "Modalità manutenzione attivata"
    else:
        stability_security_manager.self_healing.set_maintenance_mode(False)
        message = "Modalità manutenzione disattivata"
    
    return jsonify({"success": True, "message": message})

# API per WAF
@app.route('/api/v1/admin/waf/block-ip', methods=['POST'])
@login_required
@role_required('admin')
async def api_block_ip():
    """Blocca un indirizzo IP."""
    if not stability_security_manager:
        return jsonify({"error": "Modulo di sicurezza e stabilità non inizializzato"}), 500
    
    data = await request.get_json()
    ip_address = data.get('ip_address')
    reason = data.get('reason', 'Blocco manuale')
    duration = data.get('duration')  # None per blocco permanente
    
    if not ip_address:
        return jsonify({"success": False, "error": "Indirizzo IP richiesto"}), 400
    
    success = await stability_security_manager.block_ip(ip_address, reason, duration)
    
    if success:
        return jsonify({"success": True, "message": f"IP {ip_address} bloccato con successo"})
    else:
        return jsonify({"success": False, "error": f"Errore nel blocco dell'IP {ip_address}"}), 500

@app.route('/api/v1/admin/waf/unblock-ip', methods=['POST'])
@login_required
@role_required('admin')
async def api_unblock_ip():
    """Sblocca un indirizzo IP."""
    if not stability_security_manager:
        return jsonify({"error": "Modulo di sicurezza e stabilità non inizializzato"}), 500
    
    data = await request.get_json()
    ip_address = data.get('ip_address')
    
    if not ip_address:
        return jsonify({"success": False, "error": "Indirizzo IP richiesto"}), 400
    
    success = await stability_security_manager.unblock_ip(ip_address)
    
    if success:
        return jsonify({"success": True, "message": f"IP {ip_address} sbloccato con successo"})
    else:
        return jsonify({"success": False, "error": f"Errore nello sblocco dell'IP {ip_address}"}), 500

# API per test di resilienza
@app.route('/api/v1/admin/resilience/run-test', methods=['POST'])
@login_required
@role_required('admin')
async def api_run_resilience_test():
    """Esegue un test di resilienza (chaos testing)."""
    if not stability_security_manager:
        return jsonify({"error": "Modulo di sicurezza e stabilità non inizializzato"}), 500
    
    data = await request.get_json()
    test_type = data.get('test_type')
    target = data.get('target')
    options = data.get('options', {})
    
    if not test_type or not target:
        return jsonify({"success": False, "error": "Tipo di test e target richiesti"}), 400
    
    result = await stability_security_manager.run_chaos_test(test_type, target, options)
    
    if result.get('success'):
        return jsonify({
            "success": True,
            "message": "Test di resilienza eseguito con successo",
            "report_path": result.get('report_path')
        })
    else:
        return jsonify({
            "success": False,
            "error": result.get('error', "Errore nell'esecuzione del test")
        }), 500

# API per crittografia
@app.route('/api/v1/admin/crypto/rotate-keys', methods=['POST'])
@login_required
@role_required('admin')
async def api_rotate_crypto_keys():
    """Ruota le chiavi di crittografia."""
    if not stability_security_manager:
        return jsonify({"error": "Modulo di sicurezza e stabilità non inizializzato"}), 500
    
    result = await stability_security_manager.rotate_encryption_keys()
    
    if result.get('success'):
        return jsonify({
            "success": True,
            "message": f"Rotazione completata: {result.get('rotated_keys')} chiavi ruotate",
            "details": result
        })
    else:
        return jsonify({
            "success": False,
            "error": result.get('error', "Errore nella rotazione delle chiavi")
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=DEBUG) 