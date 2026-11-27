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
  if (count) {
    count.textContent = String(update.pending_count)
    count.closest<HTMLElement>('[data-room-approval-toggle]')?.setAttribute('data-pending', String(update.pending_count > 0))
  }
  for (const total of room.querySelectorAll('[data-room-pending-total]')) total.textContent = String(update.pending_count)
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
  <li v-for="entry in entries" :key="entry.pk" class="admission-request">
    <span class="admission-guest-avatar" aria-hidden="true">{{ Array.from(entry.user__username)[0]?.toUpperCase() }}</span>
    <div class="admission-guest-copy"><strong>{{ entry.user__username }}</strong><small>Muốn tham gia buổi chiếu</small></div>
    <span class="admission-decisions">
      <button type="button" class="admission-allow" :disabled="busy" :aria-label="`Duyệt ${entry.user__username}`" @click="decide('approve', entry.pk)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 4 4L19 6"/></svg>Cho vào</button>
      <button type="button" class="admission-decline" :disabled="busy" :aria-label="`Từ chối ${entry.user__username}`" title="Từ chối" @click="decide('reject', entry.pk)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>
    </span>
  </li>
</template>
