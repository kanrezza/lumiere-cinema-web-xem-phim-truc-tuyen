export function mountHeader() {
  const header = document.querySelector<HTMLElement>('.site-header')
  if (!header) return () => {}
  const abort = new AbortController()
  const {signal} = abort
  let frame: number | undefined
  const onScroll = () => {
    if (frame !== undefined) return
    frame = requestAnimationFrame(() => {
      header.classList.toggle('is-scrolled', scrollY > 20)
      frame = undefined
    })
  }
  onScroll()
  window.addEventListener('scroll', onScroll, {passive: true, signal})
  const nav = header.querySelector<HTMLElement>('.main-nav')
  const observer = typeof ResizeObserver === 'function' && nav ? new ResizeObserver(() => {
    const current = nav.querySelector('[aria-current]:not([hidden]), .nav-genre-trigger.is-current:not([hidden])')
    if (!current) return
    const rail = nav.getBoundingClientRect()
    const item = current.getBoundingClientRect()
    if (item.right > rail.right) nav.scrollLeft += item.right - rail.right + 14
    else if (item.left < rail.left) nav.scrollLeft -= rail.left - item.left + 14
  }) : undefined
  if (nav) observer?.observe(nav)
  const menu = header.querySelector<HTMLDetailsElement>('.account-menu')
  if (menu) {
    document.addEventListener('click', event => {
      if (menu.open && event.target instanceof Node && !menu.contains(event.target)) menu.open = false
    }, {signal})
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && menu.open) {
        menu.open = false
        menu.querySelector('summary')?.focus()
      }
    }, {signal})
  }
  const hideBroken = (event: Event) => {
    if (event.target instanceof HTMLImageElement && event.target.hasAttribute('data-saved-avatar')) {
      event.target.hidden = true
    }
  }
  document.addEventListener('error', hideBroken, {capture: true, signal})
  for (const image of document.querySelectorAll<HTMLImageElement>('img[data-saved-avatar]')) {
    if (image.complete && !image.naturalWidth) image.hidden = true
  }

  return () => {
    abort.abort()
    observer?.disconnect()
    if (frame !== undefined) cancelAnimationFrame(frame)
  }
}
