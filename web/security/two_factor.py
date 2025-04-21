#!/usr/bin/env python3
"""
M4Bot - Modulo di autenticazione a due fattori (2FA)
Implementa l'autenticazione a due fattori utilizzando TOTP (Time-based One-Time Password)
"""

import os
import base64
import logging
import asyncio
import pyotp
import qrcode
from io import BytesIO
import base64
from quart import current_app, session
from datetime import datetime, timedelta
import secrets

# Configurazione del logger
logger = logging.getLogger('m4bot.security.two_factor')

# Configurazione
TOTP_ISSUER = "M4Bot"  # Nome visualizzato nell'app authenticator
BACKUP_CODES_COUNT = 10  # Numero di codici di backup da generare
BACKUP_CODE_LENGTH = 10  # Lunghezza dei codici di backup

class TwoFactorAuth:
    """Gestisce l'autenticazione a due fattori utilizzando TOTP"""
    
    @staticmethod
    async def generate_secret(user_id=None):
        """Genera un nuovo secret TOTP per un utente"""
        secret = pyotp.random_base32()
        return secret
    
    @staticmethod
    async def generate_totp_uri(secret, username, issuer=TOTP_ISSUER):
        """Genera un URI TOTP per la configurazione dell'app authenticator"""
        uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=username,
            issuer_name=issuer
        )
        return uri
    
    @staticmethod
    async def generate_qr_code(uri):
        """Genera un codice QR per la configurazione dell'app authenticator"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return img_str
    
    @staticmethod
    async def verify_totp_code(secret, code):
        """Verifica un codice TOTP fornito dall'utente"""
        totp = pyotp.TOTP(secret)
        return totp.verify(code)
    
    @staticmethod
    async def generate_backup_codes():
        """Genera codici di backup per il recupero in caso di perdita del dispositivo"""
        codes = []
        for _ in range(BACKUP_CODES_COUNT):
            # Genera un codice alfanumerico casuale
            code = secrets.token_urlsafe(BACKUP_CODE_LENGTH)[:BACKUP_CODE_LENGTH]
            codes.append(code)
        return codes
    
    @staticmethod
    async def save_user_2fa(user_id, secret, backup_codes, enabled=False):
        """Salva le informazioni 2FA di un utente nel database"""
        try:
            if hasattr(current_app, 'db_pool') and current_app.db_pool:
                async with current_app.db_pool.acquire() as conn:
                    # Controlla se esiste già una configurazione 2FA per l'utente
                    existing = await conn.fetchval(
                        "SELECT id FROM user_2fa WHERE user_id = $1", 
                        user_id
                    )
                    
                    if existing:
                        # Aggiorna la configurazione esistente
                        await conn.execute(
                            """
                            UPDATE user_2fa 
                            SET secret = $1, backup_codes = $2, enabled = $3, updated_at = $4
                            WHERE user_id = $5
                            """,
                            secret, 
                            backup_codes, 
                            enabled,
                            datetime.now(),
                            user_id
                        )
                    else:
                        # Inserisce una nuova configurazione
                        await conn.execute(
                            """
                            INSERT INTO user_2fa 
                            (user_id, secret, backup_codes, enabled, created_at, updated_at)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            """,
                            user_id,
                            secret,
                            backup_codes,
                            enabled,
                            datetime.now(),
                            datetime.now()
                        )
                    
                    return True
            else:
                logger.error("Pool di database non disponibile per salvare la configurazione 2FA")
                return False
        except Exception as e:
            logger.error(f"Errore nel salvataggio della configurazione 2FA: {e}")
            return False
    
    @staticmethod
    async def get_user_2fa(user_id):
        """Ottiene le informazioni 2FA di un utente"""
        try:
            if hasattr(current_app, 'db_pool') and current_app.db_pool:
                async with current_app.db_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT * FROM user_2fa WHERE user_id = $1", 
                        user_id
                    )
                    return row
            else:
                logger.error("Pool di database non disponibile per ottenere la configurazione 2FA")
                return None
        except Exception as e:
            logger.error(f"Errore nell'ottenimento della configurazione 2FA: {e}")
            return None
    
    @staticmethod
    async def enable_2fa(user_id):
        """Abilita il 2FA per un utente"""
        try:
            if hasattr(current_app, 'db_pool') and current_app.db_pool:
                async with current_app.db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE user_2fa SET enabled = TRUE, updated_at = $1 WHERE user_id = $2",
                        datetime.now(),
                        user_id
                    )
                    
                    # Registra l'operazione nel log di sicurezza
                    await conn.execute(
                        """
                        INSERT INTO security_log 
                        (user_id, action, ip_address, created_at)
                        VALUES ($1, $2, $3, $4)
                        """,
                        user_id,
                        "enable_2fa",
                        session.get('ip_address', 'unknown'),
                        datetime.now()
                    )
                    
                    return True
            else:
                logger.error("Pool di database non disponibile per abilitare il 2FA")
                return False
        except Exception as e:
            logger.error(f"Errore nell'abilitazione del 2FA: {e}")
            return False
    
    @staticmethod
    async def disable_2fa(user_id):
        """Disabilita il 2FA per un utente"""
        try:
            if hasattr(current_app, 'db_pool') and current_app.db_pool:
                async with current_app.db_pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE user_2fa SET enabled = FALSE, updated_at = $1 WHERE user_id = $2",
                        datetime.now(),
                        user_id
                    )
                    
                    # Registra l'operazione nel log di sicurezza
                    await conn.execute(
                        """
                        INSERT INTO security_log 
                        (user_id, action, ip_address, created_at)
                        VALUES ($1, $2, $3, $4)
                        """,
                        user_id,
                        "disable_2fa",
                        session.get('ip_address', 'unknown'),
                        datetime.now()
                    )
                    
                    return True
            else:
                logger.error("Pool di database non disponibile per disabilitare il 2FA")
                return False
        except Exception as e:
            logger.error(f"Errore nella disabilitazione del 2FA: {e}")
            return False
    
    @staticmethod
    async def verify_backup_code(user_id, code):
        """Verifica un codice di backup per l'autenticazione 2FA"""
        try:
            if hasattr(current_app, 'db_pool') and current_app.db_pool:
                async with current_app.db_pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "SELECT backup_codes FROM user_2fa WHERE user_id = $1 AND enabled = TRUE", 
                        user_id
                    )
                    
                    if not row:
                        logger.warning(f"Tentativo di utilizzo codice di backup per utente {user_id} senza 2FA abilitato")
                        return False
                    
                    backup_codes = row['backup_codes']
                    
                    if code in backup_codes:
                        # Rimuovi il codice utilizzato dall'elenco
                        backup_codes.remove(code)
                        
                        # Aggiorna i codici di backup
                        await conn.execute(
                            "UPDATE user_2fa SET backup_codes = $1, updated_at = $2 WHERE user_id = $3",
                            backup_codes,
                            datetime.now(),
                            user_id
                        )
                        
                        # Registra l'utilizzo del codice di backup
                        await conn.execute(
                            """
                            INSERT INTO security_log 
                            (user_id, action, ip_address, details, created_at)
                            VALUES ($1, $2, $3, $4, $5)
                            """,
                            user_id,
                            "use_backup_code",
                            session.get('ip_address', 'unknown'),
                            "Utilizzato codice di backup per autenticazione",
                            datetime.now()
                        )
                        
                        return True
                    else:
                        logger.warning(f"Tentativo fallito di utilizzo codice di backup per utente {user_id}")
                        return False
            else:
                logger.error("Pool di database non disponibile per verificare il codice di backup")
                return False
        except Exception as e:
            logger.error(f"Errore nella verifica del codice di backup: {e}")
            return False
    
    @staticmethod
    async def verify_2fa_session(user_id):
        """Verifica se l'utente ha già completato l'autenticazione 2FA nella sessione corrente"""
        try:
            # Se l'utente ha già completato l'autenticazione 2FA nella sessione corrente
            if session.get('2fa_verified') and session.get('user_id') == user_id:
                expiry = session.get('2fa_expiry')
                if expiry and datetime.fromisoformat(expiry) > datetime.now():
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Errore nella verifica della sessione 2FA: {e}")
            return False
    
    @staticmethod
    async def mark_2fa_verified(user_id):
        """Marca la sessione corrente come verificata con 2FA"""
        try:
            # Imposta la sessione come verificata con 2FA
            session['2fa_verified'] = True
            session['user_id'] = user_id
            
            # Imposta una scadenza per la verifica 2FA (12 ore)
            expiry = datetime.now() + timedelta(hours=12)
            session['2fa_expiry'] = expiry.isoformat()
            
            return True
        except Exception as e:
            logger.error(f"Errore nel marcare la sessione come verificata con 2FA: {e}")
            return False
    
    @staticmethod
    async def reset_2fa_session():
        """Resetta la verifica 2FA nella sessione corrente"""
        try:
            if '2fa_verified' in session:
                del session['2fa_verified']
            if '2fa_expiry' in session:
                del session['2fa_expiry']
            
            return True
        except Exception as e:
            logger.error(f"Errore nel reset della sessione 2FA: {e}")
            return False 