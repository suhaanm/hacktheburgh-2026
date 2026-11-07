// (a) Core loop through the debug HTTP: health, state, point_at (found / not found), argument errors, shots, dock render.
import fs from 'node:fs'
import path from 'node:path'
import { beforeAll, describe, expect, it } from 'vitest'
import { MODE, REAL, REPO, VISIBLE, clearOverlayLog, dbg, dev, overlayLog, resetApp, shownBoxes, state, tool, uglyText } from './helpers'

describe('core loop', () => {
  beforeAll(async () => {
    await resetApp()
    if (REAL && VISIBLE) {
      await dev('/dev/stage/open', {})
      await dev('/dev/stage/call', { fn: 'go', args: ['video/lily'] })
    }
  })

  it('health reports the running app and its mock flag', async () => {
    const { status, body } = await dbg<{ ok: boolean; pid: number; mock: boolean; phase: string }>('/health')
    expect(status).toBe(200)
    expect(body.ok).toBe(true)
    expect(body.pid).toBeGreaterThan(0)
    expect(body.mock).toBe(MODE === 'mock')
  })

  it('initial state is idle, persona-neutral and trust-safe', async () => {
    const s = await state()
    expect(['asleep', 'listening_for_name']).toContain(s.phase)
    expect(s.settings.doItForMeAllowed).toBe(false)
    expect(s.pendingConfirm).toBeUndefined()
    expect(s.level).toBeGreaterThanOrEqual(1)
    expect(s.level).toBeLessThanOrEqual(4)
  })

  it.skipIf(REAL && !VISIBLE)('point_at draws a ring + arrow on a present target, with a badge when a step is given', async () => {
    await clearOverlayLog()
    const target = REAL ? 'large green button reading Start call' : 'Start call button'
    const { result, ms } = await tool<{ found: boolean; confidence: number }>('point_at', { target, step: 2 })
    expect(result.error).toBeUndefined()
    expect(result.found).toBe(true)
    expect(result.confidence).toBeGreaterThan(0.3)
    const log = await overlayLog()
    const rings = shownBoxes(log, 'ring')
    expect(rings.length).toBeGreaterThan(0)
    const box = rings[rings.length - 1]
    expect(box.xmax).toBeGreaterThan(box.xmin)
    expect(box.ymax).toBeGreaterThan(box.ymin)
    for (const v of [box.xmin, box.ymin, box.xmax, box.ymax]) expect(v).toBeGreaterThanOrEqual(0)
    for (const v of [box.xmin, box.ymin, box.xmax, box.ymax]) expect(v).toBeLessThanOrEqual(1000)
    const kinds = log.filter((o) => o.op === 'show').flatMap((o) => (o.annotations ?? []).map((a) => a.kind))
    // The numbered badge is drawn by the overlay from ring.step (no separate badge annotation).
    expect(kinds).toEqual(expect.arrayContaining(['ring', 'arrow']))
    expect(kinds).not.toContain('badge')
    const lastRing = log.filter((o) => o.op === 'show').flatMap((o) => o.annotations ?? []).filter((a) => a.kind === 'ring').pop() as { step?: number } | undefined
    expect(lastRing?.step).toBe(2)
    expect(ms).toBeLessThan(15_000)
  })

  it('point_at on an absent target says found:false in plain English and draws nothing', async () => {
    await clearOverlayLog()
    const { result } = await tool<{ found: boolean; note?: string }>('point_at', { target: 'a unicorn-shaped purple Download button that is not here' })
    expect(result.error).toBeUndefined()
    expect(result.found).toBe(false)
    expect(uglyText(result.note)).toBeNull()
    expect(shownBoxes(await overlayLog(), 'ring')).toHaveLength(0)
  })

  it('bad arguments and unknown tools return plain errors, never crash', async () => {
    const bad = await tool('point_at', {})
    expect(String(bad.result.error)).toMatch(/Bad arguments/i)
    const unknown = await tool('format_disk', {})
    expect(String(unknown.result.error)).toMatch(/Unknown tool/i)
    expect(String(bad.result.error)).not.toMatch(/\bat [\w.<>$ ]+ \(.*:\d+:\d+\)|node_modules/)
    expect((await dbg('/health')).status).toBe(200)
  })

  it('clear_annotations clears the overlay', async () => {
    await clearOverlayLog()
    const { result } = await tool<{ ok: boolean }>('clear_annotations')
    expect(result.ok).toBe(true)
    expect((await overlayLog()).some((o) => o.op === 'clear')).toBe(true)
  })

  it('GET /shot returns a JPEG with dimensions', async () => {
    const res = await fetch(`${process.env.E2E_DEBUG_URL}/shot?purpose=ground`)
    expect(res.status).toBe(200)
    const buf = Buffer.from(await res.arrayBuffer())
    expect([buf[0], buf[1]]).toEqual([0xff, 0xd8])
    if (REAL) {
      fs.mkdirSync(path.join(REPO, 'docs', 'qa-shots'), { recursive: true })
      fs.writeFileSync(path.join(REPO, 'docs', 'qa-shots', 'core-shot.jpg'), buf)
    }
    expect(Number(res.headers.get('x-shot-width'))).toBeGreaterThan(0)
    expect(Number(res.headers.get('x-shot-height'))).toBeGreaterThan(0)
    if (REAL) expect(Number(res.headers.get('x-shot-width'))).toBeLessThanOrEqual(1920)
  })

  it('dock renders (dock.png is a PNG)', async () => {
    const res = await fetch(`${process.env.E2E_DEBUG_URL}/dock.png`)
    // A hidden (headless) window may not be capturable; a visible one must be.
    if (!VISIBLE && res.status === 404) return
    expect(res.status).toBe(200)
    const buf = Buffer.from(await res.arrayBuffer())
    expect(buf.subarray(1, 4).toString('ascii')).toBe('PNG')
    expect(buf.length).toBeGreaterThan(2000)
  })
})
