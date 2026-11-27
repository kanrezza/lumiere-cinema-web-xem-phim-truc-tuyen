import { csrfToken, formParams } from '../shared/http'
import type { FormFields } from '../shared/http'

interface AdmissionState {
  requires_approval: boolean
  has_password: boolean
  settings_version: string
  error?: string
}

type AdmissionAction = FormFields & {action: 'settings' | 'approve' | 'reject'}

export function initAdmission(room: HTMLElement) {
  const initialEndpoint = room.dataset.admission
  const initialForm = room.querySelector<HTMLFormElement>('[data-room-access-form]')
  const initialStatus = room.querySelector<HTMLElement>('[data-room-access-status]')
  const initialPasswordStatus = room.querySelector<HTMLElement>('[data-room-password-status]')
  const initialSave = initialForm?.querySelector<HTMLButtonElement>('button[type=submit]')
  const initialApproval = initialForm?.querySelector<HTMLInputElement>('[name=requires_approval]')
  const initialPassword = initialForm?.querySelector<HTMLInputElement>('[name=password]')
  const initialRemovePassword = initialForm?.querySelector<HTMLInputElement>('[name=remove_password]')
  const initialVersion = initialForm?.querySelector<HTMLInputElement>('[name=settings_version]')
  if (!initialEndpoint || !initialForm || !initialStatus || !initialPasswordStatus || !initialSave || !initialApproval || !initialPassword || !initialRemovePassword || !initialVersion) return

  const endpoint = initialEndpoint
  const form = initialForm
  const status = initialStatus
  const passwordStatus = initialPasswordStatus
  const save = initialSave
  const approval = initialApproval
  const password = initialPassword
  const removePassword = initialRemovePassword
  const version = initialVersion

  let stopped = false;
  let pendingAction = false;
  let revision = 0;
  window.addEventListener('pagehide', () => {stopped = true;});
  window.addEventListener('pageshow', event => {if (event.persisted) window.location.reload();});
  document.addEventListener('lumiere:stop', () => {stopped = true;});

  let savedApproval = approval.checked;

  function settings(data: AdmissionState, preserveEdits = false) {
    if (!preserveEdits || approval.checked === savedApproval) approval.checked = data.requires_approval;
    savedApproval = data.requires_approval;
    if (!preserveEdits) password.value = '';
    if (!preserveEdits || !data.has_password) removePassword.checked = false;
    removePassword.disabled = !data.has_password;
    version.value = data.settings_version;
    passwordStatus.textContent = data.has_password ? 'Phòng đang có mật khẩu.' : 'Phòng chưa đặt mật khẩu.';
  }

  function refreshSettings(data: AdmissionState) {
    if (data.settings_version === version.value) return;
    if (approval.checked !== savedApproval || password.value || removePassword.checked) {
      status.textContent = 'Cài đặt phòng vừa thay đổi. Bản chỉnh sửa của bạn vẫn được giữ.';
      return;
    }
    settings(data);
  }

  function renderQueue(data: AdmissionState) {
    room.dispatchEvent(new CustomEvent('lumiere:room-queue-update', {detail: data}));
  }

  async function send(data: AdmissionAction) {
    if (stopped || pendingAction) return;
    revision += 1;
    pendingAction = true;
    room.dispatchEvent(new CustomEvent('lumiere:room-queue-busy', {detail: true}));
    save.disabled = true;
    form.inert = data.action === 'settings';
    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: {'X-CSRFToken': csrfToken()},
        body: formParams(data),
      });
      if (response.redirected) throw new Error('Phiên đăng nhập đã hết hạn.');
      const result: AdmissionState = await response.json().catch(() => ({}));
      if (stopped) return;
      if (response.status === 409 && data.action === 'settings' && result.settings_version) settings(result, true);
      if (!response.ok) throw new Error(result.error || 'Không thể cập nhật phòng. Hãy thử lại.');
      renderQueue(result);
      if (data.action === 'settings') settings(result);
      else refreshSettings(result);
      status.textContent = {approve: 'Đã duyệt yêu cầu.', reject: 'Đã từ chối yêu cầu.', settings: 'Đã lưu cài đặt phòng.'}[data.action];
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : 'Không thể cập nhật phòng.';
    } finally {
      pendingAction = false;
      if (!stopped) room.dispatchEvent(new CustomEvent('lumiere:room-queue-busy', {detail: false}));
      form.inert = false;
      save.disabled = false;
    }
  }

  form.addEventListener('submit', event => {
    event.preventDefault();
    const fields = new FormData(form);
    const data: AdmissionAction = {action: 'settings'};
    for (const [name, value] of fields) {
      if (typeof value === 'string' && name !== 'csrfmiddlewaretoken' && name !== 'action') data[name] = value;
    }
    void send(data);
  });

  room.addEventListener('lumiere:room-queue-decision', event => {
    const {action, id} = (event as CustomEvent<{action: string; id: number}>).detail;
    if ((action === 'approve' || action === 'reject') && Number.isInteger(id) && id > 0) {
      send({action, request: id});
    }
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
        const data: AdmissionState = await response.json();
        if (!stopped && !pendingAction && before === revision) {
          renderQueue(data);
          refreshSettings(data);
        }
      }
    } catch { /* Retry in the next refresh. */ }
    finally { if (!stopped) window.setTimeout(poll, 2500); }
  }
  poll();
}
