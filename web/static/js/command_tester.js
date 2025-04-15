// Command Tester WebSocket
document.addEventListener('DOMContentLoaded', function() {
    // Elementi DOM
    const wsStatus = document.getElementById('wsStatus');
    const commandForm = document.getElementById('commandForm');
    const commandName = document.getElementById('commandName');
    const commandParams = document.getElementById('commandParams');
    const userRole = document.getElementById('userRole');
    const testBtn = document.getElementById('testBtn');
    const clearBtn = document.getElementById('clearBtn');
    const previewContainer = document.getElementById('previewContainer');
    const testHistory = document.getElementById('testHistory');
    
    // WebSocket
    let socket;
    let reconnectAttempts = 0;
    const maxReconnectAttempts = 5;
    
    // Connessione WebSocket
    function connectWebSocket() {
        wsStatus.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Connessione...';
        wsStatus.className = 'ws-status ws-connecting';
        
        // Determina l'URL del WebSocket
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = window.location.host;
        const wsUrl = `${protocol}//${host}/ws/command-test`;
        
        socket = new WebSocket(wsUrl);
        
        socket.onopen = function() {
            wsStatus.innerHTML = '<i class="fas fa-circle"></i> Connesso';
            wsStatus.className = 'ws-status ws-connected';
            reconnectAttempts = 0;
        };
        
        socket.onclose = function() {
            wsStatus.innerHTML = '<i class="fas fa-circle"></i> Disconnesso';
            wsStatus.className = 'ws-status ws-disconnected';
            
            // Tentativo di riconnessione
            if (reconnectAttempts < maxReconnectAttempts) {
                reconnectAttempts++;
                setTimeout(connectWebSocket, 3000 * reconnectAttempts);
            }
        };
        
        socket.onerror = function() {
            wsStatus.innerHTML = '<i class="fas fa-exclamation-circle"></i> Errore';
            wsStatus.className = 'ws-status ws-disconnected';
        };
        
        socket.onmessage = function(event) {
            const response = JSON.parse(event.data);
            handleCommandResponse(response);
        };
    }
    
    // Gestisce la risposta del comando
    function handleCommandResponse(response) {
        // Aggiorna la cronologia
        addToHistory(response);
        
        // Visualizza l'anteprima
        updatePreview(response);
    }
    
    // Aggiunge un comando alla cronologia
    function addToHistory(response) {
        // Rimuovi il messaggio "nessun test"
        if (testHistory.querySelector('.text-muted')) {
            testHistory.innerHTML = '';
        }
        
        // Crea elemento della cronologia
        const historyItem = document.createElement('div');
        historyItem.className = 'history-item';
        historyItem.dataset.command = response.command;
        historyItem.dataset.params = response.params || '';
        historyItem.dataset.role = response.role || 'user';
        
        // Stato dell'esecuzione (successo/errore)
        const statusClass = response.success ? 'success' : 'error';
        
        historyItem.innerHTML = `
            <div class="history-item-header ${statusClass}">
                <div class="command-text">!${response.command}${response.params ? ' ' + response.params : ''}</div>
                <div class="command-meta">
                    <span class="badge ${response.success ? 'bg-success' : 'bg-danger'}">
                        ${response.success ? 'Successo' : 'Errore'}
                    </span>
                    <button class="btn btn-sm btn-link rerun-btn">
                        <i class="fas fa-redo-alt"></i>
                    </button>
                </div>
            </div>
        `;
        
        // Aggiunge alla cronologia
        testHistory.insertBefore(historyItem, testHistory.firstChild);
        
        // Aggiunge l'evento per rieseguire il comando
        historyItem.querySelector('.rerun-btn').addEventListener('click', function() {
            commandName.value = response.command;
            commandParams.value = response.params || '';
            userRole.value = response.role || 'user';
            testCommand();
        });
        
        // Mantieni solo gli ultimi 10 elementi
        const historyItems = testHistory.querySelectorAll('.history-item');
        if (historyItems.length > 10) {
            testHistory.removeChild(historyItems[historyItems.length - 1]);
        }
    }
    
    // Aggiorna l'anteprima del comando
    function updatePreview(response) {
        let previewHTML = '';
        
        if (response.success) {
            // Generazione dell'anteprima di una risposta Discord
            previewHTML = `
                <div class="discord-preview">
                    <div class="message">
                        <div class="avatar">
                            <img src="${response.avatar || '/static/img/bot-avatar.png'}" alt="Bot Avatar">
                        </div>
                        <div class="message-content">
                            <div class="message-header">
                                <span class="bot-name">M4Bot</span>
                                <span class="timestamp">${new Date().toLocaleTimeString()}</span>
                            </div>
                            <div class="message-text">${response.content || ''}</div>
                            ${generateEmbeds(response.embeds)}
                        </div>
                    </div>
                </div>
            `;
        } else {
            // Messaggio di errore
            previewHTML = `
                <div class="error-message">
                    <i class="fas fa-exclamation-triangle"></i>
                    <h4>Errore nell'esecuzione del comando</h4>
                    <p>${response.error || 'Si è verificato un errore durante l\'elaborazione del comando.'}</p>
                </div>
            `;
        }
        
        previewContainer.innerHTML = previewHTML;
    }
    
    // Genera il HTML per gli embed Discord
    function generateEmbeds(embeds) {
        if (!embeds || !embeds.length) return '';
        
        let embedsHTML = '';
        
        embeds.forEach(embed => {
            const embedColor = embed.color ? `border-left: 4px solid ${embed.color};` : '';
            
            let fieldsHTML = '';
            if (embed.fields && embed.fields.length) {
                fieldsHTML = '<div class="embed-fields">';
                embed.fields.forEach(field => {
                    fieldsHTML += `
                        <div class="embed-field ${field.inline ? 'embed-field-inline' : ''}">
                            <div class="embed-field-name">${field.name}</div>
                            <div class="embed-field-value">${field.value}</div>
                        </div>
                    `;
                });
                fieldsHTML += '</div>';
            }
            
            embedsHTML += `
                <div class="embed" style="${embedColor}">
                    ${embed.author ? `
                        <div class="embed-author">
                            ${embed.author.icon_url ? `<img src="${embed.author.icon_url}" alt="Author Icon">` : ''}
                            <span>${embed.author.name}</span>
                        </div>
                    ` : ''}
                    
                    ${embed.title ? `<div class="embed-title">${embed.title}</div>` : ''}
                    ${embed.description ? `<div class="embed-description">${embed.description}</div>` : ''}
                    
                    ${fieldsHTML}
                    
                    ${embed.image ? `<div class="embed-image"><img src="${embed.image.url}" alt="Embed Image"></div>` : ''}
                    ${embed.thumbnail ? `<div class="embed-thumbnail"><img src="${embed.thumbnail.url}" alt="Embed Thumbnail"></div>` : ''}
                    
                    ${embed.footer ? `
                        <div class="embed-footer">
                            ${embed.footer.icon_url ? `<img src="${embed.footer.icon_url}" alt="Footer Icon">` : ''}
                            <span>${embed.footer.text}</span>
                        </div>
                    ` : ''}
                </div>
            `;
        });
        
        return embedsHTML;
    }
    
    // Testa il comando
    function testCommand() {
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            alert('WebSocket non connesso. Impossibile testare il comando.');
            return;
        }
        
        const command = commandName.value.trim();
        if (!command) {
            alert('Inserisci un nome di comando valido.');
            return;
        }
        
        // Invia il comando al server
        socket.send(JSON.stringify({
            command: command,
            params: commandParams.value.trim(),
            role: userRole.value
        }));
        
        // Visualizza un messaggio di caricamento
        previewContainer.innerHTML = `
            <div class="text-center p-4">
                <div class="spinner-border text-primary mb-3" role="status">
                    <span class="visually-hidden">Caricamento...</span>
                </div>
                <p>Elaborazione del comando in corso...</p>
            </div>
        `;
    }
    
    // Event Listeners
    commandForm.addEventListener('submit', function(e) {
        e.preventDefault();
        testCommand();
    });
    
    clearBtn.addEventListener('click', function() {
        commandName.value = '';
        commandParams.value = '';
        userRole.value = 'user';
    });
    
    // Connetti WebSocket all'avvio
    connectWebSocket();
}); 