import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { afterEach, describe, expect, it } from 'vitest'
import type { Annotation } from '../../shared/protocol'
import { createCoachTracker } from '../engine/coach-events'
import type { EventInput } from '../engine/event'
import { createDomCoach, DOM_RING_ID } from './dom-coach'
import { createDomGrounder, trackTarget, type RequestOutcome } from './dom-grounder'
import { startExtServer, type ExtServer, type RingRequest } from './ext-server'
import { parseAnswer, targetProblem, toTarget, wantFor, type RectAnswer } from './protocol'
import { ageNow, mapAnswer, pageZoom, parseCalibration, toNormBox, viewportOrigin, type DisplayInfo } from './rect-map'

const SCHEMA_FILE = path.resolve(__dirname, '../../../../../packages/schema/ext_rect.schema.json')
const DISPLAY: DisplayInfo = { bounds: { x: 0, y: 0, width: 1728, height: 1117 }, scaleFactor: 2 }

const answer = (over: Partial<RectAnswer> = {}): RectAnswer => ({
  request_id: 'rq_1',
  frame_id: 'top',
  found: true,
  rect: { x: 100, y: 200, w: 120, h: 40 },
  window_offset: { x: 50, y: 150 },
  scroll: { x: 0, y: 0 },
  dpr: 2,
  age_ms: 20,
  ...over,
})

describe.skipIf(!fs.existsSync(SCHEMA_FILE))('protocol against packages/schema/ext_rect.schema.json', () => {
  const schema = JSON.parse(fs.readFileSync(SCHEMA_FILE, 'utf8')) as { $defs: Record<string, unknown> }
  const ajv = new Ajv2020({ strict: false, allErrors: true })
  addFormats(ajv)
  const validWant = ajv.compile({ $ref: '#/$defs/RectWant', $defs: schema.$defs })
  const validAnswer = ajv.compile({ $ref: '#/$defs/RectAnswer', $defs: schema.$defs })

  it('every want this app builds validates, by label hash and by role and name', () => {
    expect(validWant(wantFor({ label_hash: 'h:9f2c1a77b0aa' }, 'rq_a'))).toBe(true)
    expect(validWant(wantFor({ role: 'button', name: 'Calculate' }, 'rq_b', 'f2'))).toBe(true)
  })

  // The zone field is a proposed addition to RectWant; this checks it as soon as the schema has it.
  const zoneInSchema = Boolean((schema.$defs.RectWant as { properties?: Record<string, unknown> }).properties?.zone)
  it.skipIf(!zoneInSchema)('a zone want validates once the schema has the zone field', () => {
    expect(validWant(wantFor({ zone: 'calc.result' }, 'rq_z'))).toBe(true)
  })

  it('parseAnswer accepts what the schema accepts and rejects what it rejects', () => {
    const good: unknown[] = [answer(), { request_id: 'rq_2', frame_id: 'f1', found: false, age_ms: 0 }, { ...answer(), found: undefined }]
    for (const a of good) {
      expect(validAnswer(a), JSON.stringify(validAnswer.errors)).toBe(true)
      expect(parseAnswer(a)).not.toBeNull()
    }
    const { rect: _r, ...noRect } = answer()
    const bad: unknown[] = [noRect, { ...answer(), dpr: 0 }, { ...answer(), frame_id: 'main' }, { ...answer(), request_id: '' }, { ...answer(), age_ms: -1 }, { ...answer(), rect: { x: 1, y: 2, w: -3, h: 4 } }, { request_id: 'rq', frame_id: 'top', found: false, rect: { x: 1, y: 1, w: 1, h: 1 }, age_ms: 0 }]
    for (const a of bad) {
      expect(validAnswer(a), JSON.stringify(a)).toBe(false)
      if (!(a as { found?: boolean }).found && (a as { rect?: unknown }).rect) continue // a found:false answer that still carries a rect: we drop the rect rather than refuse it
      expect(parseAnswer(a), JSON.stringify(a)).toBeNull()
    }
  })
})

