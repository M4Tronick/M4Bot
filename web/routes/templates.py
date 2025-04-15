from flask import Blueprint, jsonify, request, render_template, current_app
import logging
import json
import os
import uuid
from datetime import datetime

# Inizializza il blueprint
templates_blueprint = Blueprint('templates', __name__)

# Logger
logger = logging.getLogger(__name__)

# Path per i file dei template
TEMPLATES_DIR = "data/templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# File per i vari tipi di template
WHATSAPP_TEMPLATES_FILE = os.path.join(TEMPLATES_DIR, "whatsapp_templates.json")
TELEGRAM_TEMPLATES_FILE = os.path.join(TEMPLATES_DIR, "telegram_templates.json")
YOUTUBE_TEMPLATES_FILE = os.path.join(TEMPLATES_DIR, "youtube_templates.json")

# Inizializza i file se non esistono
for file_path in [WHATSAPP_TEMPLATES_FILE, TELEGRAM_TEMPLATES_FILE, YOUTUBE_TEMPLATES_FILE]:
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump([], f)

def get_templates(platform):
    """Carica i template per una piattaforma specifica"""
    try:
        file_path = ""
        if platform == "whatsapp":
            file_path = WHATSAPP_TEMPLATES_FILE
        elif platform == "telegram":
            file_path = TELEGRAM_TEMPLATES_FILE
        elif platform == "youtube":
            file_path = YOUTUBE_TEMPLATES_FILE
        else:
            return []
        
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Errore nel caricamento dei template {platform}: {e}")
        return []

def save_templates(platform, templates):
    """Salva i template per una piattaforma specifica"""
    try:
        file_path = ""
        if platform == "whatsapp":
            file_path = WHATSAPP_TEMPLATES_FILE
        elif platform == "telegram":
            file_path = TELEGRAM_TEMPLATES_FILE
        elif platform == "youtube":
            file_path = YOUTUBE_TEMPLATES_FILE
        else:
            return False
        
        with open(file_path, 'w') as f:
            json.dump(templates, f, indent=2)
            
        return True
    except Exception as e:
        logger.error(f"Errore nel salvataggio dei template {platform}: {e}")
        return False

@templates_blueprint.route('/templates', methods=['GET'])
def templates_page():
    """Pagina di gestione dei template"""
    try:
        # Carica i template per tutte le piattaforme
        whatsapp_templates = get_templates("whatsapp")
        telegram_templates = get_templates("telegram")
        youtube_templates = get_templates("youtube")
        
        return render_template('templates_manager.html',
                              whatsapp_templates=whatsapp_templates,
                              telegram_templates=telegram_templates,
                              youtube_templates=youtube_templates)
    except Exception as e:
        logger.error(f"Errore nella visualizzazione della pagina template: {e}")
        return f"Si è verificato un errore: {str(e)}", 500

