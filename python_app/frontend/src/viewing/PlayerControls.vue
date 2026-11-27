<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { formatTime, seekPosition } from './seek'
import type { PlayerQualityState } from './playback'

type CaptionChange = CustomEvent<{ selected?: string | number; remember?: boolean }>
type NativeVideo = HTMLVideoElement & { webkitEnterFullscreen?: () => void }
type FullscreenDocument = Document & { webkitFullscreenElement?: Element | null; webkitExitFullscreen?: () => Promise<void> | void }
type FullscreenElement = HTMLElement & { webkitRequestFullscreen?: () => Promise<void> | void }

const { video, wrap, status } = defineProps<{
  video: NativeVideo
  wrap: HTMLElement
  status: HTMLElement | null
}>()
const room = document.getElementById('room')
const premiere = video.dataset.premiere === 'true'
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
const qualityOptions = ref<PlayerQualityState['qualities']>([])
const selectedQuality = ref<number | 'auto'>('auto')
const maxQuality = ref(0)
const sourceMaxQuality = ref(0)
const settingsOpen = ref(false)
const settingsButton = ref<HTMLButtonElement>()
const settingsPanel = ref<HTMLElement>()
const qualitySummary = computed(() => selectedQuality.value === 'auto' ? 'Tự động' : selectedQuality.value + 'p')
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

function tell(message: string) {
  if (status) status.textContent = message
}

