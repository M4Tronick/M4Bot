#!/usr/bin/env python3
"""
Modulo per la gestione dei punti canale di Kick.com
"""

import logging
import asyncio
import json
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/kick_points.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("KickChannelPoints")

class ChannelPointsConfig:
    """Configurazione per il sistema di punti canale"""
    
    def __init__(self, config_data: Dict[str, Any]):
        """
        Inizializza la configurazione del sistema di punti canale
        
        Args:
            config_data: Dati di configurazione
        """
        # Impostazioni generali
        self.enabled = config_data.get("enabled", True)
        self.points_name = config_data.get("points_name", "Punti")
        
        # Impostazioni per il guadagno di punti
        self.points_per_minute = config_data.get("points_per_minute", 1)
        self.points_per_chat_message = config_data.get("points_per_chat_message", 1)
        self.points_per_subscription = config_data.get("points_per_subscription", 500)
        self.points_per_follow = config_data.get("points_per_follow", 50)
        self.points_per_raid = config_data.get("points_per_raid_viewer", 1)  # Per ogni spettatore
        
        # Impostazioni per il bonus di punti
        self.subscriber_points_multiplier = config_data.get("subscriber_points_multiplier", 1.5)
        self.vip_points_multiplier = config_data.get("vip_points_multiplier", 2.0)
        self.mod_points_multiplier = config_data.get("mod_points_multiplier", 1.2)
        
        # Premi
        self.rewards = config_data.get("rewards", [])


class ChannelPointsReward:
    """Rappresenta un premio che può essere riscattato con i punti canale"""
    
    def __init__(self, reward_data: Dict[str, Any]):
        """
        Inizializza un nuovo premio
        
        Args:
            reward_data: Dati del premio
        """
        self.id = reward_data.get("id", "")
        self.title = reward_data.get("title", "")
        self.description = reward_data.get("description", "")
        self.cost = reward_data.get("cost", 100)
        self.cooldown = reward_data.get("cooldown", 0)  # In secondi
        self.is_enabled = reward_data.get("enabled", True)
        self.is_moderator_only = reward_data.get("moderator_only", False)
        self.is_subscriber_only = reward_data.get("subscriber_only", False)
        self.background_color = reward_data.get("background_color", "#9146FF")
        self.image_url = reward_data.get("image_url", "")
        self.max_per_stream = reward_data.get("max_per_stream", 0)  # 0 = illimitato
        self.max_per_user_per_stream = reward_data.get("max_per_user_per_stream", 0)  # 0 = illimitato
        self.redemption_count = 0  # Contatore per questo stream
        self.user_redemption_counts = {}  # Contatore per utente per questo stream
        self.last_redemption_time = 0  # Timestamp dell'ultimo riscatto
        
    def to_dict(self) -> Dict[str, Any]:
        """
        Converte il premio in un dizionario
        
        Returns:
            Dict[str, Any]: Dati del premio
        """
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "cost": self.cost,
            "cooldown": self.cooldown,
            "enabled": self.is_enabled,
            "moderator_only": self.is_moderator_only,
            "subscriber_only": self.is_subscriber_only,
            "background_color": self.background_color,
            "image_url": self.image_url,
            "max_per_stream": self.max_per_stream,
            "max_per_user_per_stream": self.max_per_user_per_stream
        }


