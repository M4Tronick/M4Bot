"""
Sistema di Plugin per M4Bot

Questo modulo implementa un sistema per caricare dinamicamente plugin
che possono estendere le funzionalità del bot.
"""

import os
import sys
import logging
import importlib
import inspect
from pathlib import Path
from typing import Dict, List, Callable, Any, Optional, Type, Set

logger = logging.getLogger('M4Bot-Plugins')

class PluginInterface:
    """Interfaccia base per i plugin di M4Bot."""
    
    def plugin_info(self) -> Dict[str, Any]:
        """Restituisce informazioni sul plugin."""
        raise NotImplementedError("I plugin devono implementare plugin_info()")
    
    def initialize(self) -> None:
        """Inizializza il plugin."""
        raise NotImplementedError("I plugin devono implementare initialize()")
    
    def shutdown(self) -> None:
        """Finalizza il plugin prima della chiusura."""
        pass  # Opzionale, i plugin possono sovrascriverlo
    
    def event_handlers(self) -> Dict[str, Callable]:
        """Restituisce gli handler degli eventi supportati."""
        return {}  # Default: nessun handler
    
    def commands(self) -> Dict[str, Callable]:
        """Restituisce i comandi implementati dal plugin."""
        return {}  # Default: nessun comando
    
    def get_settings(self) -> Dict[str, Any]:
        """Restituisce le impostazioni supportate dal plugin."""
        return {}  # Default: nessuna impostazione

