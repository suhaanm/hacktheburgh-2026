import fs from 'node:fs'
import http from 'node:http'
import type { AddressInfo } from 'node:net'
import path from 'node:path'
import Ajv2020 from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import { afterEach, describe, expect, it } from 'vitest'
import { createCoachTracker, withCoachTelemetry, wireCoachBus } from './coach-events'
import { createEngineClient, toProposal } from './client'
import { installDeskSignals, type PowerMonitorLike } from './desk-signals'
import { DEFAULT_ENDPOINTS, endpointsFromEnv, isLoopbackUrl, loopbackOr } from './endpoints'
import { buildEvent, eventProblem, EVENT_SOURCES, EVENT_TYPES, type EventInput, type UnderstudyEvent } from './event'
import { loadIdentity, newPersonId, roleFromMemory } from './identity'
import { EventEmitter } from 'node:events'
import { Bus } from '../bus'
import type { OverlayController } from '../../shared/contracts'

const SCHEMA_FILE = path.resolve(__dirname, '../../../../../packages/schema/event.schema.json')
const schemaExists = fs.existsSync(SCHEMA_FILE)
const ID = { person: 'p_9f3a1c20', role: 'benefits-processor' }
const T0 = new Date('2026-11-07T14:03:11.123Z')

describe.skipIf(!schemaExists)('events against packages/schema/event.schema.json', () => {
  const schema = JSON.parse(fs.readFileSync(SCHEMA_FILE, 'utf8')) as { properties: { type: { enum: string[] }; source: { enum: string[] } } }
  const ajv = new Ajv2020({ strict: false, allErrors: true })
  addFormats(ajv)
  const validate = ajv.compile(schema)

  it('uses exactly the schema enums for types and sources', () => {
    expect([...EVENT_TYPES].sort()).toEqual([...schema.properties.type.enum].sort())
    expect([...EVENT_SOURCES].sort()).toEqual([...schema.properties.source.enum].sort())
  })

  it('every desk and coach event we build validates, and our own validator agrees with the schema', () => {
    const inputs: EventInput[] = [
      { source: 'desk', type: 'lock' },
      { source: 'desk', type: 'unlock' },
      { source: 'desk', type: 'sleep' },
      { source: 'desk', type: 'resume' },
      { source: 'desk', type: 'idle', meta: { state: 'start', idle_s: 61 } },
      { source: 'desk', type: 'idle', meta: { state: 'end', idle_s: 240 } },
      { source: 'coach', type: 'coach_shown', target: { role: 'ring', label_hash: 'h:9f2c', domain_hash: 'd:77aa' }, meta: { level: 'l2' } },
      { source: 'coach', type: 'coach_followed', target: { role: 'ring' }, meta: { latency_ms: 3200, level: 'l3' } },
      { source: 'coach', type: 'coach_dismissed', target: { role: 'ring' }, meta: { latency_ms: 1200, how: 'stop' }, task_id: 't_204' },
    ]
    for (const input of inputs) {
      const ev = buildEvent(ID, input, T0, 'a1b2c3d4-0000-4000-8000-000000000001')
      expect(validate(ev), JSON.stringify(validate.errors)).toBe(true)
      expect(eventProblem(ev)).toBeNull()
    }
  })

  it('both reject the same bad events (URLs, free text, bad ids, unknown keys)', () => {
    const good = buildEvent(ID, { source: 'desk', type: 'lock' }, T0, 'a1b2c3d4-0000-4000-8000-000000000002')
    const bad: UnderstudyEvent[] = [
      { ...good, person: 'Alice' },
      { ...good, role: 'Benefits Processor' },
      { ...good, meta: { page: 'https://example.com/a' } },
      { ...good, meta: { title: 'Invoice 2041 for Mr Smith' } },
      { ...good, meta: { 'Bad Key': 1 } },
      { ...good, target: { role: 'button', label_hash: 'Save changes' } },
      { ...good, task_id: 'task 1' },
      { ...good, type: 'keystroke' as never },
      { ...good, id: 'short' },
    ]
    for (const ev of bad) {
      expect(validate(ev), JSON.stringify(ev)).toBe(false)
      expect(eventProblem(ev), JSON.stringify(ev)).not.toBeNull()
    }
  })
})

