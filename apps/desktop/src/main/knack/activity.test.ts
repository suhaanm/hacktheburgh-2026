import { describe, expect, it } from 'vitest'
import { QUIET_CLEAR_MS, createActivityTracker, isQuiet, pillOutlivedWork, progressOf } from './activity'
import { RUN_MAX_AGE_MS, type PillSignals } from './pill-state'
import type { ShellEvent } from './shell-machine'

const sig = (over: Partial<PillSignals> = {}): PillSignals => ({ reachable: true, supervisor: 'idle', runs: [], killed: false, pending: 0, ...over })
const running = (over: Partial<PillSignals> = {}): PillSignals => sig({ supervisor: 'running', runs: [{ id: 'r_1', state: 'running' }], ...over })

function rig() {
  let now = 0
  const events: ShellEvent[] = []
  const timers: { fn: () => void; at: number }[] = []
  const t = createActivityTracker({ emit: (e) => events.push(e), now: () => now, setTimer: (fn, ms) => (timers.push({ fn, at: now + ms }), timers.length), clearTimer: () => undefined })
  return { t, events, at: (ms: number) => (now = ms), fire: () => { const x = timers.at(-1)!; now = Math.max(now, x.at); x.fn() }, take: () => events.splice(0) }
}

describe('from the agent service to the shell machine', () => {
  it('a sandbox job starting is a run that does not use the real screen; the desktop acting on the worker screen is one that does', () => {
    const a = rig()
    a.t.ingest(running())
    expect(a.take()).toEqual([{ type: 'run_started', realScreen: false }])
    const b = rig()
    b.t.ingest(sig({ local: true }))
    expect(b.take()).toEqual([{ type: 'run_started', realScreen: true }])
  })

  it('progress: the words, then "n of m" when the runs list their children, and nothing when nothing changed', () => {
    const r = rig()
    r.t.ingest(running())
    r.take()
    r.at(1000)
    r.t.ingest(running())
    expect(r.take()).toEqual([{ type: 'run_progress', label: 'Working on it' }])
    r.at(2000)
    r.t.ingest(running())
    expect(r.take()).toEqual([])
    r.at(3000)
    r.t.ingest(sig({ supervisor: 'running', runs: [{ id: 'r_1', state: 'running', progress: { done: 3, total: 8 } }] }))
    expect(r.take()).toEqual([{ type: 'run_progress', label: 'Working on it', n: 3, m: 8 }])
  })

  it('a run that ends with nothing to approve is done, and the done card ends by itself after 2.5 s', () => {
    const r = rig()
    r.t.ingest(running({ pending: 1 }))
    r.at(4000)
    r.t.ingest(sig({ runs: [{ id: 'r_1', state: 'done' }], pending: 1 }))
    expect(r.take().map((e) => e.type)).toEqual(['run_started', 'run_done'])
    r.fire()
    expect(r.take()).toEqual([{ type: 'done_timer' }])
  })

  it('a run that leaves something to approve is done and then asks for the worker', () => {
    const r = rig()
    r.t.ingest(running({ pending: 1 }))
    r.at(4000)
    r.t.ingest(sig({ runs: [{ id: 'r_1', state: 'done' }], pending: 2 }))
    expect(r.take()).toEqual([{ type: 'run_started', realScreen: false }, { type: 'run_done', needsNothing: false }, { type: 'decision_needed', class: 'approval' }])
  })

  it('an approval raised in the middle of a run is a decision, not the end of the run', () => {
    const r = rig()
    r.t.ingest(running({ pending: 0 }))
    r.at(2000)
    r.t.ingest(running({ pending: 1 }))
    expect(r.take()).toEqual([{ type: 'run_started', realScreen: false }, { type: 'decision_needed', class: 'approval' }])
  })

  it('a failed run is a failure, and acknowledging it is heard', () => {
    const r = rig()
    r.t.ingest(running())
    r.at(2000)
    r.t.ingest(sig({ runs: [{ id: 'r_1', state: 'failed' }] }))
    expect(r.take().map((e) => e.type)).toEqual(['run_started', 'run_failed'])
    r.t.acknowledge()
    expect(r.take()).toEqual([{ type: 'error_acknowledged' }])
  })

  it('a quiet service sends nothing', () => {
    const r = rig()
    r.t.ingest(sig())
    r.t.ingest(sig({ reachable: false }))
    expect(r.take()).toEqual([])
  })

  it('adds up the children of the runs that are working', () => {
    expect(progressOf({ runs: [{ id: 'a', state: 'running', progress: { done: 1, total: 4 } }, { id: 'b', state: 'running', progress: { done: 2, total: 2 } }, { id: 'c', state: 'done', progress: { done: 9, total: 9 } }] })).toEqual({ n: 3, m: 6 })
    expect(progressOf({ runs: [{ id: 'a', state: 'running' }] })).toBeNull()
  })

  it('never says "n of m" when the total is one or unknown ("0 of 1" says nothing and goes stale): the words alone', () => {
    expect(progressOf({ runs: [{ id: 'a', state: 'running', progress: { done: 0, total: 1 } }] })).toBeNull()
    expect(progressOf({ runs: [{ id: 'a', state: 'running', progress: { done: 0, total: 0 } }] })).toBeNull()
    expect(progressOf({ runs: [{ id: 'a', state: 'running', progress: { done: 0, total: 2 } }] })).toEqual({ n: 0, m: 2 })
    expect(progressOf({ runs: [{ id: 'a', state: 'running', progress: { done: 5, total: 2 } }] })).toEqual({ n: 2, m: 2 }) // never more done than there are
  })
})

