import os
import json
import logging
import asyncio
import aiohttp
import discord
from discord.ext import commands
from typing import Dict, List, Optional, Any, Callable

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/discord_connector.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("DiscordConnector")

class DiscordConnector:
    """Connettore per Discord che gestisce la sincronizzazione dei messaggi tra piattaforme"""
    
    def __init__(self, config: Dict[str, Any], message_callback: Optional[Callable] = None):
        """
        Inizializza il connettore Discord
        
        Args:
            config: Configurazione del connettore
            message_callback: Callback per gestire i messaggi ricevuti da Discord
        """
        # Inizializza le variabili
        self.config = config
        self.token = config.get("discord_token", "")
        self.sync_channels = config.get("discord_sync_channels", [])
        self.command_prefix = config.get("discord_command_prefix", "!")
        self.message_callback = message_callback
        
        # Crea il client Discord
        intents = discord.Intents.default()
        intents.messages = True
        intents.message_content = True
        
        self.bot = commands.Bot(command_prefix=self.command_prefix, intents=intents)
        
        # Flag per indicare se il bot è connesso
        self.is_running = False
        
        # Registro dei messaggi sincronizzati per evitare duplicati
        self.synced_messages = {}
        
        # Configura gli eventi Discord
        self._setup_discord_events()
        
        # Crea le directory necessarie
        os.makedirs("logs", exist_ok=True)
        
        logger.info("Connettore Discord inizializzato")
    
    def _setup_discord_events(self):
        """Configura gli eventi Discord"""
        
        @self.bot.event
        async def on_ready():
            """Evento chiamato quando il bot Discord è pronto"""
            logger.info(f"Bot Discord connesso come {self.bot.user.name} ({self.bot.user.id})")
            self.is_running = True
            
            # Imposta lo stato del bot
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name="M4Bot su Twitch"
                )
            )
        
        @self.bot.event
        async def on_message(message):
            """Evento chiamato quando viene ricevuto un messaggio su Discord"""
            # Ignora i messaggi del bot stesso
            if message.author == self.bot.user:
                return
            
            # Verifica se il canale è nella lista dei canali da sincronizzare
            if str(message.channel.id) in self.sync_channels:
                # Crea un ID univoco per il messaggio
                message_id = f"discord_{message.id}"
                
                # Verifica se il messaggio è già stato sincronizzato
                if message_id in self.synced_messages:
                    return
                
                # Aggiunge il messaggio al registro dei messaggi sincronizzati
                self.synced_messages[message_id] = {
                    "timestamp": message.created_at.timestamp(),
                    "platform": "discord",
                    "channel_id": str(message.channel.id)
                }
                
                # Gestisci i comandi se il messaggio inizia con il prefisso
                if message.content.startswith(self.command_prefix):
                    await self.bot.process_commands(message)
                
                # Formatta il messaggio per la sincronizzazione
                formatted_message = {
                    "id": message_id,
                    "platform": "discord",
                    "channel_id": str(message.channel.id),
                    "channel_name": message.channel.name,
                    "author": {
                        "id": str(message.author.id),
                        "username": message.author.name,
                        "display_name": message.author.display_name,
                        "is_mod": message.author.guild_permissions.manage_messages if hasattr(message.author, "guild_permissions") else False
                    },
                    "content": message.content,
                    "timestamp": message.created_at.timestamp(),
                    "attachments": [att.url for att in message.attachments]
                }
                
                # Invia il messaggio al callback se presente
                if self.message_callback:
                    try:
                        await self.message_callback(formatted_message)
                    except Exception as e:
                        logger.error(f"Errore nel callback del messaggio: {e}")
        
        # Aggiungi comandi Discord personalizzati
        self._add_custom_commands()
    
    def _add_custom_commands(self):
        """Aggiunge comandi Discord personalizzati"""
        
        @self.bot.command(name="stato")
        async def status_command(ctx):
            """Mostra lo stato del bot"""
            embed = discord.Embed(
                title="Stato di M4Bot",
                description="Informazioni sullo stato del bot",
                color=discord.Color.blue()
            )
            
            embed.add_field(name="Discord", value="✅ Connesso", inline=True)
            embed.add_field(name="Twitch", value="✅ Connesso", inline=True)
            embed.add_field(name="Canali sincronizzati", value=str(len(self.sync_channels)), inline=True)
            
            await ctx.send(embed=embed)
        
        @self.bot.command(name="aiuto")
        async def help_command(ctx):
            """Mostra i comandi disponibili"""
            embed = discord.Embed(
                title="Comandi M4Bot",
                description="Ecco i comandi disponibili:",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name=f"{self.command_prefix}stato",
                value="Mostra lo stato attuale del bot",
                inline=False
            )
            
            embed.add_field(
                name=f"{self.command_prefix}aiuto",
                value="Mostra questo messaggio di aiuto",
                inline=False
            )
            
            await ctx.send(embed=embed)
    
    async def start(self):
        """Avvia il bot Discord"""
        if not self.token:
            logger.error("Token Discord non configurato")
            return False
        
        try:
            await self.bot.start(self.token)
            return True
        except Exception as e:
            logger.error(f"Errore nell'avvio del bot Discord: {e}")
            return False
    
    async def stop(self):
        """Ferma il bot Discord"""
        if self.is_running:
            try:
                await self.bot.close()
                self.is_running = False
                logger.info("Bot Discord disconnesso")
                return True
            except Exception as e:
                logger.error(f"Errore nella chiusura del bot Discord: {e}")
                return False
        return True
    
    async def sync_message_to_discord(self, message: Dict[str, Any]) -> bool:
        """
        Sincronizza un messaggio da un'altra piattaforma a Discord
        
        Args:
            message: Il messaggio da sincronizzare
            
        Returns:
            bool: True se il messaggio è stato sincronizzato con successo, False altrimenti
        """
        try:
            # Verifica se il messaggio è già stato sincronizzato
            message_id = message.get("id", "")
            if message_id in self.synced_messages:
                return True
            
            # Aggiunge il messaggio al registro dei messaggi sincronizzati
            self.synced_messages[message_id] = {
                "timestamp": message.get("timestamp", 0),
                "platform": message.get("platform", "unknown"),
                "channel_id": message.get("channel_id", "")
            }
            
            # Mantieni solo gli ultimi 1000 messaggi nel registro
            if len(self.synced_messages) > 1000:
                # Ordina per timestamp e rimuovi i più vecchi
                sorted_messages = sorted(
                    self.synced_messages.items(),
                    key=lambda x: x[1]["timestamp"]
                )
                self.synced_messages = dict(sorted_messages[500:])
            
            # Verifica se ci sono canali configurati per la sincronizzazione
            if not self.sync_channels or not self.is_running:
                return False
            
            # Formatta il messaggio per Discord
            platform = message.get("platform", "unknown")
            author_name = message.get("author", {}).get("display_name", "Utente")
            content = message.get("content", "")
            
            formatted_content = f"**[{platform.upper()}] {author_name}:** {content}"
            
            # Invia il messaggio a tutti i canali configurati
            for channel_id in self.sync_channels:
                try:
                    channel = await self.bot.fetch_channel(int(channel_id))
                    await channel.send(formatted_content)
                except Exception as e:
                    logger.error(f"Errore nell'invio del messaggio al canale {channel_id}: {e}")
            
            return True
        
        except Exception as e:
            logger.error(f"Errore nella sincronizzazione del messaggio a Discord: {e}")
            return False
    
    def is_connected(self) -> bool:
        """
        Verifica se il bot è connesso a Discord
        
        Returns:
            bool: True se il bot è connesso, False altrimenti
        """
        return self.is_running and self.bot.is_ready()

# Funzione per creare un'istanza del connettore Discord
def create_discord_connector(config: Dict[str, Any], message_callback: Optional[Callable] = None) -> DiscordConnector:
    """
    Crea un'istanza del connettore Discord
    
    Args:
        config: Configurazione del connettore
        message_callback: Callback per gestire i messaggi ricevuti da Discord
        
    Returns:
        DiscordConnector: Istanza del connettore Discord
    """
    return DiscordConnector(config, message_callback) 