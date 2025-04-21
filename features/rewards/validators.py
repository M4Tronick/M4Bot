#!/usr/bin/env python3
"""
Validatori di requisiti per il sistema di giveaway di M4Bot.

Questo modulo contiene le classi che verificano se un utente soddisfa i requisiti
per partecipare a un giveaway, come essere seguaci, iscritti, o avere un certo
numero di punti o tempo di visione.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple

# Logger
logger = logging.getLogger('m4bot.rewards.validators')

class RequirementValidator:
    """Classe di base per la validazione di un singolo requisito."""
    
    def __init__(self, db_pool=None):
        """
        Inizializza il validatore.
        
        Args:
            db_pool: Pool di connessioni al database
        """
        self.db_pool = db_pool
    
    async def validate(self, user_id: str, channel_id: str, requirement: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Valida se un utente soddisfa un requisito specifico.
        
        Args:
            user_id: ID dell'utente
            channel_id: ID del canale
            requirement: Dettagli del requisito
            
        Returns:
            Tuple[bool, str]: (valido, motivo)
        """
        # Da implementare nelle sottoclassi
        return False, "Validatore non implementato"

class FollowerValidator(RequirementValidator):
    """Validatore per verificare se un utente è un follower del canale."""
    
    async def validate(self, user_id: str, channel_id: str, requirement: Dict[str, Any]) -> Tuple[bool, str]:
        """Verifica se l'utente è un follower."""
        if not self.db_pool:
            return False, "Database non disponibile"
            
        try:
            async with self.db_pool.acquire() as conn:
                # Controlla se l'utente è un follower
                row = await conn.fetchrow(
                    """
                    SELECT 1 FROM followers
                    WHERE channel_id = $1 AND user_id = $2
                    """,
                    channel_id, user_id
                )
                
                if row:
                    return True, ""
                else:
                    return False, "Devi essere un follower del canale per partecipare"
        
        except Exception as e:
            logger.error(f"Errore nella validazione del follower: {e}")
            return False, "Errore nella verifica dei requisiti di follower"

class SubscriberValidator(RequirementValidator):
    """Validatore per verificare se un utente è iscritto al canale."""
    
    async def validate(self, user_id: str, channel_id: str, requirement: Dict[str, Any]) -> Tuple[bool, str]:
        """Verifica se l'utente è iscritto."""
        if not self.db_pool:
            return False, "Database non disponibile"
            
        try:
            async with self.db_pool.acquire() as conn:
                # Controlla se l'utente è iscritto
                row = await conn.fetchrow(
                    """
                    SELECT tier FROM subscriptions
                    WHERE channel_id = $1 AND user_id = $2 AND active = true
                    """,
                    channel_id, user_id
                )
                
                if row:
                    # Se richiesto un tier specifico
                    required_tier = requirement.get('tier')
                    if required_tier and int(row['tier']) < int(required_tier):
                        return False, f"Devi essere iscritto al tier {required_tier} o superiore"
                    return True, ""
                else:
                    return False, "Devi essere iscritto al canale per partecipare"
        
        except Exception as e:
            logger.error(f"Errore nella validazione dell'iscrizione: {e}")
            return False, "Errore nella verifica dei requisiti di iscrizione"

class PointsValidator(RequirementValidator):
    """Validatore per verificare se un utente ha un certo numero di punti canale."""
    
    async def validate(self, user_id: str, channel_id: str, requirement: Dict[str, Any]) -> Tuple[bool, str]:
        """Verifica se l'utente ha i punti richiesti."""
        if not self.db_pool:
            return False, "Database non disponibile"
            
        # Ottieni il valore minimo richiesto
        min_points = requirement.get('value')
        if not min_points or not min_points.isdigit():
            return False, "Requisito punti non valido"
            
        min_points = int(min_points)
        
        try:
            async with self.db_pool.acquire() as conn:
                # Controlla i punti dell'utente
                row = await conn.fetchrow(
                    """
                    SELECT points FROM channel_points
                    WHERE channel_id = $1 AND user_id = $2
                    """,
                    channel_id, user_id
                )
                
                if row:
                    user_points = row['points']
                    if user_points >= min_points:
                        return True, ""
                    else:
                        return False, f"Devi avere almeno {min_points} punti (hai {user_points})"
                else:
                    return False, f"Devi avere almeno {min_points} punti (non hai punti)"
        
        except Exception as e:
            logger.error(f"Errore nella validazione dei punti: {e}")
            return False, "Errore nella verifica dei requisiti di punti"

