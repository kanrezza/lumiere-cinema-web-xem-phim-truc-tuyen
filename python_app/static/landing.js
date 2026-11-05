/* Landing interactions. Shared motion.js owns the user's motion preference. */
(() => {
  'use strict';
  if (!document.body.classList.contains('landing-page')) return;

  const hero = document.querySelector('[data-landing-hero]');
  const scenes = hero ? [...hero.querySelectorAll('[data-parallax]')] : [];
  const magneticTargets = [...document.querySelectorAll('[data-magnetic]')];
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const root = document.documentElement;
  let heroVisible = true;
  let pointerFrame = null;
  let scrollFrame = null;
  let pointerPosition = null;
  let panelAnimation = null;

  const motionAllowed = () => !document.hidden &&
    !document.body.classList.contains('motion-paused') &&
    (document.body.classList.contains('motion-enabled') || !reduced.matches);

  function resetScene() {
    if (pointerFrame !== null) cancelAnimationFrame(pointerFrame);
    pointerFrame = null;
    pointerPosition = null;
    for (const scene of scenes) {
      scene.style.removeProperty('--scene-x');
      scene.style.removeProperty('--scene-y');
    }
    for (const target of magneticTargets) {
      target.style.removeProperty('--magnetic-x');
      target.style.removeProperty('--magnetic-y');
    }
  }

  function syncMotion() {
    if (!motionAllowed() || !finePointer.matches || !heroVisible) resetScene();
    if (!motionAllowed() && panelAnimation) {
      panelAnimation.cancel();
      panelAnimation = null;
    }
  }

  function updateScene() {
    pointerFrame = null;
    if (!pointerPosition || !hero || !heroVisible || !finePointer.matches || !motionAllowed()) return;
    const bounds = hero.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const clamp = value => Math.max(-1, Math.min(1, value));
    const x = clamp((pointerPosition.x - bounds.left) / bounds.width * 2 - 1);
    const y = clamp((pointerPosition.y - bounds.top) / bounds.height * 2 - 1);
    for (const scene of scenes) {
      scene.style.setProperty('--scene-x', `${(x * 9).toFixed(2)}px`);
      scene.style.setProperty('--scene-y', `${(y * 6).toFixed(2)}px`);
    }
  }

  if (hero && scenes.length) {
    hero.addEventListener('pointermove', event => {
      if (event.pointerType !== 'mouse' || !finePointer.matches || !motionAllowed() || !heroVisible) return;
      pointerPosition = {x: event.clientX, y: event.clientY};
      if (pointerFrame === null) pointerFrame = requestAnimationFrame(updateScene);
    }, {passive: true});
    hero.addEventListener('pointerleave', resetScene);
    hero.addEventListener('pointercancel', resetScene);
  }

  for (const target of magneticTargets) {
    let magneticFrame = null;
    let lastPointer = null;
    const clear = () => {
      if (magneticFrame !== null) cancelAnimationFrame(magneticFrame);
      magneticFrame = null;
      lastPointer = null;
      target.style.removeProperty('--magnetic-x');
      target.style.removeProperty('--magnetic-y');
    };
    target.addEventListener('pointermove', event => {
      if (event.pointerType !== 'mouse' || !finePointer.matches || !motionAllowed()) return;
      lastPointer = {x: event.clientX, y: event.clientY};
      if (magneticFrame !== null) return;
      magneticFrame = requestAnimationFrame(() => {
        magneticFrame = null;
        if (!lastPointer || !motionAllowed() || !finePointer.matches) return;
        const bounds = target.getBoundingClientRect();
        const x = Math.max(-3, Math.min(3, (lastPointer.x - bounds.left - bounds.width / 2) * .035));
        const y = Math.max(-2, Math.min(2, (lastPointer.y - bounds.top - bounds.height / 2) * .045));
        target.style.setProperty('--magnetic-x', `${x.toFixed(2)}px`);
        target.style.setProperty('--magnetic-y', `${y.toFixed(2)}px`);
      });
    }, {passive: true});
    target.addEventListener('pointerleave', clear);
    target.addEventListener('pointercancel', clear);
    target.addEventListener('blur', clear);
  }

  function updateProgress() {
    scrollFrame = null;
    const travel = root.scrollHeight - window.innerHeight;
    const progress = travel > 0 ? Math.max(0, Math.min(1, window.scrollY / travel)) : 0;
    root.style.setProperty('--landing-progress', progress.toFixed(4));
  }
  function scheduleProgress() {
    if (scrollFrame === null) scrollFrame = requestAnimationFrame(updateProgress);
  }
  window.addEventListener('scroll', scheduleProgress, {passive: true});
  window.addEventListener('resize', () => {resetScene(); scheduleProgress();}, {passive: true});
  window.addEventListener('load', scheduleProgress, {once: true});
  if ('ResizeObserver' in window) new ResizeObserver(scheduleProgress).observe(document.body);
  updateProgress();

  if (hero && 'IntersectionObserver' in window) {
    new IntersectionObserver(entries => {
      heroVisible = entries[0].isIntersecting;
      hero.classList.toggle('is-hero-visible', heroVisible);
      syncMotion();
    }, {threshold: 0}).observe(hero);
  }
  new MutationObserver(syncMotion).observe(document.body, {attributes: true, attributeFilter: ['class']});
  document.addEventListener('visibilitychange', syncMotion);
  const watchMedia = query => {
    if (query.addEventListener) query.addEventListener('change', syncMotion);
    else if (query.addListener) query.addListener(syncMotion);
  };
  watchMedia(reduced);
  watchMedia(finePointer);
  syncMotion();

  // The server renders a complete first panel. Tabs enhance it without a loader.
  const tabs = [...document.querySelectorAll('[data-experience-tab]')]
    .map(button => ({button, panel: document.getElementById(button.dataset.target)}))
    .filter(({panel}) => panel?.matches('[data-experience-panel]'));
  if (!tabs.length) return;
  let selected = Math.max(0, tabs.findIndex(({button}) => button.getAttribute('aria-selected') === 'true'));
  function selectTab(index, moveFocus = false, animate = true) {
    if (panelAnimation) {panelAnimation.cancel(); panelAnimation = null;}
    selected = index;
    tabs.forEach(({button, panel}, position) => {
      const active = position === index;
      button.setAttribute('role', 'tab');
      if (!button.id) button.id = `experience-tab-${position + 1}`;
      button.setAttribute('aria-controls', panel.id);
      button.setAttribute('aria-selected', String(active));
      button.tabIndex = active ? 0 : -1;
      panel.setAttribute('role', 'tabpanel');
      panel.setAttribute('aria-labelledby', button.id);
      panel.hidden = !active;
    });
    const {button, panel} = tabs[index];
    if (moveFocus) button.focus();
    if (animate && motionAllowed() && typeof panel.animate === 'function') {
      panelAnimation = panel.animate([
        {opacity: .4, transform: 'translateY(7px)'},
        {opacity: 1, transform: 'translateY(0)'},
      ], {duration: 280, easing: 'cubic-bezier(.2,.7,.2,1)'});
      panelAnimation.onfinish = () => {panelAnimation = null;};
    }
    scheduleProgress();
  }
  tabs.forEach(({button}, index) => {
    button.addEventListener('click', () => selectTab(index));
    button.addEventListener('keydown', event => {
      const vertical = button.closest('[role="tablist"]')?.getAttribute('aria-orientation') === 'vertical';
      let next;
      if (event.key === (vertical ? 'ArrowDown' : 'ArrowRight')) next = (selected + 1) % tabs.length;
      if (event.key === (vertical ? 'ArrowUp' : 'ArrowLeft')) next = (selected + tabs.length - 1) % tabs.length;
      if (event.key === 'Home') next = 0;
      if (event.key === 'End') next = tabs.length - 1;
      if (next === undefined) return;
      event.preventDefault();
      selectTab(next, true);
    });
  });
  selectTab(selected, false, false);
})();
