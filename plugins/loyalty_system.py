"""
Plugin per il sistema di punti fedeltà e livelli degli utenti
"""

import os
import json
import logging
import asyncio
import time
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request, render_template, current_app

# Logger
logger = logging.getLogger(__name__)

# Path per i file del sistema di fedeltà
LOYALTY_DIR = "data/loyalty"
USERS_FILE = os.path.join(LOYALTY_DIR, "users.json")
LEVELS_FILE = os.path.join(LOYALTY_DIR, "levels.json")
REWARDS_FILE = os.path.join(LOYALTY_DIR, "rewards.json")
LOYALTY_CONFIG_FILE = os.path.join(LOYALTY_DIR, "config.json")

# Blueprint
loyalty_blueprint = Blueprint('loyalty_system', __name__)

class LoyaltySystem:
    """Gestore del sistema di fedeltà"""
    
    def __init__(self, app):
        """
        Inizializza il gestore del sistema di fedeltà
        
        Args:
            app: L'applicazione Flask/Quart
        """
        self.app = app
        self.users = {}
        self.levels = []
        self.rewards = []
        self.config = {}
        self.update_task = None
        self.last_housekeeping = 0
        
        # Crea le directory necessarie
        os.makedirs(LOYALTY_DIR, exist_ok=True)
        
        # Carica i dati salvati
        self._load_users()
        self._load_levels()
        self._load_rewards()
        self._load_config()
        
        # Avvia il task di aggiornamento
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.update_task = asyncio.create_task(self._update_loop())
        
        logger.info("Sistema di fedeltà inizializzato")
    
    def _load_users(self):
        """Carica gli utenti dal file"""
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, 'r') as f:
                    self.users = json.load(f)
                logger.info(f"Caricati {len(self.users)} utenti")
            except Exception as e:
                logger.error(f"Errore nel caricamento degli utenti: {e}")
                self.users = {}
        else:
            self.users = {}
    
    def _save_users(self):
        """Salva gli utenti nel file"""
        try:
            with open(USERS_FILE, 'w') as f:
                json.dump(self.users, f, indent=2)
            logger.debug("Utenti salvati")
        except Exception as e:
            logger.error(f"Errore nel salvataggio degli utenti: {e}")
    
    def _load_levels(self):
        """Carica i livelli dal file"""
        if os.path.exists(LEVELS_FILE):
            try:
                with open(LEVELS_FILE, 'r') as f:
                    self.levels = json.load(f)
                logger.info(f"Caricati {len(self.levels)} livelli")
            except Exception as e:
                logger.error(f"Errore nel caricamento dei livelli: {e}")
                self._init_default_levels()
        else:
            self._init_default_levels()
    
    def _init_default_levels(self):
        """Inizializza i livelli predefiniti"""
        self.levels = [
            {
                "id": 1,
                "name": "Novizio",
                "points_required": 0,
                "color": "#AAAAAA",
                "benefits": []
            },
            {
                "id": 2,
                "name": "Fan",
                "points_required": 100,
                "color": "#66BB6A",
                "benefits": ["chat_emotes"]
            },
            {
                "id": 3,
                "name": "Supporter",
                "points_required": 500,
                "color": "#42A5F5",
                "benefits": ["chat_emotes", "priority_responses"]
            },
            {
                "id": 4,
                "name": "Fedele",
                "points_required": 1000,
                "color": "#FF7043",
                "benefits": ["chat_emotes", "priority_responses", "exclusive_content"]
            },
            {
                "id": 5,
                "name": "VIP",
                "points_required": 5000,
                "color": "#AB47BC",
                "benefits": ["chat_emotes", "priority_responses", "exclusive_content", "special_events"]
            }
        ]
        self._save_levels()
    
    def _save_levels(self):
        """Salva i livelli nel file"""
        try:
            with open(LEVELS_FILE, 'w') as f:
                json.dump(self.levels, f, indent=2)
            logger.debug("Livelli salvati")
        except Exception as e:
            logger.error(f"Errore nel salvataggio dei livelli: {e}")
    
    def _load_rewards(self):
        """Carica le ricompense dal file"""
        if os.path.exists(REWARDS_FILE):
            try:
                with open(REWARDS_FILE, 'r') as f:
                    self.rewards = json.load(f)
                logger.info(f"Caricate {len(self.rewards)} ricompense")
            except Exception as e:
                logger.error(f"Errore nel caricamento delle ricompense: {e}")
                self._init_default_rewards()
        else:
            self._init_default_rewards()
    
    def _init_default_rewards(self):
        """Inizializza le ricompense predefinite"""
        self.rewards = [
            {
                "id": "special_emote",
                "name": "Emoticon Speciale",
                "description": "Sblocca un'emoticon speciale da usare in chat",
                "cost": 100,
                "type": "chat_emote",
                "enabled": True
            },
            {
                "id": "custom_title",
                "name": "Titolo Personalizzato",
                "description": "Ottieni un titolo personalizzato in chat",
                "cost": 250,
                "type": "chat_title",
                "enabled": True
            },
            {
                "id": "shoutout",
                "name": "Shoutout in Diretta",
                "description": "Ricevi uno shoutout durante la prossima diretta",
                "cost": 500,
                "type": "one_time",
                "enabled": True
            },
            {
                "id": "exclusive_content",
                "name": "Contenuto Esclusivo",
                "description": "Accesso a contenuti esclusivi per una settimana",
                "cost": 1000,
                "type": "temporary_access",
                "duration": 7,  # giorni
                "enabled": True
            }
        ]
        self._save_rewards()
    
    def _save_rewards(self):
        """Salva le ricompense nel file"""
        try:
            with open(REWARDS_FILE, 'w') as f:
                json.dump(self.rewards, f, indent=2)
            logger.debug("Ricompense salvate")
        except Exception as e:
            logger.error(f"Errore nel salvataggio delle ricompense: {e}")
    
    def _load_config(self):
        """Carica la configurazione dal file"""
        if os.path.exists(LOYALTY_CONFIG_FILE):
            try:
                with open(LOYALTY_CONFIG_FILE, 'r') as f:
                    self.config = json.load(f)
                logger.info("Configurazione del sistema di fedeltà caricata")
            except Exception as e:
                logger.error(f"Errore nel caricamento della configurazione: {e}")
                self.config = self._get_default_config()
        else:
            self.config = self._get_default_config()
            self._save_config()
    
    def _get_default_config(self):
        """Restituisce la configurazione predefinita"""
        return {
            "points_per_message": 1,
            "points_per_minute_watching": 0.5,
            "points_multipliers": {
                "subscriber": 2,
                "follower": 1.2
            },
            "platforms": {
                "youtube": True,
                "kick": True,
                "telegram": True,
                "whatsapp": True
            },
            "housekeeping_interval": 3600,  # 1 ora
            "inactive_user_days": 30,  # Giorni di inattività prima della pulizia
            "enable_level_roles": True,
            "enable_rewards": True,
            "announce_level_ups": True,
            "announce_rewards": True
        }
    
    def _save_config(self):
        """Salva la configurazione nel file"""
        try:
            with open(LOYALTY_CONFIG_FILE, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.debug("Configurazione del sistema di fedeltà salvata")
        except Exception as e:
            logger.error(f"Errore nel salvataggio della configurazione: {e}")
    
    async def _update_loop(self):
        """Loop di aggiornamento del sistema di fedeltà"""
        try:
            while True:
                # Esegui housekeeping se necessario
                now = time.time()
                if now - self.last_housekeeping > self.config.get("housekeeping_interval", 3600):
                    await self._do_housekeeping()
                    self.last_housekeeping = now
                
                # Attendi 5 minuti prima del prossimo controllo
                await asyncio.sleep(300)
        except asyncio.CancelledError:
            logger.info("Task di aggiornamento del sistema di fedeltà interrotto")
            raise
        except Exception as e:
            logger.error(f"Errore nel loop di aggiornamento del sistema di fedeltà: {e}")
    
    async def _do_housekeeping(self):
        """Esegue operazioni di manutenzione periodica"""
        try:
            # Pulizia utenti inattivi (se configurata)
            if self.config.get("cleanup_inactive_users", False):
                await self._cleanup_inactive_users()
            
            # Verifica ricompense scadute
            await self._check_expired_rewards()
            
            # Salva gli utenti
            self._save_users()
        except Exception as e:
            logger.error(f"Errore nell'housekeeping: {e}")
    
    async def _cleanup_inactive_users(self):
        """Rimuove gli utenti inattivi"""
        try:
            # Calcola il timestamp di cutoff
            now = time.time()
            inactive_days = self.config.get("inactive_user_days", 30)
            cutoff_time = now - (inactive_days * 24 * 60 * 60)
            
            # Trova gli utenti inattivi
            inactive_users = []
            for user_id, user in self.users.items():
                last_active = user.get("last_active", 0)
                if last_active < cutoff_time:
                    inactive_users.append(user_id)
            
            # Rimuovi gli utenti inattivi
            for user_id in inactive_users:
                del self.users[user_id]
            
            if inactive_users:
                logger.info(f"Rimossi {len(inactive_users)} utenti inattivi")
        except Exception as e:
            logger.error(f"Errore nella pulizia degli utenti inattivi: {e}")
    
    async def _check_expired_rewards(self):
        """Verifica le ricompense scadute degli utenti"""
        try:
            now = time.time()
            
            for user_id, user in self.users.items():
                active_rewards = user.get("active_rewards", [])
                expired_rewards = []
                
                # Verifica ogni ricompensa attiva
                for reward in active_rewards:
                    # Se la ricompensa ha una scadenza ed è scaduta
                    if reward.get("expires_at", 0) > 0 and reward["expires_at"] < now:
                        expired_rewards.append(reward)
                
                # Rimuovi le ricompense scadute
                if expired_rewards:
                    user["active_rewards"] = [r for r in active_rewards if r not in expired_rewards]
                    user["expired_rewards"] = user.get("expired_rewards", []) + expired_rewards
                    logger.debug(f"Rimosse {len(expired_rewards)} ricompense scadute per l'utente {user_id}")
        except Exception as e:
            logger.error(f"Errore nella verifica delle ricompense scadute: {e}")
    
    async def process_message(self, message: Dict[str, Any]) -> bool:
        """
        Processa un messaggio per il sistema di fedeltà
        
        Args:
            message: Il messaggio ricevuto
            
        Returns:
            bool: True se il messaggio è stato processato, False altrimenti
        """
        try:
            # Verifica se la piattaforma è abilitata
            platform = message.get("platform", "unknown")
            if not self.config.get("platforms", {}).get(platform, False):
                return False
            
            # Estrai le informazioni dell'utente
            author = message.get("author", {})
            user_id = f"{platform}_{author.get('id', '')}"
            username = author.get("username", "unknown")
            display_name = author.get("display_name", username)
            
            # Ottieni o crea l'utente
            user = self.users.get(user_id)
            if not user:
                user = {
                    "id": user_id,
                    "platform": platform,
                    "platform_id": author.get("id", ""),
                    "username": username,
                    "display_name": display_name,
                    "points": 0,
                    "level": 1,
                    "created_at": time.time(),
                    "last_active": time.time(),
                    "activity": {
                        "messages": 0,
                        "watch_time": 0
                    },
                    "active_rewards": [],
                    "redeemed_rewards": []
                }
                self.users[user_id] = user
            
            # Aggiorna il timestamp di ultima attività
            user["last_active"] = time.time()
            
            # Aggiorna il conteggio dei messaggi
            user["activity"]["messages"] = user["activity"].get("messages", 0) + 1
            
            # Calcola i punti da assegnare
            points_per_message = self.config.get("points_per_message", 1)
            
            # Applica i moltiplicatori
            multiplier = 1.0
            if author.get("is_subscriber", False) and "subscriber" in self.config.get("points_multipliers", {}):
                multiplier = self.config.get("points_multipliers", {}).get("subscriber", 1.0)
            elif author.get("is_follower", False) and "follower" in self.config.get("points_multipliers", {}):
                multiplier = self.config.get("points_multipliers", {}).get("follower", 1.0)
            
            # Assegna i punti
            points_earned = points_per_message * multiplier
            await self.add_points(user_id, points_earned)
            
            return True
        except Exception as e:
            logger.error(f"Errore nel processamento del messaggio per il sistema di fedeltà: {e}")
            return False
    
    async def add_points(self, user_id: str, points: float) -> Dict[str, Any]:
        """
        Aggiunge punti a un utente
        
        Args:
            user_id: ID dell'utente
            points: Punti da aggiungere
            
        Returns:
            Dict[str, Any]: Risultato dell'operazione
        """
        try:
            # Verifica che l'utente esista
            if user_id not in self.users:
                return {"success": False, "error": "Utente non trovato"}
            
            # Ottieni l'utente
            user = self.users[user_id]
            
            # Aggiorna i punti
            old_points = user.get("points", 0)
            user["points"] = old_points + points
            
            # Verifica se l'utente ha raggiunto un nuovo livello
            old_level = user.get("level", 1)
            new_level = self._calculate_level(user["points"])
            
            # Se l'utente è salito di livello
            level_up = False
            if new_level > old_level:
                user["level"] = new_level
                level_up = True
                
                # Annuncia il passaggio di livello se configurato
                if self.config.get("announce_level_ups", True):
                    await self._announce_level_up(user, old_level, new_level)
            
            # Salva gli utenti
            self._save_users()
            
            return {
                "success": True,
                "user_id": user_id,
                "old_points": old_points,
                "new_points": user["points"],
                "points_added": points,
                "old_level": old_level,
                "new_level": new_level,
                "level_up": level_up
            }
        except Exception as e:
            logger.error(f"Errore nell'aggiunta di punti: {e}")
            return {"success": False, "error": str(e)}
    
    def _calculate_level(self, points: float) -> int:
        """
        Calcola il livello in base ai punti
        
        Args:
            points: Punti dell'utente
            
        Returns:
            int: Livello dell'utente
        """
        # Ordina i livelli per punti richiesti (decrescente)
        sorted_levels = sorted(self.levels, key=lambda x: x.get("points_required", 0), reverse=True)
        
        # Trova il primo livello che l'utente ha raggiunto
        for level in sorted_levels:
            if points >= level.get("points_required", 0):
                return level.get("id", 1)
        
        # Livello predefinito (1)
        return 1
    
    async def _announce_level_up(self, user: Dict[str, Any], old_level: int, new_level: int):
        """
        Annuncia il passaggio di livello di un utente
        
        Args:
            user: Utente che è salito di livello
            old_level: Vecchio livello
            new_level: Nuovo livello
        """
        try:
            # Ottieni i dettagli dei livelli
            old_level_info = next((level for level in self.levels if level.get("id") == old_level), {"name": f"Livello {old_level}"})
            new_level_info = next((level for level in self.levels if level.get("id") == new_level), {"name": f"Livello {new_level}"})
            
            # Prepara il messaggio
            message = f"🏆 {user.get('display_name')} è salito al livello {new_level_info.get('name')}! 🎉"
            
            # Invia il messaggio sulle piattaforme
            platform = user.get("platform")
            
            if platform == "youtube" and hasattr(self.app, "youtube_connector"):
                await self.app.youtube_connector.send_chat_message(message)
            
            elif platform == "kick" and hasattr(self.app, "kick_connector"):
                await self.app.kick_connector.send_chat_message(message)
            
            elif platform == "telegram" and hasattr(self.app, "telegram_connector"):
                for chat_id in self.app.config.get('TELEGRAM_CHAT_IDS', []):
                    await self.app.telegram_connector.send_message(chat_id, message)
            
            elif platform == "whatsapp" and hasattr(self.app, "whatsapp_connector"):
                # Per WhatsApp, non inviamo annunci pubblici ai numeri privati
                pass
        except Exception as e:
            logger.error(f"Errore nell'annuncio del passaggio di livello: {e}")
    
    async def redeem_reward(self, user_id: str, reward_id: str) -> Dict[str, Any]:
        """
        Riscatta una ricompensa per un utente
        
        Args:
            user_id: ID dell'utente
            reward_id: ID della ricompensa
            
        Returns:
            Dict[str, Any]: Risultato dell'operazione
        """
        try:
            # Verifica che l'utente esista
            if user_id not in self.users:
                return {"success": False, "error": "Utente non trovato"}
            
            # Verifica che la ricompensa esista
            reward = next((r for r in self.rewards if r.get("id") == reward_id), None)
            if not reward:
                return {"success": False, "error": "Ricompensa non trovata"}
            
            # Verifica che la ricompensa sia abilitata
            if not reward.get("enabled", True):
                return {"success": False, "error": "Ricompensa non disponibile"}
            
            # Ottieni l'utente
            user = self.users[user_id]
            
            # Verifica che l'utente abbia abbastanza punti
            cost = reward.get("cost", 0)
            if user.get("points", 0) < cost:
                return {"success": False, "error": "Punti insufficienti"}
            
            # Crea la ricompensa attiva
            active_reward = {
                "id": reward_id,
                "name": reward.get("name"),
                "redeemed_at": time.time(),
                "expires_at": 0
            }
            
            # Se la ricompensa ha una durata, calcola la scadenza
            if reward.get("type") == "temporary_access" and reward.get("duration"):
                duration_days = reward.get("duration", 0)
                active_reward["expires_at"] = time.time() + (duration_days * 24 * 60 * 60)
            
            # Aggiorna l'utente
            user["points"] -= cost
            user["active_rewards"] = user.get("active_rewards", []) + [active_reward]
            user["redeemed_rewards"] = user.get("redeemed_rewards", []) + [{
                "id": reward_id,
                "name": reward.get("name"),
                "cost": cost,
                "redeemed_at": time.time()
            }]
            
            # Salva gli utenti
            self._save_users()
            
            # Annuncia la ricompensa se configurato
            if self.config.get("announce_rewards", True):
                await self._announce_reward(user, reward)
            
            return {
                "success": True,
                "user_id": user_id,
                "reward_id": reward_id,
                "cost": cost,
                "points_remaining": user["points"],
                "active_reward": active_reward
            }
        except Exception as e:
            logger.error(f"Errore nel riscatto della ricompensa: {e}")
            return {"success": False, "error": str(e)}
    
    async def _announce_reward(self, user: Dict[str, Any], reward: Dict[str, Any]):
        """
        Annuncia il riscatto di una ricompensa
        
        Args:
            user: Utente che ha riscattato la ricompensa
            reward: Ricompensa riscattata
        """
        try:
            # Prepara il messaggio
            message = f"🎁 {user.get('display_name')} ha riscattato la ricompensa: {reward.get('name')}!"
            
            # Invia il messaggio sulle piattaforme
            platform = user.get("platform")
            
            if platform == "youtube" and hasattr(self.app, "youtube_connector"):
                await self.app.youtube_connector.send_chat_message(message)
            
            elif platform == "kick" and hasattr(self.app, "kick_connector"):
                await self.app.kick_connector.send_chat_message(message)
            
            elif platform == "telegram" and hasattr(self.app, "telegram_connector"):
                for chat_id in self.app.config.get('TELEGRAM_CHAT_IDS', []):
                    await self.app.telegram_connector.send_message(chat_id, message)
            
            elif platform == "whatsapp" and hasattr(self.app, "whatsapp_connector"):
                # Per WhatsApp, non inviamo annunci pubblici ai numeri privati
                pass
        except Exception as e:
            logger.error(f"Errore nell'annuncio del riscatto della ricompensa: {e}")

def setup(app):
    """
    Configura il plugin del sistema di fedeltà
    
    Args:
        app: L'applicazione Flask/Quart
    """
    # Inizializza il gestore del sistema di fedeltà
    app.loyalty_system = LoyaltySystem(app)
    
    # Registra il blueprint
    app.register_blueprint(loyalty_blueprint, url_prefix='/loyalty')
    
    # Definisci le route
    @loyalty_blueprint.route('/', methods=['GET'])
    async def loyalty_page():
        """Pagina principale del sistema di fedeltà"""
        # Converti gli utenti in una lista ordinata per punti
        users_list = list(app.loyalty_system.users.values())
        users_list.sort(key=lambda x: x.get("points", 0), reverse=True)
        
        return await render_template(
            'loyalty.html',
            users=users_list,
            levels=app.loyalty_system.levels,
            rewards=app.loyalty_system.rewards,
            config=app.loyalty_system.config
        )
    
    @loyalty_blueprint.route('/api/users', methods=['GET'])
    async def get_users():
        """API per ottenere tutti gli utenti"""
        # Converti gli utenti in una lista
        users_list = list(app.loyalty_system.users.values())
        
        # Ordina gli utenti per punti
        users_list.sort(key=lambda x: x.get("points", 0), reverse=True)
        
        return jsonify({"success": True, "users": users_list})
    
    @loyalty_blueprint.route('/api/users/<user_id>', methods=['GET'])
    async def get_user(user_id):
        """API per ottenere un utente specifico"""
        # Verifica che l'utente esista
        if user_id not in app.loyalty_system.users:
            return jsonify({"success": False, "error": "Utente non trovato"}), 404
        
        return jsonify({"success": True, "user": app.loyalty_system.users[user_id]})
    
    @loyalty_blueprint.route('/api/users/<user_id>/add_points', methods=['POST'])
    async def add_points(user_id):
        """API per aggiungere punti a un utente"""
        data = await request.json
        points = float(data.get("points", 0))
        
        result = await app.loyalty_system.add_points(user_id, points)
        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @loyalty_blueprint.route('/api/users/<user_id>/rewards/<reward_id>', methods=['POST'])
    async def redeem_reward(user_id, reward_id):
        """API per riscattare una ricompensa"""
        result = await app.loyalty_system.redeem_reward(user_id, reward_id)
        if result["success"]:
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @loyalty_blueprint.route('/api/levels', methods=['GET'])
    async def get_levels():
        """API per ottenere tutti i livelli"""
        return jsonify({"success": True, "levels": app.loyalty_system.levels})
    
    @loyalty_blueprint.route('/api/rewards', methods=['GET'])
    async def get_rewards():
        """API per ottenere tutte le ricompense"""
        return jsonify({"success": True, "rewards": app.loyalty_system.rewards})
    
    @loyalty_blueprint.route('/api/config', methods=['GET'])
    async def get_config():
        """API per ottenere la configurazione del sistema di fedeltà"""
        return jsonify({"success": True, "config": app.loyalty_system.config})
    
    @loyalty_blueprint.route('/api/config', methods=['POST'])
    async def update_config():
        """API per aggiornare la configurazione del sistema di fedeltà"""
        data = await request.json
        
        # Aggiorna la configurazione
        app.loyalty_system.config.update(data)
        
        # Salva la configurazione
        app.loyalty_system._save_config()
        
        return jsonify({"success": True, "config": app.loyalty_system.config})
    
    # Aggiungi la gestione dei messaggi per assegnare punti
    if hasattr(app, 'message_handler'):
        app.message_handler.register_handler(handle_loyalty_message)
    
    # Aggiungi un gestore di chiusura per interrompere il task di aggiornamento
    @app.teardown_appcontext
    async def shutdown_loyalty(exception=None):
        if hasattr(app, 'loyalty_system') and app.loyalty_system.update_task:
            app.loyalty_system.update_task.cancel()
            try:
                await app.loyalty_system.update_task
            except asyncio.CancelledError:
                pass
    
    logger.info("Plugin del sistema di fedeltà configurato")

async def handle_loyalty_message(message, app):
    """
    Gestore dei messaggi per il sistema di fedeltà
    
    Args:
        message: Il messaggio ricevuto
        app: L'applicazione Flask/Quart
        
    Returns:
        bool: True se il messaggio è stato gestito, False altrimenti
    """
    if not hasattr(app, 'loyalty_system'):
        return False
    
    return await app.loyalty_system.process_message(message) 