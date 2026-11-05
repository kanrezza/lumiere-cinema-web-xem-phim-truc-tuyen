'use strict';
(() => {
 const video = document.getElementById('player'); if (!video) return;
 const status = document.getElementById('player-status'); const retry = document.getElementById('retry-player');
 let hls, first = true, loading = false, stopped = false;
 async function loadSource() {
  if (loading || stopped) return; loading = true; video.dataset.loading = 'true';
  const position = first ? Number(video.dataset.position) : video.currentTime;
  const playing = !video.paused;
  try {
   const ticket = await postForm(video.dataset.ticket, {});
   if (hls) hls.destroy();
   const ready = () => {video.currentTime = Math.min(position || 0, video.duration || 0); if (playing) video.play().catch(() => {}); status.textContent = 'Sẵn sàng phát'; first = false; retry.hidden = true; video.dataset.loading = 'false';};
   video.addEventListener('loadedmetadata', ready, {once:true});
   if (window.Hls?.isSupported()) {
    hls = new Hls({enableWorker:true}); hls.loadSource(ticket.url); hls.attachMedia(video);
    hls.on(Hls.Events.ERROR, (_event, data) => {if (data.fatal) {status.textContent = 'Không thể phát video. Nguồn phát có thể đã hết hạn hoặc phiên đang được dùng ở thiết bị khác.'; retry.hidden = false;}});
   } else if (video.canPlayType('application/vnd.apple.mpegurl')) video.src = ticket.url;
   else {status.textContent = 'Trình duyệt này chưa hỗ trợ phát HLS. Hãy dùng trình duyệt hiện đại.'; retry.hidden = false;}
  } catch (error) {status.textContent = error.message; retry.hidden = false;}
  finally {loading = false;}
 }
 document.addEventListener('lumiere:stop', () => {stopped = true; if(hls) hls.destroy(); video.pause(); video.removeAttribute('src'); video.load();});
 retry.addEventListener('click', loadSource);
 loadSource();
 setInterval(loadSource, 480000);
 setInterval(() => {if (video.currentTime > 0 && !video.paused) postForm(video.dataset.progress, {position:video.currentTime}).catch(() => {});}, 15000);
 window.addEventListener('pagehide', () => {if (video.currentTime > 0) navigator.sendBeacon(video.dataset.progress, new URLSearchParams({position:video.currentTime, csrfmiddlewaretoken:csrfToken()}));});
 video.addEventListener('ended', () => {if (video.currentTime > 0) postForm(video.dataset.progress, {position:video.currentTime}).catch(() => {});});
 video.addEventListener('pause', () => {if (video.currentTime > 0) postForm(video.dataset.progress, {position:video.currentTime}).catch(() => {});});
})();
