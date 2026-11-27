<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { csrfToken, formParams } from '../shared/http'
import type { MountPlayer } from './room-media'
import { countdownLabel, premiereCountdown, premierePlaybackPosition } from './premiere-state'
import type { PremiereState } from './premiere-state'

const props = defineProps<{
  initialState: PremiereState
  endpoint: string
  controlEndpoint: string
  canManage: boolean
  authenticated: boolean
  playerTemplate: HTMLTemplateElement
  mountPlayer: MountPlayer
}>()
const state = ref(props.initialState)
const elapsed = ref(0)
const feedback = ref('')
const draft = ref('')
const busy = ref(false)
const draining = ref(false)
const playerHost = ref<HTMLElement>()
const chatLog = ref<HTMLElement>()
const isLive = computed(() => state.value.status === 'live')
const preparing = computed(() => isLive.value && state.value.can_watch && state.value.position < (state.value.playback_delay_seconds ?? 12))
const showPlayer = computed(() => state.value.can_watch && (draining.value || isLive.value && !preparing.value && Boolean(state.value.ticket_url)))
const canPrepare = computed(() => state.value.can_watch && (draining.value || isLive.value && state.value.position >= 6 && Boolean(state.value.ticket_url)))
const canChat = computed(() => props.authenticated && state.value.can_watch && state.value.can_chat !== false && ['scheduled', 'live'].includes(state.value.status))
const countdown = computed(() => countdownLabel(premiereCountdown(state.value, elapsed.value)))
const statusLabel = computed(() => ({scheduled: 'Sắp công chiếu', live: 'Đang công chiếu', ended: 'Buổi chiếu đã kết thúc', cancelled: 'Buổi chiếu đã hủy'}[state.value.status]))
let receivedAt = performance.now()
let disposed = false
let pollTimer: ReturnType<typeof setTimeout> | undefined
let clockTimer: ReturnType<typeof setInterval> | undefined
let disposePlayer: (() => void) | undefined
let playerEvents: AbortController | undefined
let pollRequest: AbortController | undefined
let playerSignature = ''
let video: HTMLVideoElement | undefined
let mountGeneration = 0
let requestSequence = 0
let appliedSequence = 0
let reconnecting = false
let attemptedStart = false

function currentPosition() {
  return premierePlaybackPosition(state.value, (performance.now() - receivedAt) / 1000)
}

function releasePlayer() {
  mountGeneration += 1
  playerEvents?.abort()
  disposePlayer?.()
  disposePlayer = undefined
  playerEvents = undefined
  video = undefined
  playerSignature = ''
  attemptedStart = false
  playerHost.value?.replaceChildren()
}

async function syncPlayer() {
  if (!canPrepare.value) {
    releasePlayer()
    return
  }
  if (draining.value) { startPreparedPlayer(); return }
  const signature = state.value.episode_id + ':' + state.value.ticket_url
  if (signature === playerSignature) {
    startPreparedPlayer()
    if (video && !video.paused && video.readyState >= 1 && Math.abs(video.currentTime - currentPosition()) > 4) video.currentTime = currentPosition()
    return
  }
  releasePlayer()
  const generation = mountGeneration
  await nextTick()
  if (disposed || generation !== mountGeneration || !canPrepare.value || !playerHost.value) return
  const ticket = new URL(state.value.ticket_url, location.href)
  if (ticket.origin !== location.origin || ticket.searchParams.get('premiere') !== state.value.id) {
    feedback.value = 'Nguồn công chiếu không hợp lệ.'
    return
  }
  playerHost.value.replaceChildren(document.importNode(props.playerTemplate.content, true))
  const next = playerHost.value.querySelector<HTMLVideoElement>('video#player')
  if (!next) return
  video = next
  video.dataset.ticket = ticket.href
  video.dataset.position = String(currentPosition())
  video.dataset.playOnReady = String(!preparing.value)
  attemptedStart = !preparing.value
  video.dataset.premiere = 'true'
  video.dataset.saveProgress = 'false'
  const wrap = video.closest<HTMLElement>('.player-wrap')
  if (wrap) wrap.dataset.canSeek = 'false'
  playerEvents = new AbortController()
  const snapToLive = () => {
    if (video && video.readyState >= 1 && Math.abs(video.currentTime - currentPosition()) > 2) video.currentTime = currentPosition()
  }
  video.addEventListener('loadedmetadata', snapToLive, {signal: playerEvents.signal})
  video.addEventListener('loadedmetadata', startPreparedPlayer, {signal: playerEvents.signal})
  video.addEventListener('play', snapToLive, {signal: playerEvents.signal})
  video.addEventListener('seeking', () => {
    if (video && video.currentTime > currentPosition() + 1) snapToLive()
  }, {signal: playerEvents.signal})
  video.addEventListener('ended', () => {
    draining.value = false
    if (state.value.status === 'ended') void syncPlayer()
  }, {signal: playerEvents.signal})
  disposePlayer = props.mountPlayer(video)
  playerSignature = signature
}

