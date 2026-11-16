'use strict';
(function init(event) {
  if (!event && (document.readyState === 'loading' || document.readyState === 'interactive')) {
    document.addEventListener('DOMContentLoaded', init, {once: true});
    return;
  }
  const video = document.getElementById('player');
  const panel = document.querySelector('[data-next-episode]');
  const setting = document.querySelector('[data-autoplay-setting]');
  if (!video || !panel || !setting || panel.dataset.vueNextEpisode === 'true') return;

  const toggle = setting.querySelector('[data-autoplay-next]');
  const nextLink = panel.querySelector('[data-next-link]');
  const cancel = panel.querySelector('[data-next-cancel]');
  const countdown = panel.querySelector('[data-next-countdown]');
  const seconds = panel.querySelector('[data-next-seconds]');
  const announcement = panel.querySelector('[data-next-announcement]');
  const key = `lumiere:autoplay-next:${video.closest('.player-wrap').dataset.viewer}`;
  let timer = null;

  try { toggle.checked = window.localStorage.getItem(key) === 'true'; } catch { /* The setting works for this page. */ }
  setting.hidden = false;

  function stopCountdown(announce = false) {
    if (timer !== null) window.clearInterval(timer);
    timer = null;
    countdown.hidden = true;
    cancel.hidden = true;
    if (announce) announcement.textContent = 'Đã hủy tự phát tập tiếp theo.';
  }

  function clearPanel() {
    stopCountdown();
    panel.hidden = true;
    announcement.textContent = '';
  }

  toggle.addEventListener('change', () => {
    try { window.localStorage.setItem(key, String(toggle.checked)); } catch { /* Keep the in-page selection. */ }
    if (!toggle.checked) stopCountdown(true);
  });
  cancel.addEventListener('click', () => {
    stopCountdown(true);
    nextLink.focus();
  });

  video.addEventListener('ended', () => {
    stopCountdown();
    panel.hidden = false;
    if (!toggle.checked || document.hidden) {
      announcement.textContent = 'Tập tiếp theo đã sẵn sàng.';
      return;
    }
    let remaining = 7;
    seconds.textContent = String(remaining);
    countdown.hidden = false;
    cancel.hidden = false;
    announcement.textContent = 'Tập tiếp theo sẽ tự phát sau 7 giây.';
    timer = window.setInterval(() => {
      if (!video.ended || document.hidden) {
        stopCountdown();
        return;
      }
      remaining -= 1;
      if (remaining > 0) seconds.textContent = String(remaining);
      else {
        stopCountdown();
        window.location.assign(nextLink.href);
      }
    }, 1000);
  });

  video.addEventListener('play', clearPanel);
  video.addEventListener('seeking', () => { if (!video.ended) clearPanel(); });
  document.addEventListener('visibilitychange', () => { if (document.hidden) stopCountdown(); });
  window.addEventListener('pagehide', clearPanel);
})();
