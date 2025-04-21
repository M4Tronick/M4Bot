/**
 * M4Bot - Gestione Tema e Effetti UI
 * Versione 3.0 - Migliorato con transizioni fluide ed effetti moderni
 */

document.addEventListener('DOMContentLoaded', function() {
  // Inizializzazione del tema e impostazioni UI
  initThemeSystem();
  initUIEffects();
  initParallaxEffects();
  initAccessibilityFeatures();
  observeElementsForAnimation();
});

/**
 * Sistema di gestione del tema (chiaro/scuro)
 */
function initThemeSystem() {
  const darkModeToggle = document.getElementById('darkModeToggle');
  const htmlElement = document.documentElement;
  const prefersDarkScheme = window.matchMedia('(prefers-color-scheme: dark)');
  
  // Carica preferenza dal localStorage o usa la preferenza del sistema
  const savedTheme = localStorage.getItem('theme');
  
  if (savedTheme) {
    htmlElement.setAttribute('data-bs-theme', savedTheme);
    if (darkModeToggle) {
      darkModeToggle.checked = savedTheme === 'dark';
    }
  } else if (prefersDarkScheme.matches) {
    htmlElement.setAttribute('data-bs-theme', 'dark');
    if (darkModeToggle) {
      darkModeToggle.checked = true;
    }
  }
  
  // Aggiungi classe per transizione
  document.body.classList.add('transition-colors');
  
  // Gestisci cambio tema con toggle
  if (darkModeToggle) {
    darkModeToggle.addEventListener('change', function() {
      // Aggiungi classe per animazione
      document.body.classList.add('theme-changing');
      
      // Imposta tema dopo breve delay per animazione
      setTimeout(() => {
        const newTheme = this.checked ? 'dark' : 'light';
        htmlElement.setAttribute('data-bs-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        
        // Emetti evento personalizzato per il cambio tema
        const event = new CustomEvent('themeChanged', { detail: { theme: newTheme } });
        document.dispatchEvent(event);
        
        // Rimuovi classe animazione
        setTimeout(() => {
          document.body.classList.remove('theme-changing');
        }, 300);
      }, 50);
    });
  }
  
  // Osserva il cambiamento delle preferenze del sistema
  prefersDarkScheme.addEventListener('change', function(e) {
    if (!localStorage.getItem('theme')) {
      htmlElement.setAttribute('data-bs-theme', e.matches ? 'dark' : 'light');
      if (darkModeToggle) {
        darkModeToggle.checked = e.matches;
      }
    }
  });
  
  // Esponi API theme per altri script
  window.themeSystem = {
    getTheme: () => htmlElement.getAttribute('data-bs-theme'),
    setTheme: (theme) => {
      htmlElement.setAttribute('data-bs-theme', theme);
      localStorage.setItem('theme', theme);
      if (darkModeToggle) {
        darkModeToggle.checked = theme === 'dark';
      }
      const event = new CustomEvent('themeChanged', { detail: { theme } });
      document.dispatchEvent(event);
    },
    toggleTheme: () => {
      const currentTheme = htmlElement.getAttribute('data-bs-theme');
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      htmlElement.setAttribute('data-bs-theme', newTheme);
      localStorage.setItem('theme', newTheme);
      if (darkModeToggle) {
        darkModeToggle.checked = newTheme === 'dark';
      }
      const event = new CustomEvent('themeChanged', { detail: { theme: newTheme } });
      document.dispatchEvent(event);
    }
  };
}

/**
 * Effetti UI migliorati
 */
function initUIEffects() {
  // Gestione cards con hover effects
  const hoverCards = document.querySelectorAll('.card-hover-lift, .hover-scale-shadow, .hover-lift');
  
  hoverCards.forEach(card => {
    card.addEventListener('mouseenter', function() {
      this.classList.add('hardware-accelerated');
    });
    
    card.addEventListener('mouseleave', function() {
      // Mantieni hardware acceleration per un attimo dopo il mouseleave
      setTimeout(() => {
        this.classList.remove('hardware-accelerated');
      }, 300);
    });
  });
  
  // Gestione ripple effect per pulsanti
  initRippleEffect();
  
  // Gestione barra di navigazione con effetto glassmorphism
  const navbar = document.querySelector('.navbar');
  if (navbar) {
    window.addEventListener('scroll', function() {
      if (window.scrollY > 50) {
        navbar.classList.add('navbar-scrolled');
      } else {
        navbar.classList.remove('navbar-scrolled');
      }
    });
  }
  
  // Gestione bottoni con classe .btn-gradient-border
  const gradientButtons = document.querySelectorAll('.btn-gradient-border');
  gradientButtons.forEach(button => {
    button.addEventListener('mousemove', function(e) {
      const rect = this.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      
      this.style.setProperty('--mouse-x', x + '%');
      this.style.setProperty('--mouse-y', y + '%');
    });
  });
  
  // Pulsante "torna in cima"
  initBackToTopButton();
  
  // Inizializza le notifiche toast
  initToasts();
}

/**
 * Effetto ripple per pulsanti
 */
function initRippleEffect() {
  const buttons = document.querySelectorAll('.btn-ripple, .ripple-effect');
  
  buttons.forEach(button => {
    button.addEventListener('click', function(e) {
      // Verifica se è su mobile o su browser
      const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
      
      // Crea l'elemento ripple
      const ripple = document.createElement('span');
      ripple.classList.add('ripple-element');
      this.appendChild(ripple);
      
      // Posiziona l'elemento ripple
      const rect = this.getBoundingClientRect();
      const size = Math.max(rect.width, rect.height);
      
      ripple.style.width = ripple.style.height = size + 'px';
      
      // Posiziona diversamente per mobile e desktop
      if (isMobile) {
        ripple.style.top = '50%';
        ripple.style.left = '50%';
        ripple.style.transform = 'translate(-50%, -50%)';
                } else {
        ripple.style.top = (e.clientY - rect.top - size / 2) + 'px';
        ripple.style.left = (e.clientX - rect.left - size / 2) + 'px';
      }
      
      // Aggiungi classe per attivare l'animazione
      ripple.classList.add('animate');
      
      // Rimuovi l'elemento dopo l'animazione
      setTimeout(() => {
        ripple.remove();
      }, 600);
    });
  });
}

/**
 * Effetti parallasse per elementi decorativi
 */
function initParallaxEffects() {
  const parallaxElements = document.querySelectorAll('.parallax-element');
  
  if (parallaxElements.length > 0) {
    // Verifica se usare reduced motion
            const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            
    if (!prefersReducedMotion) {
      window.addEventListener('mousemove', function(e) {
        const mouseX = e.clientX;
        const mouseY = e.clientY;
        
        parallaxElements.forEach(element => {
          const speed = element.getAttribute('data-parallax-speed') || 0.05;
          const rect = element.getBoundingClientRect();
          const centerX = rect.left + rect.width / 2;
          const centerY = rect.top + rect.height / 2;
          
          const deltaX = (mouseX - centerX) * speed;
          const deltaY = (mouseY - centerY) * speed;
          
          element.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
        });
      });
      
      // Reset parallax elements on mouse leave
      document.addEventListener('mouseleave', function() {
        parallaxElements.forEach(element => {
          element.style.transform = 'translate(0, 0)';
        });
      });
    }
  }
}

/**
 * Funzionalità di accessibilità
 */
function initAccessibilityFeatures() {
  // Toggle per alto contrasto
  const highContrastToggle = document.getElementById('highContrastToggle');
  if (highContrastToggle) {
    // Carica preferenza salvata
    const savedHighContrast = localStorage.getItem('highContrast') === 'true';
    highContrastToggle.checked = savedHighContrast;
    
    if (savedHighContrast) {
      document.documentElement.classList.add('high-contrast');
    }
    
    highContrastToggle.addEventListener('change', function() {
      if (this.checked) {
        document.documentElement.classList.add('high-contrast');
        localStorage.setItem('highContrast', 'true');
      } else {
        document.documentElement.classList.remove('high-contrast');
        localStorage.setItem('highContrast', 'false');
                }
            });
        }
        
  // Toggle per motion ridotto
  const reducedMotionToggle = document.getElementById('reducedMotionToggle');
  if (reducedMotionToggle) {
    // Carica preferenza o usa la preferenza del sistema
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const savedReducedMotion = localStorage.getItem('reducedMotion');
    
    if (savedReducedMotion !== null) {
      reducedMotionToggle.checked = savedReducedMotion === 'true';
      document.documentElement.classList.toggle('reduced-motion', savedReducedMotion === 'true');
            } else {
      reducedMotionToggle.checked = prefersReducedMotion;
      if (prefersReducedMotion) {
        document.documentElement.classList.add('reduced-motion');
      }
    }
    
    reducedMotionToggle.addEventListener('change', function() {
      document.documentElement.classList.toggle('reduced-motion', this.checked);
      localStorage.setItem('reducedMotion', this.checked);
    });
  }
  
  // Dimensione testo
  const textSizeSelect = document.getElementById('textSizeSelect');
  if (textSizeSelect) {
    // Carica preferenza salvata
    const savedTextSize = localStorage.getItem('textSize') || 'normal';
    textSizeSelect.value = savedTextSize;
    
    if (savedTextSize !== 'normal') {
      document.documentElement.classList.add(`text-size-${savedTextSize}`);
    }
    
    textSizeSelect.addEventListener('change', function() {
      // Rimuovi tutte le classi esistenti di dimensione testo
      document.documentElement.classList.remove('text-size-large', 'text-size-larger', 'text-size-largest');
      
      if (this.value !== 'normal') {
        document.documentElement.classList.add(`text-size-${this.value}`);
      }
      
      localStorage.setItem('textSize', this.value);
    });
  }
}

/**
 * Animazioni di elementi basate su IntersectionObserver
 */
function observeElementsForAnimation() {
  if ('IntersectionObserver' in window) {
    const elementsToAnimate = document.querySelectorAll('.reveal-on-scroll');
    
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('visible');
          // Non osservare più questo elemento
          observer.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.1, // Elemento visibile al 10%
      rootMargin: '0px 0px -50px 0px' // Trigger leggermente prima
    });
    
    elementsToAnimate.forEach(element => {
      observer.observe(element);
    });
    
    // Gestione delle animazioni sequenziali
    const staggerContainers = document.querySelectorAll('.stagger-items');
    const staggerObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('animate');
          staggerObserver.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.1,
      rootMargin: '0px 0px -50px 0px'
    });
    
    staggerContainers.forEach(container => {
      staggerObserver.observe(container);
    });
  } else {
    // Fallback per browser che non supportano IntersectionObserver
    document.querySelectorAll('.reveal-on-scroll').forEach(element => {
      element.classList.add('visible');
    });
    
    document.querySelectorAll('.stagger-items').forEach(container => {
      container.classList.add('animate');
    });
  }
}

