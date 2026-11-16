<script setup lang="ts">
import { onUnmounted, ref } from 'vue'

const props = defineProps<{ input: HTMLInputElement }>()
const visible = ref(false)

function toggle() {
  visible.value = !visible.value
  props.input.type = visible.value ? 'text' : 'password'
}

onUnmounted(() => { props.input.type = 'password' })
</script>

<template>
  <button type="button" class="studio-password-toggle" :aria-controls="input.id"
          :aria-pressed="visible" @click="toggle">
    {{ visible ? 'Ẩn mật khẩu' : 'Hiện mật khẩu' }}
  </button>
</template>
