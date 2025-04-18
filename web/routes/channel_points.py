#!/usr/bin/env python3
"""
Blueprint per la gestione dei punti canale in M4Bot.
Fornisce API e viste per gestire i punti, le ricompense e le statistiche.
"""

import json
import logging
from datetime import datetime, timedelta
from quart import (
    Blueprint, render_template, request, redirect, 
    url_for, session, jsonify, flash
)
from bot.kick_channel_points import KickChannelPoints
from utils.auth import login_required, get_twitch_user_from_session
from models.channel_points import ChannelPoints
from models.channel_points_rewards import ChannelPointsRewards
from models.channel_points_users import ChannelPointsUsers
from models.channel_points_activity import ChannelPointsActivity

# Configurazione del logger
logger = logging.getLogger('M4Bot-Web.channel_points')

# Creazione del blueprint
blueprint = Blueprint('channel_points', __name__, url_prefix='/channel_points')

# Rotte per la gestione dei punti canale
@blueprint.route('/')
@login_required
def index():
    """Renderizza la pagina principale dei punti canale."""
    twitch_user = get_twitch_user_from_session(session)
    if not twitch_user:
        return redirect(url_for('auth.logout'))
    return render_template('channel_points.html')

@blueprint.route('/rewards', methods=['GET'])
@login_required
def get_rewards():
    """Ottiene le ricompense disponibili per un canale."""
    twitch_user = get_twitch_user_from_session(session)
    if not twitch_user:
        return jsonify({'error': 'Non autorizzato'}), 401

    channel_id = twitch_user.get('id')
    rewards = ChannelPointsRewards.get_rewards_by_channel(channel_id)
    
    return jsonify({'rewards': rewards}), 200

@blueprint.route('/rewards/create', methods=['POST'])
@login_required
def create_reward():
    """Crea una nuova ricompensa."""
    twitch_user = get_twitch_user_from_session(session)
    if not twitch_user:
        return jsonify({'error': 'Non autorizzato'}), 401

    data = request.json
    channel_id = twitch_user.get('id')
    
    # Validation
    if not data or not data.get('name') or not data.get('cost'):
        return jsonify({'error': 'Dati mancanti'}), 400
    
    try:
        reward_data = {
            'channel_id': channel_id,
            'name': data.get('name'),
            'description': data.get('description', ''),
            'cost': int(data.get('cost')),
            'cooldown': int(data.get('cooldown', 0)),
            'color': data.get('color', '#9146FF'),
            'is_enabled': data.get('is_enabled', True)
        }
        
        reward_id = ChannelPointsRewards.create_reward(reward_data)
        return jsonify({'reward_id': reward_id, 'message': 'Premio creato con successo'}), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@blueprint.route('/rewards/<int:reward_id>', methods=['PUT', 'DELETE'])
