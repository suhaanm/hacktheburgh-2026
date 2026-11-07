// The stuck probability, read passively. The engine's GET /coach/next carries `p_stuck` (the hazard model's chance of no progress in the next
// minute, or the plain fallback) and `p_source` ("hazard" | "heuristic"). The desktop's own parser (engine/coach-next.ts) drops both and the
// coach poller reads /coach/state, so this module asks for the same decision with `dry=1`, which changes nothing in the engine (no gate
// advance, no cooldown, no recorded decision; docs/API_CONTRACT.md), about every three seconds, only while triggered glances are consented.
//
// If the lead prefers ONE poll instead, the change is three lines (not made here, files belong to other tracks):
//   engine/coach-next.ts   CoachDecision gets `pStuck: number | null`, parseCoachNext sets it from body.p_stuck (finite, 0..1, else null)
//   coach-brain.ts         lastDecision gains `pStuck`, and CoachBrainDeps gets `onDecision?(d)` called after each coachNext()
//   awareness wiring       pass that callback to StuckDetector.observe(d.pStuck, now) instead of using this reader
import { fin, isObj, realTimers, type Timers } from './types'

export interface StuckReading {
  p: number
  source: 'hazard' | 'heuristic'
}

// Reasons under which the engine has no episode to score; p_stuck is then absent or meaningless, so it is "no reading".
const NO_EPISODE = new Set(['no_events', 'no_pack', 'no_active_task', 'study_mode', 'study_post_test', 'study_off'])

export function parseStuckReading(raw: unknown): StuckReading | null {
  if (!isObj(raw)) return null
  const body = isObj(raw.data) ? raw.data : raw
  if (!fin(body.p_stuck) || body.p_stuck < 0 || body.p_stuck > 1) return null
  const reasons = Array.isArray(body.reason_codes) ? body.reason_codes : []
  if (reasons.some((r) => typeof r === 'string' && NO_EPISODE.has(r))) return null
  return { p: body.p_stuck, source: body.p_source === 'hazard' ? 'hazard' : 'heuristic' }
}

export interface StuckReaderDeps {
  engineUrl: string
  person: () => string
  // GET returning parsed JSON, or null when unreachable or not 2xx. Loopback only (the caller builds it with isLoopbackUrl).
  getJson: (url: string) => Promise<unknown | null>
  onReading: (reading: StuckReading | null, nowMs: number) => void
  intervalMs?: number
  now?: () => number
  timers?: Timers
}

export interface StuckReader {
  start(): void
  stop(): void
  running(): boolean
  tick(): Promise<void>
}

export function createStuckReader(deps: StuckReaderDeps): StuckReader {
  const timers = deps.timers ?? realTimers
  const now = deps.now ?? Date.now
  let handle: unknown = null
  let busy = false

  const tick = async (): Promise<void> => {
    if (busy) return
    busy = true
    try {
      const url = `${deps.engineUrl}/coach/next?person=${encodeURIComponent(deps.person())}&dry=1`
      const json = await deps.getJson(url)
      deps.onReading(json === null ? null : parseStuckReading(json), now())
    } catch {
      deps.onReading(null, now())
    } finally {
      busy = false
    }
  }

  return {
    start() {
      if (handle !== null) return
      handle = timers.setInterval(() => void tick(), deps.intervalMs ?? 3000)
    },
    stop() {
      if (handle !== null) timers.clearInterval(handle)
      handle = null
    },
    running: () => handle !== null,
    tick,
  }
}
