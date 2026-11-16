<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, shallowRef } from 'vue'

interface ChatMessage {
  id: number
  user_id: number
  user: string
  content: string
}

const { room, log, empty } = defineProps<{
  room: HTMLElement
  log: HTMLElement
  empty: HTMLElement | null
}>()
const messages = shallowRef<ChatMessage[]>([])
const listeners = new AbortController()
const fromViewer = (id: number) => String(id) === room.dataset.user

async function updateChat(event: Event) {
  const { added, own } = (event as CustomEvent<{ added: ChatMessage[]; own: boolean }>).detail
  const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 60
  messages.value = [...messages.value, ...added].slice(-100)
  if (empty) empty.hidden = messages.value.length > 0
  await nextTick()
  if (nearBottom || own) log.scrollTop = log.scrollHeight
}

onMounted(() => room.addEventListener('lumiere:chat-update', updateChat, { signal: listeners.signal }))
onUnmounted(() => listeners.abort())
</script>

<template>
  <p v-for="message in messages" :key="message.id" class="room-chat-message"
     :data-own="fromViewer(message.user_id) ? 'true' : undefined">
    <strong class="room-chat-author">{{ message.user }}</strong>
    <span class="room-chat-body">{{ message.content }}</span>
  </p>
</template>