@templates_blueprint.route('/api/templates/create', methods=['POST'])
def create_template():
    """Crea un nuovo template"""
    try:
        data = request.json
        platform = data.get('platform')
        
        if not platform:
            return jsonify({'success': False, 'message': 'Piattaforma non specificata'}), 400
        
        # Carica i template esistenti
        templates = get_templates(platform)
        
        # Crea il nuovo template
        new_template = {
            'id': str(uuid.uuid4()),
            'name': data.get('name'),
            'description': data.get('description', ''),
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Aggiungi i campi specifici per ciascuna piattaforma
        if platform == "whatsapp":
            new_template.update({
                'language': data.get('language', 'it'),
                'body': data.get('body', ''),
                'components': data.get('components', []),
                'status': 'pending'  # I template WhatsApp devono essere approvati
            })
        elif platform == "telegram":
            new_template.update({
                'parse_mode': data.get('parse_mode', 'HTML'),
                'disable_web_page_preview': data.get('disable_web_page_preview', False),
                'text': data.get('text', ''),
                'params': data.get('params', []),
                'reply_markup': data.get('reply_markup', None)
            })
        elif platform == "youtube":
            new_template.update({
                'type': data.get('type', 'comment'),
                'content': data.get('content', ''),
                'params': data.get('params', []),
                'last_used': None
            })
        else:
            return jsonify({'success': False, 'message': 'Piattaforma non supportata'}), 400
        
        # Aggiungi il template alla lista
        templates.append(new_template)
        
        # Salva i template
        if save_templates(platform, templates):
            return jsonify({'success': True, 'template': new_template})
        else:
            return jsonify({'success': False, 'message': 'Errore nel salvataggio del template'}), 500
    except Exception as e:
        logger.error(f"Errore nella creazione del template: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@templates_blueprint.route('/api/templates/<platform>/<template_id>', methods=['GET'])
def get_template(platform, template_id):
    """Ottiene un template specifico"""
    try:
        templates = get_templates(platform)
        
        # Cerca il template
        template = next((t for t in templates if t['id'] == template_id), None)
        
        if template:
            return jsonify({'success': True, 'template': template})
        else:
            return jsonify({'success': False, 'message': 'Template non trovato'}), 404
    except Exception as e:
        logger.error(f"Errore nell'ottenimento del template: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@templates_blueprint.route('/api/templates/<platform>/<template_id>', methods=['PUT'])
def update_template(platform, template_id):
    """Aggiorna un template esistente"""
    try:
        data = request.json
        templates = get_templates(platform)
        
        # Trova l'indice del template
        template_index = next((i for i, t in enumerate(templates) if t['id'] == template_id), None)
        
        if template_index is None:
            return jsonify({'success': False, 'message': 'Template non trovato'}), 404
        
        # Ottieni il template esistente
        template = templates[template_index]
        
        # Aggiorna i campi comuni
        template['name'] = data.get('name', template['name'])
        template['description'] = data.get('description', template['description'])
        template['updated_at'] = datetime.now().isoformat()
        
        # Aggiorna i campi specifici per ciascuna piattaforma
        if platform == "whatsapp":
            template['language'] = data.get('language', template.get('language', 'it'))
            template['body'] = data.get('body', template.get('body', ''))
            template['components'] = data.get('components', template.get('components', []))
            # Non aggiornare lo status, deve essere gestito separatamente
        elif platform == "telegram":
            template['parse_mode'] = data.get('parse_mode', template.get('parse_mode', 'HTML'))
            template['disable_web_page_preview'] = data.get('disable_web_page_preview', template.get('disable_web_page_preview', False))
            template['text'] = data.get('text', template.get('text', ''))
            template['params'] = data.get('params', template.get('params', []))
            template['reply_markup'] = data.get('reply_markup', template.get('reply_markup', None))
        elif platform == "youtube":
            template['type'] = data.get('type', template.get('type', 'comment'))
            template['content'] = data.get('content', template.get('content', ''))
            template['params'] = data.get('params', template.get('params', []))
        
        # Aggiorna il template nella lista
        templates[template_index] = template
        
        # Salva i template
        if save_templates(platform, templates):
            return jsonify({'success': True, 'template': template})
        else:
            return jsonify({'success': False, 'message': 'Errore nel salvataggio del template'}), 500
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento del template: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@templates_blueprint.route('/api/templates/<platform>/<template_id>', methods=['DELETE'])
def delete_template(platform, template_id):
    """Elimina un template"""
    try:
        templates = get_templates(platform)
        
        # Filtra la lista per rimuovere il template
        updated_templates = [t for t in templates if t['id'] != template_id]
        
        if len(updated_templates) == len(templates):
            return jsonify({'success': False, 'message': 'Template non trovato'}), 404
        
        # Salva i template aggiornati
        if save_templates(platform, updated_templates):
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'message': 'Errore nell\'eliminazione del template'}), 500
    except Exception as e:
        logger.error(f"Errore nell'eliminazione del template: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@templates_blueprint.route('/api/templates/<platform>', methods=['GET'])
def list_templates(platform):
    """Lista dei template per una piattaforma"""
    try:
        templates = get_templates(platform)
        return jsonify({'success': True, 'templates': templates})
    except Exception as e:
        logger.error(f"Errore nell'ottenimento della lista dei template: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@templates_blueprint.route('/api/templates/all', methods=['GET'])
def all_templates():
    """Lista di tutti i template per tutte le piattaforme"""
    try:
        whatsapp_templates = get_templates("whatsapp")
        telegram_templates = get_templates("telegram")
        youtube_templates = get_templates("youtube")
        
        return jsonify({
            'success': True,
            'templates': {
                'whatsapp': whatsapp_templates,
                'telegram': telegram_templates,
                'youtube': youtube_templates
            }
        })
    except Exception as e:
        logger.error(f"Errore nell'ottenimento di tutti i template: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500 