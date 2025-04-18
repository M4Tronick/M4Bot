// File JavaScript per la gestione dei punti canale

$(document).ready(function() {
    // Attiva il tab corretto in base all'hash dell'URL
    let hash = window.location.hash;
    if (hash) {
        $(`#channelPointsTabs a[href="${hash}"]`).tab('show');
    }

    // Aggiorna l'hash quando cambia il tab
    $('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
        window.location.hash = e.target.hash;
    });

    // Carica i dati appropriati in base al tab attivo
    loadInitialData();
    
    // Carica l'attività recente
    loadActivity();

    // Quando si cambia tab, carica i dati appropriati
    $('a[data-toggle="tab"]').on('shown.bs.tab', function (e) {
        const targetId = $(e.target).attr('href');
        
        if (targetId === '#rewards') {
            loadRewards();
        } else if (targetId === '#users') {
            loadUsers();
        } else if (targetId === '#stats') {
            loadStatistics();
        }
    });

    // Carica i dati iniziali in base al tab attualmente attivo
    function loadInitialData() {
        const activeTab = $('#channelPointsTabs .nav-link.active').attr('href');
        
        if (activeTab === '#rewards') {
            loadRewards();
        } else if (activeTab === '#users') {
            loadUsers();
        } else if (activeTab === '#stats') {
            loadStatistics();
        }
    }

    // Carica i premi disponibili
    function loadRewards() {
        $.ajax({
            url: '/api/channel_points/rewards',
            type: 'GET',
            success: function(response) {
                renderRewards(response.rewards);
            },
            error: function(xhr) {
                showAlert('Errore durante il caricamento dei premi', 'danger');
            }
        });
    }

    // Carica gli utenti con punti
    function loadUsers() {
        $.ajax({
            url: '/api/channel_points/users',
            type: 'GET',
            success: function(response) {
                renderUsers(response.users);
            },
            error: function(xhr) {
                showAlert('Errore durante il caricamento degli utenti', 'danger');
            }
        });
    }

    // Carica le statistiche
    function loadStatistics() {
        $.ajax({
            url: '/api/channel_points/stats',
            type: 'GET',
            success: function(response) {
                renderStatistics(response);
            },
            error: function(xhr) {
                showAlert('Errore durante il caricamento delle statistiche', 'danger');
            }
        });
    }

    // Visualizza i premi
    function renderRewards(rewards) {
        const $rewardsList = $('#rewards-list');
        $rewardsList.empty();

        if (rewards.length === 0) {
            $rewardsList.html('<div class="text-center text-muted py-3">Nessun premio configurato</div>');
            return;
        }

        rewards.forEach(function(reward) {
            const rewardHtml = `
                <div class="reward-item" data-id="${reward.id}">
                    <div class="reward-header" style="background-color: ${reward.color}">
                        <h5>${reward.title}</h5>
                        <div class="reward-cost">
                            <i class="fas fa-coins"></i> ${reward.cost}
                        </div>
                    </div>
                    <div class="reward-body">
                        <p>${reward.description || 'Nessuna descrizione'}</p>
                        <div class="reward-status ${reward.enabled ? 'enabled' : 'disabled'}">
                            ${reward.enabled ? 'Abilitato' : 'Disabilitato'}
                        </div>
                        <div class="reward-actions">
                            <button class="btn btn-sm btn-primary edit-reward" data-id="${reward.id}">
                                <i class="fas fa-edit"></i> Modifica
                            </button>
                            <button class="btn btn-sm btn-danger delete-reward" data-id="${reward.id}">
                                <i class="fas fa-trash"></i> Elimina
                            </button>
                        </div>
                    </div>
                </div>
            `;
            $rewardsList.append(rewardHtml);
        });

        // Aggiungi gestore per i pulsanti di modifica
        $('.edit-reward').on('click', function() {
            const rewardId = $(this).data('id');
            editReward(rewardId);
        });

        // Aggiungi gestore per i pulsanti di eliminazione
        $('.delete-reward').on('click', function() {
            const rewardId = $(this).data('id');
            deleteReward(rewardId);
        });
    }

    // Visualizza gli utenti
    function renderUsers(users) {
        const $usersTable = $('#users-table tbody');
        $usersTable.empty();

        if (users.length === 0) {
            $usersTable.html('<tr><td colspan="4" class="text-center">Nessun utente trovato</td></tr>');
            return;
        }

        users.forEach(function(user) {
            const userHtml = `
                <tr data-user-id="${user.id}">
                    <td>${user.username}</td>
                    <td class="user-points">${user.points}</td>
                    <td>${user.last_update}</td>
                    <td>
                        <button 
                            class="btn btn-sm btn-primary modify-points-btn" 
                            data-user-id="${user.id}" 
                            data-username="${user.username}" 
                            data-points="${user.points}">
                            <i class="fas fa-coins mr-1"></i> Modifica
                        </button>
                    </td>
                </tr>
            `;
            $usersTable.append(userHtml);
        });

        // Aggiungi gestore per i pulsanti di modifica punti
        $('.modify-points-btn').on('click', function() {
            const userId = $(this).data('user-id');
            const username = $(this).data('username');
            const points = $(this).data('points');
            
            $('#user-points-id').val(userId);
            $('#user-points-username').text(username);
            $('#user-points-current').text(points);
            $('#user-points-amount').val('');
            $('#action-add').prop('checked', true);
            
            $('#modify-points-modal').modal('show');
        });
    }

    // Visualizza le statistiche
    function renderStatistics(stats) {
        $('.display-4.text-primary').text(stats.total_points);
        $('.display-4.text-success').text(stats.total_redemptions);
        $('.display-4.text-danger').text(stats.redeemed_points);
    }

    // Carica l'attività recente
    function loadActivity(page = 1, limit = 10) {
        $.ajax({
            url: `/api/channel_points/activity?page=${page}&limit=${limit}`,
            type: 'GET',
            success: function(response) {
                renderActivity(response.activities, response.total, page, limit);
            },
            error: function(xhr) {
                showAlert('Errore durante il caricamento dell\'attività', 'danger');
            }
        });
    }

    // Visualizza l'attività recente
    function renderActivity(activities, total, currentPage, limit) {
        const $activityList = $('#activity-list');
        $activityList.empty();

        if (activities.length === 0) {
            $activityList.html('<tr><td colspan="4" class="text-center">Nessuna attività recente</td></tr>');
            return;
        }

        activities.forEach(function(activity) {
            let actionText = '';
            let valueText = '';
            
            switch(activity.action_type) {
                case 'earn':
                    actionText = 'Guadagno';
                    valueText = `+${activity.points} punti`;
                    break;
                case 'spend':
                    actionText = 'Spesa';
                    valueText = `-${activity.points} punti`;
                    break;
                case 'redeem':
                    actionText = 'Riscatto';
                    valueText = activity.reward_title || `Premio (${activity.points} punti)`;
                    break;
                case 'refund':
                    actionText = 'Rimborso';
                    valueText = `+${activity.points} punti`;
                    break;
                case 'admin':
                    actionText = 'Amministratore';
                    valueText = activity.notes || `${activity.points > 0 ? '+' : ''}${activity.points} punti`;
                    break;
                default:
                    actionText = activity.action_type;
                    valueText = `${activity.points} punti`;
            }
            
            const activityDate = new Date(activity.timestamp);
            const formattedDate = activityDate.toLocaleString('it-IT');
            
            const activityHtml = `
                <tr>
                    <td>${activity.username}</td>
                    <td>${actionText}</td>
                    <td>${valueText}</td>
                    <td>${formattedDate}</td>
                </tr>
            `;
            $activityList.append(activityHtml);
        });

        // Crea la paginazione
        renderPagination(total, currentPage, limit, '#activity-pagination', function(page) {
            loadActivity(page, limit);
        });
    }

    // Funzione per creare la paginazione
    function renderPagination(total, currentPage, limit, paginationSelector, onPageChange) {
        const $pagination = $(paginationSelector);
        $pagination.empty();
        
        const totalPages = Math.ceil(total / limit);
        
        if (totalPages <= 1) {
            return;
        }
        
        let paginationHtml = '<nav><ul class="pagination">';
        
        // Pulsante Precedente
        paginationHtml += `
            <li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${currentPage - 1}" aria-label="Precedente">
                    <span aria-hidden="true">&laquo;</span>
                </a>
            </li>
        `;
        
        // Numeri di pagina
        const startPage = Math.max(1, currentPage - 2);
        const endPage = Math.min(totalPages, startPage + 4);
        
        for (let i = startPage; i <= endPage; i++) {
            paginationHtml += `
                <li class="page-item ${i === currentPage ? 'active' : ''}">
                    <a class="page-link" href="#" data-page="${i}">${i}</a>
                </li>
            `;
        }
        
        // Pulsante Successivo
        paginationHtml += `
            <li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
                <a class="page-link" href="#" data-page="${currentPage + 1}" aria-label="Successivo">
                    <span aria-hidden="true">&raquo;</span>
                </a>
            </li>
        `;
        
        paginationHtml += '</ul></nav>';
        
        $pagination.html(paginationHtml);
        
        // Aggiungi evento click ai pulsanti di paginazione
        $(`${paginationSelector} .page-link`).on('click', function(e) {
            e.preventDefault();
            const page = parseInt($(this).data('page'));
            
            if (page >= 1 && page <= totalPages) {
                onPageChange(page);
            }
        });
    }

    // Funzione per modificare un premio
    function editReward(rewardId) {
        $.ajax({
            url: `/api/channel_points/rewards/${rewardId}`,
            type: 'GET',
            success: function(response) {
                const reward = response.reward;
                
                $('#reward-modal-title').text('Modifica Premio');
                $('#reward-id').val(reward.id);
                $('#reward-title').val(reward.title);
                $('#reward-description').val(reward.description);
                $('#reward-cost').val(reward.cost);
                $('#reward-cooldown').val(reward.cooldown);
                $('#reward-color').val(reward.color);
                $('#reward-enabled').prop('checked', reward.enabled);
                
                $('#reward-modal').modal('show');
            },
            error: function(xhr) {
                showAlert('Errore durante il caricamento del premio', 'danger');
            }
        });
    }

    // Funzione per eliminare un premio
    function deleteReward(rewardId) {
        if (confirm('Sei sicuro di voler eliminare questo premio?')) {
            $.ajax({
                url: `/api/channel_points/rewards/${rewardId}`,
                type: 'DELETE',
                success: function(response) {
                    showAlert('Premio eliminato con successo', 'success');
                    loadRewards();
                },
                error: function(xhr) {
                    showAlert('Errore durante l\'eliminazione del premio', 'danger');
                }
            });
        }
    }

    // Funzione per mostrare un avviso
    function showAlert(message, type) {
        const alertHtml = `
            <div class="alert alert-${type} alert-dismissible fade show" role="alert">
                ${message}
                <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                    <span aria-hidden="true">&times;</span>
                </button>
            </div>
        `;
        
        $('#alert-container').append(alertHtml);
        
        // Rimuovi automaticamente l'avviso dopo 5 secondi
        setTimeout(function() {
            $('.alert').alert('close');
        }, 5000);
    }

    // Gestisci il clic sul pulsante "Aggiungi Premio"
    $('#add-reward-btn').on('click', function() {
        $('#reward-modal-title').text('Aggiungi Nuovo Premio');
        $('#reward-form').trigger('reset');
        $('#reward-id').val('');
        $('#reward-color').val('#9146FF');
        $('#reward-enabled').prop('checked', true);
        
        $('#reward-modal').modal('show');
    });

    // Gestisci l'invio del form per i premi
    $('#reward-form').on('submit', function(e) {
        e.preventDefault();
        
        const rewardId = $('#reward-id').val();
        const formData = {
            title: $('#reward-title').val(),
            description: $('#reward-description').val(),
            cost: parseInt($('#reward-cost').val()),
            cooldown: parseInt($('#reward-cooldown').val()),
            color: $('#reward-color').val(),
            enabled: $('#reward-enabled').is(':checked')
        };
        
        // Se l'ID è presente, aggiorna un premio esistente, altrimenti ne crea uno nuovo
        const method = rewardId ? 'PUT' : 'POST';
        const url = rewardId 
            ? `/api/channel_points/rewards/${rewardId}` 
            : '/api/channel_points/rewards';
        
        $.ajax({
            url: url,
            type: method,
            contentType: 'application/json',
            data: JSON.stringify(formData),
            success: function(response) {
                $('#reward-modal').modal('hide');
                showAlert(rewardId ? 'Premio aggiornato con successo' : 'Premio creato con successo', 'success');
                loadRewards();
            },
            error: function(xhr) {
                showAlert('Errore durante il salvataggio del premio', 'danger');
            }
        });
    });

    // Gestisci l'invio del form per la modifica dei punti utente
    $('#modify-points-form').on('submit', function(e) {
        e.preventDefault();
        
        const userId = $('#user-points-id').val();
        const amount = parseInt($('#user-points-amount').val());
        const action = $('input[name="points-action"]:checked').val();
        
        $.ajax({
            url: `/api/channel_points/users/${userId}/points`,
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ action, amount }),
            success: function(response) {
                $('#modify-points-modal').modal('hide');
                showAlert('Punti aggiornati con successo', 'success');
                
                // Aggiorna i punti visualizzati in tabella senza ricaricare tutti gli utenti
                $(`tr[data-user-id="${userId}"] .user-points`).text(response.new_points);
                
                // Aggiorna anche l'attributo data-points sul pulsante di modifica
                $(`.modify-points-btn[data-user-id="${userId}"]`).data('points', response.new_points);
            },
            error: function(xhr) {
                showAlert('Errore durante l\'aggiornamento dei punti', 'danger');
            }
        });
    });

    // Gestisci l'invio del form per le impostazioni
    $('#channel-points-settings-form').on('submit', function(e) {
        e.preventDefault();
        
        const formData = {
            points_name: $('#points-name').val(),
            points_icon: $('#points-icon').val(),
            points_color: $('#points-color').val(),
            viewer_rate: parseInt($('#viewer-rate').val()),
            subscriber_multiplier: parseFloat($('#subscriber-multiplier').val()),
            follower_bonus_enabled: $('#follower-bonus-enabled').is(':checked'),
            follower_bonus: parseInt($('#follower-bonus').val())
        };
        
        $.ajax({
            url: '/api/channel_points/settings',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(formData),
            success: function(response) {
                showAlert('Impostazioni salvate con successo', 'success');
            },
            error: function(xhr) {
                showAlert('Errore durante il salvataggio delle impostazioni', 'danger');
            }
        });
    });

    // Funzione di ricerca utenti
    $('#user-search').on('input', function() {
        const searchTerm = $(this).val().toLowerCase();
        
        $('#users-table tbody tr').each(function() {
            const username = $(this).find('td:first').text().toLowerCase();
            
            if (username.includes(searchTerm)) {
                $(this).show();
                
                // Evidenzia il testo corrispondente
                if (searchTerm) {
                    const usernameCell = $(this).find('td:first');
                    const highlightedText = usernameCell.text().replace(
                        new RegExp(searchTerm, 'gi'),
                        match => `<span class="highlight">${match}</span>`
                    );
                    usernameCell.html(highlightedText);
                }
            } else {
                $(this).hide();
            }
        });
    });
}); 