import { createApp } from 'vue'
import ShelfControls from './ShelfControls.vue'

export function mountShelves(root: ParentNode): void {
  for (const mount of root.querySelectorAll<HTMLElement>('[data-shelf-vue]:not([data-vue-shelf-mounted])')) {
    const row = mount.closest('[data-shelf]')?.querySelector<HTMLElement>('.film-row')
    const previousLabel = mount.querySelector('[data-shelf-dir="-1"]')?.getAttribute('aria-label')
    const nextLabel = mount.querySelector('[data-shelf-dir="1"]')?.getAttribute('aria-label')
    if (!row || !previousLabel || !nextLabel) continue

    const fallback = [...mount.childNodes]
    const app = createApp(ShelfControls, { row, previousLabel, nextLabel })
    app.mount(mount)
    if (mount.querySelectorAll('button[data-shelf-dir]').length !== 2) {
      app.unmount()
      mount.replaceChildren(...fallback)
      continue
    }
    mount.setAttribute('data-vue-shelf-mounted', '')
    mount.hidden = false
  }
}
