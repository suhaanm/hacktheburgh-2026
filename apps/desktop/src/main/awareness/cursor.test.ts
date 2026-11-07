import { describe, expect, it } from 'vitest'
import { BURST_PX_S, createCursorSampler, createFakeClickSource, reduceCursorWindow, unknownClicks } from './cursor'
import { windowEvent } from './events'
import { manualTimers } from './awareness.test-util'
import type { CursorSample } from './types'

// 15 Hz samples over `ms`, positions from a function of time in ms.
function run(ms: number, at: (t: number) => { x: number; y: number }, hz = 15): CursorSample[] {
  const out: CursorSample[] = []
  for (let t = 0; t < ms; t += 1000 / hz) out.push({ t: Math.round(t), ...at(t) })
  return out
}
const opts = { windowS: 2 }

describe('dwell', () => {
  it('a cursor sitting still for the window is a dwell of about the window', () => {
    const f = reduceCursorWindow(run(2000, () => ({ x: 500, y: 400 })), opts)
    expect(f.dwell_s).toBeGreaterThanOrEqual(1.9)
    expect(f.dwell_s).toBeLessThanOrEqual(2)
    expect(f.wander).toBe(1)
    expect(f.back_forth).toBe(0)
    expect(f.idle_gap_s).toBeGreaterThanOrEqual(1.9)
    expect(f.dwell_anchor).toEqual({ bx: Math.floor(500 / 24), by: Math.floor(400 / 24) })
  })

  it('jitter inside a 24 px square still counts; a drift outside it does not', () => {
    const jitter = run(2000, (t) => ({ x: 300 + (Math.floor(t / 66) % 2) * 10, y: 300 + (Math.floor(t / 66) % 3) * 8 }))
    expect(reduceCursorWindow(jitter, opts).dwell_s).toBeGreaterThanOrEqual(1.9)
    const drift = run(2000, (t) => ({ x: 300 + t * 0.1, y: 300 })) // 200 px over the window
    expect(reduceCursorWindow(drift, opts).dwell_s).toBe(0)
  })

  it('a stay under 1.2 s is not a dwell', () => {
    // 1.0 s still, then a long move
    const s = run(2000, (t) => (t < 1000 ? { x: 100, y: 100 } : { x: 100 + (t - 1000) * 0.8, y: 100 }))
    expect(reduceCursorWindow(s, opts).dwell_s).toBe(0)
  })

  it('a click in the middle splits a dwell, so neither half reaches 1.2 s', () => {
    const s = run(2000, () => ({ x: 640, y: 360 }))
    expect(reduceCursorWindow(s, { windowS: 2, clickTimes: [1000] }).dwell_s).toBe(0)
    expect(reduceCursorWindow(s, { windowS: 2, clickTimes: [] }).dwell_s).toBeGreaterThan(1.8)
    expect(reduceCursorWindow(s, { windowS: 2, clickTimes: [1000] }).clicks).toBe(1)
  })

  it('without a click source, clicks are unknown (null), never zero', () => {
    expect(reduceCursorWindow(run(2000, () => ({ x: 1, y: 1 })), opts).clicks).toBeNull()
    expect(reduceCursorWindow(run(2000, () => ({ x: 1, y: 1 })), { windowS: 2, clickTimes: [] }).clicks).toBe(0)
  })

  it('reports the dwell zone from the resolver, and drops a zone that is not in the vocabulary pattern', () => {
    const s = run(2000, () => ({ x: 500, y: 400 }))
    expect(reduceCursorWindow(s, { windowS: 2, zoneAt: () => 'cliff_button' }).dwell_zone).toBe('cliff_button')
    expect(reduceCursorWindow(s, { windowS: 2, zoneAt: () => 'Not A Zone!' }).dwell_zone).toBeNull()
    expect(reduceCursorWindow(s, { windowS: 2, zoneAt: () => null }).dwell_zone).toBeNull()
  })
})

describe('wander and back-and-forth', () => {
  it('a straight path has wander near 1 and no reversals', () => {
    const f = reduceCursorWindow(run(2000, (t) => ({ x: 100 + t * 0.4, y: 300 })), opts)
    expect(f.wander).toBeCloseTo(1, 1)
    expect(f.back_forth).toBe(0)
  })

  it('circling returns to the start: displacement is floored so wander is large but capped', () => {
    const f = reduceCursorWindow(run(2000, (t) => ({ x: 400 + 150 * Math.cos((t / 2000) * 2 * Math.PI * 2), y: 400 + 150 * Math.sin((t / 2000) * 2 * Math.PI * 2) })), opts)
    expect(f.wander).toBeGreaterThan(5)
    expect(f.wander).toBeLessThanOrEqual(20)
  })

  it('A, B, A, B across 400 px is three legs and two reversals', () => {
    // 0 -> 400 -> 0 -> 400 px in 2 s
    const tri = (t: number): number => {
      const p = (t / 2000) * 3
      const k = Math.floor(p)
      const f = p - k
      return k % 2 === 0 ? f * 400 : (1 - f) * 400
    }
    const f = reduceCursorWindow(run(1990, (t) => ({ x: 200 + tri(t), y: 300 })), opts)
    expect(f.back_forth).toBe(2)
  })

  it('small shakes under 140 px are not back-and-forth', () => {
    const f = reduceCursorWindow(run(2000, (t) => ({ x: 300 + 60 * Math.sin(t / 80), y: 300 })), opts)
    expect(f.back_forth).toBe(0)
  })

  it('with zones, A B A B counts and names the pair (sorted)', () => {
    const zoneAt = (x: number): string => (x < 600 ? 'results_tabs' : 'case_note')
    const tri = (t: number): number => (Math.floor(t / 500) % 2 === 0 ? 300 : 900)
    const f = reduceCursorWindow(run(2000, (t) => ({ x: tri(t), y: 300 })), { windowS: 2, zoneAt })
    expect(f.back_forth).toBeGreaterThanOrEqual(2)
    expect([f.zone_a, f.zone_b]).toEqual(['case_note', 'results_tabs'])
  })
})

