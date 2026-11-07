import { describe, expect, it } from 'vitest'
import { overlapArea } from './geometry'
import { estimateTextBox, placeLabel, placeLabels } from './layout'

const vp = { width: 1000, height: 700 }

describe('placeLabel', () => {
  it('puts the label below the anchor when there is room', () => {
    const p = placeLabel({ id: 'a', size: { width: 200, height: 50 }, anchor: { x: 400, y: 300, w: 100, h: 60 }, gap: 10 }, vp, [])
    expect(p.side).toBe('below')
    expect(p.rect.y).toBe(370)
    expect(p.crowded).toBe(false)
  })
  it('flips above near the bottom edge', () => {
    const p = placeLabel({ id: 'a', size: { width: 200, height: 50 }, anchor: { x: 400, y: 620, w: 100, h: 60 }, gap: 10 }, vp, [])
    expect(p.side).toBe('above')
    expect(p.rect.y + p.rect.h).toBeLessThanOrEqual(620 - 10)
  })
  it('never leaves the viewport', () => {
    const p = placeLabel({ id: 'a', size: { width: 300, height: 60 }, anchor: { x: 950, y: 20, w: 40, h: 30 }, gap: 10 }, vp, [])
    expect(p.rect.x + p.rect.w).toBeLessThanOrEqual(vp.width)
    expect(p.rect.x).toBeGreaterThanOrEqual(0)
  })
  it('avoids obstacles', () => {
    const obstacle = { x: 300, y: 370, w: 400, h: 80 }
    const p = placeLabel({ id: 'a', size: { width: 200, height: 50 }, anchor: { x: 400, y: 300, w: 100, h: 60 }, gap: 10 }, vp, [obstacle])
    expect(overlapArea(p.rect, obstacle)).toBe(0)
  })
  it('later labels avoid earlier ones', () => {
    const reqs = [
      { id: 'a', size: { width: 200, height: 50 }, anchor: { x: 400, y: 300, w: 100, h: 60 }, gap: 10 },
      { id: 'b', size: { width: 200, height: 50 }, anchor: { x: 420, y: 300, w: 100, h: 60 }, gap: 10 },
    ]
    const placed = placeLabels(reqs, vp, [])
    expect(overlapArea(placed.get('a')!.rect, placed.get('b')!.rect)).toBe(0)
  })
  it('attach point is on the near edge', () => {
    const p = placeLabel({ id: 'a', size: { width: 200, height: 50 }, anchor: { x: 400, y: 300, w: 100, h: 60 }, gap: 10 }, vp, [])
    expect(p.attach.y).toBe(p.rect.y)
    expect(p.attach.x).toBeGreaterThanOrEqual(p.rect.x)
    expect(p.attach.x).toBeLessThanOrEqual(p.rect.x + p.rect.w)
  })
})

describe('estimateTextBox', () => {
  it('grows taller with longer text and respects max width', () => {
    const short = estimateTextBox('Click here', 20, 1.4, 16, 10, 340)
    const long = estimateTextBox('Click the blue Start call button in the middle of the window to begin', 20, 1.4, 16, 10, 340)
    expect(long.height).toBeGreaterThan(short.height)
    expect(long.width).toBeLessThanOrEqual(340)
  })
})
