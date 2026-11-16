<script setup lang="ts">
import { onMounted, onUnmounted, ref, shallowRef } from 'vue'

type Decision = 'approve' | 'reject'
interface JoinRequest {
  pk: number
  user__username: string
}

const { room, count, empty } = defineProps<{
  room: HTMLElement
  count: HTMLElement | null
  empty: HTMLElement | null
}>()
const entries = shallowRef<JoinRequest[]>([])
const busy = ref(false)
const listeners = new AbortController()

function updateQueue(event: Event) {
  const update = (event as CustomEvent<{ pending: JoinRequest[]; pending_count: number }>).detail
  entries.value = update.pending
  if (count) count.textContent = String(update.pending_count)
  if (empty) empty.hidden = update.pending.length > 0
}

function decide(action: Decision, id: number) {
  room.dispatchEvent(new CustomEvent('lumiere:room-queue-decision', {
    detail: { action, id },
  }))
}

onMounted(() => {
  const { signal } = listeners
  room.addEventListener('lumiere:room-queue-update', updateQueue, { signal })
  room.addEventListener('lumiere:room-queue-busy', event => {
    busy.value = (event as CustomEvent<boolean>).detail
  }, { signal })
  document.addEventListener('lumiere:stop', () => { busy.value = true }, { signal })
})
onUnmounted(() => listeners.abort())
</script>

<template>
  <li v-for="entry in entries" :key="entry.pk">
    <strong>{{ entry.user__username }}</strong>
    <span>
      <button type="button" class="btn small" :disabled="busy" :aria-label="`Duyệt ${entry.user__username}`" @click="decide('approve', entry.pk)">Duyệt</button>
      <button type="button" class="btn small secondary" :disabled="busy" :aria-label="`Từ chối ${entry.user__username}`" @click="decide('reject', entry.pk)">Từ chối</button>
    </span>
  </li>
</template>
