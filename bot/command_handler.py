#!/usr/bin/env python3
"""
Gestore dei comandi per il sistema di punti canale
"""

import logging
import json
import time
from typing import Dict, List, Optional, Any, Union

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/commands.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("PointsCommands")

class PointsCommandHandler:
    """Gestisce i comandi del sistema di punti canale."""
    
    def __init__(self, bot):
        """
        Inizializza il gestore dei comandi per i punti canale
        
        Args:
            bot: L'istanza del bot principale
        """
        self.bot = bot
        
        # Comandi disponibili
        self.commands = {
            "punti": self.handle_points_command,
            "points": self.handle_points_command,
            "classifica": self.handle_leaderboard_command,
            "leaderboard": self.handle_leaderboard_command,
            "top": self.handle_leaderboard_command,
            "premi": self.handle_rewards_command,
            "rewards": self.handle_rewards_command,
            "riscatta": self.handle_redeem_command,
            "redeem": self.handle_redeem_command,
            "regalo": self.handle_gift_command,
            "gift": self.handle_gift_command,
            "dailypoints": self.handle_daily_points_command,
            "daily": self.handle_daily_points_command,
            "giornalieri": self.handle_daily_points_command
        }
        
        # Cooldown per i comandi
        self.cooldowns = {}
        
    async def handle_command(self, channel_id: int, channel_name: str, user: Dict, message: str) -> bool:
        """
        Gestisce un comando dei punti canale
        
        Args:
            channel_id: ID del canale
            channel_name: Nome del canale
            user: Informazioni sull'utente che ha inviato il comando
            message: Messaggio completo contenente il comando
            
        Returns:
            bool: True se il comando è stato gestito, False altrimenti
        """
        if not message.startswith("!"):
            return False
            
        # Estrai il nome del comando e gli argomenti
        parts = message.split(" ", 1)
        command_name = parts[0][1:].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        # Verifica se è un comando gestito da questo handler
        if command_name not in self.commands:
            return False
            
        # Verifica il cooldown
        user_id = user["id"]
        current_time = time.time()
        cooldown_key = f"{channel_id}:{command_name}:{user_id}"
        
        if cooldown_key in self.cooldowns:
            # Applica un cooldown di 5 secondi per evitare spam
            if current_time - self.cooldowns[cooldown_key] < 5:
                return True  # Il comando è in cooldown, ma lo consideriamo gestito
                
        # Aggiorna il timestamp del cooldown
        self.cooldowns[cooldown_key] = current_time
        
        # Esegui il comando
        handler = self.commands[command_name]
        await handler(channel_id, channel_name, user, args)
        
        return True
        
    async def handle_points_command(self, channel_id: int, channel_name: str, user: Dict, args: str):
        """
        Gestisce il comando !punti/!points
        Mostra i punti dell'utente o di un altro utente specificato
        """
        user_id = user["id"]
        username = user["username"]
        
        # Verifica se è specificato un altro utente
        target_username = args.strip() if args else None
        
        if target_username:
            # Cerca l'utente nel database
            async with self.bot.db.pool.acquire() as conn:
                target_user = await conn.fetchrow('''
                    SELECT id, username FROM users 
                    WHERE LOWER(username) = LOWER($1)
                ''', target_username)
                
                if not target_user:
                    await self.bot.api.send_chat_message(
                        channel_id, 
                        channel_name, 
                        f"Utente {target_username} non trovato!"
                    )
                    return
                    
                target_user_id = target_user["id"]
                target_username = target_user["username"]  # Usa il nome con la corretta capitalizzazione
                
                # Ottieni i punti dell'utente target
                points = await self.bot.point_system.get_user_points(channel_id, target_user_id)
                
                # Ottieni il nome configurato per i punti
                points_name = self.bot.kick_channel_points.config.points_name
                
                # Invia il messaggio con i punti
                await self.bot.api.send_chat_message(
                    channel_id, 
                    channel_name, 
                    f"{target_username} ha {points} {points_name}."
                )
        else:
            # Ottieni i punti dell'utente che ha inviato il comando
            points = await self.bot.point_system.get_user_points(channel_id, user_id)
            
            # Ottieni il nome configurato per i punti
            points_name = self.bot.kick_channel_points.config.points_name
            
            # Invia il messaggio con i punti
            await self.bot.api.send_chat_message(
                channel_id, 
                channel_name, 
                f"{username}, hai {points} {points_name}."
            )
            
    async def handle_leaderboard_command(self, channel_id: int, channel_name: str, user: Dict, args: str):
        """
        Gestisce il comando !classifica/!leaderboard/!top
        Mostra la classifica dei punti
        """
        # Analizza gli argomenti per ottenere il numero di utenti da mostrare
        try:
            limit = int(args.strip()) if args.strip() else 5
            # Limita a un massimo di 10 utenti per evitare spam
            limit = min(limit, 10)
        except ValueError:
            limit = 5
            
        # Ottieni la classifica
        top_users = await self.bot.point_system.get_top_points(channel_id, limit)
        
        if not top_users:
            await self.bot.api.send_chat_message(
                channel_id, 
                channel_name, 
                "Nessun utente ha ancora accumulato punti!"
            )
            return
            
        # Ottieni il nome configurato per i punti
        points_name = self.bot.kick_channel_points.config.points_name
        
        # Costruisci il messaggio della classifica
        message = f"Classifica {points_name}:\n"
        for i, user_data in enumerate(top_users):
            message += f"{i+1}. {user_data['username']}: {user_data['points']} {points_name}\n"
            
        # Invia il messaggio
        await self.bot.api.send_chat_message(channel_id, channel_name, message)
        
    async def handle_rewards_command(self, channel_id: int, channel_name: str, user: Dict, args: str):
        """
        Gestisce il comando !premi/!rewards
        Mostra i premi disponibili
        """
        # Ottieni la lista dei premi
        rewards = await self.bot.kick_channel_points.get_rewards(channel_id)
        
        if not rewards:
            await self.bot.api.send_chat_message(
                channel_id, 
                channel_name, 
                "Nessun premio disponibile al momento!"
            )
            return
            
        # Filtra i premi abilitati
        enabled_rewards = [r for r in rewards if r.get("enabled", True)]
        
        if not enabled_rewards:
            await self.bot.api.send_chat_message(
                channel_id, 
                channel_name, 
                "Nessun premio disponibile al momento!"
            )
            return
            
        # Costruisci il messaggio con i premi
        message = "Premi disponibili:\n"
        for reward in enabled_rewards:
            message += f"{reward.get('id')}: {reward.get('title')} - {reward.get('cost')} punti\n"
            
        # Aggiungi istruzioni per il riscatto
        message += "\nPer riscattare un premio, digita !riscatta [id_premio]"
        
        # Invia il messaggio
        await self.bot.api.send_chat_message(channel_id, channel_name, message)
        
    async def handle_redeem_command(self, channel_id: int, channel_name: str, user: Dict, args: str):
        """
        Gestisce il comando !riscatta/!redeem
        Riscatta un premio
        """
        # Verifica che sia specificato un ID premio
        reward_id = args.strip()
        if not reward_id:
            await self.bot.api.send_chat_message(
                channel_id, 
                channel_name, 
                "Specifica l'ID del premio da riscattare! Usa !premi per vedere quelli disponibili."
            )
            return
            
        # Tenta di riscattare il premio
        success = await self.bot.kick_channel_points.handle_reward_redemption(
            channel_id, 
            int(user["id"]), 
            user["username"], 
            reward_id
        )
        
        if success:
            # Il riscatto è avvenuto correttamente, il messaggio è gestito dal sistema di riscatto
            pass
        else:
            # Errore nel riscatto
            await self.bot.api.send_chat_message(
                channel_id, 
                channel_name, 
                f"Impossibile riscattare il premio '{reward_id}'. Verifica di avere abbastanza punti e che il premio sia disponibile."
            )
            
    async def handle_gift_command(self, channel_id: int, channel_name: str, user: Dict, args: str):
        """
        Gestisce il comando !regalo/!gift
        Regala punti a un altro utente
        """
        # Verifica che l'utente sia un moderatore o il proprietario del canale
        is_mod = user.get("is_moderator", False)
        
        async with self.bot.db.pool.acquire() as conn:
            channel = await conn.fetchrow('''
                SELECT owner_id FROM channels WHERE id = $1
            ''', channel_id)
            
            is_owner = False
            if channel and str(channel["owner_id"]) == str(user["id"]):
                is_owner = True
                
        # Solo moderatori e proprietario possono usare questo comando
        if not (is_mod or is_owner):
            await self.bot.api.send_chat_message(
                channel_id, 
                channel_name, 
                "Solo i moderatori e il proprietario del canale possono regalare punti."
            )
            return
            
        # Estrai username e punti dagli argomenti
        args_parts = args.strip().split()
        if len(args_parts) < 2:
            await self.bot.api.send_chat_message(
                channel_id, 
                channel_name, 
                "Uso: !regalo [username] [punti]"
            )
            return
            
        target_username = args_parts[0]
        try:
            points_to_gift = int(args_parts[1])
            if points_to_gift <= 0:
                raise ValueError("I punti devono essere positivi")
        except ValueError:
            await self.bot.api.send_chat_message(
                channel_id, 
                channel_name, 
                "Specifica un numero valido di punti da regalare."
            )
            return
            
        # Cerca l'utente target nel database
        async with self.bot.db.pool.acquire() as conn:
            target_user = await conn.fetchrow('''
                SELECT id, username FROM users 
                WHERE LOWER(username) = LOWER($1)
            ''', target_username)
            
            if not target_user:
                await self.bot.api.send_chat_message(
                    channel_id, 
                    channel_name, 
                    f"Utente {target_username} non trovato!"
                )
                return
                
            target_user_id = target_user["id"]
            target_username = target_user["username"]  # Usa il nome con la corretta capitalizzazione
            
        # Aggiorna i punti dell'utente target
        await self.bot.point_system.update_points(channel_id, target_user_id, points_to_gift)
        
        # Ottieni il nome configurato per i punti
        points_name = self.bot.kick_channel_points.config.points_name
        
        # Invia il messaggio di conferma
        await self.bot.api.send_chat_message(
            channel_id, 
            channel_name, 
            f"{user['username']} ha regalato {points_to_gift} {points_name} a {target_username}!"
        )
        
    async def handle_daily_points_command(self, channel_id: int, channel_name: str, user: Dict, args: str):
        """
        Gestisce il comando !daily/!dailypoints/!giornalieri
        Permette agli utenti di ricevere punti giornalieri
        """
        user_id = user["id"]
        username = user["username"]
        
        # Verifica se l'utente ha già ottenuto i punti giornalieri
        current_date = time.strftime("%Y-%m-%d")
        daily_key = f"daily_points:{channel_id}:{user_id}:{current_date}"
        
        async with self.bot.db.pool.acquire() as conn:
            # Controlla se l'utente ha già ricevuto i punti oggi
            daily_claimed = await conn.fetchval('''
                SELECT value FROM settings
                WHERE channel_id = $1 AND key = $2
            ''', channel_id, daily_key)
            
            if daily_claimed:
                # L'utente ha già ricevuto i punti oggi
                await self.bot.api.send_chat_message(
                    channel_id, 
                    channel_name, 
                    f"{username}, hai già ricevuto i tuoi punti giornalieri oggi! Torna domani."
                )
                return
                
            # Determina quanti punti assegnare
            # Base: 100 punti
            # Abbonati: 200 punti
            # VIP: 250 punti
            # Moderatori: 150 punti
            
            points_to_add = 100  # Base
            
            if user.get("is_subscriber", False):
                points_to_add = 200
            elif user.get("is_vip", False):
                points_to_add = 250
            elif user.get("is_moderator", False):
                points_to_add = 150
                
            # Aggiorna i punti dell'utente
            await self.bot.point_system.update_points(channel_id, user_id, points_to_add)
            
            # Registra che l'utente ha ricevuto i punti oggi
            await conn.execute('''
                INSERT INTO settings (channel_id, key, value)
                VALUES ($1, $2, $3)
                ON CONFLICT (channel_id, key) 
                DO UPDATE SET value = $3
            ''', channel_id, daily_key, "true")
            
            # Ottieni il nome configurato per i punti
            points_name = self.bot.kick_channel_points.config.points_name
            
            # Invia il messaggio di conferma
            await self.bot.api.send_chat_message(
                channel_id, 
                channel_name, 
                f"{username}, hai ricevuto {points_to_add} {points_name} giornalieri! Torna domani per altri punti."
            ) 