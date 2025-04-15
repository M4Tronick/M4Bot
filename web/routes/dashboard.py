from flask import Blueprint, jsonify, request, render_template, current_app, session
from functools import wraps
import logging
import json
import os
import uuid
from datetime import datetime

# Inizializza il blueprint
dashboard_blueprint = Blueprint('dashboard', __name__)

# Logger
logger = logging.getLogger(__name__)

# Directory per i file di configurazione
CONFIG_DIR = "data/user_configs"
os.makedirs(CONFIG_DIR, exist_ok=True)

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

# Funzione per ottenere la configurazione della dashboard per un utente
def get_user_dashboard(user_id):
    """Carica la configurazione dashboard dell'utente"""
    try:
        file_path = os.path.join(CONFIG_DIR, f"dashboard_{user_id}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        else:
            # Configurazione di default
            return {
                "layout": "grid",
                "widgets": [
                    {"id": "youtube_stats", "position": 1, "size": "medium", "visible": True},
                    {"id": "whatsapp_stats", "position": 2, "size": "small", "visible": True},
                    {"id": "telegram_stats", "position": 3, "size": "small", "visible": True},
                    {"id": "recent_messages", "position": 4, "size": "large", "visible": True},
                    {"id": "system_health", "position": 5, "size": "medium", "visible": True}
                ],
                "theme": "light",
                "refresh_interval": 60
            }
    except Exception as e:
        logger.error(f"Errore nel caricamento della dashboard dell'utente {user_id}: {e}")
        # Configurazione fallback
        return {
            "layout": "grid", 
            "widgets": [{"id": "system_health", "position": 1, "size": "large", "visible": True}],
            "theme": "light",
            "refresh_interval": 60
        }

# Funzione per salvare la configurazione dashboard
def save_user_dashboard(user_id, config):
    """Salva la configurazione dashboard dell'utente"""
    try:
        file_path = os.path.join(CONFIG_DIR, f"dashboard_{user_id}.json")
        with open(file_path, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Errore nel salvataggio della dashboard dell'utente {user_id}: {e}")
        return False

@dashboard_blueprint.route('/custom_dashboard')
@login_required
async def custom_dashboard():
    """Pagina dashboard personalizzabile"""
    try:
        user_id = session.get('user_id')
        
        # Carica configurazione dashboard
        dashboard_config = get_user_dashboard(user_id)
        
        # Carica i dati per ogni widget
        widget_data = {}
        
        # Esempio: ottieni dati per widget delle statistiche YouTube
        if any(w['id'] == 'youtube_stats' and w['visible'] for w in dashboard_config['widgets']):
            # Usa Redis cache se disponibile
            if hasattr(current_app, 'redis_client') and current_app.redis_client:
                youtube_stats = await current_app.redis_cache(
                    f"youtube_stats_{user_id}",
                    lambda: current_app.api_request('http://localhost:5000/api/youtube/stats'),
                    expire=300
                )
            else:
                youtube_stats = await current_app.api_request('http://localhost:5000/api/youtube/stats')
            
            widget_data['youtube_stats'] = youtube_stats or {}
        
        # Aggiungere qui altri widget...
        
        return await render_template('custom_dashboard.html', 
                                    dashboard_config=dashboard_config,
                                    widget_data=widget_data)
    except Exception as e:
        logger.error(f"Errore nel caricamento della dashboard personalizzata: {e}")
        return await render_template('error.html', message=f"Errore nel caricamento della dashboard: {str(e)}"), 500

@dashboard_blueprint.route('/api/dashboard/config', methods=['GET', 'PUT'])
@login_required
async def dashboard_config():
    """API per ottenere o aggiornare la configurazione dashboard"""
    try:
        user_id = session.get('user_id')
        
        if request.method == 'GET':
            # Ottieni configurazione
            dashboard_config = get_user_dashboard(user_id)
            return jsonify({'success': True, 'config': dashboard_config})
        else:  # PUT
            # Aggiorna configurazione
            data = await request.json
            
            # Verifica campi obbligatori
            if 'layout' not in data or 'widgets' not in data:
                return jsonify({'success': False, 'message': 'Configurazione incompleta'}), 400
            
            # Salva la configurazione
            if save_user_dashboard(user_id, data):
                # Pubblica un evento per aggiornare eventuali altre schede aperte
                if hasattr(current_app, 'redis_client') and current_app.redis_client:
                    await current_app.redis_client.publish('m4bot_notifications', json.dumps({
                        'type': 'dashboard_updated',
                        'user_id': user_id,
                        'timestamp': datetime.now().isoformat()
                    }))
                
                return jsonify({'success': True, 'message': 'Configurazione aggiornata'})
            else:
                return jsonify({'success': False, 'message': 'Errore nel salvataggio della configurazione'}), 500
    except Exception as e:
        logger.error(f"Errore API dashboard config: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@dashboard_blueprint.route('/api/dashboard/widgets')
@login_required
async def available_widgets():
    """Ottieni la lista dei widget disponibili"""
    try:
        # Lista di widget disponibili
        widgets = [
            {
                "id": "youtube_stats",
                "name": "Statistiche YouTube",
                "description": "Visualizza statistiche del canale YouTube",
                "sizes": ["small", "medium", "large"],
                "refresh_interval": 60
            },
            {
                "id": "whatsapp_stats",
                "name": "Statistiche WhatsApp",
                "description": "Visualizza statistiche delle interazioni WhatsApp",
                "sizes": ["small", "medium"],
                "refresh_interval": 300
            },
            {
                "id": "telegram_stats",
                "name": "Statistiche Telegram",
                "description": "Visualizza statistiche delle interazioni Telegram",
                "sizes": ["small", "medium"],
                "refresh_interval": 300
            },
            {
                "id": "recent_messages",
                "name": "Messaggi recenti",
                "description": "Mostra i messaggi recenti da tutte le piattaforme",
                "sizes": ["medium", "large"],
                "refresh_interval": 30
            },
            {
                "id": "system_health",
                "name": "Stato del sistema",
                "description": "Visualizza lo stato del sistema e le risorse",
                "sizes": ["small", "medium", "large"],
                "refresh_interval": 60
            },
            {
                "id": "template_stats",
                "name": "Statistiche template",
                "description": "Visualizza le statistiche di utilizzo dei template",
                "sizes": ["medium", "large"],
                "refresh_interval": 300
            }
        ]
        
        return jsonify({'success': True, 'widgets': widgets})
    except Exception as e:
        logger.error(f"Errore nell'ottenimento dei widget disponibili: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500 