#!/usr/bin/env python3
"""
Documentazione API completa per M4Bot

Questo modulo fornisce una documentazione completa delle API di M4Bot utilizzando OpenAPI/Swagger.
Documenta tutti gli endpoint disponibili, i parametri, i modelli di risposta, i codici di errore e gli esempi.
"""

import os
import json
from typing import Dict, List, Any, Optional
from quart import Quart, Blueprint, jsonify, render_template, current_app, Response, request
from dataclasses import dataclass, field

# Versione corrente dell'API
API_VERSION = "1.0.0"

# Titolo e descrizione della documentazione
API_TITLE = "M4Bot API"
API_DESCRIPTION = """
# M4Bot REST API

API completa per interagire con M4Bot, il bot multi-funzione per Kick.com.

## Funzionalità

- Gestione bot e comandi personalizzati
- Sistema punti canale
- Notifiche multi-canale
- Statistiche e analytics
- Moderazione automatica
- Integrazione multi-piattaforma
- Donazioni e transazioni
- Giveaway e premi
- Pianificazione contenuti
- Overlay OBS

## Autenticazione

La maggior parte degli endpoint richiede un token JWT di autenticazione nel header:
`Authorization: Bearer YOUR_JWT_TOKEN`

I token possono essere ottenuti tramite l'endpoint `/api/auth/login`
"""

@dataclass
class APIEndpoint:
    """Rappresenta un endpoint dell'API."""
    path: str  # Percorso URL
    method: str  # GET, POST, PUT, DELETE, ecc.
    summary: str  # Breve descrizione
    description: str  # Descrizione completa
    tags: List[str]  # Categorie dell'endpoint
    parameters: List[Dict[str, Any]] = field(default_factory=list)  # Parametri URL, query, header
    request_body: Optional[Dict[str, Any]] = None  # Corpo della richiesta
    responses: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # Risposte possibili
    security: Optional[List[Dict[str, List[str]]]] = None  # Requisiti di sicurezza
    deprecated: bool = False  # Se l'endpoint è deprecato

@dataclass
class APISchema:
    """Rappresenta uno schema dati dell'API."""
    name: str  # Nome dello schema
    properties: Dict[str, Dict[str, Any]]  # Proprietà dello schema
    required: List[str] = field(default_factory=list)  # Campi obbligatori
    description: Optional[str] = None  # Descrizione dello schema
    example: Optional[Dict[str, Any]] = None  # Esempio dello schema

