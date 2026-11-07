// Follows GET /coach/state: the task in progress and the chip's fade. The chip hint goes to the chip driver (the engine's own
// `chip` wins while it answers) and the task goes to whoever needs to know whether the worker is mid-task (the coach brain
// consumer and the proposal scheduler). The ring is NOT driven from here: that is GET /coach/next (src/main/coach-brain.ts).
import type { ChipDriver } from './coach-chip'
import type { CoachStateInfo } from './engine/coach-state'

export interface CoachPollerDeps {
  engine: { coachState(): Promise<CoachStateInfo | null> }
  chip: Pick<ChipDriver, 'setEngineHint' | 'refresh'>
  intervalMs?: number
  // Run one tick straight away (default). Tests turn it off to control every tick.
  immediate?: boolean
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  // Told after every successful read (null task = no task in progress).
  onTask?: (task: CoachStateInfo['task']) => void
  log?: (scope: string, ...args: unknown[]) => void
}

export interface CoachPoller {
  tick(): Promise<void>
  lastState(): CoachStateInfo | null
  dispose(): void
}

export function createCoachPoller(deps: CoachPollerDeps): CoachPoller {
  const setT = deps.setTimer ?? ((fn, ms) => setInterval(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearInterval(h as ReturnType<typeof setInterval>))
  let last: CoachStateInfo | null = null
  let busy = false

  const tick = async (): Promise<void> => {
    if (busy) return
    busy = true
    try {
      const state = await deps.engine.coachState()
      last = state
      if (!state) {
        deps.chip.setEngineHint(null)
        deps.chip.refresh()
        return
      }
      deps.chip.setEngineHint({ fade: state.chip, level: state.level })
      deps.chip.refresh()
      deps.onTask?.(state.task)
    } catch (err) {
      deps.log?.('coach-poller', `tick failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      busy = false
    }
  }

  const handle = setT(() => void tick(), deps.intervalMs ?? 2000)
  if (deps.immediate !== false) void tick()
  return {
    tick,
    lastState: () => last,
    dispose: () => clearT(handle),
  }
}
