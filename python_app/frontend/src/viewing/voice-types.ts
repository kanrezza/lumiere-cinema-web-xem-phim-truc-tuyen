export type SignalType = 'offer' | 'answer'
export type VoiceAction = 'join' | 'leave' | 'signal' | 'mic' | 'mute'

export interface VoiceMember {
  user_id: number
  voice_session: string | null
  host_muted: boolean
  mic_on: boolean
}

export interface Signal {
  id: number
  from_user_id: number
  from_session: string
  type: SignalType
  payload: { sdp?: unknown; negotiation?: unknown } | null
}

export interface VoiceSnapshot {
  self: VoiceMember
  peers: VoiceMember[]
  signals: Signal[]
  ice_servers: RTCIceServer[]
}

export interface Peer {
  id: string
  session: string
  negotiation: string
  connection: RTCPeerConnection
  deadline?: number
  audio?: HTMLAudioElement
  sender?: RTCRtpSender
  blocked?: boolean
}

export interface VoiceState {
  listening: boolean
  microphone: boolean
  joinDisabled: boolean
  micDisabled: boolean
  micState: 'muted' | 'live' | 'off'
  showAudio: boolean
  message: string
}

export type VoiceMemberMode = 'muted' | 'off' | 'speaking' | 'listening'

export interface VoiceMemberState {
  id: string
  mode: VoiceMemberMode
  disabled: boolean
}
