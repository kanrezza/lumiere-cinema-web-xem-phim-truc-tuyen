<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const { video, title, href, preference, viewer } = defineProps<{
  video: HTMLVideoElement
  title: string
  href: string
  preference: HTMLElement
  viewer: string
}>()
const key = `lumiere:autoplay-next:${viewer}`
const showNext = ref(false)
const enabled = ref(false)
const remaining = ref<number | null>(null)
const announcement = ref('')
const nextLink = ref<HTMLAnchorElement>()
const listeners = new AbortController()
const signal = listeners.signal
let timer: number | undefined

function stop(announce = false) {
  window.clearInterval(timer)
  timer = undefined
  remaining.value = null
  if (announce) announcement.value = 'Đã hủy tự phát tập tiếp theo.'
}

function clear() {
  stop()
  showNext.value = false
  announcement.value = ''
}

function setEnabled(event: Event) {
  enabled.value = (event.currentTarget as HTMLInputElement).checked
  try { localStorage.setItem(key, String(enabled.value)) } catch { /* Retain the in-page choice. */ }
  if (!enabled.value) stop(remaining.value !== null)
}

function showCountdown() {
  stop()
  showNext.value = true
  if (!enabled.value || document.hidden) {
    announcement.value = 'Tập tiếp theo đã sẵn sàng.'
    return
  }
  remaining.value = 7
  announcement.value = 'Tập tiếp theo sẽ tự phát sau 7 giây.'
  timer = window.setInterval(() => {
    if (!video.ended || document.hidden) return stop()
    if (remaining.value === null) return
    remaining.value -= 1
    if (remaining.value <= 0) {
      stop()
      window.location.assign(href)
    }
  }, 1000)
}

function cancel() {
  stop(true)
  nextLink.value?.focus()
}

onMounted(() => {
  try { enabled.value = localStorage.getItem(key) === 'true' } catch { /* Autoplay defaults to off. */ }
  video.addEventListener('ended', showCountdown, { signal })
  video.addEventListener('play', clear, { signal })
  video.addEventListener('seeking', () => { if (!video.ended) clear() }, { signal })
  document.addEventListener('visibilitychange', () => { if (document.hidden) stop() }, { signal })
  window.addEventListener('pagehide', clear, { signal })
  if (video.ended) showCountdown()
})
onUnmounted(() => { listeners.abort(); stop() })
</script>

<template>
  <Teleport :to="preference">
    <label class="watch-autoplay" data-autoplay-setting>
      <input :checked="enabled" type="checkbox" data-autoplay-next @change="setEnabled"> Tự phát tập tiếp theo
    </label>
  </Teleport>
  <section class="player-next" aria-labelledby="player-next-title" data-next-episode data-vue-next-episode="true" :hidden="!showNext">
    <p class="player-next-label">Tập tiếp theo</p>
    <h2 id="player-next-title">{{ title }}</h2>
    <p class="player-next-countdown" data-next-countdown :hidden="remaining === null">Tự phát sau <span data-next-seconds>{{ remaining ?? 7 }}</span> giây</p>
    <div class="player-next-actions">
      <a ref="nextLink" class="btn small" :href="href" data-next-link>Phát tập kế</a>
      <button type="button" class="btn small secondary" data-next-cancel :hidden="remaining === null" @click="cancel">Hủy tự phát</button>
    </div>
    <span class="sr-only" role="status" data-next-announcement>{{ announcement }}</span>
  </section>
</template>
