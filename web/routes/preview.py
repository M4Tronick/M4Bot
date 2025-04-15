from flask import Blueprint, jsonify, request, render_template, current_app, session
from functools import wraps
import logging
import json
import os
import re
from datetime import datetime

# Inizializza il blueprint
preview_blueprint = Blueprint('preview', __name__)

# Logger
logger = logging.getLogger(__name__)

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

# Dizionario di variabili dinamiche di sistema
SYSTEM_VARIABLES = {
    "current_date": lambda: datetime.now().strftime("%d/%m/%Y"),
    "current_time": lambda: datetime.now().strftime("%H:%M"),
    "current_datetime": lambda: datetime.now().strftime("%d/%m/%Y %H:%M"),
    "current_year": lambda: datetime.now().strftime("%Y"),
    "current_month": lambda: datetime.now().strftime("%m"),
    "current_day": lambda: datetime.now().strftime("%d"),
    "current_hour": lambda: datetime.now().strftime("%H"),
    "current_minute": lambda: datetime.now().strftime("%M"),
    "current_second": lambda: datetime.now().strftime("%S"),
    "weekday": lambda: ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"][datetime.now().weekday()],
    "month_name": lambda: ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"][datetime.now().month - 1]
}

# Funzione per ottenere tutte le variabili dinamiche disponibili
def get_available_variables():
    """Ottiene tutte le variabili dinamiche disponibili"""
    variables = {
        "system": {k: v() for k, v in SYSTEM_VARIABLES.items()},
        "user": {
            "name": "Nome Utente",
            "email": "email@esempio.com",
            "phone": "+39 123 456 7890"
        },
        "custom": {
            "company_name": "Nome Azienda",
            "product_name": "Nome Prodotto",
            "support_email": "supporto@esempio.com",
            "support_phone": "+39 987 654 3210"
        }
    }
    return variables

# Funzione per processare le variabili in un template
def process_variables(content, custom_vars=None):
    """Processa le variabili in un template"""
    if not content:
        return content
        
    # Combina le variabili di sistema con quelle custom
    variables = {}
    
    # Aggiungi variabili di sistema (valutate al momento)
    for k, v in SYSTEM_VARIABLES.items():
        variables[k] = v()
    
    # Aggiungi variabili personalizzate
    if custom_vars:
        variables.update(custom_vars)
    
    # Pattern per trovare le variabili: {{nome_variabile}}
    pattern = r"{{(.*?)}}"
    
    # Funzione per la sostituzione
    def replace_var(match):
        var_name = match.group(1).strip()
        if var_name in variables:
            return str(variables[var_name])
        else:
            return match.group(0)  # Mantieni il placeholder se la variabile non è definita
    
    # Applica le sostituzioni
    processed_content = re.sub(pattern, replace_var, content)
    
    return processed_content

@preview_blueprint.route('/api/preview', methods=['POST'])
@login_required
async def preview_template():
    """API per l'anteprima di un template con variabili dinamiche"""
    try:
        data = await request.json
        
        # Ottieni il contenuto del template e la piattaforma
        content = data.get('content', '')
        platform = data.get('platform', '')
        
        # Ottieni variabili personalizzate dalla richiesta
        custom_vars = data.get('variables', {})
        
        # Processa le variabili nel template
        processed_content = process_variables(content, custom_vars)
        
        # Output in base alla piattaforma
        if platform == 'whatsapp':
            # Per WhatsApp potremmo fare un parsing specifico o aggiungere formattazione
            output = {
                'text': processed_content,
                'preview_html': processed_content.replace('\n', '<br>')
            }
        elif platform == 'telegram':
            # Per Telegram, supporta HTML o Markdown
            parse_mode = data.get('parse_mode', 'HTML')
            if parse_mode == 'HTML':
                # Assicurati che l'HTML sia utilizzabile (potremmo aggiungere sanitizzazione)
                output = {
                    'text': processed_content,
                    'preview_html': processed_content
                }
            else:  # Markdown
                # Qui potremmo aggiungere conversione da Markdown a HTML per l'anteprima
                output = {
                    'text': processed_content,
                    'preview_html': processed_content.replace('\n', '<br>')
                }
        elif platform == 'youtube':
            # Per YouTube, semplice formattazione testo
            output = {
                'text': processed_content,
                'preview_html': processed_content.replace('\n', '<br>')
            }
        else:
            # Default per altre piattaforme
            output = {
                'text': processed_content,
                'preview_html': processed_content.replace('\n', '<br>')
            }
        
        return jsonify({'success': True, 'preview': output})
    except Exception as e:
        logger.error(f"Errore nella generazione dell'anteprima: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@preview_blueprint.route('/api/variables', methods=['GET'])
@login_required
async def get_variables():
    """API per ottenere tutte le variabili disponibili"""
    try:
        # Ottieni le variabili dinamiche disponibili
        variables = get_available_variables()
        
        return jsonify({'success': True, 'variables': variables})
    except Exception as e:
        logger.error(f"Errore nell'ottenimento delle variabili: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@preview_blueprint.route('/api/variables/custom', methods=['GET', 'POST', 'PUT', 'DELETE'])
@login_required
async def manage_custom_variables():
    """API per gestire le variabili personalizzate dell'utente"""
    try:
        user_id = session.get('user_id')
        file_path = os.path.join('data/variables', f"variables_{user_id}.json")
        os.makedirs('data/variables', exist_ok=True)
        
        if request.method == 'GET':
            # Ottieni le variabili personalizzate dell'utente
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    variables = json.load(f)
            else:
                variables = {}
            
            return jsonify({'success': True, 'variables': variables})
        
        elif request.method in ['POST', 'PUT']:
            # Crea o aggiorna variabili personalizzate
            data = await request.json
            
            # Ottieni le variabili esistenti
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    variables = json.load(f)
            else:
                variables = {}
            
            # Aggiungi o aggiorna le variabili
            for key, value in data.items():
                variables[key] = value
            
            # Salva le variabili
            with open(file_path, 'w') as f:
                json.dump(variables, f, indent=2)
            
            return jsonify({'success': True, 'variables': variables})
        
        elif request.method == 'DELETE':
            # Elimina variabili personalizzate
            data = await request.json
            keys_to_delete = data.get('keys', [])
            
            # Ottieni le variabili esistenti
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    variables = json.load(f)
                
                # Rimuovi le variabili specificate
                for key in keys_to_delete:
                    if key in variables:
                        del variables[key]
                
                # Salva le variabili aggiornate
                with open(file_path, 'w') as f:
                    json.dump(variables, f, indent=2)
            
            return jsonify({'success': True})
    
    except Exception as e:
        logger.error(f"Errore nella gestione delle variabili personalizzate: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500 