describe('endpoints', () => {
  it('only ever points at this machine', () => {
    expect(isLoopbackUrl('http://127.0.0.1:7700')).toBe(true)
    expect(isLoopbackUrl('http://localhost:7700')).toBe(true)
    expect(isLoopbackUrl('http://example.com')).toBe(false)
    expect(isLoopbackUrl('http://127.0.0.1.evil.test')).toBe(false)
    expect(isLoopbackUrl('ftp://127.0.0.1')).toBe(false)
    expect(loopbackOr('http://evil.test:1', DEFAULT_ENDPOINTS.engine)).toBe(DEFAULT_ENDPOINTS.engine)
    expect(endpointsFromEnv({ UNDERSTUDY_ENGINE_URL: 'http://127.0.0.1:9000/', UNDERSTUDY_AGENT_URL: 'https://remote.test' })).toMatchObject({ engine: 'http://127.0.0.1:9000', agent: 'http://127.0.0.1:7710' })
    expect(endpointsFromEnv({ UNDERSTUDY_EXT_PORT: '9999' }).extension.port).toBe(9999)
    expect(endpointsFromEnv({ UNDERSTUDY_EXT_PORT: 'x' }).extension.port).toBe(7720)
  })
})

describe('identity', () => {
  it('generates a valid person id once and keeps it; env wins; role comes from memory front matter', () => {
    const files = new Map<string, string>()
    const deps = { userDataDir: '/u', env: {}, readFile: (f: string) => files.get(f) ?? (() => { throw new Error('nope') })(), writeFile: (f: string, d: string) => void files.set(f, d) }
    const a = loadIdentity(deps)
    expect(a.person).toMatch(/^p_[0-9a-f]{8}$/)
    expect(a.role).toBe('benefits-processor')
    expect(loadIdentity(deps)).toEqual(a)
    expect(loadIdentity({ ...deps, env: { UNDERSTUDY_PERSON: 'p_demo01', UNDERSTUDY_ROLE: 'data-analyst' } })).toEqual({ person: 'p_demo01', role: 'data-analyst' })
    expect(loadIdentity({ ...deps, env: { UNDERSTUDY_PERSON: 'Not Valid' } }).person).toBe(a.person)
    expect(newPersonId(Buffer.from([1, 2, 3, 4]))).toBe('p_01020304')
    expect(roleFromMemory('---\nrole: data-analyst\nrevision: 3\n---\n## Preferences')).toBe('data-analyst')
    expect(roleFromMemory('no front matter')).toBeNull()
  })
})

// ---------- a fake engine and agent on ephemeral ports ----------
interface Fake {
  url: string
  requests: Array<{ method: string; path: string; body: unknown }>
  close(): Promise<void>
  respond: (path: string, method: string) => { status: number; body: unknown }
}
const servers: Fake[] = []
afterEach(async () => {
  while (servers.length) await servers.pop()!.close()
})

async function fakeServer(respond: Fake['respond'] = () => ({ status: 200, body: {} }), port = 0): Promise<Fake> {
  const requests: Fake['requests'] = []
  const fake: Fake = { url: '', requests, respond, close: async () => undefined }
  const server = http.createServer((req, res) => {
    const chunks: Buffer[] = []
    req.on('data', (c: Buffer) => chunks.push(c))
    req.on('end', () => {
      const raw = Buffer.concat(chunks).toString('utf8')
      requests.push({ method: req.method ?? '', path: req.url ?? '', body: raw ? JSON.parse(raw) : null })
      const r = fake.respond(req.url ?? '', req.method ?? '')
      res.writeHead(r.status, { 'content-type': 'application/json' })
      res.end(JSON.stringify(r.body))
    })
  })
  await new Promise<void>((resolve) => server.listen(port, '127.0.0.1', resolve))
  fake.url = `http://127.0.0.1:${(server.address() as AddressInfo).port}`
  fake.close = () => new Promise((resolve) => server.close(() => resolve()))
  servers.push(fake)
  return fake
}

const manualTimers = () => {
  const fns: Array<() => void> = []
  return { setTimer: (fn: () => void) => (fns.push(fn), fns.length), clearTimer: () => undefined, fire: () => fns.splice(0).forEach((f) => f()), count: () => fns.length }
}

