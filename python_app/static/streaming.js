'use strict';
(() => {
  const header = document.querySelector('.site-header');
  if (header) {
    let scheduled = false;
    const updateHeader = () => {header.classList.toggle('is-scrolled', scrollY > 20); scheduled = false;};
    addEventListener('scroll', () => {if (!scheduled) {scheduled = true; requestAnimationFrame(updateHeader);}}, {passive:true});
    updateHeader();
  }
  const navigation = document.querySelector('.main-nav');
  if (navigation) {
    const revealCurrent = () => {
      const current = navigation.querySelector('[aria-current]:not([hidden]), .nav-genre-trigger.is-current:not([hidden])');
      if (!current) return;
      const rail = navigation.getBoundingClientRect();
      const item = current.getBoundingClientRect();
      if (item.right > rail.right) navigation.scrollLeft += item.right - rail.right + 14;
      else if (item.left < rail.left) navigation.scrollLeft -= rail.left - item.left + 14;
    };
    requestAnimationFrame(revealCurrent);
    if (window.ResizeObserver) new ResizeObserver(revealCurrent).observe(navigation);
  }
  const menu = document.querySelector('.account-menu');
  document.addEventListener('click', event => {if (menu?.open && !menu.contains(event.target)) menu.open = false;});
  document.addEventListener('keydown', event => {if (event.key === 'Escape' && menu?.open) {menu.open = false; menu.querySelector('summary').focus();}});
  for (const shelf of document.querySelectorAll('[data-shelf]')) {
    const row = shelf.querySelector('.film-row');
    const buttons = [...shelf.querySelectorAll('[data-shelf-dir]')];
    if (!row || !buttons.length) continue;
    const update = () => {for (const button of buttons) button.disabled = Number(button.dataset.shelfDir) < 0 ? row.scrollLeft <= 2 : row.scrollLeft + row.clientWidth >= row.scrollWidth - 2;};
    for (const button of buttons) button.addEventListener('click', () => row.scrollBy({left:Number(button.dataset.shelfDir)*row.clientWidth*.85,behavior:document.body.classList.contains('motion-paused')?'auto':'smooth'}));
    row.addEventListener('scroll',update,{passive:true});
    if (window.ResizeObserver) new ResizeObserver(update).observe(row); else addEventListener('resize',update);
    update();
  }
})();

// Feature selection is manual; only the short, muted public teaser auto-plays.
(() => {
  const stage = document.querySelector('[data-feature-stage]');
  if (!stage) return;
  const tabs = [...stage.querySelectorAll('[role="tab"]')];
  const panels = [...stage.querySelectorAll('[role="tabpanel"]')];
  const controls = stage.querySelector('[data-feature-controls]');
  const toggle = stage.querySelector('[data-preview-toggle]');
  const preview = stage.querySelector('.feature-preview');
  let current = 0;
  let visible = true;
  let manuallyPaused = false;
  let playRequest = 0;
  controls.hidden = false;

  function syncPreview() {
    if (!preview) {toggle.hidden = true; return;}
    const active = panels[current].contains(preview);
    toggle.hidden = !active;
    const motionPaused = document.body.classList.contains('motion-paused');
    const paused = manuallyPaused || motionPaused;
    toggle.setAttribute('aria-pressed', String(paused));
    const label = paused ? 'Phát xem trước' : 'Tạm dừng xem trước';
    toggle.setAttribute('aria-label', label);
    toggle.querySelector('[data-preview-label]').textContent = label;
    toggle.querySelector('.preview-symbol').textContent = paused ? '▷' : 'Ⅱ';
    const ticket = ++playRequest;
    if (!active || !visible || paused || document.hidden || document.body.classList.contains('quickview-open')) {
      preview.pause();
      if (!active) preview.classList.remove('is-playing');
      return;
    }
    if (!preview.getAttribute('src')) preview.src = preview.dataset.previewSrc;
    preview.muted = true;
    preview.play().then(() => {
      if (ticket === playRequest) preview.classList.add('is-playing');
    }).catch(() => {
      if (ticket !== playRequest) return;
      manuallyPaused = true;
      syncPreview();
    });
  }

  function select(index, focus = false) {
    current = index;
    tabs.forEach((tab, i) => {
      tab.setAttribute('aria-selected', String(i === current));
      tab.tabIndex = i === current ? 0 : -1;
      panels[i].hidden = i !== current;
    });
    if (focus) tabs[current].focus();
    const content = panels[current].querySelector('.feature-content');
    if (!document.body.classList.contains('motion-paused') && content.animate) {
      content.animate([{opacity:.3,transform:'translateY(10px)'},{opacity:1,transform:'none'}],{duration:350,easing:'ease-out'});
    }
    syncPreview();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => select(index));
    tab.addEventListener('keydown', event => {
      let target;
      if (event.key === 'ArrowRight') target = (current + 1) % tabs.length;
      if (event.key === 'ArrowLeft') target = (current + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') target = 0;
      if (event.key === 'End') target = tabs.length - 1;
      if (target === undefined) return;
      event.preventDefault();
      select(target, true);
    });
  });
  toggle.addEventListener('click', () => {
    if (document.body.classList.contains('motion-paused')) {
      document.querySelector('[data-motion-toggle]')?.click();
      manuallyPaused = false;
    } else manuallyPaused = !manuallyPaused;
    syncPreview();
  });
  document.addEventListener('visibilitychange', syncPreview);
  new MutationObserver(syncPreview).observe(document.body,{attributes:true,attributeFilter:['class']});
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {visible = entries[0].isIntersecting; syncPreview();},{threshold:.15}).observe(stage);
  }
  preview?.addEventListener('error', () => {preview.classList.remove('is-playing'); manuallyPaused = true; syncPreview();});
  syncPreview();
})();
