"""
Plugin per la programmazione e pianificazione di contenuti su diverse piattaforme
"""

import os
import json
import logging
import uuid
import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from flask import Blueprint, jsonify, request, render_template, current_app
import croniter

# Logger
logger = logging.getLogger(__name__)

# Path per i file della programmazione
SCHEDULER_DIR = "data/scheduler"
SCHEDULED_ITEMS_FILE = os.path.join(SCHEDULER_DIR, "scheduled_items.json")
HISTORY_FILE = os.path.join(SCHEDULER_DIR, "history.json")

# Blueprint
scheduler_blueprint = Blueprint('content_scheduler', __name__)

class ContentScheduler:
    """Gestore della programmazione dei contenuti"""
    
    def __init__(self, app):
        """
        Inizializza il gestore della programmazione
        
        Args:
            app: L'applicazione Flask/Quart
        """
        self.app = app
        self.scheduled_items = {}
        self.history = []
        self.scheduler_task = None
        self.last_check = 0
        
        # Crea le directory necessarie
        os.makedirs(SCHEDULER_DIR, exist_ok=True)
        
        # Carica gli elementi programmati e la cronologia
        self._load_scheduled_items()
        self._load_history()
        
        # Avvia il task di scheduling
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info("Gestore della programmazione contenuti inizializzato")
    
    def _load_scheduled_items(self):
        """Carica gli elementi programmati dal file"""
        if os.path.exists(SCHEDULED_ITEMS_FILE):
            try:
                with open(SCHEDULED_ITEMS_FILE, 'r') as f:
                    self.scheduled_items = json.load(f)
                logger.info(f"Caricati {len(self.scheduled_items)} elementi programmati")
            except Exception as e:
                logger.error(f"Errore nel caricamento degli elementi programmati: {e}")
                self.scheduled_items = {}
        else:
            self.scheduled_items = {}
    
    def _save_scheduled_items(self):
        """Salva gli elementi programmati nel file"""
        try:
            with open(SCHEDULED_ITEMS_FILE, 'w') as f:
                json.dump(self.scheduled_items, f, indent=2)
            logger.debug("Elementi programmati salvati")
        except Exception as e:
            logger.error(f"Errore nel salvataggio degli elementi programmati: {e}")
    
    def _load_history(self):
        """Carica la cronologia dal file"""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r') as f:
                    self.history = json.load(f)
                
                # Limita la cronologia a 1000 elementi
                if len(self.history) > 1000:
                    self.history = self.history[-1000:]
                
                logger.info(f"Caricati {len(self.history)} elementi nella cronologia")
            except Exception as e:
                logger.error(f"Errore nel caricamento della cronologia: {e}")
                self.history = []
        else:
            self.history = []
    
    def _save_history(self):
        """Salva la cronologia nel file"""
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.history, f, indent=2)
            logger.debug("Cronologia salvata")
        except Exception as e:
            logger.error(f"Errore nel salvataggio della cronologia: {e}")
    
    async def _scheduler_loop(self):
        """Loop di scheduling degli elementi programmati"""
        try:
            while True:
                try:
                    now = datetime.now()
                    current_time = now.timestamp()
                    
                    # Verifica se è passato almeno 1 secondo dall'ultimo controllo
                    if current_time - self.last_check < 1:
                        await asyncio.sleep(0.1)
                        continue
                    
                    self.last_check = current_time
                    
                    # Trova gli elementi da eseguire
                    to_execute = []
                    for item_id, item in self.scheduled_items.items():
                        if item.get("status") == "scheduled":
                            # Gestisce gli elementi con timestamp
                            if item.get("schedule_type") == "timestamp":
                                schedule_time = item.get("scheduled_time", 0)
                                if schedule_time <= current_time:
                                    to_execute.append(item_id)
                            
                            # Gestisce gli elementi con cron
                            elif item.get("schedule_type") == "cron":
                                cron_expr = item.get("cron_expression", "")
                                if cron_expr:
                                    try:
                                        # Calcola la prossima esecuzione
                                        cron = croniter.croniter(cron_expr, now - timedelta(minutes=1))
                                        next_exec = cron.get_next(datetime)
                                        
                                        # Verifica se è il momento di eseguire
                                        if next_exec <= now:
                                            to_execute.append(item_id)
                                            
                                            # Aggiorna il prossimo orario di esecuzione
                                            if item.get("repeat", False):
                                                item["last_execution"] = current_time
                                                # Salva immediatamente per evitare esecuzioni duplicate
                                                self._save_scheduled_items()
                                    except Exception as e:
                                        logger.error(f"Errore nella valutazione dell'espressione cron '{cron_expr}': {e}")
                    
                    # Esegui gli elementi
                    for item_id in to_execute:
                        await self._execute_scheduled_item(item_id)
                    
                    # Se sono stati eseguiti elementi, salva
                    if to_execute:
                        self._save_scheduled_items()
                        self._save_history()
                    
                    # Attendi 1 secondo prima del prossimo controllo
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Errore nel loop di scheduling: {e}")
                    await asyncio.sleep(5)  # Attendi 5 secondi in caso di errore
                    
        except asyncio.CancelledError:
            logger.info("Task di scheduling interrotto")
    
    async def _execute_scheduled_item(self, item_id):
        """
        Esegue un elemento programmato
        
        Args:
            item_id: ID dell'elemento da eseguire
        """
        try:
            # Ottieni l'elemento
            item = self.scheduled_items.get(item_id)
            if not item:
                logger.error(f"Elemento programmato non trovato: {item_id}")
                return
            
            logger.info(f"Esecuzione dell'elemento programmato: {item.get('title', item_id)}")
            
            # Aggiorna lo stato dell'elemento
            if item.get("repeat", False):
                # Per elementi ricorrenti, aggiorna l'ultima esecuzione
                item["last_execution"] = datetime.now().timestamp()
            else:
                # Per elementi una tantum, segna come completato
                item["status"] = "completed"
                item["completed_at"] = datetime.now().timestamp()
            
            # Ottieni la piattaforma di destinazione
            platform = item.get("platform", "")
            
            # Ottieni il connettore per la piattaforma
            connector = self._get_platform_connector(platform)
            if not connector:
                logger.error(f"Connettore non trovato per la piattaforma: {platform}")
                item["status"] = "failed"
                item["error"] = f"Connettore non trovato per la piattaforma: {platform}"
                return
            
            # Esegui l'azione in base al tipo di contenuto
            content_type = item.get("content_type", "")
            
            if content_type == "message":
                # Invia un messaggio
                result = await self._send_message(connector, item)
            elif content_type == "post":
                # Pubblica un post
                result = await self._publish_post(connector, item)
            else:
                logger.error(f"Tipo di contenuto non supportato: {content_type}")
                item["status"] = "failed"
                item["error"] = f"Tipo di contenuto non supportato: {content_type}"
                return
            
            # Gestisci il risultato
            if result.get("success", False):
                # Aggiungi alla cronologia
                history_item = {
                    "id": str(uuid.uuid4()),
                    "scheduled_item_id": item_id,
                    "title": item.get("title", ""),
                    "platform": platform,
                    "content_type": content_type,
                    "execution_time": datetime.now().timestamp(),
                    "success": True,
                    "content": item.get("content", {})
                }
                
                self.history.append(history_item)
            else:
                # In caso di errore, segna l'elemento come fallito
                if not item.get("repeat", False):
                    item["status"] = "failed"
                
                item["error"] = result.get("error", "Errore sconosciuto")
                
                # Aggiungi alla cronologia
                history_item = {
                    "id": str(uuid.uuid4()),
                    "scheduled_item_id": item_id,
                    "title": item.get("title", ""),
                    "platform": platform,
                    "content_type": content_type,
                    "execution_time": datetime.now().timestamp(),
                    "success": False,
                    "error": result.get("error", "Errore sconosciuto")
                }
                
                self.history.append(history_item)
                
                logger.error(f"Errore nell'esecuzione dell'elemento programmato {item_id}: {result.get('error', 'Errore sconosciuto')}")
        
        except Exception as e:
            logger.error(f"Errore nell'esecuzione dell'elemento programmato {item_id}: {e}")
            
            # Aggiorna lo stato dell'elemento
            item = self.scheduled_items.get(item_id)
            if item and not item.get("repeat", False):
                item["status"] = "failed"
                item["error"] = str(e)
    
    def _get_platform_connector(self, platform):
        """
        Ottiene il connettore per una piattaforma
        
        Args:
            platform: Nome della piattaforma
            
        Returns:
            Il connettore, o None se non trovato
        """
        connectors = {
            "youtube": getattr(self.app, "youtube_connector", None),
            "telegram": getattr(self.app, "telegram_connector", None),
            "whatsapp": getattr(self.app, "whatsapp_connector", None),
            "discord": getattr(self.app, "discord_connector", None)
        }
        
        return connectors.get(platform.lower())
    
    async def _send_message(self, connector, item):
        """
        Invia un messaggio
        
        Args:
            connector: Il connettore da utilizzare
            item: L'elemento programmato
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            content = item.get("content", {})
            platform = item.get("platform", "").lower()
            
            # Ottieni i dettagli specifici della piattaforma
            if platform == "youtube":
                # Per YouTube, è necessario il messaggio e il liveid
                message = content.get("message", "")
                live_id = content.get("live_id", "")
                
                if not message or not live_id:
                    return {"success": False, "error": "Messaggio o live_id mancante"}
                
                # Invia il messaggio
                result = await connector.send_chat_message(live_id, message)
                return {"success": result.get("success", False), "error": result.get("error", "")}
                
            elif platform == "telegram":
                # Per Telegram, è necessario il messaggio e la chat_id
                message = content.get("message", "")
                chat_id = content.get("chat_id", "")
                
                if not message or not chat_id:
                    return {"success": False, "error": "Messaggio o chat_id mancante"}
                
                # Invia il messaggio
                result = await connector.send_message(chat_id, message)
                return {"success": result.get("success", False), "error": result.get("error", "")}
                
            elif platform == "whatsapp":
                # Per WhatsApp, è necessario il messaggio e il numero
                message = content.get("message", "")
                phone = content.get("phone", "")
                
                if not message or not phone:
                    return {"success": False, "error": "Messaggio o numero di telefono mancante"}
                
                # Invia il messaggio
                result = await connector.send_message(phone, message)
                return {"success": result.get("success", False), "error": result.get("error", "")}
                
            elif platform == "discord":
                # Per Discord, è necessario il messaggio e il canale
                message = content.get("message", "")
                channel_id = content.get("channel_id", "")
                
                if not message or not channel_id:
                    return {"success": False, "error": "Messaggio o ID del canale mancante"}
                
                # Invia il messaggio
                result = await connector.send_message(channel_id, message)
                return {"success": result.get("success", False), "error": result.get("error", "")}
                
            else:
                return {"success": False, "error": f"Piattaforma non supportata: {platform}"}
                
        except Exception as e:
            logger.error(f"Errore nell'invio del messaggio: {e}")
            return {"success": False, "error": str(e)}
    
    async def _publish_post(self, connector, item):
        """
        Pubblica un post
        
        Args:
            connector: Il connettore da utilizzare
            item: L'elemento programmato
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            content = item.get("content", {})
            platform = item.get("platform", "").lower()
            
            # Ottieni i dettagli specifici della piattaforma
            if platform == "youtube":
                # Per ora YouTube non supporta post programmati nella nostra implementazione
                return {"success": False, "error": "La pubblicazione di post su YouTube non è supportata"}
                
            elif platform == "telegram":
                # Per Telegram, è necessario il messaggio e la chat_id
                message = content.get("message", "")
                chat_id = content.get("chat_id", "")
                
                if not message or not chat_id:
                    return {"success": False, "error": "Messaggio o chat_id mancante"}
                
                # Verifica se ci sono media
                media = content.get("media", [])
                
                if media:
                    # Invia un messaggio con media
                    result = await connector.send_media(chat_id, media, message)
                else:
                    # Invia un messaggio di testo
                    result = await connector.send_message(chat_id, message)
                
                return {"success": result.get("success", False), "error": result.get("error", "")}
                
            elif platform == "whatsapp":
                # Per WhatsApp, è necessario il messaggio e il numero
                message = content.get("message", "")
                phone = content.get("phone", "")
                
                if not message or not phone:
                    return {"success": False, "error": "Messaggio o numero di telefono mancante"}
                
                # Verifica se ci sono media
                media = content.get("media", [])
                
                if media:
                    # Invia un messaggio con media
                    result = await connector.send_media(phone, media[0], message)
                else:
                    # Invia un messaggio di testo
                    result = await connector.send_message(phone, message)
                
                return {"success": result.get("success", False), "error": result.get("error", "")}
                
            elif platform == "discord":
                # Per Discord, è necessario il messaggio e il canale
                message = content.get("message", "")
                channel_id = content.get("channel_id", "")
                
                if not message or not channel_id:
                    return {"success": False, "error": "Messaggio o ID del canale mancante"}
                
                # Verifica se ci sono media
                media = content.get("media", [])
                
                if media:
                    # Invia un messaggio con media
                    result = await connector.send_file(channel_id, media[0], message)
                else:
                    # Invia un messaggio di testo
                    result = await connector.send_message(channel_id, message)
                
                return {"success": result.get("success", False), "error": result.get("error", "")}
                
            else:
                return {"success": False, "error": f"Piattaforma non supportata: {platform}"}
                
        except Exception as e:
            logger.error(f"Errore nella pubblicazione del post: {e}")
            return {"success": False, "error": str(e)}
    
    async def schedule_item(self, data):
        """
        Programma un nuovo elemento
        
        Args:
            data: Dati dell'elemento da programmare
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica i campi obbligatori
            required_fields = ["title", "platform", "content_type", "content", "schedule_type"]
            for field in required_fields:
                if field not in data:
                    return {"success": False, "error": f"Campo obbligatorio mancante: {field}"}
            
            # Verifica che la piattaforma sia supportata
            platform = data.get("platform", "").lower()
            if platform not in ["youtube", "telegram", "whatsapp", "discord"]:
                return {"success": False, "error": f"Piattaforma non supportata: {platform}"}
            
            # Verifica che il tipo di contenuto sia supportato
            content_type = data.get("content_type", "")
            if content_type not in ["message", "post"]:
                return {"success": False, "error": f"Tipo di contenuto non supportato: {content_type}"}
            
            # Verifica il tipo di scheduling
            schedule_type = data.get("schedule_type", "")
            if schedule_type not in ["timestamp", "cron"]:
                return {"success": False, "error": f"Tipo di scheduling non supportato: {schedule_type}"}
            
            # Verifica i parametri di scheduling
            if schedule_type == "timestamp":
                if "scheduled_time" not in data:
                    return {"success": False, "error": "Campo obbligatorio mancante: scheduled_time"}
                
                # Verifica che il timestamp sia nel futuro
                if data["scheduled_time"] < datetime.now().timestamp():
                    return {"success": False, "error": "Il tempo di scheduling deve essere nel futuro"}
                    
            elif schedule_type == "cron":
                if "cron_expression" not in data:
                    return {"success": False, "error": "Campo obbligatorio mancante: cron_expression"}
                
                # Verifica la validità dell'espressione cron
                try:
                    croniter.croniter(data["cron_expression"], datetime.now())
                except Exception as e:
                    return {"success": False, "error": f"Espressione cron non valida: {e}"}
            
            # Genera un ID univoco per l'elemento
            item_id = str(uuid.uuid4())
            
            # Crea l'elemento programmato
            item = {
                "id": item_id,
                "title": data["title"],
                "description": data.get("description", ""),
                "platform": platform,
                "content_type": content_type,
                "content": data["content"],
                "schedule_type": schedule_type,
                "status": "scheduled",
                "created_at": datetime.now().timestamp(),
                "created_by": data.get("created_by", "system")
            }
            
            # Aggiungi parametri specifici per il tipo di scheduling
            if schedule_type == "timestamp":
                item["scheduled_time"] = data["scheduled_time"]
            elif schedule_type == "cron":
                item["cron_expression"] = data["cron_expression"]
                item["repeat"] = True
                item["last_execution"] = 0
            
            # Parametri opzionali
            if "tags" in data:
                item["tags"] = data["tags"]
                
            if "priority" in data:
                item["priority"] = data["priority"]
            
            # Registra l'elemento
            self.scheduled_items[item_id] = item
            
            # Salva gli elementi programmati
            self._save_scheduled_items()
            
            return {"success": True, "item": item}
            
        except Exception as e:
            logger.error(f"Errore nella programmazione dell'elemento: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_scheduled_item(self, item_id):
        """
        Ottiene un elemento programmato
        
        Args:
            item_id: ID dell'elemento
            
        Returns:
            dict: L'elemento, o None se non trovato
        """
        return self.scheduled_items.get(item_id)
    
    async def update_scheduled_item(self, item_id, data):
        """
        Aggiorna un elemento programmato
        
        Args:
            item_id: ID dell'elemento
            data: Dati aggiornati
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che l'elemento esista
            item = self.scheduled_items.get(item_id)
            if not item:
                return {"success": False, "error": "Elemento non trovato"}
            
            # Verifica che l'elemento sia in stato "scheduled"
            if item.get("status") != "scheduled":
                return {"success": False, "error": "Impossibile modificare un elemento non in stato 'scheduled'"}
            
            # Aggiorna i campi modificabili
            modifiable_fields = ["title", "description", "content", "tags", "priority"]
            for field in modifiable_fields:
                if field in data:
                    item[field] = data[field]
            
            # Aggiorna i parametri di scheduling
            if "schedule_type" in data:
                # Verifica il tipo di scheduling
                schedule_type = data["schedule_type"]
                if schedule_type not in ["timestamp", "cron"]:
                    return {"success": False, "error": f"Tipo di scheduling non supportato: {schedule_type}"}
                
                item["schedule_type"] = schedule_type
                
                # Verifica i parametri di scheduling
                if schedule_type == "timestamp":
                    if "scheduled_time" not in data:
                        return {"success": False, "error": "Campo obbligatorio mancante: scheduled_time"}
                    
                    # Verifica che il timestamp sia nel futuro
                    if data["scheduled_time"] < datetime.now().timestamp():
                        return {"success": False, "error": "Il tempo di scheduling deve essere nel futuro"}
                    
                    item["scheduled_time"] = data["scheduled_time"]
                    item.pop("cron_expression", None)
                    item.pop("repeat", None)
                    item.pop("last_execution", None)
                    
                elif schedule_type == "cron":
                    if "cron_expression" not in data:
                        return {"success": False, "error": "Campo obbligatorio mancante: cron_expression"}
                    
                    # Verifica la validità dell'espressione cron
                    try:
                        croniter.croniter(data["cron_expression"], datetime.now())
                    except Exception as e:
                        return {"success": False, "error": f"Espressione cron non valida: {e}"}
                    
                    item["cron_expression"] = data["cron_expression"]
                    item["repeat"] = True
                    item.pop("scheduled_time", None)
                    
                    # Se non esiste, inizializza last_execution
                    if "last_execution" not in item:
                        item["last_execution"] = 0
            
            # Aggiorna il timestamp di modifica
            item["updated_at"] = datetime.now().timestamp()
            
            # Salva gli elementi programmati
            self._save_scheduled_items()
            
            return {"success": True, "item": item}
            
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento dell'elemento: {e}")
            return {"success": False, "error": str(e)}
    
    async def delete_scheduled_item(self, item_id):
        """
        Elimina un elemento programmato
        
        Args:
            item_id: ID dell'elemento
            
        Returns:
            dict: Risultato dell'operazione
        """
        try:
            # Verifica che l'elemento esista
            if item_id not in self.scheduled_items:
                return {"success": False, "error": "Elemento non trovato"}
            
            # Elimina l'elemento
            del self.scheduled_items[item_id]
            
            # Salva gli elementi programmati
            self._save_scheduled_items()
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"Errore nell'eliminazione dell'elemento: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_scheduled_items(self, filters=None):
        """
        Ottiene tutti gli elementi programmati, opzionalmente filtrati
        
        Args:
            filters: Filtri da applicare
            
        Returns:
            list: Lista degli elementi programmati
        """
        try:
            # Converti il dizionario in lista
            items = list(self.scheduled_items.values())
            
            # Applica i filtri se presenti
            if filters:
                filtered_items = []
                for item in items:
                    match = True
                    
                    # Filtra per piattaforma
                    if "platform" in filters and item.get("platform") != filters["platform"]:
                        match = False
                    
                    # Filtra per tipo di contenuto
                    if "content_type" in filters and item.get("content_type") != filters["content_type"]:
                        match = False
                    
                    # Filtra per stato
                    if "status" in filters and item.get("status") != filters["status"]:
                        match = False
                    
                    # Filtra per tag
                    if "tag" in filters and "tags" in item and filters["tag"] not in item["tags"]:
                        match = False
                    
                    # Filtra per testo
                    if "search" in filters:
                        search_text = filters["search"].lower()
                        title = item.get("title", "").lower()
                        description = item.get("description", "").lower()
                        
                        if search_text not in title and search_text not in description:
                            match = False
                    
                    if match:
                        filtered_items.append(item)
                
                return filtered_items
            else:
                return items
                
        except Exception as e:
            logger.error(f"Errore nel recupero degli elementi programmati: {e}")
            return []
    
    async def get_history(self, filters=None, limit=100):
        """
        Ottiene la cronologia degli elementi eseguiti, opzionalmente filtrata
        
        Args:
            filters: Filtri da applicare
            limit: Numero massimo di elementi da restituire
            
        Returns:
            list: Lista degli elementi della cronologia
        """
        try:
            # Applica i filtri se presenti
            if filters:
                filtered_history = []
                for item in self.history:
                    match = True
                    
                    # Filtra per piattaforma
                    if "platform" in filters and item.get("platform") != filters["platform"]:
                        match = False
                    
                    # Filtra per tipo di contenuto
                    if "content_type" in filters and item.get("content_type") != filters["content_type"]:
                        match = False
                    
                    # Filtra per successo
                    if "success" in filters and item.get("success") != filters["success"]:
                        match = False
                    
                    # Filtra per ID dell'elemento programmato
                    if "scheduled_item_id" in filters and item.get("scheduled_item_id") != filters["scheduled_item_id"]:
                        match = False
                    
                    # Filtra per intervallo di date
                    if "from_date" in filters:
                        from_timestamp = datetime.fromisoformat(filters["from_date"]).timestamp()
                        if item.get("execution_time", 0) < from_timestamp:
                            match = False
                    
                    if "to_date" in filters:
                        to_timestamp = datetime.fromisoformat(filters["to_date"]).timestamp()
                        if item.get("execution_time", 0) > to_timestamp:
                            match = False
                    
                    if match:
                        filtered_history.append(item)
                
                # Ordina per execution_time discendente (più recenti prima)
                filtered_history.sort(key=lambda x: x.get("execution_time", 0), reverse=True)
                
                # Limita il numero di risultati
                return filtered_history[:limit]
            else:
                # Ordina per execution_time discendente (più recenti prima)
                sorted_history = sorted(self.history, key=lambda x: x.get("execution_time", 0), reverse=True)
                
                # Limita il numero di risultati
                return sorted_history[:limit]
                
        except Exception as e:
            logger.error(f"Errore nel recupero della cronologia: {e}")
            return []

