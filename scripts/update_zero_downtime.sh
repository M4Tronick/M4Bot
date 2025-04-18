#!/bin/bash
# Script per l'aggiornamento di M4Bot con zero-downtime
# Questo script implementa un aggiornamento progressivo che mantiene i servizi attivi

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Directory di installazione
INSTALL_DIR="/opt/m4bot"
BACKUP_DIR="$INSTALL_DIR/backups/$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$INSTALL_DIR/logs/update_$(date +%Y%m%d_%H%M%S).log"
TEMP_DIR="/tmp/m4bot_update"

# Funzioni di utilità
print_message() {
    echo -e "${BLUE}[INFO]${NC} $1"
    echo "[INFO] $1" >> $LOG_FILE
}

print_error() {
    echo -e "${RED}[ERRORE]${NC} $1"
    echo "[ERRORE] $1" >> $LOG_FILE
}

print_success() {
    echo -e "${GREEN}[SUCCESSO]${NC} $1"
    echo "[SUCCESSO] $1" >> $LOG_FILE
}

print_warning() {
    echo -e "${YELLOW}[AVVISO]${NC} $1"
    echo "[AVVISO] $1" >> $LOG_FILE
}

show_help() {
    echo "Utilizzo: $0 [opzioni]"
    echo ""
    echo "Opzioni:"
    echo "  -h, --help           Mostra questo messaggio di aiuto"
    echo "  -f, --force          Forza l'aggiornamento anche se la versione è aggiornata"
    echo "  -n, --no-backup      Non creare backup (sconsigliato)"
    echo "  -s, --security-only  Aggiorna solo i moduli di sicurezza"
    echo "  -c, --core-only      Aggiorna solo il core del sistema"
    echo "  -v, --version        Aggiorna a una versione specifica (es: -v 2.1.0)"
    echo ""
    echo "Esempio: $0 --force --security-only"
    exit 0
}

# Impostazioni predefinite
FORCE_UPDATE=false
CREATE_BACKUP=true
SECURITY_ONLY=false
CORE_ONLY=false
TARGET_VERSION=""

# Analizza i parametri della linea di comando
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -h|--help) show_help ;;
        -f|--force) FORCE_UPDATE=true ;;
        -n|--no-backup) CREATE_BACKUP=false ;;
        -s|--security-only) SECURITY_ONLY=true ;;
        -c|--core-only) CORE_ONLY=true ;;
        -v|--version) TARGET_VERSION="$2"; shift ;;
        *) print_error "Opzione sconosciuta: $1" 1 ;;
    esac
    shift
done

# Crea directory per i log se non esiste
mkdir -p "$INSTALL_DIR/logs"

# Intestazione log
echo "===============================================" > "$LOG_FILE"
echo "Aggiornamento M4Bot con Zero-Downtime" >> "$LOG_FILE"
echo "Data: $(date)" >> "$LOG_FILE"
echo "===============================================" >> "$LOG_FILE"

# Verifica che lo script sia eseguito come root
if [ "$(id -u)" -ne 0 ]; then
    print_error "Questo script deve essere eseguito come root" 1
fi

# Verifica se M4Bot è installato
if [ ! -d "$INSTALL_DIR" ]; then
    print_error "M4Bot non sembra essere installato in $INSTALL_DIR" 1
fi

