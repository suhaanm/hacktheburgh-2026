import { describe, expect, it } from 'vitest'
import { createPillController } from './pill-controller'
import { IDLE_PILL, PILL_TEXTS, PILL_TIMING, acknowledge, endOf, pillView, stepPill, type PillSignals, type PillState } from './pill-state'

const sig = (over: Partial<PillSignals> = {}): PillSignals => ({ reachable: true, supervisor: 'idle', runs: [], killed: false, pending: 0, ...over })
const running = (over: Partial<PillSignals> = {}): PillSignals => sig({ supervisor: 'running', runs: [{ id: 'r_1', state: 'running' }], ...over })
const ended = (state: string, over: Partial<PillSignals> = {}): PillSignals => sig({ runs: [{ id: 'r_1', state }], ...over })

/** Feeds a list of [signals, ms since start] into the machine and returns the final state and every kind seen. */
function play(steps: [PillSignals, number][], from: PillState = IDLE_PILL): { final: PillState; kinds: string[] } {
  let p = from
  const kinds: string[] = []
  for (const [s, t] of steps) {
    p = stepPill(p, s, t)
    if (kinds.at(-1) !== p.kind) kinds.push(p.kind)
  }
  return { final: p, kinds }
}

describe('the words', () => {
  it('come from a closed list of at most five words each', () => {
    for (const t of PILL_TEXTS) expect(t.split(/\s+/).length).toBeLessThanOrEqual(5)
    const seen = new Set<string>()
    for (const s of [IDLE_PILL, stepPill(IDLE_PILL, running(), 0), stepPill(IDLE_PILL, sig({ killed: true }), 0)]) seen.add(s.text)
    expect([...seen].every((t) => t === '' || (PILL_TEXTS as readonly string[]).includes(t))).toBe(true)
  })
})

describe('a run that ends with nothing to approve', () => {
  it('goes idle, working, done, idle, and never asks for the worker', () => {
    const { kinds, final } = play([
      [sig(), 0],
      [running({ pending: 2 }), 1000],
      [running({ pending: 2 }), 3000],
      [ended('done', { pending: 2 }), 5000],
      [ended('done', { pending: 2 }), 8000],
      [ended('done', { pending: 2 }), 5000 + PILL_TIMING.doneMs + 10],
    ])
    expect(kinds).toEqual(['idle', 'working', 'done', 'idle'])
    expect(final.kind).toBe('idle')
  })
  it('says Working on it, then Still working after a while', () => {
    const a = stepPill(IDLE_PILL, running(), 0)
    expect(a.text).toBe('Working on it')
    const b = stepPill(a, running(), PILL_TIMING.stillWorkingMs + 1)
    expect(b).toMatchObject({ kind: 'working', text: 'Still working' })
  })
})

describe('a run that leaves something to approve', () => {
  it('asks for the worker once the run ends with a new item in the queue, and stays until it is dealt with', () => {
    const { kinds, final } = play([
      [running({ pending: 1 }), 0],
      [ended('done', { pending: 2 }), 4000],
      [ended('done', { pending: 2 }), 60_000],
      [ended('done', { pending: 2 }), 600_000],
    ])
    expect(kinds).toEqual(['working', 'needs-you'])
    expect(final).toMatchObject({ kind: 'needs-you', text: 'Needs your OK' })
    // The worker approves it: the queue is back to what it was, and the pill goes away.
    expect(stepPill(final, sig({ pending: 1 }), 700_000).kind).toBe('idle')
  })
  it('asks at once when an approval is raised in the middle of a run, and goes back to working when it is answered', () => {
    const w = stepPill(IDLE_PILL, running({ pending: 0 }), 0)
    const n = stepPill(w, running({ pending: 1 }), 2000)
    expect(n.kind).toBe('needs-you')
    expect(stepPill(n, running({ pending: 0 }), 5000).kind).toBe('working')
  })
  it('asks for the worker when a run pauses itself, and only opening Knack clears that', () => {
    let p = stepPill(IDLE_PILL, running({ pending: 0 }), 0)
    p = stepPill(p, ended('paused', { pending: 0 }), 3000)
    expect(p.kind).toBe('needs-you')
    expect(stepPill(p, sig({ pending: 0 }), 9000).kind).toBe('needs-you')
    expect(acknowledge(p, 9500).kind).toBe('idle')
  })
  it('cannot tell from an unknown queue count, so it says done rather than guess', () => {
    const { final } = play([[running({ pending: null }), 0], [ended('done', { pending: null }), 4000]])
    expect(final.kind).toBe('done')
  })
})