class APIDocumentation:
    """Gestisce la documentazione dell'API."""
    
    def __init__(self):
        self.endpoints: List[APIEndpoint] = []
        self.schemas: Dict[str, APISchema] = {}
        self.tags: List[Dict[str, str]] = []
        
        # Inizializza tag predefiniti
        self._init_tags()
        
        # Inizializza schemi predefiniti
        self._init_schemas()
        
        # Inizializza endpoint API comuni
        self._init_endpoints()
    
    def _init_tags(self):
        """Inizializza i tag per categorizzare gli endpoint."""
        self.tags = [
            {"name": "auth", "description": "Autenticazione e gestione utenti"},
            {"name": "bot", "description": "Gestione del bot e impostazioni"},
            {"name": "commands", "description": "Gestione comandi personalizzati"},
            {"name": "points", "description": "Sistema punti canale"},
            {"name": "notifications", "description": "Sistema di notifiche"},
            {"name": "analytics", "description": "Statistiche e analytics"},
            {"name": "moderation", "description": "Moderazione automatica"},
            {"name": "integrations", "description": "Integrazioni con piattaforme esterne"},
            {"name": "donations", "description": "Gestione donazioni"},
            {"name": "giveaway", "description": "Sistema giveaway e premi"},
            {"name": "scheduler", "description": "Pianificazione contenuti"},
            {"name": "overlay", "description": "Overlay per OBS"}
        ]
    
    def _init_schemas(self):
        """Inizializza gli schemi dati predefiniti."""
        # Schema utente
        self.schemas["User"] = APISchema(
            name="User",
            description="Rappresenta un utente del sistema",
            properties={
                "id": {"type": "integer", "format": "int64", "description": "ID univoco dell'utente"},
                "username": {"type": "string", "description": "Nome utente"},
                "email": {"type": "string", "format": "email", "description": "Indirizzo email"},
                "is_admin": {"type": "boolean", "description": "Se l'utente è amministratore"},
                "created_at": {"type": "string", "format": "date-time", "description": "Data di creazione"},
                "last_login": {"type": "string", "format": "date-time", "description": "Ultimo accesso"}
            },
            required=["id", "username"],
            example={
                "id": 1,
                "username": "example_user",
                "email": "user@example.com",
                "is_admin": False,
                "created_at": "2023-01-01T00:00:00Z",
                "last_login": "2023-01-10T12:30:45Z"
            }
        )
        
        # Schema canale
        self.schemas["Channel"] = APISchema(
            name="Channel",
            description="Rappresenta un canale Kick.com",
            properties={
                "id": {"type": "integer", "format": "int64", "description": "ID univoco del canale"},
                "kick_channel_id": {"type": "string", "description": "ID del canale su Kick.com"},
                "name": {"type": "string", "description": "Nome del canale"},
                "owner_id": {"type": "integer", "format": "int64", "description": "ID del proprietario"},
                "created_at": {"type": "string", "format": "date-time", "description": "Data di creazione"}
            },
            required=["id", "kick_channel_id", "name", "owner_id"],
            example={
                "id": 1,
                "kick_channel_id": "abcd1234",
                "name": "example_channel",
                "owner_id": 1,
                "created_at": "2023-01-01T00:00:00Z"
            }
        )
        
        # Schema comando personalizzato
        self.schemas["Command"] = APISchema(
            name="Command",
            description="Rappresenta un comando personalizzato",
            properties={
                "id": {"type": "integer", "format": "int64", "description": "ID univoco del comando"},
                "channel_id": {"type": "integer", "format": "int64", "description": "ID del canale"},
                "name": {"type": "string", "description": "Nome del comando (senza prefisso)"},
                "response": {"type": "string", "description": "Risposta del comando"},
                "cooldown": {"type": "integer", "description": "Cooldown in secondi"},
                "user_level": {"type": "string", "enum": ["everyone", "subscriber", "moderator", "admin"], "description": "Livello utente richiesto"},
                "enabled": {"type": "boolean", "description": "Se il comando è abilitato"},
                "usage_count": {"type": "integer", "description": "Contatore utilizzi"}
            },
            required=["id", "channel_id", "name", "response"],
            example={
                "id": 1,
                "channel_id": 1,
                "name": "hello",
                "response": "Ciao {user}!",
                "cooldown": 5,
                "user_level": "everyone",
                "enabled": True,
                "usage_count": 42
            }
        )
        
        # Schema punti canale
        self.schemas["ChannelPoints"] = APISchema(
            name="ChannelPoints",
            description="Rappresenta i punti canale di un utente",
            properties={
                "id": {"type": "integer", "format": "int64", "description": "ID univoco"},
                "channel_id": {"type": "integer", "format": "int64", "description": "ID del canale"},
                "user_id": {"type": "integer", "format": "int64", "description": "ID dell'utente"},
                "points": {"type": "integer", "description": "Punti accumulati"},
                "watch_time": {"type": "integer", "description": "Tempo di visione in secondi"},
                "last_updated": {"type": "string", "format": "date-time", "description": "Ultimo aggiornamento"}
            },
            required=["channel_id", "user_id", "points"],
            example={
                "id": 1,
                "channel_id": 1,
                "user_id": 1,
                "points": 1500,
                "watch_time": 7200,
                "last_updated": "2023-01-10T12:30:45Z"
            }
        )
        
        # Schema notifica
        self.schemas["Notification"] = APISchema(
            name="Notification",
            description="Rappresenta una notifica",
            properties={
                "id": {"type": "string", "format": "uuid", "description": "ID univoco della notifica"},
                "type": {"type": "string", "enum": ["stream_start", "stream_end", "new_follower", "new_subscription", "donation", "system_alert", "scheduled_event", "custom"], "description": "Tipo di notifica"},
                "title": {"type": "string", "description": "Titolo della notifica"},
                "body": {"type": "string", "description": "Corpo della notifica"},
                "created_at": {"type": "string", "format": "date-time", "description": "Data di creazione"},
                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"], "description": "Priorità della notifica"},
                "recipients": {"type": "array", "items": {"type": "string"}, "description": "Lista ID destinatari"},
                "sent": {"type": "boolean", "description": "Se la notifica è stata inviata"},
                "sent_at": {"type": "string", "format": "date-time", "description": "Data di invio"}
            },
            required=["id", "type", "title", "body", "created_at"],
            example={
                "id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
                "type": "stream_start",
                "title": "Channel Name è in diretta!",
                "body": "Channel Name ha iniziato una diretta: 'Stream Title'",
                "created_at": "2023-01-10T18:00:00Z",
                "priority": "normal",
                "recipients": ["user1", "user2"],
                "sent": True,
                "sent_at": "2023-01-10T18:00:05Z"
            }
        )
        
        # Schema per le risposte di errore
        self.schemas["Error"] = APISchema(
            name="Error",
            description="Rappresenta un errore API",
            properties={
                "code": {"type": "integer", "description": "Codice di errore HTTP"},
                "message": {"type": "string", "description": "Messaggio di errore"},
                "details": {"type": "string", "description": "Dettagli aggiuntivi sull'errore"}
            },
            required=["code", "message"],
            example={
                "code": 400,
                "message": "Bad Request",
                "details": "Il parametro 'name' è obbligatorio"
            }
        )
        
        # Schema per l'autenticazione
        self.schemas["LoginRequest"] = APISchema(
            name="LoginRequest",
            description="Richiesta di login",
            properties={
                "username": {"type": "string", "description": "Nome utente o email"},
                "password": {"type": "string", "format": "password", "description": "Password"}
            },
            required=["username", "password"],
            example={
                "username": "user@example.com",
                "password": "password123"
            }
        )
        
        self.schemas["AuthResponse"] = APISchema(
            name="AuthResponse",
            description="Risposta di autenticazione",
            properties={
                "access_token": {"type": "string", "description": "Token JWT di accesso"},
                "token_type": {"type": "string", "description": "Tipo di token"},
                "expires_in": {"type": "integer", "description": "Durata del token in secondi"},
                "user": {"$ref": "#/components/schemas/User", "description": "Dati utente"}
            },
            required=["access_token", "token_type"],
            example={
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 86400,
                "user": {
                    "id": 1,
                    "username": "example_user",
                    "email": "user@example.com",
                    "is_admin": False
                }
            }
        )
    
    def _init_endpoints(self):
        """Inizializza gli endpoint API comuni."""
        # Endpoint di autenticazione
        self.endpoints.append(APIEndpoint(
            path="/api/auth/login",
            method="POST",
            summary="Login utente",
            description="Autentica un utente e restituisce un token JWT",
            tags=["auth"],
            request_body={
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/LoginRequest"}
                    }
                }
            },
            responses={
                "200": {
                    "description": "Login riuscito",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/AuthResponse"}
                        }
                    }
                },
                "401": {
                    "description": "Credenziali non valide",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"}
                        }
                    }
                }
            }
        ))
        
        # Endpoint informazioni utente
        self.endpoints.append(APIEndpoint(
            path="/api/users/me",
            method="GET",
            summary="Informazioni utente corrente",
            description="Restituisce informazioni sull'utente autenticato",
            tags=["auth"],
            security=[{"bearerAuth": []}],
            responses={
                "200": {
                    "description": "Informazioni utente",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/User"}
                        }
                    }
                },
                "401": {
                    "description": "Non autenticato",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"}
                        }
                    }
                }
            }
        ))
        
        # Endpoint lista comandi
        self.endpoints.append(APIEndpoint(
            path="/api/channels/{channelId}/commands",
            method="GET",
            summary="Lista comandi",
            description="Restituisce la lista dei comandi personalizzati per un canale",
            tags=["commands"],
            parameters=[
                {
                    "name": "channelId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                    "description": "ID del canale"
                },
                {
                    "name": "page",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 1},
                    "description": "Numero pagina"
                },
                {
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "default": 20},
                    "description": "Elementi per pagina"
                }
            ],
            security=[{"bearerAuth": []}],
            responses={
                "200": {
                    "description": "Lista comandi",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "total": {"type": "integer"},
                                    "page": {"type": "integer"},
                                    "limit": {"type": "integer"},
                                    "commands": {
                                        "type": "array",
                                        "items": {"$ref": "#/components/schemas/Command"}
                                    }
                                }
                            }
                        }
                    }
                },
                "401": {
                    "description": "Non autenticato",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"}
                        }
                    }
                }
            }
        ))
        
        # Endpoint creazione comando
        self.endpoints.append(APIEndpoint(
            path="/api/channels/{channelId}/commands",
            method="POST",
            summary="Crea comando",
            description="Crea un nuovo comando personalizzato",
            tags=["commands"],
            parameters=[
                {
                    "name": "channelId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                    "description": "ID del canale"
                }
            ],
            request_body={
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "response": {"type": "string"},
                                "cooldown": {"type": "integer"},
                                "user_level": {"type": "string", "enum": ["everyone", "subscriber", "moderator", "admin"]}
                            },
                            "required": ["name", "response"]
                        }
                    }
                }
            },
            security=[{"bearerAuth": []}],
            responses={
                "201": {
                    "description": "Comando creato",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Command"}
                        }
                    }
                },
                "400": {
                    "description": "Richiesta non valida",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"}
                        }
                    }
                }
            }
        ))
        
        # Endpoint punti utente
        self.endpoints.append(APIEndpoint(
            path="/api/channels/{channelId}/points/users/{userId}",
            method="GET",
            summary="Punti utente",
            description="Ottiene i punti canale di un utente specifico",
            tags=["points"],
            parameters=[
                {
                    "name": "channelId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                    "description": "ID del canale"
                },
                {
                    "name": "userId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                    "description": "ID dell'utente"
                }
            ],
            security=[{"bearerAuth": []}],
            responses={
                "200": {
                    "description": "Informazioni punti",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ChannelPoints"}
                        }
                    }
                }
            }
        ))
        
        # Endpoint aggiornamento punti
        self.endpoints.append(APIEndpoint(
            path="/api/channels/{channelId}/points/users/{userId}",
            method="PUT",
            summary="Aggiorna punti utente",
            description="Aggiorna i punti canale di un utente specifico",
            tags=["points"],
            parameters=[
                {
                    "name": "channelId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                    "description": "ID del canale"
                },
                {
                    "name": "userId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "integer"},
                    "description": "ID dell'utente"
                }
            ],
            request_body={
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "points": {"type": "integer", "description": "Nuovi punti o delta"},
                                "operation": {"type": "string", "enum": ["set", "add", "subtract"], "description": "Operazione da eseguire"}
                            },
                            "required": ["points", "operation"]
                        }
                    }
                }
            },
            security=[{"bearerAuth": []}],
            responses={
                "200": {
                    "description": "Punti aggiornati",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ChannelPoints"}
                        }
                    }
                },
                "400": {
                    "description": "Richiesta non valida",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"}
                        }
                    }
                }
            }
        ))
        
        # Endpoint per inviare notifica
        self.endpoints.append(APIEndpoint(
            path="/api/notifications",
            method="POST",
            summary="Invia notifica",
            description="Invia una notifica a uno o più utenti",
            tags=["notifications"],
            request_body={
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["stream_start", "stream_end", "new_follower", "new_subscription", "donation", "system_alert", "scheduled_event", "custom"]},
                                "recipients": {"type": "array", "items": {"type": "string"}},
                                "data": {"type": "object", "additionalProperties": True},
                                "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
                                "channels": {"type": "array", "items": {"type": "string", "enum": ["email", "telegram", "discord", "push", "sms", "app", "webhook"]}}
                            },
                            "required": ["type", "recipients"]
                        }
                    }
                }
            },
            security=[{"bearerAuth": []}],
            responses={
                "202": {
                    "description": "Notifica accettata per l'invio",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "notification_id": {"type": "string", "format": "uuid"},
                                    "message": {"type": "string"}
                                }
                            }
                        }
                    }
                },
                "400": {
                    "description": "Richiesta non valida",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Error"}
                        }
                    }
                }
            }
        ))
        
        # Endpoint preferenze notifiche utente
        self.endpoints.append(APIEndpoint(
            path="/api/users/{userId}/notification-preferences",
            method="GET",
            summary="Preferenze notifiche",
            description="Ottiene le preferenze di notifica dell'utente",
            tags=["notifications"],
            parameters=[
                {
                    "name": "userId",
                    "in": "path",
                    "required": True,
                    "schema": {"type": "string"},
                    "description": "ID dell'utente"
                }
            ],
            security=[{"bearerAuth": []}],
            responses={
                "200": {
                    "description": "Preferenze notifiche",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "user_id": {"type": "string"},
                                    "enabled": {"type": "boolean"},
                                    "quiet_hours_start": {"type": "integer", "nullable": True},
                                    "quiet_hours_end": {"type": "integer", "nullable": True},
                                    "channels": {"type": "object", "additionalProperties": True},
                                    "telegram_chat_id": {"type": "string", "nullable": True},
                                    "email": {"type": "string", "nullable": True},
                                    "discord_webhook_url": {"type": "string", "nullable": True},
                                    "push_subscription": {"type": "object", "nullable": True},
                                    "webhook_url": {"type": "string", "nullable": True},
                                    "phone_number": {"type": "string", "nullable": True}
                                }
                            }
                        }
                    }
                }
            }
        ))
        
    def generate_openapi_spec(self) -> Dict[str, Any]:
        """Genera la specifica OpenAPI completa."""
        openapi = {
            "openapi": "3.0.3",
            "info": {
                "title": API_TITLE,
                "description": API_DESCRIPTION,
                "version": API_VERSION,
                "contact": {
                    "name": "M4Bot Support",
                    "url": "https://m4bot.it/support",
                    "email": "support@m4bot.it"
                },
                "license": {
                    "name": "MIT",
                    "url": "https://opensource.org/licenses/MIT"
                }
            },
            "servers": [
                {
                    "url": "https://api.m4bot.it",
                    "description": "Server di produzione"
                },
                {
                    "url": "https://api-dev.m4bot.it",
                    "description": "Server di sviluppo"
                }
            ],
            "paths": {},
            "components": {
                "schemas": {},
                "securitySchemes": {
                    "bearerAuth": {
                        "type": "http",
                        "scheme": "bearer",
                        "bearerFormat": "JWT"
                    }
                }
            },
            "tags": self.tags
        }
        
        # Popola gli schemi
        for schema_name, schema in self.schemas.items():
            schema_dict = {
                "type": "object",
                "properties": schema.properties,
            }
            
            if schema.description:
                schema_dict["description"] = schema.description
                
            if schema.required:
                schema_dict["required"] = schema.required
                
            if schema.example:
                schema_dict["example"] = schema.example
                
            openapi["components"]["schemas"][schema_name] = schema_dict
        
        # Popola i percorsi
        for endpoint in self.endpoints:
            if endpoint.path not in openapi["paths"]:
                openapi["paths"][endpoint.path] = {}
                
            endpoint_dict = {
                "summary": endpoint.summary,
                "description": endpoint.description,
                "tags": endpoint.tags,
                "responses": endpoint.responses
            }
            
            if endpoint.parameters:
                endpoint_dict["parameters"] = endpoint.parameters
                
            if endpoint.request_body:
                endpoint_dict["requestBody"] = endpoint.request_body
                
            if endpoint.security:
                endpoint_dict["security"] = endpoint.security
                
            if endpoint.deprecated:
                endpoint_dict["deprecated"] = endpoint.deprecated
                
            openapi["paths"][endpoint.path][endpoint.method.lower()] = endpoint_dict
        
        return openapi

