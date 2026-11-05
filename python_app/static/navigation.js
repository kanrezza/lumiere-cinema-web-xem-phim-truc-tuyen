/* Shared disclosure navigation; panels escape the scrollable navigation rail. */
(() => {
  'use strict';
  const header = document.querySelector('.site-header');
  if (!header) return;

  const navigation = header.querySelector('.main-nav');
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const fallbacks = [...header.querySelectorAll('[data-nav-fallback]')];
  const disclosures = [...header.querySelectorAll('[data-nav-trigger]')]
    .map(trigger => {
      const key = trigger.dataset.navKey;
      const panel = document.getElementById(trigger.getAttribute('aria-controls'));
      const fallback = fallbacks.find(link => link.dataset.navFallback === key);
      if (!key || !panel || !header.contains(panel) || panel.dataset.navPanel !== key || !fallback) return null;
      return {trigger, panel, fallback, open:false, reason:null, enterTimer:null, leaveTimer:null};
    }).filter(Boolean);
  if (!disclosures.length) return;

  function cancelHoverTimers(disclosure) {
    window.clearTimeout(disclosure.enterTimer);
    window.clearTimeout(disclosure.leaveTimer);
    disclosure.enterTimer = null;
    disclosure.leaveTimer = null;
  }

  function contains(disclosure, target) {
    return target instanceof Node && (disclosure.trigger.contains(target) || disclosure.panel.contains(target));
  }

  function positionPanel(disclosure) {
    if (!disclosure.open) return;
    const origin = header.getBoundingClientRect();
    const button = disclosure.trigger.getBoundingClientRect();
    const width = Math.min(480, Math.max(0, window.innerWidth - 40));
    const maxLeft = Math.max(20, window.innerWidth - width - 20);
    const left = Math.max(20, Math.min(button.left - 12, maxLeft));
    disclosure.panel.style.setProperty('--genre-left', `${Math.round(left - origin.left)}px`);
  }

  function setOpen(disclosure, next, source = 'click', focusLink = false) {
    cancelHoverTimers(disclosure);
    if (next) {
      for (const other of disclosures) {
        if (other !== disclosure) setOpen(other, false);
      }
    }
    disclosure.open = next;
    disclosure.reason = next ? source : null;
    disclosure.panel.hidden = !next;
    disclosure.trigger.setAttribute('aria-expanded', String(next));
    if (next) {
      const account = header.querySelector('.account-menu');
      if (account?.open) account.open = false;
      positionPanel(disclosure);
      if (focusLink) disclosure.panel.querySelector('a[href]')?.focus({preventScroll:true});
    }
  }

  for (const disclosure of disclosures) {
    const {trigger, panel, fallback} = disclosure;
    trigger.hidden = false;
    fallback.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    panel.hidden = true;

    trigger.addEventListener('click', event => {
      const keyboard = event.detail === 0;
      // A pointer click after hover keeps the disclosure open.
      if (disclosure.open && disclosure.reason === 'hover' && !keyboard) setOpen(disclosure, true, 'click');
      else setOpen(disclosure, !disclosure.open, keyboard ? 'keyboard' : 'click', keyboard && !disclosure.open);
    });
    trigger.addEventListener('keydown', event => {
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      event.preventDefault();
      setOpen(disclosure, true, 'keyboard');
      const links = [...panel.querySelectorAll('a[href]')];
      (event.key === 'ArrowUp' ? links[links.length - 1] : links[0])?.focus({preventScroll:true});
    });
    panel.addEventListener('click', event => {
      if (event.target instanceof Element && event.target.closest('a[href]')) setOpen(disclosure, false);
    });

    trigger.addEventListener('pointerenter', event => {
      if (event.pointerType !== 'mouse' || !finePointer.matches) return;
      window.clearTimeout(disclosure.leaveTimer);
      if (!disclosure.open) disclosure.enterTimer = window.setTimeout(() => setOpen(disclosure, true, 'hover'), 120);
    });
    const scheduleHoverClose = event => {
      window.clearTimeout(disclosure.enterTimer);
      if (!disclosure.open || disclosure.reason !== 'hover' || contains(disclosure, event.relatedTarget)) return;
      disclosure.leaveTimer = window.setTimeout(() => {
        if (!contains(disclosure, document.activeElement)) setOpen(disclosure, false);
      }, 150);
    };
    trigger.addEventListener('pointerleave', scheduleHoverClose);
    panel.addEventListener('pointerenter', () => window.clearTimeout(disclosure.leaveTimer));
    panel.addEventListener('pointerleave', scheduleHoverClose);
  }

  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const disclosure = disclosures.find(item => item.open);
    if (!disclosure) return;
    event.preventDefault();
    setOpen(disclosure, false);
    disclosure.trigger.focus({preventScroll:true});
  });
  document.addEventListener('pointerdown', event => {
    for (const disclosure of disclosures) {
      if (!contains(disclosure, event.target)) setOpen(disclosure, false);
    }
  });
  document.addEventListener('focusin', event => {
    // Native Tab navigation closes a disclosure after focus leaves it.
    for (const disclosure of disclosures) {
      if (!contains(disclosure, event.target)) setOpen(disclosure, false);
    }
  });

  window.addEventListener('resize', () => disclosures.forEach(positionPanel), {passive:true});
  const onScroll = () => {
    for (const disclosure of disclosures) {
      if (!disclosure.open) continue;
      if (disclosure.reason === 'keyboard') positionPanel(disclosure);
      else setOpen(disclosure, false);
    }
  };
  window.addEventListener('scroll', onScroll, {passive:true});
  navigation?.addEventListener('scroll', onScroll, {passive:true});
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) disclosures.forEach(disclosure => setOpen(disclosure, false));
  });
})();
