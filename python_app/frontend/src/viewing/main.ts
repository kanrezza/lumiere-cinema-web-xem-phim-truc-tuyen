import { createApp } from 'vue'
import NextEpisode from './NextEpisode.vue'
import PlayerControls from './PlayerControls.vue'
import RoomChat from './RoomChat.vue'
import RoomLobby from './RoomLobby.vue'
import RoomQueue from './RoomQueue.vue'
import RoomRoster from './RoomRoster.vue'
import TrailerPlayer from './TrailerPlayer.vue'
import { mountVoiceControls } from './voice-controls'
import { initVoice } from './voice-driver'
import { initRoom } from './room-driver'
import { initAdmission } from './admission-driver'
import { initPlayback } from './playback'
import { initCaptions } from './captions'

const video = document.getElementById('player')
if (video instanceof HTMLVideoElement) {
  const wrap = video.closest<HTMLElement>('.player-wrap')
  const root = wrap?.querySelector('[data-vue-player-controls]')
  if (wrap && root) {
    const fallback = [wrap.querySelector('.player-center'), wrap.querySelector('.player-controls')]
    const app = createApp(PlayerControls, { video, wrap, status: document.getElementById('player-status') })
    app.mount(root)
    if (root.querySelector('.player-controls')) {
      fallback.forEach(node => node?.remove())
      wrap.dataset.vuePlayer = 'true'
      initCaptions(video)
    } else app.unmount()
  }

  const next = wrap?.querySelector<HTMLElement>('[data-next-episode]')
  const legacySetting = document.querySelector<HTMLElement>('[data-autoplay-setting]')
  const href = next?.querySelector<HTMLAnchorElement>('[data-next-link]')?.getAttribute('href')
  const title = next?.querySelector('h2')?.textContent?.trim()
  if (next && legacySetting && href && title) {
    const mount = document.createElement('div')
    const preference = document.createElement('span')
    mount.dataset.vueNext = ''
    preference.dataset.vueNextPreference = ''
    next.after(mount)
    legacySetting.after(preference)
    const app = createApp(NextEpisode, { video, title, href, preference, viewer: wrap?.dataset.viewer ?? '' })
    app.mount(mount)
    if (mount.querySelector('[data-next-episode]')) {
      next.remove()
      legacySetting.remove()
    } else {
      app.unmount()
      mount.remove()
      preference.remove()
    }
  }
  initPlayback(video)
}

const room = document.getElementById('room')
if (room) {
  mountVoiceControls(room)
  const queue = room.querySelector<HTMLElement>('[data-room-queue]')
  if (queue) {
    createApp(RoomQueue, {
      room, count: room.querySelector('[data-room-pending-count]'),
      empty: room.querySelector('[data-room-queue-empty]'),
    }).mount(queue)
    queue.dataset.vueRoomQueue = 'true'
  }
  const log = document.getElementById('chat-messages')
  const roster = document.getElementById('members')
  if (log && roster) {
    createApp(RoomChat, { room, log, empty: room.querySelector('[data-room-chat-empty]') }).mount(log)
    createApp(RoomRoster, { room, count: room.querySelector('[data-room-member-count]') }).mount(roster)
    room.dataset.vueRoom = 'true'
  }
  if (video instanceof HTMLVideoElement) initRoom(room, video)
  initAdmission(room)
  initVoice(room)
}

const lobby = document.querySelector<HTMLElement>('[data-room-lobby]')
if (lobby?.dataset.roomLobby) {
  const root = lobby.querySelector('[data-vue-lobby]')
  const form = lobby.querySelector<HTMLFormElement>('[data-lobby-form]')
  const checkUrl = lobby.querySelector<HTMLAnchorElement>('[data-lobby-pending] a')?.getAttribute('href')
  const status = lobby.dataset.lobbyStatus
  const initialStatus = status === 'pending' || status === 'approved' || status === 'rejected' ? status : 'open'
  const csrf = form?.querySelector<HTMLInputElement>('[name=csrfmiddlewaretoken]')?.value
  if (root && checkUrl && (initialStatus === 'rejected' || (form && csrf))) {
    const fallback = [...lobby.children].filter(child => child !== root)
    const app = createApp(RoomLobby, {
      endpoint: lobby.dataset.roomLobby, checkUrl, initialStatus,
      initialRequiresApproval: lobby.dataset.requiresApproval === 'true',
      action: form?.getAttribute('action') ?? '',
      csrf: csrf ?? '',
      passwordProtected: Boolean(form?.querySelector('[data-lobby-password]')),
    })
    app.mount(root)
    if (root.querySelector('[data-lobby-pending], [data-lobby-rejected], [data-lobby-form]')) {
      fallback.forEach(child => child.remove())
      lobby.dataset.vueLobby = 'true'
    } else app.unmount()
  }
}

const trailer = document.querySelector<HTMLElement>('[data-trailer-player]')
if (trailer) {
  const mount = trailer.querySelector('[data-vue-trailer]')
  if (mount) {
    createApp(TrailerPlayer, {
      player: trailer, button: trailer.querySelector('[data-trailer-load]'),
      placeholder: trailer.querySelector('[data-trailer-placeholder]'),
      status: document.querySelector('[data-trailer-status]'),
    }).mount(mount)
    trailer.dataset.vueTrailer = 'true'
  }
}
