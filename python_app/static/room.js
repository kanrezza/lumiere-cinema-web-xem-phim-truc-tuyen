'use strict';
(function init(event) {
  if (!event && (document.readyState === 'loading' || document.readyState === 'interactive')) {
    document.addEventListener('DOMContentLoaded', init, {once: true});
    return;
  }
  const room = document.getElementById('room');
  if (!room) return;

  const video = document.getElementById('player');
  const status = document.getElementById('room-status');
  const invite = document.getElementById('copy-invite');
  const close = document.getElementById('close-room');
  const chatForm = document.getElementById('chat-form');
  const chatList = document.getElementById('chat-messages');
  const members = document.getElementById('members');
  const roomQuery = selector => room.querySelector?.(selector);
  const memberCount = roomQuery('[data-room-member-count]');
  const emptyChat = roomQuery('[data-room-chat-empty]');
  const vuePresentation = room.dataset.vueRoom === 'true';
  const isHost = room.dataset.host === 'true';
  const currentUserId = room.dataset.user;
  const hostId = room.dataset.hostUser || (isHost ? currentUserId : '');
  let stopped = false;
  let lastChat = 0;
  let sendingChat = false;
  let reconnecting = false;

  invite.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      status.textContent = 'Đã sao chép liên kết mời.';
    } catch {
      status.textContent = 'Liên kết mời ' + location.href;
    }
  });

  async function send(data) {
    try {
      return await postForm(room.dataset.state, data);
    } catch (error) {
      status.textContent = error.message;
      throw error;
    }
  }

  function stopRoom(message) {
    stopped = true;
    for (const control of chatForm.elements) control.disabled = true;
    if (close) close.disabled = true;
    document.dispatchEvent(new Event('lumiere:stop'));
    status.textContent = message;
  }

  if (isHost) {
    // Serialize host updates so a slower old seek cannot arrive after a new one.
    let pendingSync = null;
    let sendingSync = false;
    const sync = async () => {
      if (stopped || video.dataset.loading === 'true' || !Number.isFinite(video.duration) || !Number.isFinite(video.currentTime)) return;
      pendingSync = {action: 'sync', position: video.currentTime, playing: !video.paused && !video.ended};
      if (sendingSync) return;
      sendingSync = true;
      try {
        while (pendingSync && !stopped) {
          const next = pendingSync;
          pendingSync = null;
          try { await send(next); } catch { /* send reports the failure. */ }
        }
      } finally {
        sendingSync = false;
      }
    };
    for (const event of ['play', 'pause', 'seeked', 'ended']) video.addEventListener(event, sync);
    setInterval(sync, 6000);
    close.addEventListener('click', async () => {
      if (stopped || !confirm('Kết thúc phòng cho tất cả thành viên?')) return;
      close.disabled = true;
      try {
        await send({action: 'close'});
        stopRoom('Phòng đã đóng.');
        location.href = '/library/';
      } catch {
        close.disabled = false;
      }
    });
  }

  function showMessages(messages, ownMessage = false) {
    if (vuePresentation) {
      const added = messages.filter(message => message.id > lastChat);
      if (added.length) {
        lastChat = added[added.length - 1].id;
        room.dispatchEvent(new CustomEvent('lumiere:chat-update', {detail: {added, own: ownMessage}}));
      }
      return;
    }
    const nearBottom = chatList.scrollHeight - chatList.scrollTop - chatList.clientHeight < 60;
    let added = false;
    for (const message of messages) {
      if (message.id <= lastChat) continue;
      const row = document.createElement('p');
      row.className = 'room-chat-message';
      if (String(message.user_id) === currentUserId) row.dataset.own = 'true';
      const author = document.createElement('strong');
      author.className = 'room-chat-author';
      author.textContent = message.user;
      const body = document.createElement('span');
      body.className = 'room-chat-body';
      body.textContent = message.content;
      row.append(author, body);
      if (emptyChat?.parentElement === chatList) emptyChat.remove();
      chatList.append(row);
      if (chatList.children.length > 100) chatList.firstElementChild.remove();
      lastChat = message.id;
      added = true;
    }
    if (!added) return;
    if (emptyChat) emptyChat.hidden = true;
    if (nearBottom || ownMessage) chatList.scrollTop = chatList.scrollHeight;
  }

  chatForm.addEventListener('submit', async event => {
    event.preventDefault();
    const input = chatForm.elements.content;
    const message = input.value.trim();
    if (stopped || sendingChat || !message) return;

    const submittedValue = input.value;
    const button = chatForm.querySelector('button[type="submit"], button:not([type])');
    sendingChat = true;
    button.disabled = true;
    chatForm.setAttribute('aria-busy', 'true');
    try {
      const data = await send({action: 'chat', content: message});
      if (input.value === submittedValue) input.value = '';
      if (!stopped) showMessages(data.messages, true);
    } catch { /* Keep the draft so the member can retry. */ }
    finally {
      sendingChat = false;
      button.disabled = stopped;
      chatForm.removeAttribute('aria-busy');
    }
  });

  function makeMember(member) {
    const id = String(member.user_id);
    const username = member.user__username;
    const row = document.createElement('div');
    row.className = 'room-member';
    row.dataset.memberId = id;
    row.dataset.memberName = username;
    const avatar = document.createElement('span');
    avatar.className = 'room-member-avatar';
    avatar.setAttribute('aria-hidden', 'true');
    avatar.textContent = Array.from(username.trim())[0]?.toUpperCase() || '?';
    const info = document.createElement('span');
    info.className = 'room-member-info';
    const name = document.createElement('strong');
    name.className = 'room-member-name';
    name.textContent = username;
    const role = document.createElement('span');
    role.className = 'room-member-role';
    role.textContent = id === hostId ? 'Chủ phòng' : 'Thành viên';
    if (id === currentUserId) role.textContent += ' · Bạn';
    info.append(name, role);
    const voice = document.createElement('span');
    voice.className = 'room-member-voice-state';
    voice.dataset.memberVoiceState = '';
    const actions = document.createElement('div');
    actions.className = 'room-member-actions';
    actions.dataset.memberActions = '';
    if (isHost && id !== currentUserId) {
      const kick = document.createElement('button');
      kick.type = 'button';
      kick.className = 'room-member-action room-member-kick';
      kick.textContent = '×';
      kick.title = 'Loại khỏi phòng';
      kick.setAttribute('aria-label', `Loại ${username} khỏi phòng`);
      kick.addEventListener('click', () => kickMember(member, kick));
      actions.append(kick);
    }
    row.append(avatar, info, voice, actions);
    return row;
  }

  const rows = new Map();
  const kicked = new Set();
  let previousRoster;

  async function kickMember(member, button) {
    if (stopped || button.disabled || !confirm(`Loại ${member.user__username} khỏi phòng?`)) return;
    button.disabled = true;
    try {
      const data = await send({action: 'kick', user: member.user_id});
      // A poll started before the kick can briefly return the prior roster.
      kicked.add(String(member.user_id));
      if (!stopped) showMembers(data.members);
    } catch {
      button.disabled = false;
    }
  }

  if (vuePresentation && isHost) {
    room.addEventListener('lumiere:room-kick', event => {
      const {member, button} = event.detail;
      if (member && button instanceof HTMLButtonElement) kickMember(member, button);
    });
  }

  function showMembers(roster) {
    const sorted = roster.filter(member => !kicked.has(String(member.user_id)));
    const rank = member => String(member.user_id) === hostId ? 0 : String(member.user_id) === currentUserId ? 1 : 2;
    sorted.sort((a, b) => rank(a) - rank(b) || a.user__username.localeCompare(b.user__username, 'vi'));
    if (vuePresentation) {
      const signature = JSON.stringify(sorted);
      if (signature !== previousRoster) {
        previousRoster = signature;
        room.dispatchEvent(new CustomEvent('lumiere:roster-update', {detail: sorted}));
      }
      return;
    }
    const present = new Set(sorted.map(member => String(member.user_id)));
    let changed = false;
    for (const [id, row] of rows) {
      if (present.has(id)) continue;
      row.remove();
      rows.delete(id);
      changed = true;
    }
    let position = members.firstElementChild;
    for (const member of sorted) {
      const id = String(member.user_id);
      let row = rows.get(id);
      if (!row || row.dataset.memberName !== member.user__username) {
        if (row && row === position) position = row.nextElementSibling;
        row?.remove();
        row = makeMember(member);
        rows.set(id, row);
      }
      if (row !== position) {
        members.insertBefore(row, position);
        changed = true;
      }
      position = row.nextElementSibling;
    }
    if (memberCount && memberCount.textContent !== String(rows.size)) memberCount.textContent = String(rows.size);
    if (changed) room.dispatchEvent(new Event('lumiere:room-members'));
  }

  async function poll() {
    if (stopped) return;
    try {
      const response = await fetch(room.dataset.state, {credentials: 'same-origin'});
      if (stopped) return;
      if ([403, 404, 409].includes(response.status) || response.redirected) {
        stopRoom('Phòng đã đóng hoặc bạn không còn quyền tham gia.');
        return;
      }
      if (!response.ok) throw new Error('Đang kết nối lại phòng…');
      const data = await response.json();
      if (stopped) return;
      if (data.closed) {
        stopRoom('Phòng đã đóng.');
        return;
      }
      if (reconnecting) {
        status.textContent = '';
        reconnecting = false;
      }
      if (!isHost && video.readyState >= 1) {
        const position = Number(data.position);
        if (Number.isFinite(position) && Number.isFinite(video.duration) && Math.abs(video.currentTime - position) > 2) {
          video.currentTime = Math.max(0, Math.min(video.duration, position));
        }
        if (data.playing && video.paused) {
          // Waiting on autoplay here would also delay the roster and chat.
          video.play().catch(() => {
            if (!stopped) status.textContent = 'Nhấn phát để tham gia buổi chiếu.';
          });
        }
        if (!data.playing && !video.paused) video.pause();
      }
      showMessages(data.messages);
      showMembers(data.members);
    } catch {
      if (!stopped && !reconnecting) {
        reconnecting = true;
        status.textContent = 'Đang kết nối lại phòng…';
      }
    } finally {
      if (!stopped) setTimeout(poll, 2000);
    }
  }
  poll();
})();
