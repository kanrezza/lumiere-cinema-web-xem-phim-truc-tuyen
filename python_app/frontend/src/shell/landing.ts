import { ref, watch } from 'vue'

export function mountLandingTabs(): () => void {
  const root = document.querySelector<HTMLElement>('.experience-tabs')
  if (!root) return () => {}
  const items = [...root.querySelectorAll<HTMLButtonElement>('[data-experience-tab]')].flatMap(button => {
    const panel = document.getElementById(button.dataset.target ?? '')
    return panel?.hasAttribute('data-experience-panel') ? [{ button, panel }] : []
  })
  if (!items.length) return () => {}
  const selection = ref(Math.max(0, items.findIndex(({ button }) => button.getAttribute('aria-selected') === 'true')))
  const abort = new AbortController()
  const options = { signal: abort.signal }
  let animation: Animation | undefined
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
  const allowMotion = () => !document.hidden && !document.body.classList.contains('motion-paused')
    && (document.body.classList.contains('motion-enabled') || !motion.matches)

  const stop = watch(selection, (selected, previous) => {
    animation?.cancel()
    for (const [index, { button, panel }] of items.entries()) {
      const active = index === selected
      button.id ||= `experience-tab-${index + 1}`
      button.setAttribute('role', 'tab')
      button.setAttribute('aria-controls', panel.id)
      button.setAttribute('aria-selected', String(active))
      button.tabIndex = active ? 0 : -1
      panel.setAttribute('role', 'tabpanel')
      panel.setAttribute('aria-labelledby', button.id)
      panel.hidden = !active
    }
    if (previous !== undefined && allowMotion()) {
      animation = items[selected].panel.animate?.([
        { opacity: .4, transform: 'translateY(7px)' },
        { opacity: 1, transform: 'translateY(0)' },
      ], { duration: 280, easing: 'cubic-bezier(.2,.7,.2,1)' })
    }
  }, { immediate: true, flush: 'sync' })

  for (const [index, { button }] of items.entries()) {
    button.addEventListener('click', () => { selection.value = index }, options)
    button.addEventListener('keydown', event => {
      const vertical = root.getAttribute('aria-orientation') === 'vertical'
      const { key } = event
      if (key === (vertical ? 'ArrowDown' : 'ArrowRight')) selection.value = (index + 1) % items.length
      else if (key === (vertical ? 'ArrowUp' : 'ArrowLeft')) selection.value = (index + items.length - 1) % items.length
      else if (key === 'Home') selection.value = 0
      else if (key === 'End') selection.value = items.length - 1
      else return
      event.preventDefault()
      items[selection.value].button.focus()
    }, options)
  }
  const cancelIfPaused = () => { if (!allowMotion()) animation?.cancel() }
  const observer = new MutationObserver(cancelIfPaused)
  observer.observe(document.body, { attributes: true, attributeFilter: ['class'] })
  document.addEventListener('visibilitychange', cancelIfPaused, options)
  root.dataset.vueLandingTabs = ''
  return () => { stop(); abort.abort(); observer.disconnect(); animation?.cancel() }
}
