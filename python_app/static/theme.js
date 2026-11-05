'use strict';
(() => {
  const storageKey = 'lumiere-theme';
  const root = document.documentElement;

  function savedTheme() {
    try {
      const saved = window.localStorage.getItem(storageKey);
      return saved === 'light' || saved === 'dark' ? saved : 'dark';
    } catch {
      return 'dark';
    }
  }

  function applyTheme(theme) {
    root.dataset.theme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = theme === 'light' ? '#f6f5f1' : '#0b0d0e';
    for (const button of document.querySelectorAll('[data-theme-toggle]')) {
      const action = theme === 'light' ? 'Chuyển sang giao diện tối' : 'Chuyển sang giao diện sáng';
      button.setAttribute('aria-label', action);
      button.title = action;
    }
  }

  // Loaded synchronously before styles so a saved choice is applied before paint.
  applyTheme(savedTheme());

  function bindControls() {
    for (const button of document.querySelectorAll('[data-theme-toggle]')) {
      button.hidden = false;
      button.addEventListener('click', () => {
        const next = root.dataset.theme === 'light' ? 'dark' : 'light';
        applyTheme(next);
        try { window.localStorage.setItem(storageKey, next); } catch { /* Switching still works when storage is unavailable. */ }
      });
    }
    applyTheme(root.dataset.theme);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bindControls, {once: true});
  } else {
    bindControls();
  }

  window.addEventListener('storage', event => {
    if (event.key === storageKey || event.key === null) applyTheme(savedTheme());
  });
  window.addEventListener('pageshow', () => applyTheme(savedTheme()));
})();
