<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{
  sidebar: HTMLElement
  overlay: HTMLButtonElement | null
}>()

const trigger = ref<HTMLButtonElement>()
const expanded = ref(false)
const listeners = new AbortController()

function setMenu(open: boolean, restoreFocus = false) {
  expanded.value = open
  document.body.classList.toggle('studio-nav-open', open)
  if (props.overlay) props.overlay.hidden = !open
  if (open) {
    props.sidebar.querySelector<HTMLButtonElement>('[data-studio-close]')?.focus()
  } else if (restoreFocus) {
    trigger.value?.focus()
  }
}

onMounted(() => {
  const options = { signal: listeners.signal }
  const account = document.querySelector<HTMLDetailsElement>('.studio-account')

  for (const close of [props.sidebar.querySelector('[data-studio-close]'), props.overlay]) {
    close?.addEventListener('click', () => setMenu(false, true), options)
  }
  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !expanded.value) return
    event.preventDefault()
    setMenu(false, true)
  }, options)
  document.addEventListener('focusin', event => {
    if (expanded.value && event.target instanceof Node &&
        event.target !== trigger.value && !props.sidebar.contains(event.target)) {
      setMenu(false)
    }
  }, options)
  window.addEventListener('resize', () => {
    if (expanded.value && window.innerWidth > 900) setMenu(false)
  }, options)

  if (account) {
    document.addEventListener('click', event => {
      if (event.target instanceof Node && !account.contains(event.target)) account.open = false
    }, options)
    account.addEventListener('keydown', event => {
      if (event.key !== 'Escape' || !account.open) return
      account.open = false
      account.querySelector('summary')?.focus()
    }, options)
  }
})

onUnmounted(() => {
  listeners.abort()
  setMenu(false)
})
</script>

<template>
  <button ref="trigger" type="button" class="studio-menu-toggle studio-icon-button"
          data-studio-menu aria-controls="studio-sidebar" :aria-expanded="expanded"
          :aria-label="expanded ? 'Đóng menu quản trị' : 'Mở menu quản trị'"
          @click="setMenu(!expanded)">
    <svg class="studio-icon" aria-hidden="true"><use href="#s-menu" /></svg>
  </button>
</template>
