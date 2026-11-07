// The coach brain's decisions on the screen. While a task is in progress (GET /coach/state) this asks GET /coach/next about every
// two seconds (the engine wants steady polling: it advances its own dignity gate) and acts on the answer:
//   annotate / nudge with a target ZONE   -> a ring on that element (and the nudge text in a bubble), by capture zone
//   nudge without a target                -> the text alone, as a short caption (lighter help: no ring)
//   silent, takeover_offer                -> nothing new (a takeover offer is for the dashboard and the agent; the desktop never acts)
//
// The engine speaks once per decision: an annotate carries a decision_id and the polls after it are silent (reason `already_prompted`
// while the issue is still open). So a silent answer does NOT take the ring down. The ring stays until
//   the issue is resolved  -> the engine stops saying `already_prompted`: the worker did the step, the prompt was followed
//   the worker stops it    -> Stop, kill, clear: dismissed
//   the case is over, study mode is silencing the coach, or the engine replaced its decision -> the ring just ends, nothing is posted
//   nobody acts for a long time -> the ring's own limit ends it, nothing is posted
// The worker's response goes to POST /coach/feedback with the decision id. "repeated" and "undone" are derived by the engine from
// its own event stream; the desktop never guesses them. (The engine also labels a step done within 30 s of a prompt as followed
// by itself, so the explicit post can come back `recorded: false, already recorded`; the label is the same either way.)
import type { DomCoach, DomPromptEnd } from './dom-ground/dom-coach'
import type { CoachDecision, FeedbackOutcome, FeedbackResult } from './engine/coach-next'
import type { CoachStateInfo } from './engine/coach-state'
import type { ChipDriver } from './coach-chip'

export interface CoachBrainDeps {
  engine: { coachNext(): Promise<CoachDecision | null>; coachFeedback(decisionId: string, outcome: FeedbackOutcome): Promise<FeedbackResult> }
  // The latest task from GET /coach/state (null when none is in progress or the engine did not answer).
  state: () => CoachStateInfo | null
  ring: Pick<DomCoach, 'point' | 'clear' | 'followed' | 'current'>
  // The level and chip the engine is acting at, so the chip on screen matches what the coach does (study mode included).
  chip?: Pick<ChipDriver, 'setDecisionHint' | 'refresh'>
  // A nudge with nothing to point at: shown as text for a few seconds.
  say?: (text: string, decisionId: string | null) => void
  killed?: () => boolean
  now?: () => number
  intervalMs?: number
  immediate?: boolean
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  log?: (scope: string, ...args: unknown[]) => void
}

export interface CoachBrainStatus {
  lastDecision: { action: string; decisionId: string | null; zone: string | null; message: string; reasons: string[]; level: number | null; missed: string[]; at: number } | null
  lastFeedback: { decisionId: string; outcome: FeedbackOutcome; ok: boolean; recorded: boolean | null; note: string | null; at: number } | null
  ringDecision: string | null
}

export interface CoachBrain {
  tick(): Promise<void>
  // DomCoach's onEnd: turns how a prompt ended into feedback.
  onPromptEnd(e: DomPromptEnd): void
  // The last decision that was not silent, for the proposal scheduler: a prompt in the last minute means the worker is mid-task.
  lastActiveDecisionAt(): number | null
  status(): CoachBrainStatus
  dispose(): void
}

export function outcomeFor(how: DomPromptEnd['how']): FeedbackOutcome | null {
  if (how === 'followed') return 'followed'
  if (how === 'user' || how === 'stop') return 'dismissed'
  return null
}

// Silent because there is no case to coach, or because study mode is holding the coach back: not about the worker's response.
const MOOT = new Set(['no_active_task', 'no_events', 'no_pack', 'study_mode', 'study_post_test', 'study_off'])
const HANDLED_MAX = 64

export function createCoachBrain(deps: CoachBrainDeps): CoachBrain {
  const now = deps.now ?? Date.now
  const setT = deps.setTimer ?? ((fn, ms) => setInterval(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearInterval(h as ReturnType<typeof setInterval>))
  let mine: { decisionId: string } | null = null
  let lastActiveAt: number | null = null
  let busy = false
  let lastDecision: CoachBrainStatus['lastDecision'] = null
  let lastFeedback: CoachBrainStatus['lastFeedback'] = null
  // Decisions already put on the screen (or said). A decision the worker ended is never drawn again, whatever the engine repeats.
  const handled: string[] = []
  const remember = (id: string): void => {
    handled.push(id)
    if (handled.length > HANDLED_MAX) handled.shift()
  }

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
      if (mine && !deps.ring.current()) mine = null // the ring ended on its own (the worker stopped it, or it ran out)
      const task = deps.state()?.task ?? null
      if (!task || deps.killed?.()) {
        endMine('ended') // no task in progress (or everything is stopped): the prompt is over
        return
      }
      const decision = await deps.engine.coachNext()
      if (!decision) return // the engine did not answer: keep what is there; the ring has its own stale and time limits
      if (deps.chip && (decision.chip || decision.level)) {
        deps.chip.setDecisionHint({ fade: decision.chip, level: decision.level })
        deps.chip.refresh()
      }
      lastDecision = { action: decision.action, decisionId: decision.decisionId, zone: decision.target?.zone ?? null, message: decision.message, reasons: decision.reasons, level: decision.level, missed: decision.missed, at: now() }
      if (decision.action !== 'silent') lastActiveAt = now()

      const wantsRing = (decision.action === 'annotate' || decision.action === 'nudge') && decision.target !== null
      if (wantsRing && decision.target) {
        const id = decision.decisionId ?? `local-${decision.target.zone}`
        if (mine?.decisionId === id || handled.includes(id)) return // already on the screen, or already answered
        remember(id)
        deps.ring.point(decision.target, { message: decision.message, ref: decision.decisionId ?? undefined })
        mine = { decisionId: id }
        return
      }
      if (decision.action === 'nudge' && decision.message) {
        const id = decision.decisionId
        if (id && !handled.includes(id)) {
          remember(id)
          endMine('ended') // a newer decision than the ring
          deps.say?.(decision.message, id)
        }
        return
      }
      if (!mine) return
      // The ring is up and the engine is quiet. Why?
      if (decision.reasons.some((r) => MOOT.has(r))) {
        endMine('ended')
        return
      }
      if (decision.decisionId && decision.decisionId !== mine.decisionId) {
        endMine('ended') // the engine decided something else (a takeover offer): the old prompt is replaced
        return
      }
      // The engine says `already_prompted` while the issue it prompted about is still open. When it stops, the step was done.
      // An engine that sends no reason codes at all leaves the ring to its own limit rather than guessing.
      if (decision.action === 'silent' && decision.reasons.length > 0 && !decision.reasons.includes('already_prompted')) {
        mine = null
        deps.ring.followed()
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
      if (!outcome) return
      const decisionId = e.ref
      void deps.engine
        .coachFeedback(decisionId, outcome)
        .then((r) => {
          lastFeedback = { decisionId, outcome, ok: r.ok, recorded: r.recorded, note: r.note, at: now() }
        })
        .catch(() => undefined)
    },
    lastActiveDecisionAt: () => lastActiveAt,
    status: () => ({ lastDecision, lastFeedback, ringDecision: mine?.decisionId ?? null }),
    dispose() {
      clearT(handle)
      endMine('stale') // quitting is not the worker's response: nothing is posted
    },
  }
}
