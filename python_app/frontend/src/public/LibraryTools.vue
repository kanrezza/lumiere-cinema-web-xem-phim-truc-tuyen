<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{ form: HTMLFormElement }>()
const fields = [...props.form.querySelectorAll<HTMLInputElement>('input[name="movies"][type="checkbox"]')]
const selected = ref(0)
const submitting = ref(false)
const allSelected = computed(() => fields.length > 0 && selected.value === fields.length)
function syncSelection() {
  selected.value = fields.filter(field => field.checked).length
}
function togglePage(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  for (const field of fields) field.checked = checked
  syncSelection()
}
function onSubmit(event: Event) {
  if (!selected.value || submitting.value) {
    event.preventDefault()
    return
  }
  submitting.value = true
}
function onPageShow() {
  submitting.value = false
  syncSelection()
}
onMounted(() => {
  syncSelection()
  props.form.addEventListener('change', syncSelection)
  props.form.addEventListener('submit', onSubmit)
  window.addEventListener('pageshow', onPageShow)
})
onBeforeUnmount(() => {
  props.form.removeEventListener('change', syncSelection)
  props.form.removeEventListener('submit', onSubmit)
  window.removeEventListener('pageshow', onPageShow)
})
</script>

<template>
  <label class="library-select-page"><input type="checkbox" :checked="allSelected" :indeterminate="selected > 0 && !allSelected" @change="togglePage">Chọn trang này</label>
  <span class="library-selection-count" role="status" aria-live="polite">{{ selected ? `Đã chọn ${selected} / ${fields.length} phim` : `${fields.length} phim trên trang` }}</span>
  <button class="btn secondary small library-remove" type="submit" :disabled="!selected || submitting">{{ submitting ? 'Đang xóa…' : 'Xóa phim đã chọn' }}</button>
</template>
