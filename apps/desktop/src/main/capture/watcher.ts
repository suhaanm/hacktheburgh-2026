// Screen-change watcher: samples a tiny grayscale grid on a timer and reports when the screen changed
// materially and has then settled (so a verifier looks at the finished state, not a half-open window).
// Polls only while somebody is listening. Time and sampling are injected so it is unit-testable.
import { changeScore } from './change-score'

export interface WatcherOptions {
  sample: () => Promise<Uint8Array | null>
  // Mean abs diff vs the baseline that counts as a real change (a window opening is ~0.03+, a clock tick ~0.0005).
  threshold?: number
  // Frame-to-frame diff below which the change counts as settled.
  settle?: number
  // Emit anyway after this long if the screen never settles (video call tiles, scrolling).
  maxWaitMs?: number
  intervalMs?: number
  now?: () => number
  setInterval?: (fn: () => void, ms: number) => unknown
  clearInterval?: (handle: unknown) => void
}

export class ScreenChangeWatcher {
  private readonly listeners = new Set<(score: number) => void>()
  private readonly threshold: number
  private readonly settle: number
  private readonly maxWaitMs: number
  private readonly intervalMs: number
  private readonly now: () => number
  private readonly setIv: (fn: () => void, ms: number) => unknown
  private readonly clearIv: (handle: unknown) => void
  private handle: unknown = null
  private busy = false
  private baseline: Uint8Array | null = null
  private prev: Uint8Array | null = null
  private changingSince: number | null = null

  constructor(private readonly opts: WatcherOptions) {
    this.threshold = opts.threshold ?? 0.02
    this.settle = opts.settle ?? 0.004
    this.maxWaitMs = opts.maxWaitMs ?? 1800
    this.intervalMs = opts.intervalMs ?? 500
    this.now = opts.now ?? Date.now
    this.setIv = opts.setInterval ?? ((fn, ms) => setInterval(fn, ms))
    this.clearIv = opts.clearInterval ?? ((h) => clearInterval(h as ReturnType<typeof setInterval>))
  }

  subscribe(listener: (score: number) => void): () => void {
    this.listeners.add(listener)
    if (this.handle === null) this.start()
    return () => {
      this.listeners.delete(listener)
      if (this.listeners.size === 0) this.stop()
    }
  }

  get running(): boolean {
    return this.handle !== null
  }

  private start(): void {
    this.baseline = null
    this.prev = null
    this.changingSince = null
    this.handle = this.setIv(() => void this.tick(), this.intervalMs)
    void this.tick()
  }

  private stop(): void {
    if (this.handle !== null) this.clearIv(this.handle)
    this.handle = null
  }

  async tick(): Promise<void> {
    if (this.busy) return
    this.busy = true
    try {
      const grid = await this.opts.sample()
      if (!grid || this.handle === null) return
      if (!this.baseline || !this.prev) {
        this.baseline = grid
        this.prev = grid
        return
      }
      const sinceBaseline = changeScore(this.baseline, grid)
      const frameDelta = changeScore(this.prev, grid)
      this.prev = grid
      if (sinceBaseline < this.threshold) {
        this.changingSince = null
        return
      }
      const t = this.now()
      this.changingSince ??= t
      if (frameDelta < this.settle || t - this.changingSince >= this.maxWaitMs) {
        this.baseline = grid
        this.changingSince = null
        for (const listener of [...this.listeners]) {
          try {
            listener(sinceBaseline)
          } catch {
            // a bad listener must not stop the others
          }
        }
      }
    } catch {
      // sampling can fail transiently (display asleep, permission change); try again next tick
    } finally {
      this.busy = false
    }
  }
}
