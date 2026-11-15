<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { CatalogData } from './types'

const props = defineProps<{ catalogPath: string; data: CatalogData }>()
const emit = defineEmits<{ apply: [params: URLSearchParams] }>()
function formValues(data: CatalogData) {
  return { ...data.values, sort: data.values.sort === 'rating' ? 'rating' : '' }
}
const values = reactive(formValues(props.data))
watch(() => props.data, data => Object.assign(values, formValues(data)))

function apply(event: Event) {
  const form = event.currentTarget as HTMLFormElement
  const params = new URLSearchParams()
  for (const [key, value] of new FormData(form)) {
    if (typeof value === 'string' && value.trim()) params.append(key, value.trim())
  }
  if (!params.size) params.set('sort', 'newest')
  emit('apply', params)
}
</script>

<template>
  <form id="browse-search" class="browse-filters catalog-filters" method="get" :action="catalogPath" @submit.prevent="apply">
    <input type="hidden" name="access" :value="values.access">
    <input type="hidden" name="actor" :value="values.actor">
    <input type="hidden" name="availability" :value="values.availability">
    <input type="hidden" name="release" :value="values.release">
    <input type="hidden" name="trailer" :value="values.trailer">
    <label class="browse-query">
      <span class="sr-only">Tìm phim</span>
      <svg class="icon" aria-hidden="true"><use href="#i-search" /></svg>
      <input v-model="values.q" type="search" name="q" placeholder="Tìm phim hoặc diễn viên, có dấu hoặc không dấu…">
    </label>
    <a class="reset-filter" :href="catalogPath">Xóa bộ lọc</a>
    <label class="catalog-filter">
      <span>Thể loại</span>
      <select v-model="values.category" name="category">
        <option value="">Tất cả thể loại</option>
        <option v-for="option in data.categories" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
    </label>
    <label class="catalog-filter">
      <span>Quốc gia</span>
      <select v-model="values.country" name="country">
        <option value="">Tất cả quốc gia</option>
        <option v-for="option in data.countries" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
    </label>
    <label class="catalog-filter">
      <span>Năm phát hành</span>
      <select v-model="values.year" name="year">
        <option value="">Tất cả năm</option>
        <option v-for="year in data.years" :key="year" :value="String(year)">{{ year }}</option>
      </select>
    </label>
    <label class="catalog-filter">
      <span>Định dạng</span>
      <select v-model="values.kind" name="kind">
        <option value="">Tất cả phim</option>
        <option value="movie">Phim lẻ</option>
        <option value="series">Phim bộ</option>
      </select>
    </label>
    <label class="catalog-filter">
      <span>Sắp xếp</span>
      <select v-model="values.sort" name="sort">
        <option value="">Mới nhất</option>
        <option value="rating">Đánh giá cao</option>
      </select>
    </label>
    <button class="btn secondary" type="submit">Áp dụng</button>
  </form>
</template>
