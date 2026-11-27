<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import type { ChatMessage } from './room-types'

const { room, log, empty } = defineProps<{
  room: HTMLElement
  log: HTMLElement
  empty: HTMLElement | null
}>()
const messages = shallowRef<ChatMessage[]>([])
const failedAvatars = shallowRef(new Set<string>())
const unread = ref(0)
const collapsed = ref(false)
const listeners = new AbortController()
const panel = log.closest<HTMLElement>('.room-chat')
const body = panel?.querySelector<HTMLElement>('[data-chat-body]')
const collapseButton = panel?.querySelector<HTMLButtonElement>('[data-chat-toggle]')
const unreadMount = panel?.querySelector<HTMLElement>('[data-chat-unread]')
const input = panel?.querySelector<HTMLInputElement>('#chat-form input[name=content]')
const emojiButton = panel?.querySelector<HTMLButtonElement>('[data-chat-emoji-toggle]')
const emojiPicker = panel?.querySelector<HTMLElement>('[data-chat-emojis]')
let disposed = false

const fromViewer = (id: number) => String(id) === room.dataset.user
const fromHost = (id: number) => String(id) === room.dataset.hostUser
const authorName = (message: ChatMessage) => message.display_name?.trim() || `@${message.user}`
const initial = (message: ChatMessage) => Array.from(message.display_name?.trim() || message.user)[0]?.toLocaleUpperCase('vi') || '?'
const nearBottom = () => !collapsed.value && log.scrollHeight - log.scrollTop - log.clientHeight < 48

function avatarFailed(url: string | undefined) {
  if (url) failedAvatars.value = new Set([...failedAvatars.value, url])
}

function readLatest() {
  log.scrollTop = log.scrollHeight
  unread.value = 0
}

function updateReadPosition() {
  if (nearBottom()) unread.value = 0
}

function closeEmoji() {
  if (emojiPicker) emojiPicker.hidden = true
  emojiButton?.setAttribute('aria-expanded', 'false')
}

function toggleChat() {
  if (!body || !collapseButton) return
  collapsed.value = !collapsed.value
  body.hidden = collapsed.value
  panel?.classList.toggle('is-collapsed', collapsed.value)
  collapseButton.setAttribute('aria-expanded', String(!collapsed.value))
  const label = collapsed.value ? 'Mở trò chuyện' : 'Thu gọn trò chuyện'
  collapseButton.setAttribute('aria-label', label)
  collapseButton.title = label
  closeEmoji()
}

function insertEmoji(event: Event) {
  const target = event.target
  const button = target instanceof Element ? target.closest<HTMLButtonElement>('[data-chat-emoji]') : null
  const value = button?.dataset.chatEmoji
  if (!value || !input || input.disabled) return
  const start = input.selectionStart ?? input.value.length
  const end = input.selectionEnd ?? start
  const next = input.value.slice(0, start) + value + input.value.slice(end)
  if (input.maxLength > 0 && next.length > input.maxLength) return
  input.value = next
  input.dispatchEvent(new Event('input', {bubbles: true}))
  input.focus()
  input.setSelectionRange(start + value.length, start + value.length)
  closeEmoji()
}

async function updateChat(event: Event) {
  const { added } = (event as CustomEvent<{ added: ChatMessage[]; own: boolean }>).detail
  if (!added.length || disposed) return
  const follow = nearBottom()
  messages.value = [...messages.value, ...added].slice(-100)
  if (empty) empty.hidden = true
  if (!follow) unread.value += added.length
  await nextTick()
  if (!disposed && follow) readLatest()
}

onMounted(() => {
  const {signal} = listeners
  room.addEventListener('lumiere:chat-update', updateChat, {signal})
  log.addEventListener('scroll', updateReadPosition, {signal, passive: true})
  collapseButton?.addEventListener('click', toggleChat, {signal})
  emojiButton?.addEventListener('click', () => {
    if (!emojiPicker || input?.disabled) return
    emojiPicker.hidden = !emojiPicker.hidden
    emojiButton.setAttribute('aria-expanded', String(!emojiPicker.hidden))
  }, {signal})
  emojiPicker?.addEventListener('click', insertEmoji, {signal})
  document.addEventListener('pointerdown', event => {
    if (event.target instanceof Node && !emojiPicker?.contains(event.target) && !emojiButton?.contains(event.target)) closeEmoji()
  }, {signal})
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && emojiPicker && !emojiPicker.hidden) {
      event.preventDefault()
      closeEmoji()
      emojiButton?.focus()
    }
  }, {signal})
})
onUnmounted(() => {disposed = true; listeners.abort()})
</script>

<template>
  <p v-for="message in messages" :key="message.id" class="room-chat-message"
     :data-own="fromViewer(message.user_id) ? 'true' : undefined">
    <span class="room-chat-avatar" aria-hidden="true">
      <img v-if="message.avatar_url && !failedAvatars.has(message.avatar_url)" :src="message.avatar_url" alt="" width="26" height="26" loading="lazy" @error="avatarFailed(message.avatar_url)">
      <span v-else>{{ initial(message) }}</span>
    </span>
    <span class="room-chat-copy">
      <strong class="room-chat-author" :data-host="fromHost(message.user_id) ? 'true' : undefined" :title="`@${message.user}`">{{ authorName(message) }}</strong>
      <svg v-if="fromHost(message.user_id)" class="room-chat-host" viewBox="0 0 20 20" role="img" aria-label="Chủ phòng"><path d="m3 6 4 3 3-5 3 5 4-3-2 9H5Z"/></svg>
      <span class="room-chat-body">{{ message.content }}</span>
    </span>
  </p>
  <Teleport v-if="unreadMount" :to="unreadMount">
    <button v-show="unread > 0" class="room-chat-new" type="button" @click="readLatest">
      {{ unread }} tin nhắn mới <span aria-hidden="true">↓</span>
    </button>
  </Teleport>
</template>
