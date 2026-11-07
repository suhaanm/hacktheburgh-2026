// What is happening, as events for the shell machine. The agent service's samples (GET /health, GET /agents/runs), the approval queue count and the desktop's own acting
// flag go in; out come the machine's events (run started, progress, decision needed, done, failed) and the pill's words, which come from a fixed list, never from a model.
//
// The reading of the samples (what counts as a run starting, ending, failing or waiting for the worker) is stepPill in pill-state.ts; this file turns its changes into
// machine events and puts "n of m" on progress when a run lists its children. Events go out through `emit`, in order, including the ones a timer causes later (the done
// card going, an error ageing out).
import { createPillController, type PillController } from './pill-controller'
import { PILL_TIMING, type PillSignals, type PillState, type PillTiming } from './pill-state'
import { TIMING, type ShellEvent } from './shell-machine'

export interface ActivityDeps {
  emit: (e: ShellEvent) => void
  now?: () => number
  timing?: PillTiming
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
}

export interface ActivityTracker {
  /** One look at the world. The events it caused go to `emit`. */
  ingest(signals: PillSignals): void
  state(): PillState
  /** The worker has seen a finished or failed run. */
  acknowledge(): void
  dispose(): void
}

/** Done and total over the runs that are working, when any of them lists children. */
export function progressOf(signals: Pick<PillSignals, 'runs'>): { n: number; m: number } | null {
  let n = 0
  let m = 0
  for (const r of signals.runs) {
    if (r.progress && r.state !== 'done') {
      n += r.progress.done
      m += r.progress.total
    }
  }
  return m > 0 ? { n, m } : null
}

export function createActivityTracker(deps: ActivityDeps): ActivityTracker {
  // The done card lives as long as the machine says (2.5 s), not as long as the pill's own default.
  const timing: PillTiming = deps.timing ?? { ...PILL_TIMING, doneMs: TIMING.doneMs }
  const ctrl: PillController = createPillController({ now: deps.now, timing, setTimer: deps.setTimer, clearTimer: deps.clearTimer })
  let realScreen = false
  let lastProgress = ''

  ctrl.subscribe((s, prev) => {
    const a = prev.kind
    const b = s.kind
    if (a === 'killed' && b !== 'killed') deps.emit({ type: 'resume' }) // heard first: a run that starts after a kill must not be ignored
    if (b === 'working' && a !== 'working' && !(a === 'needs-you' && prev.runStartedAt !== null)) {
      lastProgress = ''
      deps.emit({ type: 'run_started', realScreen })
    } else if (b === 'needs-you' && s.runStartedAt !== null) {
      deps.emit({ type: 'decision_needed', class: 'approval' }) // an approval raised in the middle of a run
    } else if (b === 'needs-you') {
      // The run ended and left something for the worker: the run is done, and the card says what is waiting.
      deps.emit({ type: 'run_done', needsNothing: false })
      deps.emit({ type: 'decision_needed', class: 'approval' })
    } else if (b === 'done') {
      deps.emit({ type: 'run_done', needsNothing: true })
    } else if (b === 'error') {
      deps.emit({ type: 'run_failed' })
    } else if (b === 'killed' && a !== 'killed') {
      deps.emit({ type: 'kill' }) // the agent service says killed (stopped from the dashboard, say): the machine hears it like the key
    } else if (b === 'idle' && a === 'done') {
      deps.emit({ type: 'done_timer' })
    } else if (b === 'idle' && a === 'error') {
      deps.emit({ type: 'error_acknowledged' })
    }
  })

  return {
    ingest(signals) {
      realScreen = signals.local === true
      const before = ctrl.state()
      const after = ctrl.ingest(signals)
      // Progress while working: the words ("Working on it", then "Still working") and "n of m" when the runs list their children.
      if (after.kind === 'working' && before.kind === 'working') {
        const p = progressOf(signals)
        const key = `${after.text}|${p?.n ?? ''}|${p?.m ?? ''}`
        if (key !== lastProgress) {
          lastProgress = key
          deps.emit({ type: 'run_progress', label: after.text, ...(p ? { n: p.n, m: p.m } : {}) })
        }
      }
    },
    state: () => ctrl.state(),
    acknowledge() {
      ctrl.acknowledge()
    },
    dispose: () => ctrl.dispose(),
  }
}
