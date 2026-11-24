export interface VoiceActivity {
  id: string
  speaking: boolean
}

/** A short attack and longer release avoid flashing on clicks or between words. */
export class SpeechGate {
  speaking = false
  private aboveSince: number | null = null
  private quietSince: number | null = null

  sample(rms: number, now: number) {
    const previous = this.speaking
    if (!Number.isFinite(rms) || !Number.isFinite(now)) return this.reset()
    if (this.speaking) {
      if (rms >= .01) this.quietSince = null
      else {
        this.quietSince ??= now
        if (now - this.quietSince >= 350) this.reset()
      }
    } else if (rms >= .018) {
      this.aboveSince ??= now
      if (now - this.aboveSince >= 120) {
        this.speaking = true
        this.quietSince = null
      }
    } else this.aboveSince = null
    return previous !== this.speaking
  }

  reset() {
    const changed = this.speaking
    this.speaking = false
    this.aboveSince = this.quietSince = null
    return changed
  }
}

interface Source {
  track: MediaStreamTrack
  enabled: boolean
  gate: SpeechGate
  source?: MediaStreamAudioSourceNode
  analyser?: AnalyserNode
  samples?: Float32Array<ArrayBuffer>
  removeListeners: () => void
}

export function createVoiceActivityMonitor(changed: (snapshot: VoiceActivity[]) => void) {
  const sources = new Map<string, Source>()
  let context: AudioContext | undefined
  let timer: number | undefined
  let disposed = false

  function emit() {
    changed([...sources].map(([id, entry]) => ({id, speaking: entry.enabled && entry.gate.speaking})))
  }

  function detachGraph(entry: Source) {
    entry.source?.disconnect()
    entry.analyser?.disconnect()
    entry.source = undefined
    entry.analyser = undefined
    entry.samples = undefined
  }

  function graph(entry: Source) {
    if (!context || entry.source || !entry.enabled || entry.track.readyState !== 'live') return
    try {
      const source = context.createMediaStreamSource(new MediaStream([entry.track]))
      const analyser = context.createAnalyser()
      analyser.fftSize = 512
      source.connect(analyser)
      // The analyser is never connected to the output, so the local mic cannot echo.
      entry.source = source
      entry.analyser = analyser
      entry.samples = new Float32Array(analyser.fftSize)
    } catch {
      detachGraph(entry)
    }
  }

  function sample() {
    if (disposed) return
    let updated = false
    const now = performance.now()
    for (const entry of sources.values()) {
      if (!entry.enabled || !entry.track.enabled || entry.track.muted || entry.track.readyState !== 'live' || context?.state !== 'running') {
        updated = entry.gate.reset() || updated
        continue
      }
      graph(entry)
      if (!entry.analyser || !entry.samples) continue
      try {
        entry.analyser.getFloatTimeDomainData(entry.samples)
        let squares = 0
        for (const value of entry.samples) squares += value * value
        updated = entry.gate.sample(Math.sqrt(squares / entry.samples.length), now) || updated
      } catch { updated = entry.gate.reset() || updated }
    }
    if (updated) emit()
  }

  function schedule() {
    const needed = Boolean(context && context.state !== 'closed' && [...sources.values()].some(entry => entry.enabled))
    if (needed && timer === undefined) timer = window.setInterval(sample, 80)
    if (!needed && timer !== undefined) {
      window.clearInterval(timer)
      timer = undefined
    }
  }

  function remove(id: string) {
    const entry = sources.get(id)
    if (!entry) return
    entry.removeListeners()
    detachGraph(entry)
    sources.delete(id)
    schedule()
    emit()
  }

  function clear() {
    for (const entry of sources.values()) {
      entry.removeListeners()
      detachGraph(entry)
    }
    sources.clear()
    schedule()
    emit()
  }

  return {
    /** Call in the existing Join/Mic click, never as a new capture request. */
    resume() {
      if (disposed) return
      if (!context) {
        const Constructor = window.AudioContext || (window as Window & {webkitAudioContext?: typeof AudioContext}).webkitAudioContext
        if (!Constructor) return
        try { context = new Constructor() } catch { return }
      }
      if (context.state === 'closed') return
      for (const entry of sources.values()) graph(entry)
      void context.resume().catch(() => {})
      schedule()
    },
    attach(id: string, track: MediaStreamTrack, enabled: boolean) {
      if (disposed) return
      if (sources.get(id)?.track === track) {
        this.setEnabled(id, enabled)
        return
      }
      remove(id)
      const entry: Source = {track, enabled, gate: new SpeechGate(), removeListeners: () => {}}
      const ended = () => {if (sources.get(id) === entry) remove(id)}
      const muted = () => {if (entry.gate.reset()) emit()}
      track.addEventListener('ended', ended)
      track.addEventListener('mute', muted)
      entry.removeListeners = () => {
        track.removeEventListener('ended', ended)
        track.removeEventListener('mute', muted)
      }
      sources.set(id, entry)
      graph(entry)
      schedule()
      emit()
    },
    setEnabled(id: string, enabled: boolean) {
      const entry = sources.get(id)
      if (!entry || entry.enabled === enabled) return
      entry.enabled = enabled
      if (enabled) graph(entry)
      else {
        entry.gate.reset()
        detachGraph(entry)
      }
      schedule()
      emit()
    },
    remove,
    suspend() {
      clear()
      if (context?.state === 'running') void context.suspend().catch(() => {})
    },
    dispose() {
      disposed = true
      clear()
      if (context && context.state !== 'closed') void context.close().catch(() => {})
    },
  }
}
