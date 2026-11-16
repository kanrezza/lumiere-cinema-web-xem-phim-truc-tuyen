<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { mountTheme } from './theme'
import { mountNavigation } from './navigation'
import { mountLandingTabs } from './landing'
import { mountLandingMotion } from './landing-motion'
import { mountMotion } from './motion'
import { mountHeader } from './header'

let dispose: (() => void)[] = []
onMounted(() => {
  dispose = [mountTheme(), mountNavigation(), mountHeader(), mountMotion(), mountLandingTabs(), mountLandingMotion()]
})
onUnmounted(() => { for (const stop of dispose) stop() })
</script>

<template><span hidden></span></template>
