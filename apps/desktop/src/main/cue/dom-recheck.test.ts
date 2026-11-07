import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { wantFor, type DomTarget, type RectAnswer } from '../dom-ground/protocol'
import type { RequestOutcome } from '../dom-ground/dom-grounder'
import { createDomRecheck, ringable } from './dom-recheck'

// 1440 x 900 points, page zoom 1: a CSS pixel is a point, so grid x = css x / 1440 * 1000 and grid y = css y / 900 * 1000.
const display = () => ({ bounds: { x: 0, y: 0, width: 1440, height: 900 }, scaleFactor: 1 })
const TARGET: DomTarget = { zone: 'calc_a_run', label_hint: 'Calculate', role_hint: 'button' }
const RING = { xmin: 510, ymin: 505, xmax: 590, ymax: 545 } // the engine's box, inside the zone

const answer = (rect: { x: number; y: number; w: number; h: number }, extra: Partial<RectAnswer> = {}): RequestOutcome => ({
  kind: 'answer',
  receivedAt: Date.now(),
  answer: { request_id: 'rq', frame_id: 'top', found: true, rect, window_offset: { x: 0, y: 0 }, scroll: { x: 0, y: 0 }, dpr: 1, age_ms: 0, viewport: { w: 1440, h: 900 }, ...extra },
})
const ZONE = { x: 720, y: 450, w: 144, h: 45 } // grid: x 500..600, y 500..550
const gone: RequestOutcome = { kind: 'answer', receivedAt: 0, answer: { request_id: 'rq', frame_id: 'top', found: false, age_ms: 0 } }

function fake(outcomes: RequestOutcome[]) {
  const calls: DomTarget[] = []
  let i = 0
  return { calls, grounder: { request: vi.fn(async (t: DomTarget) => (calls.push(t), outcomes[Math.min(i++, outcomes.length - 1)])) } }
}

beforeEach(() => void vi.useFakeTimers({ now: 1_000_000 }))
afterEach(() => void vi.useRealTimers())

describe('recheck: is the ring\'s element still there?', () => {
  it('no zone on the step: nothing is asked of the extension and the ring is gone', async () => {
    const f = fake([answer(ZONE)])
    const g = createDomRecheck({ grounder: f.grounder, display })
    expect(await g.recheck({ key: 'ep/step', stepId: 'calc_a', box: RING, source: 'dom', target: null })).toBe('gone')
    expect(f.grounder.request).not.toHaveBeenCalled()
  })

  it('no answer, not found, or scrolled out of view: gone', async () => {
    for (const out of [{ kind: 'timeout' } as RequestOutcome, gone, answer({ x: 720, y: -400, w: 144, h: 45 })]) {
      const g = createDomRecheck({ grounder: fake([out]).grounder, display })
      expect(await g.recheck({ key: 'ep/step', stepId: 'calc_a', box: RING, source: 'dom', target: TARGET })).toBe('gone')
    }
  })

  it('never asked about before: the ring is drawn on the zone\'s own rect, from the extension\'s numbers only', async () => {
    const f = fake([answer(ZONE)])
    const g = createDomRecheck({ grounder: f.grounder, display })
    expect(await g.recheck({ key: 'ep/step', stepId: 'calc_a', box: RING, source: 'dom', target: TARGET })).toEqual({ box: [500, 500, 550, 600] })
    expect(f.calls).toEqual([TARGET])
  })

  it('a zone that is a whole region cannot be ringed: gone', async () => {
    const g = createDomRecheck({ grounder: fake([answer({ x: 100, y: 100, w: 1000, h: 700 })]).grounder, display })
    expect(await g.recheck({ key: 'ep/step', stepId: 'calc_a', box: RING, source: 'dom', target: TARGET })).toBe('gone')
    expect(ringable({ xmin: 0, ymin: 0, xmax: 900, ymax: 900 })).toBe(false)
    expect(ringable({ xmin: 0, ymin: 0, xmax: 100, ymax: 50 })).toBe(true)
  })

  it('the same question twice within a moment shares one answer (one trip to the extension)', async () => {
    const f = fake([answer(ZONE)])
    const g = createDomRecheck({ grounder: f.grounder, display })
    const t = { key: 'ep/step', stepId: 'calc_a', box: RING, source: 'dom' as const, target: TARGET }
    await Promise.all([g.recheck(t), g.recheck(t)])
    expect(f.grounder.request).toHaveBeenCalledOnce()
    await vi.advanceTimersByTimeAsync(400)
    await g.recheck(t)
    expect(f.grounder.request).toHaveBeenCalledTimes(2)
  })

  it('only the zone goes to the extension: the hints stay here', () => {
    expect(wantFor(TARGET, 'rq1')).toEqual({ request_id: 'rq1', frame_id: 'top', zone: 'calc_a_run' })
  })

  it('the page-content boxes of every answer are handed on, in screen points', async () => {
    const onContent = vi.fn()
    const g = createDomRecheck({ grounder: fake([answer(ZONE, { content: [[0, 0, 100, 500]] })]).grounder, display, onContent })
    await g.recheck({ key: 'ep/step', stepId: 'calc_a', box: RING, source: 'dom', target: TARGET })
    expect(onContent).toHaveBeenCalledOnce()
    expect(onContent.mock.calls[0][0]).toEqual([{ x: 0, y: 0, w: 720, h: 90 }])
  })
})

