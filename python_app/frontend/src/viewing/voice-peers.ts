import type { createVoiceActivityMonitor } from './voice-activity'
import type { Peer, Signal, SignalType, VoiceMember } from './voice-types'

interface VoicePeerContext {
  selfId: string
  audioArea: HTMLElement
  members: Map<string, VoiceMember>
  activity: ReturnType<typeof createVoiceActivityMonitor>
  session: () => string
  recovering: () => boolean
  microphone: () => MediaStreamTrack | null
  iceServers: () => RTCIceServer[]
  signal: (fields: Record<string, string>) => Promise<unknown>
  changed: () => void
}

/** Own WebRTC negotiation and remote audio; the session coordinator owns access and mic consent. */
export function createVoicePeers(state: VoicePeerContext) {
  const peers = new Map<string, Peer>()
  const retries = new Map<string, { attempt: number; after: number }>()

  function closePeer(peer: Peer) {
    state.activity.remove(peer.id)
    if (peers.get(peer.id) === peer) peers.delete(peer.id)
    window.clearTimeout(peer.deadline)
    peer.connection.close()
    if (peer.audio) {
      peer.audio.pause()
      peer.audio.srcObject = null
      peer.audio.remove()
    }
  }

  function playPeerAudio(peer: Peer) {
    if (!peer.audio || peer.audio.muted || !peerCurrent(peer)) return
    peer.audio.play().then(() => {
      peer.blocked = false
      state.changed()
    }).catch(() => {
      peer.blocked = true
      state.changed()
    })
  }

  function updatePeerAudio(peer: Peer) {
    if (!peer.audio) return
    const member = state.members.get(peer.id)
    const audible = Boolean(state.session() && !state.recovering() && member?.voice_session === peer.session && member.mic_on && !member.host_muted)
    state.activity.setEnabled(peer.id, audible)
    const wasMuted = peer.audio.muted
    peer.audio.muted = !audible
    if (audible && wasMuted) playPeerAudio(peer)
  }

  function offeredFirst(id: string) {
    return BigInt(state.selfId) < BigInt(id)
  }

  function peerCurrent(peer: Peer) {
    return Boolean(state.session() && !state.recovering() && peers.get(peer.id) === peer && state.members.get(peer.id)?.voice_session === peer.session)
  }

  function failPeer(peer: Peer) {
    if (!peerCurrent(peer)) return
    const previous = retries.get(peer.id) || {attempt: 0}
    const attempt = Math.min(previous.attempt + 1, 5)
    retries.set(peer.id, {attempt, after: Date.now() + Math.min(1000 * 2 ** attempt, 15000)})
    closePeer(peer)
    state.changed()
  }

  function createPeer(member: VoiceMember & { voice_session: string }, negotiation: string) {
    const connection = new RTCPeerConnection({iceServers: state.iceServers()})
    const peer: Peer = {id: String(member.user_id), session: member.voice_session, negotiation, connection}
    peers.set(peer.id, peer)
    peer.deadline = window.setTimeout(() => failPeer(peer), 22000)
    connection.addEventListener('connectionstatechange', () => {
      if (connection.connectionState === 'failed') failPeer(peer)
      if (connection.connectionState === 'connected') {
        window.clearTimeout(peer.deadline)
        retries.delete(peer.id)
      }
      if (connection.connectionState === 'disconnected') {
        window.clearTimeout(peer.deadline)
        peer.deadline = window.setTimeout(() => failPeer(peer), 7000)
      }
    })
    connection.addEventListener('track', ({track}) => {
      if (track.kind !== 'audio' || !peerCurrent(peer)) return
      if (!peer.audio) {
        peer.audio = document.createElement('audio')
        peer.audio.muted = true
        peer.audio.setAttribute('playsinline', '')
        state.audioArea.append(peer.audio)
      }
      peer.audio.srcObject = new MediaStream([track])
      state.activity.attach(peer.id, track, false)
      updatePeerAudio(peer)
    })
    return peer
  }

  async function attachSender(peer: Peer, transceiver: RTCRtpTransceiver) {
    transceiver.direction = 'sendrecv'
    peer.sender = transceiver.sender
    await peer.sender.replaceTrack(state.microphone())
  }

  function waitForIce(connection: RTCPeerConnection): Promise<void> {
    if (connection.iceGatheringState === 'complete') return Promise.resolve()
    return new Promise<void>(resolve => {
      const finish = () => {
        window.clearTimeout(timer)
        connection.removeEventListener('icegatheringstatechange', check)
        resolve()
      }
      const check = () => { if (connection.iceGatheringState === 'complete') finish(); }
      const timer = window.setTimeout(finish, 4500)
      connection.addEventListener('icegatheringstatechange', check)
    })
  }

  async function sendDescription(peer: Peer, type: SignalType) {
    await waitForIce(peer.connection)
    if (!peerCurrent(peer) || !peer.connection.localDescription) return
    await state.signal({session: state.session(), user: peer.id, target_session: peer.session, type,
      payload: JSON.stringify({sdp: peer.connection.localDescription.sdp, negotiation: peer.negotiation})})
  }

  async function makeOffer(member: VoiceMember & { voice_session: string }) {
    const peer = createPeer(member, crypto.randomUUID())
    try {
      await attachSender(peer, peer.connection.addTransceiver('audio'))
      await peer.connection.setLocalDescription(await peer.connection.createOffer())
      await sendDescription(peer, 'offer')
    } catch { failPeer(peer); }
  }

  async function receiveSignal(signal: Signal) {
    const id = String(signal.from_user_id)
    const member = state.members.get(id)
    const {type, payload} = signal
    if (id === state.selfId || !member?.voice_session || member.voice_session !== signal.from_session) return
    if (typeof payload?.sdp !== 'string' || typeof payload.negotiation !== 'string') return
    const media = [...payload.sdp.matchAll(/^m=(\S+)/gm)]
    if (media.length !== 1 || media[0][1] !== 'audio') return
    let peer = peers.get(id)
    if (type === 'offer' && !offeredFirst(id)) {
      if (peer?.negotiation === payload.negotiation) return
      if (peer) closePeer(peer)
      peer = createPeer({ ...member, voice_session: member.voice_session }, payload.negotiation)
      try {
        await peer.connection.setRemoteDescription({type, sdp: payload.sdp})
        if (!peerCurrent(peer)) return
        await attachSender(peer, peer.connection.getTransceivers()[0])
        await peer.connection.setLocalDescription(await peer.connection.createAnswer())
        await sendDescription(peer, 'answer')
      } catch { failPeer(peer); }
    } else if (type === 'answer' && offeredFirst(id) && peer?.negotiation === payload.negotiation && peerCurrent(peer)) {
      try { await peer.connection.setRemoteDescription({type, sdp: payload.sdp}); }
      catch { failPeer(peer); }
    }
  }

  function reconcilePeers() {
    for (const peer of peers.values()) {
      if (!peerCurrent(peer)) closePeer(peer)
      else updatePeerAudio(peer)
    }
    for (const id of retries.keys()) {
      if (!state.members.get(id)?.voice_session) retries.delete(id)
    }
    if (!state.session() || state.recovering()) return
    for (const [id, member] of state.members) {
      if (id !== state.selfId && member.voice_session && !peers.has(id) && offeredFirst(id) && (retries.get(id)?.after || 0) <= Date.now()) {
        makeOffer({ ...member, voice_session: member.voice_session }).catch(() => {})
      }
    }
  }

  function closeAll() {
    for (const peer of peers.values()) closePeer(peer)
  }

  function reset() {
    closeAll()
    retries.clear()
  }

  function replaceMicrophone(track: MediaStreamTrack | null) {
    for (const peer of peers.values()) {
      peer.sender?.replaceTrack(track).catch(() => { if (track) failPeer(peer) })
    }
  }

  return {
    receiveSignal, reconcile: reconcilePeers, closeAll, reset, replaceMicrophone,
    retrying: () => retries.size > 0,
    blockedAudio: () => [...peers.values()].some(peer => peer.blocked && !peer.audio?.muted),
    playAudio: () => { for (const peer of peers.values()) playPeerAudio(peer) },
  }
}
