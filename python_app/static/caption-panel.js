'use strict';
(() => {
  const video = document.getElementById('player');
  if (!video) return;
  const wrap = video.closest('.player-wrap');
  const panel = wrap?.querySelector('[data-caption-panel]');
  const toggle = wrap?.querySelector('[data-caption-toggle]');
  if (!panel || !toggle) return;
  const closeButton = panel.querySelector('[data-caption-close]');
  const selection = panel.querySelector('.player-subtitles');
  const source = panel.querySelector('[data-caption-source]');
  const target = panel.querySelector('[data-caption-target]');
  const translateForm = panel.querySelector('[data-caption-form]');
  const translateButton = panel.querySelector('[data-caption-submit]');
  const translateStatus = panel.querySelector('[data-caption-status]');
  const generateForm = panel.querySelector('[data-caption-generate]');
  const speechLanguage = panel.querySelector('[data-caption-speech-language]');
  const generateButton = panel.querySelector('[data-caption-generate-submit]');
  const generateStatus = panel.querySelector('[data-caption-generate-status]');
  const MAX_POLLS = 120;
  const POLL_INTERVAL = 1500;
  const states = [];
  let stopped = false;

  const setStatus = (node, text, error = false) => {
    node.textContent = text;
    node.dataset.error = error ? 'true' : 'false';
  };
  const safeUrl = value => {
    const url = new URL(value, window.location.href);
    if (url.origin !== window.location.origin || !url.pathname.startsWith(panel.dataset.captionScope)) throw new Error('Địa chỉ phụ đề không hợp lệ. Hãy tải lại trang.');
    return url.href;
  };
  const showPanel = () => {panel.hidden = false; toggle.setAttribute('aria-expanded', 'true'); closeButton.focus();};
  const closePanel = (restoreFocus = true) => {panel.hidden = true; toggle.setAttribute('aria-expanded', 'false'); if (restoreFocus) toggle.focus();};
  toggle.addEventListener('click', () => {if (panel.hidden) showPanel(); else closePanel();});
  closeButton.addEventListener('click', () => closePanel());
  document.addEventListener('keydown', event => {if (!panel.hidden && event.key === 'Escape') {event.preventDefault(); closePanel();}});
  document.addEventListener('click', event => {if (!panel.hidden && !panel.contains(event.target) && !toggle.contains(event.target)) closePanel(false);});
  document.addEventListener('focusin', event => {if (!panel.hidden && !panel.contains(event.target) && !toggle.contains(event.target)) closePanel(false);});

  const refreshSelection = selected => {
    selection.disabled = video.querySelectorAll('track[data-subtitle]').length === 0;
    video.dispatchEvent(new CustomEvent('lumiere:captions-changed', {detail: {selected: String(selected)}}));
  };
  const sourceOption = () => Array.from(source.options).find(option => option.value === source.value);
  const updateTranslateButton = () => {translateButton.disabled = !source.value || states.some(state => state.button === translateButton && state.busy);};
  const chooseDifferentTarget = () => {
    const language = (sourceOption()?.dataset.language || '').split('-')[0];
    if (target.value === language) target.value = language === 'vi' ? 'en' : 'vi';
  };
  chooseDifferentTarget();

  const removeTranslated = () => {
    const translated = Array.from(video.querySelectorAll('track[data-translated]'));
    if (!translated.length) return;
    const current = Array.from(video.querySelectorAll('track[data-subtitle]'))[Number(selection.value)];
    for (const element of translated) {element.track.mode = 'disabled'; element.remove();}
    const off = document.createElement('option'); off.value = 'off'; off.textContent = 'Tắt phụ đề';
    selection.replaceChildren(off);
    const remaining = Array.from(video.querySelectorAll('track[data-subtitle]'));
    remaining.forEach((element, index) => {const option = document.createElement('option'); option.value = String(index); option.textContent = element.label; selection.append(option);});
    const selected = remaining.indexOf(current);
    selection.value = selected < 0 ? 'off' : String(selected);
    refreshSelection(selection.value);
  };
  const addTrack = ({url, language, label, id, translateUrl, translated = false}) => {
    const trackUrl = safeUrl(url);
    const translationUrl = translateUrl ? safeUrl(translateUrl) : '';
    if (typeof language !== 'string' || !/^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3}$/.test(language)) throw new Error('Ngôn ngữ phụ đề trả về không hợp lệ.');
    if (typeof label !== 'string' || !label.trim()) throw new Error('Tên phụ đề trả về không hợp lệ.');
    if (id && source.value !== String(id)) invalidateTranslation();
    if (translated) removeTranslated();
    let element = id ? Array.from(video.querySelectorAll('track[data-subtitle]')).find(track => track.dataset.subtitleId === String(id)) : null;
    if (!element) {
      element = document.createElement('track');
      element.dataset.subtitle = '';
      if (id) element.dataset.subtitleId = String(id);
      if (translated) element.dataset.translated = 'true';
      element.kind = 'subtitles'; element.srclang = language; element.label = label.slice(0, 120); element.src = trackUrl;
      video.append(element);
      const option = document.createElement('option');
      option.value = String(Array.from(video.querySelectorAll('track[data-subtitle]')).indexOf(element));
      option.textContent = label.slice(0, 120);
      if (translated) option.dataset.translated = 'true';
      selection.append(option);
    }
    const index = Array.from(video.querySelectorAll('track[data-subtitle]')).indexOf(element);
    if (id && translateUrl) {
      let option = Array.from(source.options).find(item => item.value === String(id));
      if (!option) {
        option = document.createElement('option'); option.value = String(id); option.textContent = label.slice(0, 120);
        option.dataset.language = language; option.dataset.translateUrl = translationUrl; source.append(option);
      }
      source.disabled = false; source.value = String(id);
      const empty = panel.querySelector('[data-caption-empty]'); if (empty) empty.hidden = true;
      chooseDifferentTarget(); updateTranslateButton();
    }
    selection.disabled = false; selection.value = String(index); refreshSelection(index);
  };
  const stateFor = (button, status) => {const state = {button, status, busy: false, generation: 0, controller: null, timer: null}; states.push(state); return state;};
  const cancel = state => {
    state.generation++; state.busy = false;
    if (state.timer !== null) clearTimeout(state.timer);
    state.timer = null; state.controller?.abort(); state.controller = null;
    state.button.disabled = false;
  };
  const request = async (url, state, data) => {
    state.controller = new AbortController();
    const controller = state.controller;
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(safeUrl(url), {
        method: data ? 'POST' : 'GET', credentials: 'same-origin', redirect: 'error', signal: controller.signal,
        headers: data ? {'X-CSRFToken': window.csrfToken?.() || '', 'Content-Type': 'application/x-www-form-urlencoded'} : {},
        body: data ? new URLSearchParams(data) : undefined,
      });
      let payload;
      try {payload = await response.json();} catch (_) {throw new Error('Không đọc được phản hồi. Hãy thử lại sau.');}
      if (!response.ok) throw new Error(typeof payload.error === 'string' ? payload.error : 'Chưa thể xử lý phụ đề. Kiểm tra quyền xem và thử lại.');
      return payload;
    } finally {clearTimeout(timeout); if (state.controller === controller) state.controller = null;}
  };
  const runJob = async (state, url, data, ready, messages) => {
    cancel(state);
    const generation = state.generation;
    state.busy = true; state.button.disabled = true;
    let polls = 0;
    setStatus(state.status, messages.pending);
    const active = () => !stopped && generation === state.generation;
    const fail = error => {
      if (!active()) return;
      state.busy = false; state.button.disabled = false; updateTranslateButton();
      const message = error.name === 'AbortError' ? 'Yêu cầu mất quá nhiều thời gian. Bạn có thể thử lại.' : error.name === 'TypeError' ? 'Không kết nối được máy chủ. Hãy thử lại.' : error.message;
      setStatus(state.status, message, true);
    };
    const handle = async job => {
      if (!active()) return;
      if (job.status === 'ready') {
        ready(job);
        state.busy = false; state.button.disabled = false; updateTranslateButton();
        setStatus(state.status, messages.ready);
        return;
      }
      if (job.status === 'failed') throw new Error(job.error || 'Không xử lý được phụ đề. Bạn có thể thử lại.');
      if (!['pending', 'processing'].includes(job.status)) throw new Error('Trạng thái phụ đề không hợp lệ.');
      if (++polls > MAX_POLLS) {
        state.busy = false; state.button.disabled = false; updateTranslateButton();
        setStatus(state.status, 'Tác vụ vẫn đang xử lý. Bạn có thể tiếp tục xem và bấm lại để kiểm tra sau.');
        return;
      }
      const statusUrl = safeUrl(job.status_url);
      setStatus(state.status, messages.pending);
      state.timer = setTimeout(async () => {
        state.timer = null;
        try {await handle(await request(statusUrl, state));} catch (error) {fail(error);}
      }, POLL_INTERVAL);
    };
    try {await handle(await request(url, state, data));} catch (error) {fail(error);}
  };
  const translationState = stateFor(translateButton, translateStatus);
  const generationState = stateFor(generateButton, generateStatus);
  const invalidateTranslation = () => {cancel(translationState); removeTranslated(); setStatus(translateStatus, ''); updateTranslateButton();};
  source.addEventListener('change', () => {invalidateTranslation(); chooseDifferentTarget();});
  target.addEventListener('change', invalidateTranslation);
  translateForm.addEventListener('submit', event => {
    event.preventDefault();
    const option = sourceOption();
    if (!option?.dataset.translateUrl) {setStatus(translateStatus, 'Cần phụ đề gốc trước khi dịch.', true); return;}
    if (option.dataset.language.split('-')[0] === target.value) {setStatus(translateStatus, 'Hãy chọn ngôn ngữ khác với phụ đề gốc.', true); return;}
    runJob(translationState, option.dataset.translateUrl, {target: target.value, retry: '1'}, job => {
      if (job.target !== target.value || !job.track_url) throw new Error('Bản dịch trả về không khớp ngôn ngữ đã chọn.');
      addTrack({url: job.track_url, language: job.target, label: job.label, translated: true});
    }, {pending: 'Đang dịch phụ đề… Bạn vẫn có thể tiếp tục xem.', ready: 'Đã bật phụ đề dịch tự động.'});
  });
  generateForm.addEventListener('submit', event => {
    event.preventDefault();
    runJob(generationState, generateForm.getAttribute('action'), {language: speechLanguage.value, retry: '1'}, job => {
      const subtitle = job.subtitle;
      if (!subtitle || !Number.isInteger(subtitle.id) || subtitle.id <= 0) throw new Error('Chưa tìm thấy lời thoại để tạo phụ đề.');
      addTrack({url: subtitle.url, language: subtitle.language, label: subtitle.label, id: subtitle.id, translateUrl: subtitle.translate_url});
    }, {pending: 'Đang tạo phụ đề từ lời thoại… Bạn có thể tiếp tục xem.', ready: 'Đã tạo và bật phụ đề. Bạn có thể dịch sang ngôn ngữ khác.'});
  });
  speechLanguage.addEventListener('change', () => {cancel(generationState); setStatus(generateStatus, '');});
  window.addEventListener('pagehide', () => {stopped = true; for (const state of states) cancel(state);});
  updateTranslateButton();
})();
