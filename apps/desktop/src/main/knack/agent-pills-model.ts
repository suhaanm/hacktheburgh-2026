// The background agent pills (top right of the screen): what each pill says and when it comes and goes. One small pill per task or run that is working: a calm animated icon while
// it runs, a still one with a dot while it waits for an OK, a quiet check when it is done (it fades after five seconds), a dash when it was stopped, and a red dot when it failed
// (that one stays until it is clicked). At most four at a time, then "+n". Pure: the window (agent-pills.ts) draws what this says.
//
// Where the entries come from is ONE function, `onAgentRuns(cb)` (AgentRunsSource). The shell feeds it from the agent service's task events (GET /tasks/events, the task API
// contract v1) and from its run list; anything else that knows about background work can `push` the same shape. No word is a model's: a task's words are the worker's own
// (its title) or the one short step line the service writes, cut to four words; a run's are its kind made readable; what a pill says when work ends is the one result line or
// reason the service sends.
import { ACTING_RUN_STATES, RUN_MAX_AGE_MS, type RunSample } from './pill-state'

export type AgentRunState = 'working' | 'waiting' | 'done' | 'failed' | 'stopped'
/** Which kind of work: the icon. 'run' is a background run from the service's run list. */
export type AgentRoute = 'answer' | 'browser' | 'desktop' | 'claude_agent' | 'run'

/** One background task or run as the pills see it. */
export interface AgentPillRun {
  id: string
  /** What the pill says while the work goes on (already words a person can read, four at most). */
  title: string
  route: AgentRoute
  state: AgentRunState
  /** The icon moves: true while the work is running (the default for working); a task that is only planning, and one that waits for an OK, hold still. */
  animated?: boolean
  /** When it began (ms since the epoch), when known. */
  startedAt?: number
  /** The one line to show when it ends (the result, or the reason it did not finish); a plain word is used when there is none. */
  endText?: string
  /** The service lets the worker stop it from the pill. */
  stoppable?: boolean
}

/** The one door the pills take their data through. `push` is for whatever knows the work (the shell); `onAgentRuns` is what the pills listen on. */
export interface AgentRunsSource {
  onAgentRuns(cb: (runs: readonly AgentPillRun[]) => void): () => void
  push(runs: readonly AgentPillRun[]): void
}

export function createAgentRunsSource(): AgentRunsSource {
  const listeners = new Set<(runs: readonly AgentPillRun[]) => void>()
  let last: readonly AgentPillRun[] = []
  return {
    onAgentRuns(cb) {
      listeners.add(cb)
      cb(last)
      return () => listeners.delete(cb)
    },
    push(runs) {
      last = runs
      for (const cb of listeners) cb(runs)
    },
  }
}

export type PillPhase = 'working' | 'waiting' | 'done' | 'failed' | 'stopped'
export interface PillItem {
  id: string
  /** What the pill says now: the work's words, or the line it ended with. */
  text: string
  route: AgentRoute
  phase: PillPhase
  /** The icon moves (only while the work is running). */
  animated: boolean
  /** The pill is fading out (its words stay until it is gone). */
  leaving: boolean
  stoppable: boolean
}
export interface PillsView {
  items: PillItem[]
  /** Pills beyond the four shown ("+2"), 0 when none. */
  more: number
}
export const EMPTY_PILLS: PillsView = { items: [], more: 0 }

export const PILL_LIMITS = { maxVisible: 4, doneMs: 5000, stoppedMs: 3000, fadeMs: 240, maxWords: 4, maxChars: 60, endChars: 140 } as const

const END_WORD = { done: 'Done', failed: 'Did not finish', stopped: 'Stopped' } as const

/** A line that may be drawn: one line of plain text, at most `maxChars` long. */
export function plainLine(raw: unknown, maxChars: number = PILL_LIMITS.maxChars): string {
  return typeof raw === 'string' ? raw.replace(/\s+/g, ' ').trim().slice(0, maxChars) : ''
}

/** The first four words of a line, with an ellipsis when there were more: what a pill says while its work goes on. */
export function cutWords(line: string, words: number = PILL_LIMITS.maxWords): string {
  const parts = line.split(' ').filter((w) => w.length > 0)
  return parts.length <= words ? parts.join(' ') : `${parts.slice(0, words).join(' ')}…`
}