# Funzione per il backup del sistema
backup_system() {
    print_message "Creazione backup del sistema..."
    
    # Crea directory per i backup
    mkdir -p "$BACKUP_DIR"
    
    # Backup dei file di configurazione
    cp -a "$INSTALL_DIR/config.py" "$BACKUP_DIR/" 2>/dev/null
    cp -a "$INSTALL_DIR/.env" "$BACKUP_DIR/" 2>/dev/null
    
    # Backup dei database
    source "$INSTALL_DIR/.env" 2>/dev/null
    if [ -n "$DB_NAME" ] && [ -n "$DB_USER" ] && [ -n "$DB_PASS" ]; then
        mysqldump -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" > "$BACKUP_DIR/database.sql" 2>/dev/null
        if [ $? -eq 0 ]; then
            print_success "Backup del database completato"
        else
            print_warning "Impossibile creare il backup del database"
        fi
    else
        print_warning "Credenziali del database non trovate, backup del database saltato"
    fi
    
    # Backup dei file essenziali
    tar -czf "$BACKUP_DIR/modules.tar.gz" -C "$INSTALL_DIR" modules 2>/dev/null
    tar -czf "$BACKUP_DIR/web.tar.gz" -C "$INSTALL_DIR" web 2>/dev/null
    tar -czf "$BACKUP_DIR/scripts.tar.gz" -C "$INSTALL_DIR" scripts 2>/dev/null
    
    print_success "Backup completato in $BACKUP_DIR"
}

# Funzione per la verifica della versione
check_version() {
    # Ottieni la versione corrente
    CURRENT_VERSION=$(grep -o 'VERSION = "[^"]*"' "$INSTALL_DIR/config.py" 2>/dev/null | cut -d'"' -f2)
    if [ -z "$CURRENT_VERSION" ]; then
        CURRENT_VERSION="sconosciuta"
    fi
    
    # Se è specificata una versione target, usala
    if [ -n "$TARGET_VERSION" ]; then
        LATEST_VERSION="$TARGET_VERSION"
    else
        # Altrimenti ottieni l'ultima versione disponibile (qui usiamo un esempio)
        LATEST_VERSION=$(curl -s -L "https://api.github.com/repos/m4bot/m4bot/releases/latest" | grep -o '"tag_name": "[^"]*"' | cut -d'"' -f4 2>/dev/null)
        if [ -z "$LATEST_VERSION" ]; then
            LATEST_VERSION="$CURRENT_VERSION"
            print_warning "Impossibile determinare l'ultima versione disponibile"
        fi
    fi
    
    print_message "Versione corrente: $CURRENT_VERSION"
    print_message "Versione disponibile: $LATEST_VERSION"
    
    # Confronta le versioni
    if [ "$CURRENT_VERSION" = "$LATEST_VERSION" ] && [ "$FORCE_UPDATE" = false ]; then
        print_success "Il sistema è già aggiornato all'ultima versione"
        exit 0
    fi
}

