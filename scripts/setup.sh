#!/bin/bash
# Script per l'installazione e la configurazione passo-passo di M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

print_message "Benvenuto nello script di configurazione di M4Bot"
print_message "Questo script guiderà l'installazione passo-passo"

# Funzione per eseguire una fase e controllare se ha avuto successo
execute_step() {
    local step_name="$1"
    local command="$2"
    
    print_message "[PASSO] $step_name..."
    
    eval "$command"
    
    if [ $? -eq 0 ]; then
        print_success "Completato: $step_name"
        return 0
    else
        print_error "Errore durante: $step_name" 0
        read -p "Vuoi riprovare questo passaggio? (s/n): " retry
        if [ "$retry" == "s" ]; then
            execute_step "$step_name" "$command"
        else
            return 1
        fi
    fi
}

# Esegui ogni fase dell'installazione
execute_step "Aggiornamento del sistema" "apt-get update && apt-get upgrade -y"

execute_step "Installazione dipendenze di sistema" "apt-get install -y python3 python3-pip python3-venv postgresql nginx certbot python3-certbot-nginx git python3-bcrypt"

execute_step "Configurazione del database PostgreSQL" "$PWD/setup_postgres.sh"

execute_step "Inizializzazione del database" "$PWD/init_database.sh"

execute_step "Installazione dei wrapper di sistema" "$PWD/install-wrappers.sh"

execute_step "Configurazione di Nginx" "$PWD/setup_nginx.sh"

execute_step "Configurazione dei servizi systemd" "$PWD/setup_services.sh"

print_success "Installazione completata con successo!"
print_message "Puoi ora utilizzare i seguenti comandi:"
print_message "- m4bot-start:   Avvia il bot e i servizi correlati"
print_message "- m4bot-stop:    Ferma il bot e i servizi correlati"
print_message "- m4bot-status:  Mostra lo stato del bot e dei servizi"
print_message "- m4bot-restart: Riavvia il bot e i servizi correlati" 