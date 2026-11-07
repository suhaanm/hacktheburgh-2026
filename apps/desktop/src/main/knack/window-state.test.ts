import { describe, expect, it } from 'vitest'
import { EMPTY_WINDOW_STATE, createWindowStateStore, parseWindowState } from './window-state'
import { MIN_SIZE, WINDOW_SPEC, clampToWorkArea, defaultBounds, defaultSize, displayAtPoint, displayForBounds, minSizeFor, placeDefault, restoreBounds, visibleFraction } from './window-bounds'
import transitions from '../../../../../docs/knack-ux/shell-transitions.json'

const wa = (x: number, y: number, width: number, height: number) => ({ x, y, width, height })

describe('the default size: 80 by 84 percent of the work area, held to 960..1440 by 600..1000', () => {
  // The spec's own examples (docs/knack-ux/shell-transitions.json), then the four displays the plan names.
  it.each(transitions.examples.map((e) => [e.workArea, e.window] as const))('work area %j gives %j', (area, size) => {
    expect(defaultSize({ width: area[0]!, height: area[1]! })).toEqual({ width: size[0], height: size[1] })
  })
  it.each([
    ['1280 by 800', { width: 1280, height: 775 }, { width: 1024, height: 651 }],
    ['1440 by 900', { width: 1440, height: 875 }, { width: 1152, height: 735 }],
    ['1920 by 1080', { width: 1920, height: 1055 }, { width: 1440, height: 886 }],
    ['2560 by 1440', { width: 2560, height: 1415 }, { width: 1440, height: 1000 }],
  ])('%s', (_name, area, size) => {
    expect(defaultSize(area)).toEqual(size)
  })
  it('is never larger than the work area, even on a display smaller than the clamps', () => {
    expect(defaultSize({ width: 900, height: 560 })).toEqual({ width: 900, height: 560 })
    expect(defaultSize({ width: 800, height: 500 })).toEqual({ width: 800, height: 500 })
  })
  it('the minimum is 800 by 560, and never more than the work area', () => {
    expect(MIN_SIZE).toEqual({ width: 800, height: 560 })
    expect(minSizeFor({ width: 1440, height: 875 })).toEqual({ width: 800, height: 560 })
    expect(minSizeFor({ width: 700, height: 500 })).toEqual({ width: 700, height: 500 })
  })
  it('holds the spec numbers as one object', () => {
    expect(WINDOW_SPEC).toMatchObject({ widthFraction: transitions.window.widthFraction, heightFraction: transitions.window.heightFraction, verticalCentreFraction: transitions.window.verticalCentreFraction, restoreMinVisibleFraction: transitions.window.restoreMinVisibleFraction, saveDebounceMs: transitions.window.saveDebounceMs })
    expect([...WINDOW_SPEC.widthClamp]).toEqual(transitions.window.widthClamp)
    expect([...WINDOW_SPEC.heightClamp]).toEqual(transitions.window.heightClamp)
    expect([...WINDOW_SPEC.min]).toEqual(transitions.window.min)
  })
})

describe('position: centred across, a little above centre down', () => {
  it('on the 1440 by 875 work area below the menu bar', () => {
    expect(defaultBounds(wa(0, 25, 1440, 875))).toEqual({ x: 144, y: 25 + Math.round((875 - 735) * 0.4), width: 1152, height: 735 })
  })
  it('on a second display with a negative origin', () => {
    expect(placeDefault(wa(-1920, 0, 1920, 1055), { width: 1440, height: 886 })).toEqual({ x: -1680, y: Math.round((1055 - 886) * 0.4), width: 1440, height: 886 })
  })
})

describe('clamping and how much is visible', () => {
  it('pulls a window that hangs off the right and bottom back in', () => {
    expect(clampToWorkArea({ x: 1400, y: 800, width: 1000, height: 700 }, wa(0, 25, 1440, 875))).toEqual({ x: 440, y: 200, width: 1000, height: 700 })
  })
  it('shrinks a window that is bigger than the work area, and lifts one that is too small', () => {
    expect(clampToWorkArea({ x: 0, y: 0, width: 3000, height: 2000 }, wa(0, 25, 1440, 875))).toEqual({ x: 0, y: 25, width: 1440, height: 875 })
    expect(clampToWorkArea({ x: 100, y: 100, width: 300, height: 200 }, wa(0, 25, 1440, 875))).toEqual({ x: 100, y: 100, width: 800, height: 560 })
  })
  it('measures the visible fraction', () => {
    expect(visibleFraction({ x: 0, y: 25, width: 1000, height: 600 }, wa(0, 25, 1440, 875))).toBe(1)
    expect(visibleFraction({ x: 1140, y: 25, width: 600, height: 400 }, wa(0, 25, 1440, 875))).toBe(0.5)
    expect(visibleFraction({ x: 3000, y: 25, width: 600, height: 400 }, wa(0, 25, 1440, 875))).toBe(0)
  })
})