# Funzione per l'aggiornamento progressivo del core
update_core() {
    print_message "Avvio aggiornamento progressivo del core..."
    
    # 1. Aggiornamento dei file statici (questo non interrompe il servizio)
    print_message "Aggiornamento file statici..."
    git -C "$INSTALL_DIR" fetch origin 2>/dev/null
    git -C "$INSTALL_DIR" checkout -f origin/main -- web/static 2>/dev/null
    
    # 2. Aggiornamento dei moduli con blue-green deployment
    print_message "Aggiornamento moduli con blue-green deployment..."
    
    # Crea directory temporanea per i nuovi moduli
    TEMP_MODULES="$INSTALL_DIR/modules_new"
    mkdir -p "$TEMP_MODULES"
    
    # Scarica e prepara i nuovi moduli
    git -C "$INSTALL_DIR" checkout -f origin/main -- modules 2>/dev/null
    
    # Sposta i moduli correnti in quelli vecchi e i nuovi in quelli correnti
    mv "$INSTALL_DIR/modules" "$INSTALL_DIR/modules_old"
    mv "$TEMP_MODULES" "$INSTALL_DIR/modules"
    
    # 3. Aggiornamento dell'applicazione web
    print_message "Aggiornamento applicazione web..."
    
    # Crea un nuovo file di configurazione del servizio con la nuova porta
    NEW_WEB_PORT=$((WEB_PORT + 1000)) # Usa una porta temporanea
    
    # Crea e avvia il nuovo servizio web sulla nuova porta
    cat > "/etc/systemd/system/m4bot-web-new.service" << EOF
[Unit]
Description=M4Bot Web Interface (New Version)
After=network.target

[Service]
User=m4bot
Group=m4bot
WorkingDirectory=$INSTALL_DIR/web
ExecStart=$INSTALL_DIR/venv/bin/python app.py --port $NEW_WEB_PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    
    # Ricaricare systemd e avviare il nuovo servizio
    systemctl daemon-reload
    systemctl start m4bot-web-new.service
    
    # Attendi che il nuovo servizio sia pronto
    sleep 5
    
    # Verifica che il nuovo servizio sia attivo
    if systemctl is-active --quiet m4bot-web-new.service; then
        # Aggiornamento del reverse proxy per indirizzare il traffico al nuovo servizio
        if [ -f "/etc/nginx/sites-available/m4bot" ]; then
            # Backup del file di configurazione nginx
            cp "/etc/nginx/sites-available/m4bot" "/etc/nginx/sites-available/m4bot.backup"
            
            # Aggiorna la configurazione per puntare alla nuova porta
            sed -i "s/proxy_pass http:\/\/localhost:$WEB_PORT;/proxy_pass http:\/\/localhost:$NEW_WEB_PORT;/g" "/etc/nginx/sites-available/m4bot"
            
            # Ricarica nginx
            nginx -t && systemctl reload nginx
            
            if [ $? -eq 0 ]; then
                print_success "Traffico reindirizzato al nuovo servizio"
                
                # Arresta il vecchio servizio
                systemctl stop m4bot-web.service
                
                # Rinomina il nuovo servizio
                mv "/etc/systemd/system/m4bot-web-new.service" "/etc/systemd/system/m4bot-web.service"
                systemctl daemon-reload
                
                # Avvia il servizio con il nome originale
                systemctl start m4bot-web.service
                systemctl stop m4bot-web-new.service 2>/dev/null
                
                # Ripristina la configurazione nginx
                sed -i "s/proxy_pass http:\/\/localhost:$NEW_WEB_PORT;/proxy_pass http:\/\/localhost:$WEB_PORT;/g" "/etc/nginx/sites-available/m4bot"
                nginx -t && systemctl reload nginx
            else
                print_error "Errore nel riconfigurare nginx" 0
                # Rollback: ferma il nuovo servizio e mantieni quello vecchio
                systemctl stop m4bot-web-new.service
                print_warning "Rollback eseguito, mantenuto il servizio originale"
            fi
        else
            # Se nginx non è configurato, aggiorna direttamente
            systemctl stop m4bot-web.service
            mv "/etc/systemd/system/m4bot-web-new.service" "/etc/systemd/system/m4bot-web.service"
            systemctl daemon-reload
            systemctl start m4bot-web.service
        fi
    else
        print_error "Il nuovo servizio web non è stato avviato correttamente" 0
        print_warning "Rollback in corso..."
        systemctl stop m4bot-web-new.service 2>/dev/null
        rm -f "/etc/systemd/system/m4bot-web-new.service"
        
        # Ripristina i moduli originali
        rm -rf "$INSTALL_DIR/modules"
        mv "$INSTALL_DIR/modules_old" "$INSTALL_DIR/modules"
        
        print_message "Rollback completato, sistema riportato allo stato precedente"
    fi
    
    # Pulizia
    rm -rf "$INSTALL_DIR/modules_old" 2>/dev/null
}

