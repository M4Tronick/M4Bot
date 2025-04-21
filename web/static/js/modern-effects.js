/**
 * M4Bot - Effetti moderni JavaScript
 * Implementa effetti avanzati come parallasse, mesh gradients dinamici e microinterazioni
 * Versione 3.0 - Optimized for Performance
 */

document.addEventListener('DOMContentLoaded', () => {
    // Inizializza tutti gli effetti
    initParallaxEffects();
    initMeshGradients();
    initMicroInteractions();
    initHighContrastMode();
    initTextEffects();
    initLazyLoading();
    
    // Controlla se l'utente preferisce animazioni ridotte
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        initScrollAnimations();
    }
});

/**
 * Effetto parallasse su scroll
 */
function initParallaxEffects() {
    const parallaxContainers = document.querySelectorAll('.parallax-container');
    
    if (parallaxContainers.length === 0) return;
    
    // Usa requestAnimationFrame per ottimizzare performance
    let ticking = false;
    let lastScrollY = window.scrollY;
    
    // Funzione per aggiornare gli elementi parallasse
    const updateParallax = () => {
        parallaxContainers.forEach(container => {
            const containerRect = container.getBoundingClientRect();
            
            // Calcola solo se il container è visibile
            if (containerRect.bottom >= 0 && containerRect.top <= window.innerHeight) {
                const scrollPosition = window.scrollY;
                const containerTop = container.offsetTop;
                const containerHeight = container.offsetHeight;
                const viewportHeight = window.innerHeight;
                
                // Calcola la posizione relativa rispetto alla viewport
                const relativePos = (scrollPosition + viewportHeight - containerTop) / (containerHeight + viewportHeight);
                
                // Limita i valori tra 0 e 1
                const boundedPos = Math.max(0, Math.min(1, relativePos));
                
                // Applica diversi offset per ogni layer
                const layer1 = container.querySelector('.parallax-layer-1');
                const layer2 = container.querySelector('.parallax-layer-2');
                const layer3 = container.querySelector('.parallax-layer-3');
                
                if (layer1) layer1.style.setProperty('--parallax-offset-1', `${boundedPos * -30}px`);
                if (layer2) layer2.style.setProperty('--parallax-offset-2', `${boundedPos * -50}px`);
                if (layer3) layer3.style.setProperty('--parallax-offset-3', `${boundedPos * -70}px`);
            }
        });
        
        ticking = false;
    };
    
    // Rileva scroll e triggera parallasse
    window.addEventListener('scroll', () => {
        lastScrollY = window.scrollY;
        
        if (!ticking) {
            window.requestAnimationFrame(() => {
                updateParallax();
                ticking = false;
            });
            
            ticking = true;
        }
    }, { passive: true });
    
    // Inizializza al caricamento
    updateParallax();
}

/**
 * Mesh gradients dinamici (che cambiano con il mouse e con il tempo)
 */
function initMeshGradients() {
    const meshElements = document.querySelectorAll('.mesh-gradient');
    
    if (meshElements.length === 0) return;
    
    // Parametri configurabili
    const config = {
        hueRotationSpeed: 0.05, // velocità di cambio hue (gradi per frame)
        mouseIntensity: 0.03,   // intensità del movimento con il mouse (0-1)
        pulsateIntensity: 0.05, // intensità di pulsazione (0-1)
        pulsateSpeed: 0.005     // velocità di pulsazione (0-1)
    };
    
    // Valori iniziali
    let hueRotation = 0;
    let pulsatePhase = 0;
    
    // Posizione del mouse (normalizzata 0-1)
    let mouseX = 0.5;
    let mouseY = 0.5;
    
    // Traccia movimento mouse
    document.addEventListener('mousemove', (e) => {
        mouseX = e.clientX / window.innerWidth;
        mouseY = e.clientY / window.innerHeight;
    }, { passive: true });
    
    // Animazione mesh gradient
    function animateMeshGradients() {
        // Incrementa la fase di pulsazione
        pulsatePhase += config.pulsateSpeed;
        if (pulsatePhase > Math.PI * 2) pulsatePhase = 0;
        
        // Calcola il fattore di pulsazione (0-1)
        const pulsateFactor = (Math.sin(pulsatePhase) * config.pulsateIntensity) + 1;
        
        // Incrementa la rotazione hue
        hueRotation += config.hueRotationSpeed;
        if (hueRotation > 360) hueRotation = 0;
        
        // Applica l'animazione a ogni mesh gradient
        meshElements.forEach(el => {
            // Calcola il fattore di parallax basato sul mouse
            const parallaxX = (mouseX - 0.5) * config.mouseIntensity;
            const parallaxY = (mouseY - 0.5) * config.mouseIntensity;
            
            // Applica gli effetti agli elementi
            el.style.setProperty('--mesh-hue-rotate', `${hueRotation}deg`);
            el.style.setProperty('--mesh-translate-x', `${parallaxX * 100}%`);
            el.style.setProperty('--mesh-translate-y', `${parallaxY * 100}%`);
            el.style.setProperty('--mesh-scale', pulsateFactor);
            
            // Modifica l'insieme radial-gradient - solo per elementi con data-dynamic-mesh="true"
            if (el.dataset.dynamicMesh === 'true') {
                const dynamicGradient = `
                    radial-gradient(
                        circle at ${20 + (parallaxX * 60)}% ${20 + (parallaxY * 60)}%, 
                        hsl(${hueRotation}, 70%, 60%, 0.4), 
                        transparent ${30 + (pulsateFactor * 10)}%
                    ),
                    radial-gradient(
                        circle at ${80 - (parallaxX * 60)}% ${30 + (parallaxY * 40)}%, 
                        hsl(${(hueRotation + 60) % 360}, 70%, 60%, 0.4), 
                        transparent ${40 + (pulsateFactor * 10)}%
                    ),
                    radial-gradient(
                        circle at ${50 + (parallaxX * 30)}% ${80 - (parallaxY * 50)}%, 
                        hsl(${(hueRotation + 180) % 360}, 70%, 70%, 0.4), 
                        transparent ${30 + (pulsateFactor * 15)}%
                    )
                `;
                
                // Applica il gradient dinamico come custom property
                el.style.setProperty('--dynamic-mesh-gradient', dynamicGradient);
            }
        });
        
        // Continua l'animazione
        requestAnimationFrame(animateMeshGradients);
    }
    
    // Aggiungi CSS personalizzato
    const style = document.createElement('style');
    style.textContent = `
        .mesh-gradient[data-dynamic-mesh="true"]::before {
            background: var(--dynamic-mesh-gradient);
            transform: translateX(var(--mesh-translate-x, 0)) 
                       translateY(var(--mesh-translate-y, 0)) 
                       scale(var(--mesh-scale, 1));
            filter: hue-rotate(var(--mesh-hue-rotate, 0));
            transition: transform 0.1s ease-out;
        }
    `;
    document.head.appendChild(style);
    
    // Avvia l'animazione
    animateMeshGradients();
}

