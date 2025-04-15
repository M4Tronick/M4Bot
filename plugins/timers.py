"""
Plugin per la gestione di timer e countdown per streaming
"""

import os
import json
import logging
import uuid
import asyncio
import time
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, render_template, current_app

# Logger
logger = logging.getLogger(__name__)

# Path per i file dei timer
TIMERS_DIR = "data/timers"
TIMERS_FILE = os.path.join(TIMERS_DIR, "timers.json")

# Blueprint
timers_blueprint = Blueprint('timers', __name__)

class TimerManager:
    """Gestore dei timer e countdown"""
    
    def __init__(self, app):
        """
        Inizializza il gestore dei timer
        
        Args:
            app: L'applicazione Flask/Quart
        """
        self.app = app
        self.timers = {}
        self.active_timers = {}
        self.update_task = None
        
        # Crea le directory necessarie
        os.makedirs(TIMERS_DIR, exist_ok=True)
        
        # Carica i timer salvati
        self._load_timers()
        
        # Avvia il task di aggiornamento dei timer
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.update_task = asyncio.create_task(self._update_loop())
        
        logger.info("Gestore dei timer inizializzato")
    
    def _load_timers(self):
        """Carica i timer dal file"""
        if os.path.exists(TIMERS_FILE):
            try:
                with open(TIMERS_FILE, 'r') as f:
                    self.timers = json.load(f)
                logger.info(f"Caricati {len(self.timers)} timer dal file")
                
                # Ripristina i timer attivi
                now = datetime.now().timestamp()
                for timer_id, timer in self.timers.items():
                    if timer['status'] == 'active' and (timer.get('end_time', 0) > now or timer.get('timer_type') == 'stopwatch'):
                        self.active_timers[timer_id] = timer
            except Exception as e:
                logger.error(f"Errore nel caricamento dei timer: {e}")
                self.timers = {}
        else:
            self.timers = {}
    
    def _save_timers(self):
        """Salva i timer nel file"""
        try:
            with open(TIMERS_FILE, 'w') as f:
                json.dump(self.timers, f, indent=2)
            logger.debug("Timer salvati nel file")
        except Exception as e:
            logger.error(f"Errore nel salvataggio dei timer: {e}")
    
    async def _update_loop(self):
        """Loop di aggiornamento dei timer attivi"""
        try:
            while True:
                to_complete = []
                now = datetime.now().timestamp()
                
                # Verifica quali timer sono terminati
                for timer_id, timer in self.active_timers.items():
                    if timer.get('timer_type') == 'countdown' and timer.get('end_time', 0) <= now:
                        to_complete.append(timer_id)
                    
                    # Aggiorna il tempo trascorso per i cronometri
                    if timer.get('timer_type') == 'stopwatch' and timer.get('status') == 'active':
                        elapsed = now - timer.get('start_time', now)
                        timer['elapsed_time'] = elapsed
                        self.timers[timer_id] = timer
                
                # Completa i timer terminati
                for timer_id in to_complete:
                    await self.complete_timer(timer_id)
                
                # Salva lo stato dei timer
                self._save_timers()
                
                # Attendi 0.5 secondi prima del prossimo controllo
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info("Task di aggiornamento dei timer interrotto")
        except Exception as e:
            logger.error(f"Errore nel loop di aggiornamento dei timer: {e}")
    
    async def create_timer(self, data):
        """
        Crea un nuovo timer
        
        Args:
            data: Dati del timer
            
        Returns:
            dict: Il timer creato
        """
        try:
            # Genera un ID univoco per il timer
            timer_id = str(uuid.uuid4())
            
            # Verifica il tipo di timer
            timer_type = data.get('timer_type', 'countdown')
            if timer_type not in ['countdown', 'stopwatch']:
                return {'success': False, 'error': 'Tipo di timer non valido'}
            
            # Verifica i dati richiesti per il countdown
            if timer_type == 'countdown':
                duration = data.get('duration', 0)
                if duration <= 0:
                    return {'success': False, 'error': 'La durata deve essere maggiore di zero'}
            
            # Crea il timer
            timer = {
                'id': timer_id,
                'name': data.get('name', 'Timer'),
                'timer_type': timer_type,
                'created_at': datetime.now().timestamp(),
                'status': 'created',
                'creator_id': data.get('creator_id', 'system'),
                'display_format': data.get('display_format', 'hh:mm:ss'),
                'obs_settings': data.get('obs_settings', {
                    'font_size': 48,
                    'font_color': '#FFFFFF',
                    'background_color': '#000000',
                    'transparent_background': True,
                    'show_labels': True,
                    'animation': 'fade'
                }),
                'actions': data.get('actions', {
                    'on_start': [],
                    'on_complete': []
                })
            }
            
            # Aggiungi campi specifici per il tipo di timer
            if timer_type == 'countdown':
                timer.update({
                    'duration': duration,
                    'end_message': data.get('end_message', 'Tempo scaduto!'),
                    'auto_restart': data.get('auto_restart', False),
                    'restart_delay': data.get('restart_delay', 0)
                })
            elif timer_type == 'stopwatch':
                timer.update({
                    'elapsed_time': 0,
                    'lap_times': []
                })
            
            # Registra il timer
            self.timers[timer_id] = timer
            
            # Salva i timer
            self._save_timers()
            
            return {'success': True, 'timer': timer}
        except Exception as e:
            logger.error(f"Errore nella creazione del timer: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_timer(self, timer_id):
        """
        Ottiene un timer
        
        Args:
            timer_id: ID del timer
            
        Returns:
            dict: Il timer, o None se non trovato
        """
        return self.timers.get(timer_id)
    
    async def start_timer(self, timer_id):
        """
        Avvia un timer
        
        Args:
            timer_id: ID del timer
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che il timer esista
            timer = self.timers.get(timer_id)
            if not timer:
                return {'success': False, 'error': 'Timer non trovato'}
            
            # Aggiorna lo stato del timer
            timer['status'] = 'active'
            now = datetime.now().timestamp()
            
            if timer.get('timer_type') == 'countdown':
                timer['start_time'] = now
                timer['end_time'] = now + timer.get('duration', 0)
            elif timer.get('timer_type') == 'stopwatch':
                timer['start_time'] = now
                timer['elapsed_time'] = 0
                timer['lap_times'] = []
            
            # Registra il timer come attivo
            self.active_timers[timer_id] = timer
            
            # Salva i timer
            self._save_timers()
            
            # Esegui le azioni di avvio
            await self._execute_actions(timer, 'on_start')
            
            return {'success': True, 'timer': timer}
        except Exception as e:
            logger.error(f"Errore nell'avvio del timer: {e}")
            return {'success': False, 'error': str(e)}
    
    async def pause_timer(self, timer_id):
        """
        Mette in pausa un timer
        
        Args:
            timer_id: ID del timer
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che il timer esista
            timer = self.timers.get(timer_id)
            if not timer:
                return {'success': False, 'error': 'Timer non trovato'}
            
            # Verifica che il timer sia attivo
            if timer['status'] != 'active':
                return {'success': False, 'error': 'Il timer non è attivo'}
            
            # Salva lo stato attuale
            now = datetime.now().timestamp()
            
            if timer.get('timer_type') == 'countdown':
                # Salva il tempo rimanente
                remaining = timer.get('end_time', now) - now
                timer['remaining_time'] = remaining if remaining > 0 else 0
            elif timer.get('timer_type') == 'stopwatch':
                # Salva il tempo trascorso
                timer['elapsed_time'] = now - timer.get('start_time', now)
            
            # Aggiorna lo stato del timer
            timer['status'] = 'paused'
            timer['paused_at'] = now
            
            # Rimuovi il timer dai timer attivi
            if timer_id in self.active_timers:
                del self.active_timers[timer_id]
            
            # Salva i timer
            self._save_timers()
            
            return {'success': True, 'timer': timer}
        except Exception as e:
            logger.error(f"Errore nella pausa del timer: {e}")
            return {'success': False, 'error': str(e)}
    
    async def resume_timer(self, timer_id):
        """
        Riprende un timer in pausa
        
        Args:
            timer_id: ID del timer
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che il timer esista
            timer = self.timers.get(timer_id)
            if not timer:
                return {'success': False, 'error': 'Timer non trovato'}
            
            # Verifica che il timer sia in pausa
            if timer['status'] != 'paused':
                return {'success': False, 'error': 'Il timer non è in pausa'}
            
            # Aggiorna lo stato del timer
            timer['status'] = 'active'
            now = datetime.now().timestamp()
            
            if timer.get('timer_type') == 'countdown':
                # Calcola il nuovo tempo di fine
                timer['end_time'] = now + timer.get('remaining_time', 0)
            elif timer.get('timer_type') == 'stopwatch':
                # Aggiusta il tempo di inizio per mantenere il tempo trascorso corretto
                timer['start_time'] = now - timer.get('elapsed_time', 0)
            
            # Registra il timer come attivo
            self.active_timers[timer_id] = timer
            
            # Salva i timer
            self._save_timers()
            
            return {'success': True, 'timer': timer}
        except Exception as e:
            logger.error(f"Errore nella ripresa del timer: {e}")
            return {'success': False, 'error': str(e)}
    
    async def reset_timer(self, timer_id):
        """
        Resetta un timer
        
        Args:
            timer_id: ID del timer
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che il timer esista
            timer = self.timers.get(timer_id)
            if not timer:
                return {'success': False, 'error': 'Timer non trovato'}
            
            # Aggiorna lo stato del timer
            timer['status'] = 'created'
            
            if timer.get('timer_type') == 'countdown':
                timer.pop('start_time', None)
                timer.pop('end_time', None)
                timer.pop('remaining_time', None)
            elif timer.get('timer_type') == 'stopwatch':
                timer.pop('start_time', None)
                timer['elapsed_time'] = 0
                timer['lap_times'] = []
            
            # Rimuovi il timer dai timer attivi
            if timer_id in self.active_timers:
                del self.active_timers[timer_id]
            
            # Salva i timer
            self._save_timers()
            
            return {'success': True, 'timer': timer}
        except Exception as e:
            logger.error(f"Errore nel reset del timer: {e}")
            return {'success': False, 'error': str(e)}
    
    async def complete_timer(self, timer_id):
        """
        Completa un timer (chiamato internamente quando un countdown raggiunge zero)
        
        Args:
            timer_id: ID del timer
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che il timer esista
            timer = self.timers.get(timer_id)
            if not timer:
                return {'success': False, 'error': 'Timer non trovato'}
            
            # Aggiorna lo stato del timer
            timer['status'] = 'completed'
            timer['completed_at'] = datetime.now().timestamp()
            
            # Rimuovi il timer dai timer attivi
            if timer_id in self.active_timers:
                del self.active_timers[timer_id]
            
            # Salva i timer
            self._save_timers()
            
            # Esegui le azioni di completamento
            await self._execute_actions(timer, 'on_complete')
            
            # Controlla se deve riavviarsi automaticamente
            if timer.get('timer_type') == 'countdown' and timer.get('auto_restart', False):
                # Programma il riavvio
                restart_delay = timer.get('restart_delay', 0)
                asyncio.create_task(self._delayed_restart(timer_id, restart_delay))
            
            return {'success': True, 'timer': timer}
        except Exception as e:
            logger.error(f"Errore nel completamento del timer: {e}")
            return {'success': False, 'error': str(e)}
    
    async def add_lap(self, timer_id):
        """
        Aggiunge un giro al cronometro
        
        Args:
            timer_id: ID del timer
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che il timer esista
            timer = self.timers.get(timer_id)
            if not timer:
                return {'success': False, 'error': 'Timer non trovato'}
            
            # Verifica che il timer sia un cronometro
            if timer.get('timer_type') != 'stopwatch':
                return {'success': False, 'error': 'Il timer non è un cronometro'}
            
            # Verifica che il timer sia attivo
            if timer['status'] != 'active':
                return {'success': False, 'error': 'Il cronometro non è attivo'}
            
            # Aggiungi il giro
            now = datetime.now().timestamp()
            elapsed = now - timer.get('start_time', now)
            
            lap = {
                'number': len(timer.get('lap_times', [])) + 1,
                'time': elapsed,
                'timestamp': now
            }
            
            if 'lap_times' not in timer:
                timer['lap_times'] = []
            
            timer['lap_times'].append(lap)
            
            # Salva i timer
            self._save_timers()
            
            return {'success': True, 'timer': timer, 'lap': lap}
        except Exception as e:
            logger.error(f"Errore nell'aggiunta del giro: {e}")
            return {'success': False, 'error': str(e)}
    
    async def delete_timer(self, timer_id):
        """
        Elimina un timer
        
        Args:
            timer_id: ID del timer
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che il timer esista
            if timer_id not in self.timers:
                return {'success': False, 'error': 'Timer non trovato'}
            
            # Rimuovi il timer
            del self.timers[timer_id]
            
            # Rimuovi il timer dai timer attivi
            if timer_id in self.active_timers:
                del self.active_timers[timer_id]
            
            # Salva i timer
            self._save_timers()
            
            return {'success': True}
        except Exception as e:
            logger.error(f"Errore nell'eliminazione del timer: {e}")
            return {'success': False, 'error': str(e)}
    
    async def update_timer(self, timer_id, data):
        """
        Aggiorna un timer
        
        Args:
            timer_id: ID del timer
            data: Nuovi dati del timer
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che il timer esista
            timer = self.timers.get(timer_id)
            if not timer:
                return {'success': False, 'error': 'Timer non trovato'}
            
            # Aggiorna i campi consentiti
            allowed_fields = ['name', 'display_format', 'obs_settings', 'actions']
            
            for field in allowed_fields:
                if field in data:
                    timer[field] = data[field]
            
            # Aggiorna i campi specifici per il tipo di timer
            if timer.get('timer_type') == 'countdown':
                if 'end_message' in data:
                    timer['end_message'] = data['end_message']
                if 'auto_restart' in data:
                    timer['auto_restart'] = data['auto_restart']
                if 'restart_delay' in data:
                    timer['restart_delay'] = data['restart_delay']
                
                # Aggiorna la durata solo se il timer non è attivo
                if 'duration' in data and timer['status'] == 'created':
                    timer['duration'] = data['duration']
            
            # Salva i timer
            self._save_timers()
            
            return {'success': True, 'timer': timer}
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento del timer: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _delayed_restart(self, timer_id, delay):
        """
        Riavvia un timer dopo un ritardo
        
        Args:
            timer_id: ID del timer
            delay: Ritardo in secondi
        """
        try:
            # Attendi il ritardo
            await asyncio.sleep(delay)
            
            # Resetta e avvia il timer
            await self.reset_timer(timer_id)
            await self.start_timer(timer_id)
        except Exception as e:
            logger.error(f"Errore nel riavvio ritardato del timer: {e}")
    
    async def _execute_actions(self, timer, action_type):
        """
        Esegue le azioni associate a un timer
        
        Args:
            timer: Il timer
            action_type: Tipo di azione ('on_start', 'on_complete')
        """
        try:
            actions = timer.get('actions', {}).get(action_type, [])
            
            for action in actions:
                action_type = action.get('type')
                
                if action_type == 'message':
                    # Invia un messaggio
                    platforms = action.get('platforms', [])
                    message = action.get('message', '')
                    
                    if 'youtube' in platforms and hasattr(self.app, 'youtube_connector'):
                        await self.app.youtube_connector.send_chat_message(message)
                    
                    if 'kick' in platforms and hasattr(self.app, 'kick_connector'):
                        await self.app.kick_connector.send_chat_message(message)
                    
                    if 'telegram' in platforms and hasattr(self.app, 'telegram_connector'):
                        for chat_id in self.app.config.get('TELEGRAM_CHAT_IDS', []):
                            await self.app.telegram_connector.send_message(chat_id, message)
                    
                    if 'whatsapp' in platforms and hasattr(self.app, 'whatsapp_connector'):
                        for recipient in self.app.config.get('WHATSAPP_RECIPIENTS', []):
                            await self.app.whatsapp_connector.send_message(recipient, message)
                
                elif action_type == 'sound':
                    # Riproduci un suono (per OBS)
                    # Questo richiede un'integrazione con OBS
                    sound_file = action.get('sound_file', '')
                    volume = action.get('volume', 100)
                    
                    if hasattr(self.app, 'obs_connector'):
                        await self.app.obs_connector.play_sound(sound_file, volume)
        except Exception as e:
            logger.error(f"Errore nell'esecuzione delle azioni: {e}")

def setup(app):
    """
    Configura il plugin dei timer
    
    Args:
        app: L'applicazione Flask/Quart
    """
    # Inizializza il gestore dei timer
    app.timer_manager = TimerManager(app)
    
    # Registra il blueprint
    app.register_blueprint(timers_blueprint, url_prefix='/timers')
    
    # Definisci le route
    @timers_blueprint.route('/', methods=['GET'])
    async def timers_page():
        """Pagina principale dei timer"""
        timers = app.timer_manager.timers
        return await render_template('timers.html', timers=timers)
    
    @timers_blueprint.route('/obs', methods=['GET'])
    async def obs_overlay():
        """Overlay OBS per timer e countdown"""
        timer_id = request.args.get('timer_id')
        
        # Opzioni di visualizzazione
        theme = request.args.get('theme', 'dark')
        font_size = request.args.get('font_size', '48')
        font_color = request.args.get('font_color', '#FFFFFF')
        background_color = request.args.get('background_color', '#000000')
        transparent = request.args.get('transparent', 'true').lower() == 'true'
        show_labels = request.args.get('show_labels', 'true').lower() == 'true'
        animation = request.args.get('animation', 'fade')
        
        return await render_template(
            'timer_obs_overlay.html',
            timer_id=timer_id,
            theme=theme,
            font_size=font_size,
            font_color=font_color,
            background_color=background_color,
            transparent=transparent,
            show_labels=show_labels,
            animation=animation
        )
    
    @timers_blueprint.route('/api/timers', methods=['GET'])
    async def get_timers():
        """API per ottenere tutti i timer"""
        return jsonify(list(app.timer_manager.timers.values()))
    
    @timers_blueprint.route('/api/timers/active', methods=['GET'])
    async def get_active_timers():
        """API per ottenere i timer attivi"""
        return jsonify(list(app.timer_manager.active_timers.values()))
    
    @timers_blueprint.route('/api/timers/<timer_id>', methods=['GET'])
    async def get_timer(timer_id):
        """API per ottenere un timer specifico"""
        timer = await app.timer_manager.get_timer(timer_id)
        if timer:
            # Aggiorna le informazioni in tempo reale
            if timer.get('status') == 'active':
                now = datetime.now().timestamp()
                
                if timer.get('timer_type') == 'countdown':
                    remaining = timer.get('end_time', now) - now
                    timer['remaining_time'] = max(0, remaining)
                    timer['progress_percent'] = (1 - (remaining / timer.get('duration', 1))) * 100
                    timer['progress_percent'] = min(100, max(0, timer['progress_percent']))
                elif timer.get('timer_type') == 'stopwatch':
                    timer['elapsed_time'] = now - timer.get('start_time', now)
            
            return jsonify(timer)
        else:
            return jsonify({'error': 'Timer non trovato'}), 404
    
    @timers_blueprint.route('/api/timers', methods=['POST'])
    async def create_timer():
        """API per creare un nuovo timer"""
        data = await request.json
        result = await app.timer_manager.create_timer(data)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @timers_blueprint.route('/api/timers/<timer_id>', methods=['PUT'])
    async def update_timer(timer_id):
        """API per aggiornare un timer"""
        data = await request.json
        result = await app.timer_manager.update_timer(timer_id, data)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @timers_blueprint.route('/api/timers/<timer_id>', methods=['DELETE'])
    async def delete_timer(timer_id):
        """API per eliminare un timer"""
        result = await app.timer_manager.delete_timer(timer_id)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @timers_blueprint.route('/api/timers/<timer_id>/start', methods=['POST'])
    async def start_timer(timer_id):
        """API per avviare un timer"""
        result = await app.timer_manager.start_timer(timer_id)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @timers_blueprint.route('/api/timers/<timer_id>/pause', methods=['POST'])
    async def pause_timer(timer_id):
        """API per mettere in pausa un timer"""
        result = await app.timer_manager.pause_timer(timer_id)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @timers_blueprint.route('/api/timers/<timer_id>/resume', methods=['POST'])
    async def resume_timer(timer_id):
        """API per riprendere un timer"""
        result = await app.timer_manager.resume_timer(timer_id)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @timers_blueprint.route('/api/timers/<timer_id>/reset', methods=['POST'])
    async def reset_timer(timer_id):
        """API per resettare un timer"""
        result = await app.timer_manager.reset_timer(timer_id)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @timers_blueprint.route('/api/timers/<timer_id>/lap', methods=['POST'])
    async def add_lap(timer_id):
        """API per aggiungere un giro al cronometro"""
        result = await app.timer_manager.add_lap(timer_id)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    logger.info("Plugin dei timer configurato") 