function startPreparedPlayer() {
  if (!video || attemptedStart || preparing.value || video.readyState < 1) return
  attemptedStart = true
  video.currentTime = currentPosition()
  void video.play().catch(() => { feedback.value = 'Nhấn Phát trong trình phát để tham gia.' })
}

async function apply(next: PremiereState, sequence: number) {
  if (disposed || sequence < appliedSequence || next.id !== props.initialState.id || next.state_version < state.value.state_version) return
  appliedSequence = sequence
  const log = chatLog.value
  const wasAtBottom = !log || log.scrollHeight - log.scrollTop - log.clientHeight < 70
  draining.value = next.status === 'ended' && !next.ended_manually && Boolean(video && !video.ended && playerSignature)
  state.value = next
  receivedAt = performance.now()
  elapsed.value = 0
  await syncPlayer()
  await nextTick()
  if (wasAtBottom && chatLog.value) chatLog.value.scrollTop = chatLog.value.scrollHeight
}

async function poll() {
  if (disposed) return
  const sequence = ++requestSequence
  pollRequest = new AbortController()
  try {
    const response = await fetch(props.endpoint, {credentials: 'same-origin', cache: 'no-store', signal: pollRequest.signal})
    if (!response.ok || response.redirected) throw new Error('Mất kết nối buổi chiếu. Đang thử lại…')
    await apply(await response.json() as PremiereState, sequence)
    if (reconnecting) { feedback.value = ''; reconnecting = false }
  } catch (error) {
    if (!disposed && !pollRequest.signal.aborted) { reconnecting = true; feedback.value = error instanceof Error ? error.message : 'Không thể cập nhật buổi chiếu.' }
  } finally {
    if (!disposed) pollTimer = setTimeout(poll, 3000)
  }
}

async function send(action: string) {
  if (busy.value || disposed) return
  if (action === 'chat' && (!canChat.value || !draft.value.trim())) return
  busy.value = true
  feedback.value = ''
  const submitted = draft.value
  const sequence = ++requestSequence
  try {
    const response = await fetch(action === 'chat' ? props.endpoint : props.controlEndpoint, {
      method: 'POST', credentials: 'same-origin',
      headers: {'X-CSRFToken': csrfToken(), 'Content-Type': 'application/x-www-form-urlencoded'},
      body: formParams({action, content: submitted.trim(), state_version: state.value.state_version}),
    })
    if (response.redirected) throw new Error('Vui lòng đăng nhập lại.')
    const result = await response.json() as PremiereState & {error?: string; notice?: string}
    if (!response.ok) {
      if (response.status === 409 && result.id) await apply(result, sequence)
      throw new Error(result.error || 'Chưa thể thực hiện thao tác này.')
    }
    await apply(result, sequence)
    if (action === 'chat' && draft.value === submitted) draft.value = ''
    if (result.notice) feedback.value = result.notice
    if (action !== 'chat') feedback.value = 'Đã cập nhật buổi công chiếu.'
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : 'Không thể gửi yêu cầu.'
  } finally {
    busy.value = false
  }
}

function joinLive() {
  if (!video) return
  video.currentTime = currentPosition()
  void video.play().catch(() => { feedback.value = 'Nhấn Phát trong trình phát để tham gia.' })
}

onMounted(() => {
  void syncPlayer()
  void poll()
  clockTimer = setInterval(() => { elapsed.value = (performance.now() - receivedAt) / 1000 }, 1000)
})
onBeforeUnmount(() => {
  disposed = true
  pollRequest?.abort()
  if (pollTimer) clearTimeout(pollTimer)
  if (clockTimer) clearInterval(clockTimer)
  releasePlayer()
})
</script>

