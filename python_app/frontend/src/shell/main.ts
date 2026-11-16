import { createApp } from 'vue'
import SiteControls from './SiteControls.vue'
import QuickviewDialog from './QuickviewDialog.vue'

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