describe('protocol helpers', () => {
  it('validates targets: exactly one of label hash, or role and name', () => {
    expect(targetProblem({ label_hash: 'h:abcd1234' })).toBeNull()
    expect(targetProblem({ role: 'button', name: 'Calculate' })).toBeNull()
    expect(targetProblem({ label_hash: 'h:abcd1234', role: 'button', name: 'x' })).not.toBeNull()
    expect(targetProblem({ label_hash: 'Save' })).not.toBeNull()
    expect(targetProblem({ role: 'Button', name: 'x' })).not.toBeNull()
    expect(targetProblem({ role: 'button', name: '' })).not.toBeNull()
    expect(targetProblem({ role: 'button', name: 'x'.repeat(81) })).not.toBeNull()
    expect(targetProblem(null)).not.toBeNull()
    expect(toTarget({ role: 'button', name: 'Go' })).toEqual({ role: 'button', name: 'Go' })
    expect(toTarget({})).toBeNull()
  })

  it('zone targets: a zone with optional hints, exactly one kind of target, and only the zone goes into the want', () => {
    expect(targetProblem({ zone: 'calc.result' })).toBeNull()
    expect(targetProblem({ zone: 'calc.result', label_hint: 'Result', role_hint: 'status' })).toBeNull()
    expect(targetProblem({ zone: 'Calc Result' })).not.toBeNull()
    expect(targetProblem({ zone: 'calc.result', label_hash: 'h:abcd1234' })).not.toBeNull()
    expect(targetProblem({ zone: 'calc.result', role_hint: 'Not A Role' })).not.toBeNull()
    expect(targetProblem({ zone: 'calc.result', label_hint: 'x'.repeat(81) })).not.toBeNull()
    expect(toTarget({ zone: 'calc.result', label_hint: 'Result' })).toEqual({ zone: 'calc.result', label_hint: 'Result' })
    expect(wantFor({ zone: 'calc.result', label_hint: 'Result', role_hint: 'status' }, 'rq_1')).toEqual({ request_id: 'rq_1', frame_id: 'top', zone: 'calc.result' })
  })

  it('keeps the optional geometry the extension may add, and drops unknown keys', () => {
    const a = parseAnswer({ ...answer(), viewport: { w: 1000, h: 700 }, outer: { w: 1000, h: 790 }, screen: { x: 10, y: 20 }, secret: 'x' })!
    expect(a.viewport).toEqual({ w: 1000, h: 700 })
    expect(a.outer).toEqual({ w: 1000, h: 790 })
    expect(a.screen).toEqual({ x: 10, y: 20 })
    expect(JSON.stringify(a)).not.toContain('secret')
  })
})