function updateTime() {
  duration.value = Number.isFinite(video.duration) ? Math.max(0, video.duration) : 0
  const fullDuration = Number(video.dataset.duration)
  if (premiere && Number.isFinite(fullDuration)) duration.value = Math.max(duration.value, fullDuration)
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

function seekTo(requested: number) {
  if (!canSeek || video.readyState < 1) return false
  const target = seekPosition(requested, video.duration, video.seekable)
  if (target === undefined) return false
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

function chooseQuality(height: number | 'auto') {
  if (height !== 'auto' && !qualityOptions.value.some(option => option.height === height)) return
  selectedQuality.value = height
  video.dispatchEvent(new CustomEvent('lumiere:quality-select', {detail: {height}}))
  closeSettings()
}

function changeQuality(event: Event) {
  const value = (event.currentTarget as HTMLInputElement).value
  chooseQuality(value === 'auto' ? 'auto' : Number(value))
}

function closeSettings(restoreFocus = true) {
  settingsOpen.value = false
  if (restoreFocus) settingsButton.value?.focus({preventScroll: true})
}

async function toggleSettings(event: MouseEvent) {
  if (settingsOpen.value) { closeSettings(); return }
  settingsOpen.value = true
  await nextTick()
  if (event.detail === 0) settingsPanel.value?.querySelector<HTMLInputElement>('input:checked')?.focus()
}

function updateQuality() {
  const width = video.videoWidth, height = video.videoHeight
  // A portrait720p rendition is1280px tall; its label follows the same
  // landscape/portrait quality box used by the encoder, not height alone.
  const resolution = width && height
    ? Math.ceil(Math.max(Math.min(width, height), Math.max(width, height) * 9 / 16))
    : height
  quality.value = resolution ? `${resolution}p` : ''
}

async function togglePlay() {
  if (!video.paused) video.pause()
  else {
    try { await video.play() } catch { tell('Chưa thể phát. Hãy thử lại khi video tải xong.') }
  }
}

async function toggleFullscreen() {
  const doc = document as FullscreenDocument
  const target = wrap as FullscreenElement
  try {
    if (doc.fullscreenElement) await doc.exitFullscreen()
    else if (doc.webkitFullscreenElement && doc.webkitExitFullscreen) await doc.webkitExitFullscreen()
    else if (target.requestFullscreen) await target.requestFullscreen()
    else if (target.webkitRequestFullscreen) await target.webkitRequestFullscreen()
    else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen()
    else tell('Trình duyệt này chưa hỗ trợ toàn màn hình cho video.')
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
  updateQuality()
  updateTime()
  updatePlaying()
  applySubtitles()
}

onMounted(() => {
  document.addEventListener('pointerdown', event => {
    if (settingsOpen.value && event.target instanceof Node && !settingsPanel.value?.contains(event.target) && !settingsButton.value?.contains(event.target)) closeSettings(false)
  }, {signal})
  document.addEventListener('keydown', event => {
    if (settingsOpen.value && event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); closeSettings() }
    if (settingsOpen.value && event.key === 'Tab') window.setTimeout(() => {
      if (!signal.aborted && settingsOpen.value && !settingsPanel.value?.contains(document.activeElement) && !settingsButton.value?.contains(document.activeElement)) closeSettings(false)
    }, 0)
  }, {signal})
  restoreSubtitle()
  subtitleSelector?.addEventListener('change', () => setSubtitle(subtitleSelector.value, true), { signal })
  video.textTracks.addEventListener('addtrack', applySubtitles, { signal })
  video.addEventListener('lumiere:captions-changed', event => {
    const { selected, remember } = (event as CaptionChange).detail ?? {}
    setSubtitle(String(selected ?? selectedSubtitle), Boolean(remember))
  }, { signal })
  window.addEventListener('resize', applySubtitles, { signal })
  video.addEventListener('webkitbeginfullscreen', () => { nativeFullscreen = true; fullscreen.value = true; applySubtitles() }, { signal })
  video.addEventListener('webkitendfullscreen', () => { nativeFullscreen = false; fullscreen.value = false; applySubtitles() }, { signal })
  const updateFullscreen = () => {
    const doc = document as FullscreenDocument
    fullscreen.value = Boolean(doc.fullscreenElement || doc.webkitFullscreenElement)
    applySubtitles()
  }
  document.addEventListener('fullscreenchange', updateFullscreen, { signal })
  document.addEventListener('webkitfullscreenchange', updateFullscreen, { signal })
  updateFullscreen()
  wrap.addEventListener('keydown', applyKeyboard, { signal })
  video.addEventListener('loadedmetadata', markReady, { signal })
  video.addEventListener('resize', updateQuality, { signal })
  video.addEventListener('lumiere:qualities', event => {
    const state = (event as CustomEvent<PlayerQualityState>).detail
    qualityOptions.value = state.qualities
    selectedQuality.value = state.selected
    maxQuality.value = state.maxQuality
    sourceMaxQuality.value = state.sourceMaxQuality ?? 0
  }, { signal })
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
      <button v-if="!premiere" type="button" class="player-control player-seek" data-player-action="back" aria-label="Lùi 10 giây" title="Lùi 10 giây" :disabled="!canSeek" @click="skip(-10)"><svg class="player-seek-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 10a9 9 0 1 1 .8 6.6M3 4v6h6"/><text x="12.5" y="15">10</text></svg></button>
      <button v-if="!premiere" type="button" class="player-control player-seek" data-player-action="forward" aria-label="Tua 10 giây" title="Tua 10 giây" :disabled="!canSeek" @click="skip(10)"><svg class="player-seek-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 10a9 9 0 1 1 .8 6.6M3 4v6h6" transform="translate(24 0) scale(-1 1)"/><text x="11.5" y="15">10</text></svg></button>
      <span class="player-time"><span data-player-time>{{ formatTime(position) }}</span> / <span data-player-duration>{{ formatTime(duration) }}</span></span>
      <div class="player-end-controls">
        <button type="button" class="player-control" data-player-action="mute" :aria-label="muted ? 'Bật tiếng' : 'Tắt tiếng'" @click="video.muted = !video.muted"><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9h4l5-4v14l-5-4H4V9Zm12-1a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/></svg></button>
        <input type="range" class="player-volume" min="0" max="1" step=".05" :value="volume" aria-label="Âm lượng" @input="changeVolume">
        <button ref="settingsButton" type="button" class="player-settings-trigger" data-player-settings-toggle aria-label="Cài đặt chất lượng và phụ đề" aria-haspopup="dialog" :aria-expanded="settingsOpen" aria-controls="player-settings-panel" @click="toggleSettings"><span class="player-settings-resolution">{{ quality }}</span><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 3-.7 2.5-2.4 1L3.7 6l-2 3.5 1.8 1.8v2.8l-1.8 1.8 2 3.5 2.2-.5 2.4 1L9 22h4l.7-2.1 2.4-1 2.2.5 2-3.5-1.8-1.8v-2.8l1.8-1.8-2-3.5-2.2.5-2.4-1L13 3H9Z" transform="translate(1 -.5) scale(.95)"/><circle cx="11.5" cy="12" r="3.2"/></svg></button>
        <button type="button" class="player-control" data-player-action="fullscreen" :aria-label="fullscreen ? 'Thoát toàn màn hình' : 'Toàn màn hình'" @click="toggleFullscreen"><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/></svg></button>
      </div>
    </div>
  </div>
  <section v-show="settingsOpen" id="player-settings-panel" ref="settingsPanel" class="player-settings-panel" role="dialog" aria-modal="false" aria-labelledby="player-settings-title" @keydown.esc.prevent.stop="closeSettings()" @keydown.left.stop @keydown.right.stop>
    <header><h2 id="player-settings-title">Cài đặt phát</h2><button type="button" class="player-settings-close" aria-label="Đóng cài đặt phát" @click="closeSettings()">×</button></header>
    <button type="button" class="player-settings-caption" data-caption-toggle aria-label="Phụ đề và dịch tự động" aria-haspopup="dialog" aria-expanded="false" aria-controls="caption-panel" @click="closeSettings(false)"><span class="player-settings-cc" aria-hidden="true">CC</span><span>Phụ đề và dịch tự động</span><span aria-hidden="true">›</span></button>
    <fieldset v-if="qualityOptions.length" class="player-settings-quality"><legend>Chất lượng <span>{{ qualitySummary }}</span></legend>
      <label class="player-quality-option"><input type="radio" name="player-quality" value="auto" :checked="selectedQuality === 'auto'" @change="changeQuality"><span>Tự động <small>Phù hợp đường truyền</small></span><svg v-if="selectedQuality === 'auto'" viewBox="0 0 20 20" aria-hidden="true"><path d="m4 10 4 4 8-8"/></svg></label>
      <label v-for="option in [...qualityOptions].reverse()" :key="option.height" class="player-quality-option"><input type="radio" name="player-quality" :value="option.height" :checked="selectedQuality === option.height" @change="changeQuality"><span>{{ option.label }}<small v-if="option.height >= 1080">{{ option.height >= 1440 ? '2K' : 'Full HD' }}</small></span><svg v-if="selectedQuality === option.height" viewBox="0 0 20 20" aria-hidden="true"><path d="m4 10 4 4 8-8"/></svg></label>
    </fieldset>
    <p v-if="sourceMaxQuality && maxQuality > sourceMaxQuality" class="player-source-note">Phim này hiện có tối đa <strong>{{ sourceMaxQuality }}p</strong>. Gói của bạn hỗ trợ đến {{ maxQuality }}p.</p>
    <p v-else-if="maxQuality" class="player-source-note">Gói của bạn hỗ trợ đến {{ maxQuality }}p. Chất lượng còn tùy nguồn phim.</p>
  </section>
</template>
