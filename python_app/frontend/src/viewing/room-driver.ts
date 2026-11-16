import { postForm } from '../shared/http'
import type { FormFields } from '../shared/http'

export interface RoomMember {
  user_id: number
  user__username: string
}

export interface ChatMessage {
  id: number
  user_id: number
  user: string
  content: string
}

interface RoomSnapshot {
  closed: boolean
  position: number
  playing: boolean
  messages: ChatMessage[]
  members: RoomMember[]
}

export function initRoom(room: HTMLElement, video: HTMLVideoElement) {
  const initialEndpoint = room.dataset.state
  const initialStatus = room.querySelector<HTMLElement>('#room-status')
  const invite = room.querySelector<HTMLButtonElement>('#copy-invite')
  const close = room.querySelector<HTMLButtonElement>('#close-room')
  const initialChatForm = room.querySelector<HTMLFormElement>('#chat-form')
  const input = initialChatForm?.querySelector<HTMLInputElement>('input[name=content]')
  const button = initialChatForm?.querySelector<HTMLButtonElement>('button[type=submit]')
  if (!initialEndpoint || !initialStatus || !invite || !initialChatForm || !input || !button) return

  const endpoint = initialEndpoint
  const status = initialStatus
  const chatForm = initialChatForm

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

  async function send(data: FormFields) {
    try {
      return await postForm<RoomSnapshot>(endpoint, data);
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : 'Không thể kết nối phòng.';
      throw error;
    }
  }

  function stopRoom(message: string) {
    stopped = true;
    for (const control of chatForm.querySelectorAll<HTMLInputElement | HTMLButtonElement>('input, button')) control.disabled = true;
    if (close) close.disabled = true;
    document.dispatchEvent(new Event('lumiere:stop'));
    status.textContent = message;
  }

  if (isHost) {
    // Serialize host updates so a slower old seek cannot arrive after a new one.
    let pendingSync: FormFields | null = null;
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
    close?.addEventListener('click', async () => {
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

  function showMessages(messages: ChatMessage[], own = false) {
    const added = messages.filter(message => message.id > lastChat);
    if (!added.length) return;
    lastChat = added[added.length - 1].id;
    room.dispatchEvent(new CustomEvent('lumiere:chat-update', {detail: {added, own}}));
  }

  chatForm.addEventListener('submit', async event => {
    event.preventDefault();
    const message = input.value.trim();
    if (stopped || sendingChat || !message) return;

    const submittedValue = input.value;
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

  const kicked = new Set<string>();
  let previousRoster = '';

  async function kickMember(member: RoomMember, button: HTMLButtonElement) {
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

  if (isHost) {
    room.addEventListener('lumiere:room-kick', event => {
      const {member, button} = (event as CustomEvent<{ member: RoomMember; button: HTMLButtonElement }>).detail;
      if (member && button instanceof HTMLButtonElement) kickMember(member, button);
    });
  }

  function showMembers(roster: RoomMember[]) {
    const sorted = roster.filter(member => !kicked.has(String(member.user_id)));
    const rank = (member: RoomMember) => String(member.user_id) === hostId ? 0 : String(member.user_id) === currentUserId ? 1 : 2;
    sorted.sort((a, b) => rank(a) - rank(b) || a.user__username.localeCompare(b.user__username, 'vi'));
    const signature = JSON.stringify(sorted);
    if (signature === previousRoster) return;
    previousRoster = signature;
    room.dispatchEvent(new CustomEvent('lumiere:roster-update', {detail: sorted}));
  }

  async function poll() {
    if (stopped) return;
    try {
      const response = await fetch(endpoint, {credentials: 'same-origin'});
      if (stopped) return;
      if ([403, 404, 409].includes(response.status) || response.redirected) {
        stopRoom('Phòng đã đóng hoặc bạn không còn quyền tham gia.');
        return;
      }
      if (!response.ok) throw new Error('Đang kết nối lại phòng…');
      const data: RoomSnapshot = await response.json();
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
  void poll()
}
