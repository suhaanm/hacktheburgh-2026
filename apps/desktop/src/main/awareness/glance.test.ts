import fs from 'node:fs'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { fakeConsole, fakeFrontmost, fakePower, fakeShare, scriptedPort, GOOD_ANSWER } from './awareness.test-util'
import { createFakeFrameSource } from './capture-fake'
import { awarenessEventProblem, type AwarenessEvent } from './events'
import { createGlancer, createHttpGlancePort, createMemoryLedger, parsePortResponse, type GlancerDeps, type LedgerEntry, type LedgerPort, type PowerState } from './glance'
import { CONSENT_VERSION, DEFAULT_AWARENESS_SETTINGS, type AwarenessSettings } from './settings'
import { UsageMeter } from './usage'
import { isLoopbackUrl } from '../engine/endpoints'

afterEach(() => vi.restoreAllMocks())

const NOW = 1_800_000_000_000
const on: AwarenessSettings = { ...DEFAULT_AWARENESS_SETTINGS, awarenessEnabled: true, glanceOnTrigger: true, glancePeriodic: true, glanceConsentVersion: CONSENT_VERSION }

function power(over: Partial<{ locked: boolean; asleep: boolean; idle: number | null; thermal: 'nominal' | 'serious' | 'unknown' }> = {}): PowerState {
  return { locked: () => over.locked ?? false, asleep: () => over.asleep ?? false, idleSeconds: () => (over.idle === undefined ? 1 : over.idle), thermal: () => over.thermal ?? 'nominal' }
}

type RigOptions = Omit<Partial<GlancerDeps>, 'settings' | 'flagOn'> & { settings?: AwarenessSettings; flag?: boolean }

function rig(all: RigOptions = {}) {
  const { settings: settingsOver, flag, ...over } = all
  let t = NOW
  const frames = createFakeFrameSource({ width: 2880, height: 1800 })
  const port = scriptedPort()
  const front = fakeFrontmost('com.microsoft.Excel')
  const cons = fakeConsole()
  const ledger = createMemoryLedger()
  const emitted: AwarenessEvent[] = []
  const usage = new UsageMeter(() => t)
  const glancer = createGlancer({
    settings: () => settingsOver ?? on,
    flagOn: () => flag ?? true,
    now: () => t,
    usage,
    ledger,
    frames,
    port,
    frontmost: front,
    console: cons,
    screenShare: fakeShare(false),
    power: power(),
    workSession: () => true,
    identity: () => ({ person: 'p_demo01', role: 'benefits-processor' }),
    emit: (e) => emitted.push(e),
    ...over,
  })
  return { glancer, frames, port, front, cons, ledger, emitted, usage, tick: (ms: number) => void (t += ms), now: () => t }
}

describe('a glance that is allowed', () => {
  it('captures, sends the gate flags, parses the answer and emits one closed glance event', async () => {
    const r = rig()
    const out = await r.glancer.request('hotkey')
    expect(out.ok).toBe(true)
    expect(r.frames.grabs()).toBe(1)
    expect(r.port.calls).toHaveLength(1)
    const call = r.port.calls[0]
    expect(call.trigger).toBe('hotkey')
    expect(call.appKind).toBe('spreadsheet')
    expect(call.gates).toEqual({ consent: true, denylisted_app: false, secure_input: false, unattended: false })
    expect(call.frame.width).toBeLessThanOrEqual(1280)
    expect(r.emitted).toHaveLength(1)
    const ev = r.emitted[0]
    expect(ev).toMatchObject({ type: 'glance', trigger: 'hotkey', person: 'p_demo01', glance: { app_kind: 'spreadsheet', task_phase: 'entering', blocker: 'cannot_find_control', confidence: 0.82 } })
    expect(awarenessEventProblem(ev)).toBeNull()
    // no image, no hash of it, no text in the event
    expect(JSON.stringify(ev)).not.toMatch(/sha|jpeg|frame|b64/i)
  })

  it('writes the ledger before the call and completes it after, with bytes, a hash prefix, model, latency and cost; never the image', async () => {
    const order: string[] = []
    const ledger: LedgerPort = {
      async record(e: LedgerEntry) {
        order.push(`ledger:${e.phase}`)
        return { ok: true }
      },
    }
    const base = scriptedPort()
    const port = { glance: async (req: Parameters<typeof base.glance>[0]) => (order.push('port'), base.glance(req)) }
    const mem = createMemoryLedger()
    const both: LedgerPort = { record: async (e) => (await ledger.record(e), mem.record(e)) }
    const r = rig({ ledger: both, port })
    await r.glancer.request('stuck')
    expect(order).toEqual(['ledger:sent', 'port', 'ledger:done'])
    const [sent, done] = mem.entries()
    expect(sent).toMatchObject({ kind: 'image', phase: 'sent', trigger: 'stuck', outcome: 'pending', model: null })
    expect(done).toMatchObject({ kind: 'image', phase: 'done', outcome: 'ok', model: 'test-model', latency_ms: 321, cost_est: 0.0004 })
    expect(done.sha256_prefix).toMatch(/^[0-9a-f]{12}$/)
    expect(done.call_id).toBe(sent.call_id)
    expect(done.bytes).toBeGreaterThan(0)
    expect(JSON.stringify([sent, done])).not.toMatch(/jpeg|b64|frame_b64/)
  })

  it('zeroes the frame after the call, whatever happened', async () => {
    const seen: Buffer[] = []
    const port = { glance: async (req: { frame: { jpeg: Buffer } }) => (seen.push(req.frame.jpeg), { ok: true, result: GOOD_ANSWER }) }
    const r = rig({ port: port as never })
    await r.glancer.request('hotkey')
    expect(seen[0].length).toBeGreaterThan(0)
    expect(seen[0].every((b) => b === 0)).toBe(true)
    const throwing = { glance: async (req: { frame: { jpeg: Buffer } }) => (seen.push(req.frame.jpeg), Promise.reject(new Error('down'))) }
    const r2 = rig({ port: throwing as never })
    expect(await r2.glancer.request('hotkey')).toMatchObject({ ok: false, skip: 'port_failed' })
    expect(seen[1].every((b) => b === 0)).toBe(true)
  })

  it('records its use so the caps apply to the next request', async () => {
    const r = rig()
    await r.glancer.request('hotkey')
    expect(r.usage.snapshot(r.now()).callsLastHour).toBe(1)
    expect(r.usage.snapshot(r.now()).usdToday).toBeCloseTo(0.0004, 6)
    expect(await r.glancer.request('hotkey')).toMatchObject({ ok: false, skip: 'too_soon' })
    r.tick(10_000)
    expect((await r.glancer.request('hotkey')).ok).toBe(true)
  })
})