describe('engine client against a fake engine over HTTP', () => {
  it('POSTs schema-valid events as a batch to /events and reports accepted and rejected', async () => {
    const engine = await fakeServer((p) => (p === '/events' ? { status: 200, body: { accepted: 2, rejected: [{ index: 2, reason: 'schema: meta' }] } } : { status: 404, body: {} }))
    const logs: string[] = []
    const client = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, now: () => T0, log: (_s, ...a) => logs.push(a.join(' ')), ...manualTimers() })
    client.emit({ source: 'desk', type: 'lock' })
    client.emit({ source: 'desk', type: 'unlock' })
    client.emit({ source: 'desk', type: 'idle', meta: { state: 'start', idle_s: 61 } })
    expect(client.pending()).toBe(3)
    const res = await client.flush()
    expect(res).toEqual({ accepted: 2, rejected: [{ index: 2, reason: 'schema: meta' }] })
    expect(client.pending()).toBe(0)
    expect(engine.requests).toHaveLength(1)
    expect(engine.requests[0]).toMatchObject({ method: 'POST', path: '/events' })
    const batch = engine.requests[0].body as UnderstudyEvent[]
    expect(batch.map((e) => e.type)).toEqual(['lock', 'unlock', 'idle'])
    for (const e of batch) {
      expect(eventProblem(e)).toBeNull()
      expect(e).toMatchObject({ schema: 1, origin: 'real', actor: 'human', person: ID.person, role: ID.role, source: 'desk' })
    }
    expect(logs.join('\n')).toMatch(/1 of 3 events rejected/)
  })

  it('flushes on its own when the batch is full', async () => {
    const engine = await fakeServer(() => ({ status: 200, body: { accepted: 2, rejected: [] } }))
    const client = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, batchSize: 2, ...manualTimers() })
    client.emit({ source: 'desk', type: 'lock' })
    client.emit({ source: 'desk', type: 'unlock' })
    await client.flush()
    expect(engine.requests).toHaveLength(1)
  })

  it('keeps events when the engine is down and delivers them once it is back; never throws', async () => {
    const dead = await fakeServer()
    const url = dead.url
    const port = Number(new URL(url).port)
    await dead.close()
    servers.pop()
    const timers = manualTimers()
    const client = createEngineClient({ endpoints: { engine: url, agent: url }, identity: ID, timeoutMs: 300, ...timers })
    client.emit({ source: 'desk', type: 'sleep' })
    expect(await client.flush()).toBeNull()
    expect(client.pending()).toBe(1)
    expect(timers.count()).toBeGreaterThan(0) // a retry is scheduled
    const back = await fakeServer(() => ({ status: 200, body: { accepted: 1, rejected: [] } }), port)
    expect(await client.flush()).toEqual({ accepted: 1, rejected: [] })
    expect(back.requests).toHaveLength(1)
    expect(client.pending()).toBe(0)
  })

  it('bounds the queue (drops the oldest) and drops a batch the engine refuses with a 4xx', async () => {
    const refusing = await fakeServer(() => ({ status: 422, body: { error: { code: 'bad', message: 'bad' } } }))
    const client = createEngineClient({ endpoints: { engine: refusing.url, agent: refusing.url }, identity: ID, maxQueue: 3, batchSize: 100, ...manualTimers() })
    for (let i = 0; i < 5; i++) client.emit({ source: 'desk', type: 'lock' })
    expect(client.pending()).toBe(3)
    await client.flush()
    expect(client.pending()).toBe(0) // refused for good: not retried
  })

  it('drops an invalid event instead of sending it', () => {
    const client = createEngineClient({ endpoints: { engine: 'http://127.0.0.1:1', agent: 'http://127.0.0.1:1' }, identity: ID, ...manualTimers() })
    expect(client.emit({ source: 'desk', type: 'idle', meta: { url: 'https://example.com' } })).toBe(false)
    expect(client.emit({ source: 'desk', type: 'lock', task_id: 'bad id' })).toBe(false)
    expect(client.pending()).toBe(0)
    client.setRole('data-analyst')
    expect(client.identity.role).toBe('data-analyst')
  })

  it('refuses to be pointed at a host that is not this machine', () => {
    expect(() => createEngineClient({ endpoints: { engine: 'http://example.com:7700', agent: 'http://127.0.0.1:7710' }, identity: ID })).toThrow(/this machine/)
  })

  it('kill calls both the engine and the agent, best effort, and reports each', async () => {
    const engine = await fakeServer((p) => (p.startsWith('/kill') ? { status: 200, body: { killed: true } } : { status: 404, body: {} }))
    const agent = await fakeServer((p) => (p === '/kill' ? { status: 200, body: { killed: true } } : { status: 404, body: {} }))
    const client = createEngineClient({ endpoints: { engine: engine.url, agent: agent.url }, identity: ID, ...manualTimers() })
    expect(await client.kill()).toEqual({ engine: true, agent: true })
    expect(engine.requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /kill'])
    expect(agent.requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /kill'])
    // one of them down: the other still gets called and nothing throws
    await agent.close()
    servers.splice(servers.indexOf(agent), 1)
    expect(await client.kill()).toEqual({ engine: true, agent: false })
    expect(await client.clearKill()).toEqual({ engine: true, agent: false })
    expect(engine.requests.at(-1)).toMatchObject({ path: '/kill/clear' })
  })

  it('reads proposals from GET /routines (bare list or {data}) and the role from GET /memory', async () => {
    const routine = {
      id: 'calc-entry-3x',
      title: 'Enter the household into three calculators',
      status: 'proposed',
      episodes: 14,
      minutes_per_week: 96,
      value: { hours_saved: [3.1, 5.2] },
      touches: ['gov.uk check', 'turn2us'],
      never: ['submit'],
      proposal: { what: 'You enter the same household three times.', how_often: 'about 14 times in 3 weeks' },
    }
    const engine = await fakeServer((p) => (p === '/routines' ? { status: 200, body: { meta: {}, data: [routine, { nonsense: true }] } } : p === '/memory' ? { status: 200, body: { markdown: '---\nrole: data-analyst\nrevision: 2\n---\n' } } : { status: 404, body: {} }))
    const client = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, ...manualTimers() })
    const list = await client.routines()
    expect(list).toHaveLength(1)
    expect(list![0]).toEqual({ id: 'calc-entry-3x', title: 'Enter the household into three calculators', status: 'proposed', minutesPerWeek: 96, hoursSaved: [3.1, 5.2], episodes: 14, touches: ['gov.uk check', 'turn2us'], never: ['submit'], what: 'You enter the same household three times.', howOften: 'about 14 times in 3 weeks' })
    expect(await client.syncIdentity()).toEqual({ person: null, role: 'data-analyst', captureTimesOnly: false })
    expect(client.identity.role).toBe('data-analyst')
    expect(toProposal({ id: 'x', status: 'declined' })).toMatchObject({ id: 'x', title: 'x', hoursSaved: null })
    expect(toProposal(null)).toBeNull()
  })

  it('routines() is null when the engine is unreachable; decline posts only a declining consent', async () => {
    const engine = await fakeServer(() => ({ status: 200, body: {} }))
    const client = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, ...manualTimers() })
    expect(await client.decline('calc-entry-3x', 'never')).toBe(true)
    expect(engine.requests[0]).toMatchObject({ method: 'POST', path: '/routines/calc-entry-3x/consent', body: { mode: 'never', irreversible_unattended: [], typed_confirm: '' } })
    expect(await client.health()).toBe(true)
    await engine.close()
    servers.pop()
    expect(await client.routines()).toBeNull()
    expect(await client.health()).toBe(false)
  })
})

