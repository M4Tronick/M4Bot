#!/usr/bin/env python3
"""
Script di test per l'API REST di rotazione delle credenziali.
Esegue una serie di richieste per verificare le funzionalità dell'API.
"""

import os
import sys
import json
import time
import asyncio
import argparse
import requests
from typing import Dict, Any, List, Optional

# Configurazione predefinita
API_BASE_URL = "http://localhost:8080/api/v1"
API_TOKEN = "test-token"
TEST_CREDENTIAL = {
    "name": "test_api_key",
    "type": "api_key",
    "service": "test_service",
    "description": "Credenziale di test per API",
    "value": "TEST_API_KEY_VALUE_1234",
    "rotation_schedule": "monthly"
}

class CredentialRotationApiTest:
    """Classe per testare l'API di rotazione delle credenziali."""
    
    def __init__(self, base_url: str, token: str):
        """
        Inizializza il tester dell'API.
        
        Args:
            base_url: URL base dell'API
            token: Token di autenticazione
        """
        self.base_url = base_url
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Stato dei test
        self.tests_passed = 0
        self.tests_failed = 0
        self.tests_skipped = 0
    
    def request(self, method: str, endpoint: str, data: Dict[str, Any] = None, 
                params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Esegue una richiesta all'API.
        
        Args:
            method: Metodo HTTP (GET, POST, PUT, PATCH, DELETE)
            endpoint: Endpoint da chiamare
            data: Dati da inviare (per POST, PUT, PATCH)
            params: Parametri query
            
        Returns:
            Dict: Risposta dell'API
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=data,
                params=params
            )
            
            # Se la risposta è vuota (es. DELETE), restituisci uno stato
            if not response.text.strip() and response.status_code in [204]:
                return {"status_code": response.status_code}
            
            # Altrimenti, prova a parsare JSON
            try:
                result = response.json()
                result["status_code"] = response.status_code
                return result
            except ValueError:
                return {
                    "status_code": response.status_code,
                    "text": response.text
                }
        
        except Exception as e:
            print(f"Errore nella richiesta {method} {endpoint}: {e}")
            return {"error": str(e), "status_code": 0}
    
    def run_test(self, name: str, test_func: callable) -> bool:
        """
        Esegue un singolo test e gestisce i risultati.
        
        Args:
            name: Nome del test
            test_func: Funzione di test da eseguire
            
        Returns:
            bool: True se il test è passato, False altrimenti
        """
        print(f"\n[TEST] {name}")
        print("-" * 50)
        
        try:
            result = test_func()
            if result is True:
                print(f"✅ PASSATO: {name}")
                self.tests_passed += 1
                return True
            elif result is False:
                print(f"❌ FALLITO: {name}")
                self.tests_failed += 1
                return False
            else:
                print(f"⏭️ SALTATO: {name}")
                self.tests_skipped += 1
                return False
        except Exception as e:
            print(f"❌ ERRORE: {name} - {e}")
            self.tests_failed += 1
            return False
    
    def test_health(self) -> bool:
        """Verifica l'endpoint di health check."""
        response = self.request("GET", "/health")
        
        if response.get("status_code") != 200:
            print(f"❌ Health check fallito: {response}")
            return False
        
        if response.get("status") != "ok":
            print(f"❌ Health check non OK: {response}")
            return False
        
        print(f"✓ Health check passato: {response}")
        return True
    
    def test_create_credential(self) -> bool:
        """Verifica la creazione di una credenziale."""
        # Prima controlla se la credenziale esiste già
        response = self.request("GET", f"/credentials/{TEST_CREDENTIAL['name']}")
        
        if response.get("status_code") == 200:
            print(f"ℹ️ La credenziale esiste già, la elimino...")
            delete_response = self.request("DELETE", f"/credentials/{TEST_CREDENTIAL['name']}")
            
            if delete_response.get("status_code") != 204:
                print(f"❌ Eliminazione fallita: {delete_response}")
                return False
            
            print(f"✓ Credenziale eliminata")
        
        # Crea la credenziale
        response = self.request("POST", "/credentials", data=TEST_CREDENTIAL)
        
        if response.get("status_code") != 201:
            print(f"❌ Creazione fallita: {response}")
            return False
        
        if not response.get("success", False):
            print(f"❌ Creazione non riuscita: {response}")
            return False
        
        print(f"✓ Credenziale creata: {response}")
        return True
    
    def test_get_credential(self) -> bool:
        """Verifica il recupero di una credenziale."""
        response = self.request("GET", f"/credentials/{TEST_CREDENTIAL['name']}")
        
        if response.get("status_code") != 200:
            print(f"❌ Recupero fallito: {response}")
            return False
        
        # Verifica i dati
        if response.get("name") != TEST_CREDENTIAL["name"]:
            print(f"❌ Nome non corrispondente: {response}")
            return False
        
        if response.get("type") != TEST_CREDENTIAL["type"]:
            print(f"❌ Tipo non corrispondente: {response}")
            return False
        
        print(f"✓ Credenziale recuperata: {response}")
        return True
    
    def test_update_credential(self) -> bool:
        """Verifica l'aggiornamento di una credenziale."""
        update_data = {
            "description": "Descrizione aggiornata della credenziale di test"
        }
        
        response = self.request("PATCH", f"/credentials/{TEST_CREDENTIAL['name']}", data=update_data)
        
        if response.get("status_code") != 200:
            print(f"❌ Aggiornamento fallito: {response}")
            return False
        
        # Verifica i dati aggiornati
        if response.get("description") != update_data["description"]:
            print(f"❌ Descrizione non aggiornata: {response}")
            return False
        
        print(f"✓ Credenziale aggiornata: {response}")
        return True
    
    def test_rotate_credential(self) -> bool:
        """Verifica la rotazione di una credenziale."""
        response = self.request("PUT", f"/credentials/{TEST_CREDENTIAL['name']}/rotate")
        
        if response.get("status_code") != 200:
            print(f"❌ Rotazione fallita: {response}")
            return False
        
        if not response.get("success", False):
            print(f"❌ Rotazione non riuscita: {response}")
            return False
        
        print(f"✓ Credenziale ruotata: {response}")
        return True
    
    def test_rollback_credential(self) -> bool:
        """Verifica il rollback di una credenziale."""
        # Prima dobbiamo avere almeno due rotazioni
        print(f"ℹ️ Eseguo una seconda rotazione per poter testare il rollback...")
        self.request("PUT", f"/credentials/{TEST_CREDENTIAL['name']}/rotate")
        
        # Ora eseguo il rollback
        response = self.request("PUT", f"/credentials/{TEST_CREDENTIAL['name']}/rollback")
        
        if response.get("status_code") != 200:
            print(f"❌ Rollback fallito: {response}")
            return False
        
        if not response.get("success", False):
            print(f"❌ Rollback non riuscito: {response}")
            return False
        
        print(f"✓ Credenziale ripristinata: {response}")
        return True
    
    def test_list_credentials(self) -> bool:
        """Verifica l'elenco delle credenziali."""
        response = self.request("GET", "/credentials")
        
        if response.get("status_code") != 200:
            print(f"❌ Elenco fallito: {response}")
            return False
        
        if not isinstance(response, list):
            print(f"❌ Risposta non è una lista: {response}")
            return False
        
        print(f"✓ Elenco credenziali: {len(response)} credenziali trovate")
        return True
    
    def test_pending_rotations(self) -> bool:
        """Verifica l'elenco delle rotazioni in attesa."""
        response = self.request("GET", "/rotations/pending")
        
        if response.get("status_code") != 200:
            print(f"❌ Elenco rotazioni in attesa fallito: {response}")
            return False
        
        if not isinstance(response, list):
            print(f"❌ Risposta non è una lista: {response}")
            return False
        
        print(f"✓ Elenco rotazioni in attesa: {len(response)} rotazioni trovate")
        return True
    
    def test_upcoming_rotations(self) -> bool:
        """Verifica l'elenco delle rotazioni imminenti."""
        response = self.request("GET", "/rotations/upcoming", params={"days": 30})
        
        if response.get("status_code") != 200:
            print(f"❌ Elenco rotazioni imminenti fallito: {response}")
            return False
        
        if not isinstance(response, list):
            print(f"❌ Risposta non è una lista: {response}")
            return False
        
        print(f"✓ Elenco rotazioni imminenti: {len(response)} rotazioni trovate")
        return True
    
    def test_delete_credential(self) -> bool:
        """Verifica l'eliminazione di una credenziale."""
        response = self.request("DELETE", f"/credentials/{TEST_CREDENTIAL['name']}")
        
        if response.get("status_code") != 204:
            print(f"❌ Eliminazione fallita: {response}")
            return False
        
        # Verifica che sia stata effettivamente eliminata
        get_response = self.request("GET", f"/credentials/{TEST_CREDENTIAL['name']}")
        
        if get_response.get("status_code") != 404:
            print(f"❌ La credenziale non è stata eliminata: {get_response}")
            return False
        
        print(f"✓ Credenziale eliminata con successo")
        return True
    
    def run_all_tests(self):
        """Esegue tutti i test."""
        tests = [
            ("Health Check", self.test_health),
            ("Creazione credenziale", self.test_create_credential),
            ("Recupero credenziale", self.test_get_credential),
            ("Aggiornamento credenziale", self.test_update_credential),
            ("Rotazione credenziale", self.test_rotate_credential),
            ("Rollback credenziale", self.test_rollback_credential),
            ("Elenco credenziali", self.test_list_credentials),
            ("Rotazioni in attesa", self.test_pending_rotations),
            ("Rotazioni imminenti", self.test_upcoming_rotations),
            ("Eliminazione credenziale", self.test_delete_credential)
        ]
        
        print("\n=== TEST API DI ROTAZIONE CREDENZIALI ===")
        print(f"API URL: {self.base_url}")
        print("=" * 40)
        
        start_time = time.time()
        
        for test_name, test_func in tests:
            self.run_test(test_name, test_func)
        
        elapsed_time = time.time() - start_time
        
        print("\n=== RIEPILOGO DEI TEST ===")
        print(f"Test completati in {elapsed_time:.2f} secondi")
        print(f"Passati: {self.tests_passed}")
        print(f"Falliti: {self.tests_failed}")
        print(f"Saltati: {self.tests_skipped}")
        print("=" * 40)
        
        if self.tests_failed == 0:
            print("🎉 Tutti i test sono passati!")
            return True
        else:
            print(f"❌ {self.tests_failed} test falliti")
            return False

def main():
    """Funzione principale."""
    parser = argparse.ArgumentParser(description="Test dell'API di rotazione delle credenziali")
    parser.add_argument("--url", default=API_BASE_URL, help="URL base dell'API")
    parser.add_argument("--token", default=API_TOKEN, help="Token di autenticazione")
    
    args = parser.parse_args()
    
    tester = CredentialRotationApiTest(args.url, args.token)
    success = tester.run_all_tests()
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main() 