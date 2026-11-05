'use strict';
(() => {
 const room = document.getElementById('room'); if (!room) return;
 const video = document.getElementById('player'), status = document.getElementById('room-status');
 const isHost = room.dataset.host === 'true'; let stopped = false, lastChat = 0, applying = false;
 document.getElementById('copy-invite').addEventListener('click', async () => {try {await navigator.clipboard.writeText(location.href); status.textContent = 'Đã sao chép liên kết mời.';} catch {status.textContent = 'Liên kết mời: ' + location.href;}});
 async function send(data) {try {return await postForm(room.dataset.state, data);} catch(error) {status.textContent = error.message; throw error;}}
 if (isHost) {
  ['play','pause','seeked'].forEach(name => video.addEventListener(name, () => {if (!applying && video.dataset.loading !== 'true' && Number.isFinite(video.duration)) send({action:'sync', position:video.currentTime, playing:!video.paused}).catch(() => {});}));
  setInterval(() => {if (!stopped && video.dataset.loading !== 'true' && Number.isFinite(video.duration)) send({action:'sync', position:video.currentTime, playing:!video.paused && video.readyState >= 3}).catch(() => {});}, 6000);
  document.getElementById('close-room').addEventListener('click', async () => {if (confirm('Kết thúc phòng cho tất cả thành viên?')) {await send({action:'close'}); location.href = '/library/';}});
 }
 document.getElementById('chat-form').addEventListener('submit', async e => {e.preventDefault(); const input = e.target.elements.content; if (!input.value.trim()) return; try {await send({action:'chat', content:input.value}); input.value = '';} catch {}});
 async function poll() {
  if (stopped) return;
  try {
   const response = await fetch(room.dataset.state, {credentials:'same-origin'});
   if ([403,404,409].includes(response.status) || response.redirected) {stopped = true; document.dispatchEvent(new Event('lumiere:stop')); status.textContent = 'Phòng đã đóng hoặc bạn không còn quyền tham gia.'; return;}
   if (!response.ok) throw new Error('Đang kết nối lại phòng…');
   const data = await response.json();
   if (!isHost && video.readyState >= 1) {
    applying = true;
    if (Math.abs(video.currentTime - data.position) > 2) video.currentTime = data.position;
    if (data.playing && video.paused) await video.play().catch(() => {status.textContent = 'Nhấn phát để tham gia buổi chiếu.';});
    if (!data.playing && !video.paused) video.pause();
    applying = false;
   }
   const list = document.getElementById('chat-messages');
   for (const message of data.messages) {
    if (message.id <= lastChat) continue;
    const el = document.createElement('p'), name = document.createElement('strong'), body = document.createElement('span');
    name.textContent = message.user; body.textContent = message.content; el.append(name, body); list.append(el); lastChat = message.id;
    if (list.children.length > 100) list.firstChild.remove(); list.scrollTop = list.scrollHeight;
   }
   const members = document.getElementById('members'); members.replaceChildren();
   for (const member of data.members) {
    const el = document.createElement('span'); el.textContent = member.user__username;
    if (isHost && String(member.user_id) !== room.dataset.user) {const kick = document.createElement('button'); kick.textContent = '×'; kick.setAttribute('aria-label', 'Loại ' + member.user__username); kick.onclick = () => send({action:'kick', user:member.user_id}).catch(() => {}); el.append(kick);}
    members.append(el);
   }
  } catch(error) {status.textContent = error.message;}
  finally {if (!stopped) setTimeout(poll, 2000);}
 }
 poll();
})();
