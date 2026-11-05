'use strict';
(() => {
  const player = document.querySelector('[data-trailer-player]');
  if (!player) return;
  const button = player.querySelector('[data-trailer-load]');
  const placeholder = player.querySelector('[data-trailer-placeholder]');
  const status = document.querySelector('[data-trailer-status]');
  const initialStatus = status ? status.textContent : '';
  let frame = null;

  if (button && placeholder) {
    button.addEventListener('click', () => {
      if (frame) return;
      let source;
      try {
        source = new URL(button.dataset.trailerEmbed);
        if (source.protocol !== 'https:' || source.hostname !== 'www.youtube-nocookie.com' || !/^\/embed\/[A-Za-z0-9_-]{11}$/.test(source.pathname)) throw new Error('Unsupported trailer source');
      } catch {
        if (status) status.textContent = 'Chưa thể mở trailer. Bạn có thể thử liên kết YouTube bên dưới.';
        return;
      }
      source.searchParams.set('autoplay', '1');
      frame = document.createElement('iframe');
      frame.className = 'trailer-frame';
      frame.title = `Trailer ${button.dataset.trailerTitle || ''}`.trim();
      frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-presentation');
      frame.setAttribute('allow', 'autoplay; encrypted-media; picture-in-picture');
      frame.referrerPolicy = 'strict-origin-when-cross-origin';
      frame.allowFullscreen = true;
      frame.src = source.href;
      player.append(frame);
      placeholder.hidden = true;
      frame.focus();
      if (status) status.textContent = 'Đã mở trình phát YouTube. Nếu video không tải được, dùng liên kết bên dưới.';
    });
  }

  window.addEventListener('pagehide', () => {
    const video = player.querySelector('video');
    if (video) video.pause();
    if (frame) {
      frame.remove();
      frame = null;
      if (placeholder) placeholder.hidden = false;
      if (status) status.textContent = initialStatus;
    }
  });
})();