describe('desk signals from powerMonitor', () => {
  function fakePm() {
    const em = new EventEmitter()
    let idle = 0
    const pm: PowerMonitorLike = {
      on: (e, l) => em.on(e, l),
      removeListener: (e, l) => em.removeListener(e, l),
      getSystemIdleTime: () => idle,
    }
    return { pm, em, setIdle: (n: number) => (idle = n) }
  }
  const setup = () => {
    const f = fakePm()
    const events: EventInput[] = []
    const sig = installDeskSignals({ powerMonitor: f.pm, emit: (e) => events.push(e), idleThresholdS: 60, setTimer: () => 1, clearTimer: () => undefined })
    return { ...f, events, sig }
  }

  it('lock, unlock, suspend and resume become lock, unlock, sleep and resume desk events (once each)', () => {
    const { em, events } = setup()
    em.emit('lock-screen')
    em.emit('lock-screen')
    em.emit('unlock-screen')
    em.emit('suspend')
    em.emit('resume')
    expect(events.map((e) => e.type)).toEqual(['lock', 'unlock', 'sleep', 'resume'])
    for (const e of events) expect(e).toMatchObject({ source: 'desk', actor: 'human' })
  })

  it('an idle spell starts once past the threshold and ends when input returns, with its length', () => {
    const { sig, setIdle, events } = setup()
    setIdle(30)
    sig.poll()
    expect(events).toHaveLength(0)
    setIdle(65)
    sig.poll()
    setIdle(125)
    sig.poll()
    expect(events).toEqual([{ source: 'desk', type: 'idle', actor: 'human', meta: { state: 'start', idle_s: 65 } }])
    expect(sig.state()).toMatchObject({ inIdleSpell: true, idleSeconds: 125 })
    setIdle(2)
    sig.poll()
    expect(events[1]).toEqual({ source: 'desk', type: 'idle', actor: 'human', meta: { state: 'end', idle_s: 125 } })
    expect(sig.state().inIdleSpell).toBe(false)
  })

  it('does not count idle time while locked or asleep, and closes an open spell when the screen locks', () => {
    const { em, sig, setIdle, events } = setup()
    setIdle(100)
    sig.poll()
    em.emit('lock-screen')
    expect(events.map((e) => `${e.type}:${e.meta?.state ?? ''}`)).toEqual(['idle:start', 'idle:end', 'lock:'])
    setIdle(500)
    sig.poll()
    expect(events).toHaveLength(3)
    em.emit('unlock-screen')
    em.emit('suspend')
    sig.poll()
    expect(events.map((e) => e.type).slice(3)).toEqual(['unlock', 'sleep'])
  })

  it('dispose removes the listeners', () => {
    const { em, sig, events } = setup()
    sig.dispose()
    em.emit('lock-screen')
    expect(events).toHaveLength(0)
    expect(em.listenerCount('lock-screen')).toBe(0)
  })
})

