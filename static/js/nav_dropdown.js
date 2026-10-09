// static/js/nav_dropdown.js
(function () {
  const root = document.querySelector('[data-dropdown]');
  if (!root) return;

  const trigger = root.querySelector('[data-dropdown-trigger]');
  const menu = root.querySelector('.nav__dropdown-menu');
  let closeTimer = null;
  const OPEN_CLASS = 'is-open';
  const OPEN_MS = 180;   // atraso para abrir suavemente
  const CLOSE_MS = 220;  // atraso para fechar (evita "fechar rápido")

  function setExpanded(el, val) {
    if (!el) return;
    el.setAttribute('aria-expanded', String(val));
  }

  function open() {
    clearTimeout(closeTimer);
    root.classList.add(OPEN_CLASS);
    setExpanded(trigger, true);
    menu?.setAttribute('aria-hidden', 'false');
  }

  function close() {
    clearTimeout(closeTimer);
    closeTimer = setTimeout(() => {
      root.classList.remove(OPEN_CLASS);
      setExpanded(trigger, false);
      menu?.setAttribute('aria-hidden', 'true');
      // fecha submenus internos também
      root.querySelectorAll('[data-submenu] .is-parent[aria-expanded="true"]').forEach(btn => {
        btn.setAttribute('aria-expanded', 'false');
      });
    }, CLOSE_MS);
  }

  // Abre ao focar/clicar o trigger
  trigger?.addEventListener('click', (e) => {
    e.preventDefault();
    if (root.classList.contains(OPEN_CLASS)) {
      close();
    } else {
      open();
    }
  });
  trigger?.addEventListener('mouseenter', () => {
    // pequeno atraso para intenção de abrir
    setTimeout(open, OPEN_MS);
  });
  trigger?.addEventListener('focus', open);

  // Mantém aberto quando mouse entra no menu
  menu?.addEventListener('mouseenter', () => {
    clearTimeout(closeTimer);
  });
  menu?.addEventListener('mouseleave', close);
  root.addEventListener('mouseleave', close);

  // Fecha com ESC
  root.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') close();
  });

  // ===== Submenus de 2º nível (pais NÃO clicáveis) =====
  root.querySelectorAll('[data-submenu]').forEach((item) => {
    const parentBtn = item.querySelector('.is-parent');
    const panel = item.querySelector('.nav__subpanel');
    if (!parentBtn || !panel) return;

    let subCloseTimer = null;

    function openSub() {
      clearTimeout(subCloseTimer);
      item.classList.add(OPEN_CLASS);
      parentBtn.setAttribute('aria-expanded', 'true');
    }
    function closeSub() {
      clearTimeout(subCloseTimer);
      subCloseTimer = setTimeout(() => {
        item.classList.remove(OPEN_CLASS);
        parentBtn.setAttribute('aria-expanded', 'false');
      }, CLOSE_MS);
    }

    parentBtn.addEventListener('mouseenter', openSub);
    parentBtn.addEventListener('click', (e) => {
      // não navega — apenas alterna
      e.preventDefault();
      if (item.classList.contains(OPEN_CLASS)) {
        closeSub();
      } else {
        openSub();
      }
    });
    parentBtn.addEventListener('focus', openSub);

    panel.addEventListener('mouseenter', openSub);
    panel.addEventListener('mouseleave', closeSub);
  });
})();
