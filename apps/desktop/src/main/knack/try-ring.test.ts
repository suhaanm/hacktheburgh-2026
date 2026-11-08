import { describe, expect, it, vi } from 'vitest'
import { TRY_GHOST_ID, TRY_RING_ID, TRY_RING_MS, cleanSpot, createTryRing, createTryRingPort, defaultSpot, planRing } from './try-ring'

const display = { x: 0, y: 0, width: 1440, height: 900 }
const content = { x: 144, y: 100, width: 1152, height: 700 } // a window at 80 percent, with a title bar above it

describe('the spot the ring goes around', () => {
  it('is a calm fixed box in the upper middle when the page names none', () => {
    const s = defaultSpot(content)
    expect(s.width).toBe(240)
    expect(s.x + s.width / 2).toBe(content.width / 2)
    expect(s.y).toBeLessThan(content.height / 2)
  })
  it('is the page spot when it is a real box inside the window, else nothing', () => {
    expect(cleanSpot({ x: 20, y: 30, width: 100, height: 40 }, content)).toEqual({ x: 20, y: 30, width: 100, height: 40 })
    for (const bad of ['spot', 5, { x: 20 }, { x: -1, y: 0, width: 50, height: 50 }, { x: 1100, y: 0, width: 200, height: 50 }, { x: 0, y: 0, width: 2, height: 50 }, { x: NaN, y: 0, width: 50, height: 50 }, { x: '1', y: 0, width: 50, height: 50 }]) {
      expect(cleanSpot(bad, content), JSON.stringify(bad)).toBeNull()
    }
  })
})

describe('the box on the display', () => {
  it('turns the window spot into the 0..1000 box [y0, x0, y1, x1] over the display', () => {
    const r = planRing({ x: 0, y: 0, width: 144, height: 90 }, content, display)
    expect(r).toEqual({ ok: true, box: [111, 100, 211, 200] })
  })
  it('uses the fixed spot when none is named', () => {
    const r = planRing(undefined, content, display)
    expect(r.ok).toBe(true)
    if (r.ok) for (const v of r.box) expect(v).toBeGreaterThanOrEqual(0)
  })
  it('refuses a spot that is not a box, and a window that is on another display than the overlay covers', () => {
    expect(planRing({ x: 5 }, content, display)).toEqual({ ok: false, reason: 'bad_request' })
    expect(planRing(undefined, { ...content, x: 2000 }, display)).toEqual({ ok: false, reason: 'other_display' })
    expect(planRing(undefined, content, { x: 1440, y: 0, width: 1920, height: 1080 })).toEqual({ ok: false, reason: 'other_display' })
  })
  it('keeps the box inside the grid even at the display edge', () => {
    const r = planRing({ x: 1000, y: 600, width: 152, height: 100 }, { x: 288, y: 200, width: 1152, height: 700 }, display)
    expect(r.ok).toBe(true)
    if (r.ok) for (const v of r.box) expect(v).toBeLessThanOrEqual(1000)
  })
})

describe('the sample ring as the first run asks for it', () => {
  function rig(over: { visible?: boolean; minimised?: boolean; content?: typeof content | null; ring?: boolean } = {}) {
    const calls: string[] = []
    const timers: { fn: () => void; ms: number }[] = []
    const target = { show: (b: number[], o?: { ghost?: boolean }) => void calls.push(`show ${b.join(',')} ghost=${o?.ghost === true}`), clear: () => void calls.push('clear'), displayBounds: () => display }
    const t = createTryRing({
      ring: () => (over.ring === false ? undefined : target),
      window: () => ({ visible: over.visible ?? true, minimised: over.minimised ?? false, content: over.content === undefined ? content : over.content }),
      setTimer: (fn, ms) => (timers.push({ fn, ms }), timers.length),
      clearTimer: () => undefined,
    })
    return { t, calls, timers }
  }
  it('draws the ring with the ghost cursor, and takes it away after four seconds', () => {
    const r = rig()
    expect(r.t.run({ x: 0, y: 0, width: 144, height: 90 })).toEqual({ ok: true })
    expect(r.calls).toEqual(['show 111,100,211,200 ghost=true'])
    expect(r.timers.at(-1)!.ms).toBe(TRY_RING_MS)
    r.timers.at(-1)!.fn()
    expect(r.calls.at(-1)).toBe('clear')
  })
  it('says why it cannot, and draws nothing: still starting, the window hidden or minimised, a bad spot', () => {
    expect(rig({ ring: false }).t.run(undefined)).toEqual({ ok: false, reason: 'not_ready' })
    for (const over of [{ visible: false }, { minimised: true }, { content: null }]) {
      const r = rig(over)
      expect(r.t.run(undefined)).toEqual({ ok: false, reason: 'window_hidden' })
      expect(r.calls).toEqual([])
    }
    const bad = rig()
    expect(bad.t.run({ x: 'a' })).toEqual({ ok: false, reason: 'bad_request' })
    expect(bad.calls).toEqual([])
  })
  it('a second call moves the ring and starts the four seconds again; stop takes it away at once', () => {
    const r = rig()
    r.t.run(undefined)
    r.t.run({ x: 10, y: 10, width: 50, height: 30 })
    expect(r.calls.filter((c) => c.startsWith('show'))).toHaveLength(2)
    r.t.stop()
    expect(r.calls.at(-1)).toBe('clear')
    const n = r.calls.length
    r.t.stop() // nothing left to clear
    expect(r.calls).toHaveLength(n)
  })
})

describe('the ring on the overlay', () => {
  it('draws a ring and a ghost cursor under ids of their own, with no words on them, and clears exactly those', () => {
    const show = vi.fn()
    const clear = vi.fn()
    const port = createTryRingPort({ show, clear }, () => display)
    port.show([100, 200, 160, 360], { ghost: true })
    const shown = show.mock.calls[0]![0] as { id: string; kind: string }[]
    expect(shown.map((a) => a.id)).toEqual([TRY_RING_ID, TRY_GHOST_ID])
    expect(shown.map((a) => a.kind)).toEqual(['ring', 'ghostCursor'])
    expect(JSON.stringify(shown)).not.toMatch(/label|note|text/)
    expect(TRY_RING_ID).not.toBe('point-voice') // never the voice conversation's ring
    port.clear()
    expect(clear).toHaveBeenCalledWith([TRY_RING_ID, TRY_GHOST_ID])
    expect(port.displayBounds()).toEqual(display)
  })
  it('stays four seconds', () => {
    expect(TRY_RING_MS).toBe(4000)
  })
})
