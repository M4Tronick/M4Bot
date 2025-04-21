#!/usr/bin/env python3
"""
API REST per la rotazione delle credenziali.
Fornisce endpoint per gestire la rotazione delle credenziali.
"""

import os
import sys
import json
import asyncio
import logging
from typing import Dict, List, Optional, Any, Union

# Aggiungi la directory principale al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Importa il framework FastAPI
from fastapi import FastAPI, HTTPException, Depends, Query, Path, Body, status, Response, APIRouter
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from pydantic import BaseModel, Field

# Importa il modulo di rotazione delle credenziali
from security.credential_rotation import (
    CredentialRotationManager, 
    CredentialType, 
    RotationSchedule
)

# Configurazione del logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/security/credential_rotation_api.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("CredentialRotationAPI")

# Implementazione dell'API
app = FastAPI(
    title="API di Rotazione Credenziali",
    description="API per gestire la rotazione automatica e sicura delle credenziali di M4Bot",
    version="1.0.0",
    docs_url=None,
    redoc_url="/api/docs"
)

# Aggiungi CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router API v1
router_v1 = APIRouter(prefix="/api/v1")

# Schema di sicurezza
security = HTTPBearer()

# Modelli dati
class CredentialBase(BaseModel):
    name: str
    type: str
    service: str
    description: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "name": "api_key_openai",
                "type": "api_key",
                "service": "openai",
                "description": "API key per il servizio OpenAI"
            }
        }

class CredentialCreate(CredentialBase):
    value: str
    rotation_schedule: str
    custom_interval_days: Optional[int] = None
    
    class Config:
        schema_extra = {
            "example": {
                "name": "api_key_openai",
                "type": "api_key",
                "service": "openai",
                "description": "API key per il servizio OpenAI",
                "value": "sk-1234567890abcdef1234567890abcdef",
                "rotation_schedule": "quarterly"
            }
        }

class CredentialUpdate(BaseModel):
    type: Optional[str] = None
    service: Optional[str] = None
    description: Optional[str] = None
    rotation_schedule: Optional[str] = None
    custom_interval_days: Optional[int] = None
    
    class Config:
        schema_extra = {
            "example": {
                "rotation_schedule": "monthly",
                "description": "API key aggiornata per il servizio OpenAI"
            }
        }

class CredentialResponse(CredentialBase):
    last_rotation: Optional[str] = None
    next_rotation: str
    days_to_rotation: int

class RotationResponse(BaseModel):
    success: bool
    message: str
    credential_name: Optional[str] = None
    service: Optional[str] = None
    next_rotation: Optional[str] = None

class ErrorResponse(BaseModel):
    detail: str
    status_code: int = Field(..., example=400)
    path: Optional[str] = Field(None, example="/api/v1/credentials/invalid_name")

# Gestore delle credenziali (istanza singola)
manager = CredentialRotationManager()

