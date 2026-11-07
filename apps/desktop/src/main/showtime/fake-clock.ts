// Deterministic clock for tests and for the headless full-tour run.
import type { Clock } from './machine'

export class FakeClock implements Clock {
  private t = 0
  private seq = 0
  private timers: { id: number; at: number; fn: () => void }[] = []

  now(): number {
    return this.t
  }
  setTimeout(fn: () => void, ms: number): unknown {
    const id = ++this.seq
    this.timers.push({ id, at: this.t + Math.max(0, ms), fn })
    return id
  }
  clearTimeout(handle: unknown): void {
    this.timers = this.timers.filter((x) => x.id !== handle)
  }
  // Runs every timer due within `ms`, in order, letting each one schedule more. Microtasks flush between timers.
  async advance(ms: number): Promise<void> {
    const end = this.t + ms
    for (;;) {
      this.timers.sort((a, b) => a.at - b.at || a.id - b.id)
      const next = this.timers[0]
      if (!next || next.at > end) break
      this.timers.shift()
      this.t = Math.max(this.t, next.at)
      next.fn()
      for (let i = 0; i < 5; i++) await Promise.resolve()
    }
    this.t = end
    for (let i = 0; i < 5; i++) await Promise.resolve()
  }
  get pending(): number {
    return this.timers.length
  }
}
