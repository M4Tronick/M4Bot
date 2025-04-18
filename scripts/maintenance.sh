#!/bin/bash
# Script per attivare/disattivare la modalitÃ  di manutenzione di M4Bot

# Carica le funzioni comuni
source "$(dirname "$0")/common.sh"

# Verifica che l'utente sia root
check_root

# Definizione delle variabili
NGINX_CONFIG="/etc/nginx/sites-available/m4bot"
MAINTENANCE_PAGE="/opt/m4bot/web/static/emergency.html"
MAINTENANCE_FLAG="/opt/m4bot/.maintenance"

# Funzione per mostrare l'help
show_help() {
    echo "Utilizzo: $0 [OPZIONE]"
    echo "Attiva o disattiva la modalitÃ  di manutenzione per M4Bot."
    echo ""
    echo "Opzioni:"
    echo "  --enable, -e    Attiva la modalitÃ  di manutenzione"
    echo "  --disable, -d   Disattiva la modalitÃ  di manutenzione"
    echo "  --status, -s    Mostra lo stato della modalitÃ  di manutenzione"
    echo "  --help, -h      Mostra questo messaggio di aiuto"
    echo ""
    echo "Esempio:"
    echo "  $0 --enable     Attiva la modalitÃ  di manutenzione"
}

# Funzione per attivare la modalitÃ  di manutenzione
enable_maintenance() {
    print_message "Attivazione della modalitÃ  di manutenzione..."
    
    # Controlla se la modalitÃ  di manutenzione Ã¨ giÃ  attiva
    if [ -f "$MAINTENANCE_FLAG" ]; then
        print_warning "La modalitÃ  di manutenzione Ã¨ giÃ  attiva"
        return 0
    fi
    
    # Verifica l'esistenza della pagina di manutenzione
    if [ ! -f "$MAINTENANCE_PAGE" ]; then
        print_error "Pagina di manutenzione non trovata: $MAINTENANCE_PAGE" 1
    fi
    
    # Crea il file flag
    touch "$MAINTENANCE_FLAG" || print_error "Impossibile creare il file flag di manutenzione" 1
    
    # Crea un backup della configurazione Nginx se non esiste
    if [ ! -f "${NGINX_CONFIG}.backup" ]; then
        cp "$NGINX_CONFIG" "${NGINX_CONFIG}.backup" || print_error "Impossibile creare backup della configurazione Nginx" 1
    fi
    
    # Modifica la configurazione Nginx per servire la pagina di manutenzione
    if [ -f "$NGINX_CONFIG" ]; then
        # Aggiungi la configurazione di manutenzione all'inizio del blocco server se non presente
        if ! grep -q "maintenance_mode" "$NGINX_CONFIG"; then
            # Crea una configurazione temporanea
            cat > "${NGINX_CONFIG}.temp" << EOF
# Configurazione Nginx per M4Bot
# Modificata per modalitÃ  di manutenzione

server {
    listen 80;
    server_name _;

    # ModalitÃ  di manutenzione
    set \$maintenance_mode 1;

    # Consenti solo alcuni indirizzi IP durante la manutenzione
    # Aggiungi il tuo IP qui per accedere al sito durante la manutenzione
    # if (\$remote_addr = "123.123.123.123") {
    #     set \$maintenance_mode 0;
    # }

    # Se in modalitÃ  di manutenzione, serve la pagina statica
    if (\$maintenance_mode = 1) {
        return 503;
    }

EOF
            # Aggiungi il resto della configurazione originale
            cat "$NGINX_CONFIG" | grep -v "^server {" | grep -v "listen 80" | grep -v "server_name" >> "${NGINX_CONFIG}.temp"
            
            # Aggiungi la configurazione per la risposta 503
            cat >> "${NGINX_CONFIG}.temp" << EOF

    # Pagina di errore per manutenzione
    error_page 503 /emergency.html;
    location = /emergency.html {
        root /opt/m4bot/web/static;
        internal;
    }
}
EOF
            
            # Sostituisci la configurazione originale
            mv "${NGINX_CONFIG}.temp" "$NGINX_CONFIG" || print_error "Impossibile aggiornare la configurazione Nginx" 1
        else
            # La configurazione di manutenzione Ã¨ giÃ  presente, attivala
            sed -i 's/set \$maintenance_mode 0;/set \$maintenance_mode 1;/' "$NGINX_CONFIG"
        fi
        
        # Verifica la configurazione e ricarica Nginx
        nginx -t
        if [ $? -eq 0 ]; then
            systemctl reload nginx || print_error "Impossibile ricaricare Nginx" 1
            print_success "Nginx configurato per la modalitÃ  di manutenzione"
        else
            print_error "Configurazione di Nginx non valida, ripristino dal backup"
            cp "${NGINX_CONFIG}.backup" "$NGINX_CONFIG"
            systemctl reload nginx
            rm "$MAINTENANCE_FLAG"
            exit 1
        fi
    else
        print_error "File di configurazione Nginx non trovato: $NGINX_CONFIG" 1
    fi
    
    print_success "ModalitÃ  di manutenzione attivata"
    print_message "L'applicazione ora mostra la pagina di manutenzione agli utenti"
    print_message "Per disabilitare la modalitÃ  di manutenzione, esegui: $0 --disable"
}

