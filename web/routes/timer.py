import os
import json
import time
import uuid
import threading
import logging
from flask import Blueprint, request, jsonify, render_template, current_app
from datetime import datetime, timedelta
from werkzeug.utils import secure_filename

# Inizializzazione del Blueprint e del logger
timer = Blueprint('timer', __name__, url_prefix='/timer')
logger = logging.getLogger(__name__)

# Percorso del file per salvare i timer
TIMER_DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'timer')
TIMER_FILE = os.path.join(TIMER_DIRECTORY, 'timers.json')

# Assicurati che la directory esista
os.makedirs(TIMER_DIRECTORY, exist_ok=True)

# Dizionario per tenere traccia dei timer attivi in memoria
active_timers = {}
timers_lock = threading.Lock()

# Funzione per caricare i timer
def load_timers():
    try:
        if os.path.exists(TIMER_FILE):
            with open(TIMER_FILE, 'r', encoding='utf-8') as file:
                return json.load(file)
        else:
            return {"timers": []}
    except Exception as e:
        logger.error(f"Errore durante il caricamento dei timer: {str(e)}")
        return {"timers": []}

# Funzione per salvare i timer
def save_timers(timers_data):
    try:
        with open(TIMER_FILE, 'w', encoding='utf-8') as file:
            json.dump(timers_data, file, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"Errore durante il salvataggio dei timer: {str(e)}")
        return False

# Funzione per trovare un timer per ID
def find_timer_by_id(timer_id):
    timers_data = load_timers()
    for timer in timers_data.get("timers", []):
        if timer.get("id") == timer_id:
            return timer
    return None

# Funzione per aggiornare un timer specifico
def update_timer(timer_id, updated_timer):
    timers_data = load_timers()
    for i, timer in enumerate(timers_data.get("timers", [])):
        if timer.get("id") == timer_id:
            timers_data["timers"][i] = updated_timer
            save_timers(timers_data)
            return True
    return False

# Funzione per calcolare lo stato attuale di un timer
def calculate_timer_status(timer):
    current_time = time.time()
    
    if timer.get("status") == "stopped":
        return timer
    
    if timer.get("status") == "paused":
        return timer
    
    if timer.get("type") == "countdown":
        # Calcola il tempo rimanente per il countdown
        end_time = timer.get("start_time", 0) + timer.get("duration", 0)
        
        if current_time >= end_time:
            timer["status"] = "completed"
            timer["time_remaining"] = 0
        else:
            timer["time_remaining"] = end_time - current_time
    
    elif timer.get("type") == "stopwatch":
        # Calcola il tempo trascorso per il cronometro
        if timer.get("status") == "running":
            timer["elapsed_time"] = current_time - timer.get("start_time", current_time)
    
    return timer

# Pagina di gestione dei timer
@timer.route('/', methods=['GET'])
def timer_manager_page():
    return render_template('timer_manager.html')

# Endpoint per ottenere il sovrapposizione OBS per un timer
@timer.route('/obs/<timer_id>', methods=['GET'])
def obs_timer_overlay(timer_id):
    timer_data = find_timer_by_id(timer_id)
    if not timer_data:
        return render_template('error.html', message="Timer non trovato"), 404
    
    return render_template('obs_timer.html', timer_id=timer_id)

# API ROUTES

