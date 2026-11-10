'use strict';
(() => {
  const trigger = document.querySelector('[data-studio-menu]');
  const sidebar = document.getElementById('studio-sidebar');
  const overlay = document.querySelector('.studio-sidebar-overlay');
  if (trigger && sidebar) {
    const close = (restoreFocus = true) => {
      document.body.classList.remove('studio-nav-open');
      trigger.setAttribute('aria-expanded', 'false');
      if (overlay) overlay.hidden = true;
      if (restoreFocus) trigger.focus();
    };
    trigger.addEventListener('click', () => {
      const expanded = trigger.getAttribute('aria-expanded') === 'true';
      if (expanded) return close();
      document.body.classList.add('studio-nav-open');
      trigger.setAttribute('aria-expanded', 'true');
      if (overlay) overlay.hidden = false;
      sidebar.querySelector('[data-studio-close]')?.focus();
    });
    for (const button of document.querySelectorAll('[data-studio-close]')) button.addEventListener('click', () => close());
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && trigger.getAttribute('aria-expanded') === 'true') { event.preventDefault(); close(); }
    });
    document.addEventListener('focusin', event => {
      if (trigger.getAttribute('aria-expanded') === 'true' && !sidebar.contains(event.target) && event.target !== trigger) close(false);
    });
    window.addEventListener('resize', () => { if (window.innerWidth > 900) close(false); });
  }
  for (const menu of document.querySelectorAll('.studio-account')) {
    document.addEventListener('click', event => { if (!menu.contains(event.target)) menu.open = false; });
    menu.addEventListener('keydown', event => { if (event.key === 'Escape') { menu.open = false; menu.querySelector('summary')?.focus(); } });
  }
})();
