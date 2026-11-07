import { describe, expect, it } from 'vitest'
import { createStuckReader, parseStuckReading } from './stuck-reader'
import { manualTimers } from './awareness.test-util'

const decision = (over: Record<string, unknown> = {}) => ({ meta: {}, data: { action: 'silent', p_stuck: 0.74, p_source: 'hazard', reason_codes: ['gate_wait_signals'], ...over } })

describe('parseStuckReading', () => {
  it('reads p_stuck and its source from the envelope or a bare body', () => {
    expect(parseStuckReading(decision())).toEqual({ p: 0.74, source: 'hazard' })
    expect(parseStuckReading(decision({ p_source: 'heuristic' }))).toEqual({ p: 0.74, source: 'heuristic' })
    expect(parseStuckReading({ p_stuck: 0.2, p_source: 'weird' })).toEqual({ p: 0.2, source: 'heuristic' })
  })

  it('is no reading when there is no episode, or the value is absent or out of range', () => {
    for (const code of ['no_events', 'no_pack', 'no_active_task', 'study_mode', 'study_post_test', 'study_off']) expect(parseStuckReading(decision({ reason_codes: [code] }))).toBeNull()
    for (const v of [null, undefined, 'x', -0.1, 1.2, NaN]) expect(parseStuckReading(decision({ p_stuck: v }))).toBeNull()
    expect(parseStuckReading(null)).toBeNull()
    expect(parseStuckReading('x')).toBeNull()
  })
})

describe('the reader', () => {
  it('asks GET /coach/next with dry=1 (changes nothing in the engine) for this person, every three seconds, only while started', async () => {
    const timers = manualTimers()
    const urls: string[] = []
    const readings: Array<number | null> = []
    const r = createStuckReader({
      engineUrl: 'http://127.0.0.1:7700',
      person: () => 'p_demo01',
      getJson: async (u) => (urls.push(u), decision()),
      onReading: (x) => readings.push(x ? x.p : null),
      timers,
    })
    expect(timers.created()).toBe(0)
    r.start()
    expect(timers.intervals()).toEqual([3000])
    timers.advance(3000)
    await new Promise((res) => setTimeout(res, 0))
    expect(urls).toEqual(['http://127.0.0.1:7700/coach/next?person=p_demo01&dry=1'])
    expect(readings).toEqual([0.74])
    r.stop()
    expect(timers.active()).toBe(0)
  })

  it('an unreachable engine or a throwing fetch is a null reading, which breaks a stuck chain', async () => {
    const readings: Array<number | null> = []
    let mode: 'down' | 'throw' = 'down'
    const r = createStuckReader({
      engineUrl: 'http://127.0.0.1:7700',
      person: () => 'p_demo01',
      getJson: async () => {
        if (mode === 'throw') throw new Error('x')
        return null
      },
      onReading: (x) => readings.push(x ? x.p : null),
    })
    await r.tick()
    mode = 'throw'
    await r.tick()
    expect(readings).toEqual([null, null])
  })

  it('does not overlap ticks', async () => {
    let inflight = 0
    let max = 0
    let release!: () => void
    const gate = new Promise<void>((res) => (release = res))
    const r = createStuckReader({
      engineUrl: 'http://127.0.0.1:7700',
      person: () => 'p_demo01',
      getJson: async () => {
        inflight++
        max = Math.max(max, inflight)
        await gate
        inflight--
        return decision()
      },
      onReading: () => undefined,
    })
    const a = r.tick()
    const b = r.tick()
    release()
    await Promise.all([a, b])
    expect(max).toBe(1)
  })
})
