import os
import json
import time
import uuid
import logging
from flask import Blueprint, request, jsonify, render_template, current_app
from datetime import datetime, timedelta

# Inizializzazione del Blueprint e del logger
polls = Blueprint('polls', __name__, url_prefix='/api/polls')
logger = logging.getLogger(__name__)

# Percorso del file per salvare i sondaggi
POLLS_DIRECTORY = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'polls')
POLLS_FILE = os.path.join(POLLS_DIRECTORY, 'polls.json')

# Assicurati che la directory esista
os.makedirs(POLLS_DIRECTORY, exist_ok=True)

# Funzione per caricare i sondaggi
def load_polls():
    try:
        if os.path.exists(POLLS_FILE):
            with open(POLLS_FILE, 'r', encoding='utf-8') as file:
                return json.load(file)
        else:
            return {"polls": []}
    except Exception as e:
        logger.error(f"Errore durante il caricamento dei sondaggi: {str(e)}")
        return {"polls": []}

# Funzione per salvare i sondaggi
def save_polls(polls_data):
    try:
        with open(POLLS_FILE, 'w', encoding='utf-8') as file:
            json.dump(polls_data, file, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"Errore durante il salvataggio dei sondaggi: {str(e)}")
        return False

# Funzione per trovare un sondaggio per ID
def find_poll_by_id(poll_id):
    polls_data = load_polls()
    for poll in polls_data.get("polls", []):
        if poll.get("id") == poll_id:
            return poll
    return None

# Funzione per aggiornare un sondaggio specifico
def update_poll(poll_id, updated_poll):
    polls_data = load_polls()
    for i, poll in enumerate(polls_data.get("polls", [])):
        if poll.get("id") == poll_id:
            polls_data["polls"][i] = updated_poll
            save_polls(polls_data)
            return True
    return False

# Funzione per calcolare lo stato attuale di un sondaggio
def calculate_poll_status(poll):
    current_time = time.time()
    
    # Se il sondaggio non è ancora iniziato
    if poll.get("start_time", 0) > current_time:
        poll["status"] = "scheduled"
        poll["time_remaining"] = poll.get("start_time", 0) - current_time
        return poll
    
    # Se il sondaggio è attivo
    end_time = poll.get("start_time", 0) + poll.get("duration", 0)
    if current_time < end_time:
        poll["status"] = "active"
        poll["time_remaining"] = end_time - current_time
        return poll
    
    # Se il sondaggio è terminato
    poll["status"] = "completed"
    poll["time_remaining"] = 0
    return poll

# Pagina di gestione dei sondaggi
@polls.route('/page', methods=['GET'])
def polls_manager_page():
    return render_template('polls_manager.html')

# Endpoint per ottenere il sovrapposizione OBS per un sondaggio
@polls.route('/obs/<poll_id>', methods=['GET'])
def obs_poll_overlay(poll_id):
    poll = find_poll_by_id(poll_id)
    if not poll:
        return render_template('error.html', message="Sondaggio non trovato"), 404
    
    return render_template('obs_poll.html', poll_id=poll_id)

