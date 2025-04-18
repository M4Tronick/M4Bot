#!/bin/bash
# Script di monitoraggio per M4Bot
# Consigliato: impostare come cron job per esecuzione periodica
# crontab -e
# */10 * * * * /opt/m4bot/scripts/monitor.sh > /var/log/m4bot_monitor.log 2>&1

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Impostazioni
LOG_FILE="/var/log/m4bot_monitor.log"
ALERT_EMAIL="admin@m4bot.it"  # Cambia con il tuo indirizzo email
THRESHOLD_CPU=80              # Soglia CPU (percentuale)
THRESHOLD_RAM=80              # Soglia RAM (percentuale)
THRESHOLD_DISK=80             # Soglia disco (percentuale)
CHECK_INTERVAL=10             # Intervallo controllo (minuti)

# Funzione per inviare un'email di avviso
send_alert() {
    local subject="$1"
    local message="$2"
    
    if command -v mail > /dev/null; then
        echo "$message" | mail -s "$subject" "$ALERT_EMAIL"
    else
        echo "$subject: $message" >> "$LOG_FILE"
    fi
    
    print_warning "$subject: $message"
}

# Funzione per verificare un servizio
check_service() {
    local service_name="$1"
    if ! systemctl is-active --quiet "$service_name"; then
        send_alert "Servizio $service_name non attivo" "Il servizio $service_name non Ã¨ in esecuzione sul server M4Bot. Tentativo di riavvio in corso..."
        systemctl restart "$service_name"
    fi
}

# Ottieni informazioni sul sistema
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')
RAM_TOTAL=$(free -m | awk '/Mem:/ {print $2}')
RAM_USED=$(free -m | awk '/Mem:/ {print $3}')
RAM_USAGE=$(( RAM_USED * 100 / RAM_TOTAL ))
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')

echo "============================================"
echo "M4Bot Monitor - $(date)"
echo "============================================"
echo "CPU: ${CPU_USAGE}%"
echo "RAM: ${RAM_USAGE}% (${RAM_USED}MB / ${RAM_TOTAL}MB)"
echo "DISCO: ${DISK_USAGE}%"
echo "============================================"

# Controlla i servizi M4Bot
check_service "m4bot-bot.service"
check_service "m4bot-web.service"
check_service "nginx"
check_service "postgresql"

# Verifica CPU
if (( $(echo "$CPU_USAGE > $THRESHOLD_CPU" | bc -l) )); then
    send_alert "Utilizzo CPU elevato" "L'utilizzo della CPU ha raggiunto ${CPU_USAGE}%, sopra la soglia del ${THRESHOLD_CPU}%."
fi

# Verifica RAM
if [ "$RAM_USAGE" -gt "$THRESHOLD_RAM" ]; then
    send_alert "Utilizzo RAM elevato" "L'utilizzo della RAM ha raggiunto ${RAM_USAGE}%, sopra la soglia del ${THRESHOLD_RAM}%."
fi

# Verifica Disco
if [ "$DISK_USAGE" -gt "$THRESHOLD_DISK" ]; then
    send_alert "Spazio su disco ridotto" "L'utilizzo del disco ha raggiunto ${DISK_USAGE}%, sopra la soglia del ${THRESHOLD_DISK}%."
fi

# Verifica i log per errori critici
if [ -f "/opt/m4bot/bot/logs/m4bot.log" ]; then
    ERRORS=$(grep -i "error\|exception\|critical" /opt/m4bot/bot/logs/m4bot.log | tail -n 10)
    if [ -n "$ERRORS" ]; then
        send_alert "Errori rilevati nei log del bot" "Ultimi errori rilevati nei log:\n$ERRORS"
    fi
fi

# Controlla i file di log per evitare che diventino troppo grandi
LOG_SIZE=$(du -m /var/log | sort -nr | head -n 1 | cut -f1)
if [ "$LOG_SIZE" -gt 1000 ]; then  # Se i log superano 1GB
    send_alert "Dimensione log eccessiva" "I file di log stanno occupando piÃ¹ di 1GB di spazio. Considera una rotazione o pulizia."
fi

echo "Monitoraggio completato." 