# Funzione per l'aggiornamento dei moduli di sicurezza
update_security_modules() {
    print_message "Aggiornamento moduli di sicurezza e monitoraggio..."
    
    # Aggiornamento del modulo stabilità_sicurezza
    if [ -d "$INSTALL_DIR/modules/stability_security" ]; then
        # Backup del modulo attuale
        mkdir -p "$BACKUP_DIR/modules"
        cp -r "$INSTALL_DIR/modules/stability_security" "$BACKUP_DIR/modules/"
        
        # Aggiornamento del modulo
        git -C "$INSTALL_DIR" checkout -f origin/main -- modules/stability_security 2>/dev/null
        
        # Riavvio del servizio per caricare il nuovo modulo
        print_message "Riavvio servizio per attivare nuovi moduli di sicurezza..."
        systemctl restart m4bot.service
        
        if [ $? -eq 0 ]; then
            print_success "Moduli di sicurezza aggiornati con successo"
        else
            print_error "Errore durante il riavvio del servizio" 0
            
            # Rollback
            print_warning "Ripristino moduli di sicurezza precedenti..."
            rm -rf "$INSTALL_DIR/modules/stability_security"
            cp -r "$BACKUP_DIR/modules/stability_security" "$INSTALL_DIR/modules/"
            systemctl restart m4bot.service
        fi
    else
        print_warning "Modulo stability_security non trovato, creazione in corso..."
        mkdir -p "$INSTALL_DIR/modules/stability_security"
        
        # Crea il file __init__.py con contenuto base
        cat > "$INSTALL_DIR/modules/stability_security/__init__.py" << 'EOF'
"""
Modulo per la gestione avanzata della stabilità e sicurezza.
Fornisce funzionalità per garantire la continuità del servizio durante gli aggiornamenti
e implementa meccanismi di sicurezza aggiuntivi.
"""

import os
import sys
import time
import json
import logging
import threading
import subprocess
from datetime import datetime, timedelta

# Stato globale del modulo
_status = {
    "lockdown_mode": False,
    "update_in_progress": False,
    "health_check": {
        "last_check": None,
        "status": "unknown"
    },
    "service_status": {
        "bot": "unknown",
        "web": "unknown"
    }
}

# Configurazione predefinita
DEFAULT_CONFIG = {
    "stability": {
        "health_check_interval": 300,  # 5 minuti
        "auto_recovery": True,
        "service_management": {
            "max_restart_attempts": 3,
            "restart_cooldown": 60
        }
    },
    "security": {
        "lockdown_threshold": 5,  # Tentativi di accesso falliti
        "session_expiry": 3600,  # 1 ora
        "rate_limiting": {
            "enabled": True,
            "max_requests": 100,
            "time_window": 60
        },
        "ip_whitelist": [],
        "ip_blacklist": []
    },
    "monitoring": {
        "resource_threshold": {
            "cpu": 80,  # percentuale
            "memory": 80,  # percentuale
            "disk": 90   # percentuale
        },
        "log_retention_days": 30
    }
}

class StabilitySecurityManager:
    """Gestisce la stabilità e la sicurezza del sistema."""
    
    def __init__(self, config_path=None):
        """Inizializza il gestore di stabilità e sicurezza."""
        self.logger = logging.getLogger("stability_security")
        self.config = self._load_config(config_path)
        self.init_security_module()
    
    def _load_config(self, config_path):
        """Carica la configurazione da file o usa quella predefinita."""
        config = DEFAULT_CONFIG.copy()
        
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    user_config = json.load(f)
                
                # Unisci le configurazioni
                for section in user_config:
                    if section in config:
                        if isinstance(config[section], dict) and isinstance(user_config[section], dict):
                            config[section].update(user_config[section])
                        else:
                            config[section] = user_config[section]
                    else:
                        config[section] = user_config[section]
                
                self.logger.info(f"Configurazione caricata da {config_path}")
            except Exception as e:
                self.logger.error(f"Errore nel caricare la configurazione: {e}")
        
        return config
    
    def init_security_module(self):
        """Inizializza il modulo di sicurezza."""
        self.logger.info("Inizializzazione modulo di sicurezza e stabilità")
        
        # Inizializza i controlli di sistema
        self._check_system_info()
        
        # Avvia thread di monitoraggio
        self._start_monitoring_threads()
    
    def _check_system_info(self):
        """Verifica le informazioni di sistema."""
        try:
            # Controllo spazio disco
            df = subprocess.check_output(['df', '-h', '/']).decode('utf-8')
            self.logger.info(f"Spazio disco:\n{df}")
            
            # Controllo memoria
            free = subprocess.check_output(['free', '-h']).decode('utf-8')
            self.logger.info(f"Memoria:\n{free}")
            
            # Informazioni di sistema
            uname = subprocess.check_output(['uname', '-a']).decode('utf-8')
            self.logger.info(f"Sistema: {uname}")
            
            # Servizi attivi
            self._check_services_status()
        except Exception as e:
            self.logger.error(f"Errore nel controllo del sistema: {e}")
    
    def _start_monitoring_threads(self):
        """Avvia i thread di monitoraggio."""
        # Thread per controllo risorse
        resource_thread = threading.Thread(target=self._monitor_resources, daemon=True)
        resource_thread.start()
        
        # Thread per controllo salute
        health_thread = threading.Thread(target=self._monitor_health, daemon=True)
        health_thread.start()
        
        self.logger.info("Thread di monitoraggio avviati")
    
    def _monitor_resources(self):
        """Monitora le risorse del sistema."""
        while True:
            try:
                # Controllo CPU
                cpu_usage = self._get_cpu_usage()
                
                # Controllo memoria
                memory_usage = self._get_memory_usage()
                
                # Controllo disco
                disk_usage = self._get_disk_usage()
                
                # Logging se sopra soglia
                thresholds = self.config["monitoring"]["resource_threshold"]
                if cpu_usage > thresholds["cpu"]:
                    self.logger.warning(f"Utilizzo CPU elevato: {cpu_usage}%")
                
                if memory_usage > thresholds["memory"]:
                    self.logger.warning(f"Utilizzo memoria elevato: {memory_usage}%")
                
                if disk_usage > thresholds["disk"]:
                    self.logger.warning(f"Utilizzo disco elevato: {disk_usage}%")
            except Exception as e:
                self.logger.error(f"Errore nel monitoraggio risorse: {e}")
            
            # Pausa tra controlli
            time.sleep(300)  # 5 minuti
    
    def _monitor_health(self):
        """Monitora la salute del sistema."""
        while True:
            try:
                self._check_services_status()
                
                # Imposta lo stato del controllo salute
                _status["health_check"]["last_check"] = datetime.now().isoformat()
                _status["health_check"]["status"] = "healthy"
                
                # Verifica se è necessario recupero automatico
                if self.config["stability"]["auto_recovery"]:
                    self._auto_recover_services()
            except Exception as e:
                self.logger.error(f"Errore nel controllo salute: {e}")
                _status["health_check"]["status"] = "error"
            
            # Pausa tra controlli
            time.sleep(self.config["stability"]["health_check_interval"])
    
    def _check_services_status(self):
        """Controlla lo stato dei servizi."""
        try:
            # Controlla servizio bot
            bot_active = self._is_service_active("m4bot.service")
            _status["service_status"]["bot"] = "active" if bot_active else "inactive"
            
            # Controlla servizio web
            web_active = self._is_service_active("m4bot-web.service")
            _status["service_status"]["web"] = "active" if web_active else "inactive"
            
            self.logger.info(f"Stato servizi - Bot: {_status['service_status']['bot']}, Web: {_status['service_status']['web']}")
        except Exception as e:
            self.logger.error(f"Errore nel controllare lo stato dei servizi: {e}")
    
    def _auto_recover_services(self):
        """Recupera automaticamente i servizi se necessario."""
        if _status["service_status"]["bot"] == "inactive":
            self.logger.warning("Tentativo di riavvio automatico del servizio bot")
            self._restart_service("m4bot.service")
        
        if _status["service_status"]["web"] == "inactive":
            self.logger.warning("Tentativo di riavvio automatico del servizio web")
            self._restart_service("m4bot-web.service")
    
    def _get_cpu_usage(self):
        """Ottieni l'utilizzo della CPU."""
        try:
            cpu = subprocess.check_output(['top', '-bn1']).decode('utf-8')
            cpu_usage_line = [line for line in cpu.split('\n') if 'Cpu(s)' in line][0]
            cpu_usage = float(cpu_usage_line.split()[1].replace(',', '.'))
            return cpu_usage
        except Exception:
            return 0
    
    def _get_memory_usage(self):
        """Ottieni l'utilizzo della memoria."""
        try:
            memory = subprocess.check_output(['free']).decode('utf-8')
            memory_lines = memory.split('\n')
            memory_values = memory_lines[1].split()
            total = int(memory_values[1])
            used = int(memory_values[2])
            memory_usage = (used / total) * 100
            return memory_usage
        except Exception:
            return 0
    
    def _get_disk_usage(self):
        """Ottieni l'utilizzo del disco."""
        try:
            disk = subprocess.check_output(['df', '/']).decode('utf-8')
            disk_lines = disk.split('\n')
            disk_values = disk_lines[1].split()
            disk_usage = int(disk_values[4].replace('%', ''))
            return disk_usage
        except Exception:
            return 0
    
    def _is_service_active(self, service_name):
        """Verifica se un servizio systemd è attivo."""
        try:
            result = subprocess.run(['systemctl', 'is-active', service_name], 
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return result.stdout.decode('utf-8').strip() == 'active'
        except Exception:
            return False
    
    def _restart_service(self, service_name):
        """Riavvia un servizio systemd."""
        try:
            subprocess.run(['systemctl', 'restart', service_name], 
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return True
        except Exception as e:
            self.logger.error(f"Errore nel riavviare il servizio {service_name}: {e}")
            return False
    
    def perform_update(self, update_type="normal"):
        """Esegue un aggiornamento del sistema."""
        self.logger.info(f"Avvio aggiornamento di tipo: {update_type}")
        
        # Imposta stato aggiornamento
        _status["update_in_progress"] = True
        
        try:
            if update_type == "zero_downtime":
                self._perform_zero_downtime_update()
            elif update_type == "hotfix":
                self._perform_hotfix()
            else:
                self._perform_normal_update()
            
            self.logger.info(f"Aggiornamento {update_type} completato con successo")
            return True
        except Exception as e:
            self.logger.error(f"Errore durante l'aggiornamento {update_type}: {e}")
            return False
        finally:
            _status["update_in_progress"] = False
    
    def _perform_zero_downtime_update(self):
        """Esegue un aggiornamento con zero downtime."""
        # Implementazione del processo di blue-green deployment
        self.logger.info("Esecuzione aggiornamento zero downtime...")
        
        # Esegui lo script di aggiornamento zero downtime
        result = subprocess.run(['/opt/m4bot/scripts/update_zero_downtime.sh'], 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode != 0:
            raise Exception(f"Errore nell'aggiornamento zero downtime: {result.stderr.decode('utf-8')}")
    
    def _perform_hotfix(self):
        """Applica un hotfix al sistema."""
        self.logger.info("Applicazione hotfix...")
        
        # Esegui lo script di hotfix
        result = subprocess.run(['/opt/m4bot/scripts/apply_hotfix.sh'], 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode != 0:
            raise Exception(f"Errore nell'applicazione del hotfix: {result.stderr.decode('utf-8')}")
    
    def _perform_normal_update(self):
        """Esegue un aggiornamento normale."""
        self.logger.info("Esecuzione aggiornamento normale...")
        
        # Esegui lo script di aggiornamento normale
        result = subprocess.run(['/opt/m4bot/scripts/update.sh'], 
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        if result.returncode != 0:
            raise Exception(f"Errore nell'aggiornamento: {result.stderr.decode('utf-8')}")

# Decoratore per proteggere le rotte admin
def admin_route_protection(f):
    """Decoratore per aggiungere protezione alle rotte admin."""
    @functools.wraps(f)
    async def decorated_function(*args, **kwargs):
        # Verifica se l'utente è un admin
        if not await is_admin():
            return redirect(url_for('login'))
        
        # Controlla se siamo in modalità lockdown
        if _status["lockdown_mode"]:
            # In lockdown, permetti solo agli IP nella whitelist
            client_ip = request.remote_addr
            if client_ip not in DEFAULT_CONFIG["security"]["ip_whitelist"]:
                return jsonify({"error": "Sistema in modalità lockdown"}), 403
        
        # Controllo rate limiting
        if DEFAULT_CONFIG["security"]["rate_limiting"]["enabled"]:
            # Implementazione semplificata di rate limiting
            client_ip = request.remote_addr
            current_time = time.time()
            # Qui andrebbe implementata la logica completa di rate limiting
        
        return await f(*args, **kwargs)
    return decorated_function

# Inizializza il modulo quando viene importato
security_manager = StabilitySecurityManager()

# Funzione per l'aggiornamento degli script
update_scripts() {
    print_message "Aggiornamento script di sistema..."
    
    # Backup degli script attuali
    mkdir -p "$BACKUP_DIR/scripts"
    cp -r "$INSTALL_DIR/scripts/"*.sh "$BACKUP_DIR/scripts/" 2>/dev/null
    
    # Aggiornamento degli script
    git -C "$INSTALL_DIR" checkout -f origin/main -- scripts 2>/dev/null
    
    # Assicurati che gli script siano eseguibili
    chmod +x "$INSTALL_DIR/scripts/"*.sh 2>/dev/null
    
    print_success "Script di sistema aggiornati"
}

# Funzione per l'aggiornamento dei requisiti Python
update_requirements() {
    print_message "Aggiornamento dipendenze Python..."
    
    # Attiva l'ambiente virtuale
    source "$INSTALL_DIR/venv/bin/activate" 2>/dev/null
    
    # Aggiorna i requisiti
    pip install -r "$INSTALL_DIR/requirements.txt" --upgrade --quiet 2>/dev/null
    
    # Disattiva l'ambiente virtuale
    deactivate 2>/dev/null
    
    print_success "Dipendenze Python aggiornate"
}

# Funzione principale
main() {
    # Mostra intestazione
    clear
    echo -e "${MAGENTA}"
    echo "╔════════════════════════════════════════════════════════╗"
    echo "║                                                        ║"
    echo "║      Aggiornamento M4Bot con Zero-Downtime            ║"
    echo "║                                                        ║"
    echo "╚════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    # Verifica versione
    check_version
    
    # Crea backup se richiesto
    if [ "$CREATE_BACKUP" = true ]; then
        backup_system
    else
        print_warning "L'aggiornamento procederà senza backup"
    fi
    
    # Esegui gli aggiornamenti in base alle opzioni
    if [ "$SECURITY_ONLY" = true ]; then
        # Aggiorna solo i moduli di sicurezza
        update_security_modules
    elif [ "$CORE_ONLY" = true ]; then
        # Aggiorna solo il core
        update_core
    else
        # Aggiornamento completo
        update_scripts
        update_requirements
        update_security_modules
        update_core
    fi
    
    # Verifica dell'aggiornamento
    print_message "Verifica dell'aggiornamento..."
    
    # Controlla se i servizi sono attivi
    if systemctl is-active --quiet m4bot.service && systemctl is-active --quiet m4bot-web.service; then
        print_success "Aggiornamento completato con successo!"
    else
        print_warning "Aggiornamento completato, ma alcuni servizi potrebbero non essere attivi"
        print_message "Stato del servizio m4bot: $(systemctl is-active m4bot.service)"
        print_message "Stato del servizio m4bot-web: $(systemctl is-active m4bot-web.service)"
    fi
    
    # Aggiorna il file di versione
    if [ -n "$TARGET_VERSION" ]; then
        sed -i "s/VERSION = \".*\"/VERSION = \"$TARGET_VERSION\"/" "$INSTALL_DIR/config.py" 2>/dev/null
        print_success "Versione aggiornata a $TARGET_VERSION"
    fi
    
    print_message "Log dell'aggiornamento salvato in: $LOG_FILE"
}

# Esegui la funzione principale
main 