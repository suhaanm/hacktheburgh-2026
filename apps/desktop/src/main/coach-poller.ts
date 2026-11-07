// Follows GET /coach/state: feeds the engine's chip fade to the chip driver, and rings the target element the engine names.
// It only manages rings it started itself; a ring a local process asked for (POST /coach/ring) is left alone.
//   same task, step went up while the ring is shown   -> the step was done: coach_followed, ring removed
//   task ended or changed                             -> ring removed (the prompt is over)
//   target changed                                    -> the ring moves to the new element
import type { ChipDriver } from './coach-chip'
import type { DomCoach } from './dom-ground/dom-coach'
import type { CoachStateInfo } from './engine/coach-state'

export interface CoachPollerDeps {
  engine: { coachState(): Promise<CoachStateInfo | null> }
  chip: Pick<ChipDriver, 'setEngineHint' | 'refresh'>
  ring: Pick<DomCoach, 'point' | 'clear' | 'followed' | 'current'>
  killed?: () => boolean
  intervalMs?: number
  // Run one tick straight away (default). Tests turn it off to control every tick.
  immediate?: boolean
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  // What the proposal scheduler needs to know about the work in progress.
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
  let mine = false // the current ring is the poller's
  let busy = false

  const endMine = (how: 'ended' | 'user' = 'ended'): void => {
    if (mine) {
      deps.ring.clear(how)
      mine = false
    }
  }

  const tick = async (): Promise<void> => {
    if (busy) return
    busy = true
    try {
      const state = await deps.engine.coachState()
      const prev = last
      last = state
      if (!state) {
        deps.chip.setEngineHint(null)
        deps.chip.refresh()
        return
      }
      deps.chip.setEngineHint({ fade: state.chip, level: state.level })
      const fade = deps.chip.refresh()
      deps.onTask?.(state.task)

      const taskChanged = !!prev?.task && prev.task.id !== state.task?.id
      const stepUp = !!prev?.task && !!state.task && prev.task.id === state.task.id && state.task.step > prev.task.step
      if (mine && stepUp && deps.ring.current()) {
        deps.ring.followed()
        mine = false
      } else if (taskChanged || (prev?.task && !state.task)) endMine('ended')

      if (deps.killed?.() || fade === 'gone' || !state.target) {
        if (!state.target) endMine('ended')
        else if (deps.killed?.() || fade === 'gone') endMine('user')
        return
      }
      const step = state.task && state.task.step >= 1 && state.task.step <= 99 ? state.task.step : undefined
      deps.ring.point(state.target, { ...(state.targetLabel ? { label: state.targetLabel } : {}), ...(step ? { step } : {}) })
      mine = true
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
    dispose() {
      clearT(handle)
      endMine('user')
    },
  }
}
