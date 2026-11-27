import { createApp } from 'vue'
import SiteControls from './SiteControls.vue'
import QuickviewDialog from './QuickviewDialog.vue'
import SearchSuggestions from './SearchSuggestions.vue'

for (const root of document.querySelectorAll<HTMLElement>('[data-vue-search]')) {
  const original = Array.from(root.children)
  const mount = document.createElement('div')
  mount.className = 'quick-search-mount'
  const app = createApp(SearchSuggestions, {
    endpoint: root.dataset.endpoint || '/search/suggestions/',
    catalogUrl: root.dataset.catalogUrl || '/browse/',
    initialQuery: root.dataset.initialQuery || '',
  })
  root.append(mount)
  try {
    app.mount(mount)
    if (!mount.querySelector('form')) throw new Error('Search did not mount')
    for (const child of original) if (child instanceof HTMLElement) child.hidden = true
    root.dataset.mounted = 'true'
  } catch {
    app.unmount()
    mount.remove()
  }
}

const shell = document.querySelector<HTMLElement>('[data-vue-shell-root]')
if (shell) createApp(SiteControls).mount(shell)

const quickview = document.querySelector<HTMLElement>('[data-vue-quickview-root]')
const fallback = document.querySelector<HTMLDialogElement>('#movie-quickview')
if (quickview && fallback && typeof fallback.showModal === 'function') {
  const app = createApp(QuickviewDialog)
  app.mount(quickview)
  if (quickview.querySelector('dialog')) {
    fallback.remove()
    quickview.dataset.mounted = 'true'
  } else {
    app.unmount()
  }
}
