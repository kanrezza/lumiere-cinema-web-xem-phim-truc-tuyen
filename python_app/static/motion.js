/*
 * Motion contract (load with defer, after app.js):
 * - [data-motion-toggle] contains [data-motion-label]; aria-pressed means paused.
 * - body.motion-paused follows prefers-reduced-motion until an explicit toggle.
 * - body.motion-enabled allows motion, including an explicit per-session opt-in.
 * - body.motion-suspended pauses CSS loops while the document is hidden.
 * - Visible [data-motion-loop] containers receive .is-motion-visible.
 * - .reel-viewport measures .reel-track overflow into --reel-travel (negative px).
 *   Reel links stay native keyboard-scrollable; leaving the reel resets scroll.
 * - [data-reveal] animates once; optional data-reveal-delay is milliseconds (0–240).
 *   Its normal CSS must remain visible: JavaScript never hides pending content.
 * - .movie-card .poster uses --tilt-x / --tilt-y (degrees, fallback 0deg).
 * - The membership form only gets visual feedback here; app.js owns price text.
 */
(() => {
  'use strict';

  const media = (query) => typeof window.matchMedia === 'function'
    ? window.matchMedia(query) : {matches: false};
  const reducedMotion = media('(prefers-reduced-motion: reduce)');
  const finePointer = media('(hover: hover) and (pointer: fine)');
  const toggles = [...document.querySelectorAll('[data-motion-toggle]')];
  const revealTargets = [...document.querySelectorAll('[data-reveal]')];
  const loops = [...document.querySelectorAll('[data-motion-loop]')];
  const reels = [...document.querySelectorAll('.reel-viewport')]
    .map((viewport) => ({viewport, track: viewport.querySelector('.reel-track'), travel: null}))
    .filter((reel) => reel.track);
  const posters = [...document.querySelectorAll('.movie-card .poster')];
  const seen = new WeakSet();
  const animations = new Map();
  const storageKey = 'lumiere-motion-paused';
  // null follows the device; true/false is an explicit choice for this session.
  let motionPreference = null;
  let paused = false;
  let revealObserver;
  let frame = null;
  let pendingPointer = null;

  try {
    const savedPreference = window.sessionStorage.getItem(storageKey);
    motionPreference = savedPreference === '1' ? true : savedPreference === '0' ? false : null;
  } catch (_) {
    // Motion remains usable when storage is unavailable or blocked.
  }

  function cancelAnimation(element) {
    const animation = animations.get(element);
    if (animation) {
      animation.cancel();
      animations.delete(element);
    }
  }

  function animate(element, keyframes, options = {}) {
    if (!element || paused || document.hidden || typeof element.animate !== 'function') return;
    cancelAnimation(element);
    const animation = element.animate(keyframes, {
      duration: 480, easing: 'cubic-bezier(.2,.7,.2,1)', fill: 'none', ...options,
    });
    animations.set(element, animation);
    const cleanup = () => {
      if (animations.get(element) === animation) animations.delete(element);
    };
    animation.onfinish = cleanup;
    animation.oncancel = cleanup;
  }

  function resetTilt() {
    if (frame !== null) window.cancelAnimationFrame(frame);
    frame = null;
    pendingPointer = null;
    for (const poster of posters) {
      poster.style.removeProperty('--tilt-x');
      poster.style.removeProperty('--tilt-y');
    }
  }

  function syncMotion() {
    paused = motionPreference === null ? reducedMotion.matches : motionPreference;
    document.body.classList.toggle('motion-paused', paused);
    document.body.classList.toggle('motion-enabled', !paused);
    document.body.classList.toggle('motion-suspended', document.hidden);
    for (const toggle of toggles) {
      const label = paused ? 'Bật hiệu ứng' : 'Tắt hiệu ứng';
      const description = motionPreference === null && reducedMotion.matches
        ? 'Thiết bị đang giảm chuyển động. Bật hiệu ứng trên trang này.' : label;
      const text = toggle.querySelector('[data-motion-label]');
      if (text) text.textContent = label;
      toggle.setAttribute('aria-pressed', String(paused));
      toggle.setAttribute('aria-label', label);
      toggle.title = description;
      toggle.disabled = false;
    }
    if (paused || document.hidden) {
      for (const element of [...animations.keys()]) cancelAnimation(element);
      resetTilt();
    } else {
      // A manually scrolled, unfocused reel must not add a second offset when
      // motion resumes after an explicit opt-in or returning to the tab.
      for (const {viewport} of reels) {
        if (!viewport.contains(document.activeElement)) viewport.scrollLeft = 0;
      }
    }
    if (paused) {
      revealObserver?.disconnect();
      // A pause must reveal everything immediately, including pending entrances.
      for (const element of revealTargets) seen.add(element);
    }
  }

  for (const toggle of toggles) {
    toggle.addEventListener('click', () => {
      motionPreference = !paused;
      try {
        window.sessionStorage.setItem(storageKey, motionPreference ? '1' : '0');
      } catch (_) { /* This preference is optional. */ }
      syncMotion();
    });
  }

  const onMediaChange = (query, callback) => {
    if (typeof query.addEventListener === 'function') query.addEventListener('change', callback);
    else if (typeof query.addListener === 'function') query.addListener(callback);
  };
  onMediaChange(reducedMotion, syncMotion);
  onMediaChange(finePointer, resetTilt);
  document.addEventListener('visibilitychange', syncMotion);
  syncMotion();

  if (typeof window.IntersectionObserver === 'function') {
    const loopObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        entry.target.classList.toggle('is-motion-visible', entry.isIntersecting);
      }
    }, {threshold: 0});
    for (const loop of loops) loopObserver.observe(loop);

    revealObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting || seen.has(entry.target)) continue;
        const element = entry.target;
        seen.add(element);
        revealObserver.unobserve(element);
        if (element.contains(document.activeElement)) continue;
        const delay = Math.min(240, Math.max(0, Number(element.dataset.revealDelay) || 0));
        animate(element, [
          {opacity: 0, transform: 'translateY(20px)'},
          {opacity: 1, transform: 'translateY(0)'},
        ], {delay, fill: 'backwards'});
      }
    }, {threshold: 0.08, rootMargin: '0px 0px -24px 0px'});
    for (const element of revealTargets) {
      if (!seen.has(element)) revealObserver.observe(element);
    }
  } else {
    for (const loop of loops) loop.classList.add('is-motion-visible');
  }

  function measureReel(reel) {
    const travel = `${-Math.max(0, reel.track.scrollWidth - reel.viewport.clientWidth)}px`;
    if (travel === reel.travel) return;
    reel.travel = travel;
    reel.track.style.setProperty('--reel-travel', travel);
  }

  for (const reel of reels) {
    measureReel(reel);
    let focusTimer;
    reel.viewport.addEventListener('focusout', () => {
      window.clearTimeout(focusTimer);
      focusTimer = window.setTimeout(() => {
        if (!reel.viewport.contains(document.activeElement)) reel.viewport.scrollLeft = 0;
      }, 0);
    });
  }
  if (reels.length && typeof window.ResizeObserver === 'function') {
    const reelByElement = new Map();
    const resizeObserver = new ResizeObserver((entries) => {
      const changedReels = new Set(entries.map((entry) => reelByElement.get(entry.target)));
      for (const reel of changedReels) if (reel) measureReel(reel);
    });
    for (const reel of reels) {
      for (const element of [reel.viewport, reel.track]) {
        reelByElement.set(element, reel);
        resizeObserver.observe(element);
      }
    }
  } else if (reels.length) {
    window.addEventListener('resize', () => reels.forEach(measureReel), {passive: true});
  }

  document.addEventListener('focusin', (event) => {
    if (!(event.target instanceof Element)) return;
    const target = event.target.closest('[data-reveal]');
    if (target) {
      seen.add(target);
      revealObserver?.unobserve(target);
      cancelAnimation(target);
    }
  });

  if (typeof window.requestAnimationFrame === 'function') {
    for (const poster of posters) {
      poster.addEventListener('pointermove', (event) => {
        if (paused || document.hidden || !finePointer.matches || event.pointerType !== 'mouse') return;
        pendingPointer = {poster, x: event.clientX, y: event.clientY};
        if (frame !== null) return;
        frame = window.requestAnimationFrame(() => {
          frame = null;
          const pointer = pendingPointer;
          pendingPointer = null;
          if (!pointer || paused || document.hidden) return;
          const rect = pointer.poster.getBoundingClientRect();
          if (!rect.width || !rect.height) return;
          const clamp = (value) => Math.max(-1, Math.min(1, value));
          const x = clamp(((pointer.x - rect.left) / rect.width - 0.5) * 2);
          const y = clamp(((pointer.y - rect.top) / rect.height - 0.5) * 2);
          pointer.poster.style.setProperty('--tilt-x', `${(-y * 4).toFixed(2)}deg`);
          pointer.poster.style.setProperty('--tilt-y', `${(x * 4).toFixed(2)}deg`);
        });
      }, {passive: true});
      poster.addEventListener('pointerleave', resetTilt);
      poster.addEventListener('pointercancel', resetTilt);
    }
  }

  document.getElementById('membership-form')?.addEventListener('change', (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || input.name !== 'plan' || !input.checked) return;
    animate(document.getElementById('selected-price'), [
      {opacity: 0.35, transform: 'translateY(6px)'},
      {opacity: 1, transform: 'translateY(0)'},
    ], {duration: 240});
    animate(input.closest('.plan-option'), [
      {transform: 'scale(.985)'}, {transform: 'scale(1)'},
    ], {duration: 280});
  });
})();
