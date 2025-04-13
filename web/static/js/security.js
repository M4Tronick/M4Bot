/**
 * M4Bot - Sistema di Sicurezza e Recupero Password
 * Questo modulo gestisce le funzionalità di sicurezza dell'account
 */

// Impostazioni di sicurezza
const LOCK_THRESHOLD = 5; // Tentativi falliti prima del blocco
const LOCK_DURATION = 15; // Minuti di blocco

// Stato di sicurezza dell'utente
let securityState = {
    failedAttempts: 0,
    lockedUntil: null,
    lastActivity: Date.now(),
    currentToken: null
};

/**
 * Inizializza il sistema di sicurezza
 */
function initSecuritySystem() {
    setupSecurityListeners();
    setupInactivityMonitor();
    enhanceFormSecurity();
}

/**
 * Configura i listener per eventi di sicurezza
 */
function setupSecurityListeners() {
    // Intercetta i form di login/registrazione
    const loginForm = document.getElementById('loginForm');
    const registerForm = document.getElementById('registerForm');
    const resetForm = document.getElementById('passwordResetForm');
    
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            if (isAccountLocked()) {
                e.preventDefault();
                showLockMessage();
                return false;
            }
            
            // Se il form viene inviato, aggiungiamo un token di sicurezza
            const securityToken = document.createElement('input');
            securityToken.type = 'hidden';
            securityToken.name = 'security_token';
            securityToken.value = generateSecurityToken();
            this.appendChild(securityToken);
        });
    }
    
    if (registerForm) {
        registerForm.addEventListener('submit', function(e) {
            const password = document.getElementById('password');
            const passwordConfirm = document.getElementById('passwordConfirm');
            
            // Verifica la sicurezza della password
            if (password && !isPasswordStrong(password.value)) {
                e.preventDefault();
                showToast('Sicurezza', 'La password non è abbastanza sicura. Usa almeno 8 caratteri con numeri, lettere e simboli.', 'warning');
                return false;
            }
            
            // Verifica che le password coincidano
            if (password && passwordConfirm && password.value !== passwordConfirm.value) {
                e.preventDefault();
                showToast('Errore', 'Le password non coincidono', 'danger');
                return false;
            }
        });
    }
    
    if (resetForm) {
        resetForm.addEventListener('submit', function(e) {
            // Validazione del form di reset
            const emailField = document.getElementById('resetEmail');
            if (emailField && !validateEmail(emailField.value)) {
                e.preventDefault();
                showToast('Errore', 'Inserisci un indirizzo email valido', 'danger');
                return false;
            }
        });
    }
    
    // Ascolta le risposte del server
    document.addEventListener('m4bot:loginResponse', function(e) {
        const response = e.detail;
        
        if (response.success) {
            // Reset dei tentativi falliti
            securityState.failedAttempts = 0;
            securityState.lockedUntil = null;
            localStorage.setItem('securityState', JSON.stringify(securityState));
        } else {
            // Incrementa i tentativi falliti
            handleFailedLogin();
        }
    });
}

/**
 * Verifica se la password è sufficientemente forte
 */
function isPasswordStrong(password) {
    // Almeno 8 caratteri, con numeri, lettere maiuscole, minuscole e simboli
    const strongRegex = new RegExp("^(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[!@#$%^&*])(?=.{8,})");
    return strongRegex.test(password);
}

/**
 * Valida un indirizzo email
 */
function validateEmail(email) {
    const re = /^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
    return re.test(String(email).toLowerCase());
}

/**
 * Gestisce un tentativo di login fallito
 */