# Funzione per disattivare la modalitÃ  di manutenzione
disable_maintenance() {
    print_message "Disattivazione della modalitÃ  di manutenzione..."
    
    # Controlla se la modalitÃ  di manutenzione Ã¨ attiva
    if [ ! -f "$MAINTENANCE_FLAG" ]; then
        print_warning "La modalitÃ  di manutenzione non Ã¨ attiva"
        return 0
    fi
    
    # Rimuovi il file flag
    rm "$MAINTENANCE_FLAG" || print_error "Impossibile rimuovere il file flag di manutenzione" 1
    
    # Modifica la configurazione Nginx per disattivare la modalitÃ  di manutenzione
    if [ -f "$NGINX_CONFIG" ]; then
        if grep -q "maintenance_mode" "$NGINX_CONFIG"; then
            # Disattiva la modalitÃ  di manutenzione cambiando la variabile
            sed -i 's/set \$maintenance_mode 1;/set \$maintenance_mode 0;/' "$NGINX_CONFIG"
        fi
        
        # Verifica la configurazione e ricarica Nginx
        nginx -t
        if [ $? -eq 0 ]; then
            systemctl reload nginx || print_error "Impossibile ricaricare Nginx" 1
            print_success "Nginx configurato per il funzionamento normale"
        else
            print_error "Configurazione di Nginx non valida"
            exit 1
        fi
    else
        print_error "File di configurazione Nginx non trovato: $NGINX_CONFIG" 1
    fi
    
    print_success "ModalitÃ  di manutenzione disattivata"
    print_message "L'applicazione Ã¨ ora accessibile normalmente"
}

# Funzione per mostrare lo stato
show_status() {
    print_message "Controllo dello stato della modalitÃ  di manutenzione..."
    
    if [ -f "$MAINTENANCE_FLAG" ]; then
        print_message "Stato: ATTIVA"
        print_message "La modalitÃ  di manutenzione Ã¨ attualmente attiva"
        print_message "Gli utenti stanno visualizzando la pagina di manutenzione"
    else
        print_message "Stato: DISATTIVA"
        print_message "La modalitÃ  di manutenzione non Ã¨ attiva"
        print_message "L'applicazione Ã¨ accessibile normalmente"
    fi
}

# Gestione dei parametri
case "$1" in
    --enable|-e)
        enable_maintenance
        ;;
    --disable|-d)
        disable_maintenance
        ;;
    --status|-s)
        show_status
        ;;
    --help|-h)
        show_help
        ;;
    *)
        show_help
        exit 1
        ;;
esac

exit 0 