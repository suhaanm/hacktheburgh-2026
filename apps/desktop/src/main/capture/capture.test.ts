import { describe, expect, it, vi } from 'vitest'
import { changeScore, GRID_H, GRID_W, grayGrid } from './change-score'
import { PROFILES, targetSize } from './sizing'
import { ScreenChangeWatcher } from './watcher'

function solid(width: number, height: number, bgr: [number, number, number]): Uint8Array {
  const px = new Uint8Array(width * height * 4)
  for (let i = 0; i < width * height; i++) {
    px[i * 4] = bgr[0]
    px[i * 4 + 1] = bgr[1]
    px[i * 4 + 2] = bgr[2]
    px[i * 4 + 3] = 255
  }
  return px
}

describe('targetSize', () => {
  it('caps a retina display (3456x2234 physical) at 1280 for live and 1920 for ground/verify', () => {
    const display = { width: 1728, height: 1117 }
    expect(targetSize(display, 2, 'live')).toEqual({ width: 1280, height: 827 })
    expect(targetSize(display, 2, 'ground')).toEqual({ width: 1920, height: 1241 })
    expect(targetSize(display, 2, 'verify')).toEqual({ width: 1920, height: 1241 })
  })
  it('never upscales a small display', () => {
    expect(targetSize({ width: 1024, height: 768 }, 1, 'ground')).toEqual({ width: 1024, height: 768 })
  })
  it('keeps the aspect ratio of a portrait or ultrawide display', () => {
    const wide = targetSize({ width: 3440, height: 1440 }, 1, 'live')
    expect(wide.width / wide.height).toBeCloseTo(3440 / 1440, 1)
  })
  it('uses the documented quality settings', () => {
    expect(PROFILES.live.quality).toBe(60)
    expect(PROFILES.live.maxWidth).toBe(1280)
    expect(PROFILES.ground.maxWidth).toBe(1920)
  })
})

describe('changeScore', () => {
  it('is 0 for identical frames and 1 for black vs white', () => {
    const a = grayGrid(solid(640, 360, [10, 10, 10]), 640, 360)
    expect(a).toHaveLength(GRID_W * GRID_H)
    expect(changeScore(a, a)).toBe(0)
    const black = grayGrid(solid(640, 360, [0, 0, 0]), 640, 360)
    const white = grayGrid(solid(640, 360, [255, 255, 255]), 640, 360)
    expect(changeScore(black, white)).toBeCloseTo(1, 5)
  })
  it('a small change scores low and a large one high', () => {
    const base = solid(640, 360, [200, 200, 200])
    const small = solid(640, 360, [200, 200, 200])
    // A 20x20 dark square (a button) in one corner.
    for (let y = 0; y < 20; y++) for (let x = 0; x < 20; x++) small.fill(0, (y * 640 + x) * 4, (y * 640 + x) * 4 + 3)
    const big = solid(640, 360, [40, 40, 40])
    const g = grayGrid(base, 640, 360)
    expect(changeScore(g, grayGrid(small, 640, 360))).toBeLessThan(0.01)
    expect(changeScore(g, grayGrid(big, 640, 360))).toBeGreaterThan(0.5)
  })
  it('handles rgba order and mismatched grids', () => {
    const px = new Uint8Array(4 * 4 * 4)
    for (let i = 0; i < 16; i++) px.set([255, 0, 0, 255], i * 4) // red in RGBA, blue in BGRA
    const asRgba = grayGrid(px, 4, 4, 'rgba')[0]
    const asBgra = grayGrid(px, 4, 4, 'bgra')[0]
    expect(asRgba).toBeGreaterThan(asBgra)
    expect(changeScore(new Uint8Array(3), new Uint8Array(4))).toBe(1)
  })
})

describe('ScreenChangeWatcher', () => {
  function setup(frames: (Uint8Array | null)[]) {
    let tickFn: (() => void) | null = null
    let i = 0
    let now = 0
    const cleared = vi.fn()
    const watcher = new ScreenChangeWatcher({
      sample: async () => frames[Math.min(i++, frames.length - 1)],
      now: () => now,
      setInterval: (fn) => {
        tickFn = fn
        return 1
      },
      clearInterval: cleared,
    })
    const run = async (ms = 500): Promise<void> => {
      now += ms
      await watcher.tick()
    }
    return { watcher, run, cleared, tickFn: () => tickFn }
  }
  const g = (v: number): Uint8Array => grayGrid(solid(64, 36, [v, v, v]), 64, 36)

  it('emits once after a material change settles, not during the transition', async () => {
    const { watcher, run } = setup([g(200), g(200), g(120), g(60), g(60), g(60)])
    const got: number[] = []
    watcher.subscribe((s) => got.push(s))
    await run() // initial tick from subscribe already consumed g(200)? the subscribe tick + this one
    await run()
    await run() // 120: changing, not settled
    await run() // 60: still moving
    expect(got).toHaveLength(0)
    await run() // 60: settled
    expect(got).toHaveLength(1)
    expect(got[0]).toBeGreaterThan(0.3)
    await run()
    expect(got).toHaveLength(1)
  })
  it('ignores tiny drift and reports a never-settling change after maxWait', async () => {
    const { watcher, run } = setup([g(200), g(200), g(201), g(202)])
    const got: number[] = []
    watcher.subscribe((s) => got.push(s))
    await run()
    await run()
    await run()
    expect(got).toHaveLength(0)

    const flicker = setup([g(200), g(200), g(100), g(40), g(120), g(30), g(150), g(20)])
    const hits: number[] = []
    flicker.watcher.subscribe((s) => hits.push(s))
    for (let k = 0; k < 7; k++) await flicker.run(500)
    expect(hits.length).toBeGreaterThan(0)
  })
  it('polls only while subscribed and survives sampling failures', async () => {
    const { watcher, cleared } = setup([null, g(1)])
    expect(watcher.running).toBe(false)
    const off = watcher.subscribe(() => undefined)
    expect(watcher.running).toBe(true)
    await watcher.tick()
    off()
    expect(watcher.running).toBe(false)
    expect(cleared).toHaveBeenCalled()
  })
  it('a throwing listener does not stop the others', async () => {
    const { watcher, run } = setup([g(200), g(200), g(50), g(50)])
    const ok = vi.fn()
    watcher.subscribe(() => {
      throw new Error('boom')
    })
    watcher.subscribe(ok)
    await run()
    await run()
    await run()
    await run()
    expect(ok).toHaveBeenCalled()
  })
})
