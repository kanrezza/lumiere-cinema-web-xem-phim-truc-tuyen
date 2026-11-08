'use strict';
(() => {
  const video = document.getElementById('player');
  if (!video) return;
  const wrap = video.closest('.player-wrap');
  if (!wrap) return;
  const controls = wrap.querySelector('.player-controls');
  const center = wrap.querySelector('.player-center');
  const range = wrap.querySelector('.player-range');
  const volume = wrap.querySelector('.player-volume');
  const playButton = wrap.querySelector('.player-toggle');
  const muteButton = wrap.querySelector('[data-player-action=mute]');
  const fullscreenButton = wrap.querySelector('[data-player-action=fullscreen]');
  const subtitles = wrap.querySelector('.player-subtitles');
  const captionDisplay = wrap.querySelector('[data-caption-display]');
  const captionText = wrap.querySelector('[data-caption-text]');
  const status = document.getElementById('player-status');
  const room = document.getElementById('room');
  const canSeek = wrap.dataset.canSeek !== 'false' && (!room || room.dataset.host === 'true');
  if (!controls || !range) return;
  let pendingSeek = null;
  let selectedSubtitle = 'off';
  let nativeFullscreen = false;
  let subtitleElements = Array.from(video.querySelectorAll('track[data-subtitle]'));
  const boundSubtitleElements = new WeakSet();
  const tell = message => {if (status) status.textContent = message;};
  const finite = value => Number.isFinite(Number(value)) ? Number(value) : 0;
  const time = seconds => {const safe = Math.max(0, Math.floor(finite(seconds) + 1e-3)); return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`;};
  const updateTime = () => {
    const duration = Math.max(0, finite(video.duration));
    const position = pendingSeek === null ? Math.max(0, finite(video.currentTime)) : pendingSeek;
    range.max = duration || 100;
    range.value = position;
    range.disabled = !canSeek || video.readyState < 1 || duration <= 0;
    range.setAttribute('aria-valuetext', `${time(position)} trên ${time(duration)}`);
    wrap.querySelector('[data-player-time]').textContent = time(position);
    wrap.querySelector('[data-player-duration]').textContent = time(duration);
  };
  const updatePlaying = () => {
    wrap.classList.toggle('is-playing', !video.paused && !video.ended);
    if (playButton) playButton.setAttribute('aria-label', video.paused ? 'Phát' : 'Tạm dừng');
    if (center) center.setAttribute('aria-label', video.ended ? 'Phát lại phim' : 'Phát phim');
  };
  const seekTo = target => {
    if (!canSeek || video.readyState < 1 || !Number.isFinite(video.duration) || video.duration <= 0 || !Number.isFinite(target)) return false;
    target = Math.max(0, Math.min(video.duration, target));
    // HLS may expose several seekable windows. Never assign a time inside a gap.
    const windows = [];
    for (let index = 0; index < video.seekable.length; index++) {
      const start = Math.max(0, video.seekable.start(index));
      const end = Math.min(video.duration, video.seekable.end(index));
      if (Number.isFinite(start) && Number.isFinite(end) && start <= end) windows.push([start, end]);
    }
    if (windows.length && !windows.some(([start, end]) => target >= start && target <= end)) {
      target = windows.flat().reduce((nearest, boundary) => Math.abs(boundary - target) < Math.abs(nearest - target) ? boundary : nearest);
    }
    const previous = pendingSeek;
    try {
      // Assigning the current time again may not emit seeking/seeked. Do not
      // leave a pending target that would freeze the clock at the boundary.
      const unchanged = !video.seeking && Math.abs(finite(video.currentTime) - target) < 0.001;
      pendingSeek = unchanged ? null : target;
      if (!unchanged) video.currentTime = target;
      updateTime();
      video.dispatchEvent(new CustomEvent('lumiere:seek', {detail: {position: target}}));
      tell(`Đã tua đến ${time(target)}.`);
      return true;
    } catch (_) {
      pendingSeek = previous;
      updateTime();
      tell('Chưa thể tua ở vị trí này. Hãy đợi video tải xong rồi thử lại.');
      return false;
    }
  };
  const skip = amount => seekTo((pendingSeek === null ? finite(video.currentTime) : pendingSeek) + amount);
  const togglePlay = async () => {
    if (video.paused) {try {await video.play();} catch (_) {tell('Chưa thể phát. Hãy thử lại khi video tải xong.');}}
    else video.pause();
  };
  const positionCues = element => {
    // Keep native WebVTT captions above the custom controls, including while
    // paused. Uploaded tracks are normalized without authored cue placement.
    const line = wrap.clientWidth > 0 && wrap.clientWidth <= 600 ? -2 : -5;
    for (const cue of Array.from(element.track.cues || [])) {cue.snapToLines = true; cue.line = line;}
  };
  const renderCaptions = () => {
    if (!captionDisplay || !captionText) return;
    const element = selectedSubtitle === 'off' ? null : subtitleElements[Number(selectedSubtitle)];
    const text = Array.from(element?.track.activeCues || []).map(cue => cue.getCueAsHTML?.().textContent ?? cue.text ?? '').join('\n');
    captionText.textContent = text;
    captionDisplay.hidden = !text || nativeFullscreen;
  };
  const applySubtitles = () => {
    subtitleElements = Array.from(video.querySelectorAll('track[data-subtitle]'));
    for (const track of subtitleElements) {
      if (boundSubtitleElements.has(track)) continue;
      boundSubtitleElements.add(track);
      track.addEventListener('load', () => {positionCues(track); renderCaptions();});
      track.track.addEventListener?.('cuechange', () => {positionCues(track); renderCaptions();});
      track.addEventListener('error', () => {
        if (subtitleElements[Number(selectedSubtitle)] === track) tell('Không tải được phụ đề đã chọn. Bạn có thể tắt hoặc chọn ngôn ngữ khác.');
      });
    }
    const selected = selectedSubtitle === 'off' ? -1 : Number(selectedSubtitle);
    subtitleElements.forEach((element, index) => {element.track.mode = index === selected ? (captionDisplay && !nativeFullscreen ? 'hidden' : 'showing') : 'disabled'; positionCues(element);});
    if (subtitles) subtitles.value = selectedSubtitle;
    renderCaptions();
  };
  if (subtitles) {
    subtitles.value = 'off';
    subtitles.addEventListener('change', () => {
      const value = subtitles.value;
      selectedSubtitle = value === 'off' || (/^\d+$/.test(value) && Number(value) < subtitleElements.length) ? value : 'off';
      applySubtitles();
    });
    video.textTracks.addEventListener('addtrack', applySubtitles);
    video.addEventListener('lumiere:captions-changed', event => {
      subtitleElements = Array.from(video.querySelectorAll('track[data-subtitle]'));
      const selected = String(event.detail?.selected ?? selectedSubtitle);
      selectedSubtitle = /^\d+$/.test(selected) && Number(selected) < subtitleElements.length ? selected : 'off';
      applySubtitles();
    });
    applySubtitles();
    window.addEventListener('resize', applySubtitles);
    video.addEventListener('webkitbeginfullscreen', () => {nativeFullscreen = true; applySubtitles();});
    video.addEventListener('webkitendfullscreen', () => {nativeFullscreen = false; applySubtitles();});
  }
  for (const button of wrap.querySelectorAll('[data-player-action]')) {
    if (['back', 'forward'].includes(button.dataset.playerAction)) button.disabled = !canSeek;
    button.addEventListener('click', async () => {
      switch (button.dataset.playerAction) {
        case 'play': await togglePlay(); break;
        case 'back': skip(-10); break;
        case 'forward': skip(10); break;
        case 'mute': video.muted = !video.muted; break;
        case 'fullscreen':
          try {if (document.fullscreenElement) await document.exitFullscreen(); else if (wrap.requestFullscreen) await wrap.requestFullscreen(); else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen();}
          catch (_) {tell('Không thể mở toàn màn hình trong trình duyệt này.');}
          break;
      }
    });
  }
  range.addEventListener('input', () => {seekTo(Number(range.value));});
  wrap.addEventListener('keydown', event => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    if (event.target.closest('input, select, textarea, [contenteditable="true"], [role="textbox"], [data-caption-panel]')) return;
    if (skip(event.key === 'ArrowLeft' ? -10 : 10)) event.preventDefault();
  });
  if (volume) volume.addEventListener('input', () => {video.volume = Number(volume.value); video.muted = video.volume === 0;});
  video.addEventListener('volumechange', () => {
    if (volume) volume.value = video.muted ? 0 : video.volume;
    if (muteButton) muteButton.setAttribute('aria-label', video.muted ? 'Bật tiếng' : 'Tắt tiếng');
  });
  const ready = () => {
    controls.hidden = false;
    if (center) center.hidden = false;
    video.controls = false;
    const quality = wrap.querySelector('[data-player-quality]');
    if (quality) quality.textContent = video.videoHeight ? `${video.videoHeight}p` : '';
    updateTime(); updatePlaying(); applySubtitles();
  };
  video.addEventListener('loadedmetadata', ready);
  video.addEventListener('durationchange', updateTime);
  if (video.readyState >= 1) ready();
  video.addEventListener('timeupdate', () => {
    updateTime();
    for (const element of subtitleElements) if (element.track.mode === 'showing') positionCues(element);
    renderCaptions();
  });
  video.addEventListener('seeked', () => {pendingSeek = null; updateTime(); updatePlaying();});
  video.addEventListener('emptied', () => {pendingSeek = null; controls.hidden = true; if (center) center.hidden = true; updateTime();});
  video.addEventListener('play', updatePlaying);
  video.addEventListener('pause', updatePlaying);
  video.addEventListener('ended', updatePlaying);
  video.addEventListener('error', () => {pendingSeek = null; video.controls = true; controls.hidden = true; if (center) center.hidden = true;});
  document.addEventListener('fullscreenchange', () => {if (fullscreenButton) fullscreenButton.setAttribute('aria-label', document.fullscreenElement ? 'Thoát toàn màn hình' : 'Toàn màn hình'); applySubtitles();});
})();
