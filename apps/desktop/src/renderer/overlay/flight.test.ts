import { describe, expect, it } from 'vitest'
import { DEFAULT_ANNOTATION_STYLE } from '../design/annotation-style'
import { bezierAt, leanDeg, parseEasing, planFlight, sampleFlight, smoothstep, tangentAt } from './flight'

const style = DEFAULT_ANNOTATION_STYLE.ghostCursor.flight
const ease = parseEasing(style.easing)

describe('parseEasing', () => {
  it('hits 0 and 1 and is monotonic for the DESIGN curve', () => {
    expect(ease(0)).toBe(0)
    expect(ease(1)).toBe(1)
    let prev = 0
    for (let i = 1; i <= 20; i++) {
      const v = ease(i / 20)
      expect(v).toBeGreaterThanOrEqual(prev)
      prev = v
    }
  })
  it('falls back to smoothstep for non-bezier strings', () => {
    expect(parseEasing('ease-in-out')(0.5)).toBeCloseTo(smoothstep(0.5))
  })
  it('linear bezier is identity', () => {
    expect(parseEasing('cubic-bezier(0,0,1,1)')(0.37)).toBeCloseTo(0.37, 3)
  })
})

describe('planFlight', () => {
  it('clamps duration to min/max and arcs upward', () => {
    const short = planFlight([{ x: 0, y: 0 }, { x: 10, y: 0 }], style)
    expect(short.segments[0].durationMs).toBe(style.minMs)
    const long = planFlight([{ x: 0, y: 0 }, { x: 5000, y: 0 }], style)
    expect(long.segments[0].durationMs).toBe(style.maxMs)
    expect(long.segments[0].control.y).toBeLessThan(0)
  })
  it('a single point flies in from the hint', () => {
    const plan = planFlight([{ x: 500, y: 400 }], style, { startHint: { x: 100, y: 100 } })
    expect(plan.segments).toHaveLength(1)
    expect(plan.segments[0].from).toEqual({ x: 100, y: 100 })
    expect(plan.end).toEqual({ x: 500, y: 400 })
  })
  it('a single point without a hint starts on screen', () => {
    const plan = planFlight([{ x: 30, y: 30 }], style, { viewport: { width: 800, height: 600 } })
    const from = plan.segments[0].from
    expect(from.x).toBeGreaterThanOrEqual(24)
    expect(from.y).toBeLessThanOrEqual(576)
  })
  it('multi-point holds at waypoints and longer at the end', () => {
    const plan = planFlight([{ x: 0, y: 0 }, { x: 300, y: 0 }, { x: 300, y: 300 }], style)
    expect(plan.segments).toHaveLength(2)
    expect(plan.segments[0].holdMs).toBeLessThan(plan.segments[1].holdMs)
    expect(plan.totalMs).toBe(plan.segments.reduce((s, x) => s + x.durationMs + x.holdMs, 0))
  })
})

describe('sampleFlight', () => {
  const plan = planFlight([{ x: 0, y: 0 }, { x: 800, y: 400 }], style)
  it('starts at the first point and ends at the last', () => {
    expect(sampleFlight(plan, 0, ease).pos).toEqual({ x: 0, y: 0 })
    const end = sampleFlight(plan, plan.totalMs + 1, ease)
    expect(end.phase).toBe('done')
    expect(end.pos).toEqual({ x: 800, y: 400 })
  })
  it('swoops (scale > 1) mid-flight and rests at 1 while holding', () => {
    const mid = sampleFlight(plan, plan.segments[0].durationMs / 2, ease)
    expect(mid.phase).toBe('flying')
    expect(mid.scale).toBeGreaterThan(1.2)
    const hold = sampleFlight(plan, plan.segments[0].durationMs + 10, ease)
    expect(hold.phase).toBe('holding')
    expect(hold.scale).toBe(1)
  })
  it('heading follows the tangent (rightwards-down for this path)', () => {
    const s = sampleFlight(plan, plan.segments[0].durationMs * 0.9, ease)
    expect(s.headingDeg).toBeGreaterThan(0)
    expect(s.headingDeg).toBeLessThan(90)
  })
  it('only the final hold shows the press echo, and only when asked', () => {
    const dur = plan.segments[0].durationMs
    expect(sampleFlight(plan, dur + 300, ease, 0).press).toBeNull()
    expect(sampleFlight(plan, dur + 60, ease, 700).press).toBeNull()
    const p = sampleFlight(plan, dur + 120 + 350, ease, 700).press
    expect(p).toBeCloseTo(0.5, 1)
  })
  it('bezier endpoints and tangent are consistent', () => {
    const seg = plan.segments[0]
    expect(bezierAt(seg, 0)).toEqual(seg.from)
    expect(bezierAt(seg, 1)).toEqual(seg.to)
    expect(tangentAt(seg, 1).x).toBeGreaterThan(0)
  })
})

describe('leanDeg', () => {
  it('is bounded', () => {
    for (let h = -180; h <= 180; h += 15) expect(Math.abs(leanDeg(h))).toBeLessThanOrEqual(16)
  })
})