# Funzione di autenticazione
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verifica il token di autenticazione."""
    # In un'implementazione reale, verificare il token contro un database o servizio
    # Per semplicità, qui controlliamo solo un token hardcoded
    if credentials.credentials != os.getenv("CREDENTIAL_API_TOKEN", "test-token"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token di autenticazione non valido",
        )
    return credentials.credentials

# Endpoint per la documentazione Swagger
@app.get("/api/docs", include_in_schema=False)
async def get_documentation():
    """Endpoint per la documentazione Swagger."""
    return get_swagger_ui_html(openapi_url="/openapi.json", title="API Documentation")

# Endpoint API
@router_v1.get("/health", response_model=Dict[str, str], tags=["Stato"])
async def health_check():
    """Endpoint di verifica dello stato del servizio."""
    return {"status": "ok", "service": "credential-rotation-api", "version": "1.0.0"}

# Endpoint per le credenziali
@router_v1.get("/credentials", response_model=List[CredentialResponse], tags=["Credenziali"])
async def list_credentials(token: str = Depends(verify_token)):
    """
    Elenca tutte le credenziali registrate.
    
    Restituisce un elenco di tutte le credenziali registrate nel sistema,
    con dettagli sullo stato di rotazione di ciascuna.
    """
    try:
        status = manager.get_credential_status()
        result = []
        
        for name, cred in status["credentials"].items():
            result.append(
                CredentialResponse(
                    name=name,
                    type=cred["type"],
                    service=cred["service"],
                    last_rotation=manager.config["credentials"][name].get("last_rotation"),
                    next_rotation=cred["next_rotation"],
                    days_to_rotation=cred["days_to_rotation"],
                    description=manager.config["credentials"][name].get("description")
                )
            )
        
        return result
    except Exception as e:
        logger.error(f"Errore nel recupero delle credenziali: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nel recupero delle credenziali: {str(e)}"
        )

@router_v1.get("/credentials/{name}", response_model=CredentialResponse, tags=["Credenziali"])
async def get_credential(
    name: str = Path(..., description="Nome della credenziale"),
    token: str = Depends(verify_token)
):
    """
    Ottiene i dettagli di una credenziale specifica.
    
    Restituisce informazioni dettagliate su una singola credenziale,
    identificata dal suo nome univoco.
    """
    try:
        cred_status = manager.get_credential_status(name)
        
        if "error" in cred_status:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=cred_status["error"]
            )
        
        return CredentialResponse(
            name=name,
            type=cred_status["type"],
            service=cred_status["service"],
            last_rotation=cred_status["last_rotation"],
            next_rotation=cred_status["next_rotation"],
            days_to_rotation=cred_status["days_to_rotation"],
            description=cred_status.get("description")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore nel recupero della credenziale {name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nel recupero della credenziale: {str(e)}"
        )

@router_v1.post("/credentials", response_model=RotationResponse, status_code=status.HTTP_201_CREATED, tags=["Credenziali"])
async def create_credential(
    credential: CredentialCreate = Body(...),
    token: str = Depends(verify_token)
):
    """
    Registra una nuova credenziale.
    
    Crea una nuova credenziale nel sistema con il valore fornito,
    e imposta la pianificazione per la rotazione automatica.
    """
    try:
        # Verifica se la credenziale esiste già
        if credential.name in manager.config["credentials"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Credenziale {credential.name} già esistente"
            )
        
        # Validazione dei dati
        try:
            cred_type = CredentialType(credential.type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tipo di credenziale non valido: {credential.type}"
            )
        
        try:
            rotation_schedule = RotationSchedule(credential.rotation_schedule)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Frequenza di rotazione non valida: {credential.rotation_schedule}"
            )
        
        if rotation_schedule == RotationSchedule.CUSTOM and not credential.custom_interval_days:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Intervallo personalizzato richiesto per rotazione CUSTOM"
            )
        
        # Registra la credenziale
        success = manager.register_credential(
            name=credential.name,
            credential_type=cred_type,
            current_value=credential.value,
            rotation_schedule=rotation_schedule,
            service_name=credential.service,
            custom_interval_days=credential.custom_interval_days,
            description=credential.description
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Errore nella registrazione della credenziale {credential.name}"
            )
        
        # Recupera la nuova configurazione
        cred_config = manager.config["credentials"][credential.name]
        
        return RotationResponse(
            success=True,
            message=f"Credenziale {credential.name} registrata con successo",
            credential_name=credential.name,
            service=credential.service,
            next_rotation=cred_config["next_rotation"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore nella registrazione della credenziale: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella registrazione della credenziale: {str(e)}"
        )

@router_v1.patch("/credentials/{name}", response_model=CredentialResponse, tags=["Credenziali"])
async def update_credential(
    name: str = Path(..., description="Nome della credenziale da aggiornare"),
    credential: CredentialUpdate = Body(...),
    token: str = Depends(verify_token)
):
    """
    Aggiorna una credenziale esistente.
    
    Modifica i parametri di configurazione di una credenziale esistente,
    come la pianificazione di rotazione o la descrizione.
    """
    try:
        # Verifica se la credenziale esiste
        if name not in manager.config["credentials"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Credenziale {name} non trovata"
            )
            
        # Ottieni la configurazione corrente
        current_config = manager.config["credentials"][name]
        
        # Aggiorna i campi modificati
        updated = False
        
        if credential.type is not None:
            try:
                cred_type = CredentialType(credential.type)
                current_config["type"] = credential.type
                updated = True
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Tipo di credenziale non valido: {credential.type}"
                )
                
        if credential.service is not None:
            current_config["service"] = credential.service
            updated = True
            
        if credential.description is not None:
            current_config["description"] = credential.description
            updated = True
            
        if credential.rotation_schedule is not None:
            try:
                rotation_schedule = RotationSchedule(credential.rotation_schedule)
                current_config["rotation_schedule"] = credential.rotation_schedule
                
                # Ricalcola la prossima rotazione
                if credential.custom_interval_days is not None:
                    current_config["custom_interval_days"] = credential.custom_interval_days
                
                # Calcola la nuova data di rotazione
                custom_days = current_config.get("custom_interval_days")
                next_rotation = manager._calculate_next_rotation(
                    RotationSchedule(current_config["rotation_schedule"]),
                    custom_days
                )
                current_config["next_rotation"] = next_rotation.isoformat()
                
                updated = True
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Frequenza di rotazione non valida: {credential.rotation_schedule}"
                )
        
        if credential.custom_interval_days is not None and current_config["rotation_schedule"] == RotationSchedule.CUSTOM.value:
            current_config["custom_interval_days"] = credential.custom_interval_days
            
            # Ricalcola la prossima rotazione
            next_rotation = manager._calculate_next_rotation(
                RotationSchedule(current_config["rotation_schedule"]),
                credential.custom_interval_days
            )
            current_config["next_rotation"] = next_rotation.isoformat()
            
            updated = True
            
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nessun campo da aggiornare specificato"
            )
            
        # Salva la configurazione aggiornata
        manager.config["credentials"][name] = current_config
        manager._save_config()
        
        # Ottieni lo stato aggiornato
        cred_status = manager.get_credential_status(name)
        
        return CredentialResponse(
            name=name,
            type=cred_status["type"],
            service=cred_status["service"],
            last_rotation=cred_status["last_rotation"],
            next_rotation=cred_status["next_rotation"],
            days_to_rotation=cred_status["days_to_rotation"],
            description=cred_status.get("description")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore nell'aggiornamento della credenziale {name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nell'aggiornamento della credenziale: {str(e)}"
        )

@router_v1.delete("/credentials/{name}", status_code=status.HTTP_204_NO_CONTENT, tags=["Credenziali"])
async def delete_credential(
    name: str = Path(..., description="Nome della credenziale da eliminare"),
    token: str = Depends(verify_token)
):
    """
    Elimina una credenziale.
    
    Rimuove completamente una credenziale dal sistema.
    I backup esistenti non vengono eliminati automaticamente.
    """
    try:
        # Verifica se la credenziale esiste
        if name not in manager.config["credentials"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Credenziale {name} non trovata"
            )
            
        # Elimina la credenziale
        del manager.config["credentials"][name]
        manager._save_config()
        
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore nell'eliminazione della credenziale {name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nell'eliminazione della credenziale: {str(e)}"
        )

@router_v1.put("/credentials/{name}/rotate", response_model=RotationResponse, tags=["Rotazione"])
async def rotate_credential(
    name: str = Path(..., description="Nome della credenziale da ruotare"),
    token: str = Depends(verify_token)
):
    """
    Ruota una credenziale specifica.
    
    Esegue la rotazione manuale di una credenziale, generando un nuovo valore
    e salvando un backup del valore precedente.
    """
    try:
        # Verifica se la credenziale esiste
        if name not in manager.config["credentials"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Credenziale {name} non trovata"
            )
        
        # Esegui la rotazione
        result = await manager.rotate_credential(name, manual=True)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"]
            )
        
        return RotationResponse(
            success=True,
            message=f"Credenziale {name} ruotata con successo",
            credential_name=name,
            service=result["service"],
            next_rotation=result["next_rotation"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore nella rotazione della credenziale {name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella rotazione della credenziale: {str(e)}"
        )

@router_v1.put("/credentials/{name}/rollback", response_model=RotationResponse, tags=["Rotazione"])
async def rollback_credential(
    name: str = Path(..., description="Nome della credenziale da ripristinare"),
    timestamp: Optional[str] = Query(None, description="Timestamp specifico (opzionale)"),
    token: str = Depends(verify_token)
):
    """
    Ripristina una credenziale a un valore precedente.
    
    Esegue il rollback di una credenziale a un valore precedente,
    utilizzando un backup esistente. Se non viene specificato un timestamp,
    viene utilizzato il backup più recente.
    """
    try:
        # Verifica se la credenziale esiste
        if name not in manager.config["credentials"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Credenziale {name} non trovata"
            )
        
        # Esegui il rollback
        result = await manager.rollback_rotation(name, timestamp)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=result["message"]
            )
        
        return RotationResponse(
            success=True,
            message=f"Credenziale {name} ripristinata con successo",
            credential_name=name,
            service=manager.config["credentials"][name]["service"]
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore nel ripristino della credenziale {name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nel ripristino della credenziale: {str(e)}"
        )

@router_v1.put("/rotations/pending", response_model=List[RotationResponse], tags=["Rotazione"])
async def rotate_pending_credentials(token: str = Depends(verify_token)):
    """
    Ruota tutte le credenziali in attesa.
    
    Esegue la rotazione automatica di tutte le credenziali
    che hanno raggiunto o superato la data di rotazione programmata.
    """
    try:
        # Verifica le credenziali in attesa
        pending = manager.check_pending_rotations()
        
        if not pending:
            return []
        
        results = []
        
        # Ruota ogni credenziale in attesa
        for cred in pending:
            try:
                result = await manager.rotate_credential(cred["name"])
                
                results.append(
                    RotationResponse(
                        success=result["success"],
                        message=result["message"],
                        credential_name=cred["name"],
                        service=cred["service"],
                        next_rotation=result.get("next_rotation")
                    )
                )
            except Exception as e:
                logger.error(f"Errore nella rotazione della credenziale {cred['name']}: {e}")
                results.append(
                    RotationResponse(
                        success=False,
                        message=f"Errore: {str(e)}",
                        credential_name=cred["name"],
                        service=cred["service"]
                    )
                )
        
        return results
    except Exception as e:
        logger.error(f"Errore nella rotazione delle credenziali in attesa: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nella rotazione delle credenziali in attesa: {str(e)}"
        )

@router_v1.get("/rotations/pending", response_model=List[Dict[str, Any]], tags=["Rotazione"])
async def list_pending_rotations(token: str = Depends(verify_token)):
    """
    Elenca le credenziali in attesa di rotazione.
    
    Restituisce un elenco di credenziali che hanno superato 
    la data di rotazione programmata e sono in attesa di essere ruotate.
    """
    try:
        pending = manager.check_pending_rotations()
        return pending
    except Exception as e:
        logger.error(f"Errore nel recupero delle rotazioni in attesa: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nel recupero delle rotazioni in attesa: {str(e)}"
        )

@router_v1.get("/rotations/upcoming", response_model=List[Dict[str, Any]], tags=["Rotazione"])
async def list_upcoming_rotations(
    days: int = Query(7, description="Numero di giorni da considerare"),
    token: str = Depends(verify_token)
):
    """
    Elenca le credenziali con rotazione imminente.
    
    Restituisce un elenco di credenziali la cui rotazione è programmata
    entro il numero di giorni specificato.
    """
    try:
        upcoming = manager.check_upcoming_rotations(days)
        return upcoming
    except Exception as e:
        logger.error(f"Errore nel recupero delle rotazioni imminenti: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore nel recupero delle rotazioni imminenti: {str(e)}"
        )

# Gestione globale delle eccezioni
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return Response(
        status_code=exc.status_code,
        content=json.dumps({
            "detail": exc.detail,
            "status_code": exc.status_code,
            "path": request.url.path
        }),
        media_type="application/json"
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    logger.error(f"Errore non gestito: {exc}")
    return Response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=json.dumps({
            "detail": "Errore interno del server",
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "path": request.url.path
        }),
        media_type="application/json"
    )

# Includi i router nell'app
app.include_router(router_v1)

# Alias radice
@app.get("/", include_in_schema=False)
async def root():
    """Reindirizza alla documentazione."""
    return {"message": "API di Rotazione Credenziali", "docs": "/api/docs"}

if __name__ == "__main__":
    import uvicorn
    
    # Avvia il server API
    uvicorn.run("credential_rotation_api:app", host="0.0.0.0", port=8080) 