from flask import Blueprint, jsonify, request, render_template, current_app, session
from functools import wraps
import logging
import json
import os
import uuid
from datetime import datetime, timedelta
import re

# Inizializza il blueprint
workflows_blueprint = Blueprint('workflows', __name__)

# Logger
logger = logging.getLogger(__name__)

# Directory per i file di configurazione
WORKFLOWS_DIR = "data/workflows"
os.makedirs(WORKFLOWS_DIR, exist_ok=True)

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

# Funzione per ottenere tutti i flussi di lavoro di un utente
def get_user_workflows(user_id):
    """Carica i flussi di lavoro dell'utente"""
    try:
        file_path = os.path.join(WORKFLOWS_DIR, f"workflows_{user_id}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        else:
            return []
    except Exception as e:
        logger.error(f"Errore nel caricamento dei flussi di lavoro dell'utente {user_id}: {e}")
        return []

# Funzione per salvare i flussi di lavoro di un utente
def save_user_workflows(user_id, workflows):
    """Salva i flussi di lavoro dell'utente"""
    try:
        file_path = os.path.join(WORKFLOWS_DIR, f"workflows_{user_id}.json")
        with open(file_path, 'w') as f:
            json.dump(workflows, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Errore nel salvataggio dei flussi di lavoro dell'utente {user_id}: {e}")
        return False

# Funzione per ottenere i messaggi pianificati
def get_scheduled_messages(user_id):
    """Carica i messaggi pianificati dell'utente"""
    try:
        file_path = os.path.join(WORKFLOWS_DIR, f"scheduled_{user_id}.json")
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        else:
            return []
    except Exception as e:
        logger.error(f"Errore nel caricamento dei messaggi pianificati dell'utente {user_id}: {e}")
        return []

# Funzione per salvare i messaggi pianificati
def save_scheduled_messages(user_id, messages):
    """Salva i messaggi pianificati dell'utente"""
    try:
        file_path = os.path.join(WORKFLOWS_DIR, f"scheduled_{user_id}.json")
        with open(file_path, 'w') as f:
            json.dump(messages, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Errore nel salvataggio dei messaggi pianificati dell'utente {user_id}: {e}")
        return False

# Funzione per validare una condizione
def validate_condition(condition, data):
    """Valida una condizione rispetto ai dati forniti"""
    try:
        field = condition.get('field')
        operator = condition.get('operator')
        value = condition.get('value')
        
        # Se il campo contiene punti, naviga nella struttura dati
        if '.' in field:
            parts = field.split('.')
            current = data
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return False
            field_value = current
        else:
            field_value = data.get(field)
        
        # Applica l'operatore
        if operator == 'equals':
            return field_value == value
        elif operator == 'not_equals':
            return field_value != value
        elif operator == 'contains':
            return value in str(field_value)
        elif operator == 'not_contains':
            return value not in str(field_value)
        elif operator == 'greater_than':
            try:
                return float(field_value) > float(value)
            except (ValueError, TypeError):
                return False
        elif operator == 'less_than':
            try:
                return float(field_value) < float(value)
            except (ValueError, TypeError):
                return False
        elif operator == 'matches_regex':
            try:
                pattern = re.compile(value)
                return bool(pattern.search(str(field_value)))
            except:
                return False
        else:
            return False
    except Exception as e:
        logger.error(f"Errore nella validazione della condizione: {e}")
        return False

@workflows_blueprint.route('/workflows')
@login_required
async def workflows_page():
    """Pagina di gestione dei flussi di lavoro"""
    try:
        user_id = session.get('user_id')
        
        # Carica i flussi di lavoro dell'utente
        workflows = get_user_workflows(user_id)
        
        # Carica i template per riferimento
        templates = {
            'whatsapp': [],
            'telegram': [],
            'youtube': []
        }
        
        # Ottieni i template dal file templates.py
        try:
            from web.routes.templates import get_templates
            templates['whatsapp'] = get_templates('whatsapp')
            templates['telegram'] = get_templates('telegram')
            templates['youtube'] = get_templates('youtube')
        except Exception as e:
            logger.error(f"Errore nel caricamento dei template: {e}")
        
        return await render_template('workflows.html', 
                                    workflows=workflows,
                                    templates=templates)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina dei flussi di lavoro: {e}")
        return await render_template('error.html', message=f"Errore nel caricamento dei flussi di lavoro: {str(e)}"), 500

@workflows_blueprint.route('/api/workflows', methods=['GET', 'POST'])
@login_required
async def workflows_api():
    """API per ottenere o creare flussi di lavoro"""
    try:
        user_id = session.get('user_id')
        
        if request.method == 'GET':
            # Ottieni i flussi di lavoro
            workflows = get_user_workflows(user_id)
            return jsonify({'success': True, 'workflows': workflows})
        else:  # POST
            # Crea un nuovo flusso di lavoro
            data = await request.json
            
            # Verifica campi obbligatori
            if 'name' not in data or 'trigger' not in data or 'actions' not in data:
                return jsonify({'success': False, 'message': 'Dati incompleti'}), 400
            
            # Crea il nuovo flusso di lavoro
            new_workflow = {
                'id': str(uuid.uuid4()),
                'name': data['name'],
                'description': data.get('description', ''),
                'enabled': data.get('enabled', True),
                'trigger': data['trigger'],
                'conditions': data.get('conditions', []),
                'actions': data['actions'],
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # Ottieni i flussi di lavoro esistenti
            workflows = get_user_workflows(user_id)
            
            # Aggiungi il nuovo flusso di lavoro
            workflows.append(new_workflow)
            
            # Salva i flussi di lavoro
            if save_user_workflows(user_id, workflows):
                # Pubblica un evento per aggiornare il sistema
                if hasattr(current_app, 'redis_client') and current_app.redis_client:
                    await current_app.redis_client.publish('m4bot_notifications', json.dumps({
                        'type': 'workflow_created',
                        'user_id': user_id,
                        'workflow_id': new_workflow['id'],
                        'timestamp': datetime.now().isoformat()
                    }))
                
                return jsonify({'success': True, 'workflow': new_workflow})
            else:
                return jsonify({'success': False, 'message': 'Errore nel salvataggio del flusso di lavoro'}), 500
    except Exception as e:
        logger.error(f"Errore API workflows: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@workflows_blueprint.route('/api/workflows/<workflow_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
async def workflow_api(workflow_id):
    """API per ottenere, aggiornare o eliminare un flusso di lavoro specifico"""
    try:
        user_id = session.get('user_id')
        
        # Ottieni i flussi di lavoro
        workflows = get_user_workflows(user_id)
        
        # Trova l'indice del flusso di lavoro
        workflow_index = next((i for i, w in enumerate(workflows) if w['id'] == workflow_id), None)
        
        if workflow_index is None:
            return jsonify({'success': False, 'message': 'Flusso di lavoro non trovato'}), 404
        
        if request.method == 'GET':
            # Restituisci il flusso di lavoro
            return jsonify({'success': True, 'workflow': workflows[workflow_index]})
        
        elif request.method == 'PUT':
            # Aggiorna il flusso di lavoro
            data = await request.json
            
            # Aggiorna i campi
            workflow = workflows[workflow_index]
            workflow['name'] = data.get('name', workflow['name'])
            workflow['description'] = data.get('description', workflow['description'])
            workflow['enabled'] = data.get('enabled', workflow['enabled'])
            workflow['trigger'] = data.get('trigger', workflow['trigger'])
            workflow['conditions'] = data.get('conditions', workflow['conditions'])
            workflow['actions'] = data.get('actions', workflow['actions'])
            workflow['updated_at'] = datetime.now().isoformat()
            
            # Salva i flussi di lavoro
            if save_user_workflows(user_id, workflows):
                # Pubblica un evento per aggiornare il sistema
                if hasattr(current_app, 'redis_client') and current_app.redis_client:
                    await current_app.redis_client.publish('m4bot_notifications', json.dumps({
                        'type': 'workflow_updated',
                        'user_id': user_id,
                        'workflow_id': workflow_id,
                        'timestamp': datetime.now().isoformat()
                    }))
                
                return jsonify({'success': True, 'workflow': workflow})
            else:
                return jsonify({'success': False, 'message': 'Errore nel salvataggio del flusso di lavoro'}), 500
        
        elif request.method == 'DELETE':
            # Rimuovi il flusso di lavoro
            del workflows[workflow_index]
            
            # Salva i flussi di lavoro
            if save_user_workflows(user_id, workflows):
                # Pubblica un evento per aggiornare il sistema
                if hasattr(current_app, 'redis_client') and current_app.redis_client:
                    await current_app.redis_client.publish('m4bot_notifications', json.dumps({
                        'type': 'workflow_deleted',
                        'user_id': user_id,
                        'workflow_id': workflow_id,
                        'timestamp': datetime.now().isoformat()
                    }))
                
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'message': 'Errore nel salvataggio del flusso di lavoro'}), 500
    except Exception as e:
        logger.error(f"Errore API workflow {workflow_id}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@workflows_blueprint.route('/scheduled_messages')
@login_required
async def scheduled_messages_page():
    """Pagina di gestione dei messaggi pianificati"""
    try:
        user_id = session.get('user_id')
        
        # Carica i messaggi pianificati dell'utente
        messages = get_scheduled_messages(user_id)
        
        # Carica i template per riferimento
        templates = {
            'whatsapp': [],
            'telegram': [],
            'youtube': []
        }
        
        # Ottieni i template dal file templates.py
        try:
            from web.routes.templates import get_templates
            templates['whatsapp'] = get_templates('whatsapp')
            templates['telegram'] = get_templates('telegram')
            templates['youtube'] = get_templates('youtube')
        except Exception as e:
            logger.error(f"Errore nel caricamento dei template: {e}")
        
        return await render_template('scheduled_messages.html', 
                                    messages=messages,
                                    templates=templates)
    except Exception as e:
        logger.error(f"Errore nel caricamento della pagina dei messaggi pianificati: {e}")
        return await render_template('error.html', message=f"Errore nel caricamento dei messaggi pianificati: {str(e)}"), 500

@workflows_blueprint.route('/api/scheduled', methods=['GET', 'POST'])
@login_required
async def scheduled_messages_api():
    """API per ottenere o creare messaggi pianificati"""
    try:
        user_id = session.get('user_id')
        
        if request.method == 'GET':
            # Ottieni i messaggi pianificati
            messages = get_scheduled_messages(user_id)
            return jsonify({'success': True, 'messages': messages})
        else:  # POST
            # Crea un nuovo messaggio pianificato
            data = await request.json
            
            # Verifica campi obbligatori
            if 'template_id' not in data or 'platform' not in data or 'schedule_time' not in data:
                return jsonify({'success': False, 'message': 'Dati incompleti'}), 400
            
            # Crea il nuovo messaggio pianificato
            new_message = {
                'id': str(uuid.uuid4()),
                'name': data.get('name', f"Messaggio pianificato {datetime.now().strftime('%d/%m/%Y %H:%M')}"),
                'template_id': data['template_id'],
                'platform': data['platform'],
                'recipients': data.get('recipients', []),
                'params': data.get('params', {}),
                'schedule_time': data['schedule_time'],
                'repeat': data.get('repeat', None),
                'status': 'pending',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            # Ottieni i messaggi pianificati esistenti
            messages = get_scheduled_messages(user_id)
            
            # Aggiungi il nuovo messaggio pianificato
            messages.append(new_message)
            
            # Salva i messaggi pianificati
            if save_scheduled_messages(user_id, messages):
                # Pubblica un evento per aggiornare il sistema
                if hasattr(current_app, 'redis_client') and current_app.redis_client:
                    await current_app.redis_client.publish('m4bot_notifications', json.dumps({
                        'type': 'scheduled_message_created',
                        'user_id': user_id,
                        'message_id': new_message['id'],
                        'timestamp': datetime.now().isoformat()
                    }))
                
                return jsonify({'success': True, 'message': new_message})
            else:
                return jsonify({'success': False, 'message': 'Errore nel salvataggio del messaggio pianificato'}), 500
    except Exception as e:
        logger.error(f"Errore API messaggi pianificati: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@workflows_blueprint.route('/api/scheduled/<message_id>', methods=['GET', 'PUT', 'DELETE'])
@login_required
async def scheduled_message_api(message_id):
    """API per ottenere, aggiornare o eliminare un messaggio pianificato"""
    try:
        user_id = session.get('user_id')
        
        # Ottieni i messaggi pianificati
        messages = get_scheduled_messages(user_id)
        
        # Trova l'indice del messaggio
        message_index = next((i for i, m in enumerate(messages) if m['id'] == message_id), None)
        
        if message_index is None:
            return jsonify({'success': False, 'message': 'Messaggio pianificato non trovato'}), 404
        
        if request.method == 'GET':
            # Restituisci il messaggio
            return jsonify({'success': True, 'message': messages[message_index]})
        
        elif request.method == 'PUT':
            # Aggiorna il messaggio
            data = await request.json
            
            # Aggiorna i campi
            message = messages[message_index]
            message['name'] = data.get('name', message['name'])
            message['template_id'] = data.get('template_id', message['template_id'])
            message['recipients'] = data.get('recipients', message['recipients'])
            message['params'] = data.get('params', message['params'])
            message['schedule_time'] = data.get('schedule_time', message['schedule_time'])
            message['repeat'] = data.get('repeat', message['repeat'])
            message['updated_at'] = datetime.now().isoformat()
            
            # Salva i messaggi pianificati
            if save_scheduled_messages(user_id, messages):
                # Pubblica un evento per aggiornare il sistema
                if hasattr(current_app, 'redis_client') and current_app.redis_client:
                    await current_app.redis_client.publish('m4bot_notifications', json.dumps({
                        'type': 'scheduled_message_updated',
                        'user_id': user_id,
                        'message_id': message_id,
                        'timestamp': datetime.now().isoformat()
                    }))
                
                return jsonify({'success': True, 'message': message})
            else:
                return jsonify({'success': False, 'message': 'Errore nel salvataggio del messaggio pianificato'}), 500
        
        elif request.method == 'DELETE':
            # Rimuovi il messaggio
            del messages[message_index]
            
            # Salva i messaggi pianificati
            if save_scheduled_messages(user_id, messages):
                # Pubblica un evento per aggiornare il sistema
                if hasattr(current_app, 'redis_client') and current_app.redis_client:
                    await current_app.redis_client.publish('m4bot_notifications', json.dumps({
                        'type': 'scheduled_message_deleted',
                        'user_id': user_id,
                        'message_id': message_id,
                        'timestamp': datetime.now().isoformat()
                    }))
                
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'message': 'Errore nel salvataggio del messaggio pianificato'}), 500
    except Exception as e:
        logger.error(f"Errore API messaggio pianificato {message_id}: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500 