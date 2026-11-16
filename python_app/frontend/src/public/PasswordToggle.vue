<script setup lang="ts">
import { computed, ref } from 'vue'

const props = defineProps<{ field: HTMLInputElement }>()
const visible = ref(false)
const label = computed(() => visible.value ? 'Ẩn mật khẩu' : 'Hiện mật khẩu')

function toggle() {
  visible.value = !visible.value
  props.field.type = visible.value ? 'text' : 'password'
}
</script>

<template>
  <button class="text-button password-visibility" type="button" :aria-controls="field.id" @click="toggle">{{ label }}</button>
</template>