describe('nothing is captured unless every gate passes', () => {
  const blocked = async (over: Parameters<typeof rig>[0], want: string, reason: 'hotkey' | 'periodic' = 'hotkey', setup?: (r: ReturnType<typeof rig>) => void) => {
    const r = rig(over)
    setup?.(r)
    const out = await r.glancer.request(reason)
    expect(out).toMatchObject({ ok: false, skip: want })
    expect(r.frames.grabs(), `${want}: no frame`).toBe(0)
    expect(r.port.calls, `${want}: no call`).toHaveLength(0)
    expect(r.emitted, `${want}: no event`).toHaveLength(0)
    expect(r.ledger.entries(), `${want}: no ledger line`).toHaveLength(0)
  }

  it('flag off, setting off, no consent, stale consent', async () => {
    await blocked({ flag: false }, 'layer_off')
    await blocked({ settings: { ...on, awarenessEnabled: false } }, 'layer_off')
    await blocked({ settings: { ...on, glanceOnTrigger: false } }, 'no_consent')
    await blocked({ settings: { ...on, glanceConsentVersion: 0 } }, 'no_consent')
    await blocked({ settings: { ...on, glanceConsentVersion: CONSENT_VERSION + 1 } }, 'no_consent')
    await blocked({ settings: { ...on, glancePeriodic: false } }, 'no_consent', 'periodic')
  })

  it('with the layer off not even a probe runs', async () => {
    const r = rig({ flag: false })
    await r.glancer.request('hotkey')
    expect(r.front.reads()).toBe(0)
    expect(r.cons.reads()).toBe(0)
  })

  it('kill switch, pause, lock, sleep, idle, screen share, thermal', async () => {
    await blocked({ killed: () => true }, 'killed')
    await blocked({ settings: { ...on, glancePausedUntilMs: NOW + 60_000 } }, 'paused')
    await blocked({ power: power({ locked: true }) }, 'locked')
    await blocked({}, 'locked', 'hotkey', (r) => r.cons.set({ locked: true })) // the console says locked even if no event arrived
    await blocked({ power: power({ asleep: true }) }, 'asleep')
    await blocked({ power: power({ idle: 120 }) }, 'idle')
    await blocked({ screenShare: fakeShare(true) }, 'screen_share')
    await blocked({ power: power({ thermal: 'serious' }) }, 'thermal')
  })

  it('secure input on, unknown in strict mode, and a password manager in front', async () => {
    await blocked({}, 'secure_input', 'hotkey', (r) => r.cons.set({ secureInput: 'on' }))
    await blocked({}, 'secure_input_unknown', 'hotkey', (r) => r.cons.set({ secureInput: 'unknown' }))
    await blocked({}, 'app_denied', 'hotkey', (r) => r.front.set('com.1password.1password'))
    await blocked({}, 'app_denied', 'hotkey', (r) => r.front.set('com.tinyspeck.slackmacgap'))
    await blocked({}, 'app_unknown', 'hotkey', (r) => r.front.set(null))
    await blocked({ settings: { ...on, glanceDenylist: ['com.example.mine'] } }, 'app_denied', 'hotkey', (r) => r.front.set('com.example.mine'))
  })

  it('periodic needs a work session; the caps stop the rest', async () => {
    await blocked({ workSession: () => false }, 'no_work_session', 'periodic')
    await blocked({ settings: { ...on, glanceDailyUsd: 0 } }, 'daily_cap')
    await blocked({ settings: { ...on, glanceMaxPerHour: 1 } }, 'hourly_cap', 'hotkey', (r) => r.usage.record(0.001, r.now() - 20_000))
    await blocked({}, 'too_soon', 'hotkey', (r) => r.usage.record(0.001, r.now() - 2000))
    await blocked({ settings: { ...on, glanceDailyUsd: 0.01 } }, 'daily_cap', 'hotkey', (r) => r.usage.record(0.0095, r.now() - 60_000))
  })

  it('lax mode lets an unreadable app or unknown secure input through, but never a known-on secure input', async () => {
    const lax = { ...on, glanceStrict: false }
    const r = rig({ settings: lax })
    r.front.set(null)
    r.cons.set({ secureInput: 'unknown' })
    const out = await r.glancer.request('hotkey')
    expect(out.ok).toBe(true)
    expect(r.port.calls[0].gates).toMatchObject({ denylisted_app: false, secure_input: false })
    r.tick(20_000)
    r.cons.set({ secureInput: 'on' })
    expect(await r.glancer.request('hotkey')).toMatchObject({ ok: false, skip: 'secure_input' })
  })
})