describe('where the window opens', () => {
  const d1 = { id: 1, workArea: wa(0, 25, 1440, 875) }
  const d2 = { id: 2, workArea: wa(1440, 0, 1920, 1055) }
  const saved = (m: Record<number, ReturnType<typeof wa>>) => (id: number) => m[id] ?? null

  it('first launch (nothing remembered): the default on the display under the pointer', () => {
    const r = restoreBounds({ displays: [d1, d2], cursor: { x: 2000, y: 300 }, saved: saved({}), lastDisplay: null })!
    expect(r).toMatchObject({ source: 'default', displayId: 2 })
    expect(r.bounds).toEqual(defaultBounds(d2.workArea))
  })
  it('restores what was remembered for the display it was last on, as it was', () => {
    const r = restoreBounds({ displays: [d1, d2], cursor: { x: 10, y: 100 }, saved: saved({ 2: wa(1500, 100, 1300, 800) }), lastDisplay: 2 })!
    expect(r).toMatchObject({ source: 'saved', displayId: 2, bounds: wa(1500, 100, 1300, 800) })
  })
  it('a removed display: the window was saved on display 2, which is gone: the default on the display that is there', () => {
    const r = restoreBounds({ displays: [d1], cursor: { x: 700, y: 400 }, saved: saved({ 2: wa(1500, 100, 1300, 800) }), lastDisplay: 2 })!
    expect(r).toMatchObject({ source: 'default', displayId: 1 })
    expect(r.bounds).toEqual(defaultBounds(d1.workArea))
  })
  it('a window saved on a display that is gone but sitting mostly on one that is there still counts', () => {
    const r = restoreBounds({ displays: [d1], cursor: { x: 700, y: 400 }, saved: saved({ 2: wa(100, 100, 1000, 700) }), lastDisplay: 2 })!
    expect(r.source).toBe('saved')
    expect(r.displayId).toBe(1)
  })
  it('a half-offscreen save (under 60% visible) is not used', () => {
    const r = restoreBounds({ displays: [d1], cursor: { x: 700, y: 400 }, saved: saved({ 1: wa(1140, 100, 600, 700) }), lastDisplay: 1 })!
    expect(r.source).toBe('default')
  })
  it('a save that is 60% visible or more is pulled fully inside and held to the minimum size', () => {
    const r = restoreBounds({ displays: [d1], cursor: { x: 700, y: 400 }, saved: saved({ 1: wa(1000, 100, 600, 400) }), lastDisplay: 1 })!
    expect(r).toMatchObject({ source: 'saved', bounds: { x: 640, y: 100, width: 800, height: 560 } })
  })
  it('ignores a remembered rectangle that is not numbers, and does nothing without a display', () => {
    expect(restoreBounds({ displays: [d1], cursor: { x: 0, y: 100 }, saved: saved({ 1: { x: NaN, y: 0, width: 10, height: 10 } }), lastDisplay: 1 })!.source).toBe('default')
    expect(restoreBounds({ displays: [], cursor: { x: 0, y: 0 }, saved: saved({}), lastDisplay: null })).toBeNull()
  })
})

describe('which display', () => {
  const displays = [
    { id: 1, workArea: wa(0, 25, 1440, 875) },
    { id: 2, workArea: wa(1440, 0, 1920, 1055) },
  ]
  it('is the display under the cursor, or the nearest when the cursor is in the menu bar strip', () => {
    expect(displayAtPoint(displays, { x: 2000, y: 300 })?.id).toBe(2)
    expect(displayAtPoint(displays, { x: 700, y: 5 })?.id).toBe(1)
  })
  it('remembers a window under the display it mostly sits on', () => {
    expect(displayForBounds(displays, { x: 1300, y: 100, width: 1000, height: 700 })?.id).toBe(2)
    expect(displayForBounds(displays, { x: 100, y: 100, width: 1000, height: 700 })?.id).toBe(1)
  })
})

describe('the remembered state, per display', () => {
  it('keeps a rectangle per display and writes once, 400 ms after the last move', () => {
    const writes: string[] = []
    const delays: number[] = []
    const timers: (() => void)[] = []
    const store = createWindowStateStore({ file: '/x/knack-window.json', readFile: () => { throw new Error('none') }, writeFile: (_f, d) => void writes.push(d), setTimer: (fn, ms) => (timers.push(fn), delays.push(ms), timers.length), clearTimer: () => undefined, delayMs: WINDOW_SPEC.saveDebounceMs })
    store.touch(1, { x: 1, y: 2, width: 900, height: 600 })
    store.touch(1, { x: 5, y: 6, width: 950, height: 640 })
    store.touch(2, { x: -1200, y: 10, width: 1000, height: 700 })
    expect(writes).toEqual([])
    expect(delays.at(-1)).toBe(400)
    timers.at(-1)!()
    expect(writes).toHaveLength(1)
    expect(JSON.parse(writes[0]!)).toEqual({ version: 1, displays: { '1': { x: 5, y: 6, width: 950, height: 640 }, '2': { x: -1200, y: 10, width: 1000, height: 700 } }, last: '2' })
    expect(store.get(1)).toEqual({ x: 5, y: 6, width: 950, height: 640 })
    expect(store.get(3)).toBeNull()
    expect(store.lastDisplay()).toBe(2)
  })
  it('reads a saved file back, drops bad entries, and survives a corrupt file', () => {
    const good = JSON.stringify({ version: 1, displays: { '7': { x: 1, y: 2, width: 900, height: 600 }, bad: { x: 1 }, '8': { x: 'a', y: 1, width: 1, height: 1 } }, last: '7' })
    const store = createWindowStateStore({ file: '/x', readFile: () => good, writeFile: () => undefined })
    expect(store.get(7)).toEqual({ x: 1, y: 2, width: 900, height: 600 })
    expect(store.get(8)).toBeNull()
    expect(store.lastDisplay()).toBe(7)
    const corrupt = createWindowStateStore({ file: '/x', readFile: () => '{nope', writeFile: () => undefined })
    expect(corrupt.get(7)).toBeNull()
    expect(parseWindowState(42)).toEqual(EMPTY_WINDOW_STATE)
  })
  it('keeps everything in memory when it has no file', () => {
    const store = createWindowStateStore({ file: null, setTimer: () => 1, clearTimer: () => undefined })
    store.touch(1, { x: 0, y: 0, width: 900, height: 600 })
    expect(store.get(1)).toEqual({ x: 0, y: 0, width: 900, height: 600 })
    store.flush()
  })
})
