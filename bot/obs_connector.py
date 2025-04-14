import os
import json
import logging
import asyncio
import simpleobsws
from typing import Dict, List, Optional, Any, Callable

# Configurazione logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/obs_connector.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("OBSConnector")

class OBSConnector:
    """Connettore per OBS Studio che permette il controllo da remoto dello streaming"""
    
    def __init__(self, config: Dict[str, Any], event_callback: Optional[Callable] = None):
        """
        Inizializza il connettore OBS
        
        Args:
            config: Configurazione del connettore
            event_callback: Callback per gestire gli eventi OBS
        """
        # Inizializza le variabili
        self.config = config
        self.host = config.get("obs_host", "localhost")
        self.port = config.get("obs_port", 4455)
        self.password = config.get("obs_password", "")
        self.event_callback = event_callback
        
        # Impostazioni sicurezza websocket
        self.ws_protocol = "wss" if config.get("obs_use_ssl", False) else "ws"
        self.connection_url = f"{self.ws_protocol}://{self.host}:{self.port}"
        
        # Stato connessione
        self.is_connected = False
        
        # Client websocket
        self.ws = None
        
        # Task di connessione
        self.connection_task = None
        
        # Crea le directory necessarie
        os.makedirs("logs", exist_ok=True)
        
        logger.info(f"Connettore OBS inizializzato con URL: {self.connection_url}")
    
    async def connect(self) -> bool:
        """
        Connette il client al server OBS WebSocket
        
        Returns:
            bool: True se la connessione è riuscita, False altrimenti
        """
        try:
            # Crea il client simpleobsws
            self.ws = simpleobsws.WebSocketClient(
                url=self.connection_url,
                password=self.password,
                identification_parameters={"rpcVersion": 1}
            )
            
            # Connessione a OBS
            await self.ws.connect()
            
            # Verifica che la connessione sia riuscita
            if await self.ws.wait_until_identified():
                self.is_connected = True
                logger.info("Connesso con successo a OBS Studio")
                
                # Avvia il task per gestire gli eventi
                self.connection_task = asyncio.create_task(self._event_listener())
                
                return True
            else:
                logger.error("Impossibile identificarsi con OBS Studio")
                return False
                
        except Exception as e:
            logger.error(f"Errore nella connessione a OBS: {e}")
            self.is_connected = False
            return False
    
    async def disconnect(self) -> bool:
        """
        Disconnette il client dal server OBS WebSocket
        
        Returns:
            bool: True se la disconnessione è riuscita, False altrimenti
        """
        try:
            if self.connection_task:
                self.connection_task.cancel()
                try:
                    await self.connection_task
                except asyncio.CancelledError:
                    pass
                self.connection_task = None
            
            if self.ws:
                await self.ws.disconnect()
                self.is_connected = False
                logger.info("Disconnesso da OBS Studio")
                return True
            
            return True
            
        except Exception as e:
            logger.error(f"Errore nella disconnessione da OBS: {e}")
            self.is_connected = False
            return False
    
    async def _event_listener(self):
        """Task per ascoltare gli eventi OBS"""
        try:
            while self.is_connected:
                try:
                    # Ricevi eventi dal WebSocket
                    event = await self.ws.recv()
                    
                    # Se è un evento, invia al callback
                    if event and "eventType" in event and self.event_callback:
                        try:
                            await self.event_callback(event)
                        except Exception as e:
                            logger.error(f"Errore nel callback dell'evento: {e}")
                
                except asyncio.CancelledError:
                    # Task annullato
                    break
                except Exception as e:
                    logger.error(f"Errore nella ricezione degli eventi: {e}")
                    await asyncio.sleep(5)  # Attendi prima di riprovare
        
        except asyncio.CancelledError:
            # Task annullato
            pass
        
        self.is_connected = False
    
    async def get_version(self) -> Dict[str, Any]:
        """
        Ottiene la versione di OBS Studio
        
        Returns:
            Dict: Informazioni sulla versione di OBS
        """
        if not self.is_connected or not self.ws:
            logger.error("Non connesso a OBS")
            return {"error": "Non connesso a OBS"}
        
        try:
            response = await self.ws.call({"requestType": "GetVersion"})
            
            if response.ok():
                return response.responseData
            else:
                logger.error(f"Errore nella richiesta della versione: {response.responseData}")
                return {"error": response.responseData}
                
        except Exception as e:
            logger.error(f"Errore nella richiesta della versione: {e}")
            return {"error": str(e)}
    
    async def start_streaming(self) -> bool:
        """
        Avvia lo streaming in OBS
        
        Returns:
            bool: True se lo streaming è stato avviato con successo, False altrimenti
        """
        if not self.is_connected or not self.ws:
            logger.error("Non connesso a OBS")
            return False
        
        try:
            # Prima controlla se lo streaming è già attivo
            status_response = await self.ws.call({"requestType": "GetStreamStatus"})
            
            if status_response.ok() and status_response.responseData.get("outputActive", False):
                logger.info("Streaming già attivo")
                return True
            
            # Avvia lo streaming
            response = await self.ws.call({"requestType": "StartStream"})
            
            if response.ok():
                logger.info("Streaming avviato con successo")
                return True
            else:
                logger.error(f"Errore nell'avvio dello streaming: {response.responseData}")
                return False
                
        except Exception as e:
            logger.error(f"Errore nell'avvio dello streaming: {e}")
            return False
    
    async def stop_streaming(self) -> bool:
        """
        Ferma lo streaming in OBS
        
        Returns:
            bool: True se lo streaming è stato fermato con successo, False altrimenti
        """
        if not self.is_connected or not self.ws:
            logger.error("Non connesso a OBS")
            return False
        
        try:
            # Prima controlla se lo streaming è attivo
            status_response = await self.ws.call({"requestType": "GetStreamStatus"})
            
            if status_response.ok() and not status_response.responseData.get("outputActive", False):
                logger.info("Streaming già fermo")
                return True
            
            # Ferma lo streaming
            response = await self.ws.call({"requestType": "StopStream"})
            
            if response.ok():
                logger.info("Streaming fermato con successo")
                return True
            else:
                logger.error(f"Errore nell'arresto dello streaming: {response.responseData}")
                return False
                
        except Exception as e:
            logger.error(f"Errore nell'arresto dello streaming: {e}")
            return False
    
    async def set_current_scene(self, scene_name: str) -> bool:
        """
        Imposta la scena corrente in OBS
        
        Args:
            scene_name: Nome della scena da impostare
            
        Returns:
            bool: True se la scena è stata impostata con successo, False altrimenti
        """
        if not self.is_connected or not self.ws:
            logger.error("Non connesso a OBS")
            return False
        
        try:
            response = await self.ws.call({
                "requestType": "SetCurrentProgramScene",
                "requestData": {
                    "sceneName": scene_name
                }
            })
            
            if response.ok():
                logger.info(f"Scena impostata con successo: {scene_name}")
                return True
            else:
                logger.error(f"Errore nell'impostazione della scena: {response.responseData}")
                return False
                
        except Exception as e:
            logger.error(f"Errore nell'impostazione della scena: {e}")
            return False
    
    async def get_scenes(self) -> List[Dict[str, Any]]:
        """
        Ottiene la lista delle scene in OBS
        
        Returns:
            List: Lista delle scene disponibili
        """
        if not self.is_connected or not self.ws:
            logger.error("Non connesso a OBS")
            return []
        
        try:
            response = await self.ws.call({"requestType": "GetSceneList"})
            
            if response.ok():
                scenes = response.responseData.get("scenes", [])
                logger.info(f"Ottenute {len(scenes)} scene")
                return scenes
            else:
                logger.error(f"Errore nella richiesta delle scene: {response.responseData}")
                return []
                
        except Exception as e:
            logger.error(f"Errore nella richiesta delle scene: {e}")
            return []
    
    async def get_stream_status(self) -> Dict[str, Any]:
        """
        Ottiene lo stato dello streaming
        
        Returns:
            Dict: Stato dello streaming
        """
        if not self.is_connected or not self.ws:
            logger.error("Non connesso a OBS")
            return {"active": False, "error": "Non connesso a OBS"}
        
        try:
            response = await self.ws.call({"requestType": "GetStreamStatus"})
            
            if response.ok():
                return response.responseData
            else:
                logger.error(f"Errore nella richiesta dello stato: {response.responseData}")
                return {"active": False, "error": response.responseData}
                
        except Exception as e:
            logger.error(f"Errore nella richiesta dello stato: {e}")
            return {"active": False, "error": str(e)}
    
    async def toggle_source_visibility(self, scene_name: str, source_name: str) -> bool:
        """
        Attiva/disattiva la visibilità di una fonte in una scena
        
        Args:
            scene_name: Nome della scena
            source_name: Nome della fonte
            
        Returns:
            bool: True se la visibilità è stata modificata con successo, False altrimenti
        """
        if not self.is_connected or not self.ws:
            logger.error("Non connesso a OBS")
            return False
        
        try:
            # Prima ottieni lo stato attuale della fonte
            response = await self.ws.call({
                "requestType": "GetSceneItemEnabled",
                "requestData": {
                    "sceneName": scene_name,
                    "sceneItemId": await self._get_scene_item_id(scene_name, source_name)
                }
            })
            
            if not response.ok():
                logger.error(f"Errore nella richiesta dello stato della fonte: {response.responseData}")
                return False
            
            # Stato attuale
            current_state = response.responseData.get("sceneItemEnabled", False)
            
            # Inverti lo stato
            response = await self.ws.call({
                "requestType": "SetSceneItemEnabled",
                "requestData": {
                    "sceneName": scene_name,
                    "sceneItemId": await self._get_scene_item_id(scene_name, source_name),
                    "sceneItemEnabled": not current_state
                }
            })
            
            if response.ok():
                logger.info(f"Visibilità modificata per {source_name} in {scene_name}: {not current_state}")
                return True
            else:
                logger.error(f"Errore nella modifica della visibilità: {response.responseData}")
                return False
                
        except Exception as e:
            logger.error(f"Errore nella modifica della visibilità: {e}")
            return False
    
    async def _get_scene_item_id(self, scene_name: str, source_name: str) -> int:
        """
        Ottiene l'ID di una fonte in una scena
        
        Args:
            scene_name: Nome della scena
            source_name: Nome della fonte
            
        Returns:
            int: ID della fonte nella scena
        """
        try:
            response = await self.ws.call({
                "requestType": "GetSceneItemList",
                "requestData": {
                    "sceneName": scene_name
                }
            })
            
            if response.ok():
                scene_items = response.responseData.get("sceneItems", [])
                
                for item in scene_items:
                    if item.get("sourceName") == source_name:
                        return item.get("sceneItemId", 0)
                
                logger.error(f"Fonte non trovata: {source_name}")
                return 0
            else:
                logger.error(f"Errore nella richiesta delle fonti: {response.responseData}")
                return 0
                
        except Exception as e:
            logger.error(f"Errore nella ricerca dell'ID della fonte: {e}")
            return 0

# Funzione per creare un'istanza del connettore OBS
def create_obs_connector(config: Dict[str, Any], event_callback: Optional[Callable] = None) -> OBSConnector:
    """
    Crea un'istanza del connettore OBS
    
    Args:
        config: Configurazione del connettore
        event_callback: Callback per gestire gli eventi OBS
        
    Returns:
        OBSConnector: Istanza del connettore OBS
    """
    return OBSConnector(config, event_callback) 