<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import type { DirectoryData } from './directory'

const props = defineProps<{ initial: DirectoryData }>()
const result = shallowRef(props.initial)
const query = ref(props.initial.query)
const busy = ref(false)
const heading = ref<HTMLElement>()
const isActors = props.initial.kind === 'actors'
const isCountries = props.initial.kind === 'countries'
const itemLabel = isCountries ? 'quốc gia' : 'thể loại'
const countLabel = computed(() => {
  const { count, query } = result.value
  if (busy.value) return 'Đang tìm kiếm…'
  if (isActors) return `${count} diễn viên`
  return `${count} ${itemLabel}${query ? ` phù hợp với “${query}”` : ' trong thư viện'}`
})
let pending: AbortController | undefined

async function navigate(url: URL, options: { history?: boolean; focus?: boolean } = {}) {
  pending?.abort()
  const controller = new AbortController()
  pending = controller
  const isHistory = options.history === true
  const previousInput = query.value
  busy.value = true
  const timeout = window.setTimeout(() => controller.abort(), 12_000)
  try {
    const response = await fetch(url, {
      headers: { 'X-Lumiere-Directory': 'vue' },
      credentials: 'same-origin',
      signal: controller.signal,
    })
    if (!response.ok || response.redirected || !response.headers.get('Content-Type')?.includes('application/json')) {
      throw new Error('Directory could not be loaded')
    }
    const incoming: DirectoryData = await response.json()
    if (pending !== controller) return
    if (incoming.kind !== props.initial.kind || !Array.isArray(incoming.items)) throw new Error('Invalid directory data')
    result.value = incoming
    if (isHistory || query.value === previousInput) query.value = incoming.query
    if (!isHistory && url.href !== window.location.href) window.history.pushState(null, '', url)
    if (options.focus) {
      await nextTick()
      if (pending !== controller) return
      heading.value?.focus({ preventScroll: true })
      heading.value?.scrollIntoView({ behavior: 'instant', block: 'start' })
    }
  } catch {
    if (pending !== controller) return
    if (isHistory) window.location.reload()
    else window.location.assign(url.href)
  } finally {
    window.clearTimeout(timeout)
    if (pending === controller) {
      pending = undefined
      busy.value = false
    }
  }
}

function search() {
  const url = new URL(props.initial.url, window.location.origin)
  if (query.value.trim()) url.searchParams.set('q', query.value.trim())
  void navigate(url)
}

function follow(event: MouseEvent, href: string, focus = false) {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  const url = new URL(href, window.location.href)
  if (url.origin !== window.location.origin || url.pathname !== window.location.pathname) return
  event.preventDefault()
  void navigate(url, { focus })
}

function restore() {
  void navigate(new URL(window.location.href), { history: true })
}

onMounted(() => window.addEventListener('popstate', restore))
onUnmounted(() => {
  const controller = pending
  pending = undefined
  controller?.abort()
  window.removeEventListener('popstate', restore)
})
</script>

