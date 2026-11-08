// The corner pill's state machine, without Electron: from what the agent service says (and the kill switch, and the approval queue) to one of six
// states, with the words it shows taken from a closed list. Everything here is deterministic code; no model text ever reaches the pill.
//
//   idle       nothing is happening; the pill is not on screen
//   working    an agent run (or the supervisor) is running
//   needs-you  something waits for the worker: an approval in the queue that was not there when the run began, or a run that paused itself
//   done       a run ended and there is nothing to approve (a few seconds, then idle)
//   error      a run failed, timed out, was rejected, or the agent service went quiet while working
//   killed     the kill switch is on
//
// The numbers (how long done and error stay, when "Still working" replaces "Working on it") are one object, PILL_TIMING, so the UX spec can tune them.

export type PillKind = 'idle' | 'working' | 'needs-you' | 'done' | 'error' | 'killed'

/** Every sentence the pill can ever say. Five words at most. (A test holds the list to that.) */
export const PILL_TEXTS = ['Working on it', 'Still working', 'Needs your OK', 'All done', 'Something went wrong', 'Lost contact', 'Stopped'] as const
export type PillText = (typeof PILL_TEXTS)[number]

export const PILL_TIMING = {
  /** "All done" stays this long, then the pill goes away. */
  doneMs: 6000,
  /** An error stays this long unless the worker opens Knack first. */
  errorMs: 30_000,
  /** After this long a run reads "Still working" instead of "Working on it". */
  stillWorkingMs: 90_000,
  /** The agent service did not answer for this long while a run was working: that is an error, not a silence. */
  lostMs: 15_000,
} as const
export type PillTiming = { readonly [K in keyof typeof PILL_TIMING]: number }

/** Run states that mean the agent is acting right now (agent runtime: created, planning, running; the supervisor: running). */
export const ACTING_RUN_STATES: ReadonlySet<string> = new Set(['created', 'planning', 'running'])

/**
 * No real run lasts longer than this: the agent service caps a whole run at 900 seconds (policy.RUN_MAX_SECONDS), so a run that says it is still running after 17 minutes is
 * not running. It is a record left on disk by a process that died mid-run (GET /agents/runs lists those too, state and all), and it must never keep the pill up.
 */
export const RUN_MAX_AGE_MS = 17 * 60_000

export interface RunSample {
  id: string
  state: string
  /** Children done and in all, when the run lists them: "n of m". */
  progress?: { done: number; total: number }
  /** When the run began (ms since the epoch), from the service's `started`; absent when it did not say. */
  startedAt?: number
  /** What kind of run (the service's closed list, "data.profile"): the background agent pills make it readable. */
  kind?: string
}

/** A run that is acting now: in an acting state, and young enough to be real (a run record older than any run can last is a ghost). */
export const isActingRun = (r: RunSample, now: number): boolean => ACTING_RUN_STATES.has(r.state) && (r.startedAt === undefined || now - r.startedAt <= RUN_MAX_AGE_MS)

export interface PillSignals {
  /** The agent service answered this time (GET /health). */
  reachable: boolean
  /** supervisor.state from GET /health: idle, running, queued, stopped, killed, yielded, timeout, failed; null when not known. */
  supervisor: string | null
  /** Runs listed by GET /agents/runs, when that route is on. */
  runs: readonly RunSample[]
  /** The kill switch is on (this app's, or the agent service says killed). */
  killed: boolean
  /** An agent of this app is acting on the worker's own screen (the desktop's act-for-me), which the agent service cannot see. Absent means no. */
  local?: boolean
  /** Approvals waiting in the queue now; null when the engine cannot be asked. */
  pending: number | null
}

export interface PillState {
  kind: PillKind
  text: PillText | ''
  /** When this state began (ms). */
  since: number
  /** When the current run began, while one is working or waiting for the worker. */
  runStartedAt: number | null
  /** The approval count when the run began; "needs you" means more than this now. null: not known. */
  baseline: number | null
  /** Run states seen at the last sample, to tell which run just ended. */
  prevRuns: Readonly<Record<string, string>>
  /** First time the service was unreachable during a run (null while it answers). */
  lostSince: number | null
}

export const IDLE_PILL: PillState = { kind: 'idle', text: '', since: 0, runStartedAt: null, baseline: null, prevRuns: {}, lostSince: null }

const TEXT: Record<PillKind, PillText | ''> = { idle: '', working: 'Working on it', 'needs-you': 'Needs your OK', done: 'All done', error: 'Something went wrong', killed: 'Stopped' }

const to = (prev: PillState, kind: PillKind, now: number, over: Partial<PillState> = {}): PillState => ({ ...prev, kind, text: TEXT[kind], since: prev.kind === kind ? prev.since : now, ...over })

// A ghost (an acting state on a record too old to be a real run) is listed as stopped, so the pill neither starts for it nor waits for it to end.
const runMap = (runs: readonly RunSample[], now: number): Record<string, string> => Object.fromEntries(runs.map((r) => [r.id, ACTING_RUN_STATES.has(r.state) && !isActingRun(r, now) ? 'stale' : r.state]))

/**
 * What a run that just ended asks of the worker: 'error', 'killed', 'paused' (the run stopped itself and a person must look), 'needs' (approvals are
 * waiting), 'done', or 'quiet' (the worker stopped it, or took over the keyboard).
 */
