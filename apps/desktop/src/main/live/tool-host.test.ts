import { describe, expect, it } from 'vitest'
import { MAX_BOX_AREA, NONE_ID, POINT_ID, RING_VISIBLE_MS, buildMenu, createToolHost, sanePointBox } from './tool-host'
import { createCompositeGround, createHttpGroundPort, parseGroundAnswer } from './http-ground'
import { createRingPort, VOICE_RING_ID } from './ring'
import { encodeLiveFrame, createFrameProvider, LIVE_FRAME_MAX_EDGE } from './frame-provider'
import { FakeImage, makePng } from '../awareness/capture-fake'
import { fakeCue, manualClock, openVerdict } from './live.test-util'
import { isLoopbackUrl } from '../engine/endpoints'
import type { GroundAnswer, GroundPort } from './ports'

const answer = (o: Partial<GroundAnswer> = {}): GroundAnswer => ({ available: [POINT_ID], chosen: POINT_ID, box_2d: [100, 200, 160, 360], confidence: 0.9, source: 'vision', ...o })

describe('the closed menu for point_at', () => {
  it('has the description under a code-made id, decoys from the pack labels, and a fixed "something else"', () => {
    const m = buildMenu('the green Submit button', [{ id: 'read_case', label: 'Read the household record' }, { id: 'calc_a', label: 'Run calculator A' }])
    expect(m).toEqual([
      { id: 't0', label: 'the green Submit button' },
      { id: 't1', label: 'Read the household record' },
      { id: 't2', label: 'Run calculator A' },
      { id: NONE_ID, label: 'something else on the screen' },
    ])
  })
  it('is always 2 to 6 entries, with no duplicate labels, whatever the candidates are', () => {
    expect(buildMenu('the x button', [])).toHaveLength(2)
    const many = Array.from({ length: 12 }, (_, i) => ({ id: `s${i}`, label: i < 3 ? 'same' : `Step ${i}` }))
    const m = buildMenu('the x button', many)
    expect(m.length).toBeLessThanOrEqual(6)
    expect(new Set(m.map((x) => x.label.toLowerCase())).size).toBe(m.length)
    expect(buildMenu('Same', [{ id: 'a', label: 'same' }])).toHaveLength(2) // a decoy equal to the description is dropped
  })
})

describe('boxes', () => {
  it('are clamped into the grid, reordered, and refused when tiny or huge', () => {
    expect(sanePointBox([100, 200, 160, 360])).toEqual([100, 200, 160, 360])
    expect(sanePointBox([160, 360, 100, 200])).toEqual([100, 200, 160, 360])
    expect(sanePointBox([-50, -50, 40, 40])).toEqual([0, 0, 40, 40])
    expect(sanePointBox([0, 0, 2000, 2000])).toBeNull() // clamped to the whole screen: far over the area limit
    expect(sanePointBox([100, 100, 102, 300])).toBeNull()
    expect(sanePointBox([0, 0, 1000, 1000 * (MAX_BOX_AREA / 1_000_000) + 50])).toBeNull()
    for (const bad of [null, 'x', [1, 2, 3], [1, 2, 3, NaN], [1, 2, 3, '4']]) expect(sanePointBox(bad)).toBeNull()
  })
})