<template>
  <section class="content-section" :class="isActors ? 'actors-directory' : 'discovery-directory'">
    <div :class="isActors ? 'actors-heading' : 'discovery-heading'">
      <div>
        <p class="eyebrow">{{ result.eyebrow }}</p>
        <h1 ref="heading" tabindex="-1">{{ result.title }}</h1>
        <p class="muted">{{ result.description }}</p>
      </div>
      <span v-if="isActors" class="actors-count" role="status">{{ countLabel }}</span>
      <form v-else class="discovery-search" method="get" :action="result.url" role="search" @submit.prevent="search">
        <label class="sr-only" for="discovery-query">Tìm {{ itemLabel }}</label>
        <svg class="icon" aria-hidden="true"><use href="#i-search" /></svg>
        <input id="discovery-query" v-model="query" type="search" name="q" maxlength="150" :placeholder="`Tìm ${itemLabel}…`">
        <button class="btn small secondary" type="submit">Tìm</button>
      </form>
    </div>
    <form v-if="isActors" class="actors-search" method="get" :action="result.url" role="search" @submit.prevent="search">
      <label class="actors-search-field">
        <span class="sr-only">Tìm diễn viên</span>
        <svg class="icon" aria-hidden="true"><use href="#i-search" /></svg>
        <input v-model="query" type="search" name="q" maxlength="150" placeholder="Tìm tên diễn viên…" autocomplete="off">
      </label>
      <button class="btn" type="submit">Tìm kiếm</button>
      <a v-if="result.query" class="actors-reset" :href="result.url" @click="follow($event, result.url)">Xóa tìm kiếm</a>
    </form>
    <p v-else class="discovery-count" role="status">{{ countLabel }}</p>
    <div :class="isActors ? 'actors-grid' : 'discovery-grid'" :aria-busy="busy">
      <template v-if="isActors">
        <a v-for="person in result.items" :key="person.href" class="actor-card" :href="person.href">
          <span class="actor-card-avatar" aria-hidden="true">{{ person.name.slice(0, 1).toUpperCase() }}</span>
          <div class="actor-card-copy"><h2>{{ person.name }}</h2><p>{{ person.count }} phim trong thư viện</p></div>
          <svg class="icon actor-card-arrow" aria-hidden="true"><use href="#i-arrow" /></svg>
        </a>
        <div v-if="!result.items.length" class="actors-empty">
          <span class="actors-empty-icon" aria-hidden="true"><svg class="icon"><use href="#i-users" /></svg></span>
          <h2>{{ result.query ? 'Không tìm thấy diễn viên phù hợp' : 'Thông tin diễn viên đang được cập nhật' }}</h2>
          <p>{{ result.query ? 'Thử tìm bằng tên khác hoặc xóa từ khóa để xem danh sách.' : 'Bạn vẫn có thể khám phá các bộ phim đang có trong thư viện Lumière.' }}</p>
          <div class="actions">
            <a v-if="result.query" class="btn" :href="result.url" @click="follow($event, result.url)">Xem tất cả diễn viên</a>
            <a v-else class="btn" :href="result.catalogUrl">Khám phá phim</a>
            <a v-if="result.addActorUrl" class="btn secondary" :href="result.addActorUrl">Thêm diễn viên</a>
          </div>
        </div>
      </template>
      <template v-else>
        <a v-for="item in result.items" :key="item.href" class="discovery-tile" :href="item.href">
          <span class="discovery-tile-icon"><svg class="icon" aria-hidden="true"><use :href="isCountries ? '#i-globe' : '#i-grid'" /></svg></span>
          <div><h2>{{ item.name }}</h2><p>{{ item.count }} phim</p></div>
          <svg class="icon discovery-tile-arrow" aria-hidden="true"><use href="#i-arrow" /></svg>
        </a>
        <div v-if="!result.items.length" class="empty">
          <h2>{{ result.query ? 'Chưa tìm thấy kết quả' : 'Nội dung đang được cập nhật' }}</h2>
          <p>{{ result.query ? 'Thử từ khóa khác hoặc xem lại toàn bộ danh sách.' : 'Các mục sẽ xuất hiện khi có phim được xuất bản.' }}</p>
          <a class="btn secondary" :href="result.url" @click="follow($event, result.url, true)">Xem tất cả</a>
        </div>
      </template>
    </div>
    <nav v-if="result.pagination && result.pagination.pages > 1" class="pagination" aria-label="Phân trang diễn viên">
      <a v-if="result.pagination.previous" class="btn secondary" :href="result.pagination.previous"
         @click="follow($event, result.pagination.previous, true)">Trang trước</a>
      <span>{{ result.pagination.page }} / {{ result.pagination.pages }}</span>
      <a v-if="result.pagination.next" class="btn secondary" :href="result.pagination.next"
         @click="follow($event, result.pagination.next, true)">Trang sau</a>
    </nav>
  </section>
</template>
