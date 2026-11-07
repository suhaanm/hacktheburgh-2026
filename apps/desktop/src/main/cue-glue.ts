// The small, testable pieces between the shell and Cue (src/main/cue): the signals Cue reads before it speaks, and the page-content boxes it
// docks its card away from. No Electron import: everything is an injected probe or a clock. Nothing here captures the screen, requests a
// permission, or reads a window title: the probes are the awareness layer's (frontmost bundle id by Launch Services, secure input by
// ioreg), and the input rhythm is the seconds since the last keyboard or pointer input.
import { appKindFor, decideApp } from './awareness/denylist'
import type { ConsoleProbe, FrontmostSource } from './awareness/probes'
import type { Rect } from './dom-ground/protocol'

type Timers = { setInterval(fn: () => void, ms: number): unknown; clearInterval(h: unknown): void }
const realTimers: Timers = { setInterval: (fn, ms) => setInterval(fn, ms), clearInterval: (h) => clearInterval(h as ReturnType<typeof setInterval>) }

export interface CueSignalSources {
  frontmost: FrontmostSource
  console: ConsoleProbe
  // The awareness layer's denylist options (strict mode and the worker's own list), read at each poll.
  deny: () => { strict: boolean; workerList: readonly string[] }
  // Seconds since the last keyboard or pointer input (null when unreadable).
  idleSeconds: () => number | null
  // The worker is "away" after this many idle seconds (settings.awaySeconds).
  awaySeconds: () => number
  intervalMs?: number
  timers?: Timers
}

export interface CueSignalReader {
  /** The worker is typing or using the pointer right now (input in the last 1.5 s). */
  typingNow(): boolean
  /**
   * SECONDS SINCE THE WORKER'S LAST INPUT, to a tenth: what GET /cue/next calls `quiet_s` (the engine holds with reason `flow` while it is
   * under 2). It is NOT "stay quiet for N seconds": that is POST /cue/quiet or the cueQuietUntil setting. null when unreadable.
   */
  quietS(): number | null
  /** A reason to stay away: a denylisted frontmost app, or macOS secure input (a password field has focus). null when none. Sent as denied=1. */
  suppressed(): string | null
  /** The worker is not at the screen: the screen is locked, or no input for awaySeconds. Sent as away=1. */
  away(): boolean
  start(): void
  stop(): void
  /** One probe round now (tests; also called by start). */
  refresh(): Promise<void>
}

export const TYPING_WINDOW_S = 1.5

export function createCueSignals(src: CueSignalSources): CueSignalReader {
  const timers = src.timers ?? realTimers
  let handle: unknown = null
  let reason: string | null = null
  let locked = false
  let busy = false

  const refresh = async (): Promise<void> => {
    if (busy) return
    busy = true
    try {
      const [bundleId, cons] = await Promise.all([src.frontmost.read(), src.console.read()])
      const deny = src.deny()
      const app = decideApp(bundleId, appKindFor(bundleId), { strict: deny.strict, workerList: deny.workerList })
      // Strict mode (the default) reads an app it cannot identify, or a secure-input state it cannot read, as "stay away".
      if (cons.secureInput === 'on') reason = 'secure_input'
      else if (app.verdict === 'deny') reason = 'app_denied'
      else if (deny.strict && cons.secureInput === 'unknown') reason = 'secure_input_unknown'
      else if (deny.strict && app.verdict === 'unknown') reason = 'app_unknown'
      else reason = null
      locked = cons.locked === true
    } catch {
      reason = 'probe_failed' // a probe that throws is a reason to stay away, never a reason to speak
    } finally {
      busy = false
    }
  }
  const idle = (): number | null => {
    const v = src.idleSeconds()
    return v !== null && Number.isFinite(v) && v >= 0 ? v : null
  }
  return {
    typingNow: () => {
      const v = idle()
      return v !== null && v < TYPING_WINDOW_S
    },
    quietS: () => {
      const v = idle()
      return v === null ? null : Math.round(v * 10) / 10
    },
    suppressed: () => reason,
    away: () => {
      const v = idle()
      return locked || (v !== null && v >= Math.max(3, src.awaySeconds()))
    },
    start() {
      if (handle !== null) return
      void refresh()
      handle = timers.setInterval(() => void refresh(), src.intervalMs ?? 2000)
    },
    stop() {
      if (handle !== null) timers.clearInterval(handle)
      handle = null
      reason = null
      locked = false
    },
    refresh,
  }
}

/** The latest page-content boxes (screen points) from a DOM tracker answer, kept for a few seconds; null once they are stale. */
export interface ContentKeeper {
  set(rects: readonly Rect[]): void
  get(): Rect[] | null
  clear(): void
}

export function createContentKeeper(o: { ttlMs?: number; now?: () => number } = {}): ContentKeeper {
  const ttl = o.ttlMs ?? 4000
  const now = o.now ?? Date.now
  let rects: Rect[] | null = null
  let at = 0
  return {
    set(r) {
      // An answer without content ([]) says "unknown", not "nothing there": keep the previous boxes until they go stale.
      if (r.length === 0) return
      rects = r.map((b) => ({ x: b.x, y: b.y, w: b.w, h: b.h }))
      at = now()
    },
    get: () => (rects !== null && now() - at <= ttl ? rects : null),
    clear() {
      rects = null
    },
  }
}