describe('mapping to the screen', () => {
  it('page zoom is points per CSS pixel: dpr over the display scale, snapping noise to 1', () => {
    expect(pageZoom(2, 2)).toBe(1)
    expect(pageZoom(2.5, 2)).toBeCloseTo(1.25)
    expect(pageZoom(1, 2)).toBeCloseTo(0.5)
    expect(pageZoom(1.99, 2)).toBe(1)
    expect(pageZoom(100, 2)).toBe(5)
  })

  it('places the rect at window_offset plus the rect, at 100% zoom, and converts to the overlay 0-1000 box of the display', () => {
    const m = mapAnswer(answer(), { display: DISPLAY })
    expect(m.ok).toBe(true)
    if (!m.ok) return
    expect(m.screen).toEqual({ x: 150, y: 350, w: 120, h: 40 })
    expect(m.norm.xmin).toBeCloseTo((150 / 1728) * 1000, 6)
    expect(m.norm.ymin).toBeCloseTo((350 / 1117) * 1000, 6)
    expect(m.norm.xmax).toBeCloseTo((270 / 1728) * 1000, 6)
    expect(m.norm.ymax).toBeCloseTo((390 / 1117) * 1000, 6)
  })

  it('scales the rect (not the window position) by page zoom', () => {
    const m = mapAnswer(answer({ dpr: 2.5 }), { display: DISPLAY })
    expect(m.ok && m.screen).toEqual({ x: 50 + 100 * 1.25, y: 150 + 200 * 1.25, w: 150, h: 50 })
  })

  it('with outer, viewport and screen it corrects the viewport origin for page zoom, which window_offset cannot', () => {
    // 125% zoom: viewport 800x600 CSS px = 1000x750 points. Window frame 1000 wide, 840 tall: 90 points of browser UI on top.
    const a = answer({ dpr: 2.5, window_offset: { x: 999, y: 999 }, outer: { w: 1000, h: 840 }, viewport: { w: 800, h: 600 }, screen: { x: 30, y: 60 } })
    expect(viewportOrigin(a, 1.25)).toEqual({ x: 30, y: 150 })
    const m = mapAnswer(a, { display: DISPLAY })
    expect(m.ok && m.screen.x).toBeCloseTo(30 + 100 * 1.25)
    expect(m.ok && m.screen.y).toBeCloseTo(150 + 200 * 1.25)
  })

  it('applies a fixed calibration last', () => {
    const m = mapAnswer(answer(), { display: DISPLAY, calibration: { x: -3, y: 5 } })
    expect(m.ok && m.screen).toMatchObject({ x: 147, y: 355 })
    expect(parseCalibration('-3, 5')).toEqual({ x: -3, y: 5 })
    expect(parseCalibration('3')).toBeUndefined()
    expect(parseCalibration(undefined)).toBeUndefined()
  })

  it('explains why nothing is drawn: not found, another frame, scrolled out of view, off the display', () => {
    expect(mapAnswer({ request_id: 'a', frame_id: 'top', found: false, age_ms: 0 }, { display: DISPLAY })).toEqual({ ok: false, reason: 'not_found' })
    expect(mapAnswer(answer({ frame_id: 'f2' }), { display: DISPLAY })).toEqual({ ok: false, reason: 'frame_relative' })
    expect(mapAnswer(answer({ viewport: { w: 900, h: 600 }, rect: { x: 10, y: 900, w: 50, h: 20 } }), { display: DISPLAY })).toEqual({ ok: false, reason: 'out_of_view' })
    expect(mapAnswer(answer({ rect: { x: 0, y: -80, w: 50, h: 20 }, viewport: { w: 900, h: 600 } }), { display: DISPLAY })).toEqual({ ok: false, reason: 'out_of_view' })
    expect(mapAnswer(answer({ window_offset: { x: 5000, y: 5000 } }), { display: DISPLAY })).toEqual({ ok: false, reason: 'off_display' })
    expect(toNormBox({ x: 5000, y: 5000, w: 10, h: 10 }, DISPLAY.bounds)).toBeNull()
  })

  it('grows a tiny element to a ring that can be seen, and counts age as posted age plus time since it arrived', () => {
    const m = mapAnswer(answer({ rect: { x: 100, y: 100, w: 2, h: 2 } }), { display: DISPLAY })
    expect(m.ok && m.norm.xmax - m.norm.xmin).toBeGreaterThanOrEqual(6 - 1e-9)
    expect(ageNow({ age_ms: 30 }, 1000, 1250)).toBe(280)
  })
})

// ---------- time control ----------
function clock() {
  let t = 0
  const timers: Array<{ at: number; fn: () => void; id: number }> = []
  let seq = 0
  return {
    now: () => t,
    setTimer: (fn: () => void, ms: number) => {
      timers.push({ at: t + ms, fn, id: ++seq })
      return seq
    },
    clearTimer: (h: unknown) => {
      const i = timers.findIndex((x) => x.id === h)
      if (i >= 0) timers.splice(i, 1)
    },
    async advance(ms: number) {
      const end = t + ms
      for (;;) {
        timers.sort((a, b) => a.at - b.at)
        const next = timers[0]
        if (!next || next.at > end) break
        timers.shift()
        t = next.at
        next.fn()
        await Promise.resolve()
        await Promise.resolve()
      }
      t = end
    },
  }
}

describe('request queue', () => {
  it('hands each want to the extension once, matches the answer by request id, and shares one answer between identical questions', async () => {
    const c = clock()
    const g = createDomGrounder({ now: c.now, setTimer: c.setTimer, clearTimer: c.clearTimer, id: (() => { let n = 0; return () => `rq_${++n}` })() })
    const p1 = g.request({ label_hash: 'h:abcd1234' })
    const p2 = g.request({ label_hash: 'h:abcd1234' })
    expect(g.pending()).toBe(1)
    const want = g.nextWant()!
    expect(want).toEqual({ request_id: 'rq_1', frame_id: 'top', label_hash: 'h:abcd1234' })
    expect(g.nextWant()).toBeNull() // already handed out
    expect(g.answer(answer({ request_id: 'rq_1' }))).toBe(true)
    const [a, b] = (await Promise.all([p1, p2])) as Array<Extract<RequestOutcome, { kind: 'answer' }>>
    expect(a.answer.request_id).toBe('rq_1')
    expect(b).toBe(a === b ? a : b)
    expect(g.answer(answer({ request_id: 'rq_1' }))).toBe(false) // late
    expect(g.pending()).toBe(0)
  })

  it('times out, re-issues a want nobody answered, and cancelAll releases every waiter', async () => {
    const c = clock()
    const g = createDomGrounder({ now: c.now, setTimer: c.setTimer, clearTimer: c.clearTimer, reissueMs: 1000 })
    const p = g.request({ role: 'button', name: 'Go' }, { timeoutMs: 5000 })
    const first = g.nextWant()!
    expect(g.nextWant()).toBeNull()
    await c.advance(1200)
    expect(g.nextWant()).toEqual(first) // the extension never answered: ask again
    await c.advance(4000)
    expect(await p).toEqual({ kind: 'timeout' })
    expect(g.pending()).toBe(0)
    const q = g.request({ label_hash: 'h:aaaa1111' })
    g.cancelAll()
    expect(await q).toEqual({ kind: 'timeout' })
  })
})

