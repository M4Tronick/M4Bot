"""
Route per la gestione dell'autenticazione a due fattori (2FA)
"""

import logging
from quart import Blueprint, request, render_template, redirect, url_for, session, jsonify, flash
from quart import current_app
from functools import wraps

from web.security.two_factor import TwoFactorAuth

# Setup del logger
logger = logging.getLogger('m4bot.routes.two_factor')

# Creazione del blueprint
two_factor_bp = Blueprint('two_factor', __name__, url_prefix='/account/2fa')

# Decoratore per verificare che l'utente sia autenticato
def login_required(f):
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        try:
            return await f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Errore in {f.__name__}: {e}")
            return await render_template('error.html', message=f"Errore del server: {str(e)}"), 500
    return decorated_function

# Route per la configurazione iniziale del 2FA
@two_factor_bp.route('/setup', methods=['GET', 'POST'])
@login_required
async def setup():
    """Pagina di configurazione iniziale del 2FA"""
    user_id = session.get('user_id')
    
    # Verifica se l'utente ha già abilitato il 2FA
    two_fa_config = await TwoFactorAuth.get_user_2fa(user_id)
    
    if two_fa_config and two_fa_config['enabled']:
        flash("L'autenticazione a due fattori è già abilitata per il tuo account.", "info")
        return redirect(url_for('two_factor.manage'))
    
    if request.method == 'POST':
        form = await request.form
        verification_code = form.get('verification_code')
        
        if not verification_code:
            flash("Il codice di verifica è obbligatorio.", "error")
            return redirect(url_for('two_factor.setup'))
        
        # Ottieni il secret dalla sessione
        secret = session.get('2fa_secret')
        
        if not secret:
            flash("Sessione scaduta, riprova.", "error")
            return redirect(url_for('two_factor.setup'))
        
        # Verifica il codice
        valid = await TwoFactorAuth.verify_totp_code(secret, verification_code)
        
        if valid:
            # Genera codici di backup
            backup_codes = await TwoFactorAuth.generate_backup_codes()
            
            # Salva la configurazione 2FA
            success = await TwoFactorAuth.save_user_2fa(user_id, secret, backup_codes, True)
            
            if success:
                # Marca la sessione come verificata con 2FA
                await TwoFactorAuth.mark_2fa_verified(user_id)
                
                # Rimuovi il secret dalla sessione
                if '2fa_secret' in session:
                    del session['2fa_secret']
                
                # Salva i codici di backup nella sessione per mostrarli all'utente
                session['backup_codes'] = backup_codes
                
                flash("Autenticazione a due fattori abilitata con successo!", "success")
                return redirect(url_for('two_factor.backup_codes'))
            else:
                flash("Errore nell'abilitazione del 2FA. Riprova più tardi.", "error")
                return redirect(url_for('two_factor.setup'))
        else:
            flash("Codice di verifica non valido. Riprova.", "error")
            return redirect(url_for('two_factor.setup'))
    
    # Ottieni username per generare QR code
    username = "utente"
    if hasattr(current_app, 'db_pool') and current_app.db_pool:
        try:
            async with current_app.db_pool.acquire() as conn:
                user = await conn.fetchrow("SELECT username, email FROM users WHERE id = $1", user_id)
                if user:
                    username = user['username'] or user['email']
        except Exception as e:
            logger.error(f"Errore nell'ottenimento delle informazioni utente: {e}")
    
    # Genera un nuovo secret
    secret = await TwoFactorAuth.generate_secret()
    
    # Salva il secret nella sessione
    session['2fa_secret'] = secret
    
    # Genera l'URI TOTP
    totp_uri = await TwoFactorAuth.generate_totp_uri(secret, username)
    
    # Genera il QR code
    qr_code = await TwoFactorAuth.generate_qr_code(totp_uri)
    
    return await render_template(
        'security/2fa_setup.html', 
        secret=secret, 
        qr_code=qr_code,
        username=username
    )

# Route per la visualizzazione dei codici di backup
@two_factor_bp.route('/backup-codes', methods=['GET'])
@login_required
async def backup_codes():
    """Pagina di visualizzazione dei codici di backup"""
    user_id = session.get('user_id')
    
    # Ottieni i codici di backup dalla sessione
    backup_codes = session.get('backup_codes')
    
    if not backup_codes:
        # Se non sono nella sessione, ottienili dal database
        two_fa_config = await TwoFactorAuth.get_user_2fa(user_id)
        
        if not two_fa_config or not two_fa_config['enabled']:
            flash("L'autenticazione a due fattori non è abilitata per il tuo account.", "error")
            return redirect(url_for('two_factor.setup'))
        
        backup_codes = two_fa_config['backup_codes']
    
    # Rimuovi i codici di backup dalla sessione
    if 'backup_codes' in session:
        del session['backup_codes']
    
    return await render_template(
        'security/2fa_backup_codes.html', 
        backup_codes=backup_codes
    )

# Route per la gestione del 2FA
@two_factor_bp.route('/manage', methods=['GET'])
@login_required
async def manage():
    """Pagina di gestione del 2FA"""
    user_id = session.get('user_id')
    
    # Ottieni la configurazione 2FA dell'utente
    two_fa_config = await TwoFactorAuth.get_user_2fa(user_id)
    
    return await render_template(
        'security/2fa_manage.html', 
        two_fa_config=two_fa_config
    )

