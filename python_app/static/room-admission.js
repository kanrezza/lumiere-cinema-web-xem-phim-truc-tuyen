'use strict';
(() => {
  const room = document.getElementById('room');
  const lobby = document.querySelector('[data-room-lobby]');
  const endpoint = room?.dataset.admission || lobby?.dataset.roomLobby;
  if (!endpoint) return;
  let stopped = false;
  let pendingAction = false;
  let revision = 0;
  window.addEventListener('pagehide', () => {stopped = true;});
  window.addEventListener('pageshow', event => {if (event.persisted) window.location.reload();});
  document.addEventListener('lumiere:stop', () => {stopped = true;});

  if (lobby) {
    async function checkLobby() {
      if (stopped) return;
      try {
        const response = await fetch(endpoint, {cache: 'no-store'});
        if ([403, 404].includes(response.status) || response.redirected) {
          stopped = true;
          lobby.querySelector('[data-lobby-pending] [role=status]').textContent = 'Phòng đã đóng hoặc bạn không còn quyền truy cập.';
          return;
        }
        if (!response.ok) return;
        const {status, requires_approval: requiresApproval} = await response.json();
        if (status === 'pending' && requiresApproval) return;
        stopped = true;
        if (status === 'rejected') {
          lobby.querySelector('[data-lobby-pending]').hidden = true;
          lobby.querySelector('[data-lobby-rejected]').hidden = false;
        } else if (status === 'approved') {
          lobby.querySelector('[data-lobby-pending]').hidden = true;
          lobby.querySelector('[data-lobby-form]').hidden = false;
          lobby.querySelector('[data-lobby-approved]').hidden = false;
          const label = lobby.querySelector('[data-lobby-password]');
          if (label) {
            label.hidden = true;
            label.querySelector('input').required = false;
          }
          lobby.querySelector('[data-lobby-submit]').textContent = 'Tham gia phòng';
        } else {
          window.location.reload();
        }
      } catch { /* Retry while the lobby remains open. */ }
      finally { if (!stopped) window.setTimeout(checkLobby, 2500); }
    }
    checkLobby();
    return;
  }

  const form = room.querySelector('[data-room-access-form]');
  const queue = room.querySelector('[data-room-queue]');
  const status = room.querySelector('[data-room-access-status]');
  const count = room.querySelector('[data-room-pending-count]');
  const empty = room.querySelector('[data-room-queue-empty]');
  const passwordStatus = room.querySelector('[data-room-password-status]');
  const save = form.querySelector('button');
  const {requires_approval: approval, password, remove_password: removePassword, settings_version: version} = form.elements;
  let savedApproval = approval.checked;
  let queueKey;

  function settings(data, preserveEdits = false) {
    if (!preserveEdits || approval.checked === savedApproval) approval.checked = data.requires_approval;
    savedApproval = data.requires_approval;
    if (!preserveEdits) password.value = '';
    if (!preserveEdits || !data.has_password) removePassword.checked = false;
    removePassword.disabled = !data.has_password;
    version.value = data.settings_version;
    passwordStatus.textContent = data.has_password ? 'Phòng đang có mật khẩu.' : 'Phòng chưa đặt mật khẩu.';
  }

  function refreshSettings(data) {
    if (data.settings_version === version.value) return;
    if (approval.checked !== savedApproval || password.value || removePassword.checked) {
      status.textContent = 'Cài đặt phòng vừa thay đổi. Bản chỉnh sửa của bạn vẫn được giữ.';
      return;
    }
    settings(data);
  }

  function renderQueue(data) {
    count.textContent = data.pending_count;
    empty.hidden = Boolean(data.pending.length);
    const key = data.pending.map(entry => entry.pk).join(',');
    if (key === queueKey) return;
    queueKey = key;
    const rows = data.pending.map(entry => {
      const row = document.createElement('li');
      const name = document.createElement('strong');
      name.textContent = entry.user__username;
      const actions = document.createElement('span');
      for (const [action, label] of [['approve', 'Duyệt'], ['reject', 'Từ chối']]) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn small' + (action === 'reject' ? ' secondary' : '');
        button.textContent = label;
        button.setAttribute('aria-label', label + ' ' + entry.user__username);
        button.addEventListener('click', () => send({action, request: entry.pk}));
        actions.append(button);
      }
      row.append(name, actions);
      return row;
    });
    queue.replaceChildren(...rows);
  }

  async function send(data) {
    if (stopped || pendingAction) return;
    revision += 1;
    pendingAction = true;
    save.disabled = true;
    form.inert = data.action === 'settings';
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {'X-CSRFToken': csrfToken()},
        body: new URLSearchParams(data),
      });
      if (response.redirected) throw new Error('Phiên đăng nhập đã hết hạn.');
      const result = await response.json().catch(() => ({}));
      if (stopped) return;
      if (response.status === 409 && data.action === 'settings' && result.settings_version) settings(result, true);
      if (!response.ok) throw new Error(result.error || 'Không thể cập nhật phòng. Hãy thử lại.');
      renderQueue(result);
      if (data.action === 'settings') settings(result);
      else refreshSettings(result);
      status.textContent = {approve: 'Đã duyệt yêu cầu.', reject: 'Đã từ chối yêu cầu.', settings: 'Đã lưu cài đặt phòng.'}[data.action];
    } catch (error) {
      status.textContent = error.message;
    } finally {
      pendingAction = false;
      form.inert = false;
      save.disabled = false;
    }
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    const fields = new FormData(form);
    fields.delete('csrfmiddlewaretoken');
    send(Object.fromEntries(fields));
  });

  async function poll() {
    if (stopped) return;
    const before = revision;
    try {
      const response = await fetch(endpoint, {cache: 'no-store'});
      if ([403, 404].includes(response.status) || response.redirected) {
        stopped = true;
        return;
      }
      if (response.ok) {
        const data = await response.json();
        if (!stopped && !pendingAction && before === revision) {
          renderQueue(data);
          refreshSettings(data);
        }
      }
    } catch { /* Retry in the next refresh. */ }
    finally { if (!stopped) window.setTimeout(poll, 2500); }
  }
  poll();
})();