// The stale pill (owner, 8 Nov, bottom right: "working on ... 0 of 1" after the work finished). The agent service lists the runs it has on disk as well as the live ones, and a run
// that a dead process left mid-way keeps its last state ("planning", one child, none done) for ever. It must never keep the pill up.
describe('a record left behind by a dead process', () => {
  const DAY = 24 * 60 * 60_000
  const ghost = (now: number) => ({ id: 'r_ghost', state: 'planning', startedAt: now - 3 * DAY, progress: { done: 0, total: 1 } })

  it('is not a run: nothing starts, nothing is shown, however long it is listed', () => {
    const r = rig()
    r.at(10 * DAY)
    for (let i = 0; i < 5; i++) {
      r.at(10 * DAY + i * 2000)
      r.t.ingest(sig({ runs: [ghost(10 * DAY + i * 2000)] }))
    }
    expect(r.take()).toEqual([])
    expect(r.t.state().kind).toBe('idle')
  })

  it('the exact sequence: a real run with one child starts, ends, and the pill clears even though the old record is still listed as planning', () => {
    const r = rig()
    const T0 = 10 * DAY
    r.at(T0)
    r.t.ingest(sig({ supervisor: 'running', runs: [ghost(T0), { id: 'r_now', state: 'running', startedAt: T0 - 1000, progress: { done: 0, total: 1 } }] }))
    expect(r.take()).toEqual([{ type: 'run_started', realScreen: false }])
    r.at(T0 + 2000)
    r.t.ingest(sig({ supervisor: 'running', runs: [ghost(T0 + 2000), { id: 'r_now', state: 'running', startedAt: T0 - 1000, progress: { done: 0, total: 1 } }] }))
    expect(r.take()).toEqual([{ type: 'run_progress', label: 'Working on it' }]) // the words alone: no "0 of 1"
    r.at(T0 + 4000)
    r.t.ingest(sig({ supervisor: 'idle', runs: [ghost(T0 + 4000), { id: 'r_now', state: 'done', startedAt: T0 - 1000, progress: { done: 1, total: 1 } }] }))
    expect(r.take()).toEqual([{ type: 'run_done', needsNothing: true }])
    r.fire()
    expect(r.take()).toEqual([{ type: 'done_timer' }])
    r.at(T0 + 9000)
    r.t.ingest(sig({ runs: [ghost(T0 + 9000), { id: 'r_now', state: 'done', startedAt: T0 - 1000, progress: { done: 1, total: 1 } }] }))
    expect(r.take()).toEqual([]) // and it stays quiet: the old record does not start a new run
    expect(r.t.state().kind).toBe('idle')
  })

  it('a run that is older than any run can last ends by itself (the service caps a run at 15 minutes)', () => {
    const r = rig()
    const T0 = 10 * DAY
    r.at(T0)
    r.t.ingest(sig({ runs: [{ id: 'r_1', state: 'running', startedAt: T0 - 60_000 }] }))
    expect(r.take()).toEqual([{ type: 'run_started', realScreen: false }])
    r.at(T0 + 18 * 60_000)
    r.t.ingest(sig({ runs: [{ id: 'r_1', state: 'running', startedAt: T0 - 60_000 }] }))
    expect(r.take().map((e) => e.type)).toEqual(['run_done'])
  })
})

describe('the pill never outlives its work', () => {
  it('is quiet only when the service answers and nothing is acting: not running, not local, no live run', () => {
    const now = 1_000_000
    expect(isQuiet(sig(), now)).toBe(true)
    expect(isQuiet(sig({ reachable: false }), now)).toBe(false) // a silent service says nothing about the work
    expect(isQuiet(sig({ supervisor: 'running' }), now)).toBe(false)
    expect(isQuiet(sig({ local: true }), now)).toBe(false)
    expect(isQuiet(sig({ runs: [{ id: 'a', state: 'running', startedAt: now - 1000 }] }), now)).toBe(false)
    expect(isQuiet(sig({ runs: [{ id: 'a', state: 'running', startedAt: now - 3 * RUN_MAX_AGE_MS }] }), now)).toBe(true) // a ghost is not work
  })
  it('clears a pill from the service three seconds after it went quiet, whatever it last heard, and leaves the dev hook and an unquiet service alone', () => {
    const base = { fromService: true, machineWorking: true, quietSince: 1000 }
    expect(pillOutlivedWork({ ...base, now: 3999 })).toBe(false)
    expect(pillOutlivedWork({ ...base, now: 1000 + QUIET_CLEAR_MS })).toBe(true)
    expect(pillOutlivedWork({ ...base, now: 9000, quietSince: null })).toBe(false)
    expect(pillOutlivedWork({ ...base, now: 9000, fromService: false })).toBe(false)
    expect(pillOutlivedWork({ ...base, now: 9000, machineWorking: false })).toBe(false)
  })
})
