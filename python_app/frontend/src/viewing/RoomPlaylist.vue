<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { csrfToken, formParams } from '../shared/http'
import type { FormFields } from '../shared/http'
import type { RoomMediaState } from './room-media'

interface PlaylistItem {
  id: number
  episode_id: number
  title: string
  episode_title: string
  poster_url: string
  position: number
  available: boolean
}
interface Suggestion extends PlaylistItem {
  proposed_by: string
  proposer_id: number
  status: string
}
interface PlaylistSnapshot extends RoomMediaState {
  playlist_version: number
  items: PlaylistItem[]
  suggestions: Suggestion[]
  is_host: boolean
  can_manage: boolean
  error?: string
}

const { room } = defineProps<{ room: HTMLElement }>()
const items = shallowRef<PlaylistItem[]>([])
const suggestions = shallowRef<Suggestion[]>([])
const version = ref(-1)
const canManage = ref(room.dataset.host === 'true')
const loaded = ref(false)
const busy = ref(false)
const stopped = ref(false)
const message = ref('Đang tải danh sách phim…')
const failed = ref(false)
const currentEpisode = ref(Number(room.dataset.episodeId) || null)
const currentMediaVersion = ref(Number(room.dataset.mediaVersion) || 1)
const filmEnded = ref(false)
const draggedItem = ref<number | null>(null)
const events = new AbortController()
let reading: AbortController | undefined
let writing: AbortController | undefined
let timer: ReturnType<typeof setTimeout> | undefined

const pendingSuggestions = computed(() => suggestions.value.filter(entry => entry.status === 'pending'))
const mySuggestions = computed(() => suggestions.value.filter(entry => entry.proposer_id === Number(room.dataset.user)))
const nextItem = computed(() => {
  const currentIndex = items.value.findIndex(item => item.episode_id === currentEpisode.value)
  return items.value.slice(currentIndex + 1).find(item => item.available)
})
const disabled = computed(() => busy.value || stopped.value || !loaded.value)

function endpoint() {
  const url = new URL(room.dataset.playlist || '', window.location.href)
  if (url.origin !== window.location.origin || !url.pathname.startsWith('/rooms/')) {
    throw new Error('Địa chỉ danh sách phim không hợp lệ.')
  }
  return url.href
}

function announce(text: string, error = false) {
  message.value = text
  failed.value = error
  const picker = room.querySelector<HTMLElement>('[data-room-picker]')
  const pickerStatus = picker?.querySelector<HTMLElement>('[data-room-picker-status]')
  if (picker && !picker.hidden && pickerStatus) {
    pickerStatus.textContent = text
    pickerStatus.dataset.error = String(error)
  }
}

function apply(snapshot: PlaylistSnapshot) {
  if (!Number.isSafeInteger(snapshot.playlist_version) || snapshot.playlist_version < version.value) return
  if (!Array.isArray(snapshot.items) || !Array.isArray(snapshot.suggestions)) {
    throw new Error('Không đọc được danh sách phim. Hãy thử lại.')
  }
  version.value = snapshot.playlist_version
  items.value = snapshot.items
  suggestions.value = snapshot.suggestions
  canManage.value = snapshot.can_manage
  loaded.value = true
  const count = room.querySelector('[data-room-playlist-count]')
  if (count) count.textContent = String(snapshot.items.length)
  if (Number.isSafeInteger(snapshot.media_version)) {
    room.dispatchEvent(new CustomEvent('lumiere:room-media-change', {detail: snapshot}))
  }
}

async function read() {
  if (stopped.value) return
  reading?.abort()
  const controller = new AbortController()
  reading = controller
  try {
    const response = await fetch(endpoint(), {credentials: 'same-origin', signal: controller.signal})
    if (!response.ok || response.redirected) throw new Error('Chưa thể tải danh sách phim. Kiểm tra kết nối rồi thử lại.')
    const snapshot = await response.json() as PlaylistSnapshot
    if (stopped.value || controller.signal.aborted) return
    const firstLoad = !loaded.value
    apply(snapshot)
    if (firstLoad || failed.value) announce('')
  } catch (error) {
    if (!controller.signal.aborted) announce(error instanceof Error ? error.message : 'Không tải được danh sách phim.', true)
  } finally {
    if (reading === controller) reading = undefined
    if (!stopped.value) timer = setTimeout(read, 6000)
  }
}

