/**
 * M4Bot - Global Search
 * Implementa la funzionalità di ricerca globale in tutta l'applicazione
 */

(function() {
    'use strict';
    
    // Elementi principali
    const searchInput = document.getElementById('global-search-input');
    const searchForm = document.getElementById('global-search-form');
    const searchResultsContent = document.getElementById('search-results-content');
    const searchDropdown = document.getElementById('search-results-dropdown');
    
    // Sezioni dell'applicazione che possono essere cercate
    const searchableCategories = [
        { id: 'dashboard', name: 'Dashboard', icon: 'tachometer-alt' },
        { id: 'commands', name: 'Comandi', icon: 'terminal' },
        { id: 'automations', name: 'Automazioni', icon: 'robot' },
        { id: 'settings', name: 'Impostazioni', icon: 'cog' },
        { id: 'profiles', name: 'Profili', icon: 'user' },
        { id: 'statistics', name: 'Statistiche', icon: 'chart-bar' },
        { id: 'integrations', name: 'Integrazioni', icon: 'plug' },
        { id: 'docs', name: 'Documentazione', icon: 'book' }
    ];
    
    // Indice di ricerca in memoria
    const searchIndex = {
        recentSearches: JSON.parse(localStorage.getItem('recentSearches') || '[]'),
        cachedResults: {}
    };
    
    // Risultati di esempio
    const exampleResults = {
        'dashboard': [
            { title: 'Dashboard principale', url: '/dashboard', description: 'Panoramica del tuo canale' },
            { title: 'Sistema di Automazioni', url: '/automations', description: 'Configura azioni automatiche' }
        ],
        'commands': [
            { title: 'Gestione Comandi', url: '/manage_commands', description: 'Configura i comandi del bot' },
            { title: 'Editor Comandi Visuale', url: '/visual_command_editor', description: 'Editor visuale per comandi complessi' },
            { title: 'Command Tester', url: '/command_tester', description: 'Testa i tuoi comandi prima di pubblicarli' }
        ],
        'settings': [
            { title: 'Impostazioni Profilo', url: '/user_profile', description: 'Gestisci il tuo account' },
            { title: 'Impostazioni Canale', url: '/channel_settings', description: 'Configura le impostazioni del canale' },
            { title: 'Centro Privacy', url: '/privacy_center', description: 'Gestisci le tue preferenze di privacy' }
        ],
        'statistics': [
            { title: 'Statistiche Canale', url: '/channel_stats', description: 'Visualizza statistiche base del canale' },
            { title: 'Analytics Avanzate', url: '/advanced_analytics', description: 'Analisi dettagliate e approfondite' }
        ],
        'integrations': [
            { title: 'Integrazione Discord', url: '/discord_integration', description: 'Configura bridge con Discord' },
            { title: 'Integrazione OBS', url: '/obs_integration', description: 'Gestisci OBS con il bot' },
            { title: 'Webhook Management', url: '/webhook_management', description: 'Gestisci webhook e callback' }
        ]
    };
    
    // Inizializza la ricerca globale
    function init() {
        if (!searchInput || !searchForm || !searchResultsContent) return;
        
        // Listener per input di ricerca
        searchInput.addEventListener('input', handleSearchInput);
        
        // Previeni submit del form
        searchForm.addEventListener('submit', function(e) {
            e.preventDefault();
            performSearch(searchInput.value);
        });
        
        // Chiudi dropdown quando si clicca fuori
        document.addEventListener('click', function(e) {
            if (!searchForm.contains(e.target)) {
                hideSearchResults();
            }
        });
        
        // Gestione focus/blur
        searchInput.addEventListener('focus', function() {
            if (this.value.length > 0) {
                showSearchResults();
            }
        });
        
        // Inizializza Bootstrap dropdown manualmente per maggiore controllo
        const dropdownInstance = new bootstrap.Dropdown(searchInput, {
            autoClose: false
        });
        
        console.log('Global search initialized');
    }
    
    // Gestisce l'input di ricerca
    function handleSearchInput(e) {
        const query = e.target.value.trim();
        
        if (query.length === 0) {
            hideSearchResults();
            return;
        }
        
        if (query.length >= 2) {
            performSearch(query);
        }
    }
    
    // Esegue la ricerca
    function performSearch(query) {
        // Normalizza query
        query = query.toLowerCase().trim();
        
        // Se è una query già cercata di recente, usa la cache
        if (searchIndex.cachedResults[query]) {
            displayResults(searchIndex.cachedResults[query], query);
            return;
        }
        
        // Altrimenti, esegui ricerca
        searchAPI(query)
            .then(results => {
                // Salva nella cache
                searchIndex.cachedResults[query] = results;
                
                // Mostra risultati
                displayResults(results, query);
                
                // Aggiungi a ricerche recenti (solo se ci sono risultati)
                if (results.totalCount > 0) {
                    addToRecentSearches(query);
                }
            })
            .catch(error => {
                console.error('Errore nella ricerca:', error);
                displayErrorMessage();
            });
    }
    
    // Simula API di ricerca (da sostituire con chiamata API reale)
    function searchAPI(query) {
        return new Promise((resolve) => {
            // Simula latenza di rete
            setTimeout(() => {
                // Filtra risultati di esempio in base alla query
                const results = {
                    categories: {},
                    totalCount: 0
                };
                
                // Per ogni categoria
                Object.keys(exampleResults).forEach(categoryId => {
                    // Cerca match nei risultati di esempio
                    const matchingResults = exampleResults[categoryId].filter(item => 
                        item.title.toLowerCase().includes(query) || 
                        item.description.toLowerCase().includes(query)
                    );
                    
                    if (matchingResults.length > 0) {
                        results.categories[categoryId] = matchingResults;
                        results.totalCount += matchingResults.length;
                    }
                });
                
                resolve(results);
            }, 200);
        });
    }
    
    // Mostra risultati della ricerca
    function displayResults(results, query) {
        if (!searchResultsContent) return;
        
        // Se non ci sono risultati
        if (results.totalCount === 0) {
            searchResultsContent.innerHTML = `
                <div class="text-center py-3">
                    <i class="fas fa-search fa-2x text-muted mb-2"></i>
                    <p class="mb-0">Nessun risultato trovato per "${query}"</p>
                </div>
            `;
            showSearchResults();
            return;
        }
        
        // Costruisci HTML dei risultati
        let html = '';
        
        // Per ogni categoria con risultati
        Object.keys(results.categories).forEach(categoryId => {
            const category = searchableCategories.find(c => c.id === categoryId) || 
                             { name: categoryId, icon: 'circle' };
            
            html += `
                <div class="search-category mb-3">
                    <h6 class="search-category-title">
                        <i class="fas fa-${category.icon} me-2"></i>${category.name}
                    </h6>
                    <div class="list-group list-group-flush">
            `;
            
            // Aggiungi elementi della categoria
            results.categories[categoryId].forEach(item => {
                // Evidenzia la query nei titoli e descrizioni
                const highlightedTitle = highlightText(item.title, query);
                const highlightedDesc = highlightText(item.description, query);
                
                html += `
                    <a href="${item.url}" class="list-group-item list-group-item-action px-0 py-2 border-0">
                        <div class="d-flex justify-content-between align-items-center">
                            <h6 class="mb-1">${highlightedTitle}</h6>
                        </div>
                        <p class="mb-0 small text-secondary">${highlightedDesc}</p>
                    </a>
                `;
            });
            
            html += `
                    </div>
                </div>
            `;
        });
        
        // Se ci sono ricerche recenti, mostrali
        if (searchIndex.recentSearches.length > 0 && query.length < 3) {
            html += `
                <div class="search-category mt-3 pt-3 border-top">
                    <h6 class="search-category-title">
                        <i class="fas fa-history me-2"></i>Ricerche recenti
                    </h6>
                    <div class="d-flex flex-wrap gap-1">
            `;
            
            searchIndex.recentSearches.slice(0, 5).forEach(term => {
                html += `
                    <button class="btn btn-sm btn-light rounded-pill recent-search" data-term="${term}">
                        ${term}
                    </button>
                `;
            });
            
            html += `
                    </div>
                </div>
            `;
        }
        
        // Aggiorna contenuto e mostra dropdown
        searchResultsContent.innerHTML = html;
        
        // Aggiungi listener per ricerche recenti
        const recentButtons = searchResultsContent.querySelectorAll('.recent-search');
        recentButtons.forEach(button => {
            button.addEventListener('click', function() {
                const term = this.dataset.term;
                searchInput.value = term;
                performSearch(term);
            });
        });
        
        showSearchResults();
    }
    
    // Mostra messaggio di errore
    function displayErrorMessage() {
        if (!searchResultsContent) return;
        
        searchResultsContent.innerHTML = `
            <div class="text-center py-3">
                <i class="fas fa-exclamation-triangle fa-2x text-warning mb-2"></i>
                <p class="mb-0">Si è verificato un errore durante la ricerca</p>
            </div>
        `;
        showSearchResults();
    }
    
    // Evidenzia testo della query nei risultati
    function highlightText(text, query) {
        if (!query) return text;
        
        // Escape caratteri speciali in regex
        const safeQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        
        // Replace con highlight
        return text.replace(new RegExp(safeQuery, 'gi'), match => `<mark>${match}</mark>`);
    }
    
    // Aggiungi a ricerche recenti
    function addToRecentSearches(query) {
        // Rimuovi se già presente
        const index = searchIndex.recentSearches.indexOf(query);
        if (index !== -1) {
            searchIndex.recentSearches.splice(index, 1);
        }
        
        // Aggiungi all'inizio
        searchIndex.recentSearches.unshift(query);
        
        // Limita a 10 ricerche
        if (searchIndex.recentSearches.length > 10) {
            searchIndex.recentSearches.pop();
        }
        
        // Salva in localStorage
        localStorage.setItem('recentSearches', JSON.stringify(searchIndex.recentSearches));
    }
    
    // Mostra dropdown risultati
    function showSearchResults() {
        if (searchDropdown) {
            const dropdownInstance = bootstrap.Dropdown.getInstance(searchInput);
            if (dropdownInstance) {
                dropdownInstance.show();
            } else {
                new bootstrap.Dropdown(searchInput).show();
            }
        }
    }
    
    // Nascondi dropdown risultati
    function hideSearchResults() {
        if (searchDropdown) {
            const dropdownInstance = bootstrap.Dropdown.getInstance(searchInput);
            if (dropdownInstance) {
                dropdownInstance.hide();
            }
        }
    }
    
    // Inizializza quando il DOM è caricato
    document.addEventListener('DOMContentLoaded', init);
})(); 