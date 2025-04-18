"""
Routes per il monitoraggio del sistema M4Bot
Fornisce API per il recupero di informazioni sullo stato del sistema e dei servizi
"""

import os
import psutil
import platform
import socket
import time
import json
import datetime
import asyncio
from quart import Blueprint, jsonify, render_template, request, current_app
from web.auth.decorators import admin_required
from modules.stability_security import get_service_status

# Inizializzazione del blueprint
system_bp = Blueprint('system', __name__, url_prefix='/admin')

# Funzioni di utilità
def get_size(bytes, suffix="B"):
    """
    Scala i byte in un formato leggibile
    """
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f} {unit}{suffix}"
        bytes /= factor

def get_system_info():
    """
    Recupera informazioni generali sul sistema
    """
    try:
        # Informazioni sulla piattaforma
        uname = platform.uname()
        
        # Informazioni sull'host
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(socket.gethostname())
        
        # Informazioni sul boot
        boot_time_timestamp = psutil.boot_time()
        bt = datetime.datetime.fromtimestamp(boot_time_timestamp)
        
        # Calcola l'uptime
        uptime_seconds = time.time() - boot_time_timestamp
        uptime_days = int(uptime_seconds // (24 * 3600))
        uptime_hours = int((uptime_seconds % (24 * 3600)) // 3600)
        uptime_minutes = int((uptime_seconds % 3600) // 60)
        uptime = f"{uptime_days}g {uptime_hours}h {uptime_minutes}m"
        
        # Informazioni sulla CPU
        cpu_info = {
            "cores": psutil.cpu_count(logical=False),
            "logical_cores": psutil.cpu_count(logical=True),
            "max_frequency": psutil.cpu_freq().max if psutil.cpu_freq() else "N/A",
            "current_frequency": psutil.cpu_freq().current if psutil.cpu_freq() else "N/A",
            "model": uname.processor or "N/A"
        }
        
        # Informazioni sulla memoria
        mem = psutil.virtual_memory()
        total_memory_gb = mem.total / (1024 ** 3)
        
        return {
            "os_name": uname.system,
            "os_version": uname.version,
            "hostname": hostname,
            "ip_address": ip_address,
            "kernel_version": uname.release,
            "architecture": uname.machine,
            "cpu_model": cpu_info["model"],
            "cpu_cores": cpu_info["cores"],
            "cpu_logical_cores": cpu_info["logical_cores"],
            "cpu_max_freq": cpu_info["max_frequency"],
            "total_memory": f"{total_memory_gb:.2f}",
            "boot_time": bt.strftime("%Y-%m-%d %H:%M:%S"),
            "uptime": uptime
        }
    except Exception as e:
        current_app.logger.error(f"Errore nel recupero delle informazioni di sistema: {str(e)}")
        return {}

def get_cpu_info():
    """
    Recupera informazioni sulla CPU
    """
    try:
        # Utilizzo CPU
        cpu_percent = psutil.cpu_percent(interval=0.5)
        
        # Frequenza CPU
        cpu_freq = psutil.cpu_freq()
        if cpu_freq:
            freq_current = cpu_freq.current
        else:
            freq_current = 0
            
        # Temperatura CPU (solo su alcune piattaforme)
        temperature = None
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if name.lower() in ['coretemp', 'cpu_thermal']:
                        temperature = entries[0].current
                        break
        
        return {
            "usage": cpu_percent,
            "frequency": freq_current,
            "temperature": temperature
        }
    except Exception as e:
        current_app.logger.error(f"Errore nel recupero delle informazioni CPU: {str(e)}")
        return {"usage": 0, "frequency": 0, "temperature": None}

def get_memory_info():
    """
    Recupera informazioni sulla memoria
    """
    try:
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            "total": get_size(mem.total),
            "available": get_size(mem.available),
            "used": get_size(mem.used),
            "usage": mem.percent,
            "swap_total": get_size(swap.total),
            "swap_used": get_size(swap.used),
            "swap_usage": swap.percent
        }
    except Exception as e:
        current_app.logger.error(f"Errore nel recupero delle informazioni sulla memoria: {str(e)}")
        return {"usage": 0, "total": "0 B", "available": "0 B", "used": "0 B"}

def get_disk_info():
    """
    Recupera informazioni sui dischi
    """
    try:
        partitions = []
        for part in psutil.disk_partitions():
            if os.name == 'nt':
                if 'cdrom' in part.opts or part.fstype == '':
                    continue
            try:
                usage = psutil.disk_usage(part.mountpoint)
                partitions.append({
                    "device": part.device,
                    "mount": part.mountpoint,
                    "fstype": part.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent
                })
            except PermissionError:
                continue
                
        # Statistiche di I/O del disco
        io_counters = psutil.disk_io_counters()
        if io_counters:
            disk_io = {
                "read_bytes": get_size(io_counters.read_bytes),
                "write_bytes": get_size(io_counters.write_bytes),
                "read_count": io_counters.read_count,
                "write_count": io_counters.write_count
            }
        else:
            disk_io = None
            
        # Calcola l'utilizzo medio di tutti i dischi
        total_usage = sum(p["percent"] for p in partitions) / len(partitions) if partitions else 0
            
        return {
            "partitions": partitions,
            "io": disk_io,
            "usage": total_usage
        }
    except Exception as e:
        current_app.logger.error(f"Errore nel recupero delle informazioni sui dischi: {str(e)}")
        return {"usage": 0, "partitions": []}

def get_network_info():
    """
    Recupera informazioni sulla rete
    """
    try:
        # Statistiche di I/O di rete
        io_counters = psutil.net_io_counters()
        network_io = {
            "bytes_sent": io_counters.bytes_sent,
            "bytes_recv": io_counters.bytes_recv,
            "packets_sent": io_counters.packets_sent,
            "packets_recv": io_counters.packets_recv,
            "errin": io_counters.errin,
            "errout": io_counters.errout,
            "dropin": io_counters.dropin,
            "dropout": io_counters.dropout
        }
        
        # Connessioni di rete
        connections = []
        for conn in psutil.net_connections(kind='inet'):
            connections.append({
                "fd": conn.fd,
                "family": conn.family.name if hasattr(conn.family, 'name') else conn.family,
                "type": conn.type.name if hasattr(conn.type, 'name') else conn.type,
                "local_address": conn.laddr.ip if conn.laddr else "",
                "local_port": conn.laddr.port if conn.laddr else 0,
                "remote_address": conn.raddr.ip if conn.raddr else "",
                "remote_port": conn.raddr.port if conn.raddr else 0,
                "status": conn.status,
                "pid": conn.pid
            })
            
        # Interfacce di rete
        interfaces = []
        for name, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    interfaces.append({
                        "name": name,
                        "address": addr.address,
                        "netmask": addr.netmask,
                        "broadcast": addr.broadcast
                    })
                    
        # Dati di velocità
        rx_rate = 0
        tx_rate = 0
                    
        return {
            "io": network_io,
            "connections": connections,
            "interfaces": interfaces,
            "rx_rate": rx_rate,
            "tx_rate": tx_rate
        }
    except Exception as e:
        current_app.logger.error(f"Errore nel recupero delle informazioni di rete: {str(e)}")
        return {"rx_rate": 0, "tx_rate": 0, "connections": []}

def get_services_info():
    """
    Recupera informazioni sui servizi M4Bot
    """
    try:
        # Verifica se il modulo di gestione servizi è disponibile
        services = get_service_status() if 'get_service_status' in globals() else []
        if not services:
            # Dati di esempio per lo sviluppo
            services = [
                {
                    "id": "m4bot-core",
                    "name": "M4Bot Core",
                    "status": "running",
                    "pid": 12345,
                    "cpu": 1.2,
                    "memory": 3.5
                },
                {
                    "id": "m4bot-web",
                    "name": "M4Bot Web Server",
                    "status": "running",
                    "pid": 12346,
                    "cpu": 0.8,
                    "memory": 2.1
                },
                {
                    "id": "m4bot-telegram",
                    "name": "M4Bot Telegram",
                    "status": "running",
                    "pid": 12347,
                    "cpu": 0.5,
                    "memory": 1.7
                },
                {
                    "id": "m4bot-discord",
                    "name": "M4Bot Discord",
                    "status": "stopped",
                    "pid": None,
                    "cpu": None,
                    "memory": None
                },
                {
                    "id": "m4bot-database",
                    "name": "M4Bot Database",
                    "status": "running",
                    "pid": 12348,
                    "cpu": 1.5,
                    "memory": 4.2
                }
            ]
            
        return services
    except Exception as e:
        current_app.logger.error(f"Errore nel recupero delle informazioni sui servizi: {str(e)}")
        return []

def get_system_alerts():
    """
    Recupera avvisi di sistema recenti
    """
    try:
        # In una versione produzione, questi dati verrebbero recuperati da un log o da un database
        # Per lo sviluppo, usiamo dati di esempio
        alerts = [
            {
                "id": 1,
                "timestamp": datetime.datetime.now().isoformat(),
                "severity": "critical",
                "source": "Sistema",
                "message": "Utilizzo CPU elevato (95%) negli ultimi 5 minuti"
            },
            {
                "id": 2,
                "timestamp": (datetime.datetime.now() - datetime.timedelta(minutes=5)).isoformat(),
                "severity": "warning",
                "source": "Memoria",
                "message": "Memoria disponibile sotto la soglia (85% utilizzo)"
            },
            {
                "id": 3,
                "timestamp": (datetime.datetime.now() - datetime.timedelta(minutes=15)).isoformat(),
                "severity": "info",
                "source": "Servizio Telegram",
                "message": "Riavvio automatico completato con successo"
            },
            {
                "id": 4,
                "timestamp": (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat(),
                "severity": "warning",
                "source": "Database",
                "message": "Rallentamento query rilevato (>200ms)"
            },
            {
                "id": 5,
                "timestamp": (datetime.datetime.now() - datetime.timedelta(hours=2)).isoformat(),
                "severity": "info",
                "source": "Sistema",
                "message": "Aggiornamento di sicurezza installato"
            }
        ]
        
        return alerts
    except Exception as e:
        current_app.logger.error(f"Errore nel recupero degli avvisi di sistema: {str(e)}")
        return []

# Dati per il monitoraggio della velocità di rete
last_net_io = None
last_net_time = None

def get_net_speed():
    """
    Calcola la velocità di trasferimento dati della rete
    """
    global last_net_io, last_net_time
    
    try:
        # Ottieni i dati correnti
        current_net_io = psutil.net_io_counters()
        current_time = time.time()
        
        if last_net_io is None or last_net_time is None:
            # Prima chiamata, imposta i valori iniziali
            last_net_io = current_net_io
            last_net_time = current_time
            return 0.0, 0.0
            
        # Calcola il tempo trascorso
        time_delta = current_time - last_net_time
        if time_delta < 0.1:  # Previene divisione per zero o valori anomali
            return 0.0, 0.0
            
        # Calcola i byte trasferiti
        rx_bytes = current_net_io.bytes_recv - last_net_io.bytes_recv
        tx_bytes = current_net_io.bytes_sent - last_net_io.bytes_sent
        
        # Calcola la velocità in KB/s
        rx_rate = rx_bytes / time_delta / 1024
        tx_rate = tx_bytes / time_delta / 1024
        
        # Aggiorna i valori per la prossima chiamata
        last_net_io = current_net_io
        last_net_time = current_time
        
        return rx_rate, tx_rate
    except Exception as e:
        current_app.logger.error(f"Errore nel calcolo della velocità di rete: {str(e)}")
        return 0.0, 0.0

# Routes
@system_bp.route('/monitoring')
@admin_required
async def monitoring_page():
    """
    Pagina di monitoraggio del sistema
    """
    return await render_template('admin/monitoring.html')

@system_bp.route('/api/system/stats')
@admin_required
async def system_stats():
    """
    API per ottenere statistiche di sistema in tempo reale
    """
    try:
        # Calcola la velocità di rete
        rx_rate, tx_rate = get_net_speed()
        
        # Recupera informazioni sul sistema
        cpu_info = get_cpu_info()
        memory_info = get_memory_info()
        disk_info = get_disk_info()
        
        # Recupera informazioni di rete
        network_info = get_network_info()
        network_info["rx_rate"] = rx_rate
        network_info["tx_rate"] = tx_rate
        
        # Costruisci la risposta JSON
        response = {
            "cpu": cpu_info,
            "memory": memory_info,
            "disk": disk_info,
            "network": network_info,
            "system_info": get_system_info(),
            "services": get_services_info(),
            "alerts": get_system_alerts(),
            "disks": disk_info["partitions"],
            "network_connections": network_info["connections"][:20]  # Limita a 20 connessioni
        }
        
        return jsonify(response)
    except Exception as e:
        current_app.logger.error(f"Errore nell'API system_stats: {str(e)}")
        return jsonify({
            "error": "Si è verificato un errore nel recupero dei dati di sistema"
        }), 500

@system_bp.route('/api/service/restart/<service_id>', methods=['POST'])
@admin_required
async def restart_service(service_id):
    """
    API per riavviare un servizio
    """
    try:
        # In produzione, questo chiamerebbe un sistema di gestione servizi reale
        # Per ora, simuliamo una risposta positiva
        
        # Aggiungi un ritardo artificiale per simulare l'operazione
        await asyncio.sleep(1.5)
        
        current_app.logger.info(f"Riavvio servizio {service_id} richiesto")
        
        return jsonify({
            "success": True,
            "message": f"Servizio {service_id} riavviato con successo"
        })
    except Exception as e:
        current_app.logger.error(f"Errore nel riavvio del servizio {service_id}: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"Errore durante il riavvio del servizio: {str(e)}"
        }), 500

def init_app(app):
    """
    Inizializza le rotte nell'app
    """
    app.register_blueprint(system_bp) 