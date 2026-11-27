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

export interface PlaybackQuality {
  height: number
  label: string
  url: string
}
export interface PlayerQualityState {
  qualities: Array<Pick<PlaybackQuality, 'height' | 'label'>>
  selected: number | 'auto'
  maxQuality: number
  sourceMaxQuality?: number
}
interface PlaybackTicket {
  url: string
  qualities?: PlaybackQuality[]
  max_quality?: number
  source_max_quality?: number
}

function safePosition(value: string | number | undefined) {
  const position = Number(value)
  return Number.isFinite(position) ? Math.max(0, position) : 0
}

export function initPlayback(video: HTMLVideoElement) {
  const ticketUrl = video.dataset.ticket
  const progressUrl = video.dataset.progress
  const premiere = video.dataset.premiere === 'true'
  const status = document.getElementById('player-status')
  const retry = document.getElementById('retry-player')
  if (!ticketUrl || (!progressUrl && !premiere) || !status || !retry) return

  const Hls = (window as Window & {Hls?: HlsLibrary}).Hls
  let hls: HlsInstance | undefined
  let first = true
  let loading = false
  let stopped = false
  let generation = 0
  let requestedPosition: number | null = null
  let hasPlayed = false
  let qualities: PlaybackQuality[] = []
  let selectedHeight: number | 'auto' = 'auto'
  let removeReady = () => {}

  const canSaveProgress = () => !premiere && video.dataset.saveProgress !== 'false' && hasPlayed && !stopped && video.currentTime > 0 && video.dataset.loading !== 'true'
  const saveProgress = () => {
    if (progressUrl && canSaveProgress()) void postForm(progressUrl, {position: video.currentTime}).catch(() => {})
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
      const ticket = await postForm<PlaybackTicket>(ticketUrl, {})
      if (stopped || current !== generation) return
      // Each change obtains fresh server-authorized URLs; a previous VIP
      // selection falls back to Auto when the current plan no longer allows it.
      qualities = (ticket.qualities ?? []).filter((option, index, all) =>
        Number.isInteger(option.height) && option.height > 0 && typeof option.url === 'string' && option.url &&
        all.findIndex(other => other.height === option.height) === index,
      ).sort((a, b) => a.height - b.height)
      const chosen = qualities.find(option => option.height === selectedHeight)
      if (selectedHeight !== 'auto' && !chosen) selectedHeight = 'auto'
      video.dispatchEvent(new CustomEvent<PlayerQualityState>('lumiere:qualities', {detail: {
        qualities: qualities.map(option => ({height: option.height, label: `${option.height}p`})),
        selected: selectedHeight,
        maxQuality: Number.isFinite(ticket.max_quality) ? Number(ticket.max_quality) : 0,
        sourceMaxQuality: Number.isFinite(ticket.source_max_quality) ? Number(ticket.source_max_quality) : undefined,
      }}))
      const source = chosen?.url ?? ticket.url
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
        hls.loadSource(source)
        hls.attachMedia(video)
      } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
        video.src = source
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

  const onPlaying = () => {
    hasPlayed = true
    if (!stopped && video.dataset.loading !== 'true') status.textContent = premiere ? 'Đang công chiếu' : 'Đang phát'
  }
  const onQualitySelect = (event: Event) => {
    const height = (event as CustomEvent<{height?: number | 'auto'}>).detail?.height
    if (height !== 'auto' && (typeof height !== 'number' || !qualities.some(option => option.height === height))) return
    if (selectedHeight === height) return
    selectedHeight = height
    void loadSource()
  }
  const onSeek = (event: Event) => {
    if (loading || video.dataset.loading === 'true') {
      requestedPosition = safePosition((event as CustomEvent<{position: number}>).detail.position)
    }
  }
  video.addEventListener('playing', onPlaying)
  video.addEventListener('lumiere:seek', onSeek)
  video.addEventListener('lumiere:quality-select', onQualitySelect)
  retry.addEventListener('click', loadSource)
  video.addEventListener('ended', saveProgress)
  video.addEventListener('pause', saveProgress)
  const renewal = window.setInterval(loadSource, 480000)
  const progress = window.setInterval(() => { if (!video.paused) saveProgress() }, 15000)
  const dispose = () => {
    if (stopped) return
    saveProgress()
    stopped = true
    generation += 1
    window.clearInterval(renewal)
    window.clearInterval(progress)
    video.removeEventListener('playing', onPlaying)
    video.removeEventListener('lumiere:seek', onSeek)
    video.removeEventListener('lumiere:quality-select', onQualitySelect)
    retry.removeEventListener('click', loadSource)
    video.removeEventListener('ended', saveProgress)
    video.removeEventListener('pause', saveProgress)
    document.removeEventListener('lumiere:stop', dispose)
    window.removeEventListener('pagehide', onPageHide)
    removeReady()
    hls?.destroy()
    video.pause()
    video.removeAttribute('src')
    video.load()
  }
  const onPageHide = () => {
    if (progressUrl && canSaveProgress()) {
      navigator.sendBeacon?.(progressUrl, formParams({position: video.currentTime, csrfmiddlewaretoken: csrfToken()}))
    }
  }
  document.addEventListener('lumiere:stop', dispose, {once: true})
  window.addEventListener('pagehide', onPageHide)
  void loadSource()
  return dispose
}