@login_required
def manage_reward(reward_id):
    """Modifica o elimina una ricompensa."""
    twitch_user = get_twitch_user_from_session(session)
    if not twitch_user:
        return jsonify({'error': 'Non autorizzato'}), 401

    channel_id = twitch_user.get('id')
    
    # Verify reward belongs to channel
    reward = ChannelPointsRewards.get_reward_by_id(reward_id)
    if not reward or reward.get('channel_id') != channel_id:
        return jsonify({'error': 'Premio non trovato'}), 404
    
    if request.method == 'PUT':
        data = request.json
        
        # Validation
        if not data or not data.get('name') or not data.get('cost'):
            return jsonify({'error': 'Dati mancanti'}), 400
        
        try:
            reward_data = {
                'name': data.get('name'),
                'description': data.get('description', ''),
                'cost': int(data.get('cost')),
                'cooldown': int(data.get('cooldown', 0)),
                'color': data.get('color', '#9146FF'),
                'is_enabled': data.get('is_enabled', True)
            }
            
            ChannelPointsRewards.update_reward(reward_id, reward_data)
            return jsonify({'message': 'Premio aggiornato con successo'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    elif request.method == 'DELETE':
        try:
            ChannelPointsRewards.delete_reward(reward_id)
            return jsonify({'message': 'Premio eliminato con successo'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@blueprint.route('/users', methods=['GET'])
@login_required
def get_users():
    """Ottiene gli utenti con i loro punti."""
    twitch_user = get_twitch_user_from_session(session)
    if not twitch_user:
        return jsonify({'error': 'Non autorizzato'}), 401

    channel_id = twitch_user.get('id')
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '')
    
    users, total = ChannelPointsUsers.get_users_by_channel(channel_id, page, per_page, search)
    
    return jsonify({
        'users': users,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    }), 200

@blueprint.route('/users/modify_points', methods=['POST'])
@login_required
def modify_user_points():
    """Modifica i punti di un utente."""
    twitch_user = get_twitch_user_from_session(session)
    if not twitch_user:
        return jsonify({'error': 'Non autorizzato'}), 401

    channel_id = twitch_user.get('id')
    data = request.json
    
    # Validation
    if not data or 'action' not in data or 'amount' not in data:
        return jsonify({'error': 'Dati mancanti'}), 400
    
    try:
        action = data.get('action')
        amount = int(data.get('amount'))
        
        user = ChannelPointsUsers.get_user_by_id(data.get('user_id'), channel_id)
        if not user:
            return jsonify({'error': 'Utente non trovato'}), 404
        
        current_points = user.get('points', 0)
        new_points = current_points
        
        if action == 'add':
            new_points = current_points + amount
        elif action == 'remove':
            new_points = max(0, current_points - amount)
        elif action == 'set':
            new_points = max(0, amount)
        else:
            return jsonify({'error': 'Azione non valida'}), 400
        
        ChannelPointsUsers.update_user_points(data.get('user_id'), channel_id, new_points)
        
        # Log the activity
        activity_data = {
            'channel_id': channel_id,
            'user_id': data.get('user_id'),
            'username': user.get('username'),
            'action_type': 'manual_adjustment',
            'points': amount,
            'action': action
        }
        ChannelPointsActivity.add_activity(activity_data)
        
        return jsonify({
            'success': True, 
            'message': 'Punti aggiornati con successo',
            'old_points': current_points,
            'new_points': new_points
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@blueprint.route('/stats', methods=['GET'])
@login_required
def get_stats():
    """Ottiene le statistiche dei punti canale."""
    twitch_user = get_twitch_user_from_session(session)
    if not twitch_user:
        return jsonify({'error': 'Non autorizzato'}), 401

    channel_id = twitch_user.get('id')
    stats = ChannelPoints.get_stats(channel_id)
    
    return jsonify({'stats': stats}), 200

@blueprint.route('/settings', methods=['GET', 'PUT'])
@login_required
def manage_settings():
    """Ottiene o aggiorna le impostazioni dei punti canale."""
    twitch_user = get_twitch_user_from_session(session)
    if not twitch_user:
        return jsonify({'error': 'Non autorizzato'}), 401

    channel_id = twitch_user.get('id')
    
    if request.method == 'GET':
        settings = ChannelPoints.get_settings(channel_id)
        return jsonify({'settings': settings}), 200
    
    elif request.method == 'PUT':
        data = request.json
        
        # Validation
        if not data:
            return jsonify({'error': 'Dati mancanti'}), 400
        
        try:
            settings_data = {
                'points_name': data.get('points_name', 'Punti'),
                'earning_rate': int(data.get('earning_rate', 10)),
                'subscriber_multiplier': float(data.get('subscriber_multiplier', 2.0)),
                'vip_multiplier': float(data.get('vip_multiplier', 1.5)),
                'mod_multiplier': float(data.get('mod_multiplier', 1.5)),
                'is_enabled': data.get('is_enabled', True)
            }
            
            ChannelPoints.update_settings(channel_id, settings_data)
            return jsonify({'message': 'Impostazioni aggiornate con successo'}), 200
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@blueprint.route('/leaderboard', methods=['GET'])
@login_required
def get_leaderboard():
    """Ottiene la classifica degli utenti con più punti."""
    twitch_user = get_twitch_user_from_session(session)
    if not twitch_user:
        return jsonify({'error': 'Non autorizzato'}), 401

    channel_id = twitch_user.get('id')
    limit = request.args.get('limit', 10)
    
    try:
        limit = int(limit)
        if limit <= 0 or limit > 100:
            limit = 10
    except ValueError:
        limit = 10
    
    # Recupera la classifica dal database
    leaderboard = ChannelPoints.get_leaderboard(channel_id, limit)
    
    return jsonify({'leaderboard': leaderboard}), 200

@blueprint.route('/history', methods=['GET'])
@login_required
def get_history():
    """Ottiene la cronologia delle attività relative ai punti canale."""
    twitch_user = get_twitch_user_from_session(session)
    if not twitch_user:
        return jsonify({'error': 'Non autorizzato'}), 401

    channel_id = twitch_user.get('id')
    limit = request.args.get('limit', 20)
    
    try:
        limit = int(limit)
        if limit <= 0 or limit > 100:
            limit = 20
    except ValueError:
        limit = 20
    
    # Recupera la cronologia dal database
    history = ChannelPoints.get_history(channel_id, limit)
    
    return jsonify({'history': history}), 200

@blueprint.route('/api/activity', methods=['GET'])
@login_required
def get_activity():
    """Ottiene l'attività recente dei punti canale."""
    twitch_user = get_twitch_user_from_session(session)
    if not twitch_user:
        return jsonify({'error': 'Non autorizzato'}), 401

    channel_id = twitch_user.get('id')
    
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    activity, total = ChannelPointsActivity.get_activity_by_channel(channel_id, page, per_page)
    
    return jsonify({
        'activity': activity,
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': (total + per_page - 1) // per_page
    }), 200 