describe('coach telemetry', () => {
  const setup = () => {
    let t = 1000
    const events: EventInput[] = []
    const timers: Array<() => void> = []
    const tracker = createCoachTracker({ emit: (e) => events.push(e), now: () => t, level: () => 'l2', setTimer: (fn) => (timers.push(fn), timers.length), clearTimer: (h) => void (timers[(h as number) - 1] = () => undefined) })
    return { tracker, events, advance: (ms: number) => (t += ms), fire: () => timers.splice(0).forEach((f) => f()) }
  }

  it('shown then followed carries the latency; the same ring redrawn is not a new prompt', () => {
    const { tracker, events, advance } = setup()
    tracker.shown('point-ring')
    tracker.shown('point-ring')
    advance(3200)
    tracker.followed()
    expect(events).toEqual([
      { source: 'coach', type: 'coach_shown', target: { role: 'ring' }, meta: { level: 'l2' } },
      { source: 'coach', type: 'coach_followed', target: { role: 'ring' }, meta: { level: 'l2', latency_ms: 3200 } },
    ])
    tracker.followed() // nothing open: nothing sent
    expect(events).toHaveLength(2)
  })

  it('a clear is a dismissal only if no new ring replaces it within the window', () => {
    const { tracker, events, advance, fire } = setup()
    tracker.shown('point-ring')
    advance(900)
    tracker.cleared(['point-ring'])
    tracker.shown('point-ring-2') // point_at clears and draws again: a replacement
    fire()
    expect(events.map((e) => e.type)).toEqual(['coach_shown', 'coach_shown'])
    tracker.cleared(['point-ring-2'])
    advance(100)
    fire()
    expect(events.at(-1)).toMatchObject({ type: 'coach_dismissed', meta: { how: 'user', latency_ms: 100 } })
  })

  it('every event it builds is valid, and the overlay decorator reports rings, ticks and clears', () => {
    const { tracker, events, advance, fire } = setup()
    const drawn: string[] = []
    const overlay: OverlayController = { show: (a) => drawn.push(...a.map((x) => x.id)), clear: () => undefined, caption: () => undefined, chip: () => undefined }
    const wrapped = withCoachTelemetry(overlay, tracker)
    wrapped.show([
      { id: 'point-ring', kind: 'ring', tone: 'guide', box: { xmin: 1, ymin: 1, xmax: 9, ymax: 9 } },
      { id: 'point-arrow', kind: 'arrow', tone: 'guide', to: { x: 5, y: 5 } },
    ])
    expect(drawn).toEqual(['point-ring', 'point-arrow'])
    advance(2000)
    wrapped.show([{ id: 'runner-tick', kind: 'tick', tone: 'success', box: { xmin: 1, ymin: 1, xmax: 9, ymax: 9 }, ok: true }])
    wrapped.show([{ id: 'point-ring', kind: 'ring', tone: 'guide', box: { xmin: 1, ymin: 1, xmax: 9, ymax: 9 } }])
    wrapped.clear(['point-ring'])
    fire()
    expect(events.map((e) => e.type)).toEqual(['coach_shown', 'coach_followed', 'coach_shown', 'coach_dismissed'])
    for (const e of events) expect(eventProblem(buildEvent(ID, e, T0, 'a1b2c3d4-0000-4000-8000-000000000003'))).toBeNull()
  })

  it('the bus: a verified step is followed; Stop or an aborted lesson is a dismissal', () => {
    const { tracker, events } = setup()
    const bus = new Bus()
    const off = wireCoachBus(bus, tracker)
    tracker.shown('runner-ring')
    bus.emit('lesson:step', { lessonId: 'l', skillId: 'video_call', stepIndex: 0, stepCount: 2, phase: 'verified' })
    tracker.shown('runner-ring-2')
    bus.emit('session:ended', { reason: 'stop' })
    tracker.shown('runner-ring-3')
    bus.emit('session:ended', { reason: 'idle' })
    expect(events.map((e) => (e.meta as Record<string, unknown>).how ?? e.type)).toEqual(['coach_shown', 'coach_followed', 'coach_shown', 'stop', 'coach_shown'])
    off()
  })
})

