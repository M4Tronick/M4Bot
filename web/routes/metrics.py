from flask import Blueprint, jsonify, request, render_template, current_app
import logging
import asyncio

# Inizializza il blueprint
metrics_blueprint = Blueprint('metrics', __name__)

# Logger
logger = logging.getLogger(__name__)

@metrics_blueprint.route('/api/metrics/live', methods=['GET'])
def live_metrics():
    """Endpoint per ottenere le metriche live di YouTube e Kick"""
    try:
        # Ottieni le metriche attuali
        youtube_metrics = current_app.youtube_metrics.current_metrics if hasattr(current_app, 'youtube_metrics') else {}
        kick_metrics = current_app.kick_metrics.current_metrics if hasattr(current_app, 'kick_metrics') else {}
        
        # Prepara la risposta
        response = {
            'success': True,
            'youtube': youtube_metrics,
            'kick': kick_metrics
        }
        
        return jsonify(response)
    except Exception as e:
        logger.error(f"Errore nell'ottenimento delle metriche live: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@metrics_blueprint.route('/obs/counter', methods=['GET'])
def obs_counter():
    """Pagina per il counter di like e visualizzatori da incorporare in OBS"""
    try:
        # Ottieni i parametri dalla query string
        refresh_interval = request.args.get('refresh', 5000, type=int)
        compact_mode = request.args.get('compact', 'false').lower() == 'true'
        show_youtube_likes = request.args.get('youtube_likes', 'true').lower() == 'true'
        show_youtube_viewers = request.args.get('youtube_viewers', 'true').lower() == 'true'
        show_kick_viewers = request.args.get('kick_viewers', 'true').lower() == 'true'
        animate_changes = request.args.get('animate', 'true').lower() == 'true'
        format_numbers = request.args.get('format', 'true').lower() == 'true'
        
        # Renderizza il template con le opzioni
        return render_template('obs_overlay.html',
                              refresh_interval=refresh_interval,
                              compact_mode=compact_mode,
                              show_youtube_likes=show_youtube_likes,
                              show_youtube_viewers=show_youtube_viewers,
                              show_kick_viewers=show_kick_viewers,
                              animate_changes=animate_changes,
                              format_numbers=format_numbers)
    except Exception as e:
        logger.error(f"Errore nella visualizzazione del counter OBS: {e}")
        return f"Si è verificato un errore: {str(e)}", 500

@metrics_blueprint.route('/api/metrics/force-update', methods=['POST'])
def force_update():
    """Forza l'aggiornamento delle metriche"""
    try:
        # Verifica l'autenticazione
        # TODO: Aggiungere controllo autenticazione
        
        # Avvia l'aggiornamento forzato
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        updated_youtube = False
        updated_kick = False
        
        if hasattr(current_app, 'youtube_metrics'):
            updated_youtube = loop.run_until_complete(current_app.youtube_metrics.force_update())
            
        if hasattr(current_app, 'kick_metrics'):
            updated_kick = loop.run_until_complete(current_app.kick_metrics.force_update())
        
        loop.close()
        
        return jsonify({
            'success': True,
            'updated': {
                'youtube': updated_youtube,
                'kick': updated_kick
            }
        })
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento forzato delle metriche: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@metrics_blueprint.route('/api/metrics/config', methods=['GET', 'POST'])
def metrics_config():
    """Ottiene o aggiorna la configurazione delle metriche"""
    try:
        if request.method == 'GET':
            # Ottieni la configurazione attuale
            youtube_config = {
                'youtube_api_key': current_app.config.get('YOUTUBE_API_KEY', ''),
                'youtube_channel_id': current_app.config.get('YOUTUBE_CHANNEL_ID', ''),
                'youtube_metrics_update_interval': current_app.config.get('YOUTUBE_METRICS_UPDATE_INTERVAL', 60)
            }
            
            kick_config = {
                'kick_channel_name': current_app.config.get('KICK_CHANNEL_NAME', ''),
                'kick_metrics_update_interval': current_app.config.get('KICK_METRICS_UPDATE_INTERVAL', 60)
            }
            
            return jsonify({
                'success': True,
                'config': {
                    'youtube': youtube_config,
                    'kick': kick_config
                }
            })
        else:  # POST
            # Aggiorna la configurazione
            data = request.json
            
            # Verifica l'autenticazione
            # TODO: Aggiungere controllo autenticazione
            
            # Aggiorna la configurazione di YouTube
            if 'youtube' in data:
                youtube_config = data['youtube']
                current_app.config['YOUTUBE_API_KEY'] = youtube_config.get('youtube_api_key', current_app.config.get('YOUTUBE_API_KEY', ''))
                current_app.config['YOUTUBE_CHANNEL_ID'] = youtube_config.get('youtube_channel_id', current_app.config.get('YOUTUBE_CHANNEL_ID', ''))
                current_app.config['YOUTUBE_METRICS_UPDATE_INTERVAL'] = youtube_config.get('youtube_metrics_update_interval', current_app.config.get('YOUTUBE_METRICS_UPDATE_INTERVAL', 60))
            
            # Aggiorna la configurazione di Kick
            if 'kick' in data:
                kick_config = data['kick']
                current_app.config['KICK_CHANNEL_NAME'] = kick_config.get('kick_channel_name', current_app.config.get('KICK_CHANNEL_NAME', ''))
                current_app.config['KICK_METRICS_UPDATE_INTERVAL'] = kick_config.get('kick_metrics_update_interval', current_app.config.get('KICK_METRICS_UPDATE_INTERVAL', 60))
            
            # Salva la configurazione
            # TODO: Aggiungere salvataggio configurazione
            
            return jsonify({
                'success': True,
                'message': 'Configurazione aggiornata con successo'
            })
    except Exception as e:
        logger.error(f"Errore nella gestione della configurazione delle metriche: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 