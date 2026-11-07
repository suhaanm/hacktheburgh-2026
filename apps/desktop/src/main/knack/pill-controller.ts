// Holds the pill's state between ticks and tells subscribers when it changes. Samples come from the agent-service poll (understudy.ts); the clock and
// timers are injected so the done and error timeouts are testable.
import { acknowledge, IDLE_PILL, pillView, PILL_TIMING, stepPill, type PillKind, type PillSignals, type PillState, type PillTiming, type PillView } from './pill-state'

export interface PillControllerDeps {
  now?: () => number
  timing?: PillTiming
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
}

export type PillListener = (state: PillState, prev: PillState) => void

export interface PillController {
  /** A new sample of the world. Returns the state after it. */
  ingest(signals: PillSignals): PillState
  /** The worker opened Knack: a finished or failed run has been seen. */
  acknowledge(): PillState
  state(): PillState
  view(): PillView
  subscribe(cb: PillListener): () => void
  dispose(): void
}

const QUIET: PillSignals = { reachable: true, supervisor: 'idle', runs: [], killed: false, pending: null }

export function createPillController(deps: PillControllerDeps = {}): PillController {
  const now = deps.now ?? Date.now
  const timing = deps.timing ?? PILL_TIMING
  const setT = deps.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const listeners = new Set<PillListener>()
  let state: PillState = IDLE_PILL
  let last: PillSignals = QUIET
  let timer: unknown = null
  let disposed = false

  const schedule = (): void => {
    if (timer !== null) clearT(timer)
    timer = null
    const wait = state.kind === 'done' ? timing.doneMs : state.kind === 'error' ? timing.errorMs : 0
    if (wait > 0 && !disposed) {
      const left = Math.max(0, state.since + wait - now())
      timer = setT(() => {
        timer = null
        apply(stepPill(state, { ...last, supervisor: last.supervisor === 'running' ? 'idle' : last.supervisor, runs: [] }, now(), timing))
      }, left + 5)
    }
  }
  const apply = (next: PillState): PillState => {
    const prev = state
    state = next
    const changed = prev.kind !== next.kind || prev.text !== next.text
    if (changed) {
      schedule()
      for (const l of listeners) l(next, prev)
    }
    return next
  }

  return {
    ingest(signals) {
      last = signals
      return apply(stepPill(state, signals, now(), timing))
    },
    acknowledge() {
      return apply(acknowledge(state, now()))
    },
    state: () => state,
    view: () => pillView(state),
    subscribe(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    dispose() {
      disposed = true
      if (timer !== null) clearT(timer)
      timer = null
      listeners.clear()
    },
  }
}

export type { PillKind }