<template>
  <div class="premiere-experience">
    <div class="premiere-stage">
      <div class="premiere-stage-top"><span class="premiere-status" :class="{'is-live': isLive}"><i aria-hidden="true"></i>{{ statusLabel }}</span><span>{{ state.requires_vip ? 'Dành cho VIP' : 'Mở cho mọi người' }}</span></div>
      <div class="premiere-screen">
        <div v-show="showPlayer" ref="playerHost" class="premiere-player-host"></div>
        <div v-if="!showPlayer" class="premiere-waiting">
          <span class="premiere-waiting-mark" aria-hidden="true">L.</span>
          <template v-if="state.status === 'scheduled'">
            <span class="premiere-eyebrow">BUỔI HẸN ĐANG ĐẾN GẦN</span>
            <h2>Cùng đón giờ chiếu.</h2>
            <p class="premiere-countdown" role="timer" aria-label="Thời gian đến buổi công chiếu">{{ countdown }}</p>
            <p>Phim sẽ phát theo lịch công chiếu.</p>
          </template>
          <template v-else-if="preparing"><span class="premiere-eyebrow">BUỔI CHIẾU ĐÃ BẮT ĐẦU</span><h2>Màn chiếu đang mở.</h2><p>Đang chuẩn bị những giây phim đầu tiên…</p></template>
          <template v-else-if="state.status === 'ended' || state.status === 'cancelled'">
            <span class="premiere-eyebrow">LUMIÈRE PREMIERE</span><h2>{{ statusLabel }}</h2><p>Hẹn bạn ở buổi chiếu tiếp theo.</p><a class="btn secondary small" href="/premieres/">Lịch công chiếu</a>
          </template>
          <template v-else><span class="premiere-eyebrow">SUẤT CHIẾU RIÊNG CHO THÀNH VIÊN</span><h2>{{ authenticated ? 'Buổi chiếu dành cho VIP.' : 'Đăng nhập để cùng xem.' }}</h2><p>{{ authenticated ? 'Nâng cấp để tham gia suất chiếu này.' : 'Phim đang chiếu. Đăng nhập để tham gia tại mốc hiện tại.' }}</p><a class="btn small" :href="authenticated ? '/vip/' : '/accounts/login/?next=' + encodeURIComponent('/premieres/' + state.id + '/')">{{ authenticated ? 'Khám phá VIP' : 'Đăng nhập' }}</a></template>
        </div>
      </div>
      <div class="premiere-under-screen"><p>{{ isLive ? 'Cùng một tập phim. Cùng một khoảnh khắc.' : 'Được tổ chức bởi Lumière Studio.' }}</p><button v-if="showPlayer" type="button" class="premiere-live-return" @click="joinLive"><i aria-hidden="true"></i>Về mốc đang chiếu</button></div>
      <p v-if="state.requires_vip && !state.can_watch && state.status === 'scheduled'" class="premiere-access-note">Đây là suất chiếu dành riêng cho thành viên VIP. <a :href="authenticated ? '/vip/' : '/accounts/login/?next=' + encodeURIComponent('/premieres/' + state.id + '/')">{{ authenticated ? 'Xem quyền lợi VIP ↗' : 'Đăng nhập để tham gia ↗' }}</a></p>
      <section v-if="canManage" class="premiere-host-tools" aria-label="Điều hành công chiếu"><div><span class="premiere-eyebrow">LUMIÈRE STUDIO</span><h2>Điều hành buổi chiếu</h2><p>Thao tác này áp dụng cho toàn bộ khán giả.</p></div><div class="actions"><button v-if="state.status === 'scheduled'" type="button" class="btn small" :disabled="busy" @click="send('start')">Chiếu ngay</button><button v-if="state.status === 'live'" type="button" class="btn secondary small" :disabled="busy" @click="send('end')">Kết thúc buổi chiếu</button><button v-if="state.status === 'scheduled'" type="button" class="btn secondary small" :disabled="busy" @click="send('cancel')">Hủy lịch</button></div></section>
    </div>
    <aside class="premiere-chat" aria-label="Trò chuyện công chiếu"><header><h2>Trò chuyện trực tiếp</h2><span>Cùng xem, cùng chia sẻ</span></header><div ref="chatLog" class="premiere-chat-log" role="log" aria-live="polite" aria-relevant="additions"><p v-if="!state.messages.length" class="premiere-chat-empty">{{ canChat ? 'Gửi lời chào đến mọi người trong buổi chiếu.' : 'Trò chuyện mở cho khán giả có quyền tham gia buổi chiếu.' }}</p><article v-for="message in state.messages" :key="message.id" class="premiere-message"><span class="premiere-chat-avatar" aria-hidden="true"><img v-if="message.avatar_url" :src="message.avatar_url" alt="" loading="lazy"><span v-else>{{ (message.display_name || message.username || '?').slice(0,1).toUpperCase() }}</span></span><p><strong>{{ message.display_name || message.username }}</strong> <span>{{ message.content }}</span></p></article></div><form class="premiere-chat-form" @submit.prevent="send('chat')"><label class="sr-only" for="premiere-chat-input">Tin nhắn công chiếu</label><input id="premiere-chat-input" v-model="draft" name="content" :disabled="!canChat || busy" maxlength="500" autocomplete="off" placeholder="Chia sẻ khoảnh khắc này…"><button type="submit" :disabled="!canChat || busy || !draft.trim()" aria-label="Gửi tin nhắn"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 14-7-5 14-3-6-6-1Zm6 1 8-8"/></svg></button></form><p class="premiere-chat-note">Giữ cuộc trò chuyện thân thiện. Nội dung được kiểm duyệt.</p></aside>
    <p class="premiere-feedback" role="status" aria-live="polite">{{ feedback }}</p>
  </div>
</template>
