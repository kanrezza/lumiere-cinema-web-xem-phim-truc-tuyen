<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const props = defineProps<{ field: HTMLTextAreaElement }>()
const used = ref(props.field.value.length)
const limit = props.field.maxLength
function update() {
  used.value = props.field.value.length
}
onMounted(() => props.field.addEventListener('input', update))
onUnmounted(() => props.field.removeEventListener('input', update))
</script>

<template>
  <small class="public-character-count muted" aria-hidden="true">{{ used }}/{{ limit }} ký tự</small>
</template>
