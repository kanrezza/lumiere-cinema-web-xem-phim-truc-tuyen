<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

const { player, button, placeholder, status } = defineProps<{
  player: HTMLElement
  button: HTMLButtonElement | null
  placeholder: HTMLElement | null
  status: HTMLElement | null
}>()

const video = player.querySelector<HTMLVideoElement>('video')
const iframe = ref<HTMLIFrameElement>()
const source = ref('')
const initialStatus = status?.textContent ?? ''
const message = ref(initialStatus)
const title = button?.dataset.trailerTitle ?? ''
const listeners = new AbortController()
const signal = listeners.signal

watch(message, text => { if (status) status.textContent = text })

async function loadTrailer() {
  if (source.value || !button) return
  try {
    const url = new URL(button.dataset.trailerEmbed ?? '')
    if (url.origin !== 'https://www.youtube-nocookie.com' || url.username || url.password || !/^\/embed\/[A-Za-z0-9_-]{11}$/.test(url.pathname)) {
      throw new Error('Unsupported trailer source')
    }
    url.searchParams.set('autoplay', '1')
    source.value = url.href
  } catch {
    message.value = 'Chưa thể mở trailer. Bạn có thể thử liên kết YouTube bên dưới.'
    return
  }
  if (placeholder) placeholder.hidden = true
  message.value = 'Đã mở trình phát YouTube. Nếu video không tải được, dùng liên kết bên dưới.'
  await nextTick()
  iframe.value?.focus()
}

function resetTrailer() {
  video?.pause()
  if (!source.value) return
  source.value = ''
  if (placeholder) placeholder.hidden = false
  message.value = initialStatus
}

onMounted(() => {
  button?.addEventListener('click', loadTrailer, { signal })
  video?.addEventListener('error', () => {
    message.value = 'Chưa thể phát trailer. Hãy tải lại trang để thử lại.'
  }, { signal })
  video?.addEventListener('playing', () => { message.value = 'Đang phát trailer.' }, { signal })
  video?.addEventListener('pause', () => {
    if (!video.error) message.value = video.ended ? 'Đã phát hết trailer.' : 'Trailer đang tạm dừng.'
  }, { signal })
  window.addEventListener('pagehide', resetTrailer, { signal })
})
onUnmounted(() => { listeners.abort(); resetTrailer() })
</script>

<template>
  <Teleport :to="player">
    <iframe v-if="source" ref="iframe" :src="source" class="trailer-frame" :title="`Trailer ${title}`.trim()"
            sandbox="allow-scripts allow-same-origin allow-presentation" allow="autoplay; encrypted-media; picture-in-picture"
            referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
  </Teleport>
</template>