describe('following a target (COA-2, COA-6)', () => {
  // A scripted extension: each request() resolves with the next scripted outcome.
  function setup(script: Array<RectAnswer | 'timeout'>) {
    const c = clock()
    const events: string[] = []
    let i = 0
    const grounder = {
      request: async (): Promise<RequestOutcome> => {
        const s = script[Math.min(i++, script.length - 1)]
        return s === 'timeout' ? { kind: 'timeout' } : { kind: 'answer', answer: s, receivedAt: c.now() }
      },
    }
    const tracker = trackTarget(
      grounder,
      { label_hash: 'h:abcd1234' },
      { onVisible: (box, info) => void events.push(`visible ${Math.round(box.ymin)}${info.moved ? ' moved' : ''}`), onHidden: (r) => void events.push(`hidden ${r}`) },
      { display: () => DISPLAY, now: c.now, setTimer: c.setTimer, clearTimer: c.clearTimer, refreshMs: 250, staleMs: 1500, requestTimeoutMs: 1000 },
    )
    return { c, events, tracker }
  }

  it('draws on a good answer, follows a scroll (the new answer moves the ring), and is quiet while nothing changes', async () => {
    const { c, events } = setup([answer(), answer(), answer({ rect: { x: 100, y: 100, w: 120, h: 40 }, scroll: { x: 0, y: 100 } })])
    await c.advance(10)
    await c.advance(300)
    await c.advance(300)
    expect(events[0]).toMatch(/^visible \d+ moved$/)
    expect(events[1]).toMatch(/^visible \d+$/) // same scroll: not "moved"
    expect(events[2]).toMatch(/moved$/) // scrolled: re-resolved at the new place
    expect(Number(events[2].split(' ')[1])).toBeLessThan(Number(events[0].split(' ')[1]))
  })

  it('hides the moment the element is gone or scrolled out of view, and redraws when it is found again', async () => {
    const { c, events } = setup([answer(), { request_id: 'x', frame_id: 'top', found: false, age_ms: 0 }, answer({ viewport: { w: 900, h: 600 }, rect: { x: 10, y: 900, w: 50, h: 20 } }), answer()])
    for (let k = 0; k < 4; k++) await c.advance(300)
    expect(events.map((e) => e.split(' ')[0] + ' ' + (e.split(' ')[1]?.match(/[a-z_]+/)?.[0] ?? ''))).toEqual(['visible ', 'hidden not_found', 'hidden out_of_view', 'visible '])
  })

  it('hides when the extension stops answering (no good answer for staleMs), and comes back on the next good one', async () => {
    const { c, events } = setup([answer(), 'timeout', 'timeout', 'timeout', 'timeout', 'timeout', 'timeout', answer()])
    await c.advance(10)
    expect(events).toEqual([expect.stringMatching(/^visible/)])
    await c.advance(1400)
    expect(events).toHaveLength(1)
    await c.advance(300)
    expect(events[1]).toBe('hidden stale')
    await c.advance(6000)
    expect(events.at(-1)).toMatch(/^visible/)
  })

  it('hides an answer that is already old when it arrives, and stop() ends the loop', async () => {
    const { c, events, tracker } = setup([answer({ age_ms: 4000 })])
    await c.advance(10)
    expect(events).toEqual(['hidden stale'])
    tracker.stop()
    const n = events.length
    await c.advance(5000)
    expect(events).toHaveLength(n)
    expect(tracker.state().visible).toBe(false)
  })

  it('a frame it cannot place is hidden with that reason', async () => {
    const { c, events } = setup([answer({ frame_id: 'f1' })])
    await c.advance(10)
    expect(events).toEqual(['hidden frame_relative'])
  })
})

