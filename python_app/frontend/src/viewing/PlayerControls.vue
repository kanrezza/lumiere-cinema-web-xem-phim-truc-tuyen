<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

type CaptionChange = CustomEvent<{ selected?: string | number; remember?: boolean }>
type NativeVideo = HTMLVideoElement & { webkitEnterFullscreen?: () => void }

const { video, wrap, status } = defineProps<{
  video: NativeVideo
  wrap: HTMLElement
  status: HTMLElement | null
}>()
const room = document.getElementById('room')
const canSeek = wrap.dataset.canSeek !== 'false' && (!room || room.dataset.host === 'true')
const ready = ref(false)
const playing = ref(false)
const ended = ref(false)
const muted = ref(video.muted)
const volume = ref(video.muted ? 0 : video.volume)
const fullscreen = ref(false)
const position = ref(0)
const duration = ref(0)
const quality = ref('')
const canUseRange = computed(() => canSeek && ready.value && duration.value > 0)
const seekLabel = computed(() => `${formatTime(position.value)} trên ${formatTime(duration.value)}`)

const listeners = new AbortController()
const signal = listeners.signal
const subtitleSelector = wrap.querySelector<HTMLSelectElement>('.player-subtitles')
const captionDisplay = wrap.querySelector<HTMLElement>('[data-caption-display]')
const captionText = wrap.querySelector<HTMLElement>('[data-caption-text]')
const subtitleKey = wrap.dataset.viewer ? `lumiere:subtitle:${wrap.dataset.viewer}` : ''
const boundTracks = new WeakSet<HTMLTrackElement>()

let tracks = subtitleTracks()
let selectedSubtitle = 'off'
let pendingSeek: number | null = null
let nativeFullscreen = false

function subtitleTracks() {
  return [...video.querySelectorAll<HTMLTrackElement>('track[data-subtitle]')]
}

