import { ref, watchEffect } from 'vue'

type Theme = 'light' | 'dark'
const key = 'lumiere-theme'

export function mountTheme() {
  const root = document.documentElement
  const buttons = [...document.querySelectorAll<HTMLButtonElement>('[data-theme-toggle]')]
  const meta = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
  const value = ref<Theme>(root.dataset.theme === 'light' ? 'light' : 'dark')
  const abort = new AbortController()
  const events = { signal: abort.signal }

  function refresh() {
    try { value.value = localStorage.getItem(key) === 'light' ? 'light' : 'dark' }
    catch { /* Retain the current theme if this browser blocks storage. */ }
  }

  function toggle() {
    value.value = value.value === 'dark' ? 'light' : 'dark'
    try { localStorage.setItem(key, value.value) }
    catch { /* The change still applies to this page. */ }
  }

  const stop = watchEffect(() => {
    root.dataset.theme = value.value
    if (meta) meta.content = value.value === 'light' ? '#f6f5f1' : '#0b0d0e'
    const label = value.value === 'light' ? 'Chuyển sang giao diện tối' : 'Chuyển sang giao diện sáng'
    for (const button of buttons) {
      button.setAttribute('aria-label', label)
      button.title = label
    }
  }, { flush: 'sync' })
  for (const button of buttons) {
    button.addEventListener('click', toggle, events)
    button.hidden = false
  }
  window.addEventListener('pageshow', refresh, events)
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) refresh()
  }, events)
  root.dataset.vueTheme = ''
  return () => { abort.abort(); stop(); delete root.dataset.vueTheme }
}