export function endOf(prevRuns: Readonly<Record<string, string>>, nowRuns: Readonly<Record<string, string>>, supervisor: string | null, approvalsWaiting: boolean): 'error' | 'killed' | 'paused' | 'needs' | 'done' | 'quiet' {
  const ended = Object.entries(prevRuns)
    .filter(([id, st]) => ACTING_RUN_STATES.has(st) && nowRuns[id] !== undefined && !ACTING_RUN_STATES.has(nowRuns[id]!))
    .map(([id]) => nowRuns[id]!)
  if (supervisor === 'failed' || supervisor === 'timeout' || ended.some((s) => ['failed', 'timeout', 'rejected'].includes(s))) return 'error'
  if (supervisor === 'killed' || ended.includes('killed')) return 'killed'
  if (ended.includes('paused')) return 'paused'
  if (approvalsWaiting) return 'needs'
  if (ended.length > 0 && ended.every((s) => ['stopped', 'yielded'].includes(s))) return 'quiet'
  if (ended.length === 0 && (supervisor === 'stopped' || supervisor === 'yielded')) return 'quiet'
  return 'done'
}

/** One tick: the new state from the old one, the latest signals and the clock. Pure. */
export function stepPill(prev: PillState, s: PillSignals, now: number, timing: PillTiming = PILL_TIMING): PillState {
  const nowRuns = runMap(s.runs, now)
  const keepRuns = s.reachable ? nowRuns : prev.prevRuns

  // The kill switch beats everything, and clearing it returns to quiet, never straight to working.
  if (s.killed) return to(prev, 'killed', now, { runStartedAt: null, baseline: null, prevRuns: keepRuns, lostSince: null })
  const was: PillState = prev.kind === 'killed' ? { ...IDLE_PILL, prevRuns: keepRuns } : prev

  if (!s.reachable) {
    // Never turn a showing pill off, or a quiet one on, because of one failed look. During a run, a long silence is an error.
    if (was.kind === 'working' || (was.kind === 'needs-you' && was.runStartedAt !== null)) {
      const lostSince = was.lostSince ?? now
      if (now - lostSince >= timing.lostMs && was.kind === 'working') return { ...to(was, 'error', now, { runStartedAt: null, baseline: null }), text: 'Lost contact', lostSince: null }
      return { ...was, lostSince }
    }
    return expire(was, now, timing)
  }

  const acting = s.local === true || s.supervisor === 'running' || s.runs.some((r) => isActingRun(r, now))
  const waiting = was.baseline !== null && s.pending !== null && s.pending > was.baseline

  if (acting) {
    const starting = was.kind !== 'working' && !(was.kind === 'needs-you' && was.runStartedAt !== null)
    const base: Partial<PillState> = starting ? { runStartedAt: now, baseline: s.pending, prevRuns: nowRuns, lostSince: null } : { prevRuns: nowRuns, lostSince: null }
    // An approval raised in the middle of a run: the run is at its gate, and the worker is asked now.
    if (!starting && waiting) return to(was, 'needs-you', now, base)
    const still = !starting && was.runStartedAt !== null && now - was.runStartedAt >= timing.stillWorkingMs
    const next = to(was, 'working', now, base)
    return still ? { ...next, text: 'Still working' } : next
  }

  // Nothing is acting. Did a run just end?
  const hadRun = was.kind === 'working' || (was.kind === 'needs-you' && was.runStartedAt !== null)
  if (hadRun) {
    const outcome = endOf(was.prevRuns, nowRuns, s.supervisor, waiting)
    const cleared: Partial<PillState> = { runStartedAt: null, baseline: was.baseline, prevRuns: nowRuns, lostSince: null }
    if (outcome === 'error') return to(was, 'error', now, { ...cleared, baseline: null })
    if (outcome === 'killed') return to(was, 'killed', now, { ...cleared, baseline: null })
    if (outcome === 'paused') return to(was, 'needs-you', now, { ...cleared, baseline: null }) // nothing in the queue to settle it: it waits until the worker has looked
    if (outcome === 'needs') return to(was, 'needs-you', now, cleared)
    if (outcome === 'quiet') return { ...IDLE_PILL, prevRuns: nowRuns, since: now }
    return to(was, 'done', now, { ...cleared, baseline: null })
  }

  // needs-you with no run behind it: it clears when the queue is back to what it was.
  if (was.kind === 'needs-you') {
    const settled = was.baseline === null || s.pending === null ? false : s.pending <= was.baseline
    return settled ? { ...IDLE_PILL, prevRuns: nowRuns, since: now } : { ...was, prevRuns: nowRuns }
  }
  return expire({ ...was, prevRuns: nowRuns }, now, timing)
}

function expire(p: PillState, now: number, timing: PillTiming): PillState {
  if (p.kind === 'done' && now - p.since >= timing.doneMs) return { ...IDLE_PILL, prevRuns: p.prevRuns, since: now }
  if (p.kind === 'error' && now - p.since >= timing.errorMs) return { ...IDLE_PILL, prevRuns: p.prevRuns, since: now }
  return p
}

/** The worker opened Knack (the pill, the Dock icon, or the window itself): what was waiting for their eye is seen. */
export function acknowledge(p: PillState, now: number): PillState {
  if (p.kind === 'done' || p.kind === 'error' || (p.kind === 'needs-you' && p.runStartedAt === null)) return { ...IDLE_PILL, prevRuns: p.prevRuns, since: now }
  return p
}

/** What the pill window draws: nothing for idle; a Stop button only while something works; the whole pill opens Knack. */
export interface PillView {
  kind: PillKind
  text: PillText | ''
  stop: boolean
  open: boolean
}
export const IDLE_VIEW: PillView = { kind: 'idle', text: '', stop: false, open: false }

export function pillView(p: PillState): PillView {
  if (p.kind === 'idle') return IDLE_VIEW
  return { kind: p.kind, text: p.text, stop: p.kind === 'working', open: true }
}
