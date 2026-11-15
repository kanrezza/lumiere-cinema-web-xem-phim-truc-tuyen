<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import type { FeaturedSlide } from './featured'

const props = defineProps<{ stage: HTMLElement; slides: FeaturedSlide[] }>()
const tabs = ref<HTMLElement>()
const active = ref(0)
const preview = computed(() => props.slides[active.value].preview)
const visible = ref(!('IntersectionObserver' in window))
const motionPaused = ref(false)
const manuallyPaused = ref(false)
const playbackBlocked = ref(false)
const previewPaused = computed(() => manuallyPaused.value || motionPaused.value)
const previewLabel = computed(() => previewPaused.value ? 'Phát xem trước' : 'Tạm dừng xem trước')

let playRequest = 0
let bodyObserver: MutationObserver
let stageObserver: IntersectionObserver | undefined

function syncEnvironment() {
  motionPaused.value = document.body.classList.contains('motion-paused')
  playbackBlocked.value = document.hidden || document.body.classList.contains('quickview-open')
}

function playPreview() {
  const ticket = ++playRequest
  const current = preview.value
  for (const slide of props.slides) {
    if (slide.preview && slide.preview !== current) {
      slide.preview.pause()
      slide.preview.classList.remove('is-playing')
    }
  }
  if (!current) return
  if (!visible.value || previewPaused.value || playbackBlocked.value) {
    current.pause()
    return
  }
  const source = current.dataset.previewSrc
  if (!current.hasAttribute('src') && source) current.src = source
  current.muted = true
  current.play().then(() => {
    if (ticket === playRequest) current.classList.add('is-playing')
  }).catch(() => {
    if (ticket === playRequest) {
      current.classList.remove('is-playing')
      manuallyPaused.value = true
    }
  })
}

function previewError(event: Event) {
  if (event.currentTarget !== preview.value) return
  preview.value?.classList.remove('is-playing')
  manuallyPaused.value = true
}

async function select(index: number, focus = false) {
  if (index !== active.value) {
    active.value = index
    props.slides.forEach(({ panel }, position) => { panel.hidden = position !== index })
    if (!motionPaused.value) {
      props.slides[index].panel.querySelector('.feature-content')?.animate?.(
        [{ opacity: 0.3, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }],
        { duration: 350, easing: 'ease-out' },
      )
    }
  }
  if (focus) {
    await nextTick()
    tabs.value?.querySelector<HTMLButtonElement>('[aria-selected=true]')?.focus()
  }
}

function selectWithKeyboard(event: KeyboardEvent) {
  const last = props.slides.length - 1
  let target: number
  switch (event.key) {
    case 'ArrowRight': target = active.value === last ? 0 : active.value + 1; break
    case 'ArrowLeft': target = active.value === 0 ? last : active.value - 1; break
    case 'Home': target = 0; break
    case 'End': target = last; break
    default: return
  }
  event.preventDefault()
  void select(target, true)
}

function togglePreview() {
  if (motionPaused.value) {
    document.querySelector<HTMLElement>('[data-motion-toggle]')?.click()
    manuallyPaused.value = false
    syncEnvironment()
  } else {
    manuallyPaused.value = !manuallyPaused.value
  }
}

watch([preview, previewPaused, playbackBlocked, visible], playPreview, { flush: 'post' })

onMounted(() => {
  syncEnvironment()
  bodyObserver = new MutationObserver(syncEnvironment)
  bodyObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] })
  document.addEventListener('visibilitychange', syncEnvironment)
  if ('IntersectionObserver' in window) {
    stageObserver = new IntersectionObserver(([entry]) => {
      visible.value = Boolean(entry?.isIntersecting)
    }, { threshold: 0.15 })
    stageObserver.observe(props.stage)
  }
  for (const slide of props.slides) slide.preview?.addEventListener('error', previewError)
  playPreview()
})

onUnmounted(() => {
  ++playRequest
  bodyObserver?.disconnect()
  stageObserver?.disconnect()
  document.removeEventListener('visibilitychange', syncEnvironment)
  for (const slide of props.slides) {
    slide.preview?.removeEventListener('error', previewError)
    slide.preview?.pause()
  }
})
</script>

<template>
  <div class="feature-bottom" data-feature-controls data-vue-featured>
    <button
      class="preview-toggle" type="button" data-preview-toggle :hidden="!preview"
      :aria-label="previewLabel" :aria-pressed="previewPaused" @click="togglePreview"
    >
      <span class="preview-symbol" aria-hidden="true">{{ previewPaused ? '▷' : 'Ⅱ' }}</span>
      <span data-preview-label>{{ previewLabel }}</span>
    </button>
    <div ref="tabs" class="feature-tabs" role="tablist" aria-label="Chọn phim nổi bật">
      <button
        v-for="(slide, index) in slides" :id="slide.tabId" :key="slide.tabId" class="feature-tab"
        type="button" role="tab" :aria-controls="slide.panel.id" :aria-selected="index === active"
        :tabindex="index === active ? 0 : -1" @click="select(index)" @keydown="selectWithKeyboard"
      >
        <img :src="slide.image" alt="">
        <span><small aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</small>{{ slide.title }}</span>
      </button>
    </div>
  </div>
</template>
