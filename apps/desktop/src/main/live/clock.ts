// Timers behind a small interface so the session's limits (grace, idle, hard cap, the 250 ms tick) are tested with a manual clock, not by
// waiting. LiveClock owns the timers of one session and clears every one of them when the session ends.
export interface Timers {
  setInterval(fn: () => void, ms: number): unknown
  clearInterval(h: unknown): void
  setTimeout(fn: () => void, ms: number): unknown
  clearTimeout(h: unknown): void
}

export const realTimers: Timers = {
  setInterval: (fn, ms) => setInterval(fn, ms),
  clearInterval: (h) => clearInterval(h as ReturnType<typeof setInterval>),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (h) => clearTimeout(h as ReturnType<typeof setTimeout>),
}

export class LiveClock {
  private intervals = new Set<unknown>()
  private timeouts = new Set<unknown>()
  private disposed = false

  constructor(private readonly t: Timers = realTimers) {}

  every(ms: number, fn: () => void): void {
    if (this.disposed) return
    this.intervals.add(this.t.setInterval(fn, ms))
  }

  after(ms: number, fn: () => void): void {
    if (this.disposed) return
    const h = this.t.setTimeout(() => {
      this.timeouts.delete(h)
      if (!this.disposed) fn()
    }, ms)
    this.timeouts.add(h)
  }

  dispose(): void {
    this.disposed = true
    for (const h of this.intervals) this.t.clearInterval(h)
    for (const h of this.timeouts) this.t.clearTimeout(h)
    this.intervals.clear()
    this.timeouts.clear()
  }
}
