'use strict';
(() => {
 const video = document.getElementById('player'); if (!video) return;
 const status = document.getElementById('player-status'); const retry = document.getElementById('retry-player');
 let hls, first = true, loading = false, stopped = false, generation = 0, removeReady = () => {};
 let requestedPosition = null;
 const safePosition = value => Number.isFinite(Number(value)) ? Math.max(0, Number(value)) : 0;
 video.addEventListener('lumiere:seek', event => {if (loading || video.dataset.loading === 'true') requestedPosition = safePosition(event.detail.position);});
 async function loadSource() {
  if (loading || stopped) return;
  loading = true; video.dataset.loading = 'true'; requestedPosition = null;
  let playing = !video.paused;
  const currentGeneration = ++generation;
  try {
   const ticket = await postForm(video.dataset.ticket, {});
   if (stopped || currentGeneration !== generation) return;
   // A viewer may seek while the ticket request is in flight. Keep that latest
   // target rather than restoring the older position captured before the request.
   let position = requestedPosition ?? (first ? safePosition(video.dataset.position) : safePosition(video.currentTime));
   playing = !video.paused;
   removeReady();
   if (hls) hls.destroy();
   const ready = () => {
    if (stopped || currentGeneration !== generation || video.readyState < 1 || !Number.isFinite(video.duration) || video.duration <= 0) return;
    position = requestedPosition ?? position;
    try {video.currentTime = Math.min(position, video.duration);} catch (_) {return;}
    removeReady();
    if (playing) video.play().catch(() => {});
    status.textContent = 'Sẵn sàng phát'; first = false; retry.hidden = true; video.dataset.loading = 'false';
   };
   video.addEventListener('loadedmetadata', ready);
   video.addEventListener('durationchange', ready);
   removeReady = () => {video.removeEventListener('loadedmetadata', ready); video.removeEventListener('durationchange', ready);};
   if (window.Hls?.isSupported()) {
    hls = new Hls({enableWorker:true}); hls.loadSource(ticket.url); hls.attachMedia(video);
    hls.on(Hls.Events.ERROR, (_event, data) => {
     if (data.fatal && currentGeneration === generation) {removeReady(); video.dataset.loading = 'false'; status.textContent = 'Không thể phát video. Nguồn phát có thể đã hết hạn hoặc phiên đang được dùng ở thiết bị khác.'; retry.hidden = false;}
    });
   } else if (video.canPlayType('application/vnd.apple.mpegurl')) video.src = ticket.url;
   else {removeReady(); video.dataset.loading = 'false'; status.textContent = 'Trình duyệt này chưa hỗ trợ phát HLS. Hãy dùng trình duyệt hiện đại.'; retry.hidden = false;}
  } catch (error) {removeReady(); video.dataset.loading = 'false'; status.textContent = error.message; retry.hidden = false;}
  finally {loading = false;}
 }
 document.addEventListener('lumiere:stop', () => {stopped = true; generation++; removeReady(); if(hls) hls.destroy(); video.pause(); video.removeAttribute('src'); video.load();});
 retry.addEventListener('click', loadSource);
 loadSource();
 setInterval(loadSource, 480000);
 setInterval(() => {if (video.currentTime > 0 && !video.paused && video.dataset.loading !== 'true') postForm(video.dataset.progress, {position:video.currentTime}).catch(() => {});}, 15000);
 window.addEventListener('pagehide', () => {if (video.currentTime > 0 && video.dataset.loading !== 'true') navigator.sendBeacon(video.dataset.progress, new URLSearchParams({position:video.currentTime, csrfmiddlewaretoken:csrfToken()}));});
 video.addEventListener('ended', () => {if (video.currentTime > 0 && video.dataset.loading !== 'true') postForm(video.dataset.progress, {position:video.currentTime}).catch(() => {});});
 video.addEventListener('pause', () => {if (video.currentTime > 0 && video.dataset.loading !== 'true') postForm(video.dataset.progress, {position:video.currentTime}).catch(() => {});});
})();