class KickChannelPoints:
    """Gestisce il sistema di punti canale per Kick.com"""
    
    def __init__(self, bot):
        """
        Inizializza il gestore dei punti canale
        
        Args:
            bot: Istanza del bot principale
        """
        self.bot = bot
        self.db = bot.db
        self.config = None
        self.rewards = {}
        self.active_viewers = {}  # {channel_id: {user_id: last_active_time}}
        self.update_tasks = {}  # {channel_id: task}
        
        # Carica la configurazione predefinita
        self._load_default_config()
        
    def _load_default_config(self):
        """Carica la configurazione predefinita per i punti canale"""
        default_config = {
            "enabled": True,
            "points_name": "Punti",
            "points_per_minute": 1,
            "points_per_chat_message": 1,
            "points_per_subscription": 500,
            "points_per_follow": 50,
            "points_per_raid_viewer": 1,
            "subscriber_points_multiplier": 1.5,
            "vip_points_multiplier": 2.0,
            "mod_points_multiplier": 1.2,
            "rewards": [
                {
                    "id": "highlight_message",
                    "title": "Evidenzia il mio messaggio",
                    "description": "Il tuo messaggio verrà evidenziato in chat",
                    "cost": 100,
                    "cooldown": 60,
                    "enabled": True,
                    "background_color": "#9146FF"
                },
                {
                    "id": "play_sound",
                    "title": "Riproduci un suono",
                    "description": "Riproduci un suono durante lo stream",
                    "cost": 300,
                    "cooldown": 120,
                    "enabled": True,
                    "background_color": "#FF4500"
                }
            ]
        }
        
        self.config = ChannelPointsConfig(default_config)
        
        # Inizializza i premi predefiniti
        for reward_data in default_config["rewards"]:
            reward = ChannelPointsReward(reward_data)
            self.rewards[reward.id] = reward
    
    async def load_channel_config(self, channel_id: int) -> bool:
        """
        Carica la configurazione dei punti canale per un canale specifico
        
        Args:
            channel_id: ID del canale
            
        Returns:
            bool: True se la configurazione è stata caricata con successo
        """
        try:
            async with self.db.pool.acquire() as conn:
                config_row = await conn.fetchrow('''
                    SELECT value FROM settings
                    WHERE channel_id = $1 AND key = 'channel_points_config'
                ''', channel_id)
                
                if config_row:
                    config_data = json.loads(config_row["value"])
                    self.config = ChannelPointsConfig(config_data)
                    
                    # Carica i premi personalizzati
                    self.rewards = {}
                    for reward_data in config_data.get("rewards", []):
                        reward = ChannelPointsReward(reward_data)
                        self.rewards[reward.id] = reward
                    
                    logger.info(f"Configurazione dei punti canale caricata per il canale {channel_id}")
                    return True
                else:
                    # Se non esiste una configurazione personalizzata, usa quella predefinita e salvala
                    await self.save_channel_config(channel_id)
                    logger.info(f"Creata configurazione dei punti canale predefinita per il canale {channel_id}")
                    return True
        except Exception as e:
            logger.error(f"Errore nel caricamento della configurazione dei punti canale: {e}")
            return False
    
    async def save_channel_config(self, channel_id: int) -> bool:
        """
        Salva la configurazione dei punti canale per un canale specifico
        
        Args:
            channel_id: ID del canale
            
        Returns:
            bool: True se la configurazione è stata salvata con successo
        """
        try:
            # Prepara il dizionario di configurazione
            config_data = {
                "enabled": self.config.enabled,
                "points_name": self.config.points_name,
                "points_per_minute": self.config.points_per_minute,
                "points_per_chat_message": self.config.points_per_chat_message,
                "points_per_subscription": self.config.points_per_subscription,
                "points_per_follow": self.config.points_per_follow,
                "points_per_raid_viewer": self.config.points_per_raid_viewer,
                "subscriber_points_multiplier": self.config.subscriber_points_multiplier,
                "vip_points_multiplier": self.config.vip_points_multiplier,
                "mod_points_multiplier": self.config.mod_points_multiplier,
                "rewards": [reward.to_dict() for reward in self.rewards.values()]
            }
            
            async with self.db.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO settings (channel_id, key, value)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (channel_id, key) 
                    DO UPDATE SET value = $3
                ''', channel_id, 'channel_points_config', json.dumps(config_data))
                
                logger.info(f"Configurazione dei punti canale salvata per il canale {channel_id}")
                return True
        except Exception as e:
            logger.error(f"Errore nel salvataggio della configurazione dei punti canale: {e}")
            return False
    
    async def start_points_tracker(self, channel_id: int) -> bool:
        """
        Avvia il tracker dei punti canale per un canale specifico
        
        Args:
            channel_id: ID del canale
            
        Returns:
            bool: True se il tracker è stato avviato con successo
        """
        # Ferma eventuali task precedenti
        if channel_id in self.update_tasks:
            if not self.update_tasks[channel_id].done():
                self.update_tasks[channel_id].cancel()
            
        # Inizializza la lista degli spettatori attivi
        self.active_viewers[channel_id] = {}
        
        # Avvia il task di aggiornamento dei punti
        update_task = asyncio.create_task(self._points_update_loop(channel_id))
        self.update_tasks[channel_id] = update_task
        
        logger.info(f"Tracker dei punti canale avviato per il canale {channel_id}")
        return True
    
    async def stop_points_tracker(self, channel_id: int) -> bool:
        """
        Ferma il tracker dei punti canale per un canale specifico
        
        Args:
            channel_id: ID del canale
            
        Returns:
            bool: True se il tracker è stato fermato con successo
        """
        if channel_id in self.update_tasks:
            if not self.update_tasks[channel_id].done():
                self.update_tasks[channel_id].cancel()
            del self.update_tasks[channel_id]
        
        if channel_id in self.active_viewers:
            del self.active_viewers[channel_id]
        
        logger.info(f"Tracker dei punti canale fermato per il canale {channel_id}")
        return True
    
    async def _points_update_loop(self, channel_id: int):
        """
        Loop di aggiornamento dei punti canale
        
        Args:
            channel_id: ID del canale
        """
        try:
            while True:
                # Verifica se il canale è in diretta
                is_live = await self._is_channel_live(channel_id)
                
                if is_live:
                    # Aggiorna i punti degli spettatori attivi
                    current_time = time.time()
                    viewers_to_update = []
                    
                    for user_id, last_active in self.active_viewers.get(channel_id, {}).items():
                        # Se l'utente è stato attivo negli ultimi 10 minuti
                        if current_time - last_active < 600:
                            viewers_to_update.append(user_id)
                    
                    if viewers_to_update:
                        await self._update_viewers_points(channel_id, viewers_to_update)
                
                # Attendi 1 minuto prima del prossimo aggiornamento
                await asyncio.sleep(60)
                
        except asyncio.CancelledError:
            logger.info(f"Task di aggiornamento punti canale cancellato per il canale {channel_id}")
        except Exception as e:
            logger.error(f"Errore nel loop di aggiornamento dei punti canale: {e}")
    
    async def _is_channel_live(self, channel_id: int) -> bool:
        """
        Verifica se il canale è in diretta
        
        Args:
            channel_id: ID del canale
            
        Returns:
            bool: True se il canale è in diretta
        """
        try:
            async with self.db.pool.acquire() as conn:
                channel = await conn.fetchrow('''
                    SELECT name FROM channels WHERE id = $1
                ''', channel_id)
                
                if not channel:
                    return False
                
                # Usa l'API di Kick per verificare se il canale è in diretta
                channel_name = channel["name"]
                api = self.bot.api
                channel_info = await api.get_channel_info(channel_name)
                
                if channel_info and "is_live" in channel_info:
                    return channel_info["is_live"]
                return False
                
        except Exception as e:
            logger.error(f"Errore nella verifica dello stato del canale: {e}")
            return False
    
    async def _update_viewers_points(self, channel_id: int, user_ids: List[int]):
        """
        Aggiorna i punti degli spettatori
        
        Args:
            channel_id: ID del canale
            user_ids: Lista degli ID utente da aggiornare
        """
        try:
            if not user_ids:
                return
                
            async with self.db.pool.acquire() as conn:
                # Ottieni le informazioni sugli utenti per determinare i moltiplicatori
                users_data = await conn.fetch('''
                    SELECT u.id, u.username, ur.role FROM users u
                    LEFT JOIN user_roles ur ON u.id = ur.user_id AND ur.channel_id = $1
                    WHERE u.id = ANY($2)
                ''', channel_id, user_ids)
                
                # Mappa degli ID utente ai loro ruoli
                user_roles = {user["id"]: user["role"] for user in users_data}
                
                # Per ogni utente, calcola i punti da assegnare
                for user_id in user_ids:
                    role = user_roles.get(user_id, "viewer")
                    
                    # Calcola il moltiplicatore in base al ruolo
                    multiplier = 1.0
                    if role == "subscriber":
                        multiplier = self.config.subscriber_points_multiplier
                    elif role == "vip":
                        multiplier = self.config.vip_points_multiplier
                    elif role == "moderator":
                        multiplier = self.config.mod_points_multiplier
                    
                    # Calcola i punti da assegnare
                    points_to_add = int(self.config.points_per_minute * multiplier)
                    
                    # Aggiorna i punti dell'utente nel database
                    await self.bot.point_system.update_points(channel_id, user_id, points_to_add)
        
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento dei punti degli spettatori: {e}")
    
    async def mark_user_active(self, channel_id: int, user_id: int):
        """
        Segna un utente come attivo nel canale
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente
        """
        if channel_id not in self.active_viewers:
            self.active_viewers[channel_id] = {}
            
        self.active_viewers[channel_id][user_id] = time.time()
    
    async def handle_chat_message(self, channel_id: int, user_id: int, username: str, is_subscriber: bool, is_moderator: bool, is_vip: bool):
        """
        Gestisce un messaggio in chat, assegnando punti e segnando l'utente come attivo
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente
            username: Nome utente
            is_subscriber: True se l'utente è un abbonato
            is_moderator: True se l'utente è un moderatore
            is_vip: True se l'utente è un VIP
        """
        # Segna l'utente come attivo
        await self.mark_user_active(channel_id, user_id)
        
        # Assegna punti per il messaggio in chat
        if self.config.enabled and self.config.points_per_chat_message > 0:
            # Calcola il moltiplicatore in base al ruolo
            multiplier = 1.0
            if is_subscriber:
                multiplier = self.config.subscriber_points_multiplier
            elif is_vip:
                multiplier = self.config.vip_points_multiplier
            elif is_moderator:
                multiplier = self.config.mod_points_multiplier
                
            # Calcola i punti da assegnare
            points_to_add = int(self.config.points_per_chat_message * multiplier)
            
            # Aggiorna i punti dell'utente
            await self.bot.point_system.update_points(channel_id, user_id, points_to_add)
    
    async def handle_follow(self, channel_id: int, user_id: int, username: str):
        """
        Gestisce un nuovo follower, assegnando punti
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente
            username: Nome utente
        """
        if self.config.enabled and self.config.points_per_follow > 0:
            # Assegna punti per il nuovo follower
            await self.bot.point_system.update_points(channel_id, user_id, self.config.points_per_follow)
            
            logger.info(f"Assegnati {self.config.points_per_follow} punti a {username} per aver seguito il canale {channel_id}")
    
    async def handle_subscription(self, channel_id: int, user_id: int, username: str):
        """
        Gestisce un nuovo abbonamento, assegnando punti
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente
            username: Nome utente
        """
        if self.config.enabled and self.config.points_per_subscription > 0:
            # Assegna punti per il nuovo abbonamento
            await self.bot.point_system.update_points(channel_id, user_id, self.config.points_per_subscription)
            
            logger.info(f"Assegnati {self.config.points_per_subscription} punti a {username} per essersi abbonato al canale {channel_id}")
    
    async def handle_raid(self, channel_id: int, raider_id: int, raider_username: str, viewer_count: int):
        """
        Gestisce un raid, assegnando punti
        
        Args:
            channel_id: ID del canale
            raider_id: ID dell'utente che effettua il raid
            raider_username: Nome dell'utente che effettua il raid
            viewer_count: Numero di spettatori del raid
        """
        if self.config.enabled and self.config.points_per_raid_viewer > 0:
            # Calcola i punti da assegnare
            points_to_add = self.config.points_per_raid_viewer * viewer_count
            
            # Assegna punti per il raid
            await self.bot.point_system.update_points(channel_id, raider_id, points_to_add)
            
            logger.info(f"Assegnati {points_to_add} punti a {raider_username} per aver effettuato un raid con {viewer_count} spettatori al canale {channel_id}")
    
    async def handle_reward_redemption(self, channel_id: int, user_id: int, username: str, reward_id: str) -> bool:
        """
        Gestisce il riscatto di un premio
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente
            username: Nome utente
            reward_id: ID del premio
            
        Returns:
            bool: True se il riscatto è stato gestito con successo
        """
        # Verifica se il sistema è abilitato
        if not self.config.enabled:
            return False
            
        # Verifica se il premio esiste
        if reward_id not in self.rewards:
            logger.warning(f"Tentativo di riscatto di un premio non esistente: {reward_id}")
            return False
            
        reward = self.rewards[reward_id]
        
        # Verifica se il premio è abilitato
        if not reward.is_enabled:
            logger.warning(f"Tentativo di riscatto di un premio disabilitato: {reward_id}")
            return False
            
        # Verifica il cooldown
        current_time = time.time()
        if reward.last_redemption_time > 0 and (current_time - reward.last_redemption_time) < reward.cooldown:
            logger.warning(f"Tentativo di riscatto di un premio in cooldown: {reward_id}")
            return False
            
        # Verifica il limite per stream
        if reward.max_per_stream > 0 and reward.redemption_count >= reward.max_per_stream:
            logger.warning(f"Limite per stream raggiunto per il premio: {reward_id}")
            return False
            
        # Verifica il limite per utente per stream
        if user_id in reward.user_redemption_counts:
            if (reward.max_per_user_per_stream > 0 and 
                reward.user_redemption_counts[user_id] >= reward.max_per_user_per_stream):
                logger.warning(f"Limite per utente per stream raggiunto per il premio: {reward_id}")
                return False
        
        # Verifica se l'utente ha abbastanza punti
        user_points = await self.bot.point_system.get_user_points(channel_id, user_id)
        if user_points < reward.cost:
            logger.warning(f"L'utente {username} non ha abbastanza punti per riscattare il premio: {reward_id}")
            return False
            
        # Verifica i requisiti di ruolo
        if reward.is_subscriber_only or reward.is_moderator_only:
            async with self.db.pool.acquire() as conn:
                user_role = await conn.fetchval('''
                    SELECT role FROM user_roles
                    WHERE user_id = $1 AND channel_id = $2
                ''', user_id, channel_id)
                
                if reward.is_subscriber_only and user_role != "subscriber":
                    logger.warning(f"L'utente {username} non è un abbonato, non può riscattare il premio riservato agli abbonati: {reward_id}")
                    return False
                    
                if reward.is_moderator_only and user_role != "moderator":
                    logger.warning(f"L'utente {username} non è un moderatore, non può riscattare il premio riservato ai moderatori: {reward_id}")
                    return False
        
        # Sottrai i punti all'utente
        await self.bot.point_system.update_points(channel_id, user_id, -reward.cost)
        
        # Aggiorna le statistiche del premio
        reward.redemption_count += 1
        reward.last_redemption_time = current_time
        if user_id not in reward.user_redemption_counts:
            reward.user_redemption_counts[user_id] = 0
        reward.user_redemption_counts[user_id] += 1
        
        # Registra il riscatto
        async with self.db.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO reward_redemptions (
                    channel_id, user_id, reward_id, reward_title, reward_cost, redeemed_at
                ) VALUES ($1, $2, $3, $4, $5, NOW())
            ''', channel_id, user_id, reward_id, reward.title, reward.cost)
            
        logger.info(f"L'utente {username} ha riscattato il premio {reward.title} (ID: {reward_id}) per {reward.cost} punti")
        
        # Qui puoi aggiungere la logica per eseguire azioni specifiche in base al premio
        # Ad esempio, se il premio è "highlight_message", potresti inviare un evento al frontend
        # per evidenziare il prossimo messaggio dell'utente
        
        return True
    
    async def add_reward(self, channel_id: int, reward_data: Dict[str, Any]) -> bool:
        """
        Aggiunge un nuovo premio
        
        Args:
            channel_id: ID del canale
            reward_data: Dati del premio
            
        Returns:
            bool: True se il premio è stato aggiunto con successo
        """
        try:
            reward = ChannelPointsReward(reward_data)
            self.rewards[reward.id] = reward
            
            # Salva la configurazione aggiornata
            await self.save_channel_config(channel_id)
            
            logger.info(f"Aggiunto nuovo premio: {reward.title} (ID: {reward.id}) per il canale {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Errore nell'aggiunta del premio: {e}")
            return False
    
    async def update_reward(self, channel_id: int, reward_id: str, reward_data: Dict[str, Any]) -> bool:
        """
        Aggiorna un premio esistente
        
        Args:
            channel_id: ID del canale
            reward_id: ID del premio da aggiornare
            reward_data: Nuovi dati del premio
            
        Returns:
            bool: True se il premio è stato aggiornato con successo
        """
        try:
            if reward_id not in self.rewards:
                logger.warning(f"Tentativo di aggiornare un premio non esistente: {reward_id}")
                return False
                
            # Mantieni le statistiche correnti
            current_stats = {
                "redemption_count": self.rewards[reward_id].redemption_count,
                "user_redemption_counts": self.rewards[reward_id].user_redemption_counts,
                "last_redemption_time": self.rewards[reward_id].last_redemption_time
            }
            
            # Aggiorna il premio
            reward = ChannelPointsReward(reward_data)
            reward.redemption_count = current_stats["redemption_count"]
            reward.user_redemption_counts = current_stats["user_redemption_counts"]
            reward.last_redemption_time = current_stats["last_redemption_time"]
            
            self.rewards[reward_id] = reward
            
            # Salva la configurazione aggiornata
            await self.save_channel_config(channel_id)
            
            logger.info(f"Aggiornato premio: {reward.title} (ID: {reward.id}) per il canale {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento del premio: {e}")
            return False
    
    async def delete_reward(self, channel_id: int, reward_id: str) -> bool:
        """
        Elimina un premio
        
        Args:
            channel_id: ID del canale
            reward_id: ID del premio da eliminare
            
        Returns:
            bool: True se il premio è stato eliminato con successo
        """
        try:
            if reward_id not in self.rewards:
                logger.warning(f"Tentativo di eliminare un premio non esistente: {reward_id}")
                return False
                
            # Elimina il premio
            del self.rewards[reward_id]
            
            # Salva la configurazione aggiornata
            await self.save_channel_config(channel_id)
            
            logger.info(f"Eliminato premio con ID: {reward_id} per il canale {channel_id}")
            return True
        except Exception as e:
            logger.error(f"Errore nell'eliminazione del premio: {e}")
            return False
    
    async def get_rewards(self, channel_id: int) -> List[Dict[str, Any]]:
        """
        Ottiene la lista dei premi disponibili
        
        Args:
            channel_id: ID del canale
            
        Returns:
            List[Dict[str, Any]]: Lista dei premi disponibili
        """
        try:
            return [reward.to_dict() for reward in self.rewards.values()]
        except Exception as e:
            logger.error(f"Errore nell'ottenimento dei premi: {e}")
            return []
    
    async def reset_reward_limits(self, channel_id: int):
        """
        Resetta i limiti dei premi per un nuovo stream
        
        Args:
            channel_id: ID del canale
        """
        try:
            for reward in self.rewards.values():
                reward.redemption_count = 0
                reward.user_redemption_counts = {}
                
            logger.info(f"Limiti dei premi resettati per il canale {channel_id}")
        except Exception as e:
            logger.error(f"Errore nel reset dei limiti dei premi: {e}")
    
    async def get_user_point_rank(self, channel_id: int, user_id: int) -> Dict[str, Any]:
        """
        Ottiene il rank dell'utente nella classifica dei punti
        
        Args:
            channel_id: ID del canale
            user_id: ID dell'utente
            
        Returns:
            Dict[str, Any]: Informazioni sul rank dell'utente
        """
        try:
            async with self.db.pool.acquire() as conn:
                # Ottieni i punti dell'utente
                user_points = await self.bot.point_system.get_user_points(channel_id, user_id)
                
                # Ottieni la posizione dell'utente nella classifica
                rank = await conn.fetchval('''
                    SELECT COUNT(*) + 1 FROM channel_points
                    WHERE channel_id = $1 AND points > $2
                ''', channel_id, user_points)
                
                # Ottieni il numero totale di utenti con punti
                total_users = await conn.fetchval('''
                    SELECT COUNT(*) FROM channel_points
                    WHERE channel_id = $1 AND points > 0
                ''', channel_id)
                
                # Ottieni l'username dell'utente
                username = await conn.fetchval('''
                    SELECT username FROM users WHERE id = $1
                ''', user_id)
                
                return {
                    "username": username,
                    "user_id": user_id,
                    "points": user_points,
                    "rank": rank,
                    "total_users": total_users
                }
        except Exception as e:
            logger.error(f"Errore nell'ottenimento del rank dell'utente: {e}")
            return {
                "username": "Sconosciuto",
                "user_id": user_id,
                "points": 0,
                "rank": 0,
                "total_users": 0
            }

    async def setup_database(self):
        """Crea le tabelle necessarie nel database"""
        try:
            async with self.db.pool.acquire() as conn:
                # Tabella per i riscatti dei premi
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS reward_redemptions (
                        id SERIAL PRIMARY KEY,
                        channel_id INTEGER REFERENCES channels(id),
                        user_id INTEGER REFERENCES users(id),
                        reward_id VARCHAR(255) NOT NULL,
                        reward_title VARCHAR(255) NOT NULL,
                        reward_cost INTEGER NOT NULL,
                        redeemed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                    )
                ''')
                
                # Indice per velocizzare le query
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS reward_redemptions_channel_id_idx 
                    ON reward_redemptions(channel_id)
                ''')
                
                # Indice per velocizzare le query per utente
                await conn.execute('''
                    CREATE INDEX IF NOT EXISTS reward_redemptions_user_id_idx 
                    ON reward_redemptions(user_id)
                ''')
                
                logger.info("Tabelle per i punti canale create con successo")
                return True
        except Exception as e:
            logger.error(f"Errore nella creazione delle tabelle per i punti canale: {e}")
            return False 