class WatchTimeValidator(RequirementValidator):
    """Validatore per verificare se un utente ha visto il canale per un certo tempo."""
    
    async def validate(self, user_id: str, channel_id: str, requirement: Dict[str, Any]) -> Tuple[bool, str]:
        """Verifica se l'utente ha il tempo di visione richiesto."""
        if not self.db_pool:
            return False, "Database non disponibile"
            
        # Ottieni il valore minimo richiesto (in secondi)
        min_seconds = requirement.get('value')
        if not min_seconds or not min_seconds.isdigit():
            return False, "Requisito tempo di visione non valido"
            
        min_seconds = int(min_seconds)
        
        try:
            async with self.db_pool.acquire() as conn:
                # Controlla il tempo di visione dell'utente
                row = await conn.fetchrow(
                    """
                    SELECT watch_time FROM channel_points
                    WHERE channel_id = $1 AND user_id = $2
                    """,
                    channel_id, user_id
                )
                
                if row:
                    user_watch_time = row['watch_time']
                    if user_watch_time >= min_seconds:
                        return True, ""
                    else:
                        # Converti in ore per un messaggio più leggibile
                        min_hours = min_seconds / 3600
                        user_hours = user_watch_time / 3600
                        return False, f"Devi aver guardato il canale per almeno {min_hours:.1f} ore (hai {user_hours:.1f} ore)"
                else:
                    min_hours = min_seconds / 3600
                    return False, f"Devi aver guardato il canale per almeno {min_hours:.1f} ore"
        
        except Exception as e:
            logger.error(f"Errore nella validazione del tempo di visione: {e}")
            return False, "Errore nella verifica dei requisiti di tempo di visione"

class CustomValidator(RequirementValidator):
    """Validatore per requisiti personalizzati basati su query SQL."""
    
    async def validate(self, user_id: str, channel_id: str, requirement: Dict[str, Any]) -> Tuple[bool, str]:
        """Esegue una validazione personalizzata."""
        if not self.db_pool:
            return False, "Database non disponibile"
            
        # Ottieni la query e i parametri
        query = requirement.get('query')
        if not query:
            return False, "Query di validazione mancante"
            
        try:
            async with self.db_pool.acquire() as conn:
                # Parametri predefiniti
                params = {
                    'user_id': user_id,
                    'channel_id': channel_id
                }
                
                # Aggiungi parametri personalizzati
                custom_params = requirement.get('params', {})
                params.update(custom_params)
                
                # Esegui la query di validazione
                row = await conn.fetchrow(query, *params.values())
                
                if row and row[0]:
                    return True, ""
                else:
                    return False, requirement.get('failure_message', "Non soddisfi i requisiti personalizzati")
        
        except Exception as e:
            logger.error(f"Errore nella validazione personalizzata: {e}")
            return False, "Errore nella verifica dei requisiti personalizzati"

class ParticipationValidator:
    """
    Classe principale che coordina la validazione di tutti i requisiti di partecipazione.
    """
    
    def __init__(self, db_pool=None, config: Dict[str, Any] = None):
        """
        Inizializza il validatore di partecipazione.
        
        Args:
            db_pool: Pool di connessioni al database
            config: Configurazione personalizzata
        """
        self.db_pool = db_pool
        self.config = config or {}
        
        # Inizializza i validatori per i vari tipi di requisiti
        self.validators = {
            'follower': FollowerValidator(db_pool),
            'subscriber': SubscriberValidator(db_pool),
            'points': PointsValidator(db_pool),
            'watch_time': WatchTimeValidator(db_pool),
            'custom': CustomValidator(db_pool)
        }
        
        logger.info("Validatore di partecipazione inizializzato")
    
    async def validate_requirements(self, user_id: str, channel_id: str, 
                                  requirements: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verifica se un utente soddisfa tutti i requisiti specificati.
        
        Args:
            user_id: ID dell'utente
            channel_id: ID del canale
            requirements: Lista dei requisiti da verificare
            
        Returns:
            Dict: Risultato della validazione con stato e dettagli
        """
        if not requirements:
            # Se non ci sono requisiti, l'utente è idoneo
            return {'valid': True, 'details': {}}
        
        results = {}
        details = {}
        
        # Verifica ogni requisito
        for req in requirements:
            req_type = req.get('type')
            validator = self.validators.get(req_type)
            
            if not validator:
                logger.warning(f"Tipo di requisito non supportato: {req_type}")
                results[req_type] = False
                details[req_type] = f"Tipo di requisito non supportato: {req_type}"
                continue
            
            valid, message = await validator.validate(user_id, channel_id, req)
            results[req_type] = valid
            
            if not valid:
                details[req_type] = message
        
        # L'utente è idoneo solo se soddisfa TUTTI i requisiti
        is_valid = all(results.values())
        
        # Costruisci l'oggetto di risposta
        response = {
            'valid': is_valid,
            'details': details
        }
        
        # Aggiungi un messaggio di riepilogo per il fallimento
        if not is_valid:
            # Ottieni il primo motivo di fallimento
            first_failure = next((details[k] for k in details if not results[k]), 
                                "Non soddisfi tutti i requisiti")
            response['reason'] = first_failure
        
        return response 