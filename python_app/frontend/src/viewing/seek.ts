export function formatTime(seconds: number) {
  const safe = Math.max(0, Math.floor(seconds + 0.001))
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`
}

export function seekPosition(target: number, duration: number, seekable: TimeRanges) {
  if (!Number.isFinite(target) || !Number.isFinite(duration) || duration <= 0) return
  const requested = Math.max(0, Math.min(duration, target))
  let nearest = requested
  let distance = Infinity
  for (let index = 0; index < seekable.length; index += 1) {
    const start = Math.max(0, seekable.start(index))
    const end = Math.min(duration, seekable.end(index))
    if (!Number.isFinite(start) || !Number.isFinite(end) || start > end) continue
    if (requested >= start && requested <= end) return requested
    const boundary = requested < start ? start : end
    const delta = Math.abs(boundary - requested)
    if (delta < distance) {
      distance = delta
      nearest = boundary
    }
  }
  return nearest
}
