export interface PremiereMessage {
  id: number
  user_id: number
  username: string
  display_name?: string
  avatar_url?: string
  content: string
  created_at?: string
}

export interface PremiereState {
  id: string
  title: string
  movie_title: string
  episode_title: string
  episode_id: number
  status: 'scheduled' | 'live' | 'ended' | 'cancelled'
  scheduled_at: string
  started_at: string | null
  server_time: string
  position: number
  playback_position?: number
  playback_delay_seconds?: number
  ended_manually?: boolean
  duration: number
  playing: boolean
  can_watch: boolean
  can_chat?: boolean
  requires_vip: boolean
  state_version: number
  messages: PremiereMessage[]
  ticket_url: string
}

export function premierePlaybackPosition(state: PremiereState, elapsedSeconds = 0): number {
  const delay = Number.isFinite(state.playback_delay_seconds) ? Math.max(0, state.playback_delay_seconds!) : 12
  return Math.max(0, premierePosition(state, elapsedSeconds) - delay)
}

/** Advance from the server snapshot, independent of the viewer's wall clock. */
export function premierePosition(state: PremiereState, elapsedSeconds = 0): number {
  const duration = Number.isFinite(state.duration) ? Math.max(0, state.duration) : 0
  const base = Number.isFinite(state.position) ? Math.max(0, state.position) : 0
  const elapsed = state.status === 'live' && state.playing && Number.isFinite(elapsedSeconds) ? Math.max(0, elapsedSeconds) : 0
  return Math.min(duration, base + elapsed)
}

export function premiereCountdown(state: PremiereState, elapsedSeconds = 0): number {
  const scheduled = Date.parse(state.scheduled_at)
  const server = Date.parse(state.server_time)
  if (!Number.isFinite(scheduled) || !Number.isFinite(server)) return 0
  return Math.max(0, Math.ceil((scheduled - server) / 1000 - Math.max(0, elapsedSeconds)))
}

export function countdownLabel(seconds: number): string {
  const value = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0
  const days = Math.floor(value / 86400)
  const hours = String(Math.floor(value % 86400 / 3600)).padStart(2, '0')
  const minutes = String(Math.floor(value % 3600 / 60)).padStart(2, '0')
  const remaining = String(value % 60).padStart(2, '0')
  return (days ? days + ' ngày · ' : '') + hours + ':' + minutes + ':' + remaining
}
