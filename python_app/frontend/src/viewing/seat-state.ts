import type { RoomMember } from './room-types'
import type { VoiceMemberMode } from './voice-types'

export type SeatVoiceMode = VoiceMemberMode

/** Retain occupied seats across polling, while keeping the host at the front. */
export function allocateSeats(previous: readonly (number | null)[], members: readonly RoomMember[], host: number, count = 10) {
  const ids = [...new Set(members.map(member => member.user_id).filter(id => Number.isSafeInteger(id) && id > 0))].slice(0, count)
  const present = new Set(ids)
  const assigned = new Set<number>()
  const seats = Array.from({length: count}, (_, index): number | null => {
    const id = previous[index]
    if (id === null || id === undefined || !present.has(id) || assigned.has(id)) return null
    assigned.add(id)
    return id
  })
  if (present.has(host) && seats[0] !== host) {
    const oldSeat = seats.indexOf(host)
    const displaced = seats[0]
    if (oldSeat >= 0) seats[oldSeat] = null
    seats[0] = host
    if (displaced !== null) {
      const free = seats.indexOf(null)
      if (free >= 0) seats[free] = displaced
    }
  }
  for (const id of ids) {
    if (seats.includes(id)) continue
    const free = seats.indexOf(null)
    if (free < 0) break
    seats[free] = id
  }
  return seats
}

export function seatIsSpeaking(mode: SeatVoiceMode | undefined, active: boolean) {
  return mode === 'speaking' && active
}

export function seatDisplayName(member: RoomMember) {
  return member.display_name?.trim() || member.user__username
}

export function seatLabel(index: number) {
  return `${index < 5 ? 'A' : 'B'}${index % 5 + 1}`
}