describe('follow: the ring goes with its element', () => {
  const start = (outcomes: RequestOutcome[]) => {
    const f = fake(outcomes)
    const g = createDomRecheck({ grounder: f.grounder, display, refreshMs: 100, timeoutMs: 50 })
    const boxes: Array<[number, number, number, number]> = []
    let goneCount = 0
    const stop = g.follow!({ key: 'ep/step', target: TARGET, box: RING }, { onBox: (b) => boxes.push(b), onGone: () => void goneCount++ })
    return { f, g, boxes, gone: () => goneCount, stop }
  }
  const tick = (ms = 150) => vi.advanceTimersByTimeAsync(ms)

  it('the first answer is the baseline: the ring stays where the engine drew it', async () => {
    const t = start([answer(ZONE), answer(ZONE)])
    await tick(400)
    expect(t.boxes).toEqual([])
    t.stop()
  })

  it('the page scrolls: the ring moves by exactly how far the zone moved, and keeps its own size (never adopts the zone\'s rect)', async () => {
    // Zone up by 90 css px = 100 grid units on y.
    const t = start([answer(ZONE), answer({ ...ZONE, y: ZONE.y - 90 })])
    await tick(400)
    expect(t.boxes.at(-1)).toEqual([405, 510, 445, 590])
    expect(t.boxes.at(-1)![3] - t.boxes.at(-1)![1]).toBe(RING.xmax - RING.xmin)
    t.stop()
  })

  it('a repeated answer at the same place is not a move', async () => {
    const t = start([answer(ZONE), answer({ ...ZONE, y: ZONE.y - 90 }), answer({ ...ZONE, y: ZONE.y - 90 })])
    await tick(800)
    expect(t.boxes).toHaveLength(1)
    t.stop()
  })

  it('the element is scrolled away or not found: gone; when it comes back the ring is shown again, even in the same place', async () => {
    const t = start([answer(ZONE), gone, answer(ZONE)])
    await tick(100)
    await tick(200)
    expect(t.gone()).toBeGreaterThan(0)
    await tick(400)
    expect(t.boxes.at(-1)).toEqual([505, 510, 545, 590])
    t.stop()
  })

  it('a zone that changed size (the page was laid out again): gone', async () => {
    const t = start([answer(ZONE), answer({ ...ZONE, w: 400, h: 120 })])
    await tick(400)
    expect(t.gone()).toBeGreaterThan(0)
    expect(t.boxes).toEqual([])
    t.stop()
  })

  it('stop() stops asking', async () => {
    const t = start([answer(ZONE)])
    await tick(250)
    t.stop()
    const n = t.f.grounder.request.mock.calls.length
    await tick(1000)
    expect(t.f.grounder.request.mock.calls.length).toBe(n)
  })

  it('after following has taken a baseline, a recheck re-rings by how far the zone moved since, not on the zone\'s own rect', async () => {
    const t = start([answer(ZONE), answer({ ...ZONE, y: ZONE.y - 90 })])
    await tick(1) // the baseline answer is in
    const r = await t.g.recheck({ key: 'ep/step', stepId: 'calc_a', box: RING, source: 'dom', target: TARGET })
    expect(r).toEqual({ box: [405, 510, 445, 590] })
    t.stop()
  })

  it('a ring that is already where the zone says it should be is "same"', async () => {
    const t = start([answer(ZONE), answer(ZONE)])
    await tick(1)
    expect(await t.g.recheck({ key: 'ep/step', stepId: 'calc_a', box: RING, source: 'dom', target: TARGET })).toBe('same')
    t.stop()
  })
})
