// The coach brain's decisions on the screen. While a task is in progress (GET /coach/state) this asks GET /coach/next about every
// two seconds and acts on the answer:
//   annotate / nudge with a target ZONE   -> a ring on that element (and the nudge text in a bubble), by capture zone
//   silent, no target, or takeover_offer  -> no ring (a takeover offer is for the dashboard and the agent; the desktop never acts)
// The worker's response goes back to POST /coach/feedback with the decision id:
//   the step was done while the ring was up   -> followed
//   the worker stopped it (Stop, kill, clear) -> dismissed
// Anything else (the brain replaced its own decision, the ring timed out, the task ended) is not the worker's response, so
// nothing is posted. "repeated" and "undone" are derived by the engine from its own event stream; the desktop never guesses them.
import type { DomCoach, DomPromptEnd } from './dom-ground/dom-coach'
import type { CoachDecision, FeedbackOutcome } from './engine/coach-next'
import type { CoachStateInfo } from './engine/coach-state'

export interface CoachBrainDeps {
  engine: { coachNext(): Promise<CoachDecision | null>; coachFeedback(decisionId: string, outcome: FeedbackOutcome): Promise<boolean> }
  // The latest task from GET /coach/state (null when none is in progress or the engine did not answer).
  state: () => CoachStateInfo | null
  ring: Pick<DomCoach, 'point' | 'clear' | 'followed' | 'current'>
  killed?: () => boolean
  now?: () => number
  intervalMs?: number
  immediate?: boolean
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  log?: (scope: string, ...args: unknown[]) => void
}

export interface CoachBrain {
  tick(): Promise<void>
  // DomCoach's onEnd: turns how a prompt ended into feedback.
  onPromptEnd(e: DomPromptEnd): void
  // The last decision that was not silent, for the proposal scheduler: a prompt in the last minute means the worker is mid-task.
  lastActiveDecisionAt(): number | null
  dispose(): void
}

export function outcomeFor(how: DomPromptEnd['how']): FeedbackOutcome | null {
  if (how === 'followed') return 'followed'
  if (how === 'user' || how === 'stop') return 'dismissed'
  return null
}

export function createCoachBrain(deps: CoachBrainDeps): CoachBrain {
  const now = deps.now ?? Date.now
  const setT = deps.setTimer ?? ((fn, ms) => setInterval(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearInterval(h as ReturnType<typeof setInterval>))
  let mine: { decisionId: string; taskId: string | null; step: number | null } | null = null
  let lastActiveAt: number | null = null
  let busy = false

  const endMine = (how: 'ended' | 'stale'): void => {
    if (mine) {
      mine = null
      deps.ring.clear(how)
    }
  }

  const tick = async (): Promise<void> => {
    if (busy) return
    busy = true
    try {
      const task = deps.state()?.task ?? null
      if (!task || deps.killed?.()) {
        endMine('ended') // no task in progress (or everything is stopped): the prompt is over
        return
      }
      const decision = await deps.engine.coachNext()
      if (!decision) return // the engine did not answer: keep what is there; the ring has its own stale and time limits

      // Did the worker finish the step this ring pointed at?
      if (mine && deps.ring.current() && mine.taskId === task.id && mine.step !== null && task.step > mine.step) {
        mine = null
        deps.ring.followed()
      }

      const wantsRing = (decision.action === 'annotate' || decision.action === 'nudge') && decision.target !== null
      if (decision.action !== 'silent') lastActiveAt = now()
      if (!wantsRing || !decision.target) {
        endMine('ended')
        return
      }
      const id = decision.decisionId ?? `local-${decision.target.zone}`
      if (!mine || mine.decisionId !== id) {
        deps.ring.point(decision.target, { message: decision.message, step: task.step >= 1 && task.step <= 99 ? task.step : undefined, ref: decision.decisionId ?? undefined })
        mine = { decisionId: id, taskId: task.id, step: task.step }
      }
    } catch (err) {
      deps.log?.('coach-brain', `tick failed: ${err instanceof Error ? err.message : String(err)}`)
    } finally {
      busy = false
    }
  }

  const handle = setT(() => void tick(), deps.intervalMs ?? 2000)
  if (deps.immediate !== false) void tick()
  return {
    tick,
    onPromptEnd(e) {
      if (!e.ref || !e.shown) return // never drawn, or not from the brain: no response to report
      const outcome = outcomeFor(e.how)
      if (outcome) void deps.engine.coachFeedback(e.ref, outcome).catch(() => undefined)
    },
    lastActiveDecisionAt: () => lastActiveAt,
    dispose() {
      clearT(handle)
      endMine('stale') // quitting is not the worker's response: nothing is posted
    },
  }
}
