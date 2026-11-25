<script setup lang="ts">
import { useRoomPlaylist } from './use-room-playlist'

const { room } = defineProps<{ room: HTMLElement }>()
const {
  items, canManage, loaded, busy, message, failed, currentEpisode, filmEnded, draggedItem,
  pendingSuggestions, mySuggestions, nextItem, disabled, change, move, drag, drop,
} = useRoomPlaylist(room)
</script>

<template>
  <section class="cinema-playlist" aria-labelledby="room-playlist-title" :aria-busy="busy">
    <h2 id="room-playlist-title" class="sr-only">Danh sách xem</h2>
    <p class="playlist-notice" :class="{ 'is-error': failed }" role="status" aria-live="polite">{{ message }}</p>
    <div v-if="loaded && !items.length" class="playlist-empty"><p>Danh sách đang trống. {{ canManage ? 'Thêm phim để chuẩn bị buổi xem.' : 'Bạn có thể đề xuất một phim cho chủ phòng.' }}</p></div>
    <ol v-else class="playlist-list" aria-label="Thứ tự xem phim">
      <li v-for="(item, index) in items" :key="item.id" class="playlist-item" :class="{ 'is-current': currentEpisode === item.episode_id, 'is-dragging': draggedItem === item.id }" :draggable="canManage && !disabled" @dragstart="drag($event, item)" @dragend="draggedItem = null" @dragover.prevent @drop="drop($event, item.id)">
        <span class="playlist-number">{{ index + 1 }}</span>
        <img class="playlist-poster" v-if="item.poster_url" :src="item.poster_url" alt="" loading="lazy" width="48" height="66">
        <div class="playlist-copy"><h3>{{ item.title }}</h3><p>{{ item.episode_title }}</p><span v-if="currentEpisode === item.episode_id" class="playlist-current">Đang xem</span><span v-else-if="!item.available" class="playlist-unavailable">Chưa có bản xem</span></div>
        <div v-if="canManage" class="playlist-actions">
          <button type="button" :disabled="disabled || !item.available" class="playlist-play" :aria-label="`Phát ${item.title}`" @click="change('play', {item: item.id})">Phát</button>
          <button type="button" :disabled="disabled || index === 0" class="playlist-icon" :aria-label="`Đưa ${item.title} lên trước`" title="Đưa lên trước" @click="move(item.id, -1)">↑</button>
          <button type="button" :disabled="disabled || index === items.length - 1" class="playlist-icon" :aria-label="`Đưa ${item.title} xuống sau`" title="Đưa xuống sau" @click="move(item.id, 1)">↓</button>
          <button type="button" :disabled="disabled" class="playlist-icon" :aria-label="`Bỏ ${item.title} khỏi danh sách`" @click="change('remove', {item: item.id})">×</button>
        </div>
      </li>
    </ol>
    <div v-if="canManage && nextItem" class="playlist-next" :class="{ 'is-ready': filmEnded }" data-room-next>
      <div><span>{{ filmEnded ? 'Phim vừa kết thúc' : 'Tiếp theo trong danh sách' }}</span><strong>{{ nextItem.title }}</strong><small>{{ nextItem.episode_title }}</small></div>
      <button class="btn small" type="button" :disabled="disabled" @click="change('play', {item: nextItem.id})">{{ currentEpisode ? 'Phát tiếp theo' : 'Bắt đầu xem' }}</button>
    </div>
    <section v-if="canManage && pendingSuggestions.length" class="playlist-suggestions" aria-labelledby="room-suggestions-title">
      <h3 id="room-suggestions-title" class="suggestion-heading">Phim được đề xuất <span>{{ pendingSuggestions.length }}</span></h3>
      <ul class="suggestion-list">
        <li class="suggestion-item" v-for="entry in pendingSuggestions" :key="entry.id">
          <div class="suggestion-copy"><strong>{{ entry.title }}</strong><small>{{ entry.episode_title }} · {{ entry.proposed_by }}</small></div>
          <div class="suggestion-actions"><button type="button" :disabled="disabled || !entry.available" @click="change('approve', {suggestion: entry.id})">Thêm</button><button type="button" :disabled="disabled" @click="change('reject', {suggestion: entry.id})">Từ chối</button></div>
        </li>
      </ul>
    </section>
    <section v-else-if="!canManage && mySuggestions.length" class="playlist-suggestions" aria-labelledby="room-suggestions-title">
      <h3 id="room-suggestions-title" class="suggestion-heading">Đề xuất của bạn</h3>
      <ul class="suggestion-list"><li class="suggestion-item" v-for="entry in mySuggestions" :key="entry.id"><div class="suggestion-copy"><strong>{{ entry.title }}</strong><small>{{ entry.episode_title }}</small></div><span>{{ entry.status === 'approved' ? 'Đã thêm' : entry.status === 'rejected' ? 'Đã từ chối' : 'Chờ chủ phòng' }}</span></li></ul>
    </section>
  </section>
</template>
