import { csrfToken } from '../shared/http'
import { createVoiceActivityMonitor } from './voice-activity'
import { createVoicePeers } from './voice-peers'
import { postVoiceAction, voiceRequest, VoiceRequestError } from './voice-transport'
import type { VoiceAction, VoiceMember, VoiceSnapshot, VoiceState } from './voice-types'

export function initVoice(room: HTMLElement): void {
  const { voice: initialVoiceUrl, voiceAction: initialActionUrl, user: initialSelfId } = room.dataset
  if (!initialVoiceUrl || !initialActionUrl || !initialSelfId) return

  const initialJoinButton = room.querySelector<HTMLButtonElement>('[data-voice-join]')
  const initialMicButton = room.querySelector<HTMLButtonElement>('[data-voice-mic]')
  const playButton = room.querySelector<HTMLButtonElement>('[data-voice-play]')
  const initialAudioArea = room.querySelector<HTMLElement>('[data-voice-audio]')
  if (!initialJoinButton || !initialMicButton || !initialAudioArea) return

  const voiceUrl = initialVoiceUrl
  const actionUrl = initialActionUrl
  const selfId = initialSelfId
  const joinButton = initialJoinButton
  const micButton = initialMicButton
  const audioArea = initialAudioArea

  const isHost = room.dataset.host === 'true'
  const canListen = typeof window.RTCPeerConnection === 'function'
  const canSpeak = Boolean(window.isSecureContext && navigator.mediaDevices?.getUserMedia)
  const members = new Map<string, VoiceMember>()
  const muteRequests = new Set<string>()
  const leaseLimit = 6000
  let session = ''
  let latestSignal = '0'
  let iceServers: RTCIceServer[] = []
  let selfMuted = false
  let microphone: MediaStreamTrack | null = null
  let pendingMicrophone: MediaStreamTrack | null = null
  let joinBusy = false
  let joining: Promise<boolean> | null = null
  let micBusy = false
  let micChange = 0
  let revision = 0
  let lastSnapshot = 0
  let leaseTimer: number | undefined
  let pollTimer: number | undefined
  let polling = false
  let refreshRequested = false
  let closed = false
  let suspended = false
  let recovering = false
  let notice = ''
  const activity = createVoiceActivityMonitor(detail => {
    room.dispatchEvent(new CustomEvent('lumiere:voice-activity', {detail}))
  })

  const peers = createVoicePeers({
    selfId, audioArea, members, activity, session: () => session, recovering: () => recovering,
    microphone: () => microphone, iceServers: () => iceServers,
    signal: fields => post('signal', fields), changed: render,
  })

  const joinDisabled = () => closed || joinBusy || !canListen
  const micDisabled = () => closed || suspended || selfMuted || micBusy || !canListen || !canSpeak || recovering

  function render() {
    let message = notice
    if (!message) {
      if (closed) message = 'Đã ngắt trò chuyện thoại.'
      else if (recovering) message = 'Đang kết nối lại trò chuyện thoại…'
      else if (!canListen) message = 'Trình duyệt này chưa hỗ trợ trò chuyện thoại.'
      else if (joinBusy) message = 'Đang kết nối âm thanh phòng. Mic đang tắt.'
      else if (!session) message = 'Chưa kết nối âm thanh. Bấm avatar của bạn để thử lại.'
      else if (selfMuted) message = 'Chủ phòng đã tắt mic của bạn. Bạn vẫn nghe được mọi người.'
      else if (peers.retrying()) message = 'Đang thử lại kết nối thoại với thành viên.'
      else if (microphone) message = 'Mic đang bật.'
      else if (!canSpeak) message = 'Bạn đang nghe. Bật mic cần trình duyệt hỗ trợ và kết nối HTTPS.'
      else message = 'Đang nghe phòng. Bấm avatar trên ghế của bạn để bật mic.'
    }
    const micState = selfMuted ? 'muted' : microphone ? 'live' : 'off'
    const showAudio = peers.blockedAudio()
    room.dispatchEvent(new CustomEvent<VoiceState>('lumiere:voice-state', {detail: {
      listening: Boolean(session), microphone: Boolean(microphone), joinDisabled: joinDisabled(),
      micDisabled: micDisabled(), micState, showAudio, message,
    }}))
  }

  function renderMembers() {
    const states = [...members].map(([id, member]) => ({
      id,
      mode: member.host_muted ? 'muted' : !member.voice_session ? 'off' : member.mic_on ? 'speaking' : 'listening',
      disabled: closed || muteRequests.has(id),
    }))
    room.dispatchEvent(new CustomEvent('lumiere:voice-members', {detail: states}))
  }

  const post = <T = unknown>(action: VoiceAction, fields: Record<string, string> = {}) => postVoiceAction<T>(actionUrl, action, fields)

  function clearMicrophone() {
    micChange += 1
    micBusy = false
    const wasOn = Boolean(microphone)
    activity.remove(selfId)
    microphone?.stop()
    pendingMicrophone?.stop()
    microphone = null
    pendingMicrophone = null
    peers.replaceMicrophone(null)
    return wasOn
  }

  function stopSession() {
    const oldSession = session
    session = ''
    revision += 1
    latestSignal = '0'
    window.clearTimeout(leaseTimer)
    clearMicrophone()
    peers.reset()
    activity.suspend()
    return oldSession
  }

  function disconnect() {
    closed = true
    notice = ''
    stopSession()
    activity.dispose()
    window.clearTimeout(pollTimer)
    renderMembers()
    render()
  }

  function schedulePoll(delay = 0) {
    if (closed || suspended) return
    if (polling) { refreshRequested = true; return; }
    window.clearTimeout(pollTimer)
    pollTimer = window.setTimeout(poll, delay)
  }

  function checkLease() {
    if (!session || Date.now() - lastSnapshot < leaseLimit || recovering) return
    recovering = true
    notice = ''
    if (clearMicrophone()) post('mic', {session, enabled: 'false'}).catch(() => {})
    peers.closeAll()
    activity.suspend()
    render()
  }

  function renewLease() {
    lastSnapshot = Date.now()
    window.clearTimeout(leaseTimer)
    if (session) leaseTimer = window.setTimeout(checkLease, leaseLimit)
  }

  async function poll() {
    if (closed || suspended) return
    polling = true
    const observed = revision
    checkLease()
    try {
      const url = new URL(voiceUrl, location.href)
      if (session) {
        url.searchParams.set('session', session)
        url.searchParams.set('after', latestSignal)
      }
      const data = await voiceRequest<VoiceSnapshot>(url)
      if (closed || suspended || observed !== revision) return
      renewLease()
      const wasRecovering = recovering
      recovering = false
      if (wasRecovering && session) activity.resume()
      if (session && data.self.voice_session !== session) {
        stopSession()
        notice = 'Phiên thoại đã kết thúc. Bấm avatar của bạn để kết nối lại.'
      }
      selfMuted = data.self.host_muted
      if (selfMuted) {
        clearMicrophone()
        if (session) notice = ''
      }
      iceServers = data.ice_servers
      members.clear()
      for (const member of [data.self, ...data.peers]) members.set(String(member.user_id), member)
      peers.reconcile()
      if (session) {
        for (const signal of data.signals) {
          latestSignal = String(signal.id)
          peers.receiveSignal(signal).catch(() => {})
        }
      }
      renderMembers()
      render()
    } catch (error) {
      if (error instanceof VoiceRequestError && [403, 404, 409].includes(error.status)) disconnect()
      else checkLease()
    } finally {
      polling = false
      const delay = refreshRequested ? 0 : session ? 1000 : 2500
      refreshRequested = false
      schedulePoll(delay)
    }
  }

  function ensureSession(): Promise<boolean> {
    if (closed || suspended || !canListen) return Promise.resolve(false)
    if (session) return Promise.resolve(true)
    if (joining) return joining
    joinBusy = true
    notice = ''
    render()
    joining = (async () => {
      try {
        const result = await post<{ session: string }>('join')
        if (closed || suspended) {
          await post('leave', {session: result.session}).catch(() => {})
          return false
        }
        session = result.session
        latestSignal = '0'
        renewLease()
        recovering = false
        revision += 1
        return true
      } catch {
        notice = 'Chưa kết nối được âm thanh. Bấm avatar của bạn để thử lại.'
        return false
      } finally {
        joining = null
        joinBusy = false
        render()
        schedulePoll()
      }
    })()
    return joining
  }

  // Legacy controls remain backstage; the visible control is the viewer's seat.
  joinButton.addEventListener('click', async () => {
    if (joinDisabled()) return
    activity.resume()
    if (session) {
      const oldSession = stopSession()
      await post('leave', {session: oldSession}).catch(() => {})
      render()
      schedulePoll()
    } else await ensureSession()
  })

  async function toggleMicrophone() {
    if (micDisabled()) return
    activity.resume()
    notice = ''
    if (microphone) {
      clearMicrophone()
      micBusy = true
      render()
      try { await post('mic', {session, enabled: 'false'}) }
      catch { notice = 'Mic đã tắt trên thiết bị.' }
      micBusy = false
    } else {
      const change = ++micChange
      micBusy = true
      render()
      let track: MediaStreamTrack | undefined
      let enabledSession = ''
      try {
        // Capture is requested in the actual avatar-click call stack. Automatic
        // listening and reconnection never request microphone permission.
        const stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true}})
        const tracks = stream.getAudioTracks()
        track = tracks[0]
        for (const extra of tracks.slice(1)) extra.stop()
        if (change !== micChange || closed || suspended) return void track?.stop()
        if (!track || track.readyState !== 'live') throw new Error('no microphone track')
        track.enabled = false
        pendingMicrophone = track
        if (!await ensureSession() || change !== micChange || selfMuted || recovering || closed || suspended) {
          track.stop()
          return
        }
        enabledSession = session
        await post('mic', {session: enabledSession, enabled: 'true'})
        if (enabledSession !== session || change !== micChange || selfMuted || recovering || closed || suspended || track.readyState !== 'live') {
          track.stop()
          if (enabledSession === session && !selfMuted) post('mic', {session, enabled: 'false'}).catch(() => {})
          return
        }
        microphone = track
        microphone.enabled = true
        activity.attach(selfId, microphone, true)
        peers.replaceMicrophone(microphone)
        microphone.addEventListener('ended', () => {
          if (microphone !== track) return
          clearMicrophone()
          notice = 'Mic đã ngắt kết nối.'
          post('mic', {session, enabled: 'false'}).catch(() => {})
          render()
          schedulePoll()
        }, {once: true})
      } catch (error) {
        track?.stop()
        if (enabledSession && enabledSession === session) post('mic', {session, enabled: 'false'}).catch(() => {})
        if (change !== micChange || closed || suspended) return
        const reason = error instanceof Error ? error.name : ''
        notice = reason === 'NotAllowedError' ? 'Hãy cấp quyền dùng mic trong trình duyệt.'
          : reason === 'NotFoundError' ? 'Chưa tìm thấy mic trên thiết bị.'
          : 'Chưa bật được mic. Hãy kiểm tra thiết bị và thử lại.'
      } finally {
        if (pendingMicrophone === track) pendingMicrophone = null
        if (change === micChange) micBusy = false
      }
    }
    revision += 1
    render()
    schedulePoll()
  }

  micButton.addEventListener('click', toggleMicrophone)
  room.addEventListener('lumiere:voice-toggle-mic', toggleMicrophone)

  room.addEventListener('click', async event => {
    const button = event.target instanceof Element ? event.target.closest<HTMLButtonElement>('[data-voice-mute]') : null
    if (!isHost || !button || button.disabled) return
    const id = button.dataset.voiceMute
    if (!id) return
    const member = members.get(id)
    if (!member) return
    const muted = !member.host_muted
    muteRequests.add(id)
    renderMembers()
    try {
      await post('mute', {user: id, muted: String(muted)})
      revision += 1
      const current = members.get(id)
      if (current) {
        current.host_muted = muted
        current.mic_on = false
      }
      notice = ''
      peers.reconcile()
    } catch { notice = 'Chưa cập nhật được mic của thành viên.'; }
    finally {
      muteRequests.delete(id)
      renderMembers()
      render()
      schedulePoll()
    }
  })

  const playAudio = () => { activity.resume(); peers.playAudio() }
  playButton?.addEventListener('click', playAudio)
  room.addEventListener('lumiere:voice-play-audio', playAudio)
  room.addEventListener('lumiere:room-members', renderMembers)
  document.addEventListener('lumiere:stop', disconnect)
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      checkLease()
      schedulePoll()
    }
  })
  window.addEventListener('pagehide', () => {
    suspended = true
    const oldSession = stopSession()
    window.clearTimeout(pollTimer)
    if (oldSession) navigator.sendBeacon?.(actionUrl, new URLSearchParams({action: 'leave', session: oldSession, csrfmiddlewaretoken: csrfToken()}))
  })
  window.addEventListener('pageshow', () => {
    if (!suspended) return
    suspended = false
    render()
    void ensureSession()
    schedulePoll()
  })
  render()
  void ensureSession()
  schedulePoll()
}
