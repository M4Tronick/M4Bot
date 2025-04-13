#!/bin/bash
# Script per controllare lo stato di M4Bot

# Carica le funzioni comuni
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

print_message "Controllo dello stato di M4Bot..."

# Mostra informazioni di sistema
show_system_info

# Verifica lo stato dei servizi
print_step "Stato dei servizi di M4Bot:"

echo -e "${CYAN}Servizio bot:${NC}"
if is_service_active "m4bot-bot.service"; then
    systemctl status m4bot-bot.service --no-pager | grep -E "Active:|Main PID:"
    echo -e "${GREEN}● Attivo${NC}"
    echo -n "In esecuzione da: "
    systemctl show -p ActiveEnterTimestamp --value m4bot-bot.service | xargs -I{} date -d "{}" "+%Y-%m-%d %H:%M:%S"
    
    # Mostra utilizzo delle risorse
    BOT_PID=$(systemctl show -p MainPID --value m4bot-bot.service)
    if [ "$BOT_PID" != "0" ]; then
        echo -n "Utilizzo CPU: "
        ps -p $BOT_PID -o %cpu= | xargs
        echo -n "Utilizzo memoria: "
        ps -p $BOT_PID -o %mem= | xargs
    fi
else
    echo -e "${RED}○ Inattivo${NC}"
fi

echo -e "\n${CYAN}Servizio web:${NC}"
if is_service_active "m4bot-web.service"; then
    systemctl status m4bot-web.service --no-pager | grep -E "Active:|Main PID:"
    echo -e "${GREEN}● Attivo${NC}"
    echo -n "In esecuzione da: "
    systemctl show -p ActiveEnterTimestamp --value m4bot-web.service | xargs -I{} date -d "{}" "+%Y-%m-%d %H:%M:%S"
    
    # Mostra utilizzo delle risorse
    WEB_PID=$(systemctl show -p MainPID --value m4bot-web.service)
    if [ "$WEB_PID" != "0" ]; then
        echo -n "Utilizzo CPU: "
        ps -p $WEB_PID -o %cpu= | xargs
        echo -n "Utilizzo memoria: "
        ps -p $WEB_PID -o %mem= | xargs
    fi
else
    echo -e "${RED}○ Inattivo${NC}"
fi

# Controlla lo stato del database
echo -e "\n${CYAN}Database PostgreSQL:${NC}"
if is_service_active "postgresql"; then
    echo -e "${GREEN}● Attivo${NC}"
    
    # Verifica se possiamo connetterci al database
    if [ -f "$INSTALL_DIR/db_credentials.conf" ]; then
        source "$INSTALL_DIR/db_credentials.conf"
        if su - postgres -c "psql -d $DATABASE_NAME -c '\l' >/dev/null 2>&1"; then
            echo -e "Connessione al database: ${GREEN}OK${NC}"
            
            # Mostra le statistiche del database
            echo "Statistiche del database:"
            su - postgres -c "psql -d $DATABASE_NAME -c 'SELECT COUNT(*) FROM pg_stat_activity WHERE datname = '\''$DATABASE_NAME'\'';'" | grep -v "COUNT" | grep -v "-----" | xargs -I{} echo "  Connessioni attive: {}"
        else
            echo -e "Connessione al database: ${RED}FALLITA${NC}"
        fi
    else
        echo "Credenziali del database non trovate in $INSTALL_DIR/db_credentials.conf"
    fi
else
    echo -e "${RED}○ Inattivo${NC}"
fi

# Controllo server Nginx
echo -e "\n${CYAN}Server web Nginx:${NC}"
if is_service_active "nginx"; then
    echo -e "${GREEN}● Attivo${NC}"
    # Verifica della configurazione
    nginx -t 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "Configurazione: ${GREEN}OK${NC}"
    else
        echo -e "Configurazione: ${RED}ERRORI${NC}"
    fi
    
    # Controlla se la porta 80 è in ascolto
    if netstat -tulpn 2>/dev/null | grep -q ":80 "; then
        echo -e "Porta 80: ${GREEN}In ascolto${NC}"
    else
        echo -e "Porta 80: ${RED}Non in ascolto${NC}"
    fi
    
    # Controlla se la porta 443 è in ascolto (HTTPS)
    if netstat -tulpn 2>/dev/null | grep -q ":443 "; then
        echo -e "Porta 443 (HTTPS): ${GREEN}In ascolto${NC}"
    else
        echo -e "Porta 443 (HTTPS): ${RED}Non in ascolto${NC}"
    fi
else
    echo -e "${RED}○ Inattivo${NC}"
fi

# Verifica gli errori nei log
print_step "Controllo dei log per errori recenti:"

if [ -f "$LOGS_DIR/bot-error.log" ]; then
    ERROR_COUNT=$(grep -c "ERROR\|Error\|error\|Exception\|exception" "$LOGS_DIR/bot-error.log")
    if [ $ERROR_COUNT -gt 0 ]; then
        echo -e "${YELLOW}Trovati $ERROR_COUNT errori nel log del bot${NC}"
        echo "Ultimi 3 errori:"
        grep -m 3 "ERROR\|Error\|error\|Exception\|exception" "$LOGS_DIR/bot-error.log" | tail -3
    else
        echo -e "${GREEN}Nessun errore nel log del bot${NC}"
    fi
else
    echo "File di log bot-error.log non trovato"
fi

if [ -f "$LOGS_DIR/web-error.log" ]; then
    ERROR_COUNT=$(grep -c "ERROR\|Error\|error\|Exception\|exception" "$LOGS_DIR/web-error.log")
    if [ $ERROR_COUNT -gt 0 ]; then
        echo -e "${YELLOW}Trovati $ERROR_COUNT errori nel log dell'applicazione web${NC}"
        echo "Ultimi 3 errori:"
        grep -m 3 "ERROR\|Error\|error\|Exception\|exception" "$LOGS_DIR/web-error.log" | tail -3
    else
        echo -e "${GREEN}Nessun errore nel log dell'applicazione web${NC}"
    fi
else
    echo "File di log web-error.log non trovato"
fi

# Informazioni di rete
print_step "Informazioni di rete:"
echo -e "${CYAN}Interfacce di rete:${NC}"
ip -4 addr | grep -v "127.0.0.1" | grep "inet " | awk '{print "  " $NF ": " $2}'

echo -e "\n${CYAN}Porte in ascolto:${NC}"
netstat -tulpn 2>/dev/null | grep "LISTEN" | awk '{print "  " $4 " - " $7}' | grep -v "127.0.0.1"

# Informazioni finali
if is_service_active "m4bot-bot.service" && is_service_active "m4bot-web.service"; then
    print_success "M4Bot è completamente operativo"
    echo -e "${GREEN}===============================================${NC}"
    echo -e "${GREEN}M4Bot è in esecuzione e accessibile!${NC}"
    
    # Ottieni l'URL dall'host
    HOST=$(grep -i "server_name" /etc/nginx/sites-available/m4bot.conf 2>/dev/null | head -1 | awk '{print $2}' | sed 's/;//')
    if [ -n "$HOST" ]; then
        echo -e "${GREEN}URL: https://$HOST${NC}"
    fi
    echo -e "${GREEN}===============================================${NC}"
else
    print_warning "M4Bot non è completamente operativo"
    echo -e "${YELLOW}===============================================${NC}"
    echo -e "${YELLOW}Alcuni servizi di M4Bot non sono in esecuzione${NC}"
    echo -e "${YELLOW}Usa 'm4bot-start' per avviare tutti i servizi${NC}"
    echo -e "${YELLOW}===============================================${NC}"
fi
