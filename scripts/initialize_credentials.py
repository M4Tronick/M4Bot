#!/usr/bin/env python3
"""
Script di inizializzazione per il sistema di rotazione delle credenziali.
Questo script genera valori iniziali per le credenziali definite nella configurazione.
"""

import os
import sys
import json
import secrets
import argparse
from pathlib import Path

# Aggiungi la directory principale al path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Importa il modulo di rotazione delle credenziali
from security.credential_rotation import CredentialRotationManager, CredentialType, RotationSchedule

def generate_initial_values(config_path: str, backup: bool = True):
    """
    Genera valori iniziali per le credenziali definite nella configurazione.
    
    Args:
        config_path: Percorso del file di configurazione
        backup: Se True, crea un backup dei valori generati
    """
    # Carica la configurazione
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
    except Exception as e:
        print(f"Errore nel caricamento della configurazione: {e}")
        return False
    
    # Inizializza il gestore
    manager = CredentialRotationManager(config_path)
    
    # Per ogni credenziale definita
    for name, cred in config["credentials"].items():
        # Genera un valore in base al tipo
        cred_type = CredentialType(cred["type"])
        value = manager._generate_new_value(cred_type.value)
        
        print(f"Valore generato per {name} ({cred_type.value}): {value}")
        
        if backup:
            # Registra la credenziale nel sistema (crea il backup)
            manager.register_credential(
                name=name,
                credential_type=cred_type,
                current_value=value,
                rotation_schedule=RotationSchedule(cred["rotation_schedule"]),
                service_name=cred["service"],
                custom_interval_days=cred.get("custom_interval_days"),
                description=cred.get("description")
            )
            print(f"Credenziale {name} registrata nel sistema")
    
    return True

def main():
    parser = argparse.ArgumentParser(description="Inizializza il sistema di rotazione delle credenziali")
    parser.add_argument("--config", default="config/security/credential_rotation.json", 
                        help="Percorso del file di configurazione")
    parser.add_argument("--no-backup", action="store_true", 
                        help="Non creare backup delle credenziali")
    
    args = parser.parse_args()
    
    print(f"Inizializzazione credenziali da {args.config}...")
    result = generate_initial_values(args.config, not args.no_backup)
    
    if result:
        print("Inizializzazione completata con successo")
    else:
        print("Errore nell'inizializzazione")
        sys.exit(1)

if __name__ == "__main__":
    main() 