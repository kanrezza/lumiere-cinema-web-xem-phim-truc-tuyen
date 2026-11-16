export function mountLandingMotion() {
  if (!document.body.classList.contains('landing-page')) return () => {};
  const abort = new AbortController();
  const {signal} = abort;
  let heroObserver: IntersectionObserver | undefined;
  let sizeObserver: ResizeObserver | undefined;

  const hero = document.querySelector<HTMLElement>('[data-landing-hero]');
  const scenes = hero ? [...hero.querySelectorAll<HTMLElement>('[data-parallax]')] : [];
  const magneticTargets = [...document.querySelectorAll<HTMLElement>('[data-magnetic]')];
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const root = document.documentElement;
  let heroVisible = true;
  let pointerFrame: number | null = null;
  let scrollFrame: number | null = null;
  let pointerPosition: {x: number; y: number} | null = null;

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
  }

  function updateScene() {
    pointerFrame = null;
    if (!pointerPosition || !hero || !heroVisible || !finePointer.matches || !motionAllowed()) return;
    const bounds = hero.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    const clamp = (value: number) => Math.max(-1, Math.min(1, value));
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
    }, {passive: true, signal});
    hero.addEventListener('pointerleave', resetScene, {signal});
    hero.addEventListener('pointercancel', resetScene, {signal});
  }

  for (const target of magneticTargets) {
    let magneticFrame: number | null = null;
    let lastPointer: {x: number; y: number} | null = null;
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
    }, {passive: true, signal});
    target.addEventListener('pointerleave', clear, {signal});
    target.addEventListener('pointercancel', clear, {signal});
    target.addEventListener('blur', clear, {signal});
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
  window.addEventListener('scroll', scheduleProgress, {passive: true, signal});
  window.addEventListener('resize', () => {resetScene(); scheduleProgress();}, {passive: true, signal});
  window.addEventListener('load', scheduleProgress, {once: true, signal});
  if ('ResizeObserver' in window) {
    sizeObserver = new ResizeObserver(scheduleProgress);
    sizeObserver.observe(document.body);
  }
  updateProgress();

  if (hero && 'IntersectionObserver' in window) {
    heroObserver = new IntersectionObserver(entries => {
      heroVisible = entries[0].isIntersecting;
      hero.classList.toggle('is-hero-visible', heroVisible);
      syncMotion();
    }, {threshold: 0});
    heroObserver.observe(hero);
  }
  const motionObserver = new MutationObserver(syncMotion);
  motionObserver.observe(document.body, {attributes: true, attributeFilter: ['class']});
  document.addEventListener('visibilitychange', syncMotion, {signal});
  const watchMedia = (query: MediaQueryList) => {
    if (query.addEventListener) query.addEventListener('change', syncMotion, {signal});
  };
  watchMedia(reduced);
  watchMedia(finePointer);
  syncMotion();

  return () => {
    abort.abort();
    heroObserver?.disconnect();
    sizeObserver?.disconnect();
    motionObserver.disconnect();
    resetScene();
    if (scrollFrame !== null) cancelAnimationFrame(scrollFrame);
  };
}