describe('the tool host', () => {
  const rig = (g: GroundPort | null) => {
    const rings: unknown[] = []
    const clock = manualClock()
    let cleared = 0
    const host = createToolHost({ cue: fakeCue(), ground: g, ring: { show: (b) => void rings.push(b), clear: () => void cleared++ }, setTimer: (fn, ms) => clock.setTimeout(fn, ms), clearTimer: (h) => clock.clearTimeout(h) })
    return { host, rings, clock, cleared: () => cleared }
  }
  it('draws the ring only when the grounder chose the description with enough confidence and a sane box', async () => {
    const calls: unknown[] = []
    const t = rig({ ground: async (r) => (calls.push(r), answer()) })
    expect(await t.host.point('the green Submit button')).toEqual({ found: true })
    expect(t.rings).toEqual([[100, 200, 160, 360]])
    expect((calls[0] as { menu: unknown[] }).menu.length).toBeGreaterThanOrEqual(2)
  })
  it.each([
    ['a decoy chosen', answer({ chosen: 't1' })],
    ['nothing chosen', answer({ chosen: null, box_2d: null })],
    ['the none entry', answer({ chosen: NONE_ID })],
    ['low confidence', answer({ confidence: 0.4 })],
    ['no box', answer({ box_2d: null })],
    ['an absurd box', answer({ box_2d: [0, 0, 1000, 1000] })],
    ['an unknown id', answer({ chosen: 'made_up' })],
  ])('finds nothing for %s', async (_l, a) => {
    const t = rig({ ground: async () => a })
    expect(await t.host.point('the x button')).toEqual({ found: false })
    expect(t.rings).toEqual([])
  })
  it('finds nothing when there is no grounder or it fails or says nothing', async () => {
    expect(await rig(null).host.point('the x button')).toEqual({ found: false })
    expect(await rig({ ground: async () => { throw new Error('boom') } }).host.point('the x button')).toEqual({ found: false })
    expect(await rig({ ground: async () => null }).host.point('the x button')).toEqual({ found: false })
  })
  it('clears the ring after fifteen seconds, and on dispose', async () => {
    const t = rig({ ground: async () => answer() })
    await t.host.point('the x button')
    t.clock.advance(RING_VISIBLE_MS - 1)
    expect(t.cleared()).toBe(0)
    t.clock.advance(2)
    expect(t.cleared()).toBe(1)
    await t.host.point('the x button')
    t.host.dispose()
    expect(t.cleared()).toBe(2)
  })
})

describe('the grounding adapters', () => {
  const frames = { grab: async () => { const jpeg = Buffer.alloc(50, 9); return { jpeg, width: 640, height: 360, release: () => jpeg.fill(0) } } }
  it('parses an answer in the route\'s shape and refuses anything off-shape', () => {
    expect(parseGroundAnswer({ available: ['t0'], chosen: 't0', box_2d: [1, 2, 3, 4], confidence: 1.7, source: 'vision', model_tier: 'lite', latency_ms: 880 })).toEqual({ available: ['t0'], chosen: 't0', box_2d: [1, 2, 3, 4], confidence: 1, source: 'vision', model_tier: 'lite', latency_ms: 880 })
    expect(parseGroundAnswer({ data: { chosen: 't0', box_2d: [1, 2, 3, 4], confidence: 0.8, source: 'dom' } })).toMatchObject({ source: 'dom', chosen: 't0' })
    expect(parseGroundAnswer({ chosen: 5, box_2d: 'x', confidence: 'high' })).toMatchObject({ chosen: null, box_2d: null, confidence: 0 })
    expect(parseGroundAnswer('x')).toBeNull()
    expect(parseGroundAnswer(null)).toBeNull()
  })
  it('sends the frame and the closed menu to /cue/ground with the gate booleans, and zeroes the frame', async () => {
    const calls: Array<{ url: string; body: any }> = []
    let zeroed = false
    const f = (async (url: string, init: RequestInit) => (calls.push({ url: String(url), body: JSON.parse(String(init.body)) }), { ok: true, json: async () => ({ chosen: 't0', box_2d: [1, 2, 30, 40], confidence: 0.9, source: 'vision' }) })) as unknown as typeof fetch
    const port = createHttpGroundPort({ agentUrl: 'http://127.0.0.1:7710', isLoopback: isLoopbackUrl, frames: { grab: async () => { const g = await frames.grab(); return { ...g, release: () => { zeroed = g.jpeg.every((x) => x === 0) || (g.release(), true) } } } }, gates: async () => openVerdict(), fetchImpl: f })
    const a = await port.ground({ menu: [{ id: 't0', label: 'x ok' }, { id: 't_none', label: 'something else' }], app_kind: 'browser' })
    expect(a).toMatchObject({ chosen: 't0', confidence: 0.9 })
    expect(calls[0]!.url).toBe('http://127.0.0.1:7710/cue/ground')
    expect(calls[0]!.body).toMatchObject({ purpose: 'cue.ground', app_kind: 'browser', gates: { consent: true, denylisted_app: false, secure_input: false, unattended: false }, frame: { mime: 'image/jpeg', width: 640, height: 360 } })
    expect(calls[0]!.body.menu).toEqual([{ id: 't0', label: 'x ok' }, { id: 't_none', label: 'something else' }])
    expect(zeroed).toBe(true)
  })
  it('takes no frame and sends nothing when the gate is closed', async () => {
    let grabbed = 0
    const port = createHttpGroundPort({ agentUrl: 'http://127.0.0.1:7710', isLoopback: isLoopbackUrl, frames: { grab: async () => (grabbed++, null) }, gates: async () => openVerdict({ open: false, reason: 'secure_input' }), fetchImpl: (async () => { throw new Error('network used') }) as never })
    expect(await port.ground({ menu: [] })).toBeNull()
    expect(grabbed).toBe(0)
  })
  it('only talks to the agent on this machine, and answers null when it fails', async () => {
    expect(() => createHttpGroundPort({ agentUrl: 'https://example.com', isLoopback: isLoopbackUrl, frames, gates: async () => openVerdict() })).toThrow(/this machine/)
    const port = createHttpGroundPort({ agentUrl: 'http://127.0.0.1:7710', isLoopback: isLoopbackUrl, frames, gates: async () => openVerdict(), fetchImpl: (async () => { throw new Error('down') }) as never })
    expect(await port.ground({ menu: [] })).toBeNull()
  })
  it('tries the page\'s DOM first and falls through to vision only when the DOM has no answer', async () => {
    const dom: GroundPort = { ground: async () => answer({ source: 'dom' }) }
    const vision: GroundPort = { ground: async () => { throw new Error('vision must not run') } }
    expect(await createCompositeGround(dom, vision)!.ground({ menu: [] })).toMatchObject({ source: 'dom' })
    const noDom: GroundPort = { ground: async () => null }
    const v2: GroundPort = { ground: async () => answer({ source: 'vision' }) }
    expect(await createCompositeGround(noDom, v2)!.ground({ menu: [] })).toMatchObject({ source: 'vision' })
    expect(createCompositeGround(null, null)).toBeNull()
  })
})

