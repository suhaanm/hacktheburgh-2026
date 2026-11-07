// The optional `content` field of the element-rect answer (page boxes for the overlay): parsing, mapping to the screen, and the server.
import fs from 'node:fs'
import http from 'node:http'
import path from 'node:path'
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { afterEach, describe, expect, it } from 'vitest'
import { createDomGrounder, mapContentRects as mapContentRectsViaGrounder, trackTarget } from './dom-grounder'
import { startExtServer, type ExtServer } from './ext-server'
import { CONTENT_MAX, parseAnswer, parseContent, type ContentBox, type RectAnswer } from './protocol'
import { mapAnswer, mapContentRects, type DisplayInfo } from './rect-map'

const SCHEMA_FILE = path.resolve(__dirname, '../../../../../packages/schema/ext_rect.schema.json')
const DISPLAY: DisplayInfo = { bounds: { x: 0, y: 0, width: 1728, height: 1117 }, scaleFactor: 2 }

// a raw answer as the extension posts it (JSON-shaped, so unknown)
const raw = (over: Record<string, unknown> = {}): Record<string, unknown> => ({
  request_id: 'rq_1',
  frame_id: 'top',
  found: true,
  rect: { x: 100, y: 50, w: 200, h: 100 },
  window_offset: { x: 50, y: 150 },
  scroll: { x: 0, y: 0 },
  dpr: 2,
  viewport: { w: 1000, h: 500 },
  outer: { w: 1000, h: 590 },
  screen: { x: 10, y: 20 },
  age_ms: 20,
  ...over,
})
const answer = (over: Partial<RectAnswer> = {}): RectAnswer => parseAnswer(raw(over as Record<string, unknown>))!

describe.skipIf(!fs.existsSync(SCHEMA_FILE))('content against packages/schema/ext_rect.schema.json', () => {
  const schema = JSON.parse(fs.readFileSync(SCHEMA_FILE, 'utf8')) as { $defs: Record<string, unknown> }
  const ajv = new Ajv2020({ strict: false, allErrors: true })
  addFormats(ajv)
  const validAnswer = ajv.compile({ $ref: '#/$defs/RectAnswer', $defs: schema.$defs })

  it('an answer the schema accepts with content parses to the same content, and one it rejects does not slip through the parser', () => {
    const boxes = [[100, 100, 300, 300], [0, 0, 1000, 1000], [500, 20, 550, 120]]
    const ok = raw({ content: boxes })
    expect(validAnswer(ok), JSON.stringify(validAnswer.errors)).toBe(true)
    expect(parseAnswer(ok)!.content).toEqual(boxes)
    // what the schema rejects is cleaned, not passed on
    for (const bad of [[[1, 2, 3]], ['text'], [[1.5, 2, 3, 4]], [[-1, 2, 3, 4]], [[1, 2, 3, 1001]]]) {
      expect(validAnswer(raw({ content: bad }))).toBe(false)
      expect(parseAnswer(raw({ content: bad }))!.content).not.toEqual(bad)
    }
    expect(validAnswer(raw({ content: Array.from({ length: 81 }, () => [1, 1, 2, 2]) }))).toBe(false)
    expect(parseAnswer(raw({ content: Array.from({ length: 81 }, () => [1, 1, 2, 2]) }))!.content).toEqual([])
  })
})