/**
 * Sistema di notifiche toast
 */
function initToasts() {
  // API globale per le notifiche toast
  window.toastSystem = {
    show: function(message, type = 'info', duration = 3000) {
      const toastContainer = document.querySelector('.toast-container');
      
      if (!toastContainer) return;
      
      const toast = document.createElement('div');
      toast.classList.add('toast', 'fade-in', `toast-${type}`);
      toast.setAttribute('role', 'alert');
      toast.setAttribute('aria-live', 'assertive');
      toast.setAttribute('aria-atomic', 'true');
      
      let icon = 'info-circle';
      if (type === 'success') icon = 'check-circle';
      if (type === 'warning') icon = 'exclamation-triangle';
      if (type === 'danger') icon = 'exclamation-circle';
      
      toast.innerHTML = `
        <div class="toast-header">
          <i class="fas fa-${icon} me-2"></i>
          <strong class="me-auto">${type.charAt(0).toUpperCase() + type.slice(1)}</strong>
          <button type="button" class="btn-close" aria-label="Chiudi"></button>
        </div>
        <div class="toast-body">
          ${message}
        </div>
      `;
      
      toastContainer.appendChild(toast);
      
      // Aggiungi ascoltatore per chiusura
      const closeButton = toast.querySelector('.btn-close');
      closeButton.addEventListener('click', function() {
        toast.classList.remove('fade-in');
        toast.classList.add('fade-out');
        
        // Rimuovi dopo animazione
        setTimeout(() => {
          toast.remove();
        }, 300);
      });
      
      // Autochiusura dopo durata specificata
      if (duration > 0) {
        setTimeout(() => {
          if (toast.parentNode) {
            toast.classList.remove('fade-in');
            toast.classList.add('fade-out');
            
            setTimeout(() => {
              if (toast.parentNode) {
                toast.remove();
              }
            }, 300);
          }
        }, duration);
      }
    }
  };
}

/**
 * Button "Torna in cima"
 */
function initBackToTopButton() {
  const toTopButton = document.getElementById('to-top-button');
  
  if (toTopButton) {
    window.addEventListener('scroll', function() {
      if (window.scrollY > 300) {
        toTopButton.classList.add('visible');
      } else {
        toTopButton.classList.remove('visible');
      }
    });
    
    toTopButton.addEventListener('click', function() {
      window.scrollTo({
        top: 0,
        behavior: 'smooth'
      });
    });
  }
} 