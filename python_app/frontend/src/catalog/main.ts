import { createApp } from 'vue'
import CatalogApp from './CatalogApp.vue'
import type { CatalogData } from './types'

const root = document.querySelector<HTMLElement>('[data-catalog-app]')
const fallback = document.querySelector<HTMLElement>('[data-catalog-fallback]')
const state = document.getElementById('catalog-data')

if (root?.dataset.catalogUrl && fallback && state?.textContent) {
  const grid = fallback.querySelector('.movie-grid')
  if (grid) {
    try {
      const data: Omit<CatalogData, 'gridHtml'> = JSON.parse(state.textContent)
      const app = createApp(CatalogApp, {
        catalogPath: root.dataset.catalogUrl,
        initial: { ...data, gridHtml: grid.innerHTML },
        root,
      })
      app.mount(root)
      if (root.querySelector('.movie-grid')) {
        fallback.remove()
        root.hidden = false
        if (location.hash === '#browse-search') {
          root.querySelector('#browse-search')?.scrollIntoView({ behavior: 'instant' })
        }
      } else {
        app.unmount()
      }
    } catch (error) {
      console.error('Lumière catalog could not start', error)
    }
  }
}
