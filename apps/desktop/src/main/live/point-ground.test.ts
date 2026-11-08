import { describe, expect, it } from 'vitest'
import type { RectAnswer } from '../dom-ground/protocol'
import type { DomTarget } from '../dom-ground/protocol'
import { chainGround, createDomPointPort, createKnackWindowGround, createScreenGate, domTargets, nameTokens, parseKnackElements, pickByName, type KnackElement } from './point-ground'
import { buildMenu, createToolHost } from './tool-host'
import type { GroundAnswer, GroundPort } from './ports'

const DISPLAY = { bounds: { x: 0, y: 0, width: 1440, height: 900 }, scaleFactor: 2 }
const menu = (d: string) => ({ menu: buildMenu(d, []) })
const el = (name: string, x = 10, y = 10, w = 120, h = 32): KnackElement => ({ name, x, y, w, h })

describe('what a description names', () => {
  it('keeps the naming words and drops colours, positions and kinds of control', () => {
    expect(nameTokens('the green Submit button')).toEqual(['submit'])
    expect(nameTokens('the Needs you list in the sidebar')).toEqual(['needs', 'you'])
    expect(nameTokens('the big red button at the top left')).toEqual([])
    expect(nameTokens('Save application')).toEqual(['save', 'application'])
    expect(nameTokens('a b c d e f g h i j').length).toBeLessThanOrEqual(6)
  })
  it('turns a description into at most three role and name wants', () => {
    expect(domTargets('the green Submit button')).toEqual([{ role: 'button', name: 'submit' }, { role: 'link', name: 'submit' }])
    expect(domTargets('the Settings link')[0]).toEqual({ role: 'link', name: 'settings' })
    expect(domTargets('the search field')[0]).toEqual({ role: 'textbox', name: 'search' })
    const t = domTargets('the Email address field')
    expect(t[0]).toEqual({ role: 'textbox', name: 'email address' })
    expect(t.length).toBeLessThanOrEqual(3)
    expect(domTargets('the big red button')).toEqual([])
  })
})

describe('the Knack window', () => {
  const els = [el('Home', 10, 100), el('Needs you', 10, 140), el('Needs you 2', 10, 300), el('Routines', 10, 180), el('Your data', 10, 260), el('Show my week', 400, 500)]
  it('finds the sidebar row by its name, preferring the shortest name', () => {
    expect(pickByName('the Needs you list in the sidebar', els)?.y).toBe(140)
    expect(pickByName('Routines', els)?.name).toBe('Routines')
    expect(pickByName('where my data is', els)).toBeNull() // every naming word (where, data, is) must be in one name
  })
  it('never guesses: a tie, no match, or nothing to name is null', () => {
    expect(pickByName('Needs', [el('Needs one'), el('Needs two')])).toBeNull()
    expect(pickByName('the Billing button', els)).toBeNull()
    expect(pickByName('the big red button', els)).toBeNull()
  })
  it('answers with the element box on the display grid, and nothing when the window is not on screen', async () => {
    const port = createKnackWindowGround({ elements: async () => els, content: () => ({ x: 100, y: 50, zoom: 1 }), display: () => DISPLAY })
    const a = (await port.ground(menu('the Needs you list in the sidebar'))) as GroundAnswer
    expect(a).toMatchObject({ chosen: 't0', source: 'dom' })
    // x: 100 + 10 = 110 to 230 of 1440; y: 50 + 140 = 190 to 222 of 900; all on the 0..1000 grid
    expect(a.box_2d?.map((n) => Math.round(n * 10) / 10)).toEqual([211.1, 76.4, 246.7, 159.7])
    const hidden = createKnackWindowGround({ elements: async () => null, content: () => null, display: () => DISPLAY })
    expect(await hidden.ground(menu('Needs you'))).toBeNull()
    const noEls = createKnackWindowGround({ elements: async () => null, content: () => ({ x: 0, y: 0, zoom: 1 }), display: () => DISPLAY })
    expect(await noEls.ground(menu('Needs you'))).toBeNull()
    const boom = createKnackWindowGround({ elements: async () => Promise.reject(new Error('x')), content: () => ({ x: 0, y: 0, zoom: 1 }), display: () => DISPLAY })
    expect(await boom.ground(menu('Needs you'))).toBeNull()
  })
  it('a page that returns rubbish gives no elements', () => {
    expect(parseKnackElements('x')).toEqual([])
    expect(parseKnackElements([{ name: '', x: 1, y: 1, w: 1, h: 1 }, { name: 'ok', x: 1, y: 1, w: 0, h: 5 }, { name: 'ok', x: NaN, y: 1, w: 5, h: 5 }, { name: 'x'.repeat(81), x: 1, y: 1, w: 5, h: 5 }, null, { name: 'Fine', x: 1, y: 2, w: 3, h: 4 }])).toEqual([{ name: 'Fine', x: 1, y: 2, w: 3, h: 4 }])
  })
  it('through the tool host: found true, a ring at the element, and no screen capture anywhere', async () => {
    const rings: Array<{ box: number[]; ghost: boolean }> = []
    const knack = createKnackWindowGround({ elements: async () => els, content: () => ({ x: 100, y: 50, zoom: 1 }), display: () => DISPLAY })
    let screenCalls = 0
    const vision: GroundPort = { ground: async () => { screenCalls++; return null } }
    const host = createToolHost({ cue: { candidates: () => [], showStep: () => ({ ok: false, chip: null }), askChoice: () => false, onAnswer: () => () => undefined }, ground: chainGround(knack, vision), ring: { show: (b, o) => void rings.push({ box: [...b], ghost: o?.ghost === true }), clear: () => undefined }, wake: { doIt: async () => ({ ok: false, reason: 'x' }) } })
    expect(await host.point('the Needs you list in the sidebar')).toEqual({ found: true })
    expect(rings).toHaveLength(1)
    expect(rings[0].ghost).toBe(true)
    expect(screenCalls).toBe(0)
  })
})