describe('speed bursts and idle gap', () => {
  it('a fast flick is one burst; a slow move is none', () => {
    const slow = reduceCursorWindow(run(2000, (t) => ({ x: 100 + t * 0.3, y: 100 })), opts)
    expect(slow.speed_bursts).toBe(0)
    // 1 s still, a 600 px flick in ~130 ms, still again
    const flick = run(2000, (t) => ({ x: t < 1000 ? 100 : t < 1130 ? 100 + ((t - 1000) / 130) * 600 : 700, y: 100 }))
    const f = reduceCursorWindow(flick, opts)
    expect(f.speed_bursts).toBe(1)
    expect(600 / 0.13).toBeGreaterThan(BURST_PX_S)
  })

  it('idle gap is the longest stretch without moving', () => {
    const s = run(2000, (t) => ({ x: t < 1200 ? 100 : 100 + (t - 1200) * 0.5, y: 100 }))
    const f = reduceCursorWindow(s, opts)
    expect(f.idle_gap_s).toBeGreaterThan(1.1)
    expect(f.idle_gap_s).toBeLessThan(1.4)
  })
})

describe('robustness', () => {
  it('empty and single-sample windows are empty features; NaN samples are ignored', () => {
    expect(reduceCursorWindow([], opts).dwell_s).toBe(0)
    expect(reduceCursorWindow([{ t: 0, x: 1, y: 1 }], opts).wander).toBe(1)
    const s = [...run(2000, () => ({ x: 5, y: 5 })), { t: 2100, x: NaN, y: 3 }]
    expect(reduceCursorWindow(s, opts).dwell_s).toBeGreaterThan(1.8)
  })

  it('features and the wire event carry no coordinates', () => {
    const f = reduceCursorWindow(run(2000, (t) => ({ x: 123 + t * 0.2, y: 456 })), opts)
    const ev = windowEvent({ person: 'p_demo01', role: 'benefits-processor' }, f, { t: new Date(0), appKind: 'browser', sysIdleS: 0.4 })
    const text = JSON.stringify(ev)
    expect(text).not.toMatch(/"(x|y|bx|by|dwell_anchor)"/)
    expect(ev.cursor).not.toHaveProperty('dwell_anchor')
  })
})

describe('the sampler', () => {
  it('creates no timer until started, samples at 15 Hz, closes a window every 2 s, and drops coordinates on stop', () => {
    const timers = manualTimers()
    let t = 0
    const windows: number[] = []
    const sampler = createCursorSampler({ getPoint: () => ({ x: 10 + t / 100, y: 10 }), now: () => t, timers, onWindow: (f) => windows.push(f.dwell_s) })
    expect(timers.created()).toBe(0)
    sampler.start()
    expect(timers.intervals()).toEqual([67]) // 1000 / 15, rounded
    for (let i = 0; i < 100; i++) {
      t += 67
      timers.advance(67)
    }
    expect(windows.length).toBeGreaterThanOrEqual(3) // 6.7 s of samples
    sampler.stop()
    expect(timers.active()).toBe(0)
    expect(sampler.running()).toBe(false)
  })

  it('a getPoint that throws is skipped; clicks are unknown by default', () => {
    const timers = manualTimers()
    let t = 0
    let boom = true
    const seen: Array<number | null> = []
    const sampler = createCursorSampler({
      getPoint: () => {
        if (boom) throw new Error('x')
        return { x: 1, y: 1 }
      },
      now: () => t,
      timers,
      clicks: unknownClicks,
      onWindow: (f) => seen.push(f.clicks),
    })
    sampler.start()
    for (let i = 0; i < 40; i++) {
      t += 67
      timers.advance(67)
    }
    expect(seen).toEqual([]) // nothing was sampled
    boom = false
    for (let i = 0; i < 60; i++) {
      t += 67
      timers.advance(67)
    }
    expect(seen.length).toBeGreaterThan(0)
    expect(seen.every((c) => c === null)).toBe(true)
  })

  it('a fake click source (the interface a real one would implement) splits a dwell and fills the click count', () => {
    const timers = manualTimers()
    let t = 0
    const clicks = createFakeClickSource()
    const seen: Array<{ dwell: number; clicks: number | null }> = []
    const sampler = createCursorSampler({ getPoint: () => ({ x: 300, y: 300 }), now: () => t, timers, clicks, onWindow: (f) => seen.push({ dwell: f.dwell_s, clicks: f.clicks }) })
    sampler.start()
    for (let i = 0; i < 70; i++) {
      t += 67
      if (i === 15) clicks.click(t) // roughly mid first window
      timers.advance(67)
    }
    expect(seen.length).toBeGreaterThanOrEqual(2)
    expect(seen[0]).toEqual({ dwell: 0, clicks: 1 }) // the click cut the dwell in two halves under 1.2 s
    expect(seen[1].clicks).toBe(0)
    expect(seen[1].dwell).toBeGreaterThan(1.8)
  })

  it('a consumer that throws does not stop sampling', () => {
    const timers = manualTimers()
    let t = 0
    let n = 0
    const sampler = createCursorSampler({
      getPoint: () => ({ x: 1, y: 1 }),
      now: () => t,
      timers,
      onWindow: () => {
        n++
        throw new Error('consumer')
      },
    })
    sampler.start()
    for (let i = 0; i < 120; i++) {
      t += 67
      timers.advance(67)
    }
    expect(n).toBeGreaterThanOrEqual(3)
  })
})