/**
 * Microinterazioni avanzate per migliorare l'UX
 */
function initMicroInteractions() {
    // Azioni hover con feedback
    document.querySelectorAll('.micro-hover').forEach(el => {
        el.addEventListener('mouseenter', () => {
            el.classList.add('micro-active');
            
            // Opzionale: effetto sonoro sottile
            if (el.dataset.hoverSound) {
                const audio = new Audio(el.dataset.hoverSound);
                audio.volume = 0.1;
                audio.play().catch(e => console.log('Audio non supportato:', e));
            }
        });
        
        el.addEventListener('mouseleave', () => {
            el.classList.remove('micro-active');
        });
    });
    
    // Azioni click con feedback
    document.querySelectorAll('.micro-click').forEach(el => {
        el.addEventListener('mousedown', () => {
            el.classList.add('micro-pressed');
            
            // Opzionale: effetto sonoro
            if (el.dataset.clickSound) {
                const audio = new Audio(el.dataset.clickSound);
                audio.volume = 0.2;
                audio.play().catch(e => console.log('Audio non supportato:', e));
            }
            
            // Aggiungi un'animazione di propagazione dell'onda click (ripple)
            const ripple = document.createElement('span');
            ripple.classList.add('ripple-effect');
            el.appendChild(ripple);
            
            setTimeout(() => {
                ripple.remove();
            }, 600);
        });
        
        el.addEventListener('mouseup', () => {
            el.classList.remove('micro-pressed');
        });
        
        el.addEventListener('mouseleave', () => {
            el.classList.remove('micro-pressed');
        });
    });
    
    // Aggiungi CSS per effetto ripple
    const style = document.createElement('style');
    style.textContent = `
        .ripple-effect {
            position: absolute;
            background: rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            pointer-events: none;
            transform: scale(0);
            animation: ripple-animation 0.6s ease-out;
        }
        
        @keyframes ripple-animation {
            to {
                transform: scale(4);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
}

/**
 * Modalità alto contrasto per migliorare l'accessibilità
 */
function initHighContrastMode() {
    const highContrastToggle = document.getElementById('high-contrast-toggle');
    const storedContrast = localStorage.getItem('m4bot-high-contrast');
    
    // Se il toggle esiste, configura l'interazione
    if (highContrastToggle) {
        // Imposta lo stato iniziale basato su localStorage
        if (storedContrast === 'true') {
            document.body.classList.add('high-contrast');
            highContrastToggle.setAttribute('aria-checked', 'true');
        } else {
            highContrastToggle.setAttribute('aria-checked', 'false');
        }
        
        // Gestisci il toggle
        highContrastToggle.addEventListener('click', () => {
            const isActive = document.body.classList.toggle('high-contrast');
            highContrastToggle.setAttribute('aria-checked', isActive ? 'true' : 'false');
            localStorage.setItem('m4bot-high-contrast', isActive);
            
            // Se in modalità scura, abilita high-contrast-dark invece
            if (document.body.getAttribute('data-bs-theme') === 'dark') {
                document.body.classList.toggle('high-contrast-dark', isActive);
                document.body.classList.toggle('high-contrast', false);
            }
        });
    }
    
    // Applica comunque la modalità se salvata, anche senza toggle
    if (!highContrastToggle && storedContrast === 'true') {
        const isDarkMode = document.body.getAttribute('data-bs-theme') === 'dark';
        document.body.classList.add(isDarkMode ? 'high-contrast-dark' : 'high-contrast');
    }
}

/**
 * Effetti di testo avanzati
 */
function initTextEffects() {
    // Inizializza testo glitch
    document.querySelectorAll('.text-glitch').forEach(el => {
        // Imposta data-text uguale al testo contenuto se non già impostato
        if (!el.hasAttribute('data-text')) {
            el.setAttribute('data-text', el.textContent);
        }
    });
    
    // Inizializza testo gradient animato
    document.querySelectorAll('.text-gradient-animated').forEach(el => {
        // Applica randomizzazione della fase iniziale per evitare sincronizzazione
        const randomStart = Math.floor(Math.random() * 100);
        el.style.animationDelay = `-${randomStart}%`;
    });
}

/**
 * Lazy loading ottimizzato per immagini e componenti pesanti
 */
function initLazyLoading() {
    // Configura l'IntersectionObserver
    const lazyObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const el = entry.target;
                
                // Gestione immagini con data-src
                if (el.tagName === 'IMG' && el.dataset.src) {
                    // Precarica l'immagine
                    const img = new Image();
                    img.onload = () => {
                        el.src = el.dataset.src;
                        el.classList.add('loaded');
                    };
                    img.src = el.dataset.src;
                    
                    // Se c'è srcset
                    if (el.dataset.srcset) {
                        el.srcset = el.dataset.srcset;
                    }
                    
                    // Pulisci gli attributi di dati
                    delete el.dataset.src;
                    delete el.dataset.srcset;
                }
                
                // Gestione componenti lazy loaded
                if (el.classList.contains('lazy-component')) {
                    const template = document.getElementById(el.dataset.template);
                    if (template) {
                        el.innerHTML = template.innerHTML;
                        el.classList.add('loaded');
                        
                        // Esegui eventuali script all'interno del componente
                        el.querySelectorAll('script').forEach(script => {
                            const newScript = document.createElement('script');
                            Array.from(script.attributes).forEach(attr => {
                                newScript.setAttribute(attr.name, attr.value);
                            });
                            newScript.textContent = script.textContent;
                            
                            script.parentNode.replaceChild(newScript, script);
                        });
                    }
                }
                
                // Rimuovi dalla osservazione
                observer.unobserve(el);
            }
        });
    }, {
        root: null,
        rootMargin: '100px', // Inizia a caricare quando gli elementi sono a 100px dalla visualizzazione
        threshold: 0.1
    });
    
    // Osserva tutte le immagini con data-src
    document.querySelectorAll('img[data-src]').forEach(img => {
        lazyObserver.observe(img);
    });
    
    // Osserva i componenti lazy
    document.querySelectorAll('.lazy-component').forEach(component => {
        lazyObserver.observe(component);
    });
}

/**
 * Animazioni al scroll
 */
function initScrollAnimations() {
    // Configura l'IntersectionObserver
    const scrollObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const el = entry.target;
                
                // Aggiungi classe per triggerare animazione
                el.classList.add('animate');
                
                // Determina se osservare continuamente o una volta sola
                if (!el.dataset.repeatAnimation) {
                    observer.unobserve(el);
                }
            } else if (entry.target.dataset.repeatAnimation) {
                // Rimuovi la classe animate se l'elemento esce dalla viewport
                // e deve essere animato nuovamente all'ingresso
                entry.target.classList.remove('animate');
            }
        });
    }, {
        root: null,
        rootMargin: '0px',
        threshold: 0.25
    });
    
    // Osserva gli elementi con animazione al scroll
    document.querySelectorAll('.reveal-on-scroll, .stagger-items').forEach(el => {
        scrollObserver.observe(el);
    });
}

/**
 * Esporta utility per l'uso in altri moduli
 */
window.M4BotEffects = {
    updateMeshGradient: function(element, options) {
        // Implementa logica per aggiornare gradients dinamicamente
    },
    
    createParallax: function(container, options) {
        // Implementa inizializzazione programmatica parallax
    },
    
    applyHighContrast: function(enabled) {
        // Implementa toggle programmatico high contrast
        if (enabled) {
            const isDarkMode = document.body.getAttribute('data-bs-theme') === 'dark';
            document.body.classList.add(isDarkMode ? 'high-contrast-dark' : 'high-contrast');
        } else {
            document.body.classList.remove('high-contrast', 'high-contrast-dark');
        }
        localStorage.setItem('m4bot-high-contrast', enabled);
    }
}; 