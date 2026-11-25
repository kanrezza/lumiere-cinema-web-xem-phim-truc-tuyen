import type { RoomMediaState } from './room-types'

export type MountPlayer = (video: HTMLVideoElement) => () => void

export function initRoomMedia(
  room: HTMLElement,
  initialVideo: HTMLVideoElement | null,
  mountPlayer: MountPlayer | undefined,
  changed: (video: HTMLVideoElement | null) => void,
) {
  const screen = room.querySelector<HTMLElement>('[data-room-player]')
  const status = room.querySelector<HTMLElement>('#room-status')
  const title = room.querySelector<HTMLElement>('[data-room-film-title]')
  const picker = room.querySelector<HTMLElement>('[data-room-picker]')
  const results = picker?.querySelector<HTMLElement>('[data-room-picker-results]')
  const open = room.querySelector<HTMLElement>('[data-room-picker-open]')
  const close = picker?.querySelector<HTMLButtonElement>('[data-room-picker-close]')
  const pickerStatus = picker?.querySelector<HTMLElement>('[data-room-picker-status]')
  const selectionEndpoint = room.dataset.selection
  let version = Number(room.dataset.mediaVersion) || 1
  let signature = [version, room.dataset.episodeId || '', room.dataset.canWatch === 'true'].join(':')
  let disposePlayer = initialVideo && mountPlayer ? mountPlayer(initialVideo) : undefined
  let mediaRequest: AbortController | undefined
  let pendingSignature = ''
  let pickerRequest: AbortController | undefined
  let disposed = false
  let selecting = false

  function roomUrl(path: string) {
    const url = new URL(path, window.location.href)
    const roomPath = new URL(room.dataset.state || '', window.location.href).pathname.replace(/state\/$/, '')
    if (url.origin !== location.origin || !url.pathname.startsWith(roomPath)) throw new Error('Địa chỉ phòng không hợp lệ.')
    return url.href
  }

  async function apply(state: RoomMediaState) {
    if (disposed || !Number.isSafeInteger(state.media_version) || state.media_version! < version) return
    version = state.media_version!
    room.dataset.mediaVersion = String(version)
    const next = [version, state.episode_id ?? '', Boolean(state.can_watch)].join(':')
    if (title) title.textContent = state.title ? state.title + (state.episode_title ? ' · ' + state.episode_title : '') : 'Chưa chọn phim'
    for (const input of room.querySelectorAll<HTMLInputElement>('input[name=media_version]')) input.value = String(version)
    if (!screen || !state.player_url || next === signature || next === pendingSignature) return

    mediaRequest?.abort()
    const controller = new AbortController()
    mediaRequest = controller
    pendingSignature = next
    changed(null)
    disposePlayer?.()
    disposePlayer = undefined
    screen.setAttribute('aria-busy', 'true')
    const loading = document.createElement('p')
    loading.className = 'room-waiting'
    loading.textContent = 'Đang chuyển phim cho phòng…'
    screen.replaceChildren(loading)
    try {
      const response = await fetch(roomUrl(state.player_url), {credentials: 'same-origin', signal: controller.signal})
      if (!response.ok || response.redirected) throw new Error('Chưa thể tải phim trong phòng.')
      const html = await response.text()
      if (disposed || controller.signal.aborted) return
      const parsed = document.createElement('template')
      parsed.innerHTML = html
      const fragment = parsed.content.querySelector<HTMLElement>('[data-media-version][data-can-watch]')
      if (!fragment || fragment.dataset.mediaVersion !== String(version) || fragment.dataset.canWatch !== String(Boolean(state.can_watch))) {
        throw new Error('Phim vừa thay đổi. Đang cập nhật lại…')
      }
      screen.replaceChildren(fragment)
      const video = screen.querySelector<HTMLVideoElement>('video#player')
      if (video && mountPlayer) disposePlayer = mountPlayer(video)
      changed(video)
      signature = next
      if (status) status.textContent = ''
    } catch (error) {
      if (!controller.signal.aborted && status) status.textContent = error instanceof Error ? error.message : 'Không thể chuyển phim.'
    } finally {
      if (mediaRequest === controller) {
        mediaRequest = undefined
        pendingSignature = ''
        screen.removeAttribute('aria-busy')
      }
    }
  }

  function pickerFeedback(message: string, error = false) {
    if (pickerStatus && picker && !picker.hidden) {
      pickerStatus.textContent = message
      pickerStatus.dataset.error = String(error)
    }
    if (error && status) status.textContent = message
  }

  async function loadPicker(path: string, focusSearch = false) {
    if (!results || disposed) return
    pickerRequest?.abort()
    const controller = new AbortController()
    pickerRequest = controller
    results.setAttribute('aria-busy', 'true')
    try {
      const response = await fetch(roomUrl(path), {
        credentials: 'same-origin', signal: controller.signal,
        headers: {'X-Lumiere-Room-Selection': '1'},
      })
      if (!response.ok || response.redirected) throw new Error('Không thể tải danh sách phim.')
      const html = await response.text()
      if (disposed || controller.signal.aborted) return
      const parsed = document.createElement('template')
      parsed.innerHTML = html
      const content = parsed.content.querySelector('[data-room-picker-content]')
      if (!content) throw new Error('Danh sách phim chưa sẵn sàng.')
      results.replaceChildren(content)
      if (focusSearch && picker && !picker.hidden) {
        results.querySelector<HTMLInputElement>('input[type="search"]')?.focus({preventScroll: true})
      }
    } catch (error) {
      if (!controller.signal.aborted) pickerFeedback(error instanceof Error ? error.message : 'Không thể tìm phim.', true)
    } finally {
      if (pickerRequest === controller) {
        pickerRequest = undefined
        results.removeAttribute('aria-busy')
      }
    }
  }

  const events = new AbortController()
  if (open && picker && results && selectionEndpoint) {
    const closePicker = () => {
      pickerRequest?.abort()
      picker.hidden = true
      open.setAttribute('aria-expanded', 'false')
      open.focus({preventScroll: true})
    }
    open.addEventListener('click', event => {
      event.preventDefault()
      picker.hidden = false
      open.setAttribute('aria-expanded', 'true')
      pickerFeedback('')
      picker.focus({preventScroll: true})
      void loadPicker(selectionEndpoint, true)
    }, {signal: events.signal})
    close?.addEventListener('click', closePicker, {signal: events.signal})
    document.addEventListener('keydown', event => {
      if (picker.hidden) return
      if (event.key === 'Escape') {
        event.preventDefault()
        event.stopPropagation()
        closePicker()
        return
      }
      if (event.key !== 'Tab') return
      const focusable = Array.from(picker.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )).filter(element => !element.hidden && element.tabIndex >= 0 && element.getClientRects().length > 0)
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (!first || !last) {
        event.preventDefault()
        picker.focus({preventScroll: true})
      } else if (event.shiftKey && (document.activeElement === first || document.activeElement === picker || !picker.contains(document.activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (document.activeElement === last || document.activeElement === picker || !picker.contains(document.activeElement))) {
        event.preventDefault()
        first.focus()
      }
    }, {signal: events.signal})
    picker.addEventListener('click', event => {
      const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('[data-room-picker-page]') : null
      if (!link || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
      event.preventDefault()
      void loadPicker(link.href)
    }, {signal: events.signal})
    picker.addEventListener('submit', async event => {
      const form = event.target
      if (!(form instanceof HTMLFormElement)) return
      if (form.matches('[data-room-search-form]')) {
        event.preventDefault()
        const url = new URL(form.getAttribute('action') || selectionEndpoint, window.location.href)
        url.search = ''
        for (const [key, value] of new FormData(form)) {
          if (typeof value === 'string') url.searchParams.set(key, value)
        }
        await loadPicker(url.href)
        return
      }
      if (!form.matches('[data-room-selection-form]')) return
      event.preventDefault()
      if (selecting || disposed) return
      selecting = true
      const button = form.querySelector<HTMLButtonElement>('button')
      if (button) button.disabled = true
      form.setAttribute('aria-busy', 'true')
      try {
        const response = await fetch(roomUrl(form.getAttribute('action') || selectionEndpoint), {
          method: 'POST', credentials: 'same-origin', body: new FormData(form),
          headers: {'X-Lumiere-Room-Selection': '1'},
        })
        if (response.redirected || ![200, 409].includes(response.status)) throw new Error('Chưa thể chọn phim. Kiểm tra quyền xem và thử lại.')
        const state = await response.json() as RoomMediaState & {error?: string}
        await apply(state)
        if (response.status === 409) {
          await loadPicker(selectionEndpoint)
          pickerFeedback(state.error || 'Chủ phòng đã chọn phim khác. Vui lòng chọn lại.', true)
        } else {
          closePicker()
        }
      } catch (error) {
        pickerFeedback(error instanceof Error ? error.message : 'Không thể chọn phim.', true)
      } finally {
        selecting = false
        if (button) button.disabled = false
        form.removeAttribute('aria-busy')
      }
    }, {signal: events.signal})
  }

  return {
    apply,
    version: () => version,
    stop: () => {
      disposed = true
      mediaRequest?.abort()
      pickerRequest?.abort()
      events.abort()
      changed(null)
      disposePlayer?.()
    },
  }
}