describe('the ring', () => {
  it('goes through the overlay contract with a guidance id, no label and no note', () => {
    const shown: unknown[][] = []
    const cleared: unknown[] = []
    const ring = createRingPort({ show: (a) => void shown.push(a), clear: (ids) => void cleared.push(ids) })
    ring.show([100, 200, 160, 360])
    expect(shown[0]).toEqual([{ id: VOICE_RING_ID, kind: 'ring', tone: 'guide', box: { xmin: 200, ymin: 100, xmax: 360, ymax: 160 }, exact: true }])
    expect(VOICE_RING_ID.startsWith('point-')).toBe(true)
    ring.clear()
    expect(cleared).toEqual([[VOICE_RING_ID]])
  })
})

describe('frames for the session', () => {
  it('are at most 1024 px on the long edge, JPEG, and zeroed on release', () => {
    const img = new FakeImage(makePng(2560, 1440))
    const f = encodeLiveFrame(img)
    expect(Math.max(f.width, f.height)).toBeLessThanOrEqual(LIVE_FRAME_MAX_EDGE)
    expect(f.width).toBe(1024)
    expect(f.height).toBe(576)
    expect(f.jpeg.length).toBeGreaterThan(0)
    f.release()
    expect(f.jpeg.every((b) => b === 0)).toBe(true)
    f.release() // twice is fine
  })
  it('never upscales a small screen, and an empty image is an error the provider turns into "no frame"', async () => {
    expect(encodeLiveFrame(new FakeImage(makePng(640, 360))).width).toBe(640)
    const empty = { isEmpty: () => true, getSize: () => ({ width: 0, height: 0 }), resize: () => empty, toJPEG: () => Buffer.alloc(0) }
    expect(() => encodeLiveFrame(empty as never)).toThrow()
    const p = createFrameProvider({ kind: 'fake', grab: async () => empty as never })
    expect(await p.grab()).toBeNull()
    const denied = createFrameProvider({ kind: 'desktop', grab: async () => { throw new Error('permission') } })
    expect(await denied.grab()).toBeNull()
  })
})