function formatTime(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds + 0.001))
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`
}

function tell(message: string) {
  if (status) status.textContent = message
}

function updateTime() {
  duration.value = Number.isFinite(video.duration) ? Math.max(0, video.duration) : 0
  position.value = pendingSeek ?? (Number.isFinite(video.currentTime) ? video.currentTime : 0)
}

function updatePlaying() {
  ended.value = video.ended
  playing.value = !video.paused && !video.ended
  wrap.classList.toggle('is-playing', playing.value)
}

function updateVolume() {
  muted.value = video.muted
  volume.value = video.muted ? 0 : video.volume
}

function seekTo(target: number) {
  const limit = video.duration
  if (!canSeek || video.readyState < 1 || !Number.isFinite(limit) || limit <= 0 || !Number.isFinite(target)) return false
  target = Math.max(0, Math.min(limit, target))
  // A seek across discontinuous HLS windows must land on a seekable boundary.
  const windows: Array<[number, number]> = []
  for (let index = 0; index < video.seekable.length; index += 1) {
    const start = Math.max(0, video.seekable.start(index))
    const end = Math.min(limit, video.seekable.end(index))
    if (Number.isFinite(start) && Number.isFinite(end) && start <= end) windows.push([start, end])
  }
  if (windows.length && !windows.some(([start, end]) => target >= start && target <= end)) {
    target = windows.flat().reduce((nearest, boundary) =>
      Math.abs(boundary - target) < Math.abs(nearest - target) ? boundary : nearest)
  }
  const previous = pendingSeek
  try {
    const unchanged = !video.seeking && Math.abs(video.currentTime - target) < 0.001
    pendingSeek = unchanged ? null : target
    if (!unchanged) video.currentTime = target
    updateTime()
    video.dispatchEvent(new CustomEvent('lumiere:seek', { detail: { position: target } }))
    tell(`Đã tua đến ${formatTime(target)}.`)
    return true
  } catch {
    pendingSeek = previous
    updateTime()
    tell('Chưa thể tua ở vị trí này. Hãy đợi video tải xong rồi thử lại.')
    return false
  }
}

function skip(amount: number) {
  return seekTo((pendingSeek ?? video.currentTime) + amount)
}

function seekFromRange(event: Event) {
  const input = event.currentTarget as HTMLInputElement
  seekTo(input.valueAsNumber)
  input.value = String(position.value)
}

function changeVolume(event: Event) {
  video.volume = (event.currentTarget as HTMLInputElement).valueAsNumber
  video.muted = video.volume === 0
}

async function togglePlay() {
  if (!video.paused) video.pause()
  else {
    try { await video.play() } catch { tell('Chưa thể phát. Hãy thử lại khi video tải xong.') }
  }
}

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else if (wrap.requestFullscreen) await wrap.requestFullscreen()
    else video.webkitEnterFullscreen?.()
  } catch {
    tell('Không thể mở toàn màn hình trong trình duyệt này.')
  }
}

function applyKeyboard(event: KeyboardEvent) {
  if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  if (event.target instanceof Element && event.target.closest('input, select, textarea, [contenteditable="true"], [role="textbox"], [data-caption-panel]')) return
  if (skip(event.key === 'ArrowLeft' ? -10 : 10)) event.preventDefault()
}

function rememberSubtitle() {
  if (!subtitleKey) return
  const language = selectedSubtitle === 'off' ? 'off' : tracks[Number(selectedSubtitle)]?.srclang.toLowerCase()
  if (language) {
    try { localStorage.setItem(subtitleKey, language) } catch { /* The selected track stays active. */ }
  }
}

function setCuePosition(element: HTMLTrackElement) {
  const line = wrap.clientWidth > 0 && wrap.clientWidth <= 600 ? -2 : -5
  for (const cue of Array.from(element.track.cues ?? [])) {
    const vtt = cue as VTTCue
    vtt.snapToLines = true
    vtt.line = line
  }
}

function renderCaptions() {
  if (!captionDisplay || !captionText) return
  const selected = selectedSubtitle === 'off' ? undefined : tracks[Number(selectedSubtitle)]
  const text = Array.from(selected?.track.activeCues ?? [], cue => {
    const vtt = cue as VTTCue
    return vtt.getCueAsHTML?.().textContent ?? vtt.text ?? ''
  }).join('\n')
  captionText.textContent = text
  captionDisplay.hidden = !text || nativeFullscreen
}

function applySubtitles() {
  tracks = subtitleTracks()
  const selected = selectedSubtitle === 'off' ? -1 : Number(selectedSubtitle)
  tracks.forEach((element, index) => {
    if (!boundTracks.has(element)) {
      boundTracks.add(element)
      const update = () => {
        setCuePosition(element)
        renderCaptions()
      }
      element.addEventListener('load', update, { signal })
      element.track.addEventListener('cuechange', update, { signal })
      element.addEventListener('error', () => {
        if (tracks[Number(selectedSubtitle)] === element) tell('Không tải được phụ đề đã chọn. Bạn có thể tắt hoặc chọn ngôn ngữ khác.')
      }, { signal })
    }
    element.track.mode = index === selected ? (captionDisplay && !nativeFullscreen ? 'hidden' : 'showing') : 'disabled'
    setCuePosition(element)
  })
  if (subtitleSelector) subtitleSelector.value = selectedSubtitle
  renderCaptions()
}

function setSubtitle(value: string, remember: boolean) {
  tracks = subtitleTracks()
  selectedSubtitle = /^\d+$/.test(value) && Number(value) < tracks.length ? value : 'off'
  applySubtitles()
  if (remember) rememberSubtitle()
}

function restoreSubtitle() {
  if (!subtitleKey) return
  try {
    const language = localStorage.getItem(subtitleKey)
    if (!language || language === 'off') return
    let index = tracks.findIndex(track => track.srclang.toLowerCase() === language)
    if (index < 0) {
      const primary = language.split('-')[0]
      index = tracks.findIndex(track => track.srclang.toLowerCase().split('-')[0] === primary)
    }
    if (index >= 0) selectedSubtitle = String(index)
  } catch { /* Captions start off when storage is unavailable. */ }
}

function markReady() {
  ready.value = true
  video.controls = false
  quality.value = video.videoHeight ? `${video.videoHeight}p` : ''
  updateTime()
  updatePlaying()
  applySubtitles()
}

onMounted(() => {
  restoreSubtitle()
  subtitleSelector?.addEventListener('change', () => setSubtitle(subtitleSelector.value, true), { signal })
  video.textTracks.addEventListener('addtrack', applySubtitles, { signal })
  video.addEventListener('lumiere:captions-changed', event => {
    const { selected, remember } = (event as CaptionChange).detail ?? {}
    setSubtitle(String(selected ?? selectedSubtitle), Boolean(remember))
  }, { signal })
  window.addEventListener('resize', applySubtitles, { signal })
  video.addEventListener('webkitbeginfullscreen', () => { nativeFullscreen = true; applySubtitles() }, { signal })
  video.addEventListener('webkitendfullscreen', () => { nativeFullscreen = false; applySubtitles() }, { signal })
  document.addEventListener('fullscreenchange', () => {
    fullscreen.value = Boolean(document.fullscreenElement)
    applySubtitles()
  }, { signal })
  wrap.addEventListener('keydown', applyKeyboard, { signal })
  video.addEventListener('loadedmetadata', markReady, { signal })
  video.addEventListener('durationchange', updateTime, { signal })
  video.addEventListener('volumechange', updateVolume, { signal })
  video.addEventListener('timeupdate', () => {
    updateTime()
    for (const track of tracks) if (track.track.mode === 'showing') setCuePosition(track)
    renderCaptions()
  }, { signal })
  video.addEventListener('seeked', () => {
    pendingSeek = null
    updateTime()
    updatePlaying()
  }, { signal })
  video.addEventListener('emptied', () => {
    pendingSeek = null
    ready.value = false
    updateTime()
  }, { signal })
  for (const event of ['play', 'pause', 'ended']) video.addEventListener(event, updatePlaying, { signal })
  video.addEventListener('error', () => {
    pendingSeek = null
    video.controls = true
    ready.value = false
  }, { signal })
  applySubtitles()
  if (video.readyState >= 1 && !video.error) markReady()
})

onUnmounted(() => listeners.abort())
</script>

<template>
  <button type="button" class="player-center" data-player-action="play" :aria-label="ended ? 'Phát lại phim' : 'Phát phim'" :hidden="!ready" @click="togglePlay"><svg class="icon" aria-hidden="true"><use href="#i-play"/></svg></button>
  <div class="player-controls" :hidden="!ready">
    <input class="player-range" type="range" min="0" :max="duration || 100" :value="position" step="1" aria-label="Vị trí phát" :aria-valuetext="seekLabel" :disabled="!canUseRange" @input="seekFromRange">
    <div class="player-controls-row">
      <button type="button" class="player-control player-toggle" data-player-action="play" :aria-label="playing ? 'Tạm dừng' : 'Phát'" @click="togglePlay"><svg class="icon" aria-hidden="true"><use href="#i-play"/></svg><span class="player-pause-symbol" aria-hidden="true">Ⅱ</span></button>
      <button type="button" class="player-control player-seek" data-player-action="back" aria-label="Lùi 10 giây" title="Lùi 10 giây" :disabled="!canSeek" @click="skip(-10)"><svg class="player-seek-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 10a9 9 0 1 1 .8 6.6M3 4v6h6"/><text x="12.5" y="15">10</text></svg></button>
      <button type="button" class="player-control player-seek" data-player-action="forward" aria-label="Tua 10 giây" title="Tua 10 giây" :disabled="!canSeek" @click="skip(10)"><svg class="player-seek-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 10a9 9 0 1 1 .8 6.6M3 4v6h6" transform="translate(24 0) scale(-1 1)"/><text x="11.5" y="15">10</text></svg></button>
      <span class="player-time"><span data-player-time>{{ formatTime(position) }}</span> / <span data-player-duration>{{ formatTime(duration) }}</span></span>
      <div class="player-end-controls">
        <button type="button" class="player-caption-toggle" data-caption-toggle aria-label="Phụ đề" aria-haspopup="dialog" aria-expanded="false" aria-controls="caption-panel"><span aria-hidden="true">CC</span><span>Phụ đề</span></button>
        <button type="button" class="player-control" data-player-action="mute" :aria-label="muted ? 'Bật tiếng' : 'Tắt tiếng'" @click="video.muted = !video.muted"><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4V9Zm12-1a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/></svg></button>
        <input type="range" class="player-volume" min="0" max="1" step=".05" :value="volume" aria-label="Âm lượng" @input="changeVolume">
        <span class="player-quality" data-player-quality>{{ quality }}</span>
        <button type="button" class="player-control" data-player-action="fullscreen" :aria-label="fullscreen ? 'Thoát toàn màn hình' : 'Toàn màn hình'" @click="toggleFullscreen"><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/></svg></button>
      </div>
    </div>
  </div>
</template>