async function change(action: string, fields: FormFields = {}, selectedForm?: HTMLFormElement) {
  if (disabled.value) return
  busy.value = true
  writing = new AbortController()
  const button = selectedForm?.querySelector<HTMLButtonElement>('button[type="submit"], button:not([type])')
  if (button) button.disabled = true
  selectedForm?.setAttribute('aria-busy', 'true')
  try {
    const response = await fetch(endpoint(), {
      method: 'POST', credentials: 'same-origin', signal: writing.signal,
      headers: {'X-CSRFToken': csrfToken(), 'Content-Type': 'application/x-www-form-urlencoded'},
      body: formParams({action, ...fields, playlist_version: version.value}),
    })
    if (response.redirected) throw new Error('Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại.')
    let snapshot: PlaylistSnapshot
    try { snapshot = await response.json() as PlaylistSnapshot }
    catch { throw new Error('Không đọc được phản hồi. Kiểm tra kết nối và quyền truy cập rồi thử lại.') }
    if (stopped.value) return
    if (response.ok || response.status === 409) apply(snapshot)
    if (!response.ok) throw new Error(snapshot.error || 'Danh sách đã thay đổi. Kiểm tra lại trước khi thao tác.')
    const messages: Record<string, string> = {
      add: 'Đã thêm vào danh sách phim.', suggest: 'Đã gửi đề xuất cho chủ phòng.',
      remove: 'Đã bỏ phim khỏi danh sách.', reorder: 'Đã lưu thứ tự xem.',
      play: 'Đang mở phim cho cả phòng…', approve: 'Đã thêm phim được đề xuất.', reject: 'Đã từ chối đề xuất.',
    }
    announce(messages[action] || 'Đã cập nhật danh sách phim.')
  } catch (error) {
    if (!stopped.value) announce(error instanceof Error ? error.message : 'Chưa thể cập nhật danh sách.', true)
  } finally {
    writing = undefined
    busy.value = false
    if (button) button.disabled = false
    selectedForm?.removeAttribute('aria-busy')
  }
}

function move(id: number, offset: number) {
  const order = items.value.map(item => item.id)
  const source = order.indexOf(id)
  const destination = source + offset
  if (source < 0 || destination < 0 || destination >= order.length) return
  order.splice(destination, 0, order.splice(source, 1)[0])
  void change('reorder', {item_ids: JSON.stringify(order)})
}

function drag(event: DragEvent, item: PlaylistItem) {
  if (!canManage.value || disabled.value || !event.dataTransfer) {
    event.preventDefault()
    return
  }
  draggedItem.value = item.id
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', String(item.id))
}

function drop(event: DragEvent, target: number) {
  event.preventDefault()
  const moving = draggedItem.value
  draggedItem.value = null
  if (moving === null || moving === target || !canManage.value || disabled.value) return
  const order = items.value.map(item => item.id)
  const source = order.indexOf(moving)
  const destination = order.indexOf(target)
  if (source < 0 || destination < 0) return
  order.splice(destination, 0, order.splice(source, 1)[0])
  void change('reorder', {item_ids: JSON.stringify(order)})
}

function stop() {
  stopped.value = true
  if (timer !== undefined) clearTimeout(timer)
  reading?.abort()
  writing?.abort()
}

onMounted(() => {
  room.addEventListener('lumiere:room-media-update', event => {
    const state = (event as CustomEvent<RoomMediaState>).detail
    if (!Number.isSafeInteger(state.media_version) || state.media_version! < currentMediaVersion.value) return
    if (state.media_version !== currentMediaVersion.value) filmEnded.value = false
    currentMediaVersion.value = state.media_version!
    currentEpisode.value = state.episode_id ?? null
  }, {signal: events.signal})
  room.addEventListener('lumiere:room-film-ended', () => {filmEnded.value = true}, {signal: events.signal})
  room.addEventListener('submit', event => {
    const form = event.target
    if (!(form instanceof HTMLFormElement) || !form.matches('[data-room-playlist-selection]')) return
    event.preventDefault()
    const episode = new FormData(form).get('episode')
    if (typeof episode !== 'string') return
    if (!loaded.value) {
      announce('Đang tải danh sách phim. Bạn thử lại sau giây lát.')
      return
    }
    void change(canManage.value ? 'add' : 'suggest', {episode}, form)
  }, {signal: events.signal})
  document.addEventListener('lumiere:stop', stop, {signal: events.signal})
  window.addEventListener('pagehide', stop, {signal: events.signal})
  void read()
})
onUnmounted(() => {stop(); events.abort()})
</script>

