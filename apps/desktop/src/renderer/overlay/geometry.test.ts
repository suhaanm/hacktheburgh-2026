import { describe, expect, it } from 'vitest'
import {
  displayPhysicalPxToNorm,
  normBoxToRect,
  normToDisplayPhysicalPx,
  normToPx,
  normToScreenDip,
  normToShotPx,
  pxToNorm,
  rectToNormBox,
  screenDipToNorm,
  shotPxToNorm,
  clampRectInto,
  targetRect,
} from './geometry'

const retinaPrimary = { bounds: { x: 0, y: 0, width: 1728, height: 1117 }, scaleFactor: 2 }
// External display to the left and above the primary: negative global origin.
const external = { bounds: { x: -2560, y: -300, width: 2560, height: 1440 }, scaleFactor: 1 }

describe('norm <-> css px', () => {
  const vp = { width: 1728, height: 1117 }
  it('maps corners and centre', () => {
    expect(normToPx({ x: 0, y: 0 }, vp)).toEqual({ x: 0, y: 0 })
    expect(normToPx({ x: 1000, y: 1000 }, vp)).toEqual({ x: 1728, y: 1117 })
    expect(normToPx({ x: 500, y: 500 }, vp)).toEqual({ x: 864, y: 558.5 })
  })
  it('round-trips', () => {
    const p = { x: 123.4, y: 876.5 }
    const back = pxToNorm(normToPx(p, vp), vp)
    expect(back.x).toBeCloseTo(p.x, 9)
    expect(back.y).toBeCloseTo(p.y, 9)
  })
  it('maps boxes, tolerating swapped min/max and out-of-range values', () => {
    const r = normBoxToRect({ xmin: 600, ymin: 400, xmax: 200, ymax: 100 }, vp)
    expect(r.x).toBeCloseTo(345.6)
    expect(r.w).toBeCloseTo(691.2)
    expect(r.y).toBeCloseTo(111.7)
    expect(r.h).toBeCloseTo(335.1)
    const clamped = normBoxToRect({ xmin: -50, ymin: 0, xmax: 1200, ymax: 10 }, vp)
    expect(clamped.x).toBe(0)
    expect(clamped.w).toBe(1728)
  })
  it('round-trips rect <-> box', () => {
    const box = { xmin: 100, ymin: 200, xmax: 300, ymax: 450 }
    const back = rectToNormBox(normBoxToRect(box, vp), vp)
    expect(back.xmax).toBeCloseTo(300)
    expect(back.ymax).toBeCloseTo(450)
  })
  it('clamps when asked', () => {
    expect(pxToNorm({ x: 2000, y: -5 }, vp, { clamp: true })).toEqual({ x: 1000, y: 0 })
  })
})

describe('display geometry (retina, window not at origin)', () => {
  it('norm centre of a retina display is the middle in DIPs and in physical px', () => {
    expect(normToScreenDip({ x: 500, y: 500 }, retinaPrimary)).toEqual({ x: 864, y: 558.5 })
    expect(normToDisplayPhysicalPx({ x: 500, y: 500 }, retinaPrimary)).toEqual({ x: 1728, y: 1117 })
  })
  it('scaleFactor does not change the norm of a DIP point', () => {
    const dip = { x: 432, y: 279.25 }
    const n = screenDipToNorm(dip, retinaPrimary)
    expect(n.x).toBeCloseTo(250)
    expect(n.y).toBeCloseTo(250)
    const physical = normToDisplayPhysicalPx(n, retinaPrimary)
    expect(physical).toEqual({ x: 864, y: 559 })
    const again = displayPhysicalPxToNorm(physical, retinaPrimary)
    expect(again.x).toBeCloseTo(250)
    expect(again.y).toBeCloseTo(250.2, 0)
  })
  it('handles a display with a negative global origin', () => {
    const globalPoint = normToScreenDip({ x: 0, y: 0 }, external)
    expect(globalPoint).toEqual({ x: -2560, y: -300 })
    const bottomRight = normToScreenDip({ x: 1000, y: 1000 }, external)
    expect(bottomRight).toEqual({ x: 0, y: 1140 })
    expect(screenDipToNorm({ x: -1280, y: 420 }, external)).toEqual({ x: 500, y: 500 })
  })
  it('a point outside the display maps outside 0-1000 unless clamped', () => {
    const outside = screenDipToNorm({ x: 10, y: 10 }, external)
    expect(outside.x).toBeGreaterThan(1000)
    expect(screenDipToNorm({ x: 10, y: 10 }, external, { clamp: true }).x).toBe(1000)
  })
})

describe('screenshot pixels', () => {
  it('maps a 1280-wide live frame and a 1920-wide ground frame to the same norm', () => {
    const live = { widthPx: 1280, heightPx: 827 }
    const ground = { widthPx: 1920, heightPx: 1241 }
    const a = shotPxToNorm({ x: 640, y: 413.5 }, live)
    const b = shotPxToNorm({ x: 960, y: 620.5 }, ground)
    expect(a.x).toBeCloseTo(b.x)
    expect(a.y).toBeCloseTo(b.y)
    expect(normToShotPx({ x: 250, y: 750 }, ground)).toEqual({ x: 480, y: 930.75 })
  })
})

describe('targetRect / clampRectInto', () => {
  it('turns a point into a square', () => {
    const r = targetRect({ x: 500, y: 500 }, { width: 1000, height: 1000 }, 20)
    expect(r).toEqual({ x: 480, y: 480, w: 40, h: 40 })
  })
  it('shifts a rect into the viewport without resizing', () => {
    const r = clampRectInto({ x: -30, y: 990, w: 100, h: 50 }, { width: 400, height: 1000 }, 10)
    expect(r).toEqual({ x: 10, y: 940, w: 100, h: 50 })
  })
})
