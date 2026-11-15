import { createApp } from 'vue'
import FeaturedControls from './FeaturedControls.vue'

export interface FeaturedSlide {
  panel: HTMLElement
  tabId: string
  title: string
  image: string
  preview: HTMLVideoElement | null
}

export function mountFeatured(stage: HTMLElement): void {
  if (stage.dataset.featureEnhanced === 'vue') return
  const root = stage.querySelector<HTMLElement>('[data-feature-vue]')
  const fallback = stage.querySelector<HTMLElement>('[data-feature-controls]')
  if (!root || !fallback) return

  const panels = new Map([...stage.querySelectorAll<HTMLElement>('[role=tabpanel]')].map(panel => [panel.id, panel]))
  const tabs = [...fallback.querySelectorAll<HTMLButtonElement>('[role=tab]')]
  const slides: FeaturedSlide[] = []
  for (const tab of tabs) {
    const panel = panels.get(tab.getAttribute('aria-controls') ?? '')
    const title = panel?.querySelector('.feature-title')?.textContent?.trim()
    const image = tab.querySelector('img')?.getAttribute('src')
    if (!panel || !title || !image) return
    slides.push({ panel, tabId: tab.id, title, image, preview: panel.querySelector('.feature-preview') })
  }
  if (!slides.length || slides.length !== panels.size) return

  const app = createApp(FeaturedControls, { stage, slides })
  app.mount(root)
  if (root.querySelectorAll('[role=tab]').length !== slides.length) {
    app.unmount()
    return
  }

  fallback.remove()
  root.hidden = false
  stage.dataset.featureEnhanced = 'vue'
}
