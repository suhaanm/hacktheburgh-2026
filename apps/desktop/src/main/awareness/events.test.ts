import fs from 'node:fs'
import path from 'node:path'
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { describe, expect, it } from 'vitest'
import { awarenessEventProblem, createAwarenessSink, createLoopbackPost, glanceEvent, windowEvent, type AwarenessEvent } from './events'
import { emptyFeatures } from './cursor'
import { APP_KINDS, BLOCKERS, TASK_PHASES, TRIGGER_REASONS } from './types'
import { SKIP_REASONS } from './types'
import { isLoopbackUrl } from '../engine/endpoints'

const SCHEMA_FILE = path.resolve(__dirname, '../../../../../packages/schema/awareness.schema.json')
const schema = JSON.parse(fs.readFileSync(SCHEMA_FILE, 'utf8')) as Record<string, any>
const ajv = new Ajv2020({ strict: false, allErrors: true })
addFormats(ajv)
const validate = ajv.compile(schema)
const validateRequest = ajv.getSchema(`${schema.$id}#/$defs/GlanceHttpRequest`)!
const validateResponse = ajv.getSchema(`${schema.$id}#/$defs/GlanceHttpResponse`)!

const id = { person: 'p_demo01', role: 'benefits-processor' }
const t = new Date('2026-11-07T17:30:00.000Z')
const feats = { ...emptyFeatures(2, null), dwell_s: 1.9, dwell_zone: 'cliff_button', wander: 3.2, back_forth: 2, zone_a: 'case_note', zone_b: 'results_tabs', speed_bursts: 1, idle_gap_s: 0.4 }
const win = (): AwarenessEvent => windowEvent(id, feats, { t, appKind: 'browser', sysIdleS: 0.3 }, 'evt-window-0001')
const glance = (): AwarenessEvent => glanceEvent(id, 'stuck', { app_kind: 'spreadsheet', task_phase: 'entering', blocker: 'none', confidence: 0.7, box_2d: [10, 20, 100, 200] }, t, 'evt-glance-0001')

describe('the enums match the schema file (one source of truth)', () => {
  it('app kinds, task phases, blockers, trigger reasons', () => {
    expect([...APP_KINDS]).toEqual(schema.$defs.AppKind.enum)
    expect([...APP_KINDS, 'unknown']).toEqual(schema.$defs.AppKindOrUnknown.enum)
    expect([...TASK_PHASES]).toEqual(schema.$defs.TaskPhase.enum)
    expect([...BLOCKERS]).toEqual(schema.$defs.Blocker.enum)
    expect([...TRIGGER_REASONS]).toEqual(schema.$defs.TriggerReason.enum)
    expect(SKIP_REASONS.length).toBeGreaterThan(10)
    expect(new Set(SKIP_REASONS).size).toBe(SKIP_REASONS.length)
  })
})

