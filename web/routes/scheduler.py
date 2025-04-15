import os
import json
import logging
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, current_app
from plugins.content_scheduler import ContentScheduler

# Inizializzazione del Blueprint
scheduler_bp = Blueprint('scheduler', __name__)

# Configurazione del logger
logger = logging.getLogger(__name__)

# Istanza del content scheduler
scheduler = None

def get_scheduler():
    """
    Ottiene l'istanza del ContentScheduler, inizializzandola se necessario.
    """
    global scheduler
    if scheduler is None:
        scheduler = ContentScheduler()
    return scheduler

@scheduler_bp.route('/scheduler')
def scheduler_page():
    """
    Render della pagina di gestione della programmazione dei contenuti.
    """
    return render_template('content_scheduler.html', page_title="Programmazione Contenuti")

@scheduler_bp.route('/api/scheduler/items')
def list_scheduled_items():
    """
    Elenca tutti gli elementi programmati.
    """
    try:
        items = get_scheduler().get_scheduled_items()
        return jsonify({"success": True, "items": items})
    except Exception as e:
        logger.error(f"Error retrieving scheduled items: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scheduler_bp.route('/api/scheduler/items/<item_id>')
def get_scheduled_item(item_id):
    """
    Ottiene i dettagli di un elemento programmato specifico.
    """
    try:
        item = get_scheduler().get_item_by_id(item_id)
        if item:
            return jsonify({"success": True, "item": item})
        else:
            return jsonify({"success": False, "message": "Item not found"}), 404
    except Exception as e:
        logger.error(f"Error retrieving scheduled item {item_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scheduler_bp.route('/api/scheduler/items', methods=['POST'])
def create_scheduled_item():
    """
    Crea un nuovo elemento programmato.
    """
    try:
        data = request.json
        
        # Validazione dei dati
        required_fields = ['title', 'type', 'platform', 'content', 'scheduled_time']
        for field in required_fields:
            if field not in data:
                return jsonify({"success": False, "message": f"Missing required field: {field}"}), 400
        
        # Aggiunta dell'elemento programmato
        item_id = get_scheduler().add_scheduled_item(
            title=data['title'],
            item_type=data['type'],
            platform=data['platform'],
            content=data['content'],
            scheduled_time=data['scheduled_time'],
            repeat_info=data.get('repeat_info', None)
        )
        
        return jsonify({"success": True, "item_id": item_id})
    except Exception as e:
        logger.error(f"Error creating scheduled item: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scheduler_bp.route('/api/scheduler/items/<item_id>', methods=['PUT'])
def update_scheduled_item(item_id):
    """
    Aggiorna un elemento programmato esistente.
    """
    try:
        data = request.json
        
        # Validazione dei dati
        required_fields = ['title', 'type', 'platform', 'content', 'scheduled_time']
        for field in required_fields:
            if field not in data:
                return jsonify({"success": False, "message": f"Missing required field: {field}"}), 400
        
        # Aggiornamento dell'elemento programmato
        success = get_scheduler().update_scheduled_item(
            item_id=item_id,
            title=data['title'],
            item_type=data['type'],
            platform=data['platform'],
            content=data['content'],
            scheduled_time=data['scheduled_time'],
            repeat_info=data.get('repeat_info', None)
        )
        
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "message": "Item not found"}), 404
    except Exception as e:
        logger.error(f"Error updating scheduled item {item_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scheduler_bp.route('/api/scheduler/items/<item_id>', methods=['DELETE'])
def delete_scheduled_item(item_id):
    """
    Elimina un elemento programmato.
    """
    try:
        success = get_scheduler().remove_scheduled_item(item_id)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "message": "Item not found"}), 404
    except Exception as e:
        logger.error(f"Error deleting scheduled item {item_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scheduler_bp.route('/api/scheduler/items/<item_id>/execute', methods=['POST'])
def execute_scheduled_item(item_id):
    """
    Esegue immediatamente un elemento programmato.
    """
    try:
        success, message = get_scheduler().execute_item_now(item_id)
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "message": message}), 400
    except Exception as e:
        logger.error(f"Error executing scheduled item {item_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scheduler_bp.route('/api/scheduler/history')
def get_scheduler_history():
    """
    Ottiene lo storico delle esecuzioni programmate.
    """
    try:
        history = get_scheduler().get_execution_history()
        return jsonify({"success": True, "items": history})
    except Exception as e:
        logger.error(f"Error retrieving scheduler history: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scheduler_bp.route('/api/scheduler/history/<item_id>')
def get_history_item(item_id):
    """
    Ottiene i dettagli di un elemento dello storico specifico.
    """
    try:
        item = get_scheduler().get_history_item(item_id)
        if item:
            return jsonify({"success": True, "item": item})
        else:
            return jsonify({"success": False, "message": "History item not found"}), 404
    except Exception as e:
        logger.error(f"Error retrieving history item {item_id}: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scheduler_bp.route('/api/scheduler/status')
def get_scheduler_status():
    """
    Ottiene lo stato attuale del scheduler.
    """
    try:
        status = get_scheduler().get_status()
        return jsonify({"success": True, "status": status})
    except Exception as e:
        logger.error(f"Error retrieving scheduler status: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

@scheduler_bp.route('/api/scheduler/status', methods=['POST'])
def set_scheduler_status():
    """
    Imposta lo stato del scheduler (attivo/inattivo).
    """
    try:
        data = request.json
        if 'active' not in data:
            return jsonify({"success": False, "message": "Missing 'active' field"}), 400
        
        active = data['active']
        if active:
            get_scheduler().start()
        else:
            get_scheduler().stop()
        
        return jsonify({"success": True, "active": active})
    except Exception as e:
        logger.error(f"Error setting scheduler status: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500

def register_routes(app):
    """
    Registra tutte le rotte del content scheduler nell'app Flask.
    """
    app.register_blueprint(scheduler_bp)
    logger.info("Content scheduler routes registered") 