describe('queue count', () => {
  it('counts pending approvals from a bare list or {data}, and is null when unreachable', async () => {
    const engine = await fakeServer((p) => (p === '/queue?status=pending' ? { status: 200, body: { meta: {}, data: [{ id: 'q_1' }, { id: 'q_2' }] } } : { status: 404, body: {} }))
    const client = createEngineClient({ endpoints: { engine: engine.url, agent: engine.url }, identity: ID, ...manualTimers() })
    expect(await client.pendingQueue()).toBe(2)
    await engine.close()
    servers.pop()
    expect(await client.pendingQueue()).toBeNull()
  })
})

describe('capture consent (PR3: desk events are opt-in)', () => {
  const MEM = (prefs: string, extra = '') => `---\nrole: benefits-processor\nrevision: 4\n---\n## Preferences\n${prefs}\n## Procedure\n- Usually checks child-related benefits first.\n${extra}`

  it('reads the Capture line only from the Preferences section, tolerant of case, spacing and a trailing comment', async () => {
    const { captureFromMemory } = await import('./capture-consent')
    expect(captureFromMemory(MEM('- Summaries: short.\n- Capture: times only'))).toBe(true)
    expect(captureFromMemory(MEM('-   capture:   TIMES ONLY  <!-- accepted 2026-11-07 -->'))).toBe(true)
    expect(captureFromMemory(MEM('- Summaries: short.'))).toBe(false)
    expect(captureFromMemory(MEM('- Capture: off'))).toBe(false)
    expect(captureFromMemory(MEM('- Capture: times only and window titles'))).toBe(false)
    expect(captureFromMemory(MEM('- Summaries: short.', '## Never\n- Capture: times only'))).toBe(false) // another section does not count
    expect(captureFromMemory('')).toBe(false)
  })

  const fakeEngine = (answers: Array<{ captureTimesOnly: boolean } | null>) => {
    let i = 0
    const purged: string[] = []
    return {
      purged,
      engine: {
        memory: async () => {
          const a = answers[Math.min(i++, answers.length - 1)]
          return a ? { person: null, role: null, captureTimesOnly: a.captureTimesOnly } : null
        },
        purge: (source: string) => (purged.push(source), 2),
      },
    }
  }
  const manual = () => {
    const fns: Array<() => void> = []
    return { setTimer: (fn: () => void) => (fns.push(fn), 1), clearTimer: () => undefined, tick: () => fns.forEach((f) => f()) }
  }

  it('is off by default and when the engine cannot say; turns on only with the line; off again the moment it disappears, discarding unsent events', async () => {
    const { createCaptureConsent } = await import('./capture-consent')
    const t = manual()
    const fe = fakeEngine([null, { captureTimesOnly: true }, { captureTimesOnly: true }, { captureTimesOnly: false }, null])
    const modes: string[] = []
    const c = createCaptureConsent({ engine: fe.engine, env: {}, ...t })
    c.subscribe((m) => modes.push(m))
    expect(c.mode()).toBe('off')
    expect(c.allowed()).toBe(false)
    expect(await c.check()).toBe('times_only') // 2nd read of memory: the line is there
    expect(c.allowed()).toBe(true)
    expect(await c.check()).toBe('times_only')
    expect(await c.check()).toBe('off') // the line is gone
    expect(fe.purged.length).toBeGreaterThan(0)
    expect(await c.check()).toBe('off') // engine unreachable: fail closed
    expect(modes).toEqual(['off', 'times_only', 'off']) // the first check announces the starting mode
    c.dispose()
  })

  it('UNDERSTUDY_DESK_EVENTS=1 forces it on for development without reading the memory file', async () => {
    const { createCaptureConsent, captureLabel } = await import('./capture-consent')
    const fe = fakeEngine([{ captureTimesOnly: false }])
    const c = createCaptureConsent({ engine: fe.engine, env: { UNDERSTUDY_DESK_EVENTS: '1' }, ...manual() })
    expect(c.mode()).toBe('forced')
    expect(await c.check()).toBe('forced')
    expect(c.allowed()).toBe(true)
    expect(captureLabel('off')).toMatch(/off/i)
    expect(captureLabel('times_only')).toMatch(/times only/)
  })

  it('rechecks on its timer and applies the person and role it reads', async () => {
    const { createCaptureConsent } = await import('./capture-consent')
    const t = manual()
    const seen: unknown[] = []
    const engine = { memory: async () => ({ person: 'p_abc123', role: 'data-analyst', captureTimesOnly: true }), purge: () => 0 }
    const c = createCaptureConsent({ engine, env: {}, onMemory: (i) => void seen.push(i), ...t })
    await c.check()
    t.tick()
    await new Promise((r) => setTimeout(r, 5))
    expect(seen.length).toBeGreaterThanOrEqual(3) // startup, explicit check, timer
    expect(seen[0]).toEqual({ person: 'p_abc123', role: 'data-analyst', captureTimesOnly: true })
  })

  it('client.purge drops only the queued events of that source', () => {
    const client = createEngineClient({ endpoints: { engine: 'http://127.0.0.1:1', agent: 'http://127.0.0.1:1' }, identity: ID, batchSize: 100, ...manualTimers() })
    client.emit({ source: 'desk', type: 'lock' })
    client.emit({ source: 'coach', type: 'coach_shown' })
    client.emit({ source: 'desk', type: 'unlock' })
    expect(client.purge('desk')).toBe(2)
    expect(client.pending()).toBe(1)
  })

  it('client.memory reads GET /identity first (200 wins), falls back to GET /memory, and applies person and role', async () => {
    const md = '---\nrole: data-analyst\nrevision: 2\n---\n## Preferences\n- Capture: times only\n'
    const withIdentity = await fakeServer((p) => (p === '/identity' ? { status: 200, body: { person: 'p_9f3a1c20', role: 'benefits-processor' } } : p === '/memory' ? { status: 200, body: { markdown: md, person: 'p_other01' } } : { status: 404, body: {} }))
    const a = createEngineClient({ endpoints: { engine: withIdentity.url, agent: withIdentity.url }, identity: { person: 'p_local001', role: 'data-analyst' }, ...manualTimers() })
    expect(await a.syncIdentity()).toEqual({ person: 'p_9f3a1c20', role: 'benefits-processor', captureTimesOnly: true })
    expect(a.identity).toEqual({ person: 'p_9f3a1c20', role: 'benefits-processor' })

    const memoryOnly = await fakeServer((p) => (p === '/memory' ? { status: 200, body: { data: { markdown: md, person: 'p_other01' } } } : { status: 404, body: {} }))
    const b = createEngineClient({ endpoints: { engine: memoryOnly.url, agent: memoryOnly.url }, identity: { person: 'p_local001', role: 'benefits-processor' }, ...manualTimers() })
    expect(await b.memory()).toEqual({ person: 'p_other01', role: 'data-analyst', captureTimesOnly: true })

    const neither = await fakeServer((p) => (p === '/memory' ? { status: 200, body: { markdown: '## Preferences\n- Summaries: short.' } } : { status: 404, body: {} }))
    const c = createEngineClient({ endpoints: { engine: neither.url, agent: neither.url }, identity: ID, ...manualTimers() })
    expect(await c.syncIdentity()).toEqual({ person: null, role: null, captureTimesOnly: false })
    expect(c.identity).toEqual(ID) // nothing usable: the local identity stays
  })
})
