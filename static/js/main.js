/* === Toggle do menu mobile ====================================== */
(function(){
  var toggle = document.getElementById('js-nav-toggle');
  var menu = document.getElementById('js-mobile-menu');
  if(!toggle || !menu) return;

  function setExpanded(isOpen){
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    if(isOpen){
      menu.classList.add('nav__menu--open');
      menu.removeAttribute('hidden');
    } else {
      menu.classList.remove('nav__menu--open');
      menu.setAttribute('hidden','');
    }
  }

  toggle.addEventListener('click', function(){
    setExpanded(!menu.classList.contains('nav__menu--open'));
  });

  // Fecha ao redimensionar p/ desktop
  window.addEventListener('resize', function(){ setExpanded(false); });
})();

/* === Dropdown "Configurações" (desktop) com gatilho <a> ========= */
(function(){
  var dd = document.querySelector('.nav__dropdown');
  if(!dd) return;

  var btn  = dd.querySelector('[data-dropdown-trigger]') || dd.querySelector('.nav__link--dropdown');
  var menu = dd.querySelector('.nav__dropdown-menu');
  if(!btn || !menu) return;

  // Sempre inicia FECHADO (independente da rota atual)
  btn.setAttribute('aria-expanded', 'false');
  menu.setAttribute('aria-hidden', 'true');
  dd.classList.remove('is-open');

  function getItems(){
    var sel = 'a[href]:not([disabled]), [tabindex]:not([tabindex="-1"])';
    return Array.prototype.slice.call(menu.querySelectorAll(sel));
  }

  function openMenu(){
    dd.classList.add('is-open');
    btn.setAttribute('aria-expanded','true');
    menu.setAttribute('aria-hidden','false');
  }
  function closeMenu(){
    dd.classList.remove('is-open');
    btn.setAttribute('aria-expanded','false');
    menu.setAttribute('aria-hidden','true');
    // opcional: btn.blur();
  }
  function toggleMenu(){
    (btn.getAttribute('aria-expanded') === 'true') ? closeMenu() : openMenu();
  }

  // Clique no link: abre/fecha (sem JS, href navega para config.setup)
  btn.addEventListener('click', function(e){
    e.preventDefault();
    var willOpen = btn.getAttribute('aria-expanded') !== 'true';
    toggleMenu();
    if(willOpen){
      var items = getItems();
      if(items.length) items[0].focus();
    }
  });

  // Teclas no link: ↓ ↑ Enter Espaço Esc
  btn.addEventListener('keydown', function(e){
    if(e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' '){
      e.preventDefault();
      if(btn.getAttribute('aria-expanded') !== 'true') openMenu();
      var items = getItems();
      if(items.length) items[0].focus();
    } else if(e.key === 'ArrowUp'){
      e.preventDefault();
      if(btn.getAttribute('aria-expanded') !== 'true') openMenu();
      var items = getItems();
      if(items.length) items[items.length - 1].focus();
    } else if(e.key === 'Escape'){
      closeMenu();
    }
  });

  // Navegação dentro do menu
  menu.addEventListener('keydown', function(e){
    var items = getItems();
    if(!items.length) return;
    var idx = items.indexOf(document.activeElement);

    if(e.key === 'ArrowDown'){
      e.preventDefault();
      items[(idx + 1) % items.length].focus();
    } else if(e.key === 'ArrowUp'){
      e.preventDefault();
      items[(idx - 1 + items.length) % items.length].focus();
    } else if(e.key === 'Home'){
      e.preventDefault();
      items[0].focus();
    } else if(e.key === 'End'){
      e.preventDefault();
      items[items.length - 1].focus();
    } else if(e.key === 'Escape'){
      e.preventDefault();
      closeMenu();
      btn.focus();
    }
  });

  // Fecha ao clicar/focar fora
  document.addEventListener('click', function(e){
    if(!dd.contains(e.target)) closeMenu();
  });
  document.addEventListener('focusin', function(e){
    if(!dd.contains(e.target)) closeMenu();
  });

  // Evita estados presos após resize
  window.addEventListener('resize', closeMenu);
})();