# Endpoint per creare un nuovo timer
@timer.route('/api', methods=['POST'])
def create_timer():
    try:
        data = request.json
        
        # Validazione dei dati
        if not data.get("name"):
            return jsonify({"success": False, "error": "Il nome è obbligatorio"}), 400
            
        if not data.get("type") or data.get("type") not in ["countdown", "stopwatch"]:
            return jsonify({"success": False, "error": "Tipo non valido"}), 400
        
        # Generazione di un nuovo ID univoco
        timer_id = str(uuid.uuid4())
        
        # Creazione del nuovo timer
        current_time = time.time()
        new_timer = {
            "id": timer_id,
            "name": data.get("name", ""),
            "type": data.get("type", "countdown"),
            "duration": data.get("duration", 300) if data.get("type") == "countdown" else 0,  # Durata predefinita: 5 minuti
            "created_at": current_time,
            "updated_at": current_time,
            "start_time": 0,  # Sarà impostato quando il timer viene avviato
            "status": "stopped",  # stopped, running, paused, completed
            "time_remaining": data.get("duration", 300) if data.get("type") == "countdown" else 0,
            "elapsed_time": 0,
            "settings": {
                "text_color": data.get("settings", {}).get("text_color", "#FFFFFF"),
                "background_color": data.get("settings", {}).get("background_color", "rgba(0, 0, 0, 0.7)"),
                "font_size": data.get("settings", {}).get("font_size", "48px"),
                "show_title": data.get("settings", {}).get("show_title", True),
                "show_milliseconds": data.get("settings", {}).get("show_milliseconds", False),
                "alert_at": data.get("settings", {}).get("alert_at", []),  # Array di secondi in cui mostrare un alert
                "action_at_zero": data.get("settings", {}).get("action_at_zero", "stop"),  # stop, loop, continue
                "format": data.get("settings", {}).get("format", "hh:mm:ss")
            }
        }
        
        # Salvataggio del timer
        timers_data = load_timers()
        timers_data.setdefault("timers", []).append(new_timer)
        
        if save_timers(timers_data):
            return jsonify({
                "success": True,
                "timer": new_timer
            })
        else:
            return jsonify({"success": False, "error": "Errore durante il salvataggio del timer"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante la creazione del timer: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per ottenere un timer specifico
@timer.route('/api/<timer_id>', methods=['GET'])
def get_timer(timer_id):
    timer_data = find_timer_by_id(timer_id)
    
    if not timer_data:
        return jsonify({"success": False, "error": "Timer non trovato"}), 404
    
    # Aggiorna lo stato del timer
    timer_data = calculate_timer_status(timer_data)
    update_timer(timer_id, timer_data)
    
    return jsonify({"success": True, "timer": timer_data})

# Endpoint per gli aggiornamenti live di un timer (per OBS)
@timer.route('/api/<timer_id>/live', methods=['GET'])
def get_timer_live(timer_id):
    timer_data = find_timer_by_id(timer_id)
    
    if not timer_data:
        return jsonify({"success": False, "error": "Timer non trovato"}), 404
    
    # Aggiorna lo stato del timer
    timer_data = calculate_timer_status(timer_data)
    update_timer(timer_id, timer_data)
    
    # Semplifica i dati per l'overlay OBS
    live_timer = {
        "name": timer_data.get("name", ""),
        "type": timer_data.get("type", ""),
        "status": timer_data.get("status", ""),
        "time_remaining": timer_data.get("time_remaining", 0) if timer_data.get("type") == "countdown" else 0,
        "elapsed_time": timer_data.get("elapsed_time", 0) if timer_data.get("type") == "stopwatch" else 0,
        "settings": timer_data.get("settings", {})
    }
    
    return jsonify({"success": True, "timer": live_timer})

# Endpoint per aggiornare un timer
@timer.route('/api/<timer_id>', methods=['PUT', 'PATCH'])
def update_timer_endpoint(timer_id):
    try:
        timer_data = find_timer_by_id(timer_id)
        
        if not timer_data:
            return jsonify({"success": False, "error": "Timer non trovato"}), 404
        
        data = request.json
        
        # Aggiorna i campi consentiti
        for field in ["name", "type", "duration", "status", "settings"]:
            if field in data:
                timer_data[field] = data[field]
        
        # Aggiorna i timestamp
        timer_data["updated_at"] = time.time()
        
        # Aggiorna lo stato
        timer_data = calculate_timer_status(timer_data)
        
        # Salva le modifiche
        if update_timer(timer_id, timer_data):
            return jsonify({"success": True, "timer": timer_data})
        else:
            return jsonify({"success": False, "error": "Errore durante l'aggiornamento del timer"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante l'aggiornamento del timer: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per avviare un timer
@timer.route('/api/<timer_id>/start', methods=['POST'])
def start_timer(timer_id):
    try:
        timer_data = find_timer_by_id(timer_id)
        
        if not timer_data:
            return jsonify({"success": False, "error": "Timer non trovato"}), 404
        
        current_time = time.time()
        
        # Se il timer è già in esecuzione, non fare nulla
        if timer_data.get("status") == "running":
            return jsonify({"success": True, "timer": timer_data})
        
        # Se il timer è in pausa, riprendilo
        if timer_data.get("status") == "paused":
            # Calcola il nuovo tempo di inizio in base al tempo rimanente (per countdown)
            # o al tempo già trascorso (per cronometro)
            if timer_data.get("type") == "countdown":
                timer_data["start_time"] = current_time - (timer_data.get("duration", 0) - timer_data.get("time_remaining", 0))
            else:
                timer_data["start_time"] = current_time - timer_data.get("elapsed_time", 0)
        else:
            # Se il timer è fermo o completato, avvialo da capo
            timer_data["start_time"] = current_time
            if timer_data.get("type") == "countdown":
                timer_data["time_remaining"] = timer_data.get("duration", 0)
            else:
                timer_data["elapsed_time"] = 0
        
        timer_data["status"] = "running"
        
        # Aggiorna lo stato
        timer_data = calculate_timer_status(timer_data)
        
        # Salva le modifiche
        if update_timer(timer_id, timer_data):
            return jsonify({"success": True, "timer": timer_data})
        else:
            return jsonify({"success": False, "error": "Errore durante l'avvio del timer"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante l'avvio del timer: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per mettere in pausa un timer
@timer.route('/api/<timer_id>/pause', methods=['POST'])
def pause_timer(timer_id):
    try:
        timer_data = find_timer_by_id(timer_id)
        
        if not timer_data:
            return jsonify({"success": False, "error": "Timer non trovato"}), 404
        
        # Se il timer non è in esecuzione, non fare nulla
        if timer_data.get("status") != "running":
            return jsonify({"success": True, "timer": timer_data})
        
        # Aggiorna lo stato
        timer_data = calculate_timer_status(timer_data)
        timer_data["status"] = "paused"
        
        # Salva le modifiche
        if update_timer(timer_id, timer_data):
            return jsonify({"success": True, "timer": timer_data})
        else:
            return jsonify({"success": False, "error": "Errore durante la pausa del timer"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante la pausa del timer: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per fermare un timer
@timer.route('/api/<timer_id>/stop', methods=['POST'])
def stop_timer(timer_id):
    try:
        timer_data = find_timer_by_id(timer_id)
        
        if not timer_data:
            return jsonify({"success": False, "error": "Timer non trovato"}), 404
        
        timer_data["status"] = "stopped"
        
        if timer_data.get("type") == "countdown":
            timer_data["time_remaining"] = timer_data.get("duration", 0)
        else:
            timer_data["elapsed_time"] = 0
        
        # Salva le modifiche
        if update_timer(timer_id, timer_data):
            return jsonify({"success": True, "timer": timer_data})
        else:
            return jsonify({"success": False, "error": "Errore durante l'arresto del timer"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante l'arresto del timer: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per resettare un timer
@timer.route('/api/<timer_id>/reset', methods=['POST'])
def reset_timer(timer_id):
    try:
        timer_data = find_timer_by_id(timer_id)
        
        if not timer_data:
            return jsonify({"success": False, "error": "Timer non trovato"}), 404
        
        if timer_data.get("type") == "countdown":
            timer_data["time_remaining"] = timer_data.get("duration", 0)
        else:
            timer_data["elapsed_time"] = 0
        
        # Non cambiamo lo stato per consentire un reset senza interrompere un timer in esecuzione
        
        # Aggiorna lo stato
        if timer_data.get("status") == "running":
            timer_data["start_time"] = time.time()
        
        # Salva le modifiche
        if update_timer(timer_id, timer_data):
            return jsonify({"success": True, "timer": timer_data})
        else:
            return jsonify({"success": False, "error": "Errore durante il reset del timer"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante il reset del timer: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per eliminare un timer
@timer.route('/api/<timer_id>', methods=['DELETE'])
def delete_timer(timer_id):
    try:
        timers_data = load_timers()
        
        # Cerca il timer da eliminare
        found = False
        for i, timer in enumerate(timers_data.get("timers", [])):
            if timer.get("id") == timer_id:
                del timers_data["timers"][i]
                found = True
                break
                
        if not found:
            return jsonify({"success": False, "error": "Timer non trovato"}), 404
        
        # Salva le modifiche
        if save_timers(timers_data):
            return jsonify({"success": True, "message": "Timer eliminato con successo"})
        else:
            return jsonify({"success": False, "error": "Errore durante l'eliminazione del timer"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante l'eliminazione del timer: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per elencare tutti i timer
@timer.route('/api', methods=['GET'])
def list_timers():
    try:
        timers_data = load_timers()
        
        # Aggiorna lo stato di ogni timer
        for timer in timers_data.get("timers", []):
            calculate_timer_status(timer)
            
        # Filtra timer in base ai parametri di query
        status = request.args.get('status')
        type_filter = request.args.get('type')
        limit = request.args.get('limit', type=int)
        
        filtered_timers = timers_data.get("timers", [])
        
        if status:
            filtered_timers = [t for t in filtered_timers if t.get("status") == status]
            
        if type_filter:
            filtered_timers = [t for t in filtered_timers if t.get("type") == type_filter]
            
        # Ordina per data di creazione (più recente prima)
        filtered_timers.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        
        # Applica il limite se specificato
        if limit and limit > 0:
            filtered_timers = filtered_timers[:limit]
            
        return jsonify({
            "success": True,
            "timers": filtered_timers,
            "total": len(filtered_timers)
        })
            
    except Exception as e:
        logger.error(f"Errore durante l'elenco dei timer: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Aggiorna lo stato dei timer attivi
def update_active_timers():
    with timers_lock:
        current_time = time.time()
        timers = load_timers()
        
        for timer_id, timer in list(active_timers.items()):
            if timer['status'] == 'running':
                if timer['type'] == 'countdown':
                    # Calcola il tempo rimanente
                    elapsed = current_time - timer['start_time']
                    remaining = max(0, timer['duration'] - elapsed)
                    timer['time_remaining'] = remaining
                    
                    # Controlla se il countdown è terminato
                    if remaining <= 0:
                        timer['status'] = 'completed'
                        timer['time_remaining'] = 0
                        
                        # Aggiorna il timer nel file
                        for i, t in enumerate(timers.get("timers", [])):
                            if t.get("id") == timer_id:
                                timers["timers"][i].update(timer)
                                save_timers(timers)
                                break
                
                elif timer['type'] == 'stopwatch':
                    # Calcola il tempo trascorso
                    if 'pause_time' in timer:
                        elapsed = timer['elapsed_time'] + (current_time - timer['start_time'])
                    else:
                        elapsed = current_time - timer['start_time']
                    timer['elapsed_time'] = elapsed
        
        # Aggiorna i timer nel file con lo stato attuale
        for timer_id, timer in active_timers.items():
            for i, t in enumerate(timers.get("timers", [])):
                if t.get("id") == timer_id:
                    timers["timers"][i].update({
                        'status': timer['status'],
                        'time_remaining': timer.get('time_remaining', 0),
                        'elapsed_time': timer.get('elapsed_time', 0)
                    })
                    break
        
        save_timers(timers)

# Thread per aggiornare periodicamente i timer
def timer_updater():
    while True:
        try:
            update_active_timers()
            time.sleep(0.5)  # Aggiorna ogni mezzo secondo
        except Exception as e:
            logger.error(f"Errore nel thread di aggiornamento dei timer: {str(e)}")
            time.sleep(5)  # In caso di errore, attendi un po' di più

# Avvia il thread di aggiornamento
timer_thread = threading.Thread(target=timer_updater, daemon=True)
timer_thread.start()

# API per ottenere lo stato di un timer (per OBS)
@timer.route('/api/<timer_id>/status', methods=['GET'])
def timer_status(timer_id):
    try:
        timer_data = find_timer_by_id(timer_id)
        
        if not timer_data:
            return jsonify({
                'success': False,
                'error': 'Timer non trovato'
            }), 404
        
        # Aggiorna i dati del timer
        timer_data = calculate_timer_status(timer_data)
        update_timer(timer_id, timer_data)
        
        # Prepara i dati per la risposta
        response_data = {
            'success': True,
            'id': timer_id,
            'name': timer_data['name'],
            'type': timer_data['type'],
            'status': timer_data['status'],
            'settings': timer_data['settings']
        }
        
        if timer_data['type'] == 'countdown':
            response_data['time_remaining'] = timer_data.get('time_remaining', timer_data['duration'])
            response_data['duration'] = timer_data['duration']
            
            # Aggiungi informazioni sugli avvisi
            alert_at = timer_data['settings'].get('alert_at', [])
            alerts = []
            
            for alert_time in alert_at:
                if alert_time >= response_data['time_remaining'] and alert_time < response_data['time_remaining'] + 1:
                    alerts.append(alert_time)
            
            response_data['alerts'] = alerts
        else:  # stopwatch
            response_data['elapsed_time'] = timer_data.get('elapsed_time', 0)
        
        return jsonify(response_data)
    except Exception as e:
        logger.error(f"Errore durante il recupero dello stato del timer {timer_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500 