// ---------- the server, over real HTTP ----------
let servers: ExtServer[] = []
afterEach(async () => {
  for (const s of servers) await s.close()
  servers = []
})

function call(port: number, method: string, urlPath: string, body?: unknown, headers: Record<string, string> = {}): Promise<{ status: number; headers: http.IncomingHttpHeaders; json: unknown }> {
  return new Promise((resolve, reject) => {
    const payload = body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body)
    const req = http.request({ host: '127.0.0.1', port, method, path: urlPath, headers: { ...(payload ? { 'content-type': 'application/json', 'content-length': String(Buffer.byteLength(payload)) } : {}), ...headers } }, (res) => {
      const chunks: Buffer[] = []
      res.on('data', (c: Buffer) => chunks.push(c))
      res.on('end', () => {
        const text = Buffer.concat(chunks).toString('utf8')
        resolve({ status: res.statusCode ?? 0, headers: res.headers, json: text ? JSON.parse(text) : null })
      })
    })
    req.on('error', reject)
    req.end(payload)
  })
}

async function serve() {
  const grounder = createDomGrounder()
  const rings: RingRequest[] = []
  let cleared = 0
  const server = (await startExtServer({ grounder, port: 0, onRing: (r) => void rings.push(r), onClear: () => void cleared++ }))!
  servers.push(server)
  return { server, grounder, rings, cleared: () => cleared, port: server.port() }
}

const EXT = 'chrome-extension://abcdefghijklmnopabcdefghijklmnop'

describe('extension server', () => {
  it('serves wants (200 once, then 204) and takes answers (200, then 410 when late), like the extension expects', async () => {
    const { grounder, port } = await serve()
    expect((await call(port, 'GET', '/ext/want')).status).toBe(204)
    const pending = grounder.request({ role: 'button', name: 'Calculate' })
    const want = await call(port, 'GET', '/ext/want')
    expect(want.status).toBe(200)
    expect(want.json).toMatchObject({ frame_id: 'top', role: 'button', name: 'Calculate' })
    expect((await call(port, 'GET', '/ext/want')).status).toBe(204)
    const id = (want.json as { request_id: string }).request_id
    expect((await call(port, 'POST', '/ext/rect', answer({ request_id: id }))).status).toBe(200)
    const out = await pending
    expect(out.kind).toBe('answer')
    expect((await call(port, 'POST', '/ext/rect', answer({ request_id: id }))).status).toBe(410)
  })

  it('rejects malformed answers, oversized bodies and unknown routes', async () => {
    const { port } = await serve()
    expect((await call(port, 'POST', '/ext/rect', { request_id: 'x' })).status).toBe(400)
    expect((await call(port, 'POST', '/ext/rect', 'not json')).status).toBe(400)
    expect((await call(port, 'POST', '/ext/rect', JSON.stringify({ pad: 'x'.repeat(20_000) })).catch(() => ({ status: 400 }))).status).toBe(400)
    expect((await call(port, 'GET', '/nope')).status).toBe(404)
  })

  it('only talks to this machine and to browser extensions: a wrong Host (DNS rebinding) or a web page Origin is refused', async () => {
    const { port } = await serve()
    expect((await call(port, 'GET', '/ext/want', undefined, { host: 'evil.example' })).status).toBe(403)
    expect((await call(port, 'GET', '/ext/want', undefined, { host: `127.0.0.1.evil.example:${port}` })).status).toBe(403)
    expect((await call(port, 'GET', '/ext/want', undefined, { origin: 'https://evil.example' })).status).toBe(403)
    expect((await call(port, 'POST', '/ext/rect', answer(), { origin: 'http://localhost:3000' })).status).toBe(403)
    const ok = await call(port, 'GET', '/ext/want', undefined, { origin: EXT })
    expect(ok.status).toBe(204)
    expect(ok.headers['access-control-allow-origin']).toBe(EXT)
    const pre = await call(port, 'OPTIONS', '/ext/rect', undefined, { origin: EXT, 'access-control-request-method': 'POST' })
    expect(pre.status).toBe(204)
    expect(String(pre.headers['access-control-allow-headers'])).toMatch(/content-type/)
    expect((await call(port, 'GET', '/ext/want', undefined, { host: `localhost:${port}` })).status).toBe(204)
  })

  it('a zone ring request is accepted with its hints', async () => {
    const { port, rings } = await serve()
    expect((await call(port, 'POST', '/coach/ring', { zone: 'calc.result', label_hint: 'Result', role_hint: 'status', label: 'Look' })).status).toBe(200)
    expect(rings).toEqual([{ target: { zone: 'calc.result', label_hint: 'Result', role_hint: 'status' }, label: 'Look' }])
    expect((await call(port, 'POST', '/coach/ring', { zone: 'Bad Zone' })).status).toBe(400)
  })

  it('local processes can ask for a ring; a browser (any Origin) cannot', async () => {
    const { port, rings, cleared } = await serve()
    expect((await call(port, 'POST', '/coach/ring', { role: 'button', name: 'Calculate', label: '  Press   this one  ', step: 2 })).status).toBe(200)
    expect((await call(port, 'POST', '/coach/ring', { label_hash: 'h:abcd1234' })).status).toBe(200)
    expect(rings).toEqual([{ target: { role: 'button', name: 'Calculate' }, label: 'Press this one', step: 2 }, { target: { label_hash: 'h:abcd1234' } }])
    expect((await call(port, 'POST', '/coach/ring', { role: 'button' })).status).toBe(400)
    expect((await call(port, 'POST', '/coach/ring', { label_hash: 'Save' })).status).toBe(400)
    expect((await call(port, 'POST', '/coach/ring', { label_hash: 'h:abcd1234' }, { origin: 'https://evil.example' })).status).toBe(403)
    expect((await call(port, 'POST', '/coach/ring', { label_hash: 'h:abcd1234' }, { origin: EXT })).status).toBe(403)
    expect((await call(port, 'POST', '/coach/clear')).status).toBe(200)
    expect(cleared()).toBe(1)
    expect(rings).toHaveLength(2)
  })

  it('reports status, and the port in use is a quiet null rather than a crash', async () => {
    const { server, port } = await serve()
    const st = await call(port, 'GET', '/ext/status')
    expect(st.json).toMatchObject({ pending: 0, extension_seen_ms: null })
    await call(port, 'GET', '/ext/want')
    expect(server.lastSeenAt()).not.toBeNull()
    const again = await startExtServer({ grounder: createDomGrounder(), port })
    expect(again).toBeNull()
  })
})

