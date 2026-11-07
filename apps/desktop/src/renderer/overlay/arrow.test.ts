import { describe, expect, it } from 'vitest'
import { DEFAULT_ANNOTATION_STYLE } from '../design/annotation-style'
import { arrowHeadPoints, arrowShaftPath, planArrow } from './arrow'
import { distance, inflate, overlapArea } from './geometry'

const vp = { width: 1728, height: 1117 }
const style = DEFAULT_ANNOTATION_STYLE.arrow
const base = { vp, style, pointHalf: 22 }

describe('planArrow', () => {
  it('stops `gap` short of the target and never covers it', () => {
    const plan = planArrow({ ...base, to: { xmin: 500, ymin: 400, xmax: 600, ymax: 480 } })
    const keepOut = inflate(plan.target, style.gap - 0.5)
    expect(overlapArea({ x: plan.tip.x - 0.1, y: plan.tip.y - 0.1, w: 0.2, h: 0.2 }, keepOut)).toBe(0)
    expect(distance(plan.start, plan.tip)).toBeGreaterThanOrEqual(style.minLength)
  })
  it('stays on screen for a target in each corner', () => {
    const corners = [
      { x: 20, y: 20 },
      { x: 980, y: 20 },
      { x: 20, y: 980 },
      { x: 980, y: 980 },
    ]
    for (const c of corners) {
      const plan = planArrow({ ...base, to: c })
      for (const p of [plan.start, plan.tip, ...plan.head]) {
        expect(p.x).toBeGreaterThanOrEqual(0)
        expect(p.x).toBeLessThanOrEqual(vp.width)
        expect(p.y).toBeGreaterThanOrEqual(0)
        expect(p.y).toBeLessThanOrEqual(vp.height)
      }
    }
  })
  it('honours an explicit `from`', () => {
    const plan = planArrow({ ...base, to: { x: 700, y: 700 }, from: { x: 300, y: 300 } })
    expect(plan.start.x).toBeCloseTo((300 / 1000) * vp.width, 0)
    expect(plan.start.y).toBeCloseTo((300 / 1000) * vp.height, 0)
    // The tip is on the near side of the target.
    expect(plan.tip.x).toBeLessThan(plan.target.x + plan.target.w / 2)
  })
  it('prefers a path that avoids another mark', () => {
    const target = { xmin: 480, ymin: 480, xmax: 560, ymax: 540 }
    const free = planArrow({ ...base, to: target })
    const blocker = { x: Math.min(free.start.x, free.tip.x), y: Math.min(free.start.y, free.tip.y), w: Math.abs(free.tip.x - free.start.x), h: Math.abs(free.tip.y - free.start.y) }
    const dodged = planArrow({ ...base, to: target, avoid: [blocker] })
    expect(dodged.start).not.toEqual(free.start)
  })
  it('falls back to automatic when `from` sits on top of the target', () => {
    const plan = planArrow({ ...base, to: { x: 500, y: 500 }, from: { x: 500, y: 500 } })
    expect(distance(plan.start, plan.tip)).toBeGreaterThanOrEqual(style.minLength)
  })
  it('emits well-formed SVG strings', () => {
    const plan = planArrow({ ...base, to: { x: 500, y: 500 } })
    expect(arrowShaftPath(plan)).toMatch(/^M [\d.]+ [\d.]+ Q [\d.]+ [\d.]+ [\d.]+ [\d.]+$/)
    expect(arrowHeadPoints(plan).split(' ')).toHaveLength(3)
  })
})