class PluginManager:
    """Gestisce i plugin di M4Bot con caricamento dinamico."""
    
    def __init__(self, plugins_dir: str = 'plugins', core_plugins: bool = True):
        # Converte il percorso relativo in assoluto
        base_path = Path(__file__).parent
        self.plugins_dir = base_path
        
        self.plugins: Dict[str, PluginInterface] = {}
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.commands: Dict[str, Dict[str, Callable]] = {}
        self.plugin_configs: Dict[str, Dict] = {}
        self.plugin_categories: Dict[str, Set[str]] = {}
        
        # Flag per il caricamento dei plugin core
        self.core_plugins = core_plugins
        
        # Lista di directory da cercare (sempre includi la directory base)
        self.plugin_dirs = [self.plugins_dir]
        if core_plugins:
            self.plugin_dirs.append(self.plugins_dir / 'core')
    
    def discover_plugins(self) -> List[Dict[str, Any]]:
        """Cerca plugin in tutte le directory configurate."""
        plugin_files = []
        
        for plugin_dir in self.plugin_dirs:
            if not os.path.exists(plugin_dir):
                logger.warning(f"Directory plugin non trovata: {plugin_dir}")
                continue
                
            logger.info(f"Cercando plugin in: {plugin_dir}")
            
            # Trova tutti i file Python che potrebbero essere plugin
            for item in os.listdir(plugin_dir):
                if item.endswith('.py') and not item.startswith('__'):
                    plugin_path = os.path.join(plugin_dir, item)
                    module_name = item[:-3]  # Rimuovi .py
                    is_core = 'core' in str(plugin_dir)
                    
                    plugin_files.append({
                        'path': plugin_path,
                        'module': module_name,
                        'is_core': is_core
                    })
        
        logger.info(f"Trovati {len(plugin_files)} potenziali plugin")
        return plugin_files
    
    def load_plugin(self, plugin_info: Dict[str, Any]) -> bool:
        """Carica un singolo plugin."""
        try:
            # Ottieni informazioni sul plugin
            plugin_path = plugin_info['path']
            module_name = plugin_info['module']
            is_core = plugin_info.get('is_core', False)
            
            logger.debug(f"Tentativo di caricamento del plugin: {module_name} (core: {is_core})")
            
            # Aggiungi temporaneamente la directory del plugin al path
            plugin_dir = os.path.dirname(plugin_path)
            sys.path.insert(0, plugin_dir)
            
            try:
                # Importa il modulo dinamicamente
                spec = importlib.util.spec_from_file_location(module_name, plugin_path)
                if not spec or not spec.loader:
                    logger.error(f"Impossibile caricare il plugin {module_name}: spec o loader non validi")
                    return False
                    
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # Cerca la classe del plugin
                plugin_class = None
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    
                    # Verifica se è una classe derivata da PluginInterface
                    if (inspect.isclass(attr) and 
                        issubclass(attr, PluginInterface) and 
                        attr is not PluginInterface):
                        plugin_class = attr
                        break
                
                if not plugin_class:
                    logger.warning(f"Nessuna classe plugin valida trovata in {module_name}")
                    return False
                
                # Crea l'istanza del plugin
                plugin_instance = plugin_class()
                
                # Ottieni informazioni
                plugin_meta = plugin_instance.plugin_info()
                plugin_id = plugin_meta.get('id', module_name)
                
                # Controlla se esiste già un plugin con lo stesso ID
                if plugin_id in self.plugins:
                    logger.warning(f"Plugin con ID '{plugin_id}' già caricato, viene sovrascritto")
                
                # Registra il plugin
                self.plugins[plugin_id] = plugin_instance
                
                # Salva i metadati
                category = plugin_meta.get('category', 'general')
                if category not in self.plugin_categories:
                    self.plugin_categories[category] = set()
                self.plugin_categories[category].add(plugin_id)
                
                # Registra i gestori di eventi
                if hasattr(plugin_instance, 'event_handlers'):
                    for event, handler in plugin_instance.event_handlers().items():
                        if event not in self.event_handlers:
                            self.event_handlers[event] = []
                        self.event_handlers[event].append(handler)
                
                # Registra i comandi
                if hasattr(plugin_instance, 'commands'):
                    plugin_commands = plugin_instance.commands()
                    if plugin_commands:
                        self.commands[plugin_id] = plugin_commands
                
                # Inizializza il plugin
                plugin_instance.initialize()
                
                logger.info(f"Plugin caricato: {plugin_meta.get('name', plugin_id)} ({plugin_id}) - {plugin_meta.get('version', '1.0.0')}")
                return True
                
            finally:
                # Ripristina il path
                if plugin_dir in sys.path:
                    sys.path.remove(plugin_dir)
                
        except Exception as e:
            logger.error(f"Errore nel caricamento del plugin {plugin_info.get('module', 'sconosciuto')}: {e}", exc_info=True)
            return False
    
    def load_all_plugins(self) -> int:
        """Carica tutti i plugin disponibili."""
        plugin_infos = self.discover_plugins()
        loaded_count = 0
        
        # Prima carica i plugin core
        for plugin_info in [p for p in plugin_infos if p.get('is_core', False)]:
            if self.load_plugin(plugin_info):
                loaded_count += 1
        
        # Poi carica i plugin non-core
        for plugin_info in [p for p in plugin_infos if not p.get('is_core', False)]:
            if self.load_plugin(plugin_info):
                loaded_count += 1
        
        logger.info(f"Caricati {loaded_count} plugin su {len(plugin_infos)} trovati")
        return loaded_count
    
    def get_plugin(self, plugin_id: str) -> Optional[PluginInterface]:
        """Ottiene un plugin dal suo ID."""
        return self.plugins.get(plugin_id)
    
    def get_plugins_by_category(self, category: str) -> List[str]:
        """Restituisce gli ID dei plugin di una determinata categoria."""
        return list(self.plugin_categories.get(category, set()))
    
    def get_all_commands(self) -> Dict[str, Dict[str, Callable]]:
        """Restituisce tutti i comandi disponibili, organizzati per plugin."""
        return self.commands
    
    def get_command(self, command_name: str) -> Optional[Callable]:
        """Cerca un comando in tutti i plugin e lo restituisce se trovato."""
        for plugin_commands in self.commands.values():
            if command_name in plugin_commands:
                return plugin_commands[command_name]
        return None
    
    def trigger_event(self, event_name: str, **kwargs) -> None:
        """Attiva tutti i gestori registrati per un evento."""
        if event_name in self.event_handlers:
            for handler in self.event_handlers[event_name]:
                try:
                    handler(**kwargs)
                except Exception as e:
                    logger.error(f"Errore nell'esecuzione dell'handler per {event_name}: {e}", exc_info=True)
    
    def execute_command(self, command_name: str, **kwargs) -> Any:
        """Esegue un comando registrato."""
        command_func = self.get_command(command_name)
        if command_func:
            try:
                return command_func(**kwargs)
            except Exception as e:
                logger.error(f"Errore nell'esecuzione del comando {command_name}: {e}", exc_info=True)
                return None
        return None
    
    def unload_plugin(self, plugin_id: str) -> bool:
        """Scarica un plugin dal suo ID."""
        if plugin_id not in self.plugins:
            logger.warning(f"Tentativo di scaricare plugin non caricato: {plugin_id}")
            return False
        
        try:
            # Ottieni l'istanza del plugin
            plugin = self.plugins[plugin_id]
            
            # Chiama il metodo di shutdown se implementato
            if hasattr(plugin, 'shutdown'):
                plugin.shutdown()
            
            # Rimuovi gli handler di eventi registrati da questo plugin
            for event, handlers in list(self.event_handlers.items()):
                self.event_handlers[event] = [h for h in handlers if h.__self__ != plugin]
                if not self.event_handlers[event]:
                    del self.event_handlers[event]
            
            # Rimuovi i comandi registrati
            if plugin_id in self.commands:
                del self.commands[plugin_id]
            
            # Rimuovi il plugin dalle categorie
            for category, plugins in list(self.plugin_categories.items()):
                if plugin_id in plugins:
                    plugins.remove(plugin_id)
                if not plugins:
                    del self.plugin_categories[category]
            
            # Rimuovi il plugin
            del self.plugins[plugin_id]
            
            logger.info(f"Plugin scaricato: {plugin_id}")
            return True
            
        except Exception as e:
            logger.error(f"Errore nello scaricamento del plugin {plugin_id}: {e}", exc_info=True)
            return False
    
    def reload_plugin(self, plugin_id: str) -> bool:
        """Ricarica un plugin dal suo ID."""
        if plugin_id not in self.plugins:
            logger.warning(f"Tentativo di ricaricare plugin non caricato: {plugin_id}")
            return False
        
        # Ottieni il percorso del file del plugin
        plugin = self.plugins[plugin_id]
        module = plugin.__class__.__module__
        module_obj = sys.modules.get(module)
        
        if not module_obj or not hasattr(module_obj, '__file__'):
            logger.error(f"Impossibile trovare il file del modulo per il plugin {plugin_id}")
            return False
        
        plugin_path = module_obj.__file__
        is_core = 'core' in plugin_path
        
        # Scarica il plugin
        if not self.unload_plugin(plugin_id):
            return False
        
        # Ricarica il plugin
        return self.load_plugin({
            'path': plugin_path,
            'module': module,
            'is_core': is_core
        })
    
    def shutdown_all(self) -> None:
        """Chiude ordinatamente tutti i plugin."""
        for plugin_id, plugin in list(self.plugins.items()):
            try:
                if hasattr(plugin, 'shutdown'):
                    plugin.shutdown()
            except Exception as e:
                logger.error(f"Errore nella chiusura del plugin {plugin_id}: {e}", exc_info=True)
        
        # Pulisci le strutture dati
        self.plugins.clear()
        self.event_handlers.clear()
        self.commands.clear()
        self.plugin_categories.clear()
        
        logger.info("Tutti i plugin sono stati chiusi")

# Istanza globale
plugin_manager = PluginManager() 