def create_api_documentation_blueprint() -> Blueprint:
    """Crea un blueprint Flask/Quart per la documentazione API."""
    bp = Blueprint('api_docs', __name__, url_prefix='/api/docs')
    
    # Crea la documentazione API
    api_docs = APIDocumentation()
    
    @bp.route('', methods=['GET'])
    async def docs_ui():
        """Pagina di documentazione API interattiva basata su SwaggerUI."""
        return await render_template('api_docs.html', title=API_TITLE)
    
    @bp.route('/openapi.json', methods=['GET'])
    async def openapi_spec():
        """Endpoint che fornisce la specifica OpenAPI in formato JSON."""
        spec = api_docs.generate_openapi_spec()
        return jsonify(spec)
    
    @bp.route('/endpoints', methods=['GET'])
    async def list_endpoints():
        """Elenco degli endpoint in formato JSON semplificato."""
        endpoints = []
        
        for endpoint in api_docs.endpoints:
            endpoints.append({
                "path": endpoint.path,
                "method": endpoint.method,
                "summary": endpoint.summary,
                "tags": endpoint.tags
            })
            
        return jsonify({"endpoints": endpoints})
    
    return bp

def register_api_docs(app: Quart):
    """Registra la documentazione API in un'app Quart."""
    # Aggiungi la directory dei template se non esiste
    if not os.path.exists('web/templates'):
        os.makedirs('web/templates', exist_ok=True)
    
    # Crea il template SwaggerUI se non esiste
    swagger_template_path = 'web/templates/api_docs.html'
    if not os.path.exists(swagger_template_path):
        with open(swagger_template_path, 'w') as f:
            f.write('''
<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - Documentazione API</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@4.5.0/swagger-ui.css">
    <style>
        body {
            margin: 0;
            padding: 0;
        }
        #swagger-ui {
            max-width: 1460px;
            margin: 0 auto;
            padding: 20px;
        }
        .topbar {
            display: none;
        }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    
    <script src="https://unpkg.com/swagger-ui-dist@4.5.0/swagger-ui-bundle.js"></script>
    <script>
        window.onload = function() {
            const ui = SwaggerUIBundle({
                url: "/api/docs/openapi.json",
                dom_id: "#swagger-ui",
                deepLinking: true,
                presets: [
                    SwaggerUIBundle.presets.apis,
                    SwaggerUIBundle.SwaggerUIStandalonePreset
                ],
                layout: "BaseLayout",
                persistAuthorization: true
            });
            window.ui = ui;
        };
    </script>
</body>
</html>
            ''')
    
    # Registra il blueprint
    app.register_blueprint(create_api_documentation_blueprint())

# Esempio di utilizzo
if __name__ == "__main__":
    import json
    
    # Crea l'istanza di documentazione API
    api_docs = APIDocumentation()
    
    # Genera la specifica OpenAPI
    spec = api_docs.generate_openapi_spec()
    
    # Salva la specifica in un file
    with open("openapi.json", "w") as f:
        json.dump(spec, f, indent=2)
    
    print(f"Documentazione API generata con {len(api_docs.endpoints)} endpoint e {len(api_docs.schemas)} schemi") 