<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { moveSearchSelection, searchableQuery, SearchSuggestionLoader, type SearchPayload } from './search-state'

const props = defineProps<{ endpoint: string; catalogUrl: string; initialQuery: string }>()
const query = ref(props.initialQuery.slice(0, 150))
const root = ref<HTMLElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const mobileButton = ref<HTMLButtonElement | null>(null)
const opened = ref(false)
const mobileExpanded = ref(false)
const state = ref<'idle' | 'waiting' | 'loading' | 'ready' | 'error'>('idle')
const result = ref<SearchPayload | null>(null)
const active = ref(-1)
const id = useId()
const listId = `search-results-${id}`
const loader = new SearchSuggestionLoader(props.endpoint, props.catalogUrl, location.origin, (url, init) => fetch(url, init))
const abort = new AbortController()
let timer: ReturnType<typeof setTimeout> | undefined
let sequence = 0
const composing = ref(false)
const items = computed(() => [
  ...(result.value?.movies || []).map(movie => ({ key: `movie-${movie.id}`, title: movie.title, url: movie.url, meta: `${movie.meta} · ${movie.ready ? 'Đã có bản xem' : 'Đang chuẩn bị'}`, poster: movie.poster, vip: movie.vip, type: 'movie' })),
  ...(result.value?.actors || []).map(actor => ({ key: `actor-${actor.id}`, title: actor.name, url: actor.url, meta: 'Diễn viên', poster: null, vip: false, type: 'actor' })),
])
const showPanel = computed(() => opened.value)
const selectedId = computed(() => showPanel.value && active.value >= 0 ? `${listId}-${active.value}` : undefined)
const allUrl = computed(() => {
  const url = new URL(props.catalogUrl, location.origin)
  url.searchParams.set('q', query.value.trim().slice(0, 150))
  return result.value?.all_url || url.pathname + url.search
})
const announcement = computed(() => {
  if (state.value === 'loading' || state.value === 'waiting') return 'Đang tìm kiếm…'
  if (state.value === 'error') return 'Chưa tải được gợi ý. Bạn vẫn có thể nhấn Enter để tìm kiếm.'
  if (state.value === 'ready') return items.value.length ? `${items.value.length} gợi ý tìm kiếm.` : 'Chưa tìm thấy phim hoặc diễn viên phù hợp.'
  return 'Nhập ít nhất 2 ký tự để tìm phim hoặc diễn viên.'
})

function queueSearch() {
  if (timer) clearTimeout(timer)
  sequence += 1
  const request = sequence
  loader.cancel()
  active.value = -1
  result.value = null
  if (!searchableQuery(query.value.trim().slice(0, 150))) { state.value = 'idle'; return }
  state.value = 'waiting'
  timer = setTimeout(async () => {
    state.value = 'loading'
    try {
      const payload = await loader.load(query.value)
      if (sequence === request && payload) { result.value = payload; state.value = 'ready' }
    } catch { if (sequence === request) state.value = 'error' }
  }, 240)
}
watch(query, () => { opened.value = true; if (!composing.value) queueSearch() })
function focusSearch() { opened.value = true; if (state.value === 'idle' && searchableQuery(query.value)) queueSearch() }
function close() {
  opened.value = false
  active.value = -1
  if (mobileExpanded.value) { mobileExpanded.value = false; mobileButton.value?.focus() }
}
async function openMobile() { mobileExpanded.value = true; await nextTick(); input.value?.focus() }
function keydown(event: KeyboardEvent) {
  if (event.isComposing || composing.value) return
  if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); return }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    opened.value = true
    active.value = moveSearchSelection(active.value, items.value.length, event.key === 'ArrowDown' ? 1 : -1)
    void nextTick(() => document.getElementById(selectedId.value || '')?.scrollIntoView({ block: 'nearest' }))
  } else if (event.key === 'Enter' && opened.value && active.value >= 0) {
    const item = items.value[active.value]
    if (item) { event.preventDefault(); location.assign(item.url) }
  }
}
function startComposition() { composing.value = true }
function endComposition() { composing.value = false; queueSearch() }
function clear() { query.value = ''; input.value?.focus() }
function focusout(event: FocusEvent) { if (event.relatedTarget instanceof Node && !root.value?.contains(event.relatedTarget)) close() }
function imageFailed(event: Event) { if (event.target instanceof HTMLImageElement) event.target.hidden = true }
onMounted(() => {
  document.addEventListener('pointerdown', event => { if (event.target instanceof Node && !root.value?.contains(event.target)) close() }, { signal: abort.signal })
})
onBeforeUnmount(() => { abort.abort(); loader.cancel(); if (timer) clearTimeout(timer) })
</script>

<template>
  <div ref="root" class="quick-search" :class="{ 'is-mobile-open': mobileExpanded }" @focusout="focusout" @keydown.esc.stop.prevent="close">
    <button ref="mobileButton" class="quick-search-mobile" type="button" aria-label="Mở tìm kiếm" :aria-expanded="mobileExpanded" @click="openMobile"><svg class="icon" aria-hidden="true"><use href="#i-search" /></svg></button>
    <form class="search-suggestion-form" :action="catalogUrl" method="get" role="search">
      <svg class="icon" aria-hidden="true"><use href="#i-search" /></svg>
      <input ref="input" v-model="query" type="search" name="q" maxlength="150" placeholder="Tìm phim, diễn viên…" aria-label="Tìm kiếm phim" role="combobox" aria-autocomplete="list" :aria-expanded="showPanel" :aria-controls="showPanel ? listId : undefined" :aria-activedescendant="selectedId" autocomplete="off" @focus="focusSearch" @keydown="keydown" @compositionstart="startComposition" @compositionend="endComposition">
      <button v-if="query" class="quick-search-clear" type="button" aria-label="Xóa từ khóa tìm kiếm" @click="clear">×</button>
      <button v-if="mobileExpanded" class="quick-search-close" type="button" aria-label="Đóng tìm kiếm" @click="close">Đóng</button>
      <button type="submit" class="sr-only">Tìm kiếm</button>
    </form>
    <section v-if="showPanel" class="search-suggestion-panel" aria-label="Gợi ý tìm kiếm">
      <div class="search-suggestion-heading"><strong>Tìm trên Lumière</strong><span v-if="state === 'ready'">{{ items.length }} gợi ý</span></div>
      <p class="search-suggestion-status" :class="{ 'sr-only': state === 'ready' && items.length }" role="status" aria-live="polite">{{ announcement }}</p>
      <ul :id="listId" role="listbox" aria-label="Phim và diễn viên phù hợp" :aria-busy="state === 'loading' || state === 'waiting'">
        <li v-for="(item, index) in items" :key="item.key" role="presentation">
          <a :id="`${listId}-${index}`" :href="item.url" role="option" :aria-selected="active === index" tabindex="-1" @pointermove="active = index">
            <span class="search-suggestion-art" :class="{ 'is-actor': item.type === 'actor' }" aria-hidden="true"><span>{{ item.title.slice(0, 1) }}</span><img v-if="item.poster" :src="item.poster" alt="" width="32" height="44" loading="lazy" @error="imageFailed"></span>
            <span class="search-suggestion-copy"><strong>{{ item.title }}</strong><small>{{ item.meta }}</small></span><span v-if="item.vip" class="search-suggestion-vip">VIP</span>
          </a>
        </li>
      </ul>
      <a v-if="searchableQuery(query)" class="search-suggestion-all" :href="allUrl">Xem tất cả kết quả <span aria-hidden="true">↗</span></a>
    </section>
  </div>
</template>
