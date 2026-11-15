<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import CatalogFilters from './CatalogFilters.vue'
import CatalogPagination from './CatalogPagination.vue'
import { syncCatalogHeader } from './header'
import type { CatalogData } from './types'

const props = defineProps<{ catalogPath: string; initial: CatalogData; root: HTMLElement }>()
const data = shallowRef(props.initial)
const heading = ref<HTMLHeadingElement>()
const loading = ref(false)
let request: AbortController | undefined

function revealQuickview() {
  props.root.dispatchEvent(new CustomEvent('lumiere:catalog-render', { bubbles: true }))
}

async function navigate(url: URL, push: boolean) {
  request?.abort()
  const controller = new AbortController()
  request = controller
  loading.value = true
  const timer = window.setTimeout(() => controller.abort(), 12000)

  try {
    const response = await fetch(url, {
      headers: { 'X-Lumiere-Catalog': 'vue' },
      credentials: 'same-origin',
      signal: controller.signal,
    })
    if (!response.ok || !response.headers.get('Content-Type')?.includes('application/json')) {
      throw new Error('Catalog data unavailable')
    }
    const payload: CatalogData = await response.json()
    if (request !== controller) return
    if (typeof payload.gridHtml !== 'string') throw new Error('Catalog data invalid')
    if (push && url.href !== location.href) history.pushState(null, '', url)
    data.value = payload
    syncCatalogHeader(payload.values, props.catalogPath)
    await nextTick()
    if (request !== controller) return
    revealQuickview()
    if (push) {
      heading.value?.focus({ preventScroll: true })
      heading.value?.scrollIntoView({ behavior: 'instant', block: 'start' })
    }
  } catch {
    if (request !== controller) return
    if (push) location.assign(url.href)
    else location.reload()
  } finally {
    window.clearTimeout(timer)
    if (request === controller) {
      request = undefined
      loading.value = false
    }
  }
}

function filteredUrl(url: URL) {
  return url.origin === location.origin && url.pathname === props.catalogPath && Boolean(url.search)
}

function follow(event: MouseEvent, href: string) {
  if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
  const url = new URL(href, location.href)
  if (!filteredUrl(url)) return
  event.preventDefault()
  void navigate(url, true)
}

function apply(params: URLSearchParams) {
  const url = new URL(props.catalogPath, location.origin)
  url.search = params.toString()
  void navigate(url, true)
}

function restore() {
  const url = new URL(location.href)
  if (filteredUrl(url)) void navigate(url, false)
  else location.reload()
}

onMounted(() => {
  revealQuickview()
  window.addEventListener('popstate', restore)
})
onUnmounted(() => {
  const pending = request
  request = undefined
  pending?.abort()
  window.removeEventListener('popstate', restore)
})
</script>

<template>
  <section class="catalog-section">
    <div class="browse-heading">
      <div>
        <p class="eyebrow">THƯ VIỆN LUMIÈRE</p>
        <h1 ref="heading" tabindex="-1">{{ data.title }}</h1>
        <p class="muted" role="status">{{ loading ? 'Đang tải kết quả…' : `${data.count} phim trong thư viện` }}</p>
      </div>
    </div>
    <nav class="catalog-segments" aria-label="Lọc trạng thái và nội dung">
      <a v-for="item in data.contentLinks" :key="item.label" :href="item.href" :class="{ selected: item.active }"
         :aria-current="item.active ? 'true' : undefined" @click="follow($event, item.href)">{{ item.label }}</a>
    </nav>
    <CatalogFilters :catalog-path="catalogPath" :data="data" @apply="apply" />
    <div v-if="data.activeFilters.length" class="discovery-active-filters" aria-label="Bộ lọc đang áp dụng">
      <span v-for="label in data.activeFilters" :key="label">{{ label }}</span>
    </div>
    <!-- Django renders these shared cards with the current viewer's playback permissions. -->
    <div class="movie-grid portrait-grid" :aria-busy="loading" v-html="data.gridHtml"></div>
    <CatalogPagination :pagination="data.pagination" @navigate="follow" />
  </section>
</template>
