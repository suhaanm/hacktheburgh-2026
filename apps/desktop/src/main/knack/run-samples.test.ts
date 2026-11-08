import { describe, expect, it } from 'vitest'
import { createActivityTracker } from './activity'
import { runsOf, taskSamplesOf } from './run-samples'
import type { PillSignals } from './pill-state'
import type { ShellEvent } from './shell-machine'

const taskRow = (id: string, state: string, over: Record<string, unknown> = {}) => ({ task_id: id, title: 'Fill in the form', route: 'browser', state, latest: null, started: '2026-11-08T00:10:00Z', ...over })

describe('the run list as samples', () => {
  it('reads a list, { data } or { runs }, with the children done and in all, the start time and the kind', () => {
    const row = { run_id: 'r_1', state: 'running', kind: 'data.profile', started: '2026-11-08T00:10:00Z', children: [{ state: 'done' }, { state: 'created' }, { state: 'partial' }] }
    for (const raw of [[row], { data: [row] }, { runs: [row] }]) {
      expect(runsOf(raw)).toEqual([{ id: 'r_1', state: 'running', progress: { done: 2, total: 3 }, startedAt: Date.parse('2026-11-08T00:10:00Z'), kind: 'data.profile' }])
    }
  })
  it('skips rows without an id or a state, and anything that is not a list', () => {
    expect(runsOf([{ state: 'running' }, { run_id: 'r_2' }, null, 'x'])).toEqual([])
    expect(runsOf(null)).toEqual([])
    expect(runsOf('nope')).toEqual([])
  })
})

describe('the task events as samples for the corner pill', () => {
  it('planning, running and waiting for consent are acting; ended tasks say how; nothing else is a sample', () => {
    const out = taskSamplesOf([taskRow('tk_a', 'planning'), taskRow('tk_b', 'running'), taskRow('tk_c', 'waiting_consent'), taskRow('tk_d', 'done'), taskRow('tk_e', 'failed'), taskRow('tk_f', 'stopped'), taskRow('tk_g', 'surprise'), { state: 'running' }, null])
    expect(out.map((r) => [r.id, r.state])).toEqual([['tk_a', 'running'], ['tk_b', 'running'], ['tk_c', 'running'], ['tk_d', 'done'], ['tk_e', 'failed'], ['tk_f', 'stopped']])
    expect(out[0]).toMatchObject({ kind: 'task', startedAt: Date.parse('2026-11-08T00:10:00Z') })
  })
  it('never carries children, so the pill never says "n of m" for a task', () => {
    for (const r of taskSamplesOf([taskRow('tk_a', 'running')])) expect(r.progress).toBeUndefined()
  })
})

// The owner's stale pill, from the task side: a task starts, the pill says working; the task finishes and the pill goes, whatever else is listed.
describe('the corner pill follows a task from its start to its end', () => {
  function rig() {
    let now = 5_000_000
    const events: ShellEvent[] = []
    const timers: { fn: () => void; at: number }[] = []
    const t = createActivityTracker({ emit: (e) => events.push(e), now: () => now, setTimer: (fn, ms) => (timers.push({ fn, at: now + ms }), timers.length), clearTimer: () => undefined })
    const sig = (rows: unknown[], over: Partial<PillSignals> = {}): PillSignals => ({ reachable: true, supervisor: 'idle', runs: taskSamplesOf(rows), killed: false, pending: 0, ...over })
    return { t, events, tick: (ms: number) => (now += ms), sig, take: () => events.splice(0) }
  }
  it('task_started shows the pill with the words alone, and task_finished (done) turns it into the check and clears it', () => {
    const r = rig()
    r.t.ingest(r.sig([taskRow('tk_a', 'running', { started: new Date(5_000_000 - 1000).toISOString() })]))
    expect(r.take()).toEqual([{ type: 'run_started', realScreen: false }])
    r.tick(2000)
    r.t.ingest(r.sig([taskRow('tk_a', 'running', { latest: 'Opening the page', started: new Date(5_000_000 - 1000).toISOString() })]))
    expect(r.take()).toEqual([{ type: 'run_progress', label: 'Working on it' }]) // no n of m, no step 0
    r.tick(2000)
    r.t.ingest(r.sig([taskRow('tk_a', 'done', { started: new Date(5_000_000 - 1000).toISOString() })]))
    expect(r.take()).toEqual([{ type: 'run_done', needsNothing: true }])
  })
  it('a failed or stopped task also ends the pill (a failure turns it to the error state; a stop ends it quietly)', () => {
    const r1 = rig()
    r1.t.ingest(r1.sig([taskRow('tk_a', 'running', { started: new Date(4_999_000).toISOString() })]))
    r1.take()
    r1.t.ingest(r1.sig([taskRow('tk_a', 'failed', { started: new Date(4_999_000).toISOString() })]))
    expect(r1.take()).toEqual([{ type: 'run_failed' }])
    const r2 = rig()
    r2.t.ingest(r2.sig([taskRow('tk_a', 'running', { started: new Date(4_999_000).toISOString() })]))
    r2.take()
    r2.t.ingest(r2.sig([taskRow('tk_a', 'stopped', { started: new Date(4_999_000).toISOString() })]))
    expect(r2.take().map((e) => e.type)).not.toContain('run_failed')
  })
  it('a task that disappears from the stream ends the pill too: the pill never outlives the list', () => {
    const r = rig()
    r.t.ingest(r.sig([taskRow('tk_a', 'running', { started: new Date(4_999_000).toISOString() })]))
    r.take()
    r.t.ingest(r.sig([]))
    expect(r.take()).toEqual([{ type: 'run_done', needsNothing: true }])
  })
})
