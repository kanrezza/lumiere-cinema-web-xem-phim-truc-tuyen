<script setup lang="ts">
import { onUnmounted, ref } from 'vue'

const props = defineProps<{ input: HTMLInputElement }>()
const visible = ref(false)
let restoreInputFocus = false

function rememberFocus() {
  restoreInputFocus = document.activeElement === props.input
}

function toggle() {
  const start = props.input.selectionStart
  const end = props.input.selectionEnd
  const direction = props.input.selectionDirection
  visible.value = !visible.value
  props.input.type = visible.value ? 'text' : 'password'
  if (restoreInputFocus) props.input.focus({ preventScroll: true })
  restoreInputFocus = false
  if (start !== null && end !== null) {
    try { props.input.setSelectionRange(start, end, direction || undefined) }
    catch { /* Visibility remains usable on browsers without selection support. */ }
  }
}

onUnmounted(() => { props.input.type = 'password' })
</script>

<template>
  <button type="button" class="studio-password-toggle" :aria-controls="input.id"
          :aria-pressed="visible" :aria-label="visible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'"
          :title="visible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'" @pointerdown="rememberFocus" @click="toggle">
    <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">
      <template v-if="visible">
        <path d="m3 3 18 18M9.9 5.2A10.9 10.9 0 0 1 12 5c5.5 0 9 7 9 7a17.7 17.7 0 0 1-3.4 4.3M6.1 6.1A18.3 18.3 0 0 0 3 12s3.5 7 9 7a10.4 10.4 0 0 0 5-1.3M10 10a3 3 0 0 0 4 4"/>
      </template>
      <template v-else>
        <path d="M3 12s3.5-7 9-7 9 7 9 7-3.5 7-9 7-9-7-9-7Z"/>
        <circle cx="12" cy="12" r="3"/>
      </template>
    </svg>
  </button>
</template>