describe('a browser tab with the extension', () => {
  const answer = (found: boolean): RectAnswer => ({ request_id: 'r', frame_id: 'top', found, rect: { x: 100, y: 200, w: 120, h: 40 }, dpr: 2, age_ms: 10, viewport: { w: 1440, h: 900 }, window_offset: { x: 0, y: 80 } })
  it('asks the extension by role and name, maps the answer to the display grid, and stops at the first hit', async () => {
    const asked: DomTarget[] = []
    const port = createDomPointPort({
      display: () => DISPLAY,
      grounder: { request: async (t) => (asked.push(t), t && 'role' in t && t.role === 'link' ? { kind: 'answer' as const, answer: answer(true), receivedAt: 0 } : { kind: 'answer' as const, answer: answer(false), receivedAt: 0 }) },
    })
    const a = (await port.ground(menu('the green Submit button'))) as GroundAnswer
    expect(asked.map((t) => ('role' in t ? t.role : ''))).toEqual(['button', 'link'])
    expect(a).toMatchObject({ chosen: 't0', source: 'dom' })
    expect(a.box_2d).toHaveLength(4)
    expect(a.box_2d?.every((n) => n >= 0 && n <= 1000)).toBe(true)
  })
  it('answers null at once when the extension has not been seen, and when nothing is found or the description names nothing', async () => {
    let calls = 0
    const g = { request: async () => (calls++, { kind: 'timeout' as const }) }
    expect(await createDomPointPort({ grounder: g, display: () => DISPLAY, extensionPresent: () => false }).ground(menu('the Submit button'))).toBeNull()
    expect(calls).toBe(0)
    expect(await createDomPointPort({ grounder: g, display: () => DISPLAY }).ground(menu('the Submit button'))).toBeNull()
    expect(await createDomPointPort({ grounder: g, display: () => DISPLAY }).ground(menu('the big red button'))).toBeNull()
  })
  it('an element scrolled out of view is not found', async () => {
    const off: RectAnswer = { ...answer(true), rect: { x: 100, y: 2000, w: 100, h: 30 } }
    const port = createDomPointPort({ display: () => DISPLAY, grounder: { request: async () => ({ kind: 'answer' as const, answer: off, receivedAt: 0 }) } })
    expect(await port.ground(menu('the Submit button'))).toBeNull()
  })
})

describe('the screen picture is the last resort and has its own permission', () => {
  const vision: GroundPort = { ground: async () => ({ available: ['t0'], chosen: 't0', box_2d: [100, 100, 150, 200], confidence: 0.9, source: 'vision' }) }
  it('with no Screen Recording permission it never calls the vision route and says why, once per call', async () => {
    let missing = 0
    let called = 0
    const gate = createScreenGate({ ground: async (r) => (called++, vision.ground(r)) }, { status: () => 'not-determined', onMissing: () => void missing++ })
    expect(await gate?.ground(menu('the Save button'))).toBeNull()
    expect(missing).toBe(1)
    expect(called).toBe(0)
  })
  it('with the permission it passes straight through', async () => {
    const gate = createScreenGate(vision, { status: () => 'granted', onMissing: () => undefined })
    expect(await gate?.ground(menu('the Save button'))).toMatchObject({ source: 'vision' })
  })
  it('chains in order and a failing grounder only costs its own turn', async () => {
    const order: string[] = []
    const mk = (name: string, a: GroundAnswer | null | 'throw'): GroundPort => ({ ground: async () => (order.push(name), a === 'throw' ? Promise.reject(new Error('x')) : a) })
    const hit: GroundAnswer = { available: ['t0'], chosen: 't0', box_2d: [1, 2, 30, 40], confidence: 1, source: 'dom' }
    const chain = chainGround(mk('knack', null), null, mk('ext', 'throw'), mk('vision', hit))
    expect(await chain?.ground(menu('x y'))).toEqual(hit)
    expect(order).toEqual(['knack', 'ext', 'vision'])
    expect(chainGround(null, null)).toBeNull()
  })
})