describe('parsing content', () => {
  it('a valid answer round-trips: content is kept as sent, in order', () => {
    const boxes: ContentBox[] = [[100, 100, 300, 300], [0, 0, 1000, 1000], [500, 20, 550, 120], [7, 7, 7, 7]]
    const a = parseAnswer(raw({ content: boxes }))!
    expect(a.content).toEqual(boxes)
    expect(JSON.parse(JSON.stringify(a))).toEqual(JSON.parse(JSON.stringify({ ...raw(), content: boxes })))
    expect(a.rect).toEqual({ x: 100, y: 50, w: 200, h: 100 })   // nothing else changed
  })

  it('an answer without content still parses; the key is simply absent (content is undefined, not [])', () => {
    const a = parseAnswer(raw())!
    expect(a).not.toBeNull()
    expect(a.content).toBeUndefined()
    expect('content' in a).toBe(false)
    expect(parseAnswer(raw({ content: [] }))!.content).toEqual([])
  })

  it('content that is not an array, or is oversized, becomes an empty array and the rest of the answer survives', () => {
    for (const v of ['text', 12, true, null, {}, { length: 2, 0: [1, 1, 2, 2] }, Array.from({ length: CONTENT_MAX + 1 }, () => [1, 1, 2, 2])]) {
      const a = parseAnswer(raw({ content: v }))
      expect(a, JSON.stringify(v)).not.toBeNull()
      expect(a!.content, JSON.stringify(v).slice(0, 30)).toEqual([])
      expect(a!.rect).toEqual({ x: 100, y: 50, w: 200, h: 100 })
    }
    expect(parseAnswer(raw({ content: Array.from({ length: CONTENT_MAX }, (_, i) => [i, 0, i + 1, 5]) }))!.content).toHaveLength(80)
  })

  it('drops entries that are not exactly four finite integers, keeping the good ones around them in order', () => {
    const dirty: unknown[] = [
      [1, 2, 3, 4],
      [1, 2, 3], [1, 2, 3, 4, 5], [], 'a text', null, undefined, 7, {}, { 0: 1, 1: 2, 2: 3, 3: 4, length: 4 },
      [1, 2, 3, Number.NaN], [1, 2, 3, Number.POSITIVE_INFINITY], [Number.NEGATIVE_INFINITY, 2, 3, 4],
      [1.5, 2, 3, 4], [1, 2, 3, 4.0000001], ['1', 2, 3, 4], [1, 2, 3, null], [1, 2, 3, undefined], [[1], 2, 3, 4], [true, 2, 3, 4],
      [5, 6, 7, 8],
    ]
    expect(parseAnswer(raw({ content: dirty }))!.content).toEqual([[1, 2, 3, 4], [5, 6, 7, 8]])
    expect(parseContent(dirty)).toEqual([[1, 2, 3, 4], [5, 6, 7, 8]])
  })

  it('drops boxes whose corners are the wrong way round (y0 > y1 or x0 > x1), and keeps degenerate ones', () => {
    expect(parseContent([[300, 100, 100, 300], [100, 300, 300, 100], [100, 100, 100, 100], [0, 0, 0, 10]])).toEqual([[100, 100, 100, 100], [0, 0, 0, 10]])
  })

  it('clamps out-of-range integers to 0..1000 (and checks the order after clamping)', () => {
    expect(parseContent([[-5, 0, 1200, 2000], [-50, -40, -5, 10], [900, 900, 5000, 5000], [1500, 0, 2000, 10]])).toEqual([[0, 0, 1000, 1000], [0, 0, 0, 10], [900, 900, 1000, 1000], [1000, 0, 1000, 10]])
  })

  it('never throws, whatever it is given', () => {
    const thrower = (): never => { throw new Error('hostile') }
    const hostile: unknown[] = [
      new Proxy([], { get: thrower }),
      new Proxy([[1, 2, 3, 4]], { get: (t, k) => (k === 'length' ? 1 : thrower()) }),
      Object.defineProperty([[1, 2, 3, 4]], 0, { get: thrower }),
      Object.defineProperty([[1, 2, 3, 4]], 'length', { value: 1e9 }),
      [Object.defineProperty([1, 2, 3, 4], 0, { get: thrower })],
      Symbol('x'), () => 1, BigInt(3), [[BigInt(1), 2, 3, 4]],
    ]
    for (const h of hostile) {
      expect(() => parseContent(h)).not.toThrow()
      expect(() => parseAnswer(raw({ content: h }))).not.toThrow()
    }
    const readThrows = raw()
    Object.defineProperty(readThrows, 'content', { enumerable: true, get: thrower })
    expect(() => parseAnswer(readThrows)).not.toThrow()
    expect(parseAnswer(readThrows)!.content).toEqual([])
    const deep: unknown[] = []
    for (let i = 0, cur = deep; i < 5000; i++) { const n: unknown[] = []; cur.push(n); cur = n }
    expect(() => parseContent(deep)).not.toThrow()
  })

  it('content on a found:false answer is ignored', () => {
    const a = parseAnswer({ request_id: 'rq', frame_id: 'top', found: false, age_ms: 0, content: [[1, 2, 3, 4]] })!
    expect(a).toEqual({ request_id: 'rq', frame_id: 'top', found: false, age_ms: 0 })
  })

  it('the parsed answer carries only numbers in content, never a string from the sender', () => {
    const a = parseAnswer(raw({ content: [[1, 2, 3, 4], ['zqxText', 'x', 'y', 'z'], 'zqxText'] }))!
    expect(JSON.stringify(a)).not.toContain('zqx')
  })
})

