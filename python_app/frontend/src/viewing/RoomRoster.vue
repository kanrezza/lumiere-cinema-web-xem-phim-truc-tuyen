<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, shallowRef } from 'vue'

interface RoomMember {
  user_id: number
  user__username: string
}

const { room, count } = defineProps<{ room: HTMLElement; count: HTMLElement | null }>()
const currentUser = room.dataset.user ?? ''
const host = room.dataset.hostUser ?? ''
const isHost = room.dataset.host === 'true'
const roster = shallowRef<RoomMember[]>([])
const listeners = new AbortController()

function initial(name: string) {
  return Array.from(name.trim())[0]?.toUpperCase() || '?'
}

function roleFor(id: number) {
  const role = String(id) === host ? 'Chủ phòng' : 'Thành viên'
  return String(id) === currentUser ? `${role} · Bạn` : role
}

async function applyRoster(event: Event) {
  const update = (event as CustomEvent<RoomMember[]>).detail
  roster.value = update
  if (count) count.textContent = String(update.length)
  await nextTick()
  room.dispatchEvent(new Event('lumiere:room-members'))
}

function kick(member: RoomMember, event: MouseEvent) {
  room.dispatchEvent(new CustomEvent('lumiere:room-kick', {
    detail: { member, button: event.currentTarget },
  }))
}

onMounted(() => room.addEventListener('lumiere:roster-update', applyRoster, { signal: listeners.signal }))
onUnmounted(() => listeners.abort())
</script>

<template>
  <div v-for="member in roster" :key="member.user_id" class="room-member"
       :data-member-id="member.user_id" :data-member-name="member.user__username">
    <span class="room-member-avatar" aria-hidden="true">{{ initial(member.user__username) }}</span>
    <span class="room-member-info">
      <strong class="room-member-name">{{ member.user__username }}</strong>
      <span class="room-member-role">{{ roleFor(member.user_id) }}</span>
    </span>
    <span class="room-member-voice-state" data-member-voice-state></span>
    <div class="room-member-actions" data-member-actions>
      <button v-if="isHost && String(member.user_id) !== currentUser"
              type="button" class="room-member-action room-member-kick" title="Loại khỏi phòng"
              :aria-label="`Loại ${member.user__username} khỏi phòng`" @click="kick(member, $event)">×</button>
    </div>
  </div>
</template>