def setup(app):
    """
    Inizializza il plugin per la programmazione dei contenuti
    
    Args:
        app: L'applicazione Flask/Quart
    """
    # Inizializza il gestore della programmazione
    scheduler = ContentScheduler(app)
    
    # Registra il gestore nell'app
    app.content_scheduler = scheduler
    
    # Registra il blueprint
    app.register_blueprint(scheduler_blueprint, url_prefix='/scheduler')
    
    # Definisci le route
    
    @scheduler_blueprint.route('/', methods=['GET'])
    async def scheduler_page():
        """Renderizza la pagina di gestione della programmazione"""
        return render_template('content_scheduler.html', page_title="Programmazione Contenuti")
    
    @scheduler_blueprint.route('/api/items', methods=['GET'])
    async def get_scheduled_items():
        """API per ottenere gli elementi programmati"""
        filters = {}
        
        # Estrai i filtri dalla query string
        if request.args.get('platform'):
            filters['platform'] = request.args.get('platform')
        
        if request.args.get('content_type'):
            filters['content_type'] = request.args.get('content_type')
        
        if request.args.get('status'):
            filters['status'] = request.args.get('status')
        
        if request.args.get('tag'):
            filters['tag'] = request.args.get('tag')
        
        if request.args.get('search'):
            filters['search'] = request.args.get('search')
        
        items = await scheduler.get_scheduled_items(filters)
        return jsonify(items)
    
    @scheduler_blueprint.route('/api/items/<item_id>', methods=['GET'])
    async def get_scheduled_item(item_id):
        """API per ottenere un elemento programmato specifico"""
        item = await scheduler.get_scheduled_item(item_id)
        if item:
            return jsonify(item)
        else:
            return jsonify({"error": "Elemento non trovato"}), 404
    
    @scheduler_blueprint.route('/api/items', methods=['POST'])
    async def schedule_item():
        """API per programmare un nuovo elemento"""
        data = await request.json
        
        # Chiamata al metodo di scheduling
        result = await scheduler.schedule_item(data)
        
        if result.get('success', False):
            return jsonify(result), 201
        else:
            return jsonify(result), 400
    
    @scheduler_blueprint.route('/api/items/<item_id>', methods=['PUT'])
    async def update_scheduled_item(item_id):
        """API per aggiornare un elemento programmato"""
        data = await request.json
        
        # Chiamata al metodo di aggiornamento
        result = await scheduler.update_scheduled_item(item_id, data)
        
        if result.get('success', False):
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @scheduler_blueprint.route('/api/items/<item_id>', methods=['DELETE'])
    async def delete_scheduled_item(item_id):
        """API per eliminare un elemento programmato"""
        result = await scheduler.delete_scheduled_item(item_id)
        
        if result.get('success', False):
            return jsonify(result)
        else:
            return jsonify(result), 400
    
    @scheduler_blueprint.route('/api/history', methods=['GET'])
    async def get_history():
        """API per ottenere la cronologia"""
        filters = {}
        
        # Estrai i filtri dalla query string
        if request.args.get('platform'):
            filters['platform'] = request.args.get('platform')
        
        if request.args.get('content_type'):
            filters['content_type'] = request.args.get('content_type')
        
        if request.args.get('success') is not None:
            filters['success'] = request.args.get('success').lower() == 'true'
        
        if request.args.get('scheduled_item_id'):
            filters['scheduled_item_id'] = request.args.get('scheduled_item_id')
        
        if request.args.get('from_date'):
            filters['from_date'] = request.args.get('from_date')
        
        if request.args.get('to_date'):
            filters['to_date'] = request.args.get('to_date')
        
        # Estrai il limite
        limit = request.args.get('limit', 100, type=int)
        
        history = await scheduler.get_history(filters, limit)
        return jsonify(history)
    
    @app.teardown_appcontext
    async def shutdown_scheduler(exception=None):
        """Chiude il gestore della programmazione alla chiusura dell'app"""
        if hasattr(app, 'content_scheduler'):
            await app.content_scheduler.close() 