describe('mapping content to the screen', () => {
  const content: ContentBox[] = [[100, 100, 300, 300], [500, 20, 550, 120], [0, 0, 1000, 1000]]
  const opts = { display: DISPLAY }

  it('a content box that coincides with the answered rect maps to the same screen rect as the rect (exactly, for several geometries)', () => {
    // rect {100,50,200,100} on a 1000 x 500 viewport is the grid box [100,100,300,300]
    const cases: Array<[string, RectAnswer, { calibration?: { x: number; y: number } }]> = [
      ['outer, viewport and screen', answer({ content }), {}],
      ['the same with a calibration', answer({ content }), { calibration: { x: -3, y: 5 } }],
      ['only window_offset (older extension)', answer({ content, outer: undefined, screen: undefined }), {}],
      ['page zoom 125%', answer({ content, dpr: 2.5, viewport: { w: 800, h: 400 }, rect: { x: 80, y: 40, w: 160, h: 80 } }), {}],
      ['1x display', answer({ content, dpr: 1 }), {}],
    ]
    for (const [name, a, extra] of cases) {
      const o = { display: name === '1x display' ? { ...DISPLAY, scaleFactor: 1 } : DISPLAY, ...extra }
      const m = mapAnswer(a, o)
      expect(m.ok, name).toBe(true)
      const rects = mapContentRects(a, o)
      expect(rects, name).toHaveLength(content.length)
      expect(rects[0], name).toEqual(m.ok ? m.screen : null)
    }
    // spot value: viewport origin (10, 20 + 90), zoom 1
    expect(mapContentRects(answer({ content }), opts)[0]).toEqual({ x: 110, y: 160, w: 200, h: 100 })
  })

  it('maps every box, in order, with the same origin, zoom and calibration as the rect', () => {
    const a = answer({ content })
    const r = mapContentRects(a, { ...opts, calibration: { x: 2, y: -4 } })
    expect(r).toEqual([
      { x: 112, y: 156, w: 200, h: 100 },       // [100,100,300,300]
      { x: 10 + 20 + 2, y: 110 + 250 - 4, w: 100, h: 25 },   // [500,20,550,120]: x 20..120, y 250..275
      { x: 12, y: 106, w: 1000, h: 500 },       // the whole viewport
    ])
    expect(mapContentRectsViaGrounder).toBe(mapContentRects)
  })

  it('is empty when there is nothing to place: no content, not found, frame-relative, no viewport, no dpr', () => {
    expect(mapContentRects(answer(), opts)).toEqual([])
    expect(mapContentRects(answer({ content: [] }), opts)).toEqual([])
    expect(mapContentRects({ request_id: 'a', frame_id: 'top', found: false, age_ms: 0 }, opts)).toEqual([])
    expect(mapContentRects(answer({ content, frame_id: 'f2' }), opts)).toEqual([])
    expect(mapContentRects(answer({ content, viewport: undefined }), opts)).toEqual([])
    expect(mapContentRects({ ...answer({ content }), viewport: { w: 0, h: 500 } }, opts)).toEqual([])
    expect(mapContentRects({ ...answer({ content }), dpr: undefined }, opts)).toEqual([])
  })

  it('does not depend on the answered rect being in view', () => {
    const a = answer({ content, rect: { x: 10, y: 9000, w: 50, h: 20 } })
    expect(mapAnswer(a, opts)).toEqual({ ok: false, reason: 'out_of_view' })
    expect(mapContentRects(a, opts)).toHaveLength(3)
  })

  it('the tracker hands the mapped content to the Cue wiring beside the ring box', async () => {
    const grounder = createDomGrounder()
    const seen: Array<{ content: unknown }> = []
    const tracker = trackTarget(grounder, { zone: 'calc_result' }, { onVisible: (_box, info) => void seen.push({ content: info.content }), onHidden: () => undefined }, { display: () => DISPLAY, setTimer: () => 1, clearTimer: () => undefined })
    const want = grounder.nextWant()!
    grounder.answer(answer({ request_id: want.request_id, content }))
    await new Promise((r) => setTimeout(r, 0))
    tracker.stop()
    expect(seen).toHaveLength(1)
    expect(seen[0]!.content).toEqual(mapContentRects(answer({ content }), opts))
  })
})

// ---------- the real server ----------
let servers: ExtServer[] = []
afterEach(async () => {
  for (const s of servers) await s.close()
  servers = []
})

function post(port: number, body: unknown): Promise<{ status: number; bytes: number }> {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body)
    const req = http.request({ host: '127.0.0.1', port, method: 'POST', path: '/ext/rect', headers: { 'content-type': 'application/json', 'content-length': String(Buffer.byteLength(payload)) } }, (res) => {
      res.resume()
      res.on('end', () => resolve({ status: res.statusCode ?? 0, bytes: Buffer.byteLength(payload) }))
    })
    req.on('error', reject)
    req.end(payload)
  })
}

describe('the extension server and content', () => {
  it('an answer with 80 boxes of the widest numbers, and every other field, fits the 8 KiB body cap and reaches the grounder', async () => {
    const grounder = createDomGrounder()
    const server = (await startExtServer({ grounder, port: 0 }))!
    servers.push(server)
    const pending = grounder.request({ role: 'button', name: 'Calculate' })
    const want = grounder.nextWant()!
    const boxes = Array.from({ length: 80 }, () => [1000, 1000, 1000, 1000])
    const res = await post(server.port(), raw({ request_id: want.request_id, content: boxes, scroll: { x: 12345.6789, y: 98765.4321 } }))
    expect(res.status).toBe(200)
    expect(res.bytes).toBeLessThan(4 * 1024)   // far inside MAX_BODY (8 KiB): no need to raise it
    const out = await pending
    expect(out.kind).toBe('answer')
    if (out.kind === 'answer') expect(out.answer.content).toHaveLength(80)
  })

  it('malformed content in a posted answer is cleaned, not refused, and the answer still reaches the grounder', async () => {
    const grounder = createDomGrounder()
    const server = (await startExtServer({ grounder, port: 0 }))!
    servers.push(server)
    const pending = grounder.request({ role: 'button', name: 'Calculate' })
    const want = grounder.nextWant()!
    expect((await post(server.port(), raw({ request_id: want.request_id, content: [[1, 2, 3, 4], 'zqxText', [9, 9, 1, 1]] }))).status).toBe(200)
    const out = await pending
    expect(out.kind === 'answer' && out.answer.content).toEqual([[1, 2, 3, 4]])
  })
})
