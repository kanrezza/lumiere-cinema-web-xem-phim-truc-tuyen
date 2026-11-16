'use strict';

(function initVoice(event) {
  if (!event && document.readyState !== 'complete') {
    document.addEventListener('DOMContentLoaded', initVoice, {once: true});
    return;
  }
  const room = document.getElementById('room');
  if (!room?.dataset.voice || !room.dataset.voiceAction) return;

  const joinButton = room.querySelector('[data-voice-join]');
  const micButton = room.querySelector('[data-voice-mic]');
  const playButton = room.querySelector('[data-voice-play]');
  const status = room.querySelector('[data-voice-status]');
  const audioArea = room.querySelector('[data-voice-audio]');
  if (!joinButton || !micButton || !status || !audioArea) return;

  const selfId = room.dataset.user;
  const isHost = room.dataset.host === 'true';
  const canListen = typeof window.RTCPeerConnection === 'function';
  const canSpeak = Boolean(window.isSecureContext && navigator.mediaDevices?.getUserMedia);
  const vueVoice = room.dataset.vueVoice === 'true';
  const members = new Map();
  const peers = new Map();
  const retries = new Map();
  const muteRequests = new Set();
  const leaseLimit = 6000;
  let session = '';
  let latestSignal = '0';
  let iceServers = [];
  let selfMuted = false;
  let microphone = null;
  let pendingMicrophone = null;
  let joinBusy = false;
  let micBusy = false;
  let micChange = 0;
  let revision = 0;
  let lastSnapshot = 0;
  let leaseTimer;
  let pollTimer;
  let polling = false;
  let refreshRequested = false;
  let closed = false;
  let suspended = false;
  let recovering = false;
  let notice = '';

  function setText(element, text) {
    if (element.textContent !== text) element.textContent = text;
  }

  function setButton(button, label, active) {
    setText(button.querySelector('[data-voice-label]') || button, label);
    button.dataset.active = String(active);
    button.setAttribute('aria-pressed', String(active));
  }

  const joinDisabled = () => closed || joinBusy || !canListen;
  const micDisabled = () => closed || !session || selfMuted || micBusy || !canSpeak || recovering;

  function render() {
    let message = notice;
    if (!message) {
      if (closed) message = 'Đã ngắt trò chuyện thoại.';
      else if (recovering) message = 'Đang kết nối lại trò chuyện thoại…';
      else if (!canListen) message = 'Trình duyệt này chưa hỗ trợ trò chuyện thoại.';
      else if (!session) message = 'Tham gia thoại để nghe mọi người. Mic mặc định tắt.';
      else if (selfMuted) message = 'Chủ phòng đã tắt mic của bạn. Bạn vẫn nghe được mọi người.';
      else if (retries.size) message = 'Đang thử lại kết nối thoại với thành viên.';
      else if (microphone) message = 'Mic đang bật.';
      else if (!canSpeak) message = 'Bạn đang nghe. Bật mic cần trình duyệt hỗ trợ và kết nối HTTPS.';
      else message = 'Đang nghe phòng thoại. Mic đang tắt.';
    }
    const micState = selfMuted ? 'muted' : microphone ? 'live' : 'off';
    const showAudio = [...peers.values()].some(peer => peer.blocked && !peer.audio?.muted);
    if (vueVoice) {
      room.dispatchEvent(new CustomEvent('lumiere:voice-state', {detail: {
        listening: Boolean(session), microphone: Boolean(microphone), joinDisabled: joinDisabled(),
        micDisabled: micDisabled(), micState, showAudio, message,
      }}));
      return;
    }
    setButton(joinButton, session ? 'Rời thoại' : 'Tham gia thoại', Boolean(session));
    setButton(micButton, microphone ? 'Tắt mic' : 'Bật mic', Boolean(microphone));
    joinButton.disabled = joinDisabled();
    micButton.disabled = micDisabled();
    micButton.dataset.state = micState;
    if (playButton) playButton.hidden = !showAudio;
    setText(status, message);
  }

  function renderMembers() {
    for (const row of room.querySelectorAll('[data-member-id]')) {
      const id = row.dataset.memberId;
      const member = members.get(id);
      const state = row.querySelector('[data-member-voice-state]');
      if (state) {
        let text = 'Chưa vào thoại';
        let kind = 'off';
        if (member?.host_muted) { text = 'Chủ phòng đã tắt mic'; kind = 'muted'; }
        else if (member?.voice_session && member.mic_on) { text = 'Mic đang bật'; kind = 'speaking'; }
        else if (member?.voice_session) { text = 'Đang nghe'; kind = 'listening'; }
        state.dataset.state = kind;
        setText(state, text);
      }
      const actions = row.querySelector('[data-member-actions]');
      if (!actions || !isHost || id === selfId) continue;
      let button = actions.querySelector('[data-voice-mute]');
      if (!button) {
        button = document.createElement('button');
        button.type = 'button';
        button.className = 'room-mic-action';
        button.dataset.voiceMute = id;
        actions.prepend(button);
      }
      const muted = Boolean(member?.host_muted);
      const label = muted ? 'Cho phép bật mic' : 'Tắt mic';
      setText(button, label);
      button.setAttribute('aria-label', `${label} cho ${row.dataset.memberName}`);
      button.dataset.muted = String(muted);
      button.disabled = closed || !member || muteRequests.has(id);
    }
  }

  async function voiceRequest(url, options = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4500);
    try {
      const response = await fetch(url, {credentials: 'same-origin', cache: 'no-store', ...options, signal: controller.signal});
      if (response.redirected || !response.ok) {
        const error = new Error('Không kết nối được với phòng thoại.');
        error.status = response.redirected ? 403 : response.status;
        throw error;
      }
      return await response.json();
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function post(action, fields = {}) {
    return voiceRequest(room.dataset.voiceAction, {
      method: 'POST',
      headers: {'Content-Type': 'application/x-www-form-urlencoded', 'X-CSRFToken': csrfToken()},
      body: new URLSearchParams({action, ...fields}),
    });
  }

  function clearMicrophone() {
    micChange += 1;
    micBusy = false;
    const wasOn = Boolean(microphone);
    microphone?.stop();
    pendingMicrophone?.stop();
    microphone = null;
    pendingMicrophone = null;
    for (const peer of peers.values()) peer.sender?.replaceTrack(null).catch(() => {});
    return wasOn;
  }

  function closePeer(peer) {
    if (peers.get(peer.id) === peer) peers.delete(peer.id);
    window.clearTimeout(peer.deadline);
    peer.connection.close();
    if (peer.audio) {
      peer.audio.pause();
      peer.audio.srcObject = null;
      peer.audio.remove();
    }
  }

  function stopSession() {
    const oldSession = session;
    session = '';
    revision += 1;
    latestSignal = '0';
    window.clearTimeout(leaseTimer);
    clearMicrophone();
    for (const peer of peers.values()) closePeer(peer);
    retries.clear();
    return oldSession;
  }

  function disconnect() {
    closed = true;
    notice = '';
    stopSession();
    window.clearTimeout(pollTimer);
    renderMembers();
    render();
  }

  function schedulePoll(delay = 0) {
    if (closed || suspended) return;
    if (polling) { refreshRequested = true; return; }
    window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(poll, delay);
  }

  function checkLease() {
    if (!session || Date.now() - lastSnapshot < leaseLimit || recovering) return;
    recovering = true;
    notice = '';
    if (clearMicrophone()) post('mic', {session, enabled: 'false'}).catch(() => {});
    for (const peer of peers.values()) closePeer(peer);
    render();
  }

  function renewLease() {
    lastSnapshot = Date.now();
    window.clearTimeout(leaseTimer);
    if (session) leaseTimer = window.setTimeout(checkLease, leaseLimit);
  }

  function playPeerAudio(peer) {
    if (!peer.audio || peer.audio.muted || !peerCurrent(peer)) return;
    peer.audio.play().then(() => {
      peer.blocked = false;
      render();
    }).catch(() => {
      peer.blocked = true;
      render();
    });
  }

  function updatePeerAudio(peer) {
    if (!peer.audio) return;
    const member = members.get(peer.id);
    const audible = Boolean(session && !recovering && member?.voice_session === peer.session && member.mic_on && !member.host_muted);
    const wasMuted = peer.audio.muted;
    peer.audio.muted = !audible;
    if (audible && wasMuted) playPeerAudio(peer);
  }

  function offeredFirst(id) {
    return BigInt(selfId) < BigInt(id);
  }

  function peerCurrent(peer) {
    return Boolean(session && !recovering && peers.get(peer.id) === peer && members.get(peer.id)?.voice_session === peer.session);
  }

  function failPeer(peer) {
    if (!peerCurrent(peer)) return;
    const previous = retries.get(peer.id) || {attempt: 0};
    const attempt = Math.min(previous.attempt + 1, 5);
    retries.set(peer.id, {attempt, after: Date.now() + Math.min(1000 * 2 ** attempt, 15000)});
    closePeer(peer);
    render();
  }

  function createPeer(member, negotiation) {
    const connection = new RTCPeerConnection({iceServers});
    const peer = {id: String(member.user_id), session: member.voice_session, negotiation, connection};
    peers.set(peer.id, peer);
    peer.deadline = window.setTimeout(() => failPeer(peer), 22000);
    connection.addEventListener('connectionstatechange', () => {
      if (connection.connectionState === 'failed') failPeer(peer);
      if (connection.connectionState === 'connected') {
        window.clearTimeout(peer.deadline);
        retries.delete(peer.id);
      }
      if (connection.connectionState === 'disconnected') {
        window.clearTimeout(peer.deadline);
        peer.deadline = window.setTimeout(() => failPeer(peer), 7000);
      }
    });
    connection.addEventListener('track', ({track}) => {
      if (track.kind !== 'audio' || !peerCurrent(peer)) return;
      if (!peer.audio) {
        peer.audio = document.createElement('audio');
        peer.audio.muted = true;
        peer.audio.setAttribute('playsinline', '');
        audioArea.append(peer.audio);
      }
      peer.audio.srcObject = new MediaStream([track]);
      updatePeerAudio(peer);
    });
    return peer;
  }

  async function attachSender(peer, transceiver) {
    transceiver.direction = 'sendrecv';
    peer.sender = transceiver.sender;
    await peer.sender.replaceTrack(microphone);
  }

  function waitForIce(connection) {
    if (connection.iceGatheringState === 'complete') return Promise.resolve();
    return new Promise(resolve => {
      const finish = () => {
        window.clearTimeout(timer);
        connection.removeEventListener('icegatheringstatechange', check);
        resolve();
      };
      const check = () => { if (connection.iceGatheringState === 'complete') finish(); };
      const timer = window.setTimeout(finish, 4500);
      connection.addEventListener('icegatheringstatechange', check);
    });
  }

  async function sendDescription(peer, type) {
    await waitForIce(peer.connection);
    if (!peerCurrent(peer) || !peer.connection.localDescription) return;
    await post('signal', {session, user: peer.id, target_session: peer.session, type,
      payload: JSON.stringify({sdp: peer.connection.localDescription.sdp, negotiation: peer.negotiation})});
  }

  async function makeOffer(member) {
    const peer = createPeer(member, crypto.randomUUID());
    try {
      await attachSender(peer, peer.connection.addTransceiver('audio'));
      await peer.connection.setLocalDescription(await peer.connection.createOffer());
      await sendDescription(peer, 'offer');
    } catch { failPeer(peer); }
  }

  async function receiveSignal(signal) {
    const id = String(signal.from_user_id);
    const member = members.get(id);
    const {type, payload} = signal;
    if (id === selfId || !member?.voice_session || member.voice_session !== signal.from_session) return;
    if (typeof payload?.sdp !== 'string' || typeof payload.negotiation !== 'string') return;
    const media = [...payload.sdp.matchAll(/^m=(\S+)/gm)];
    if (media.length !== 1 || media[0][1] !== 'audio') return;
    let peer = peers.get(id);
    if (type === 'offer' && !offeredFirst(id)) {
      if (peer?.negotiation === payload.negotiation) return;
      if (peer) closePeer(peer);
      peer = createPeer(member, payload.negotiation);
      try {
        await peer.connection.setRemoteDescription({type, sdp: payload.sdp});
        if (!peerCurrent(peer)) return;
        await attachSender(peer, peer.connection.getTransceivers()[0]);
        await peer.connection.setLocalDescription(await peer.connection.createAnswer());
        await sendDescription(peer, 'answer');
      } catch { failPeer(peer); }
    } else if (type === 'answer' && offeredFirst(id) && peer?.negotiation === payload.negotiation && peerCurrent(peer)) {
      try { await peer.connection.setRemoteDescription({type, sdp: payload.sdp}); }
      catch { failPeer(peer); }
    }
  }

  function reconcilePeers() {
    for (const peer of peers.values()) {
      if (!peerCurrent(peer)) closePeer(peer);
      else updatePeerAudio(peer);
    }
    for (const id of retries.keys()) {
      if (!members.get(id)?.voice_session) retries.delete(id);
    }
    if (!session || recovering) return;
    for (const [id, member] of members) {
      if (id !== selfId && member.voice_session && !peers.has(id) && offeredFirst(id) && (retries.get(id)?.after || 0) <= Date.now()) {
        makeOffer(member).catch(() => {});
      }
    }
  }

  async function poll() {
    if (closed || suspended) return;
    polling = true;
    const observed = revision;
    checkLease();
    try {
      const url = new URL(room.dataset.voice, location.href);
      if (session) {
        url.searchParams.set('session', session);
        url.searchParams.set('after', latestSignal);
      }
      const data = await voiceRequest(url);
      if (closed || suspended || observed !== revision) return;
      renewLease();
      recovering = false;
      if (session && data.self.voice_session !== session) {
        stopSession();
        notice = 'Phiên thoại đã kết thúc. Chọn Tham gia thoại để kết nối lại.';
      }
      selfMuted = data.self.host_muted;
      if (selfMuted) {
        clearMicrophone();
        if (session) notice = '';
      }
      iceServers = data.ice_servers;
      members.clear();
      for (const member of [data.self, ...data.peers]) members.set(String(member.user_id), member);
      reconcilePeers();
      if (session) {
        for (const signal of data.signals) {
          latestSignal = String(signal.id);
          receiveSignal(signal).catch(() => {});
        }
      }
      renderMembers();
      render();
    } catch (error) {
      if ([403, 404, 409].includes(error.status)) disconnect();
      else checkLease();
    } finally {
      polling = false;
      const delay = refreshRequested ? 0 : session ? 1000 : 2500;
      refreshRequested = false;
      schedulePoll(delay);
    }
  }

  joinButton.addEventListener('click', async () => {
    if (joinDisabled()) return;
    joinBusy = true;
    notice = '';
    render();
    try {
      if (session) {
        const oldSession = stopSession();
        render();
        await post('leave', {session: oldSession}).catch(() => {});
      } else {
        session = (await post('join')).session;
        if (closed || suspended) {
          await post('leave', {session: stopSession()}).catch(() => {});
          return;
        }
        latestSignal = '0';
        renewLease();
        recovering = false;
        revision += 1;
      }
    } catch {
      notice = 'Chưa vào được phòng thoại. Hãy thử lại.';
    } finally {
      joinBusy = false;
      render();
      schedulePoll();
    }
  });

  micButton.addEventListener('click', async () => {
    if (micDisabled()) return;
    notice = '';
    const activeSession = session;
    if (microphone) {
      clearMicrophone();
      micBusy = true;
      render();
      try { await post('mic', {session, enabled: 'false'}); } catch { notice = 'Mic đã tắt trên thiết bị.'; }
      micBusy = false;
    } else {
      const change = ++micChange;
      micBusy = true;
      render();
      let track;
      try {
        const stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true}});
        [track] = stream.getAudioTracks();
        if (activeSession !== session || change !== micChange) return void track?.stop();
        if (!track || track.readyState !== 'live') throw new Error('no microphone track');
        track.enabled = false;
        pendingMicrophone = track;
        await post('mic', {session, enabled: 'true'});
        if (activeSession !== session || change !== micChange || selfMuted || recovering || track.readyState !== 'live') {
          track.stop();
          if (activeSession === session && !selfMuted) post('mic', {session, enabled: 'false'}).catch(() => {});
          return;
        }
        microphone = track;
        microphone.enabled = true;
        for (const peer of peers.values()) peer.sender?.replaceTrack(microphone).catch(() => failPeer(peer));
        microphone.addEventListener('ended', () => {
          if (microphone !== track) return;
          clearMicrophone();
          notice = 'Mic đã ngắt kết nối.';
          post('mic', {session, enabled: 'false'}).catch(() => {});
          render();
          schedulePoll();
        }, {once: true});
      } catch (error) {
        track?.stop();
        if (activeSession !== session || change !== micChange) return;
        notice = error.name === 'NotAllowedError' ? 'Hãy cấp quyền dùng mic trong trình duyệt.'
          : error.name === 'NotFoundError' ? 'Chưa tìm thấy mic trên thiết bị.'
          : 'Chưa bật được mic. Hãy kiểm tra thiết bị và thử lại.';
      } finally {
        if (pendingMicrophone === track) pendingMicrophone = null;
        if (change === micChange) micBusy = false;
      }
    }
    revision += 1;
    render();
    schedulePoll();
  });

  room.addEventListener('click', async event => {
    const button = event.target.closest?.('[data-voice-mute]');
    if (!isHost || !button || button.disabled) return;
    const id = button.dataset.voiceMute;
    const member = members.get(id);
    if (!member) return;
    const muted = !member.host_muted;
    muteRequests.add(id);
    renderMembers();
    try {
      await post('mute', {user: id, muted: String(muted)});
      revision += 1;
      const current = members.get(id);
      if (current) {
        current.host_muted = muted;
        current.mic_on = false;
      }
      notice = '';
      reconcilePeers();
    } catch { notice = 'Chưa cập nhật được mic của thành viên.'; }
    finally {
      muteRequests.delete(id);
      renderMembers();
      render();
      schedulePoll();
    }
  });

  playButton?.addEventListener('click', () => {
    for (const peer of peers.values()) playPeerAudio(peer);
  });
  room.addEventListener('lumiere:room-members', renderMembers);
  document.addEventListener('lumiere:stop', disconnect);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      checkLease();
      schedulePoll();
    }
  });
  window.addEventListener('pagehide', () => {
    suspended = true;
    const oldSession = stopSession();
    window.clearTimeout(pollTimer);
    if (oldSession) navigator.sendBeacon?.(room.dataset.voiceAction, new URLSearchParams({action: 'leave', session: oldSession, csrfmiddlewaretoken: csrfToken()}));
  });
  window.addEventListener('pageshow', () => {
    if (!suspended) return;
    suspended = false;
    render();
    schedulePoll();
  });
  render();
  schedulePoll();
})();
