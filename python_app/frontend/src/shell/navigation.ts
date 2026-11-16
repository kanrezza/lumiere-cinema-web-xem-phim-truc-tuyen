import { shallowRef, watchEffect } from 'vue'

interface Menu {
  trigger: HTMLButtonElement
  panel: HTMLElement
  fallback: HTMLAnchorElement
}
type OpenMenu = { menu: Menu; source: 'hover' | 'click' | 'keyboard' }

export function mountNavigation(): () => void {
  const header = document.querySelector<HTMLElement>('.site-header')
  if (!header) return () => {}
  const navigation = header.querySelector('.main-nav')
  const account = header.querySelector<HTMLDetailsElement>('.account-menu')
  const menus: Menu[] = []
  for (const trigger of header.querySelectorAll<HTMLButtonElement>('[data-nav-trigger]')) {
    const key = trigger.dataset.navKey
    const panel = document.getElementById(trigger.getAttribute('aria-controls') ?? '')
    const fallback = [...header.querySelectorAll<HTMLAnchorElement>('[data-nav-fallback]')]
      .find(link => link.dataset.navFallback === key)
    if (key && panel && fallback && header.contains(panel) && panel.dataset.navPanel === key) menus.push({ trigger, panel, fallback })
  }
  if (!menus.length) return () => {}
  const current = shallowRef<OpenMenu>()
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)')
  const abort = new AbortController()
  const events = { signal: abort.signal }
  let entering: number | undefined
  let leaving: number | undefined

  function cancelHover() {
    window.clearTimeout(entering)
    window.clearTimeout(leaving)
  }
  function contains(menu: Menu, target: EventTarget | null) {
    return target instanceof Node && (menu.trigger.contains(target) || menu.panel.contains(target))
  }
  function position(menu: Menu) {
    const width = Math.min(480, Math.max(0, window.innerWidth - 40))
    const left = Math.max(20, Math.min(menu.trigger.getBoundingClientRect().left - 12, window.innerWidth - width - 20))
    menu.panel.style.setProperty('--genre-left', `${Math.round(left - header!.getBoundingClientRect().left)}px`)
  }
  function open(menu: Menu, source: OpenMenu['source']) {
    cancelHover()
    if (account?.open) account.open = false
    current.value = { menu, source }
  }
  function close() {
    cancelHover()
    current.value = undefined
  }

  const stop = watchEffect(() => {
    for (const menu of menus) {
      const expanded = current.value?.menu === menu
      menu.panel.hidden = !expanded
      menu.trigger.setAttribute('aria-expanded', String(expanded))
      if (expanded) position(menu)
    }
  }, { flush: 'sync' })

  for (const menu of menus) {
    const { trigger, panel, fallback } = menu
    trigger.hidden = false
    fallback.hidden = true
    trigger.addEventListener('click', event => {
      const keyboard = event.detail === 0
      const prior = current.value
      if (prior?.menu === menu && !(prior.source === 'hover' && !keyboard)) close()
      else {
        open(menu, keyboard ? 'keyboard' : 'click')
        if (keyboard) panel.querySelector<HTMLAnchorElement>('a[href]')?.focus({ preventScroll: true })
      }
    }, events)
    trigger.addEventListener('keydown', event => {
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
      event.preventDefault()
      open(menu, 'keyboard')
      const links = panel.querySelectorAll<HTMLAnchorElement>('a[href]')
      links[event.key === 'ArrowUp' ? links.length - 1 : 0]?.focus({ preventScroll: true })
    }, events)
    panel.addEventListener('click', event => {
      if (event.target instanceof Element && event.target.closest('a[href]')) close()
    }, events)
    trigger.addEventListener('pointerenter', event => {
      if (event.pointerType !== 'mouse' || !finePointer.matches) return
      cancelHover()
      if (current.value?.menu !== menu) entering = window.setTimeout(() => open(menu, 'hover'), 120)
    }, events)
    const leave = (event: PointerEvent) => {
      window.clearTimeout(entering)
      if (current.value?.menu !== menu || current.value.source !== 'hover' || contains(menu, event.relatedTarget)) return
      leaving = window.setTimeout(() => {
        if (!contains(menu, document.activeElement)) close()
      }, 150)
    }
    trigger.addEventListener('pointerleave', leave, events)
    panel.addEventListener('pointerenter', () => window.clearTimeout(leaving), events)
    panel.addEventListener('pointerleave', leave, events)
  }
  document.addEventListener('keydown', event => {
    const menu = current.value?.menu
    if (event.key !== 'Escape' || !menu) return
    event.preventDefault()
    close()
    menu.trigger.focus({ preventScroll: true })
  }, events)
  const outside = (event: Event) => {
    if (current.value && !contains(current.value.menu, event.target)) close()
  }
  document.addEventListener('pointerdown', outside, events)
  document.addEventListener('focusin', outside, events)
  document.addEventListener('visibilitychange', () => { if (document.hidden) close() }, events)
  window.addEventListener('resize', () => { if (current.value) position(current.value.menu) }, events)
  const scroll = () => {
    if (current.value?.source === 'keyboard') position(current.value.menu)
    else if (current.value) close()
  }
  window.addEventListener('scroll', scroll, { ...events, passive: true })
  navigation?.addEventListener('scroll', scroll, { ...events, passive: true })
  header.dataset.vueNavigation = ''
  return () => { close(); abort.abort(); stop(); delete header.dataset.vueNavigation }
}
