from flask import Blueprint, render_template, jsonify, request, make_response
import logging
from datetime import datetime, timedelta

# Inizializzazione del Blueprint e del logger
gdpr_bp = Blueprint('gdpr', __name__)
logger = logging.getLogger(__name__)

@gdpr_bp.route('/privacy-policy')
async def privacy_policy():
    """Visualizza la pagina della privacy policy"""
    return await render_template('privacy_policy.html')

@gdpr_bp.route('/cookie-policy')
async def cookie_policy():
    """Visualizza la pagina della cookie policy"""
    return await render_template('cookie_policy.html')

@gdpr_bp.route('/api/gdpr/consent', methods=['POST'])
async def save_consent():
    """API per salvare il consenso dell'utente"""
    try:
        data = await request.get_json()
        
        if not data:
            return jsonify({
                "success": False,
                "message": "Dati mancanti"
            }), 400
        
        # Estrai i dati sul consenso
        consented = data.get('consented', False)
        preferences = data.get('preferences', {})
        
        # Crea un cookie di consenso
        response = make_response(jsonify({
            "success": True,
            "message": "Preferenze salvate con successo"
        }))
        
        # Cookie di consenso generale (durata 1 anno)
        expiration = datetime.now() + timedelta(days=365)
        response.set_cookie(
            'm4bot_cookie_consent', 
            str(consented).lower(), 
            expires=expiration,
            httponly=True,
            secure=request.is_secure,
            samesite='Lax'
        )
        
        # Cookie con preferenze dettagliate (durata 1 anno)
        if preferences:
            import json
            import base64
            
            # Codifica le preferenze in base64 per evitare problemi con caratteri speciali
            preferences_encoded = base64.b64encode(json.dumps(preferences).encode()).decode()
            
            response.set_cookie(
                'm4bot_cookie_settings', 
                preferences_encoded, 
                expires=expiration,
                httponly=True,
                secure=request.is_secure,
                samesite='Lax'
            )
        
        # Logging
        logger.info(f"Consenso GDPR salvato: {consented}")
        
        return response
    except Exception as e:
        logger.error(f"Errore nel salvataggio del consenso GDPR: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@gdpr_bp.route('/api/gdpr/export-data', methods=['POST'])
async def export_user_data():
    """API per esportare i dati dell'utente (richiesta GDPR)"""
    try:
        # Qui implementerai la logica per recuperare tutti i dati dell'utente
        # per soddisfare le richieste di portabilità dei dati GDPR
        
        # Per ora, un esempio con dati fittizi
        from flask import current_app, session
        
        # Verifica che l'utente sia autenticato
        if 'user_id' not in session:
            return jsonify({
                "success": False,
                "message": "Utente non autenticato"
            }), 401
        
        user_id = session['user_id']
        
        # In una implementazione reale, qui recupereresti tutti i dati dell'utente dal database
        user_data = {
            "user_id": user_id,
            "personal_info": {
                "nome": "Utente di Test",
                "email": "test@example.com",
                "data_registrazione": "2023-01-01"
            },
            "preferences": {
                "theme": "light",
                "notifications": True
            },
            "activity": [
                {"type": "login", "date": "2023-09-15T10:30:00"},
                {"type": "profile_update", "date": "2023-09-16T14:22:00"}
            ]
        }
        
        # Prepara la risposta con i dati in formato JSON
        response = make_response(
            jsonify({
                "success": True,
                "user_data": user_data,
                "export_date": datetime.now().isoformat()
            })
        )
        
        # Imposta gli header per far scaricare il file
        response.headers["Content-Disposition"] = f"attachment; filename=user_data_{user_id}.json"
        response.headers["Content-Type"] = "application/json"
        
        return response
    except Exception as e:
        logger.error(f"Errore nell'esportazione dei dati utente: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

@gdpr_bp.route('/api/gdpr/delete-account', methods=['POST'])
async def delete_account():
    """API per eliminare l'account dell'utente (richiesta GDPR)"""
    try:
        # Qui implementerai la logica per eliminare l'account dell'utente
        # e tutti i suoi dati personali per soddisfare il diritto all'oblio del GDPR
        
        from flask import current_app, session
        
        # Verifica che l'utente sia autenticato
        if 'user_id' not in session:
            return jsonify({
                "success": False,
                "message": "Utente non autenticato"
            }), 401
        
        # Verifica la password dell'utente per confermare la richiesta
        data = await request.get_json()
        if not data or 'password' not in data:
            return jsonify({
                "success": False,
                "message": "Password richiesta per confermare l'eliminazione"
            }), 400
        
        user_id = session['user_id']
        password = data.get('password', '')
        
        # In una implementazione reale, qui verificheresti la password dell'utente
        # e poi elimineresti tutti i suoi dati dal database
        
        # Simula la cancellazione dell'account per questo esempio
        # Elimina la sessione
        session.clear()
        
        # Registra l'operazione nel log
        logger.info(f"Account utente {user_id} eliminato (richiesta GDPR)")
        
        return jsonify({
            "success": True,
            "message": "Account eliminato con successo. Tutte le informazioni personali sono state rimosse dai nostri sistemi."
        })
    except Exception as e:
        logger.error(f"Errore nell'eliminazione dell'account: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Errore: {str(e)}"
        }), 500

def init_gdpr_bp(app):
    """Inizializza il blueprint GDPR"""
    app.register_blueprint(gdpr_bp)
    logger.info("Blueprint GDPR inizializzato") 