describe('errors and the kill switch', () => {
  it('shows an error for a failed, timed-out or rejected run, until it times out or Knack is opened', () => {
    for (const st of ['failed', 'timeout', 'rejected']) {
      const e = play([[running(), 0], [ended(st), 3000]]).final
      expect(e, st).toMatchObject({ kind: 'error', text: 'Something went wrong' })
      expect(stepPill(e, sig(), 3000 + PILL_TIMING.errorMs + 1).kind).toBe('idle')
      expect(acknowledge(e, 4000).kind).toBe('idle')
    }
  })
  it('reads the supervisor too (the benefits run has no run list)', () => {
    expect(play([[sig({ supervisor: 'running' }), 0], [sig({ supervisor: 'failed' }), 2000]]).final.kind).toBe('error')
    expect(play([[sig({ supervisor: 'running' }), 0], [sig({ supervisor: 'idle' }), 2000]]).final.kind).toBe('done')
  })
  it('a run the worker stopped or interrupted leaves no card', () => {
    expect(play([[running(), 0], [ended('stopped'), 2000]]).final.kind).toBe('idle')
    expect(play([[running(), 0], [ended('yielded'), 2000]]).final.kind).toBe('idle')
    expect(play([[sig({ supervisor: 'running' }), 0], [sig({ supervisor: 'stopped' }), 2000]]).final.kind).toBe('idle')
  })
  it('the kill switch wins over everything, shows Stopped, and clearing it goes quiet, not back to working', () => {
    let p = stepPill(IDLE_PILL, running(), 0)
    p = stepPill(p, running({ killed: true }), 1000)
    expect(p).toMatchObject({ kind: 'killed', text: 'Stopped' })
    p = stepPill(p, sig({ killed: true }), 2000)
    expect(p.kind).toBe('killed')
    p = stepPill(p, sig({ killed: false }), 3000)
    expect(p.kind).toBe('idle')
  })
  it('a run ending with the supervisor killed is shown as Stopped', () => {
    expect(play([[running(), 0], [ended('killed', { supervisor: 'killed' }), 2000]]).final.kind).toBe('killed')
  })
})

describe('an agent service that stops answering', () => {
  it('never turns a quiet pill on, never turns a showing pill off on one failed look, and calls a long silence during a run an error', () => {
    const quiet = stepPill(IDLE_PILL, sig({ reachable: false }), 0)
    expect(quiet.kind).toBe('idle')
    let p = stepPill(IDLE_PILL, running(), 0)
    p = stepPill(p, sig({ reachable: false }), 2000)
    expect(p.kind).toBe('working')
    p = stepPill(p, running(), 4000) // it answers again: the silence is forgotten
    expect(p.lostSince).toBeNull()
    p = stepPill(p, sig({ reachable: false }), 6000)
    p = stepPill(p, sig({ reachable: false }), 6000 + PILL_TIMING.lostMs + 1)
    expect(p).toMatchObject({ kind: 'error', text: 'Lost contact' })
  })
})

describe('a new run after something else', () => {
  it('starts again from done, error and killed with a fresh baseline', () => {
    let p = play([[running({ pending: 1 }), 0], [ended('done', { pending: 1 }), 3000]]).final
    expect(p.kind).toBe('done')
    p = stepPill(p, running({ pending: 5 }), 4000)
    expect(p).toMatchObject({ kind: 'working', baseline: 5 })
  })
})

describe('the view', () => {
  it('draws nothing when idle, a Stop button only while working, and lets the label open Knack in every state', () => {
    expect(pillView(IDLE_PILL)).toMatchObject({ kind: 'idle', stop: false, open: false })
    const w = stepPill(IDLE_PILL, running(), 0)
    expect(pillView(w)).toEqual({ kind: 'working', text: 'Working on it', stop: true, open: true })
    expect(pillView(stepPill(w, sig({ killed: true }), 1))).toMatchObject({ kind: 'killed', stop: false, open: true })
  })
  it('endOf is deterministic', () => {
    expect(endOf({ a: 'running' }, { a: 'done' }, 'idle', false)).toBe('done')
    expect(endOf({ a: 'running' }, { a: 'partial' }, 'idle', true)).toBe('needs')
    expect(endOf({ a: 'running' }, { a: 'failed' }, 'idle', true)).toBe('error')
  })
})

describe('the controller', () => {
  function rig() {
    let now = 0
    const timers: { fn: () => void; at: number }[] = []
    const seen: string[] = []
    const c = createPillController({ now: () => now, setTimer: (fn, ms) => (timers.push({ fn, at: now + ms }), timers.length), clearTimer: () => undefined })
    c.subscribe((s, prev) => seen.push(`${prev.kind}>${s.kind}`))
    return { c, seen, at: (t: number) => (now = t), fire: () => { const t = timers.at(-1)!; now = Math.max(now, t.at); t.fn() } }
  }
  it('reports each change once and ends a done card by itself after its time', () => {
    const r = rig()
    r.c.ingest(running())
    r.at(1000)
    r.c.ingest(running())
    r.at(2000)
    r.c.ingest(ended('done'))
    expect(r.c.state().kind).toBe('done')
    r.fire()
    expect(r.c.state().kind).toBe('idle')
    expect(r.seen).toEqual(['idle>working', 'working>done', 'done>idle'])
  })
  it('opening Knack acknowledges a card; it never ends a working run', () => {
    const r = rig()
    r.c.ingest(running())
    r.c.acknowledge()
    expect(r.c.state().kind).toBe('working')
    r.c.ingest(ended('failed'))
    expect(r.c.state().kind).toBe('error')
    r.c.acknowledge()
    expect(r.c.state().kind).toBe('idle')
  })
})
