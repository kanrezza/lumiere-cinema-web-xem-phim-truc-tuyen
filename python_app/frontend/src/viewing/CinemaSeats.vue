<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import type { RoomMember } from './room-driver'
import { allocateSeats, seatDisplayName, seatIsSpeaking, seatLabel } from './seat-state'
import type { SeatVoiceMode } from './seat-state'

interface SeatVoiceMember { id: string; mode: SeatVoiceMode; disabled: boolean }
const { room } = defineProps<{room: HTMLElement}>()
const hostId = Number(room.dataset.hostUser)
const viewerId = Number(room.dataset.user)
const isHost = room.dataset.host === 'true'
const members = shallowRef<RoomMember[]>([])
const assignments = shallowRef<(number | null)[]>(Array(10).fill(null))
const voices = shallowRef(new Map<string, SeatVoiceMember>())
const speakers = shallowRef(new Set<string>())
const failedAvatars = shallowRef<Record<number, string>>({})
const selectedId = ref<number | null>(null)
const menu = ref<HTMLElement | null>(null)
let opener: HTMLButtonElement | null = null
const listeners = new AbortController()

const seats = computed(() => {
  const lookup = new Map(members.value.map(member => [member.user_id, member]))
  return assignments.value.map((id, index) => ({index, member: id === null ? undefined : lookup.get(id)}))
})

function initial(member: RoomMember) {
  return Array.from(seatDisplayName(member).trim())[0]?.toUpperCase() || '?'
}
function role(member: RoomMember) {
  const base = member.user_id === hostId ? 'Chủ phòng' : 'Thành viên'
  return member.user_id === viewerId ? `${base} · Bạn` : base
}
function voice(member: RoomMember) { return voices.value.get(String(member.user_id)) }
function speaking(member: RoomMember) { return seatIsSpeaking(voice(member)?.mode, speakers.value.has(String(member.user_id))) }
function micOff(member: RoomMember) { return voice(member)?.mode !== 'speaking' }
function voiceLabel(member: RoomMember) {
  const mode = voice(member)?.mode
  if (mode === 'muted') return 'Chủ phòng đã khóa mic'
  if (mode === 'off' || !mode) return 'Chưa tham gia thoại'
  if (mode === 'listening') return 'Mic đang tắt'
  return speaking(member) ? 'Đang nói' : 'Mic đang bật'
}
function avatar(member: RoomMember) {
  const url = member.avatar_url?.trim() || ''
  if (failedAvatars.value[member.user_id] === url) return ''
  return url.startsWith('/') && !url.startsWith('//') || /^https?:\/\//i.test(url) ? url : ''
}
function avatarFailed(member: RoomMember) {
  failedAvatars.value = {...failedAvatars.value, [member.user_id]: member.avatar_url || ''}
}
function bindMenu(element: Element | ComponentPublicInstance | null) {
  menu.value = element instanceof HTMLElement ? element : null
}
function closeMenu(restoreFocus = true) {
  selectedId.value = null
  if (restoreFocus && opener?.isConnected) opener.focus({preventScroll: true})
  opener = null
}
async function openMenu(member: RoomMember, event: MouseEvent) {
  const trigger = event.currentTarget as HTMLButtonElement
  if (selectedId.value === member.user_id) {closeMenu(); return}
  selectedId.value = member.user_id
  opener = trigger
  await nextTick()
  const focusTarget = menu.value?.querySelector<HTMLButtonElement>('button:not(:disabled)') || menu.value
  focusTarget?.focus({preventScroll: true})
}
function kick(member: RoomMember, event: MouseEvent) {
  if (!isHost || member.user_id === viewerId) return
  room.dispatchEvent(new CustomEvent('lumiere:room-kick', {detail: {member, button: event.currentTarget}}))
  closeMenu(false)
}
async function roster(event: Event) {
  const incoming = (event as CustomEvent<RoomMember[]>).detail
  members.value = incoming
  assignments.value = allocateSeats(assignments.value, incoming, hostId)
  if (selectedId.value !== null && !incoming.some(member => member.user_id === selectedId.value)) closeMenu(false)
  await nextTick()
  room.dispatchEvent(new Event('lumiere:room-members'))
}
function outside(event: Event) {
  if (selectedId.value === null || !(event.target instanceof Node)) return
  if (!menu.value?.contains(event.target) && !opener?.contains(event.target)) closeMenu(false)
}
function keyboard(event: KeyboardEvent) {
  if (selectedId.value === null || event.key !== 'Escape') return
  event.preventDefault()
  event.stopPropagation()
  closeMenu()
}

onMounted(() => {
  room.addEventListener('lumiere:roster-update', roster, {signal: listeners.signal})
  room.addEventListener('lumiere:voice-members', event => {
    const states = (event as CustomEvent<SeatVoiceMember[]>).detail
    voices.value = new Map(states.map(state => [state.id, state]))
  }, {signal: listeners.signal})
  room.addEventListener('lumiere:voice-activity', event => {
    const states = (event as CustomEvent<{id: string; speaking: boolean}[]>).detail
    speakers.value = new Set(states.filter(state => state.speaking).map(state => state.id))
  }, {signal: listeners.signal})
  document.addEventListener('pointerdown', outside, {signal: listeners.signal})
  document.addEventListener('keydown', keyboard, {signal: listeners.signal})
})
onUnmounted(() => listeners.abort())
</script>

