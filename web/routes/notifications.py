from flask import Blueprint, jsonify, request, render_template, current_app, session
from functools import wraps
import logging
import json
import os
import uuid
from datetime import datetime

# Inizializza il blueprint
notifications_blueprint = Blueprint('notifications', __name__)

# Logger
logger = logging.getLogger(__name__)

# Directory per i file di configurazione
NOTIFICATIONS_DIR = "data/notifications"
os.makedirs(NOTIFICATIONS_DIR, exist_ok=True)

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

# Funzione per ottenere le notifiche di un utente
def get_user_notifications(user_id, limit=50):
    """Carica le notifiche dell'utente"""
    try:
        file_path = os.path.join(NOTIFICATIONS_DIR, f"notifications_{user_id}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                notifications = json.load(f)
                # Ritorna le ultime 'limit' notifiche
                return sorted(notifications, key=lambda x: x['timestamp'], reverse=True)[:limit]
        else:
            return []
    except Exception as e:
        logger.error(f"Errore nel caricamento delle notifiche dell'utente {user_id}: {e}")
        return []

# Funzione per salvare le notifiche di un utente
def save_user_notifications(user_id, notifications):
    """Salva le notifiche dell'utente"""
    try:
        file_path = os.path.join(NOTIFICATIONS_DIR, f"notifications_{user_id}.json")
        with open(file_path, 'w') as f:
            json.dump(notifications, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Errore nel salvataggio delle notifiche dell'utente {user_id}: {e}")
        return False

# Funzione per aggiungere una notifica per un utente
def add_notification(user_id, notification_type, title, message, icon=None, url=None):
    """Aggiunge una notifica per l'utente"""
    try:
        # Ottieni le notifiche esistenti
        notifications = get_user_notifications(user_id, limit=1000)  # Ottieni più notifiche per evitare di perderne
        
        # Crea la nuova notifica
        new_notification = {
            'id': str(uuid.uuid4()),
            'type': notification_type,
            'title': title,
            'message': message,
            'icon': icon,
            'url': url,
            'read': False,
            'timestamp': datetime.now().isoformat()
        }
        
        # Aggiungi la notifica all'inizio della lista
        notifications.insert(0, new_notification)
        
        # Limita a 1000 notifiche per utente
        if len(notifications) > 1000:
            notifications = notifications[:1000]
        
        # Salva le notifiche
        save_user_notifications(user_id, notifications)
        
        # Pubblica l'evento in Redis se disponibile
        if hasattr(current_app, 'redis_client') and current_app.redis_client:
            current_app.redis_client.publish('m4bot_notifications', json.dumps({
                'type': 'new_notification',
                'user_id': user_id,
                'notification': new_notification
            }))
        
        return new_notification
    except Exception as e:
        logger.error(f"Errore nell'aggiunta di una notifica per l'utente {user_id}: {e}")
        return None

@notifications_blueprint.route('/notifications')
@login_required
async def notifications_page():
    """Pagina di gestione delle notifiche"""
    try:
        user_id = session.get('user_id')
        
        # Carica le notifiche dell'utente
        notifications = get_user_notifications(user_id)
        
        return await render_template('notifications.html', 
                                    notifications=notifications)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina delle notifiche: {e}")
        return await render_template('error.html', message=f"Errore nel caricamento delle notifiche: {str(e)}"), 500

@notifications_blueprint.route('/api/notifications', methods=['GET'])
@login_required
async def get_notifications_api():
    """API per ottenere le notifiche dell'utente"""
    try:
        user_id = session.get('user_id')
        
        # Ottieni parametri di query
        limit = request.args.get('limit', 50, type=int)
        unread_only = request.args.get('unread_only', 'false').lower() == 'true'
        
        # Carica le notifiche
        notifications = get_user_notifications(user_id, limit=limit)
        
        # Filtra solo non lette se richiesto
        if unread_only:
            notifications = [n for n in notifications if not n.get('read', False)]
        
        return jsonify({
            'success': True, 
            'notifications': notifications,
            'unread_count': sum(1 for n in notifications if not n.get('read', False))
        })
    except Exception as e:
        logger.error(f"Errore API notifiche: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@notifications_blueprint.route('/api/notifications/<notification_id>/read', methods=['POST'])
@login_required
async def mark_notification_read(notification_id):
    """API per segnare una notifica come letta"""
    try:
        user_id = session.get('user_id')
        
        # Carica le notifiche
        notifications = get_user_notifications(user_id, limit=1000)
        
        # Trova la notifica
        notification_index = next((i for i, n in enumerate(notifications) if n['id'] == notification_id), None)
        
        if notification_index is None:
            return jsonify({'success': False, 'message': 'Notifica non trovata'}), 404
        
        # Segna come letta
        notifications[notification_index]['read'] = True
        
        # Salva le notifiche
        if save_user_notifications(user_id, notifications):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Errore nel salvataggio delle notifiche'}), 500
    except Exception as e:
        logger.error(f"Errore nel segnare la notifica come letta: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@notifications_blueprint.route('/api/notifications/read_all', methods=['POST'])
@login_required
async def mark_all_notifications_read():
    """API per segnare tutte le notifiche come lette"""
    try:
        user_id = session.get('user_id')
        
        # Carica le notifiche
        notifications = get_user_notifications(user_id, limit=1000)
        
        # Segna tutte come lette
        for notification in notifications:
            notification['read'] = True
        
        # Salva le notifiche
        if save_user_notifications(user_id, notifications):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Errore nel salvataggio delle notifiche'}), 500
    except Exception as e:
        logger.error(f"Errore nel segnare tutte le notifiche come lette: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@notifications_blueprint.route('/api/notifications/settings', methods=['GET', 'PUT'])
@login_required
async def notification_settings():
    """API per ottenere o aggiornare le impostazioni delle notifiche"""
    try:
        user_id = session.get('user_id')
        file_path = os.path.join(NOTIFICATIONS_DIR, f"settings_{user_id}.json")
        
        if request.method == 'GET':
            # Ottieni le impostazioni
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    settings = json.load(f)
            else:
                # Impostazioni di default
                settings = {
                    'browser_notifications': True,
                    'sound_enabled': True,
                    'email_notifications': False,
                    'notification_types': {
                        'system': True,
                        'message': True,
                        'workflow': True,
                        'scheduled': True,
                        'template': True
                    }
                }
            
            return jsonify({'success': True, 'settings': settings})
        
        else:  # PUT
            # Aggiorna le impostazioni
            data = await request.json
            
            # Salva le impostazioni
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            return jsonify({'success': True, 'message': 'Impostazioni aggiornate'})
    except Exception as e:
        logger.error(f"Errore API impostazioni notifiche: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@notifications_blueprint.route('/api/notifications/<notification_id>', methods=['DELETE'])
@login_required
async def delete_notification(notification_id):
    """API per eliminare una notifica"""
    try:
        user_id = session.get('user_id')
        
        # Carica le notifiche
        notifications = get_user_notifications(user_id, limit=1000)
        
        # Filtra le notifiche, rimuovendo quella con l'ID specificato
        notifications = [n for n in notifications if n['id'] != notification_id]
        
        # Salva le notifiche
        if save_user_notifications(user_id, notifications):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Errore nel salvataggio delle notifiche'}), 500
    except Exception as e:
        logger.error(f"Errore nell'eliminazione della notifica: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500 