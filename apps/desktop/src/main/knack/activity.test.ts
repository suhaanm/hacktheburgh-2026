import { describe, expect, it } from 'vitest'
import { createActivityTracker, progressOf } from './activity'
import type { PillSignals } from './pill-state'
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
})
