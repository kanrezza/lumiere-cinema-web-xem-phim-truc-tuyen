<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{
  options: { value: string; label: string; disabled: boolean }[]
  current: string
}>()
const selected = ref(props.current)
</script>

<template>
  <label>Đánh giá
    <select v-model="selected" name="score" required>
      <option v-for="option in options" :key="option.value" :value="option.value" :disabled="option.disabled">{{ option.label }}</option>
    </select>
  </label>
  <button class="btn small secondary" :disabled="!selected">Gửi đánh giá</button>
</template>
