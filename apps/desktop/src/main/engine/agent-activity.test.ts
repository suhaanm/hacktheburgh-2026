import { describe, expect, it, vi } from 'vitest'
import { actingFrom, createAgentActivity } from './agent-activity'

const json = (body: unknown, ok = true) => ({ ok, json: async () => body }) as Response

describe('actingFrom: what the agent service says', () => {
  it('acting when the supervisor runs, or any listed run runs', () => {
    expect(actingFrom({ supervisor: { state: 'running' } }, null)).toBe(true)
    expect(actingFrom({ supervisor: { state: 'idle' } }, null)).toBe(false)
    expect(actingFrom({ supervisor: { state: 'idle' } }, [{ state: 'done' }, { state: 'running' }])).toBe(true)
    expect(actingFrom(null, { data: [{ state: 'running' }] })).toBe(true)
    for (const state of ['queued', 'stopped', 'killed', 'failed']) expect(actingFrom({ supervisor: { state } }, [])).toBe(false)
  })
  it('cannot tell from nothing or junk', () => {
    expect(actingFrom(null, null)).toBeNull()
    expect(actingFrom({ ok: true }, 'x')).toBeNull()
  })
})

describe('the agent activity poller', () => {
  function setup(answer: (path: string) => Response | Error) {
    const changes: boolean[] = []
    const timers: { fn: () => void; ms: number }[] = []
    const fetchImpl = vi.fn(async (url: string | URL | Request) => {
      const r = answer(new URL(String(url)).pathname)
      if (r instanceof Error) throw r
      return r
    }) as unknown as typeof fetch
    let idle = 0
    const a = createAgentActivity({ agentUrl: 'http://127.0.0.1:7710', fetchImpl, onChange: (v) => changes.push(v), idleSeconds: () => idle, setTimer: (fn, ms) => (timers.push({ fn, ms }), timers.length), clearTimer: () => undefined })
    return { a, changes, fetchImpl, timers, setIdle: (n: number) => (idle = n) }
  }

  it('turns on when a run starts and off when it ends, reporting only changes', async () => {
    let state = 'idle'
    const { a, changes } = setup((p) => (p === '/health' ? json({ supervisor: { state } }) : json({}, false)))
    await a.poll()
    expect(a.acting()).toBe(false)
    state = 'running'
    await a.poll()
    await a.poll()
    expect(a.acting()).toBe(true)
    state = 'idle'
    await a.poll()
    expect(changes).toEqual([true, false])
  })

  it('a poll that fails never turns the pill on, and never turns a showing pill off', async () => {
    let down = false
    const { a, changes } = setup((p) => (down ? new Error('down') : p === '/health' ? json({ supervisor: { state: 'running' } }) : json({}, false)))
    await a.poll()
    expect(a.acting()).toBe(true)
    down = true
    await a.poll()
    expect(a.acting()).toBe(true) // still showing
    expect(changes).toEqual([true])
    const cold = setup(() => new Error('down'))
    await cold.a.poll()
    expect(cold.a.acting()).toBe(false)
    expect(cold.changes).toEqual([])
  })

  it('polls every 2 s while the person is at the machine or something acts, and every 10 s when it is quiet', async () => {
    const { a, timers, setIdle } = setup((p) => (p === '/health' ? json({ supervisor: { state: 'idle' } }) : json({}, false)))
    await a.poll()
    await Promise.resolve()
    await new Promise((r) => setTimeout(r, 0))
    expect(timers.at(-1)?.ms).toBe(2000) // at the machine
    setIdle(600)
    timers.at(-1)!.fn()
    await new Promise((r) => setTimeout(r, 0))
    expect(timers.at(-1)?.ms).toBe(10_000) // away and nothing acting
    a.dispose()
  })

  it('only ever asks a loopback address', async () => {
    const fetchImpl = vi.fn() as unknown as typeof fetch
    const a = createAgentActivity({ agentUrl: 'http://example.com:7710', fetchImpl, onChange: () => undefined, setTimer: () => 0, clearTimer: () => undefined })
    await a.poll()
    expect(fetchImpl).not.toHaveBeenCalled()
  })
})

describe('the raw samples (the Knack pill reads them)', () => {
  it('hands every poll to onSample with the parsed answers, and null for a call that failed', async () => {
    const samples: { health: unknown; runs: unknown }[] = []
    const fetchImpl = vi.fn(async (url: string | URL | Request) => (new URL(String(url)).pathname === '/health' ? json({ supervisor: { state: 'running' } }) : json({}, false))) as unknown as typeof fetch
    const a = createAgentActivity({ agentUrl: 'http://127.0.0.1:7710', fetchImpl, onChange: () => undefined, onSample: (s) => samples.push(s), setTimer: () => 0, clearTimer: () => undefined })
    await a.poll()
    await a.poll()
    expect(samples.slice(-2)).toEqual([
      { health: { supervisor: { state: 'running' } }, runs: null },
      { health: { supervisor: { state: 'running' } }, runs: null },
    ])
    a.dispose()
  })
})
