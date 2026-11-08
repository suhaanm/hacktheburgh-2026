// The agent service's answers as run samples for the corner pill's own tracking (pill-state.ts): the run list (GET /agents/runs) and the task events' rows (GET /tasks/events). Pure.
import type { PillSignals } from './pill-state'

type Run = NonNullable<PillSignals['runs']>[number]
const asObj = (v: unknown): Record<string, unknown> | null => (typeof v === 'object' && v !== null && !Array.isArray(v) ? (v as Record<string, unknown>) : null)

/** GET /agents/runs, as a list or { data: [...] }, to the ids, states and (when listed) children done and in all. */
export function runsOf(raw: unknown): Run[] {
  const wrapped = asObj(raw)
  const list = Array.isArray(raw) ? raw : wrapped && Array.isArray(wrapped.data) ? (wrapped.data as unknown[]) : wrapped && Array.isArray(wrapped.runs) ? (wrapped.runs as unknown[]) : []
  const out: Run[] = []
  for (const r of list) {
    const o = asObj(r)
    const id = typeof o?.run_id === 'string' ? o.run_id : typeof o?.id === 'string' ? o.id : null
    if (!o || !id || typeof o.state !== 'string') continue
    const kids = Array.isArray(o.children) ? o.children.map(asObj).filter((c): c is Record<string, unknown> => c !== null) : []
    const done = kids.filter((c) => typeof c.state === 'string' && ['done', 'partial'].includes(c.state)).length
    // `started` is when the run began: the pill needs it to tell a real run from a record that a dead process left on disk (which the service lists with its last state).
    const startedAt = typeof o.started === 'string' ? Date.parse(o.started) : Number.NaN
    out.push({ id, state: o.state, ...(kids.length > 0 ? { progress: { done, total: kids.length } } : {}), ...(Number.isFinite(startedAt) ? { startedAt } : {}), ...(typeof o.kind === 'string' ? { kind: o.kind } : {}) })
  }
  return out
}

/**
 * The task API's rows as run samples for the corner pill's own tracking, so the pill follows tasks as well as runs: a task that is planning, running or waiting for consent is a run that
 * is acting, and one that has ended says how (done, failed, stopped), which clears the pill. No children, so never an "n of m": the words alone.
 */
export function taskSamplesOf(rows: readonly unknown[]): Run[] {
  const out: Run[] = []
  for (const raw of rows) {
    const o = asObj(raw)
    if (!o || typeof o.task_id !== 'string' || typeof o.state !== 'string') continue
    const state = o.state === 'planning' || o.state === 'running' || o.state === 'waiting_consent' ? 'running' : o.state === 'done' ? 'done' : o.state === 'failed' ? 'failed' : o.state === 'stopped' ? 'stopped' : null
    if (!state) continue
    const startedAt = typeof o.started === 'string' ? Date.parse(o.started) : Number.NaN
    out.push({ id: o.task_id, state, kind: 'task', ...(Number.isFinite(startedAt) ? { startedAt } : {}) })
  }
  return out
}

