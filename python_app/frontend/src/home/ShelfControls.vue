<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{
  row: HTMLElement
  previousLabel: string
  nextLabel: string
}>()

const atStart = ref(true)
const atEnd = ref(true)
let observer: ResizeObserver | undefined

function updateBounds() {
  const { scrollLeft, scrollWidth, clientWidth } = props.row
  // A scroll position can be fractional at browser zoom levels.
  atStart.value = scrollLeft <= 2
  atEnd.value = scrollLeft + clientWidth >= scrollWidth - 2
}

function scroll(direction: -1 | 1) {
  const classes = document.body.classList
  const reduceMotion = classes.contains('motion-paused')
    || (!classes.contains('motion-enabled') && window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  props.row.scrollBy({
    left: direction * props.row.clientWidth * 0.85,
    behavior: reduceMotion ? 'instant' : 'smooth',
  })
}

onMounted(() => {
  props.row.addEventListener('scroll', updateBounds, { passive: true })
  if (typeof ResizeObserver === 'function') {
    observer = new ResizeObserver(updateBounds)
    observer.observe(props.row)
  } else {
    window.addEventListener('resize', updateBounds)
  }
  updateBounds()
})

onUnmounted(() => {
  props.row.removeEventListener('scroll', updateBounds)
  if (observer) observer.disconnect()
  else window.removeEventListener('resize', updateBounds)
})
</script>

<template>
  <button class="shelf-arrow previous" type="button" data-shelf-dir="-1"
          :aria-label="previousLabel" :disabled="atStart" @click="scroll(-1)">
    <svg class="icon" aria-hidden="true"><use href="#i-arrow" /></svg>
  </button>
  <button class="shelf-arrow" type="button" data-shelf-dir="1"
          :aria-label="nextLabel" :disabled="atEnd" @click="scroll(1)">
    <svg class="icon" aria-hidden="true"><use href="#i-arrow" /></svg>
  </button>
</template>