# Endpoint per creare un nuovo sondaggio
@polls.route('/', methods=['POST'])
def create_poll():
    try:
        data = request.json
        
        # Validazione dei dati
        if not data.get("question"):
            return jsonify({"success": False, "error": "La domanda è obbligatoria"}), 400
            
        if not data.get("options") or len(data.get("options", [])) < 2:
            return jsonify({"success": False, "error": "Sono necessarie almeno due opzioni"}), 400
        
        # Generazione di un nuovo ID univoco
        poll_id = str(uuid.uuid4())
        
        # Formattazione delle opzioni
        options = []
        for option in data.get("options", []):
            options.append({
                "id": str(uuid.uuid4()),
                "text": option.get("text", ""),
                "votes": 0
            })
            
        # Creazione del nuovo sondaggio
        current_time = time.time()
        new_poll = {
            "id": poll_id,
            "question": data.get("question", ""),
            "options": options,
            "platforms": data.get("platforms", []),
            "created_at": current_time,
            "updated_at": current_time,
            "start_time": data.get("start_time", current_time),
            "duration": data.get("duration", 300),  # Durata predefinita: 5 minuti
            "total_votes": 0,
            "status": "scheduled" if data.get("start_time", current_time) > current_time else "active",
            "creator_id": data.get("creator_id"),
            "settings": data.get("settings", {})
        }
        
        # Aggiornamento dello stato in base ai tempi
        new_poll = calculate_poll_status(new_poll)
        
        # Salvataggio del sondaggio
        polls_data = load_polls()
        polls_data.setdefault("polls", []).append(new_poll)
        
        if save_polls(polls_data):
            # Qui potremmo aggiungere la logica per inviare il sondaggio alle piattaforme
            return jsonify({
                "success": True,
                "poll": new_poll
            })
        else:
            return jsonify({"success": False, "error": "Errore durante il salvataggio del sondaggio"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante la creazione del sondaggio: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per ottenere un sondaggio specifico
@polls.route('/<poll_id>', methods=['GET'])
def get_poll(poll_id):
    poll = find_poll_by_id(poll_id)
    
    if not poll:
        return jsonify({"success": False, "error": "Sondaggio non trovato"}), 404
    
    # Aggiorna lo stato del sondaggio
    poll = calculate_poll_status(poll)
    update_poll(poll_id, poll)
    
    return jsonify({"success": True, "poll": poll})

# Endpoint per gli aggiornamenti live di un sondaggio (per OBS)
@polls.route('/<poll_id>/live', methods=['GET'])
def get_poll_live(poll_id):
    poll = find_poll_by_id(poll_id)
    
    if not poll:
        return jsonify({"success": False, "error": "Sondaggio non trovato"}), 404
    
    # Aggiorna lo stato del sondaggio
    poll = calculate_poll_status(poll)
    update_poll(poll_id, poll)
    
    # Semplifica i dati per l'overlay OBS
    live_poll = {
        "question": poll.get("question", ""),
        "options": poll.get("options", []),
        "total_votes": poll.get("total_votes", 0),
        "status": poll.get("status", ""),
        "time_remaining": poll.get("time_remaining", 0)
    }
    
    return jsonify({"success": True, "poll": live_poll})

# Endpoint per aggiornare un sondaggio
@polls.route('/<poll_id>', methods=['PUT', 'PATCH'])
def update_poll_endpoint(poll_id):
    try:
        poll = find_poll_by_id(poll_id)
        
        if not poll:
            return jsonify({"success": False, "error": "Sondaggio non trovato"}), 404
        
        data = request.json
        
        # Aggiorna i campi consentiti
        for field in ["question", "options", "platforms", "duration", "status", "settings"]:
            if field in data:
                if field == "options":
                    # Mantieni i conteggi dei voti per le opzioni esistenti
                    existing_options = {opt.get("id"): opt.get("votes", 0) for opt in poll.get("options", [])}
                    
                    for option in data["options"]:
                        option_id = option.get("id")
                        if option_id in existing_options and "votes" not in option:
                            option["votes"] = existing_options[option_id]
                        elif "votes" not in option:
                            option["votes"] = 0
                
                poll[field] = data[field]
        
        # Aggiorna i timestamp
        poll["updated_at"] = time.time()
        
        # Aggiorna lo stato
        poll = calculate_poll_status(poll)
        
        # Salva le modifiche
        if update_poll(poll_id, poll):
            return jsonify({"success": True, "poll": poll})
        else:
            return jsonify({"success": False, "error": "Errore durante l'aggiornamento del sondaggio"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante l'aggiornamento del sondaggio: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per l'invio di un voto
@polls.route('/<poll_id>/vote', methods=['POST'])
def submit_vote(poll_id):
    try:
        poll = find_poll_by_id(poll_id)
        
        if not poll:
            return jsonify({"success": False, "error": "Sondaggio non trovato"}), 404
        
        # Verifica se il sondaggio è attivo
        poll = calculate_poll_status(poll)
        if poll.get("status") != "active":
            return jsonify({"success": False, "error": "Il sondaggio non è attivo"}), 400
        
        data = request.json
        option_id = data.get("option_id")
        user_id = data.get("user_id")
        platform = data.get("platform")
        
        if not option_id:
            return jsonify({"success": False, "error": "ID dell'opzione non fornito"}), 400
        
        # Cerca l'opzione selezionata
        option_found = False
        for option in poll.get("options", []):
            if option.get("id") == option_id:
                option["votes"] = option.get("votes", 0) + 1
                option_found = True
                break
        
        if not option_found:
            return jsonify({"success": False, "error": "Opzione non trovata"}), 404
        
        # Incrementa il conteggio totale dei voti
        poll["total_votes"] = poll.get("total_votes", 0) + 1
        
        # Registra il voto dell'utente (se fornito l'ID utente)
        if user_id:
            poll.setdefault("votes", []).append({
                "user_id": user_id,
                "option_id": option_id,
                "platform": platform,
                "timestamp": time.time()
            })
        
        # Salva le modifiche
        if update_poll(poll_id, poll):
            return jsonify({"success": True, "poll": poll})
        else:
            return jsonify({"success": False, "error": "Errore durante il salvataggio del voto"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante l'invio del voto: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per terminare un sondaggio
@polls.route('/<poll_id>/end', methods=['POST'])
def end_poll(poll_id):
    try:
        poll = find_poll_by_id(poll_id)
        
        if not poll:
            return jsonify({"success": False, "error": "Sondaggio non trovato"}), 404
        
        # Imposta lo stato come completato
        poll["status"] = "completed"
        poll["time_remaining"] = 0
        poll["updated_at"] = time.time()
        
        # Salva le modifiche
        if update_poll(poll_id, poll):
            return jsonify({"success": True, "poll": poll})
        else:
            return jsonify({"success": False, "error": "Errore durante la terminazione del sondaggio"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante la terminazione del sondaggio: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per eliminare un sondaggio
@polls.route('/<poll_id>', methods=['DELETE'])
def delete_poll(poll_id):
    try:
        polls_data = load_polls()
        
        # Cerca il sondaggio da eliminare
        found = False
        for i, poll in enumerate(polls_data.get("polls", [])):
            if poll.get("id") == poll_id:
                del polls_data["polls"][i]
                found = True
                break
                
        if not found:
            return jsonify({"success": False, "error": "Sondaggio non trovato"}), 404
        
        # Salva le modifiche
        if save_polls(polls_data):
            return jsonify({"success": True, "message": "Sondaggio eliminato con successo"})
        else:
            return jsonify({"success": False, "error": "Errore durante l'eliminazione del sondaggio"}), 500
            
    except Exception as e:
        logger.error(f"Errore durante l'eliminazione del sondaggio: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

# Endpoint per elencare tutti i sondaggi
@polls.route('/', methods=['GET'])
def list_polls():
    try:
        polls_data = load_polls()
        
        # Aggiorna lo stato di ogni sondaggio
        for poll in polls_data.get("polls", []):
            calculate_poll_status(poll)
            
        # Filtra sondaggi in base ai parametri di query
        status = request.args.get('status')
        platform = request.args.get('platform')
        limit = request.args.get('limit', type=int)
        
        filtered_polls = polls_data.get("polls", [])
        
        if status:
            filtered_polls = [p for p in filtered_polls if p.get("status") == status]
            
        if platform:
            filtered_polls = [p for p in filtered_polls if platform in p.get("platforms", [])]
            
        # Ordina per data di creazione (più recente prima)
        filtered_polls.sort(key=lambda x: x.get("created_at", 0), reverse=True)
        
        # Applica il limite se specificato
        if limit and limit > 0:
            filtered_polls = filtered_polls[:limit]
            
        return jsonify({
            "success": True,
            "polls": filtered_polls,
            "total": len(filtered_polls)
        })
            
    except Exception as e:
        logger.error(f"Errore durante l'elenco dei sondaggi: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500