import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { csrfToken, formParams } from '../shared/http'
import type { FormFields } from '../shared/http'
import type { PlaylistItem, PlaylistSnapshot, RoomMediaState, Suggestion } from './room-types'

/** Coordinate playlist requests, permissions and polling independently from its presentation. */
export function useRoomPlaylist(room: HTMLElement) {
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

  function reorder(order: number[], source: number, destination: number) {
    order.splice(destination, 0, order.splice(source, 1)[0])
    void change('reorder', {item_ids: JSON.stringify(order)})
  }

  function move(id: number, offset: number) {
    const order = items.value.map(item => item.id)
    const source = order.indexOf(id)
    const destination = source + offset
    if (source < 0 || destination < 0 || destination >= order.length) return
    reorder(order, source, destination)
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
    reorder(order, source, destination)
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

  return {
    items, canManage, loaded, busy, message, failed, currentEpisode, filmEnded, draggedItem,
    pendingSuggestions, mySuggestions, nextItem, disabled, change, move, drag, drop,
  }
}