function handleFailedLogin() {
    // Carica lo stato corrente
    let state = JSON.parse(localStorage.getItem('securityState')) || securityState;
    
    // Incrementa i tentativi falliti
    state.failedAttempts += 1;
    
    // Verifica se l'account deve essere bloccato
    if (state.failedAttempts >= LOCK_THRESHOLD) {
        const now = Date.now();
        state.lockedUntil = now + (LOCK_DURATION * 60 * 1000);
        
        showToast('Sicurezza', `Account temporaneamente bloccato. Riprova tra ${LOCK_DURATION} minuti.`, 'danger');
    }
    
    // Salva lo stato
    securityState = state;
    localStorage.setItem('securityState', JSON.stringify(state));
}

/**
 * Verifica se l'account è attualmente bloccato
 */
function isAccountLocked() {
    // Carica lo stato corrente
    let state = JSON.parse(localStorage.getItem('securityState')) || securityState;
    
    // Se esiste un timestamp di blocco, verifica se è ancora valido
    if (state.lockedUntil) {
        const now = Date.now();
        if (now < state.lockedUntil) {
            return true;
        } else {
            // Reset automatico dopo il periodo di blocco
            state.failedAttempts = 0;
            state.lockedUntil = null;
            localStorage.setItem('securityState', JSON.stringify(state));
            return false;
        }
    }
    
    return false;
}

/**
 * Mostra un messaggio che l'account è bloccato
 */
function showLockMessage() {
    let state = JSON.parse(localStorage.getItem('securityState')) || securityState;
    
    if (state.lockedUntil) {
        const now = Date.now();
        const remainingMinutes = Math.ceil((state.lockedUntil - now) / (60 * 1000));
        
        showToast('Sicurezza', `Account temporaneamente bloccato. Riprova tra ${remainingMinutes} minuti.`, 'danger');
    }
}

/**
 * Genera un token di sicurezza
 */
function generateSecurityToken() {
    const token = Math.random().toString(36).substring(2, 15) + 
                Math.random().toString(36).substring(2, 15);
    
    securityState.currentToken = token;
    return token;
}

/**
 * Configura il monitoraggio dell'inattività
 */
function setupInactivityMonitor() {
    // Eventi che indicano attività dell'utente
    const activityEvents = [
        'mousedown', 'mousemove', 'keypress', 
        'scroll', 'touchstart', 'click'
    ];
    
    // Resetta il timer di inattività quando l'utente fa qualcosa
    activityEvents.forEach(event => {
        document.addEventListener(event, function() {
            securityState.lastActivity = Date.now();
        }, true);
    });
    
    // Verifica periodicamente l'inattività
    setInterval(checkInactivity, 60000); // Ogni minuto
}

/**
 * Verifica se l'utente è inattivo
 */
function checkInactivity() {
    const now = Date.now();
    const inactiveTime = now - securityState.lastActivity;
    
    // Se l'utente è inattivo per più di 30 minuti, offrire il logout
    if (inactiveTime > 30 * 60 * 1000) {
        // Controlla se l'utente è loggato
        const userMenu = document.querySelector('.user-menu');
        if (userMenu) {
            showInactivityModal();
        }
    }
    
    // Se inattivo per più di 60 minuti, logout automatico
    if (inactiveTime > 60 * 60 * 1000) {
        // Controlla se l'utente è loggato
        const userMenu = document.querySelector('.user-menu');
        if (userMenu) {
            window.location.href = '/logout';
        }
    }
}

/**
 * Mostra un modal per avvisare l'utente dell'inattività
 */
