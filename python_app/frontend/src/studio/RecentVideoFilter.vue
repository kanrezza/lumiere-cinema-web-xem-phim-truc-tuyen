<script setup lang="ts">
import { computed, onUnmounted, ref, watchEffect } from 'vue'

const props = defineProps<{
  rows: { row: HTMLTableRowElement; status: string }[]
  options: { value: string; label: string }[]
}>()

const status = ref('')
const visibleRows = computed(() => props.rows.filter(item => !status.value || item.status === status.value))

watchEffect(() => {
  const visible = new Set(visibleRows.value)
  for (const item of props.rows) item.row.hidden = !visible.has(item)
})

onUnmounted(() => {
  for (const item of props.rows) item.row.hidden = false
})
</script>

<template>
  <div class="sd-video-filter">
    <label for="studio-video-status">Lọc video theo trạng thái</label>
    <select id="studio-video-status" v-model="status">
      <option value="">Tất cả trạng thái</option>
      <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
    </select>
    <span role="status">{{ visibleRows.length }} / {{ rows.length }} video</span>
  </div>
</template>
