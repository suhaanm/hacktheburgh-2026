// Capture consent (principle PR3: opt-in everywhere). Desk events (idle, lock, unlock, sleep, resume: times only) and coach events
// (coach_shown, coach_followed, coach_dismissed) are sent to the engine ONLY while the worker's memory file says so, in its
// Preferences section (the worker's explicit answer to a prompt still goes to /coach/feedback: it is their own action):
//     - Capture: times only
// which onboarding writes after the worker turns capture on in the dashboard. Dev and demo can force it with
// UNDERSTUDY_DESK_EVENTS=1. The file is read at startup and every few minutes; the moment the line is gone (or the engine
// cannot confirm it) desk signals stop, and events that were queued but not sent are thrown away.
import type { EngineClient, MemoryInfo } from './client'

export const CAPTURE_LINE = 'Capture: times only'
export const CAPTURE_RECHECK_MS = 2 * 60_000

/** The front matter `role:` of the memory file. */
export function roleFromMemory(markdown: string): string | null {
  const m = /^---\s*\n([\s\S]*?)\n---/m.exec(markdown)
  if (!m) return null
  const line = /^role:\s*([a-z][a-z0-9-]{1,40})\s*$/m.exec(m[1])
  // "unknown" is what the engine writes before onboarding: not a role.
  return line && line[1] !== 'unknown' ? line[1] : null
}

/** True when the Preferences section has the line "Capture: times only" (case and spacing tolerant). Other sections do not count. */
export function captureFromMemory(markdown: string): boolean {
  let inPreferences = false
  for (const raw of markdown.split(/\r?\n/)) {
    const heading = /^##\s+(.+?)\s*$/.exec(raw)
    if (heading) {
      inPreferences = heading[1].toLowerCase() === 'preferences'
      continue
    }
    if (!inPreferences) continue
    // "- Capture: times only" with an optional trailing HTML comment, e.g. <!-- accepted 2026-11-07 -->
    const item = /^\s*[-*]\s+(.*?)\s*(?:<!--.*?-->)?\s*$/.exec(raw)
    if (item && item[1].replace(/\s+/g, ' ').trim().toLowerCase() === CAPTURE_LINE.toLowerCase()) return true
  }
  return false
}

export type CaptureMode = 'off' | 'times_only' | 'forced'

export interface CaptureConsentOptions {
  engine: Pick<EngineClient, 'memory' | 'purge'>
  env?: Record<string, string | undefined>
  recheckMs?: number
  // Called with every successful read of the memory file (the same GET also carries the person id and the role).
  onMemory?: (info: MemoryInfo) => void
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  log?: (scope: string, ...args: unknown[]) => void
}

export interface CaptureConsent {
  mode(): CaptureMode
  allowed(): boolean
  // Re-read the memory file now. Resolves with the mode after the check.
  check(): Promise<CaptureMode>
  // Called on every change of mode (and once at the first check).
  subscribe(cb: (mode: CaptureMode) => void): () => void
  dispose(): void
}

/** One line for the menu: what is being captured, in plain words. */
export function captureLabel(mode: CaptureMode): string {
  if (mode === 'times_only') return 'Desk capture: times only (you turned this on)'
  if (mode === 'forced') return 'Desk capture: times only (forced for development)'
  return 'Desk capture is off. Turn it on in setup to share when you are active.'
}

export function createCaptureConsent(opts: CaptureConsentOptions): CaptureConsent {
  const env = opts.env ?? process.env
  const forced = env.UNDERSTUDY_DESK_EVENTS === '1'
  const setT = opts.setTimer ?? ((fn, ms) => setInterval(fn, ms))
  const clearT = opts.clearTimer ?? ((h) => clearInterval(h as ReturnType<typeof setInterval>))
  const log = opts.log ?? (() => undefined)
  const listeners = new Set<(m: CaptureMode) => void>()
  let mode: CaptureMode = forced ? 'forced' : 'off'
  let announced = false
  let disposed = false

  const set = (next: CaptureMode): void => {
    const changed = next !== mode || !announced
    mode = next
    announced = true
    if (next === 'off') {
      // Everything that is capture (desk signals and coach telemetry) stops, and what has not been sent is thrown away.
      const dropped = opts.engine.purge('desk') + opts.engine.purge('coach')
      if (dropped) log('capture', `consent is off: ${dropped} unsent events discarded`)
    }
    if (changed) {
      log('capture', `desk capture is ${next}`)
      for (const l of listeners) l(mode)
    }
  }

  const check = async (): Promise<CaptureMode> => {
    if (disposed) return mode
    if (forced) {
      set('forced')
      return mode
    }
    let info = null
    try {
      info = await opts.engine.memory()
    } catch {
      info = null
    }
    if (info) {
      try {
        opts.onMemory?.(info)
      } catch {
        /* applying the identity must never decide the consent */
      }
    }
    // Fail closed: if the engine cannot confirm the line, capture is off.
    set(info?.captureTimesOnly ? 'times_only' : 'off')
    return mode
  }

  const handle = setT(() => void check(), opts.recheckMs ?? CAPTURE_RECHECK_MS)
  void check()

  return {
    mode: () => mode,
    allowed: () => mode !== 'off',
    check,
    subscribe(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    dispose() {
      disposed = true
      clearT(handle)
    },
  }
}
