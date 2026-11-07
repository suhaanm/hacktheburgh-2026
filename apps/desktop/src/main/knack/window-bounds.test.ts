import { describe, expect, it } from 'vitest'
import { EMPTY_WINDOW_STATE, createWindowStateStore, parseWindowState } from './window-state'
import { DEFAULT_SIZE, MIN_SIZE, centred, clampToWorkArea, defaultSize, displayAtPoint, displayForBounds, initialBounds, minSizeFor } from './window-bounds'

const wa = (x: number, y: number, width: number, height: number) => ({ x, y, width, height })

describe('default size', () => {
  it('is 1120 by 740 on a roomy display', () => {
    expect(defaultSize({ width: 2560, height: 1415 })).toEqual(DEFAULT_SIZE)
  })
  it('is held to 80% of the work area on a laptop (1440 by 875 usable)', () => {
    expect(defaultSize({ width: 1440, height: 875 })).toEqual({ width: 1120, height: 700 })
  })
  it('never goes below the minimum (881 by 600) while that still fits', () => {
    expect(defaultSize({ width: 1100, height: 740 })).toEqual({ width: 881, height: 600 })
  })
  it('on a display smaller than the minimum, fills the work area and no more', () => {
    expect(minSizeFor({ width: 800, height: 500 })).toEqual({ width: 800, height: 500 })
    expect(defaultSize({ width: 800, height: 500 })).toEqual({ width: 800, height: 500 })
  })
})

describe('centring and clamping', () => {
  it('centres in a work area that starts below the menu bar', () => {
    expect(centred(wa(0, 25, 1440, 875), { width: 1120, height: 700 })).toEqual({ x: 160, y: 113, width: 1120, height: 700 })
  })
  it('centres on a second display with a negative origin', () => {
    expect(centred(wa(-1920, 0, 1920, 1055), { width: 1120, height: 740 })).toEqual({ x: -1520, y: 158, width: 1120, height: 740 })
  })
  it('pulls a window that hangs off the right and bottom back in', () => {
    expect(clampToWorkArea({ x: 1400, y: 800, width: 1000, height: 700 }, wa(0, 25, 1440, 875))).toEqual({ x: 440, y: 200, width: 1000, height: 700 })
  })
  it('pulls a window that is off to the left or above back in', () => {
    expect(clampToWorkArea({ x: -300, y: -50, width: 1000, height: 700 }, wa(0, 25, 1440, 875))).toEqual({ x: 0, y: 25, width: 1000, height: 700 })
  })
  it('shrinks a window that is bigger than the work area, and lifts one that is too small', () => {
    expect(clampToWorkArea({ x: 0, y: 0, width: 3000, height: 2000 }, wa(0, 25, 1440, 875))).toEqual({ x: 0, y: 25, width: 1440, height: 875 })
    expect(clampToWorkArea({ x: 100, y: 100, width: 300, height: 200 }, wa(0, 25, 1440, 875))).toEqual({ x: 100, y: 100, width: MIN_SIZE.width, height: MIN_SIZE.height })
  })
})

describe('initial bounds', () => {
  const area = wa(0, 25, 1440, 875)
  it('is the default, centred, with nothing remembered', () => {
    expect(initialBounds(area, null)).toEqual({ x: 160, y: 113, width: 1120, height: 700 })
  })
  it('restores what was remembered for this display, clamped to it', () => {
    expect(initialBounds(area, { x: 40, y: 60, width: 1000, height: 650 })).toEqual({ x: 40, y: 60, width: 1000, height: 650 })
    expect(initialBounds(wa(0, 25, 1280, 775), { x: 900, y: 500, width: 1000, height: 650 })).toEqual({ x: 280, y: 150, width: 1000, height: 650 })
  })
  it('ignores a remembered rectangle that is not numbers', () => {
    expect(initialBounds(area, { x: NaN, y: 0, width: 10, height: 10 })).toEqual(initialBounds(area, null))
  })
})

describe('which display', () => {
  const displays = [
    { id: 1, workArea: wa(0, 25, 1440, 875) },
    { id: 2, workArea: wa(1440, 0, 1920, 1055) },
  ]
  it('is the display under the cursor', () => {
    expect(displayAtPoint(displays, { x: 2000, y: 300 })?.id).toBe(2)
    expect(displayAtPoint(displays, { x: 10, y: 500 })?.id).toBe(1)
  })
  it('is the nearest display when the cursor is in the menu bar strip or a gap', () => {
    expect(displayAtPoint(displays, { x: 700, y: 5 })?.id).toBe(1)
  })
  it('remembers a window under the display it mostly sits on', () => {
    expect(displayForBounds(displays, { x: 1300, y: 100, width: 1000, height: 700 })?.id).toBe(2)
    expect(displayForBounds(displays, { x: 100, y: 100, width: 1000, height: 700 })?.id).toBe(1)
  })
})

describe('the remembered state, per display', () => {
  it('keeps a rectangle per display and writes once after a pause', () => {
    const writes: string[] = []
    const timers: (() => void)[] = []
    const store = createWindowStateStore({ file: '/x/knack-window.json', readFile: () => { throw new Error('none') }, writeFile: (_f, d) => void writes.push(d), setTimer: (fn) => (timers.push(fn), timers.length), clearTimer: () => undefined })
    store.touch(1, { x: 1, y: 2, width: 900, height: 600 })
    store.touch(1, { x: 5, y: 6, width: 950, height: 640 })
    store.touch(2, { x: -1200, y: 10, width: 1000, height: 700 })
    expect(writes).toEqual([])
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
