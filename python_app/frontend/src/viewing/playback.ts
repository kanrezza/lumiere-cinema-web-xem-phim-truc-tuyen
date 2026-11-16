import { csrfToken, formParams, postForm } from '../shared/http'

interface HlsInstance {
  loadSource(url: string): void
  attachMedia(video: HTMLVideoElement): void
  destroy(): void
  on(event: string, callback: (event: string, data: {fatal: boolean}) => void): void
}
interface HlsLibrary {
  new (options: {enableWorker: boolean}): HlsInstance
  Events: {ERROR: string}
  isSupported(): boolean
}

function safePosition(value: string | number | undefined) {
  const position = Number(value)
  return Number.isFinite(position) ? Math.max(0, position) : 0
}

export function initPlayback(video: HTMLVideoElement) {
  const ticketUrl = video.dataset.ticket
  const progressUrl = video.dataset.progress
  const status = document.getElementById('player-status')
  const retry = document.getElementById('retry-player')
  if (!ticketUrl || !progressUrl || !status || !retry) return

  const Hls = (window as Window & {Hls?: HlsLibrary}).Hls
  let hls: HlsInstance | undefined
  let first = true
  let loading = false
  let stopped = false
  let generation = 0
  let requestedPosition: number | null = null
  let hasPlayed = false
  let removeReady = () => {}

  const canSaveProgress = () => hasPlayed && !stopped && video.currentTime > 0 && video.dataset.loading !== 'true'
  const saveProgress = () => {
    if (canSaveProgress()) void postForm(progressUrl, {position: video.currentTime}).catch(() => {})
  }
  const showFailure = (message: string) => {
    removeReady()
    video.dataset.loading = 'false'
    status.textContent = message
    retry.hidden = false
  }

  async function resume(playing: boolean, playOnReady: boolean, current: number) {
    if (!playing && !playOnReady) return
    try {
      await video.play()
    } catch {
      if (playOnReady && !stopped && current === generation) {
        const message = document.getElementById('player-status')
        if (message) message.textContent = 'Nhấn Phát để bắt đầu tập này.'
      }
    }
  }

  const loadSource = async () => {
    if (loading || stopped) return
    loading = true
    video.dataset.loading = 'true'
    requestedPosition = null
    const current = ++generation
    try {
      const ticket = await postForm<{url: string}>(ticketUrl, {})
      if (stopped || current !== generation) return
      const position = requestedPosition ?? safePosition(first ? video.dataset.position : video.currentTime)
      const playing = !video.paused
      removeReady()
      hls?.destroy()
      hls = undefined

      const ready = () => {
        if (stopped || current !== generation || video.readyState < 1 || !Number.isFinite(video.duration) || video.duration <= 0) return
        try {
          video.currentTime = Math.min(requestedPosition ?? position, video.duration)
        } catch { return }
        removeReady()
        const playOnReady = first && video.dataset.playOnReady === 'true'
        first = false
        status.textContent = 'Sẵn sàng phát'
        retry.hidden = true
        video.dataset.loading = 'false'
        void resume(playing, playOnReady, current)
      }
      video.addEventListener('loadedmetadata', ready)
      video.addEventListener('durationchange', ready)
      removeReady = () => {
        video.removeEventListener('loadedmetadata', ready)
        video.removeEventListener('durationchange', ready)
      }
      if (Hls?.isSupported()) {
        hls = new Hls({enableWorker: true})
        hls.on(Hls.Events.ERROR, (_event, data) => {
          if (data.fatal && !stopped && current === generation) {
            showFailure('Không thể phát video. Nguồn phát có thể đã hết hạn hoặc phiên đang được dùng ở thiết bị khác.')
          }
        })
        hls.loadSource(ticket.url)
        hls.attachMedia(video)
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = ticket.url
      } else {
        showFailure('Trình duyệt này chưa hỗ trợ phát HLS. Hãy dùng trình duyệt hiện đại.')
      }
    } catch (error) {
      if (!stopped && current === generation) {
        showFailure(error instanceof Error ? error.message : 'Chưa thể lấy nguồn phát. Hãy thử lại.')
      }
    } finally {
      loading = false
    }
  }

  video.addEventListener('playing', () => { hasPlayed = true })
  video.addEventListener('lumiere:seek', event => {
    if (loading || video.dataset.loading === 'true') {
      requestedPosition = safePosition((event as CustomEvent<{position: number}>).detail.position)
    }
  })
  retry.addEventListener('click', loadSource)
  video.addEventListener('ended', saveProgress)
  video.addEventListener('pause', saveProgress)
  const renewal = window.setInterval(loadSource, 480000)
  const progress = window.setInterval(() => { if (!video.paused) saveProgress() }, 15000)
  document.addEventListener('lumiere:stop', () => {
    stopped = true
    generation += 1
    window.clearInterval(renewal)
    window.clearInterval(progress)
    removeReady()
    hls?.destroy()
    video.pause()
    video.removeAttribute('src')
    video.load()
  }, {once: true})
  window.addEventListener('pagehide', () => {
    if (canSaveProgress()) {
      navigator.sendBeacon?.(progressUrl, formParams({position: video.currentTime, csrfmiddlewaretoken: csrfToken()}))
    }
  })
  void loadSource()
}
