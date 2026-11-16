import { computed, ref, watchEffect } from 'vue'

export function mountMotion() {
  const media = (query: string) => window.matchMedia(query);
  const abort = new AbortController();
  const {signal} = abort;
  const reducedMotion = media('(prefers-reduced-motion: reduce)');
  const finePointer = media('(hover: hover) and (pointer: fine)');
  const toggles = [...document.querySelectorAll<HTMLButtonElement>('[data-motion-toggle]')];
  const revealTargets = [...document.querySelectorAll<HTMLElement>('[data-reveal]')];
  const loops = [...document.querySelectorAll('[data-motion-loop]')];
  const reels = [...document.querySelectorAll<HTMLElement>('.reel-viewport')].flatMap(viewport => {
    const track = viewport.querySelector<HTMLElement>('.reel-track');
    return track ? [{viewport, track, travel: ''}] : [];
  });
  const seen = new WeakSet();
  const animations = new Map<Element, Animation>();
  const storageKey = 'lumiere-motion-paused';
  // null follows the device; true/false is an explicit choice for this session.
  const motionPreference = ref<boolean | null>(null);
  const paused = computed(() => motionPreference.value ?? reduced.value);
  const reduced = ref(reducedMotion.matches);
  const pageHidden = ref(document.hidden);
  let revealObserver: IntersectionObserver | undefined;
  let loopObserver: IntersectionObserver | undefined;
  let resizeObserver: ResizeObserver | undefined;
  let frame: number | null = null;
  let pendingPointer: {poster: HTMLElement; x: number; y: number} | null = null;

  try {
    const savedPreference = window.sessionStorage.getItem(storageKey);
    motionPreference.value = savedPreference === '1' ? true : savedPreference === '0' ? false : null;
  } catch (_) {
    // Motion remains usable when storage is unavailable or blocked.
  }

  function cancelAnimation(element: Element) {
    const animation = animations.get(element);
    if (animation) {
      animation.cancel();
      animations.delete(element);
    }
  }

  function animate(element: Element | null, keyframes: Keyframe[], options: KeyframeAnimationOptions = {}) {
    if (!element || paused.value || document.hidden || typeof element.animate !== 'function') return;
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
    for (const poster of document.querySelectorAll<HTMLElement>('.movie-card .poster')) {
      poster.style.removeProperty('--tilt-x');
      poster.style.removeProperty('--tilt-y');
    }
  }

  function syncMotion() {
    document.body.classList.toggle('motion-paused', paused.value);
    document.body.classList.toggle('motion-enabled', !paused.value);
    document.body.classList.toggle('motion-suspended', pageHidden.value);
    for (const toggle of toggles) {
      const label = paused.value ? 'Bật hiệu ứng' : 'Tắt hiệu ứng';
      const description = motionPreference.value === null && reduced.value
        ? 'Thiết bị đang giảm chuyển động. Bật hiệu ứng trên trang này.' : label;
      const text = toggle.querySelector('[data-motion-label]');
      if (text) text.textContent = label;
      toggle.setAttribute('aria-pressed', String(paused.value));
      toggle.setAttribute('aria-label', label);
      toggle.title = description;
      toggle.disabled = false;
    }
    if (paused.value || pageHidden.value) {
      for (const element of [...animations.keys()]) cancelAnimation(element);
      resetTilt();
    } else {
      // A manually scrolled, unfocused reel must not add a second offset when
      // motion resumes after an explicit opt-in or returning to the tab.
      for (const {viewport} of reels) {
        if (!viewport.contains(document.activeElement)) viewport.scrollLeft = 0;
      }
    }
    if (paused.value) {
      revealObserver?.disconnect();
      // A pause must reveal everything immediately, including pending entrances.
      for (const element of revealTargets) seen.add(element);
    }
  }

  for (const toggle of toggles) {
    toggle.addEventListener('click', () => {
      motionPreference.value = !paused.value;
      try {
        window.sessionStorage.setItem(storageKey, motionPreference.value ? '1' : '0');
      } catch (_) { /* This preference is optional. */ }
    }, {signal});
  }

  reducedMotion.addEventListener('change', event => {reduced.value = event.matches;}, {signal});
  finePointer.addEventListener('change', resetTilt, {signal});
  document.addEventListener('visibilitychange', () => {pageHidden.value = document.hidden;}, {signal});
  const stop = watchEffect(syncMotion, {flush: 'sync'});

  if (typeof window.IntersectionObserver === 'function') {
    loopObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        entry.target.classList.toggle('is-motion-visible', entry.isIntersecting);
      }
    }, {threshold: 0});
    for (const loop of loops) loopObserver.observe(loop);

    revealObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting || seen.has(entry.target)) continue;
        if (!(entry.target instanceof HTMLElement)) continue;
        const element = entry.target;
        seen.add(element);
        revealObserver?.unobserve(element);
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

  function measureReel(reel: (typeof reels)[number]) {
    const travel = `${-Math.max(0, reel.track.scrollWidth - reel.viewport.clientWidth)}px`;
    if (travel === reel.travel) return;
    reel.travel = travel;
    reel.track.style.setProperty('--reel-travel', travel);
  }

  for (const reel of reels) {
    measureReel(reel);
    let focusTimer: number | undefined;
    reel.viewport.addEventListener('focusout', () => {
      window.clearTimeout(focusTimer);
      focusTimer = window.setTimeout(() => {
        if (!reel.viewport.contains(document.activeElement)) reel.viewport.scrollLeft = 0;
      }, 0);
    });
  }
  if (reels.length && typeof window.ResizeObserver === 'function') {
    const reelByElement = new Map<Element, (typeof reels)[number]>();
    resizeObserver = new ResizeObserver((entries) => {
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
    window.addEventListener('resize', () => reels.forEach(measureReel), {passive: true, signal});
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

  const boundPosters = new WeakSet<HTMLElement>();
  function bindPosters(root: ParentNode) {
    for (const poster of root.querySelectorAll<HTMLElement>('.movie-card .poster')) {
      if (boundPosters.has(poster)) continue;
      boundPosters.add(poster);
      poster.addEventListener('pointermove', (event) => {
        if (paused.value || document.hidden || !finePointer.matches || event.pointerType !== 'mouse') return;
        pendingPointer = {poster, x: event.clientX, y: event.clientY};
        if (frame !== null) return;
        frame = window.requestAnimationFrame(() => {
          frame = null;
          const pointer = pendingPointer;
          pendingPointer = null;
          if (!pointer || paused.value || document.hidden) return;
          const rect = pointer.poster.getBoundingClientRect();
          if (!rect.width || !rect.height) return;
          const clamp = (value: number) => Math.max(-1, Math.min(1, value));
          const x = clamp(((pointer.x - rect.left) / rect.width - 0.5) * 2);
          const y = clamp(((pointer.y - rect.top) / rect.height - 0.5) * 2);
          pointer.poster.style.setProperty('--tilt-x', `${(-y * 4).toFixed(2)}deg`);
          pointer.poster.style.setProperty('--tilt-y', `${(x * 4).toFixed(2)}deg`);
        });
      }, {passive: true, signal});
      poster.addEventListener('pointerleave', resetTilt, {signal});
      poster.addEventListener('pointercancel', resetTilt, {signal});
    }
  }

  bindPosters(document);
  document.addEventListener('lumiere:catalog-render', event => {
    if (event.target instanceof HTMLElement) bindPosters(event.target);
  }, {signal});

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
  }, {signal});
  return () => {
    stop();
    abort.abort();
    loopObserver?.disconnect();
    revealObserver?.disconnect();
    resizeObserver?.disconnect();
    for (const element of animations.keys()) cancelAnimation(element);
    resetTilt();
  };
}
