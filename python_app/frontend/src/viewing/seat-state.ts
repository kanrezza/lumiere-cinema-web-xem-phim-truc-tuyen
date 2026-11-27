import type { RoomCapacity, RoomMember } from './room-types'
import type { VoiceMemberMode } from './voice-types'

export type SeatVoiceMode = VoiceMemberMode

export function roomSeatCapacity(value: unknown, fallback: RoomCapacity = 3): RoomCapacity {
  const capacity = typeof value === 'string' ? Number(value) : value
  return capacity === 3 || capacity === 10 ? capacity : fallback
}

/** Retain occupied seats across polling and resizing, with the host at the front. */
export function allocateSeats(previous: readonly (number | null)[], members: readonly RoomMember[], host: number, count: RoomCapacity) {
  const incoming = [...new Set(members.map(member => member.user_id).filter(id => Number.isSafeInteger(id) && id > 0))]
  const presentIds = new Set(incoming)
  const priority = [
    ...(presentIds.has(host) ? [host] : []),
    ...previous.filter((id): id is number => id !== null && presentIds.has(id)),
    ...incoming,
  ]
  const ids = [...new Set(priority)].slice(0, count)
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