describe('events against packages/schema/awareness.schema.json', () => {
  it('window and glance events built here validate, and so does the mirror', () => {
    for (const e of [win(), glance(), { ...win(), cursor: { ...win().cursor!, clicks: 3 } }]) {
      expect(validate(e), JSON.stringify(validate.errors)).toBe(true)
      expect(awarenessEventProblem(e)).toBeNull()
    }
  })

  it('the mirror and the schema agree on a set of bad events', () => {
    const w = win()
    const g = glance()
    const bad: Array<[string, unknown]> = [
      ['unknown key', { ...w, title: 'Payroll' }],
      ['coordinates', { ...w, cursor: { ...w.cursor, x: 10, y: 20 } }],
      ['cursor key missing', { ...w, cursor: { dwell_s: 1 } }],
      ['bad app kind', { ...w, app_kind: 'martian' }],
      ['bad zone', { ...w, cursor: { ...w.cursor, dwell_zone: 'Not A Zone' } }],
      ['wander under 1', { ...w, cursor: { ...w.cursor, wander: 0.5 } }],
      ['dwell over 30', { ...w, cursor: { ...w.cursor, dwell_s: 31 } }],
      ['back_forth not an integer', { ...w, cursor: { ...w.cursor, back_forth: 1.5 } }],
      ['window without cursor', { ...w, cursor: undefined }],
      ['window carrying a glance', { ...w, glance: g.glance }],
      ['glance carrying a cursor', { ...g, cursor: w.cursor }],
      ['glance without a trigger', { ...g, trigger: undefined }],
      ['bad trigger', { ...g, trigger: 'curiosity' }],
      ['free text in a glance', { ...g, glance: { ...g.glance, description: 'a payroll sheet' } }],
      ['bad blocker', { ...g, glance: { ...g.glance, blocker: 'boredom' } }],
      ['confidence over 1', { ...g, glance: { ...g.glance, confidence: 1.2 } }],
      ['box with 3 numbers', { ...g, glance: { ...g.glance, box_2d: [1, 2, 3] } }],
      ['bad person', { ...w, person: 'alice' }],
      ['bad time', { ...w, t: 'yesterday' }],
      ['bad schema version', { ...w, schema: 2 }],
      ['bad type', { ...w, type: 'frame' }],
    ]
    for (const [name, e] of bad) {
      const clean = JSON.parse(JSON.stringify(e)) // drop undefined keys
      expect(validate(clean), `schema should reject: ${name}`).toBe(false)
      expect(awarenessEventProblem(clean), `mirror should reject: ${name}`).not.toBeNull()
    }
  })

  it('the wire shapes of the glance route validate (documentation of the contract)', () => {
    const req = { frame_b64: 'AAAA', gates: { consent: true, denylisted_app: false, secure_input: false, unattended: false }, trigger: 'hotkey', app_kind: 'browser', width: 640, height: 400 }
    expect(validateRequest(req), JSON.stringify(validateRequest.errors)).toBe(true)
    expect(validateRequest({ ...req, gates: { consent: true } })).toBe(false)
    expect(validateRequest({ ...req, width: 4000 })).toBe(false)
    expect(validateResponse({ ok: true, result: { app_kind: 'browser' }, model: 'm', latency_ms: 5, cost_usd_est: 0.001 })).toBe(true)
    expect(validateResponse({ ok: false, blocked_reason: 'no_consent' })).toBe(true)
    expect(validateResponse({ blocked_reason: 'x' })).toBe(false)
  })

  it('sys_idle_s is optional and bounded; an unknown idle time is omitted, not zero', () => {
    const none = windowEvent(id, feats, { t, appKind: 'other', sysIdleS: null }, 'evt-window-0002')
    expect('sys_idle_s' in none).toBe(false)
    expect(validate(none)).toBe(true)
  })
})

describe('the sink', () => {
  const mkTimers = () => {
    const pending: Array<() => void> = []
    return { pending, setTimer: (fn: () => void) => (pending.push(fn), pending.length), clearTimer: () => undefined }
  }

  it('posts batches to /awareness/events on the engine, and drops invalid events', async () => {
    const posts: Array<{ url: string; body: any }> = []
    const sink = createAwarenessSink({ engineUrl: 'http://127.0.0.1:7700', post: async (url, body) => (posts.push({ url, body }), { status: 200 }), batchSize: 3, ...mkTimers() })
    expect(sink.emit(win())).toBe(true)
    expect(sink.emit({ ...win(), junk: 1 } as never)).toBe(false)
    expect(sink.pending()).toBe(1)
    sink.emit(win())
    sink.emit(win())
    await sink.flush()
    expect(posts).toHaveLength(1)
    expect(posts[0].url).toBe('http://127.0.0.1:7700/awareness/events')
    expect(posts[0].body).toHaveLength(3)
    expect(sink.pending()).toBe(0)
  })

  it('keeps events while the engine is away (bounded), and drops them when it refuses', async () => {
    let status: number | null = null
    const sink = createAwarenessSink({ engineUrl: 'http://127.0.0.1:7700', post: async () => (status === null ? null : { status }), maxQueue: 4, batchSize: 100, ...mkTimers() })
    for (let i = 0; i < 6; i++) sink.emit(win())
    await sink.flush()
    expect(sink.pending()).toBe(4) // away: kept, oldest dropped
    status = 404 // the layer is off on the engine
    await sink.flush()
    expect(sink.pending()).toBe(0)
    expect(sink.dropped()).toBeGreaterThanOrEqual(4)
  })

  it('dispose empties the queue and stops accepting', () => {
    const sink = createAwarenessSink({ engineUrl: 'http://127.0.0.1:7700', post: async () => ({ status: 200 }), ...mkTimers() })
    sink.emit(win())
    sink.dispose()
    expect(sink.pending()).toBe(0)
    expect(sink.emit(win())).toBe(false)
  })

  it('the loopback post refuses a remote host without calling fetch', async () => {
    let called = 0
    const post = createLoopbackPost({ fetchImpl: (async () => (called++, new Response('{}'))) as never, isLoopback: isLoopbackUrl })
    expect(await post('https://example.com/awareness/events', [])).toBeNull()
    expect(called).toBe(0)
    expect(await post('http://127.0.0.1:7700/awareness/events', [])).toEqual({ status: 200 })
    expect(called).toBe(1)
  })
})
