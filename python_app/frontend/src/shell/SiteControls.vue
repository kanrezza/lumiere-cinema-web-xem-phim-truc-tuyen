<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { mountTheme } from './theme'
import { mountNavigation } from './navigation'
import { mountLandingTabs } from './landing'

let dispose: (() => void)[] = []
onMounted(() => { dispose = [mountTheme(), mountNavigation(), mountLandingTabs()] })
onUnmounted(() => { for (const stop of dispose) stop() })
</script>

<template><span hidden></span></template>
