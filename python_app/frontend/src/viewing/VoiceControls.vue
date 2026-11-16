<script setup lang="ts">
import { onMounted, onUnmounted, shallowRef } from 'vue'

const props = defineProps<{ room: HTMLElement; initialMessage: string }>()
interface VoiceState {
  listening: boolean
  microphone: boolean
  joinDisabled: boolean
  micDisabled: boolean
  micState: 'muted' | 'live' | 'off'
  showAudio: boolean
  message: string
}

const state = shallowRef<VoiceState>({
  listening: false, microphone: false, joinDisabled: true, micDisabled: true,
  micState: 'off', showAudio: false, message: props.initialMessage,
})
function update(event: Event) {
  state.value = (event as CustomEvent<VoiceState>).detail
}
onMounted(() => props.room.addEventListener('lumiere:voice-state', update))
onUnmounted(() => props.room.removeEventListener('lumiere:voice-state', update))
</script>

<template>
  <div class="room-voice-actions">
    <button class="btn small" type="button" data-voice-join :aria-pressed="state.listening"
            :data-active="String(state.listening)" :disabled="state.joinDisabled">
      <svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><path d="M3 14v-2a9 9 0 0 1 18 0v2M3 15a3 3 0 0 1 3-3h1v8H6a3 3 0 0 1-3-3Zm18 0a3 3 0 0 0-3-3h-1v8h1a3 3 0 0 0 3-3Z" /></svg>
      <span data-voice-label>{{ state.listening ? 'Rời thoại' : 'Tham gia thoại' }}</span>
    </button>
    <button class="btn secondary small" type="button" data-voice-mic :aria-pressed="state.microphone"
            :data-active="String(state.microphone)" :data-state="state.micState" :disabled="state.micDisabled">
      <svg class="icon" aria-hidden="true" viewBox="0 0 24 24"><rect x="9" y="2" width="6" height="13" rx="3" /><path d="M5 11a7 7 0 0 0 14 0m-7 7v4m-3 0h6" /></svg>
      <span data-voice-label>{{ state.microphone ? 'Tắt mic' : 'Bật mic' }}</span>
    </button>
    <button class="btn secondary small" type="button" data-voice-play :hidden="!state.showAudio">Nghe tiếng phòng</button>
  </div>
  <p data-voice-status role="status">{{ state.message }}</p>
</template>