function showInactivityModal() {
    // Controlla se il modal è già presente
    let modal = document.getElementById('inactivityModal');
    
    if (!modal) {
        // Crea il modal se non esiste
        modal = document.createElement('div');
        modal.id = 'inactivityModal';
        modal.className = 'modal fade';
        modal.tabIndex = '-1';
        modal.innerHTML = `
            <div class="modal-dialog">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">Sei ancora qui?</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body">
                        <p>Sembra che tu sia inattivo da un po'. Per motivi di sicurezza, verrai disconnesso automaticamente se continui a rimanere inattivo.</p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Resta Connesso</button>
                        <a href="/logout" class="btn btn-primary">Disconnetti</a>
                    </div>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
    }
    
    // Mostra il modal
    const bsModal = new bootstrap.Modal(modal);
    bsModal.show();
    
    // Resetta il timer quando l'utente interagisce con il modal
    modal.addEventListener('click', function() {
        securityState.lastActivity = Date.now();
    });
}

/**
 * Migliora la sicurezza dei form
 */
function enhanceFormSecurity() {
    // Aggiunge validazione di sicurezza a tutti i form
    document.querySelectorAll('form').forEach(form => {
        // Evita di processare form già migliorati
        if (form.dataset.securityEnhanced) return;
        
        // Aggiungi validazione dei campi
        form.querySelectorAll('input, select, textarea').forEach(field => {
            if (field.type === 'password') {
                // Aggiungi rilevamento della forza della password
                field.addEventListener('input', function() {
                    const strength = getPasswordStrength(this.value);
                    updatePasswordStrengthIndicator(field, strength);
                });
            }
            
            if (field.type === 'email') {
                // Validazione email
                field.addEventListener('blur', function() {
                    if (this.value && !validateEmail(this.value)) {
                        this.classList.add('is-invalid');
                    } else {
                        this.classList.remove('is-invalid');
                    }
                });
            }
        });
        
        // Segna questo form come migliorato
        form.dataset.securityEnhanced = true;
    });
}

/**
 * Calcola la forza di una password
 */
function getPasswordStrength(password) {
    // Implementa un algoritmo per calcolare la forza della password
    let score = 0;
    
    // Criteri di base
    if (password.length >= 8) score += 1;
    if (password.length >= 12) score += 1;
    if (/[A-Z]/.test(password)) score += 1;
    if (/[a-z]/.test(password)) score += 1;
    if (/[0-9]/.test(password)) score += 1;
    if (/[^A-Za-z0-9]/.test(password)) score += 1;
    
    // Variabilità dei caratteri
    const uniqueChars = new Set(password.split('')).size;
    if (uniqueChars > 5) score += 1;
    if (uniqueChars > 10) score += 1;
    
    return Math.min(5, score); // Massimo 5 punti
}

/**
 * Aggiorna l'indicatore della forza della password
 */
function updatePasswordStrengthIndicator(field, strength) {
    // Cerca un indicatore esistente o creane uno nuovo
    let indicator = field.parentNode.querySelector('.password-strength');
    
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.className = 'password-strength mt-1';
        
        // Crea la barra di forza
        const strengthBar = document.createElement('div');
        strengthBar.className = 'strength-bar';
        
        // Crea i segmenti della barra
        for (let i = 0; i < 5; i++) {
            const segment = document.createElement('div');
            segment.className = 'segment';
            strengthBar.appendChild(segment);
        }
        
        // Crea l'etichetta
        const label = document.createElement('div');
        label.className = 'strength-label mt-1 small';
        
        indicator.appendChild(strengthBar);
        indicator.appendChild(label);
        
        field.parentNode.appendChild(indicator);
    }
    
    // Aggiorna l'indicatore in base alla forza
    const segments = indicator.querySelectorAll('.segment');
    const label = indicator.querySelector('.strength-label');
    
    // Resetta tutti i segmenti
    segments.forEach(segment => {
        segment.className = 'segment';
    });
    
    // Etichette e colori in base alla forza
    let strengthText = '';
    let strengthClass = '';
    
    switch(strength) {
        case 0:
            strengthText = 'Molto debole';
            strengthClass = 'very-weak';
            break;
        case 1:
            strengthText = 'Debole';
            strengthClass = 'weak';
            break;
        case 2:
            strengthText = 'Media';
            strengthClass = 'medium';
            break;
        case 3:
            strengthText = 'Buona';
            strengthClass = 'good';
            break;
        case 4:
            strengthText = 'Forte';
            strengthClass = 'strong';
            break;
        case 5:
            strengthText = 'Molto forte';
            strengthClass = 'very-strong';
            break;
    }
    
    // Aggiorna i segmenti attivi
    for (let i = 0; i < strength; i++) {
        segments[i].classList.add('active', strengthClass);
    }
    
    label.textContent = strengthText;
    label.className = `strength-label mt-1 small ${strengthClass}`;
}

/**
 * Procedura di recupero password
 */
function initiatePasswordReset(email) {
    // Validazione email
    if (!validateEmail(email)) {
        showToast('Errore', 'Inserisci un indirizzo email valido', 'danger');
        return;
    }
    
    // Mostra loader
    showLoader();
    
    // Invia richiesta di reset password
    fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email })
    })
    .then(response => response.json())
    .then(data => {
        hideLoader();
        
        if (data.success) {
            showToast('Recupero Password', 'Ti abbiamo inviato un\'email con le istruzioni per reimpostare la password', 'success');
            
            // Mostra la sezione di conferma
            const resetForm = document.getElementById('passwordResetForm');
            const confirmSection = document.getElementById('resetConfirmation');
            
            if (resetForm && confirmSection) {
                resetForm.style.display = 'none';
                confirmSection.style.display = 'block';
            }
        } else {
            showToast('Errore', data.message || 'Impossibile inviare l\'email di reset', 'danger');
        }
    })
    .catch(err => {
        hideLoader();
        console.error('Errore nel reset della password:', err);
        showToast('Errore', 'Si è verificato un errore. Riprova più tardi.', 'danger');
    });
}

/**
 * Verifica la validità del token di reset
 */
function verifyResetToken(token) {
    // Mostra loader
    showLoader();
    
    // Verifica il token
    fetch(`/api/auth/verify-reset-token/${token}`, {
        method: 'GET'
    })
    .then(response => response.json())
    .then(data => {
        hideLoader();
        
        if (data.valid) {
            // Token valido, mostra il form per impostare una nuova password
            const tokenInput = document.getElementById('resetToken');
            if (tokenInput) {
                tokenInput.value = token;
            }
            
            const verificationSection = document.getElementById('tokenVerification');
            const newPasswordSection = document.getElementById('newPasswordSection');
            
            if (verificationSection && newPasswordSection) {
                verificationSection.style.display = 'none';
                newPasswordSection.style.display = 'block';
            }
        } else {
            showToast('Errore', 'Il token non è valido o è scaduto', 'danger');
        }
    })
    .catch(err => {
        hideLoader();
        console.error('Errore nella verifica del token:', err);
        showToast('Errore', 'Si è verificato un errore. Riprova più tardi.', 'danger');
    });
}

/**
 * Imposta una nuova password
 */
function setNewPassword(token, password, confirmPassword) {
    // Validazione
    if (password !== confirmPassword) {
        showToast('Errore', 'Le password non coincidono', 'danger');
        return;
    }
    
    if (!isPasswordStrong(password)) {
        showToast('Errore', 'La password non è abbastanza sicura', 'warning');
        return;
    }
    
    // Mostra loader
    showLoader();
    
    // Invia la nuova password
    fetch('/api/auth/set-new-password', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ token, password })
    })
    .then(response => response.json())
    .then(data => {
        hideLoader();
        
        if (data.success) {
            showToast('Successo', 'Password reimpostata con successo! Ora puoi accedere.', 'success');
            
            // Redirect alla pagina di login dopo un breve ritardo
            setTimeout(() => {
                window.location.href = '/login';
            }, 2000);
        } else {
            showToast('Errore', data.message || 'Impossibile reimpostare la password', 'danger');
        }
    })
    .catch(err => {
        hideLoader();
        console.error('Errore nel cambio password:', err);
        showToast('Errore', 'Si è verificato un errore. Riprova più tardi.', 'danger');
    });
}

// Inizializza il sistema quando il documento è pronto
document.addEventListener('DOMContentLoaded', initSecuritySystem); 