"""
Modulo per la gestione della sicurezza e stabilità di M4Bot.
Fornisce controlli per il sistema di self-healing, il WAF e i test di resilienza.
"""

import os
import sys
import json
import logging
import asyncio
import datetime
from typing import Dict, List, Any, Optional, Tuple, Union

import aiohttp
import asyncpg
import aioredis

# Importa i moduli di sicurezza e stabilità
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
from stability.self_healing.self_healing_system import get_self_healing_system
from stability.self_healing.chaos_testing import ChaosTestRunner, ServiceKillTest, ResourceExhaustionTest, NetworkFailureTest
from security.waf import WAFManager
from security.crypto import CryptoManager, get_crypto_manager

logger = logging.getLogger('stability_security')

class StabilitySecurityManager:
    """Gestisce le funzionalità di sicurezza e stabilità di M4Bot."""
    
    def __init__(self, db_pool: asyncpg.Pool, redis_pool: aioredis.ConnectionPool):
        self.db_pool = db_pool
        self.redis_pool = redis_pool
        self.self_healing = None
        self.waf_manager = None
        self.crypto_manager = None
        self.chaos_runner = None
        
    async def initialize(self):
        """Inizializza i componenti di sicurezza e stabilità."""
        try:
            # Inizializza self-healing system
            self.self_healing = get_self_healing_system()
            
            # Inizializza WAF
            self.waf_manager = WAFManager()
            
            # Inizializza crypto
            self.crypto_manager = get_crypto_manager()
            
            # Inizializza chaos testing
            self.chaos_runner = ChaosTestRunner()
            
            logger.info("Componenti di sicurezza e stabilità inizializzati")
            return True
        except Exception as e:
            logger.error(f"Errore nell'inizializzazione dei componenti di sicurezza e stabilità: {e}")
            return False
    
    async def get_system_status(self) -> Dict[str, Any]:
        """Ottiene lo stato attuale dei componenti di sicurezza e stabilità."""
        status = {
            "self_healing": {
                "enabled": False,
                "maintenance_mode": False,
                "services": {},
                "system_health": {},
                "last_check": None
            },
            "waf": {
                "enabled": False,
                "blocked_ips": 0,
                "recent_attacks": [],
                "rules_active": 0
            },
            "encryption": {
                "enabled": True,
                "key_rotation_status": "unknown",
                "last_rotation": None
            },
            "chaos_testing": {
                "last_test_run": None,
                "success_rate": None,
                "tests_available": 0
            }
        }
        
        # Aggiorna stato self-healing
        if self.self_healing:
            try:
                diagnostics = self.self_healing.get_diagnostics()
                status["self_healing"]["enabled"] = self.self_healing.config.get("enabled", False)
                status["self_healing"]["maintenance_mode"] = self.self_healing.config.get("maintenance_mode", False)
                
                if "services" in diagnostics:
                    status["self_healing"]["services"] = {
                        name: {
                            "is_healthy": service.get("is_healthy", False),
                            "last_check": service.get("last_check", 0),
                            "consecutive_failures": service.get("consecutive_failures", 0),
                            "last_error": service.get("last_error", "")
                        } for name, service in diagnostics["services"].items()
                    }
                
                if "system_health" in diagnostics:
                    status["self_healing"]["system_health"] = diagnostics["system_health"]
                
                status["self_healing"]["last_check"] = diagnostics.get("timestamp", None)
            except Exception as e:
                logger.error(f"Errore nel recupero diagnostica self-healing: {e}")
        
        # Aggiorna stato WAF
        if self.waf_manager:
            try:
                waf_stats = self.waf_manager.get_stats()
                status["waf"]["enabled"] = True
                status["waf"]["blocked_ips"] = waf_stats.get("blocked_ips", 0)
                status["waf"]["rules_active"] = len(self.waf_manager.config.get("rules", {}))
                
                # Ottieni gli ultimi 5 attacchi
                async with self.db_pool.acquire() as conn:
                    attacks = await conn.fetch("""
                        SELECT time, source_ip, attack_type, severity, details
                        FROM security_events
                        WHERE severity >= 'high'
                        ORDER BY time DESC
                        LIMIT 5
                    """)
                    
                    status["waf"]["recent_attacks"] = [dict(attack) for attack in attacks]
            except Exception as e:
                logger.error(f"Errore nel recupero statistiche WAF: {e}")
        
        # Aggiorna stato crittografia
        if self.crypto_manager:
            try:
                # Verifica quando è avvenuta l'ultima rotazione delle chiavi
                async with self.db_pool.acquire() as conn:
                    last_rotation = await conn.fetchval("""
                        SELECT MAX(rotation_time) FROM crypto_key_rotations
                    """)
                    
                    status["encryption"]["last_rotation"] = last_rotation
                    
                    # Determina se è necessaria una rotazione
                    needs_rotation = False
                    if last_rotation:
                        days_since_rotation = (datetime.datetime.now() - last_rotation).days
                        needs_rotation = days_since_rotation > 30  # Soglia: 30 giorni
                    
                    status["encryption"]["key_rotation_status"] = "needs_rotation" if needs_rotation else "ok"
            except Exception as e:
                logger.error(f"Errore nel recupero stato crittografia: {e}")
        
        # Aggiorna stato chaos testing
        try:
            async with self.db_pool.acquire() as conn:
                last_test = await conn.fetchrow("""
                    SELECT 
                        run_time, 
                        total_tests, 
                        successful_tests
                    FROM chaos_test_runs
                    ORDER BY run_time DESC
                    LIMIT 1
                """)
                
                if last_test:
                    status["chaos_testing"]["last_test_run"] = last_test["run_time"]
                    success_rate = (last_test["successful_tests"] / last_test["total_tests"]) * 100 if last_test["total_tests"] > 0 else 0
                    status["chaos_testing"]["success_rate"] = round(success_rate, 1)
                
                # Conta i test disponibili
                tests_count = await conn.fetchval("""
                    SELECT COUNT(*) FROM chaos_tests WHERE active = TRUE
                """)
                
                status["chaos_testing"]["tests_available"] = tests_count or 0
        except Exception as e:
            logger.error(f"Errore nel recupero stato chaos testing: {e}")
        
        return status
    
    async def get_self_healing_config(self) -> Dict[str, Any]:
        """Recupera la configurazione attuale del sistema di self-healing."""
        if not self.self_healing:
            return {}
        
        try:
            config = self.self_healing.config.copy()
            
            # Rimuovi dati sensibili o troppo dettagliati per l'interfaccia
            if "recovery_scripts" in config:
                config["recovery_scripts"] = {name: True for name in config["recovery_scripts"]}
            
            return config
        except Exception as e:
            logger.error(f"Errore nel recupero configurazione self-healing: {e}")
            return {}
    
    async def update_self_healing_config(self, new_config: Dict[str, Any]) -> bool:
        """Aggiorna la configurazione del sistema di self-healing."""
        if not self.self_healing:
            return False
        
        try:
            # Aggiorna solo i campi consentiti
            allowed_fields = [
                "enabled", "maintenance_mode", "recovery_threshold", 
                "max_restarts_per_day", "check_interval"
            ]
            
            for field in allowed_fields:
                if field in new_config:
                    self.self_healing.config[field] = new_config[field]
            
            # Salva la configurazione su file
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                                     "stability", "self_healing", "config.json")
            
            with open(config_path, "w") as f:
                json.dump(self.self_healing.config, f, indent=4)
            
            logger.info("Configurazione self-healing aggiornata")
            return True
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento configurazione self-healing: {e}")
            return False
    
    async def get_waf_config(self) -> Dict[str, Any]:
        """Recupera la configurazione attuale del Web Application Firewall."""
        if not self.waf_manager:
            return {}
        
        try:
            config = {}
            
            # Estrai i dati di configurazione del WAF
            config["enabled"] = self.waf_manager.config.get("enabled", True)
            config["log_only_mode"] = self.waf_manager.config.get("log_only_mode", False)
            config["rate_limits"] = self.waf_manager.config.get("rate_limits", {})
            config["rules"] = self.waf_manager.config.get("rules", {})
            config["whitelist"] = self.waf_manager.config.get("whitelist", {})
            
            return config
        except Exception as e:
            logger.error(f"Errore nel recupero configurazione WAF: {e}")
            return {}
    
    async def update_waf_config(self, new_config: Dict[str, Any]) -> bool:
        """Aggiorna la configurazione del Web Application Firewall."""
        if not self.waf_manager:
            return False
        
        try:
            # Aggiorna i campi principali
            if "enabled" in new_config:
                self.waf_manager.config["enabled"] = new_config["enabled"]
            
            if "log_only_mode" in new_config:
                self.waf_manager.config["log_only_mode"] = new_config["log_only_mode"]
            
            if "rate_limits" in new_config:
                self.waf_manager.config["rate_limits"] = new_config["rate_limits"]
            
            if "rules" in new_config:
                self.waf_manager.config["rules"] = new_config["rules"]
            
            if "whitelist" in new_config and "ips" in new_config["whitelist"]:
                self.waf_manager.config["whitelist"]["ips"] = new_config["whitelist"]["ips"]
            
            # Salva la configurazione
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                                     "security", "waf_config.json")
            
            with open(config_path, "w") as f:
                json.dump(self.waf_manager.config, f, indent=4)
            
            logger.info("Configurazione WAF aggiornata")
            return True
        except Exception as e:
            logger.error(f"Errore nell'aggiornamento configurazione WAF: {e}")
            return False
    
    async def block_ip(self, ip_address: str, reason: str, duration: Optional[int] = None) -> bool:
        """Blocca un indirizzo IP tramite il WAF."""
        if not self.waf_manager:
            return False
        
        try:
            permanent = duration is None
            if permanent:
                success, message = self.waf_manager.block_ip(ip_address, permanent=True)
            else:
                success, message = self.waf_manager.block_ip(ip_address, permanent=False, duration_minutes=duration)
            
            if success:
                # Registra l'azione nel database
                async with self.db_pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO ip_block_history (ip_address, reason, permanent, duration_minutes, added_time)
                        VALUES ($1, $2, $3, $4, NOW())
                    """, ip_address, reason, permanent, duration)
                
                logger.info(f"IP {ip_address} bloccato: {message}")
            else:
                logger.error(f"Errore nel blocco IP {ip_address}: {message}")
            
            return success
        except Exception as e:
            logger.error(f"Errore nel blocco IP {ip_address}: {e}")
            return False
    
    async def unblock_ip(self, ip_address: str) -> bool:
        """Sblocca un indirizzo IP dal WAF."""
        if not self.waf_manager:
            return False
        
        try:
            success, message = self.waf_manager.unblock_ip(ip_address)
            
            if success:
                # Aggiorna il database
                async with self.db_pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE ip_block_history 
                        SET removed_time = NOW(), active = FALSE
                        WHERE ip_address = $1 AND active = TRUE
                    """, ip_address)
                
                logger.info(f"IP {ip_address} sbloccato: {message}")
            else:
                logger.error(f"Errore nello sblocco IP {ip_address}: {message}")
            
            return success
        except Exception as e:
            logger.error(f"Errore nello sblocco IP {ip_address}: {e}")
            return False
    
    async def get_blocked_ips(self) -> List[Dict[str, Any]]:
        """Recupera la lista degli IP bloccati."""
        try:
            async with self.db_pool.acquire() as conn:
                blocked_ips = await conn.fetch("""
                    SELECT 
                        ip_address, 
                        reason, 
                        permanent, 
                        duration_minutes, 
                        added_time,
                        removed_time,
                        active
                    FROM ip_block_history
                    WHERE active = TRUE
                    ORDER BY added_time DESC
                """)
                
                return [dict(ip) for ip in blocked_ips]
        except Exception as e:
            logger.error(f"Errore nel recupero IP bloccati: {e}")
            return []
    
    async def run_chaos_test(self, test_type: str, target: str, options: Dict[str, Any] = None) -> Dict[str, Any]:
        """Esegue un test di resilienza (chaos testing)."""
        if not self.chaos_runner:
            return {"success": False, "error": "Chaos testing non inizializzato"}
        
        try:
            # Crea il test appropriato
            test = None
            if test_type == "service_kill":
                test = ServiceKillTest(target, duration=options.get("duration", 120))
            elif test_type == "resource_exhaustion":
                test = ResourceExhaustionTest(
                    target, 
                    intensity=options.get("intensity", 80),
                    duration=options.get("duration", 90)
                )
            elif test_type == "network_failure":
                test = NetworkFailureTest(
                    target,
                    failure_type=options.get("failure_type", "latency"),
                    duration=options.get("duration", 120)
                )
            else:
                return {"success": False, "error": f"Tipo di test non supportato: {test_type}"}
            
            # Aggiungi il test al runner
            self.chaos_runner.add_test(test)
            
            # Esegui il test
            results = await self.chaos_runner.run_all_tests()
            
            # Genera report HTML
            html_report = self.chaos_runner.generate_html_report()
            
            # Salva i risultati nel database
            async with self.db_pool.acquire() as conn:
                run_id = await conn.fetchval("""
                    INSERT INTO chaos_test_runs 
                    (run_time, total_tests, successful_tests, failed_tests)
                    VALUES (NOW(), $1, $2, $3)
                    RETURNING id
                """, results['total_tests'], results['successful_tests'], results['failed_tests'])
                
                # Salva i dettagli dei test
                for test_result in results['test_results']:
                    await conn.execute("""
                        INSERT INTO chaos_test_results
                        (run_id, test_name, test_type, description, success, duration, error, results_json)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """, 
                      run_id,
                      test_result['name'],
                      test_type,
                      test_result['description'],
                      test_result['success'],
                      test_result['actual_duration'],
                      test_result['error'],
                      json.dumps(test_result['results'])
                    )
            
            return {
                "success": True,
                "results": results,
                "report_path": html_report
            }
        except Exception as e:
            logger.error(f"Errore nell'esecuzione del test di chaos: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_last_chaos_test_results(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Recupera i risultati degli ultimi test di resilienza."""
        try:
            async with self.db_pool.acquire() as conn:
                runs = await conn.fetch("""
                    SELECT 
                        id, 
                        run_time, 
                        total_tests, 
                        successful_tests, 
                        failed_tests
                    FROM chaos_test_runs
                    ORDER BY run_time DESC
                    LIMIT $1
                """, limit)
                
                results = []
                for run in runs:
                    run_dict = dict(run)
                    
                    # Recupera i dettagli dei test in questa esecuzione
                    tests = await conn.fetch("""
                        SELECT 
                            test_name, 
                            test_type, 
                            success, 
                            duration,
                            error
                        FROM chaos_test_results
                        WHERE run_id = $1
                    """, run["id"])
                    
                    run_dict["tests"] = [dict(test) for test in tests]
                    results.append(run_dict)
                
                return results
        except Exception as e:
            logger.error(f"Errore nel recupero risultati chaos test: {e}")
            return []
    
    async def rotate_encryption_keys(self) -> Dict[str, Any]:
        """Ruota le chiavi di crittografia."""
        if not self.crypto_manager:
            return {"success": False, "error": "Gestore crittografia non inizializzato"}
        
        try:
            # Esegui la rotazione delle chiavi
            rotated_keys = self.crypto_manager._crypto.rotate_expired_keys()
            
            # Registra la rotazione nel database
            async with self.db_pool.acquire() as conn:
                for key_id in rotated_keys:
                    await conn.execute("""
                        INSERT INTO crypto_key_rotations 
                        (key_id, rotation_time, rotated_by)
                        VALUES ($1, NOW(), 'admin')
                    """, key_id)
            
            return {
                "success": True,
                "rotated_keys": len(rotated_keys),
                "key_ids": list(rotated_keys.keys())
            }
        except Exception as e:
            logger.error(f"Errore nella rotazione delle chiavi: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_encryption_stats(self) -> Dict[str, Any]:
        """Recupera statistiche sulla crittografia."""
        if not self.crypto_manager:
            return {}
        
        try:
            stats = {
                "total_keys": 0,
                "last_rotation": None,
                "key_age": {},
                "encryption_operations": {
                    "total": 0,
                    "failures": 0
                }
            }
            
            # Recupera statistiche dal database
            async with self.db_pool.acquire() as conn:
                # Ultima rotazione
                last_rotation = await conn.fetchrow("""
                    SELECT key_id, rotation_time
                    FROM crypto_key_rotations
                    ORDER BY rotation_time DESC
                    LIMIT 1
                """)
                
                if last_rotation:
                    stats["last_rotation"] = {
                        "key_id": last_rotation["key_id"],
                        "time": last_rotation["rotation_time"]
                    }
                
                # Statistiche operazioni
                op_stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN success = FALSE THEN 1 ELSE 0 END) as failures
                    FROM crypto_operations
                    WHERE operation_time > NOW() - INTERVAL '30 days'
                """)
                
                if op_stats:
                    stats["encryption_operations"]["total"] = op_stats["total"]
                    stats["encryption_operations"]["failures"] = op_stats["failures"]
                
                # Età delle chiavi
                key_ages = await conn.fetch("""
                    SELECT 
                        key_id,
                        MAX(rotation_time) as last_rotation,
                        NOW() - MAX(rotation_time) as age
                    FROM crypto_key_rotations
                    GROUP BY key_id
                """)
                
                for key in key_ages:
                    stats["key_age"][key["key_id"]] = {
                        "last_rotation": key["last_rotation"],
                        "age_days": key["age"].days if key["age"] else None
                    }
                
                stats["total_keys"] = len(stats["key_age"])
            
            return stats
        except Exception as e:
            logger.error(f"Errore nel recupero statistiche crittografia: {e}")
            return {}
    
    async def get_recent_security_events(self, days: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
        """Recupera gli eventi di sicurezza recenti."""
        try:
            async with self.db_pool.acquire() as conn:
                events = await conn.fetch("""
                    SELECT 
                        time, 
                        source_ip, 
                        event_type, 
                        severity, 
                        details,
                        mitigated
                    FROM security_events
                    WHERE time > NOW() - INTERVAL '$1 days'
                    ORDER BY time DESC
                    LIMIT $2
                """, days, limit)
                
                return [dict(event) for event in events]
        except Exception as e:
            logger.error(f"Errore nel recupero eventi di sicurezza: {e}")
            return []
    
    async def get_security_summary(self) -> Dict[str, Any]:
        """Genera un riepilogo dello stato di sicurezza del sistema."""
        summary = {
            "total_attacks_blocked": 0,
            "critical_events_24h": 0,
            "top_attack_sources": [],
            "top_attack_types": [],
            "security_score": 0,  # 0-100
            "recommendations": []
        }
        
        try:
            async with self.db_pool.acquire() as conn:
                # Totale attacchi bloccati
                total_blocked = await conn.fetchval("""
                    SELECT COUNT(*) FROM security_events
                    WHERE mitigated = TRUE
                """)
                summary["total_attacks_blocked"] = total_blocked or 0
                
                # Eventi critici nelle ultime 24 ore
                critical_events = await conn.fetchval("""
                    SELECT COUNT(*) FROM security_events
                    WHERE severity = 'critical' AND time > NOW() - INTERVAL '24 hours'
                """)
                summary["critical_events_24h"] = critical_events or 0
                
                # Top 5 sorgenti di attacco
                attack_sources = await conn.fetch("""
                    SELECT source_ip, COUNT(*) as count
                    FROM security_events
                    WHERE time > NOW() - INTERVAL '7 days'
                    GROUP BY source_ip
                    ORDER BY count DESC
                    LIMIT 5
                """)
                summary["top_attack_sources"] = [
                    {"ip": source["source_ip"], "count": source["count"]}
                    for source in attack_sources
                ]
                
                # Top 5 tipi di attacco
                attack_types = await conn.fetch("""
                    SELECT event_type, COUNT(*) as count
                    FROM security_events
                    WHERE time > NOW() - INTERVAL '7 days'
                    GROUP BY event_type
                    ORDER BY count DESC
                    LIMIT 5
                """)
                summary["top_attack_types"] = [
                    {"type": type_["event_type"], "count": type_["count"]}
                    for type_ in attack_types
                ]
                
                # Calcola security score
                # Fattori: WAF attivo, self-healing attivo, % attacchi bloccati, età chiavi, ecc.
                score = 50  # Partenza
                
                # WAF attivo: +20 punti
                if self.waf_manager and self.waf_manager.config.get("enabled", False):
                    score += 20
                else:
                    summary["recommendations"].append("Attiva il Web Application Firewall")
                
                # Self-healing attivo: +15 punti
                if self.self_healing and self.self_healing.config.get("enabled", False):
                    score += 15
                else:
                    summary["recommendations"].append("Attiva il sistema di self-healing")
                
                # Rotazione chiavi recente: +10 punti
                if summary.get("last_rotation") and isinstance(summary["last_rotation"], dict):
                    last_rotation_time = summary["last_rotation"].get("time")
                    if last_rotation_time:
                        days_since_rotation = (datetime.datetime.now() - last_rotation_time).days
                        if days_since_rotation < 30:
                            score += 10
                        else:
                            summary["recommendations"].append("Ruota le chiavi di crittografia")
                
                # Penalità per eventi critici recenti
                if critical_events:
                    score -= min(20, critical_events * 2)  # Max -20 punti
                
                summary["security_score"] = max(0, min(100, score))
                
            return summary
        except Exception as e:
            logger.error(f"Errore nella generazione del riepilogo di sicurezza: {e}")
            return summary 