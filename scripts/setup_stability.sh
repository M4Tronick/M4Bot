#!/bin/bash
# Script di installazione dei moduli di stabilità di M4Bot
# Questo script installa e configura tutti i componenti necessari per
# il sistema di stabilità, self-healing e monitoraggio.

set -e  # Termina in caso di errore

# Colori per output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directory base
BASE_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_DIR="$BASE_DIR/M4Bot-Config"
SYSTEMD_DIR="/etc/systemd/system"

# Logo
echo -e "${GREEN}"
echo "  __  __ _  _  ____        _        "
echo " |  \/  | || || __ )  ___ | |_      "
echo " | |\/| | || ||  _ \ / _ \| __|     "
echo " | |  | |__   _| |_) | (_) | |_      "
echo " |_|  |_|  |_||____/ \___/ \__|     "
echo -e "${NC}"
echo -e "${YELLOW}Installazione Moduli di Stabilità${NC}\n"

# Controlla se l'utente è root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}Questo script deve essere eseguito come root${NC}"
  exit 1
fi

# Controlla la presenza di Python 3.8+
echo -e "${YELLOW}Verifica prerequisiti...${NC}"
python3 --version | grep -E "Python 3\.(8|9|10|11|12)" > /dev/null
if [ $? -ne 0 ]; then
  echo -e "${RED}È richiesto Python 3.8 o superiore${NC}"
  exit 1
fi

# Installa dipendenze
echo -e "${YELLOW}Installazione dipendenze...${NC}"
pip3 install psutil aiohttp pytest locust

# Crea directory necessarie
echo -e "${YELLOW}Creazione directory...${NC}"
mkdir -p "$BASE_DIR/logs/reports"
mkdir -p "$BASE_DIR/stability/monitoring/monitoring_data"
mkdir -p "$BASE_DIR/stability/self_healing/chaos_reports"

# Controlla se esistono i file di configurazione, altrimenti crea esempi
echo -e "${YELLOW}Configurazione...${NC}"
mkdir -p "$CONFIG_DIR"

if [ ! -f "$CONFIG_DIR/self_healing.json" ]; then
    echo -e "${YELLOW}Creazione esempio di configurazione self-healing...${NC}"
    cp "$BASE_DIR/stability/self_healing/self_healing_example.json" "$CONFIG_DIR/self_healing.json" 2>/dev/null || \
    echo '{
        "services": {
            "web": {
                "type": "systemd",
                "unit": "m4bot-web.service",
                "check_type": "systemd",
                "max_restarts": 5,
                "failure_threshold": 3
            },
            "bot": {
                "type": "systemd",
                "unit": "m4bot-bot.service",
                "check_type": "systemd",
                "max_restarts": 5,
                "failure_threshold": 3
            }
        },
        "system": {
            "check_interval": 60,
            "service_check_interval": 30,
            "cleanup_interval": 3600,
            "max_restarts": 5,
            "restart_window": 300
        }
    }' > "$CONFIG_DIR/self_healing.json"
fi

if [ ! -f "$CONFIG_DIR/monitoring.json" ]; then
    echo -e "${YELLOW}Creazione esempio di configurazione monitoraggio...${NC}"
    cp "$BASE_DIR/stability/monitoring/config.json" "$CONFIG_DIR/monitoring.json" 2>/dev/null || \
    echo '{
        "system_metrics_interval": 60,
        "app_metrics_interval": 30,
        "service_check_interval": 60,
        "data_dir": "./monitoring_data",
        "log_level": "INFO",
        "enable_prometheus": false,
        "prometheus_port": 9090
    }' > "$CONFIG_DIR/monitoring.json"
fi

# Crea unità systemd per il self-healing
echo -e "${YELLOW}Creazione servizi systemd...${NC}"

cat > "$SYSTEMD_DIR/m4bot-self-healing.service" << EOF
[Unit]
Description=M4Bot Self-Healing System
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$BASE_DIR
ExecStart=/usr/bin/python3 $BASE_DIR/stability/self_healing/self_healing_system.py --config $CONFIG_DIR/self_healing.json
Restart=on-failure
RestartSec=5
SyslogIdentifier=m4bot-self-healing

[Install]
WantedBy=multi-user.target
EOF

cat > "$SYSTEMD_DIR/m4bot-monitoring.service" << EOF
[Unit]
Description=M4Bot System Monitoring
After=network.target

[Service]
User=root
Group=root
WorkingDirectory=$BASE_DIR
ExecStart=/usr/bin/python3 $BASE_DIR/scripts/monitor_system.py --config $CONFIG_DIR/monitoring.json
Restart=on-failure
RestartSec=5
SyslogIdentifier=m4bot-monitoring

[Install]
WantedBy=multi-user.target
EOF

# Ricarica systemd, abilita e avvia i servizi
echo -e "${YELLOW}Configurazione servizi...${NC}"
systemctl daemon-reload
systemctl enable m4bot-self-healing.service
systemctl enable m4bot-monitoring.service

echo -e "${YELLOW}Avvio servizi...${NC}"
systemctl start m4bot-self-healing.service
systemctl start m4bot-monitoring.service

# Verifica stato
echo -e "${YELLOW}Verifica stato servizi...${NC}"
systemctl status m4bot-self-healing.service --no-pager
systemctl status m4bot-monitoring.service --no-pager

echo -e "\n${GREEN}Installazione completata con successo!${NC}"
echo -e "Servizi di stabilità sono ora in esecuzione."
echo -e "Per monitorare lo stato, usa: systemctl status m4bot-monitoring.service"
echo -e "Per controllare i log: journalctl -u m4bot-self-healing -f"
echo -e "\nReport di monitoraggio disponibili in: $BASE_DIR/logs/reports/" 