<template>
  <section class="cinema-playlist" aria-labelledby="room-playlist-title" :aria-busy="busy">
    <h2 id="room-playlist-title" class="sr-only">Danh sách xem</h2>
    <p class="playlist-notice" :class="{ 'is-error': failed }" role="status" aria-live="polite">{{ message }}</p>
    <div v-if="loaded && !items.length" class="playlist-empty"><p>Danh sách đang trống. {{ canManage ? 'Thêm phim để chuẩn bị buổi xem.' : 'Bạn có thể đề xuất một phim cho chủ phòng.' }}</p></div>
    <ol v-else class="playlist-list" aria-label="Thứ tự xem phim">
      <li v-for="(item, index) in items" :key="item.id" class="playlist-item" :class="{ 'is-current': currentEpisode === item.episode_id, 'is-dragging': draggedItem === item.id }" :draggable="canManage && !disabled" @dragstart="drag($event, item)" @dragend="draggedItem = null" @dragover.prevent @drop="drop($event, item.id)">
        <span class="playlist-number">{{ index + 1 }}</span>
        <img class="playlist-poster" v-if="item.poster_url" :src="item.poster_url" alt="" loading="lazy" width="48" height="66">
        <div class="playlist-copy"><h3>{{ item.title }}</h3><p>{{ item.episode_title }}</p><span v-if="currentEpisode === item.episode_id" class="playlist-current">Đang xem</span><span v-else-if="!item.available" class="playlist-unavailable">Chưa có bản xem</span></div>
        <div v-if="canManage" class="playlist-actions">
          <button type="button" :disabled="disabled || !item.available" class="playlist-play" :aria-label="`Phát ${item.title}`" @click="change('play', {item: item.id})">Phát</button>
          <button type="button" :disabled="disabled || index === 0" class="playlist-icon" :aria-label="`Đưa ${item.title} lên trước`" title="Đưa lên trước" @click="move(item.id, -1)">↑</button>
          <button type="button" :disabled="disabled || index === items.length - 1" class="playlist-icon" :aria-label="`Đưa ${item.title} xuống sau`" title="Đưa xuống sau" @click="move(item.id, 1)">↓</button>
          <button type="button" :disabled="disabled" class="playlist-icon" :aria-label="`Bỏ ${item.title} khỏi danh sách`" @click="change('remove', {item: item.id})">×</button>
        </div>
      </li>
    </ol>
    <div v-if="canManage && nextItem" class="playlist-next" :class="{ 'is-ready': filmEnded }" data-room-next>
      <div><span>{{ filmEnded ? 'Phim vừa kết thúc' : 'Tiếp theo trong danh sách' }}</span><strong>{{ nextItem.title }}</strong><small>{{ nextItem.episode_title }}</small></div>
      <button class="btn small" type="button" :disabled="disabled" @click="change('play', {item: nextItem.id})">{{ currentEpisode ? 'Phát tiếp theo' : 'Bắt đầu xem' }}</button>
    </div>
    <section v-if="canManage && pendingSuggestions.length" class="playlist-suggestions" aria-labelledby="room-suggestions-title">
      <h3 id="room-suggestions-title" class="suggestion-heading">Phim được đề xuất <span>{{ pendingSuggestions.length }}</span></h3>
      <ul class="suggestion-list">
        <li class="suggestion-item" v-for="entry in pendingSuggestions" :key="entry.id">
          <div class="suggestion-copy"><strong>{{ entry.title }}</strong><small>{{ entry.episode_title }} · {{ entry.proposed_by }}</small></div>
          <div class="suggestion-actions"><button type="button" :disabled="disabled || !entry.available" @click="change('approve', {suggestion: entry.id})">Thêm</button><button type="button" :disabled="disabled" @click="change('reject', {suggestion: entry.id})">Từ chối</button></div>
        </li>
      </ul>
    </section>
    <section v-else-if="!canManage && mySuggestions.length" class="playlist-suggestions" aria-labelledby="room-suggestions-title">
      <h3 id="room-suggestions-title" class="suggestion-heading">Đề xuất của bạn</h3>
      <ul class="suggestion-list"><li class="suggestion-item" v-for="entry in mySuggestions" :key="entry.id"><div class="suggestion-copy"><strong>{{ entry.title }}</strong><small>{{ entry.episode_title }}</small></div><span>{{ entry.status === 'approved' ? 'Đã thêm' : entry.status === 'rejected' ? 'Đã từ chối' : 'Chờ chủ phòng' }}</span></li></ul>
    </section>
  </section>
</template>