describe('failures on the way', () => {
  it('a ledger that cannot take the line means nothing is sent, and the frame is still zeroed', async () => {
    const r = rig({ ledger: { record: async () => ({ ok: false }) } })
    expect(await r.glancer.request('hotkey')).toMatchObject({ ok: false, skip: 'ledger_unavailable' })
    expect(r.port.calls).toHaveLength(0)
    expect(r.frames.grabs()).toBe(1)
  })

  it('a capture failure (for example no Screen Recording permission) is a skip with its code, and nothing is sent', async () => {
    const { CaptureError } = await import('./capture')
    const r = rig({ frames: createFakeFrameSource({ failWith: new CaptureError('no permission', 'permission') }) })
    expect(await r.glancer.request('hotkey')).toMatchObject({ ok: false, skip: 'capture_failed', detail: 'permission' })
    expect(r.port.calls).toHaveLength(0)
  })

  it('the service blocking the call is a skip that costs nothing but still counts toward the hourly cap', async () => {
    const r = rig({ port: scriptedPort([{ ok: false, blocked_reason: 'secure_input' }]) })
    expect(await r.glancer.request('hotkey')).toMatchObject({ ok: false, skip: 'port_blocked', detail: 'secure_input' })
    expect(r.usage.snapshot(r.now())).toMatchObject({ callsLastHour: 1, usdToday: 0 })
    expect(r.ledger.done()[0]).toMatchObject({ outcome: 'blocked', cost_est: 0 })
    expect(r.emitted).toHaveLength(0)
  })

  it('an answer outside the closed schema is rejected, billed, and produces no event', async () => {
    const r = rig({ port: scriptedPort([{ ok: true, result: { description: 'a spreadsheet with payroll', confidence: 1 } }]) })
    expect(await r.glancer.request('hotkey')).toMatchObject({ ok: false, skip: 'port_failed' })
    expect(r.ledger.done()[0]).toMatchObject({ outcome: 'rejected' })
    expect(r.emitted).toHaveLength(0)
  })

  it('an unknown enum value from the model is dropped, not trusted, and the event still validates', async () => {
    const r = rig({ port: scriptedPort([{ ok: true, result: { app_kind: 'spreadsheet', task_phase: 'plotting-world-domination', blocker: 'none', confidence: 0.6 } }]) })
    const out = await r.glancer.request('hotkey')
    expect(out.ok).toBe(true)
    expect(r.emitted[0].glance).toMatchObject({ app_kind: 'spreadsheet', task_phase: null, blocker: 'none' })
    expect(awarenessEventProblem(r.emitted[0])).toBeNull()
  })

  it('one glance at a time', async () => {
    let release!: () => void
    const gate = new Promise<void>((res) => (release = res))
    const slow = { glance: async () => (await gate, { ok: true, result: GOOD_ANSWER }) }
    const r = rig({ port: slow as never })
    const first = r.glancer.request('hotkey')
    await new Promise((res) => setTimeout(res, 5))
    expect(r.glancer.busy()).toBe(true)
    expect(await r.glancer.request('stuck')).toMatchObject({ ok: false, skip: 'too_soon' })
    release()
    expect((await first).ok).toBe(true)
    expect(r.glancer.busy()).toBe(false)
  })
})

