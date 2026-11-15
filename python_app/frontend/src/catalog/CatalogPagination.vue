<script setup lang="ts">
import type { CatalogData } from './types'

defineProps<{ pagination: CatalogData['pagination'] }>()
const emit = defineEmits<{ navigate: [event: MouseEvent, href: string] }>()
</script>

<template>
  <nav v-if="pagination.pages > 1" class="pagination" aria-label="Trang kết quả">
    <a v-if="pagination.previous" class="btn secondary" :href="pagination.previous"
       @click="emit('navigate', $event, pagination.previous)">Trước</a>
    <span>Trang {{ pagination.page }} / {{ pagination.pages }}</span>
    <a v-if="pagination.next" class="btn secondary" :href="pagination.next"
       @click="emit('navigate', $event, pagination.next)">Tiếp</a>
  </nav>
</template>
