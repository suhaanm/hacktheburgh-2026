import { describe, expect, it } from 'vitest'
import type { Annotation } from '../../shared/protocol'
import { annotationStyle } from '../design/annotation-style'
import { overlapArea, type Rect } from './geometry'
import { chooseCaptionRect, labelKey, planScene } from './scene-plan'
import type { ActiveAnnotation } from './store'

const vp = { width: 1728, height: 1117 }
const style = annotationStyle({ bigAnnotations: false, highContrast: false })
const entry = (annotation: Annotation): ActiveAnnotation => ({ annotation, shownAt: 0, expiresAt: null, exitingAt: null })
const box = { xmin: 400, ymin: 600, xmax: 480, ymax: 680 }

describe('planScene', () => {
  it('ring rect surrounds its box with padding, and a step badge sits on its top-left corner', () => {
    const plan = planScene([entry({ id: 'r', kind: 'ring', tone: 'guide', box, step: 2 })], vp, style, {})
    const ring = plan.rings.get('r')!
    expect(ring.rect.x).toBeLessThan((400 / 1000) * vp.width)
    expect(ring.rect.w).toBeGreaterThan(((480 - 400) / 1000) * vp.width)
    expect(ring.step!.x).toBeLessThan(ring.rect.x + style.badge.diameter)
  })
  it('tiny targets get a ring of at least minSize', () => {
    const plan = planScene([entry({ id: 'r', kind: 'ring', tone: 'guide', box: { xmin: 500, ymin: 500, xmax: 501, ymax: 501 } })], vp, style, {})
    expect(plan.rings.get('r')!.rect.w).toBeGreaterThanOrEqual(style.ring.minSize)
  })
  it('an arrow stops short of the ring around the same target', () => {
    const plan = planScene(
      [entry({ id: 'r', kind: 'ring', tone: 'guide', box }), entry({ id: 'a', kind: 'arrow', tone: 'guide', to: box })],
      vp,
      style,
      {},
    )
    const ring = plan.rings.get('r')!.rect
    const tip = plan.arrows.get('a')!.tip
    const inside = tip.x > ring.x && tip.x < ring.x + ring.w && tip.y > ring.y && tip.y < ring.y + ring.h
    expect(inside).toBe(false)
  })
  it('ring labels avoid other rings and stay on screen', () => {
    const entries = [
      entry({ id: 'r1', kind: 'ring', tone: 'guide', box, label: 'Mute' }),
      entry({ id: 'r2', kind: 'ring', tone: 'guide', box: { xmin: 500, ymin: 600, xmax: 580, ymax: 680 }, label: 'Camera' }),
    ]
    const plan = planScene(entries, vp, style, {})
    const rings: Rect[] = [plan.rings.get('r1')!.rect, plan.rings.get('r2')!.rect]
    for (const id of ['r1', 'r2']) {
      const p = plan.labels.get(labelKey(id, 'label'))!
      expect(p.rect.x).toBeGreaterThanOrEqual(0)
      expect(p.rect.x + p.rect.w).toBeLessThanOrEqual(vp.width)
      for (const r of rings) expect(overlapArea(p.rect, r)).toBe(0)
    }
    const a = plan.labels.get(labelKey('r1', 'label'))!.rect
    const b = plan.labels.get(labelKey('r2', 'label'))!.rect
    expect(overlapArea(a, b)).toBe(0)
  })
  it('a bubble near the top-right corner is placed inside the viewport', () => {
    const plan = planScene([entry({ id: 'b', kind: 'bubble', tone: 'guide', at: { x: 990, y: 10 }, text: 'Over here, please' })], vp, style, {})
    const p = plan.labels.get(labelKey('b', 'bubble'))!
    expect(p.rect.x + p.rect.w).toBeLessThanOrEqual(vp.width)
    expect(p.rect.y).toBeGreaterThanOrEqual(0)
  })
  it('highlightText note is anchored to the first box; ticks stay on screen at the top-right', () => {
    const plan = planScene(
      [
        entry({ id: 'h', kind: 'highlightText', tone: 'danger', boxes: [{ xmin: 600, ymin: 300, xmax: 900, ymax: 330 }], note: 'Banks never ask for this' }),
        entry({ id: 't', kind: 'tick', tone: 'success', box: { xmin: 960, ymin: 5, xmax: 1000, ymax: 40 }, ok: true }),
      ],
      vp,
      style,
      {},
    )
    expect(plan.labels.has(labelKey('h', 'note'))).toBe(true)
    const t = plan.ticks.get('t')!
    expect(t.center.x).toBeLessThanOrEqual(vp.width)
    expect(t.center.y).toBeGreaterThanOrEqual(0)
  })
  it('maps ghost cursor paths to px', () => {
    const plan = planScene([entry({ id: 'g', kind: 'ghostCursor', tone: 'guide', path: [{ x: 0, y: 0 }, { x: 1000, y: 1000 }] })], vp, style, {})
    expect(plan.ghosts.get('g')).toEqual([{ x: 0, y: 0 }, { x: vp.width, y: vp.height }])
  })

  it('captions stay at the bottom when nothing is there, and move to the top when a mark would be covered', () => {
    const size = { width: 700, height: 120 }
    const free = planScene([entry({ id: 'r', kind: 'ring', tone: 'guide', box: { xmin: 400, ymin: 300, xmax: 480, ymax: 380 } })], vp, style, {})
    expect(chooseCaptionRect(free.marks, size, vp, style)).toMatchObject({ atTop: false })
    const low = planScene([entry({ id: 'r', kind: 'ring', tone: 'guide', box: { xmin: 400, ymin: 900, xmax: 480, ymax: 970 }, label: 'Mute' })], vp, style, {})
    const placed = chooseCaptionRect(low.marks, size, vp, style)
    expect(placed.atTop).toBe(true)
    expect(placed.rect.y).toBeLessThan(vp.height / 3)
    for (const m of low.marks) expect(overlapArea(placed.rect, m)).toBe(0)
  })
  it('below the level chip when one is showing, and the bottom wins when the top is no better', () => {
    const size = { width: 700, height: 120 }
    const low = planScene([entry({ id: 'r', kind: 'ring', tone: 'guide', box: { xmin: 400, ymin: 900, xmax: 480, ymax: 970 } })], vp, style, {})
    const chip = { x: 600, y: 56, w: 300, h: 50 }
    expect(chooseCaptionRect(low.marks, size, vp, style, chip).rect.y).toBeGreaterThanOrEqual(chip.y + chip.h)
    const both = planScene(
      [entry({ id: 'a', kind: 'ring', tone: 'guide', box: { xmin: 400, ymin: 900, xmax: 480, ymax: 970 } }), entry({ id: 'b', kind: 'spotlight', tone: 'guide', box: { xmin: 0, ymin: 0, xmax: 1000, ymax: 300 } })],
      vp,
      style,
      {},
    )
    const placed = chooseCaptionRect(both.marks, size, vp, style)
    expect(placed.atTop).toBe(false)
  })
})
