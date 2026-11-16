import { createApp } from 'vue'
import VoiceControls from './VoiceControls.vue'

export function mountVoiceControls(room: HTMLElement) {
  const mount = room.querySelector<HTMLElement>('[data-vue-voice-controls]')
  const controls = room.querySelector('.room-voice-actions')
  const status = room.querySelector('[data-voice-status]')
  if (!mount || !controls || !status) return
  const app = createApp(VoiceControls, { room, initialMessage: status.textContent?.trim() || '' })
  app.mount(mount)
  if (!mount.querySelector('[data-voice-join]')) {
    app.unmount()
    return
  }
  controls.remove()
  status.remove()
  room.dataset.vueVoice = 'true'
}
