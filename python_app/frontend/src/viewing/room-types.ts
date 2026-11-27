export type RoomCapacity = 3 | 10

export interface RoomMediaState {
  capacity?: RoomCapacity
  media_version?: number
  episode_id?: number | null
  can_watch?: boolean
  title?: string
  episode_title?: string
  player_url?: string
}

export interface RoomMember {
  user_id: number
  user__username: string
  display_name?: string
  avatar_url?: string
}

export interface ChatMessage {
  id: number
  user_id: number
  user: string
  display_name?: string
  avatar_url?: string
  content: string
}

export interface RoomSnapshot extends RoomMediaState {
  closed: boolean
  position: number
  playing: boolean
  messages: ChatMessage[]
  members: RoomMember[]
}

export interface PlaylistItem {
  id: number
  episode_id: number
  title: string
  episode_title: string
  poster_url: string
  position: number
  available: boolean
}
export interface Suggestion extends PlaylistItem {
  proposed_by: string
  proposer_id: number
  status: string
}
export interface PlaylistSnapshot extends RoomMediaState {
  playlist_version: number
  items: PlaylistItem[]
  suggestions: Suggestion[]
  is_host: boolean
  can_manage: boolean
  error?: string
}

