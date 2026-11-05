'use strict';
(() => {
  const video = document.getElementById('player');
  if (!video) return;
  const wrap = video.closest('.player-wrap');
  const controls = wrap.querySelector('.player-controls');
  const center = wrap.querySelector('.player-center');
  const range = wrap.querySelector('.player-range');
  const volume = wrap.querySelector('.player-volume');
  const playButton = wrap.querySelector('.player-toggle');
  const muteButton = wrap.querySelector('[data-player-action=mute]');
  const fullscreenButton = wrap.querySelector('[data-player-action=fullscreen]');
  const status = document.getElementById('player-status');
  if (!controls || !range) return;
  const time = seconds => {const safe = Math.max(0,Math.floor(Number(seconds)||0)); return `${Math.floor(safe/60)}:${String(safe%60).padStart(2,'0')}`;};
  const updateTime = () => {
    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    range.max = duration || 100;
    range.value = video.currentTime || 0;
    range.setAttribute('aria-valuetext', `${time(video.currentTime)} trên ${time(duration)}`);
    wrap.querySelector('[data-player-time]').textContent = time(video.currentTime);
    wrap.querySelector('[data-player-duration]').textContent = time(duration);
  };
  const updatePlaying = () => {wrap.classList.toggle('is-playing',!video.paused&&!video.ended); playButton.setAttribute('aria-label',video.paused?'Phát':'Tạm dừng'); center.setAttribute('aria-label',video.ended?'Phát lại phim':'Phát phim');};
  const togglePlay = async () => {if (video.paused) {try {await video.play();} catch (_) {status.textContent='Chưa thể phát. Hãy thử lại khi video tải xong.';}} else video.pause();};
  for (const button of wrap.querySelectorAll('[data-player-action]')) button.addEventListener('click',async () => {
    switch(button.dataset.playerAction) {
      case 'play': await togglePlay(); break;
      case 'back': if(Number.isFinite(video.duration)) video.currentTime=Math.max(0,video.currentTime-10); break;
      case 'forward': if(Number.isFinite(video.duration)) video.currentTime=Math.min(video.duration,video.currentTime+10); break;
      case 'mute': video.muted=!video.muted; break;
      case 'fullscreen':
        try {if(document.fullscreenElement) await document.exitFullscreen(); else if(wrap.requestFullscreen) await wrap.requestFullscreen(); else if(video.webkitEnterFullscreen) video.webkitEnterFullscreen();} catch (_) {status.textContent='Không thể mở toàn màn hình trong trình duyệt này.';}
        break;
    }
  });
  range.addEventListener('input',()=>{if(Number.isFinite(video.duration)) video.currentTime=Math.max(0,Math.min(video.duration,Number(range.value)));updateTime();});
  volume.addEventListener('input',()=>{video.volume=Number(volume.value);video.muted=video.volume===0;});
  video.addEventListener('volumechange',()=>{volume.value=video.muted?0:video.volume;muteButton.setAttribute('aria-label',video.muted?'Bật tiếng':'Tắt tiếng');});
  const ready = () => {controls.hidden=false;center.hidden=false;video.controls=false;wrap.querySelector('[data-player-quality]').textContent=video.videoHeight?`${video.videoHeight}p`:'';updateTime();updatePlaying();};
  video.addEventListener('loadedmetadata',ready);
  if(video.readyState>=1) ready();
  video.addEventListener('timeupdate',updateTime);
  video.addEventListener('play',updatePlaying);
  video.addEventListener('pause',updatePlaying);
  video.addEventListener('ended',updatePlaying);
  video.addEventListener('error',()=>{video.controls=true;controls.hidden=true;center.hidden=true;});
  document.addEventListener('fullscreenchange',()=>{fullscreenButton.setAttribute('aria-label',document.fullscreenElement?'Thoát toàn màn hình':'Toàn màn hình');});
})();
