"""
Plugin per la gestione di sondaggi multipiattaforma
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

# Path per i file dei sondaggi
POLLS_DIR = "data/polls"
POLLS_FILE = os.path.join(POLLS_DIR, "polls.json")

# Blueprint
polls_blueprint = Blueprint('polls', __name__)

class PollManager:
    """Gestore dei sondaggi"""
    
    def __init__(self, app):
        """
        Inizializza il gestore dei sondaggi
        
        Args:
            app: L'applicazione Flask/Quart
        """
        self.app = app
        self.polls = {}
        self.active_polls = {}
        self.update_task = None
        
        # Crea le directory necessarie
        os.makedirs(POLLS_DIR, exist_ok=True)
        
        # Carica i sondaggi salvati
        self._load_polls()
        
        # Avvia il task di aggiornamento dei sondaggi
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.update_task = asyncio.create_task(self._update_loop())
        
        logger.info("Gestore dei sondaggi inizializzato")
    
    def _load_polls(self):
        """Carica i sondaggi dal file"""
        if os.path.exists(POLLS_FILE):
            try:
                with open(POLLS_FILE, 'r') as f:
                    self.polls = json.load(f)
                logger.info(f"Caricati {len(self.polls)} sondaggi dal file")
                
                # Riattiva i sondaggi attivi
                now = datetime.now().timestamp()
                for poll_id, poll in self.polls.items():
                    if poll['status'] == 'active' and poll['end_time'] > now:
                        self.active_polls[poll_id] = poll
            except Exception as e:
                logger.error(f"Errore nel caricamento dei sondaggi: {e}")
                self.polls = {}
        else:
            self.polls = {}
    
    def _save_polls(self):
        """Salva i sondaggi nel file"""
        try:
            with open(POLLS_FILE, 'w') as f:
                json.dump(self.polls, f, indent=2)
            logger.debug("Sondaggi salvati nel file")
        except Exception as e:
            logger.error(f"Errore nel salvataggio dei sondaggi: {e}")
    
    async def _update_loop(self):
        """Loop di aggiornamento dei sondaggi attivi"""
        try:
            while True:
                to_close = []
                now = datetime.now().timestamp()
                
                # Verifica quali sondaggi sono terminati
                for poll_id, poll in self.active_polls.items():
                    if poll['end_time'] <= now:
                        to_close.append(poll_id)
                
                # Chiudi i sondaggi terminati
                for poll_id in to_close:
                    await self.close_poll(poll_id)
                
                # Attendi 5 secondi prima del prossimo controllo
                await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Task di aggiornamento dei sondaggi interrotto")
        except Exception as e:
            logger.error(f"Errore nel loop di aggiornamento dei sondaggi: {e}")
    
    async def create_poll(self, data):
        """
        Crea un nuovo sondaggio
        
        Args:
            data: Dati del sondaggio
            
        Returns:
            dict: Il sondaggio creato
        """
        try:
            # Genera un ID univoco per il sondaggio
            poll_id = str(uuid.uuid4())
            
            # Verifica i dati richiesti
            if not data.get('question'):
                return {'success': False, 'error': 'Domanda mancante'}
            
            if not data.get('options') or len(data.get('options', [])) < 2:
                return {'success': False, 'error': 'Sono necessarie almeno 2 opzioni'}
            
            # Crea il sondaggio
            duration = int(data.get('duration', 60))  # Durata in secondi
            
            # Crea lo stato iniziale delle opzioni
            options = {}
            for i, option in enumerate(data['options']):
                options[str(i)] = {
                    'text': option,
                    'votes': 0,
                    'voters': []
                }
            
            # Crea il sondaggio
            poll = {
                'id': poll_id,
                'question': data['question'],
                'options': options,
                'platforms': data.get('platforms', ['youtube', 'kick', 'telegram', 'whatsapp']),
                'created_at': datetime.now().timestamp(),
                'start_time': datetime.now().timestamp(),
                'end_time': (datetime.now() + timedelta(seconds=duration)).timestamp(),
                'duration': duration,
                'status': 'active',
                'total_votes': 0,
                'creator_id': data.get('creator_id', 'system'),
                'allow_multiple_votes': data.get('allow_multiple_votes', False)
            }
            
            # Registra il sondaggio
            self.polls[poll_id] = poll
            self.active_polls[poll_id] = poll
            
            # Salva i sondaggi
            self._save_polls()
            
            # Pubblica il sondaggio sulle piattaforme selezionate
            await self._publish_poll(poll)
            
            return {'success': True, 'poll': poll}
        except Exception as e:
            logger.error(f"Errore nella creazione del sondaggio: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_poll(self, poll_id):
        """
        Ottiene un sondaggio
        
        Args:
            poll_id: ID del sondaggio
            
        Returns:
            dict: Il sondaggio, o None se non trovato
        """
        return self.polls.get(poll_id)
    
    async def vote(self, poll_id, option_id, voter_id, platform):
        """
        Registra un voto per un sondaggio
        
        Args:
            poll_id: ID del sondaggio
            option_id: ID dell'opzione
            voter_id: ID del votante
            platform: Piattaforma da cui proviene il voto
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che il sondaggio esista
            poll = self.polls.get(poll_id)
            if not poll:
                return {'success': False, 'error': 'Sondaggio non trovato'}
            
            # Verifica che il sondaggio sia attivo
            if poll['status'] != 'active':
                return {'success': False, 'error': 'Il sondaggio non è attivo'}
            
            # Verifica che l'opzione esista
            if option_id not in poll['options']:
                return {'success': False, 'error': 'Opzione non valida'}
            
            # Crea un ID univoco per il votante + piattaforma
            voter_key = f"{platform}_{voter_id}"
            
            # Verifica se l'utente ha già votato
            has_voted = False
            for option in poll['options'].values():
                if voter_key in option['voters']:
                    has_voted = True
                    # Se non sono permessi voti multipli, rifiuta il voto
                    if not poll['allow_multiple_votes']:
                        return {'success': False, 'error': 'Hai già votato per questo sondaggio'}
                    # Altrimenti rimuovi il voto precedente
                    option['voters'].remove(voter_key)
                    option['votes'] -= 1
                    poll['total_votes'] -= 1
            
            # Registra il voto
            poll['options'][option_id]['voters'].append(voter_key)
            poll['options'][option_id]['votes'] += 1
            poll['total_votes'] += 1
            
            # Salva i sondaggi
            self._save_polls()
            
            return {'success': True, 'poll': poll}
        except Exception as e:
            logger.error(f"Errore nella registrazione del voto: {e}")
            return {'success': False, 'error': str(e)}
    
    async def close_poll(self, poll_id):
        """
        Chiude un sondaggio
        
        Args:
            poll_id: ID del sondaggio
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che il sondaggio esista
            poll = self.polls.get(poll_id)
            if not poll:
                return {'success': False, 'error': 'Sondaggio non trovato'}
            
            # Verifica che il sondaggio sia attivo
            if poll['status'] != 'active':
                return {'success': False, 'error': 'Il sondaggio non è attivo'}
            
            # Chiudi il sondaggio
            poll['status'] = 'closed'
            poll['end_time'] = datetime.now().timestamp()
            
            # Rimuovi il sondaggio dai sondaggi attivi
            if poll_id in self.active_polls:
                del self.active_polls[poll_id]
            
            # Salva i sondaggi
            self._save_polls()
            
            # Pubblica i risultati del sondaggio
            await self._publish_results(poll)
            
            return {'success': True, 'poll': poll}
        except Exception as e:
            logger.error(f"Errore nella chiusura del sondaggio: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _publish_poll(self, poll):
        """
        Pubblica un sondaggio sulle piattaforme selezionate
        
        Args:
            poll: Il sondaggio da pubblicare
        """
        # Formatta il messaggio del sondaggio
        question = poll['question']
        options_text = "\n".join([f"{i+1}) {option['text']}" for i, option in enumerate(poll['options'].values())])
        duration_minutes = round(poll['duration'] / 60)
        
        message = f"📊 SONDAGGIO: {question}\n\n{options_text}\n\nVota rispondendo con il numero dell'opzione. Hai {duration_minutes} minuti per votare."
        
        # Pubblica sulle piattaforme selezionate
        for platform in poll['platforms']:
            try:
                if platform == 'youtube' and hasattr(self.app, 'youtube_connector'):
                    await self._send_youtube_poll(poll, message)
                
                elif platform == 'kick' and hasattr(self.app, 'kick_connector'):
                    await self._send_kick_message(message)
                
                elif platform == 'telegram' and hasattr(self.app, 'telegram_connector'):
                    await self._send_telegram_poll(poll)
                
                elif platform == 'whatsapp' and hasattr(self.app, 'whatsapp_connector'):
                    await self._send_whatsapp_message(message)
            except Exception as e:
                logger.error(f"Errore nella pubblicazione del sondaggio su {platform}: {e}")
    
    async def _publish_results(self, poll):
        """
        Pubblica i risultati di un sondaggio
        
        Args:
            poll: Il sondaggio di cui pubblicare i risultati
        """
        # Formatta il messaggio dei risultati
        question = poll['question']
        
        # Calcola le percentuali
        total_votes = max(poll['total_votes'], 1)  # Evita divisione per zero
        results = []
        
        for i, (option_id, option) in enumerate(poll['options'].items()):
            percentage = round((option['votes'] / total_votes) * 100)
            results.append(f"{i+1}) {option['text']} - {option['votes']} voti ({percentage}%)")
        
        results_text = "\n".join(results)
        message = f"📊 RISULTATI SONDAGGIO: {question}\n\n{results_text}\n\nTotale voti: {total_votes}"
        
        # Pubblica sulle piattaforme selezionate
        for platform in poll['platforms']:
            try:
                if platform == 'youtube' and hasattr(self.app, 'youtube_connector'):
                    await self._send_youtube_message(message)
                
                elif platform == 'kick' and hasattr(self.app, 'kick_connector'):
                    await self._send_kick_message(message)
                
                elif platform == 'telegram' and hasattr(self.app, 'telegram_connector'):
                    await self._send_telegram_message(message)
                
                elif platform == 'whatsapp' and hasattr(self.app, 'whatsapp_connector'):
                    await self._send_whatsapp_message(message)
            except Exception as e:
                logger.error(f"Errore nella pubblicazione dei risultati su {platform}: {e}")
    
    async def _send_youtube_poll(self, poll, message):
        """Invia un sondaggio su YouTube (come messaggio nella chat)"""
        if hasattr(self.app, 'youtube_connector'):
            await self.app.youtube_connector.send_chat_message(message)
    
    async def _send_youtube_message(self, message):
        """Invia un messaggio su YouTube"""
        if hasattr(self.app, 'youtube_connector'):
            await self.app.youtube_connector.send_chat_message(message)
    
    async def _send_kick_message(self, message):
        """Invia un messaggio su Kick"""
        if hasattr(self.app, 'kick_connector'):
            await self.app.kick_connector.send_chat_message(message)
    
    async def _send_telegram_poll(self, poll):
        """Invia un sondaggio su Telegram"""
        if hasattr(self.app, 'telegram_connector'):
            # Estrai le opzioni
            options = [option['text'] for option in poll['options'].values()]
            
            # Calcola la durata in secondi
            duration = int(poll['end_time'] - datetime.now().timestamp())
            if duration < 5:
                duration = 5  # Durata minima di 5 secondi
            
            # Invia il sondaggio
            for chat_id in self.app.config.get('TELEGRAM_CHAT_IDS', []):
                await self.app.telegram_connector.send_poll(
                    chat_id=chat_id,
                    question=poll['question'],
                    options=options,
                    is_anonymous=False,
                    open_period=duration
                )
    
    async def _send_telegram_message(self, message):
        """Invia un messaggio su Telegram"""
        if hasattr(self.app, 'telegram_connector'):
            for chat_id in self.app.config.get('TELEGRAM_CHAT_IDS', []):
                await self.app.telegram_connector.send_message(
                    chat_id=chat_id,
                    text=message
                )
    
    async def _send_whatsapp_message(self, message):
        """Invia un messaggio su WhatsApp"""
        if hasattr(self.app, 'whatsapp_connector'):
            for recipient in self.app.config.get('WHATSAPP_RECIPIENTS', []):
                await self.app.whatsapp_connector.send_message(
                    recipient=recipient,
                    message=message
                )

def setup(app):
    """
    Configura il plugin di sondaggi
    
    Args:
        app: L'applicazione Flask/Quart
    """
    # Inizializza il gestore dei sondaggi
    app.poll_manager = PollManager(app)
    
    # Registra il blueprint
    app.register_blueprint(polls_blueprint, url_prefix='/polls')
    
    # Definisci le route
    @polls_blueprint.route('/', methods=['GET'])
    async def polls_page():
        """Pagina principale dei sondaggi"""
        polls = app.poll_manager.polls
        return await render_template('polls.html', polls=polls)
    
    @polls_blueprint.route('/api/polls', methods=['GET'])
    async def get_polls():
        """API per ottenere tutti i sondaggi"""
        return jsonify(list(app.poll_manager.polls.values()))
    
    @polls_blueprint.route('/api/polls/active', methods=['GET'])
    async def get_active_polls():
        """API per ottenere i sondaggi attivi"""
        return jsonify(list(app.poll_manager.active_polls.values()))
    
    @polls_blueprint.route('/api/polls/<poll_id>', methods=['GET'])
    async def get_poll(poll_id):
        """API per ottenere un sondaggio specifico"""
        poll = await app.poll_manager.get_poll(poll_id)
        if poll:
            return jsonify(poll)
        else:
            return jsonify({'error': 'Sondaggio non trovato'}), 404
    
    @polls_blueprint.route('/api/polls', methods=['POST'])
    async def create_poll():
        """API per creare un nuovo sondaggio"""
        data = await request.json
        result = await app.poll_manager.create_poll(data)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @polls_blueprint.route('/api/polls/<poll_id>/vote', methods=['POST'])
    async def vote(poll_id):
        """API per votare un sondaggio"""
        data = await request.json
        result = await app.poll_manager.vote(
            poll_id=poll_id,
            option_id=data.get('option_id'),
            voter_id=data.get('voter_id'),
            platform=data.get('platform', 'web')
        )
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @polls_blueprint.route('/api/polls/<poll_id>/close', methods=['POST'])
    async def close_poll(poll_id):
        """API per chiudere un sondaggio"""
        result = await app.poll_manager.close_poll(poll_id)
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    # Aggiungi la gestione dei messaggi in arrivo per rilevare i voti
    if hasattr(app, 'message_handler'):
        app.message_handler.register_handler(handle_poll_vote)
    
    logger.info("Plugin di sondaggi configurato")

async def handle_poll_vote(message, app):
    """
    Gestore dei messaggi per i voti ai sondaggi
    
    Args:
        message: Il messaggio ricevuto
        app: L'applicazione Flask/Quart
        
    Returns:
        bool: True se il messaggio è stato gestito, False altrimenti
    """
    if not hasattr(app, 'poll_manager') or not app.poll_manager.active_polls:
        return False
    
    try:
        # Estrai il contenuto del messaggio
        content = message.get('content', '').strip()
        platform = message.get('platform', 'unknown')
        user_id = message.get('author', {}).get('id', 'unknown')
        
        # Verifica se il contenuto è un numero
        if not content.isdigit():
            return False
        
        option_number = int(content)
        
        # Verifica se c'è un sondaggio attivo e registra il voto
        for poll_id, poll in app.poll_manager.active_polls.items():
            # Controlla se la piattaforma è inclusa nel sondaggio
            if platform not in poll['platforms']:
                continue
            
            # Verifica se l'opzione è valida (1-based)
            if option_number < 1 or option_number > len(poll['options']):
                continue
            
            # Converti l'opzione in index 0-based
            option_id = str(option_number - 1)
            
            # Registra il voto
            await app.poll_manager.vote(poll_id, option_id, user_id, platform)
            return True
        
        return False
    except Exception as e:
        logger.error(f"Errore nella gestione del voto: {e}")
        return False 