<template>
  <section class="cinema-audience-live" aria-labelledby="cinema-seats-title">
    <div class="cinema-seats-heading"><h2 id="cinema-seats-title">Ghế trong rạp <span>{{ members.length }} / 10</span></h2><p>{{ isHost ? 'Bấm vào một người để quản lý' : 'Cùng nhau trong một buổi chiếu' }}</p></div>
    <ol class="cinema-seating-grid" aria-label="Chỗ ngồi của thành viên">
      <li v-for="seat in seats" :key="seat.index" class="cinema-seat-place" :class="{
        'is-occupied': Boolean(seat.member),
        'is-speaking': seat.member && speaking(seat.member),
        'is-muted': seat.member && micOff(seat.member),
        'is-self': seat.member?.user_id === viewerId,
      }" :data-seat="seat.index + 1" :data-member-id="seat.member?.user_id" :data-speaking="seat.member ? String(speaking(seat.member)) : undefined" :aria-label="seat.member ? undefined : `Ghế trống ${seatLabel(seat.index)}`">
        <template v-if="seat.member">
          <button type="button" class="cinema-seat-person" :aria-expanded="selectedId === seat.member.user_id" aria-haspopup="dialog" :aria-controls="`cinema-seat-menu-${seat.member.user_id}`" :aria-label="`Ghế ${seatLabel(seat.index)}, ${seatDisplayName(seat.member)}, ${role(seat.member)}, ${voiceLabel(seat.member)}`" :title="`${seatDisplayName(seat.member)} · ${voiceLabel(seat.member)}`" @click="openMenu(seat.member, $event)">
            <span class="cinema-seat-avatar"><img v-if="avatar(seat.member)" :src="avatar(seat.member)" alt="" width="46" height="46" @error="avatarFailed(seat.member)"><span v-else>{{ initial(seat.member) }}</span></span>
            <span class="cinema-seat-mic" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><template v-if="micOff(seat.member)"><path d="m3 3 18 18M9 9v3a3 3 0 0 0 5.1 2.1M9 5V4a3 3 0 0 1 6 0v7M5 11v1a7 7 0 0 0 12 4.9M19 11v1c0 .5-.1 1-.2 1.5M12 19v3m-3 0h6"/></template><template v-else><rect x="9" y="2" width="6" height="13" rx="3"/><path d="M5 11a7 7 0 0 0 14 0m-7 7v4m-3 0h6"/></template></svg></span>
          </button>
          <button v-if="isHost && seat.member.user_id !== viewerId" class="cinema-seat-kick" type="button" :aria-label="`Loại ${seatDisplayName(seat.member)} khỏi phòng`" title="Loại khỏi phòng" @click.stop="kick(seat.member, $event)">×</button>
          <strong class="cinema-seat-name" :title="seatDisplayName(seat.member)">{{ seatDisplayName(seat.member) }}</strong>
          <span class="cinema-seat-role">{{ seatLabel(seat.index) }} · {{ role(seat.member) }}</span>
          <div v-if="selectedId === seat.member.user_id" :id="`cinema-seat-menu-${seat.member.user_id}`" :ref="bindMenu" class="cinema-seat-menu" role="dialog" :aria-label="`Thông tin ${seatDisplayName(seat.member)}`" tabindex="-1">
            <div class="cinema-seat-menu-title"><strong>{{ seatDisplayName(seat.member) }}</strong><button type="button" aria-label="Đóng thông tin thành viên" @click="closeMenu()">×</button></div>
            <p>{{ role(seat.member) }} · {{ voiceLabel(seat.member) }}</p>
            <div v-if="isHost && seat.member.user_id !== viewerId" class="cinema-seat-menu-actions">
              <button type="button" :data-voice-mute="seat.member.user_id" :data-muted="String(voice(seat.member)?.mode === 'muted')" :disabled="voice(seat.member)?.disabled ?? true">{{ voice(seat.member)?.mode === 'muted' ? 'Cho phép bật mic' : 'Tắt mic' }}</button>
              <button type="button" @click="kick(seat.member, $event)">Loại khỏi phòng</button>
            </div>
            <small v-if="isHost && seat.member.user_id !== viewerId">Khi được mở quyền nói, người xem tự bật lại mic.</small>
          </div>
        </template>
        <template v-else><span class="cinema-seat-empty" aria-hidden="true"></span><span class="cinema-seat-name" aria-hidden="true"></span><span class="cinema-seat-role" aria-hidden="true">{{ seatLabel(seat.index) }}</span></template>
      </li>
    </ol>
    <p class="cinema-seats-legend"><span aria-hidden="true"></span> Viền sáng khi đang nói · Biểu tượng gạch chéo khi mic tắt</p>
  </section>
</template>
