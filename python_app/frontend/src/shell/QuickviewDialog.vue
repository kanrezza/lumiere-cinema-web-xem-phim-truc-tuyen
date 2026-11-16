<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'

const dialog = ref<HTMLDialogElement>()
const movie = ref<DOMStringMap>()
let returnFocus: HTMLButtonElement | undefined
let pointerStartedOutside = false
let addedScrollLock = false

const meta = computed(() => {
  const data = movie.value
  if (!data) return ''
  return [data.movieYear, data.movieKind, data.movieDuration && `${data.movieDuration} phút`].filter(Boolean).join(' · ')
})
const imdb = computed(() => {
  const id = movie.value?.movieImdbId ?? ''
  const rating = movie.value?.movieImdbRating ?? ''
  const score = Number(rating)
  if (!/^tt[0-9]{7,10}$/.test(id) || !/^[0-9]+(?:\.[0-9])?$/.test(rating) || score < 1 || score > 10) return
  return {
    url: `https://www.imdb.com/title/${id}/`,
    score: score.toLocaleString('vi-VN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
  }
})

function localUrl(value: string | undefined) {
  if (!value) return
  try {
    const url = new URL(value, location.origin)
    if (url.origin === location.origin && (url.protocol === 'http:' || url.protocol === 'https:')) return url.href
  } catch { /* Invalid movie metadata should never become a link. */ }
}

function reveal(root: ParentNode) {
  for (const button of root.querySelectorAll<HTMLButtonElement>('.quickview-trigger')) button.hidden = false
}

function onRendered(event: Event) {
  if (event.target instanceof HTMLElement) reveal(event.target)
}

async function onClick(event: MouseEvent) {
  if (!(event.target instanceof Element) || dialog.value?.open || returnFocus) return
  const trigger = event.target.closest<HTMLButtonElement>('.quickview-trigger')
  if (!trigger || trigger.hidden || !localUrl(trigger.dataset.movieDetail)) return
  returnFocus = trigger
  movie.value = { ...trigger.dataset }
  await nextTick()
  if (!dialog.value || !trigger.isConnected) {
    returnFocus = undefined
    return
  }
  dialog.value.showModal()
  addedScrollLock = !document.body.classList.contains('quickview-open')
  document.body.classList.add('quickview-open')
}

function isBackdrop(event: MouseEvent) {
  const rect = dialog.value?.getBoundingClientRect()
  return event.target === dialog.value && rect
    && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)
}

function closeOnBackdrop(event: MouseEvent) {
  if (pointerStartedOutside && isBackdrop(event)) dialog.value?.close()
  pointerStartedOutside = false
}

function closed() {
  if (addedScrollLock) document.body.classList.remove('quickview-open')
  addedScrollLock = false
  pointerStartedOutside = false
  if (returnFocus?.isConnected) returnFocus.focus({ preventScroll: true })
  returnFocus = undefined
}

onMounted(() => {
  reveal(document)
  document.addEventListener('lumiere:catalog-render', onRendered)
  document.addEventListener('click', onClick)
})
onUnmounted(() => {
  document.removeEventListener('lumiere:catalog-render', onRendered)
  document.removeEventListener('click', onClick)
  closed()
})
</script>

<template>
  <dialog ref="dialog" class="quickview-dialog" id="movie-quickview" aria-labelledby="quickview-title"
          aria-describedby="quickview-description quickview-status-message" @close="closed"
          @pointerdown="pointerStartedOutside = Boolean(isBackdrop($event))" @click="closeOnBackdrop">
    <div v-if="movie" class="quickview-surface">
      <button class="quickview-close" type="button" aria-label="Đóng xem nhanh" autofocus @click="dialog?.close()">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18" /></svg>
      </button>
      <div class="quickview-hero">
        <img id="quickview-image" :src="localUrl(movie.movieImage)" alt="">
        <div class="quickview-shade"></div><span class="quickview-wordmark">lumière<span>.</span></span>
      </div>
      <div class="quickview-copy">
        <div class="quickview-kicker">
          <span>PHIM TRÊN LUMIÈRE</span>
          <span class="quickview-vip" id="quickview-vip" :hidden="movie.movieVip !== '1'">VIP</span>
          <span class="cinema-tag" id="quickview-cinema" :hidden="movie.movieCinema !== '1'">Chiếu rạp</span>
        </div>
        <h2 id="quickview-title">{{ movie.movieTitle }}</h2>
        <p class="quickview-meta" id="quickview-meta">{{ meta }}</p>
        <div class="quickview-ratings">
          <p class="quickview-availability" id="quickview-status" :class="{ 'is-preparing': movie.movieReady !== '1' }">{{ movie.movieStatus }}</p>
          <a class="imdb-rating" id="quickview-imdb" :href="imdb?.url" :hidden="!imdb" target="_blank" rel="noopener noreferrer"
             :aria-label="imdb ? `Điểm IMDb ${imdb.score} trên 10 — mở nguồn IMDb` : undefined">
            <span class="imdb-wordmark">IMDb</span><span class="imdb-score"><span id="quickview-imdb-score">{{ imdb?.score }}</span><small>/10</small></span>
            <span class="imdb-source-arrow" aria-hidden="true">↗</span>
          </a>
        </div>
        <p class="quickview-description" id="quickview-description">{{ movie.movieDescription }}</p>
        <p class="quickview-status-message" id="quickview-status-message" :hidden="!movie.movieStatusMessage">{{ movie.movieStatusMessage }}</p>
        <div class="quickview-actions">
          <a class="quickview-play" id="quickview-play" :href="movie.movieReady === '1' ? localUrl(movie.moviePlay) : undefined"
             :hidden="movie.movieReady !== '1' || !localUrl(movie.moviePlay)">
            <svg class="icon" aria-hidden="true"><use href="#i-play" /></svg><span id="quickview-play-label">{{ movie.moviePlayLabel }}</span>
          </a>
          <a class="quickview-trailer" id="quickview-trailer" :href="localUrl(movie.movieTrailer)" :hidden="!localUrl(movie.movieTrailer)">
            <svg class="icon" aria-hidden="true"><use href="#i-play" /></svg>Xem trailer
          </a>
          <a class="quickview-details" id="quickview-details" :href="localUrl(movie.movieDetail)">
            Thông tin phim <svg class="icon" aria-hidden="true"><use href="#i-arrow" /></svg>
          </a>
        </div>
      </div>
    </div>
  </dialog>
</template>