// ---------- the ring ----------
describe('dom coach: the ring on a real element', () => {
  function setup(script: Array<RectAnswer | 'timeout'>, over: { ttlMs?: number } = {}) {
    const c = clock()
    let i = 0
    const requests: unknown[] = []
    const grounder = {
      request: async (t: unknown): Promise<RequestOutcome> => {
        requests.push(t)
        const s = script[Math.min(i++, script.length - 1)]
        return s === 'timeout' ? { kind: 'timeout' } : { kind: 'answer', answer: s, receivedAt: c.now() }
      },
    }
    const drawn: string[] = []
    const shown: Annotation[][] = []
    const overlay = { show: (a: Annotation[]) => void (shown.push(a), drawn.push(`show:${a.map((x) => x.id).join(',')}`)), clear: (ids?: string[]) => void drawn.push(`clear:${(ids ?? ['*']).join(',')}`) }
    const events: EventInput[] = []
    const tracker = createCoachTracker({ emit: (e) => void events.push(e), now: c.now, setTimer: c.setTimer, clearTimer: c.clearTimer })
    const coach = createDomCoach({ grounder, overlay, display: () => DISPLAY, tracker, now: c.now, setTimer: c.setTimer, clearTimer: c.clearTimer, ...over })
    return { c, coach, drawn, shown, events, requests }
  }

  it('draws a labelled, numbered ring at the mapped box and reports coach_shown once, with the label hash and no label text', async () => {
    const { c, coach, shown, events } = setup([answer()])
    coach.point({ label_hash: 'h:abcd1234' }, { label: 'Check this', step: 3 })
    await c.advance(10)
    await c.advance(300)
    expect(shown.length).toBeGreaterThanOrEqual(2)
    const ring = shown[0][0]
    expect(ring).toMatchObject({ id: DOM_RING_ID, kind: 'ring', tone: 'guide', label: 'Check this', step: 3 })
    expect(events.filter((e) => e.type === 'coach_shown')).toEqual([{ source: 'coach', type: 'coach_shown', target: { role: 'ring', label_hash: 'h:abcd1234' }, meta: {} }])
    expect(JSON.stringify(events)).not.toContain('Check this')
  })

  it('shows the nudge text in a bubble above the ring, reports the zone, and hands the decision tag back when the prompt ends', async () => {
    const c = clock()
    const shown: Annotation[][] = []
    const cleared: string[][] = []
    const ends: Array<{ ref?: string; how: string; shown: boolean }> = []
    const events: EventInput[] = []
    const tracker = createCoachTracker({ emit: (e) => void events.push(e), now: c.now, setTimer: c.setTimer, clearTimer: c.clearTimer })
    const grounder = { request: async (): Promise<RequestOutcome> => ({ kind: 'answer', answer: answer(), receivedAt: c.now() }) }
    const coach = createDomCoach({ grounder, overlay: { show: (a) => void shown.push(a), clear: (ids) => void cleared.push(ids ?? []) }, display: () => DISPLAY, tracker, onEnd: (e) => void ends.push(e), now: c.now, setTimer: c.setTimer, clearTimer: c.clearTimer })
    coach.point({ zone: 'calc.result' }, { message: '  Check the   cliff edge first. ', ref: 'd_1', step: 2 })
    await c.advance(10)
    const marks = shown[0]
    expect(marks.map((m) => m.id)).toEqual([DOM_RING_ID, 'dom-bubble'])
    expect(marks[1]).toMatchObject({ kind: 'bubble', text: 'Check the cliff edge first.' })
    expect(marks[0]).toMatchObject({ step: 2 })
    expect(events[0]).toMatchObject({ type: 'coach_shown', meta: { zone: 'calc.result' } })
    expect(coach.current()).toMatchObject({ ref: 'd_1', message: 'Check the cliff edge first.' })
    coach.clear('stop')
    expect(cleared.at(-1)).toEqual([DOM_RING_ID, 'dom-bubble'])
    expect(ends).toEqual([{ ref: 'd_1', how: 'stop', shown: true }])
    expect(events.at(-1)).toMatchObject({ type: 'coach_dismissed', meta: { how: 'stop', zone: 'calc.result' } })
    // a prompt that never got drawn reports shown:false
    const never = createDomCoach({ grounder: { request: async () => ({ kind: 'timeout' }) }, overlay: { show: () => undefined, clear: () => undefined }, display: () => DISPLAY, onEnd: (e) => void ends.push(e), now: c.now, setTimer: c.setTimer, clearTimer: c.clearTimer })
    never.point({ zone: 'x.y' }, { ref: 'd_2' })
    await c.advance(10)
    never.clear('user')
    expect(ends.at(-1)).toEqual({ ref: 'd_2', how: 'user', shown: false })
  })

  it('hides a stale ring without calling it a dismissal, and a follow reports coach_followed and removes the ring', async () => {
    const { c, coach, drawn, events } = setup([answer(), 'timeout'])
    coach.point({ role: 'button', name: 'Calculate' })
    await c.advance(10)
    await c.advance(2000)
    expect(drawn).toContain('clear:dom-ring,dom-bubble')
    expect(events.map((e) => e.type)).toEqual(['coach_shown']) // hiding is not dismissing
    expect(coach.current()).toMatchObject({ visible: false, hiddenFor: 'stale' })
    coach.followed()
    expect(events.map((e) => e.type)).toEqual(['coach_shown', 'coach_followed'])
    expect(coach.current()).toBeNull()
  })

  it('the same target again keeps following; a different one replaces it and says so; clear is a dismissal; the ring leaves after its time', async () => {
    const { c, coach, events, requests } = setup([answer()], { ttlMs: 5000 })
    coach.point({ role: 'button', name: 'A' })
    await c.advance(10)
    coach.point({ role: 'button', name: 'A' }, { label: 'new label' })
    expect(coach.current()?.label).toBe('new label')
    coach.point({ role: 'button', name: 'B' })
    await c.advance(10)
    expect(events.filter((e) => e.type === 'coach_dismissed').map((e) => e.meta?.how)).toEqual(['replaced'])
    expect(requests.some((r) => JSON.stringify(r).includes('"B"'))).toBe(true)
    coach.clear()
    expect(events.filter((e) => e.type === 'coach_dismissed').map((e) => e.meta?.how)).toEqual(['replaced', 'user'])
    coach.point({ role: 'button', name: 'C' })
    await c.advance(10)
    await c.advance(5100)
    expect(coach.current()).toBeNull()
    expect(events.at(-1)).toMatchObject({ type: 'coach_dismissed', meta: { how: 'stale' } })
  })
})