# Route per la disabilitazione del 2FA
@two_factor_bp.route('/disable', methods=['POST'])
@login_required
async def disable():
    """Disabilitazione del 2FA"""
    user_id = session.get('user_id')
    
    # Verifica la password dell'utente per sicurezza
    form = await request.form
    password = form.get('password')
    
    if not password:
        flash("La password è obbligatoria per disabilitare il 2FA.", "error")
        return redirect(url_for('two_factor.manage'))
    
    # Verifica la password dell'utente
    password_valid = False
    if hasattr(current_app, 'db_pool') and current_app.db_pool:
        try:
            import bcrypt
            async with current_app.db_pool.acquire() as conn:
                stored_hash = await conn.fetchval(
                    "SELECT password_hash FROM users WHERE id = $1", 
                    user_id
                )
                
                if stored_hash:
                    password_valid = bcrypt.checkpw(
                        password.encode(), 
                        stored_hash.encode() if isinstance(stored_hash, str) else stored_hash
                    )
        except Exception as e:
            logger.error(f"Errore nella verifica della password: {e}")
    
    if not password_valid:
        flash("Password non valida.", "error")
        return redirect(url_for('two_factor.manage'))
    
    # Disabilita il 2FA
    success = await TwoFactorAuth.disable_2fa(user_id)
    
    if success:
        # Resetta la sessione 2FA
        await TwoFactorAuth.reset_2fa_session()
        
        flash("Autenticazione a due fattori disabilitata con successo.", "success")
    else:
        flash("Errore nella disabilitazione del 2FA. Riprova più tardi.", "error")
    
    return redirect(url_for('account.security'))

# Route per rigenerare i codici di backup
@two_factor_bp.route('/regenerate-backup-codes', methods=['POST'])
@login_required
async def regenerate_backup_codes():
    """Rigenerazione dei codici di backup"""
    user_id = session.get('user_id')
    
    # Verifica la password dell'utente per sicurezza
    form = await request.form
    password = form.get('password')
    
    if not password:
        flash("La password è obbligatoria per rigenerare i codici di backup.", "error")
        return redirect(url_for('two_factor.manage'))
    
    # Verifica la password dell'utente
    password_valid = False
    if hasattr(current_app, 'db_pool') and current_app.db_pool:
        try:
            import bcrypt
            async with current_app.db_pool.acquire() as conn:
                stored_hash = await conn.fetchval(
                    "SELECT password_hash FROM users WHERE id = $1", 
                    user_id
                )
                
                if stored_hash:
                    password_valid = bcrypt.checkpw(
                        password.encode(), 
                        stored_hash.encode() if isinstance(stored_hash, str) else stored_hash
                    )
        except Exception as e:
            logger.error(f"Errore nella verifica della password: {e}")
    
    if not password_valid:
        flash("Password non valida.", "error")
        return redirect(url_for('two_factor.manage'))
    
    # Ottieni la configurazione 2FA attuale
    two_fa_config = await TwoFactorAuth.get_user_2fa(user_id)
    
    if not two_fa_config or not two_fa_config['enabled']:
        flash("L'autenticazione a due fattori non è abilitata per il tuo account.", "error")
        return redirect(url_for('two_factor.setup'))
    
    # Genera nuovi codici di backup
    backup_codes = await TwoFactorAuth.generate_backup_codes()
    
    # Aggiorna la configurazione 2FA
    success = await TwoFactorAuth.save_user_2fa(
        user_id, 
        two_fa_config['secret'], 
        backup_codes, 
        True
    )
    
    if success:
        # Salva i codici di backup nella sessione per mostrarli all'utente
        session['backup_codes'] = backup_codes
        
        flash("Codici di backup rigenerati con successo!", "success")
        return redirect(url_for('two_factor.backup_codes'))
    else:
        flash("Errore nella rigenerazione dei codici di backup. Riprova più tardi.", "error")
        return redirect(url_for('two_factor.manage'))

# Route per la verifica 2FA durante il login
@two_factor_bp.route('/verify', methods=['GET', 'POST'])
async def verify():
    """Pagina di verifica 2FA durante il login"""
    user_id = session.get('2fa_user_id')
    
    if not user_id:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        form = await request.form
        verification_code = form.get('verification_code')
        backup_code = form.get('backup_code')
        
        if not verification_code and not backup_code:
            flash("È necessario fornire un codice di verifica o un codice di backup.", "error")
            return redirect(url_for('two_factor.verify'))
        
        # Ottieni la configurazione 2FA dell'utente
        two_fa_config = await TwoFactorAuth.get_user_2fa(user_id)
        
        if not two_fa_config or not two_fa_config['enabled']:
            # L'utente non ha il 2FA abilitato, completa direttamente il login
            session['user_id'] = user_id
            if '2fa_user_id' in session:
                del session['2fa_user_id']
            return redirect(url_for('dashboard'))
        
        valid = False
        
        if verification_code:
            # Verifica il codice TOTP
            valid = await TwoFactorAuth.verify_totp_code(two_fa_config['secret'], verification_code)
        elif backup_code:
            # Verifica il codice di backup
            valid = await TwoFactorAuth.verify_backup_code(user_id, backup_code)
        
        if valid:
            # Autenticazione 2FA completata con successo
            await TwoFactorAuth.mark_2fa_verified(user_id)
            
            # Rimuovi l'ID utente temporaneo
            if '2fa_user_id' in session:
                del session['2fa_user_id']
            
            # Imposta completamente la sessione dell'utente
            session['user_id'] = user_id
            
            # Reindirizza alla pagina richiesta o alla dashboard
            next_page = session.get('next') or url_for('dashboard')
            if 'next' in session:
                del session['next']
            
            return redirect(next_page)
        else:
            flash("Codice non valido. Riprova.", "error")
            return redirect(url_for('two_factor.verify'))
    
    return await render_template('security/2fa_verify.html')

# Inizializzazione del blueprint
def init_two_factor_bp(app):
    app.register_blueprint(two_factor_bp)
    logger.info("Blueprint per autenticazione a due fattori (2FA) registrato") 