/** A run's kind as words the worker can read: "data.profile" becomes "Data profile". Four words at most, letters and digits only; a kind with nothing readable is "Task". */
export function titleOf(kind: string): string {
  const words = kind
    .replace(/[^A-Za-z0-9]+/g, ' ')
    .trim()
    .split(/\s+/)
    .filter((w) => w.length > 0)
    .slice(0, PILL_LIMITS.maxWords)
  if (words.length === 0) return 'Task'
  const text = words.join(' ').toLowerCase()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

const FAILED = new Set(['failed', 'timeout', 'rejected'])
const FINISHED = new Set(['done', 'partial'])

/** The service's run rows to what the pills need. A run that is "running" on a record older than any run can last is a ghost left by a dead process: not working, and not shown. */
export function pillRunsOf(runs: readonly RunSample[], now: number): AgentPillRun[] {
  return runs.map((r) => {
    const ghost = ACTING_RUN_STATES.has(r.state) && r.startedAt !== undefined && now - r.startedAt > RUN_MAX_AGE_MS
    const state: AgentRunState = ghost ? 'stopped' : ACTING_RUN_STATES.has(r.state) ? 'working' : FINISHED.has(r.state) ? 'done' : FAILED.has(r.state) ? 'failed' : 'stopped'
    return { id: r.id, title: titleOf(r.kind ?? ''), route: 'run', state, animated: true, ...(r.startedAt !== undefined ? { startedAt: r.startedAt } : {}) }
  })
}

const ROUTES: ReadonlySet<string> = new Set(['answer', 'browser', 'desktop', 'claude_agent'])
const TASK_ID = /^tk_[A-Za-z0-9]{4,24}$/

/** The paths the service recorded for finished tasks (row.open.path, a folder or a file): the only paths the desktop will reveal in Finder. */
export function openPathsOfTasks(rows: readonly unknown[]): string[] {
  const out: string[] = []
  for (const raw of rows) {
    const open = typeof raw === 'object' && raw !== null ? (raw as { open?: unknown }).open : null
    if (typeof open !== 'object' || open === null) continue
    const o = open as { kind?: unknown; path?: unknown }
    if ((o.kind === 'folder' || o.kind === 'file') && typeof o.path === 'string' && o.path.startsWith('/') && o.path.length <= 1024 && !o.path.includes('\0')) out.push(o.path)
  }
  return out
}

/**
 * The task API's rows (GET /tasks/events, contract v1) to pills. One pill per task that is planning, running or waiting for consent; a task that has ended is listed with its end line
 * so a pill that was showing it can say how it went. The label is the current step line, else the title, cut to four words: both are short plain lines the service writes (nothing
 * here ever draws a prompt or an output). A row that is not an object with a well-formed id is skipped.
 */
export function pillRunsOfTasks(rows: readonly unknown[]): AgentPillRun[] {
  const out: AgentPillRun[] = []
  for (const raw of rows) {
    if (typeof raw !== 'object' || raw === null) continue
    const r = raw as Record<string, unknown>
    if (typeof r.task_id !== 'string' || !TASK_ID.test(r.task_id) || typeof r.state !== 'string') continue
    const title = cutWords(plainLine(r.latest) || plainLine(r.title)) || 'Task'
    const route: AgentRoute = typeof r.route === 'string' && ROUTES.has(r.route) ? (r.route as AgentRoute) : 'answer'
    const started = typeof r.started === 'string' ? Date.parse(r.started) : Number.NaN
    const base = { id: r.task_id, title, route, ...(Number.isFinite(started) ? { startedAt: started } : {}) }
    if (r.state === 'running') out.push({ ...base, state: 'working', animated: true, stoppable: true })
    else if (r.state === 'planning') out.push({ ...base, state: 'working', animated: false, stoppable: true })
    else if (r.state === 'waiting_consent') out.push({ ...base, state: 'waiting', animated: false, stoppable: true })
    else if (r.state === 'done') out.push({ ...base, state: 'done', endText: plainLine(r.result, PILL_LIMITS.endChars) || undefined })
    else if (r.state === 'failed') out.push({ ...base, state: 'failed', endText: plainLine(r.reason, PILL_LIMITS.endChars) || undefined })
    else if (r.state === 'stopped') out.push({ ...base, state: 'stopped' })
  }
  return out
}

export interface PillsModelDeps {
  now?: () => number
  setTimer?: (fn: () => void, ms: number) => unknown
  clearTimer?: (h: unknown) => void
  onChange: (view: PillsView) => void
}

export interface PillsModel {
  /** The work as it is now (all of it, finished included: only work seen going on earns a finished pill, and nothing is left behind). */
  update(runs: readonly AgentPillRun[]): void
  /** The worker clicked a pill that stays until it is seen (a failure): it fades away. */
  dismiss(id: string): void
  view(): PillsView
  dispose(): void
}

interface Held {
  id: string
  text: string
  route: AgentRoute
  phase: PillPhase
  animated: boolean
  stoppable: boolean
  startedAt: number
  leaving: boolean
  timer: unknown
  order: number
}

export function createPillsModel(deps: PillsModelDeps): PillsModel {
  const now = deps.now ?? Date.now
  const setT = deps.setTimer ?? ((fn, ms) => setTimeout(fn, ms))
  const clearT = deps.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  const held = new Map<string, Held>()
  let order = 0
  let last: PillsView = EMPTY_PILLS

  const compute = (): PillsView => {
    const all = [...held.values()].sort((a, b) => a.startedAt - b.startedAt || a.order - b.order)
    const shown = all.slice(0, PILL_LIMITS.maxVisible)
    return { items: shown.map((h) => ({ id: h.id, text: h.text, route: h.route, phase: h.phase, animated: h.animated, leaving: h.leaving, stoppable: h.stoppable })), more: all.length - shown.length }
  }
  const emit = (): void => {
    const next = compute()
    if (JSON.stringify(next) === JSON.stringify(last)) return
    last = next
    deps.onChange(next)
  }

  const fadeOut = (h: Held): void => {
    h.leaving = true
    emit()
    h.timer = setT(() => {
      held.delete(h.id)
      emit()
    }, PILL_LIMITS.fadeMs)
  }
  const ending = (h: Held, phase: 'done' | 'failed' | 'stopped', text: string): void => {
    if (h.timer !== null) clearT(h.timer)
    h.phase = phase
    h.text = text
    h.stoppable = false
    h.animated = false
    h.leaving = false
    // A failure stays until the worker has seen it (a click); a check and a dash go by themselves.
    h.timer = phase === 'failed' ? null : setT(() => fadeOut(h), phase === 'done' ? PILL_LIMITS.doneMs : PILL_LIMITS.stoppedMs)
  }
  const working = (h: Held): boolean => h.phase === 'working' || h.phase === 'waiting'

  return {
    update(runs) {
      const t = now()
      const listed = new Set(runs.map((r) => r.id))
      for (const r of runs) {
        const cur = held.get(r.id)
        if (r.state === 'working' || r.state === 'waiting') {
          const animated = r.state === 'working' && r.animated !== false
          if (!cur) held.set(r.id, { id: r.id, text: r.title, route: r.route, phase: r.state, animated, stoppable: r.stoppable === true, startedAt: r.startedAt ?? t, leaving: false, timer: null, order: order++ })
          else {
            if (!working(cur) && cur.timer !== null) {
              clearT(cur.timer) // the same work is going again (a resume): back to a working pill
              cur.timer = null
            }
            cur.phase = r.state
            cur.text = r.title
            cur.route = r.route
            cur.animated = animated
            cur.stoppable = r.stoppable === true
            cur.leaving = false
          }
        } else if (cur && working(cur)) {
          ending(cur, r.state, plainLine(r.endText, PILL_LIMITS.endChars) || END_WORD[r.state])
        }
      }
      // Work that was going on and is no longer listed has ended (the list is the service's live view): a quiet check, never a stuck pill.
      for (const h of [...held.values()]) if (working(h) && !listed.has(h.id)) ending(h, 'done', END_WORD.done)
      emit()
    },
    dismiss(id) {
      const h = held.get(id)
      if (h && h.phase === 'failed' && !h.leaving) fadeOut(h)
    },
    view: () => last,
    dispose() {
      for (const h of held.values()) if (h.timer !== null) clearT(h.timer)
      held.clear()
    },
  }
}