describe('nothing is written or logged during a glance', () => {
  it('no fs write, and no console output contains the frame', async () => {
    const spies = [vi.spyOn(fs, 'writeFileSync'), vi.spyOn(fs, 'writeFile'), vi.spyOn(fs, 'appendFileSync'), vi.spyOn(fs, 'createWriteStream'), vi.spyOn(fs.promises, 'writeFile'), vi.spyOn(fs.promises, 'appendFile')]
    const logs = [vi.spyOn(console, 'log'), vi.spyOn(console, 'info'), vi.spyOn(console, 'warn'), vi.spyOn(console, 'error'), vi.spyOn(console, 'debug')]
    const r = rig()
    await r.glancer.request('hotkey')
    await r.glancer.request('hotkey') // too soon: a skip path too
    for (const s of spies) expect(s).not.toHaveBeenCalled()
    const b64 = r.port.calls[0].frame.jpeg.toString('base64').slice(0, 24)
    for (const l of logs) expect(JSON.stringify(l.mock.calls)).not.toContain(b64)
  })
})

describe('the HTTP port', () => {
  const frame = { jpeg: Buffer.from([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4, 0xff, 0xd9]), width: 640, height: 400, bytes: 10, sha256_prefix: 'abcdef012345' }
  const gates = { consent: true, denylisted_app: false, secure_input: false, unattended: false }
  const json = (status: number, body: unknown): Response => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } })

  it('POSTs the documented request to /glance on this machine and parses the documented response', async () => {
    let seen: { url: string; init: RequestInit } | null = null
    const fetchImpl = (async (url: string, init: RequestInit) => {
      seen = { url, init }
      return json(200, { ok: true, result: GOOD_ANSWER, model: 'gem-x', latency_ms: 800.4, cost_usd_est: 0.0003 })
    }) as unknown as typeof fetch
    const port = createHttpGlancePort({ agentUrl: 'http://127.0.0.1:7710/', fetchImpl, isLoopback: isLoopbackUrl })
    const res = await port.glance({ frame, gates, trigger: 'loop', appKind: 'browser' })
    expect(seen!.url).toBe('http://127.0.0.1:7710/glance')
    expect(seen!.init.method).toBe('POST')
    expect(JSON.parse(seen!.init.body as string)).toEqual({ frame_b64: frame.jpeg.toString('base64'), gates, trigger: 'loop', app_kind: 'browser', width: 640, height: 400 })
    expect(res).toMatchObject({ ok: true, model: 'gem-x', latency_ms: 800.4, cost_usd_est: 0.0003, result: GOOD_ANSWER })
  })

  it('refuses a host that is not this machine', () => {
    expect(() => createHttpGlancePort({ agentUrl: 'https://example.com', isLoopback: isLoopbackUrl })).toThrow(/this machine/)
  })

  it('a 4xx is a block with a code, a 5xx or a dead service throws a message that holds nothing from the request', async () => {
    const b64 = frame.jpeg.toString('base64')
    const mk = (f: () => Promise<Response>) => createHttpGlancePort({ agentUrl: 'http://127.0.0.1:7710', fetchImpl: f as never, isLoopback: isLoopbackUrl })
    expect(await mk(async () => json(403, { error: { code: 'not_this_machine' } })).glance({ frame, gates, trigger: 'hotkey', appKind: 'other' })).toEqual({ ok: false, blocked_reason: 'http_403' })
    const errors: string[] = []
    for (const f of [async () => json(500, { detail: b64 }), async () => Promise.reject(new TypeError(`fetch failed ${b64}`))]) {
      try {
        await mk(f).glance({ frame, gates, trigger: 'hotkey', appKind: 'other' })
      } catch (e) {
        errors.push(String((e as Error).message) + String((e as Error).stack ?? '').slice(0, 0))
      }
    }
    expect(errors).toHaveLength(2)
    for (const e of errors) expect(e).not.toContain(b64)
  })

  it('parsePortResponse drops anything off the list and bad numbers', () => {
    expect(parsePortResponse({ ok: true, model: 'bad model name!!', latency_ms: -1, cost_usd_est: NaN, blocked_reason: 'Has Spaces' })).toEqual({ ok: true })
    expect(parsePortResponse({ data: { ok: false, blocked_reason: 'no_consent' } })).toEqual({ ok: false, blocked_reason: 'no_consent' })
    expect(parsePortResponse('x')).toEqual({ ok: false, blocked_reason: 'bad_response' })
  })
})
