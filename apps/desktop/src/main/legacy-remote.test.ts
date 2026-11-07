import { describe, expect, it } from 'vitest'
import {
  authorizeLegacy,
  base64Bytes,
  configureLegacyRemote,
  createLegacyRemoteGate,
  legacyGateReader,
  legacyRemote,
  legacyRemoteOn,
  LegacyRemoteBlocked,
  localReason,
  measureCompletion,
  purposeId,
  type GateBooleans,
  type LegacyCall,
} from './legacy-remote'

const ON = { UNDERSTUDY_LEGACY_REMOTE: '1' }
const OPEN: GateBooleans = { consent: true, denylisted_app: false, secure_input: false, unattended: false }
const ID = 'e_0123456789abcdef'

const call = (over: Partial<LegacyCall> = {}): LegacyCall => ({ kind: 'image', purpose: 'legacy.port_vision', provider: 'openai', model: 'gpt-model-from-env', bytes: 52_000, count: 1, ...over })

interface Seen {
  url: string
  headers: Record<string, string>
  body: Record<string, unknown>
}
function fakeEngine(reply: (path: string, body: Record<string, unknown>) => { status: number; json?: unknown } | 'down') {
  const seen: Seen[] = []
  const impl = (async (url: string, init: RequestInit) => {
    const body = JSON.parse(String(init.body)) as Record<string, unknown>
    seen.push({ url: String(url), headers: Object.fromEntries(Object.entries((init.headers ?? {}) as Record<string, string>)), body })
    const r = reply(new URL(String(url)).pathname, body)
    if (r === 'down') throw new Error('ECONNREFUSED')
    return new Response(JSON.stringify(r.json ?? {}), { status: r.status })
  }) as unknown as typeof fetch
  return { impl, seen }
}

const allowed = () => ({ status: 200, json: { allowed: true, status: 'sending', reason: null, ledger_id: ID } })

function gateWith(over: { gates?: GateBooleans | (() => Promise<GateBooleans>); reply?: Parameters<typeof fakeEngine>[0]; env?: Record<string, string>; killed?: () => boolean } = {}) {
  const engine = fakeEngine(over.reply ?? allowed)
  const gate = createLegacyRemoteGate({
    env: over.env ?? ON,
    engineUrl: 'http://127.0.0.1:7700',
    gates: typeof over.gates === 'function' ? over.gates : async () => (over.gates as GateBooleans | undefined) ?? OPEN,
    killed: over.killed,
    fetchImpl: engine.impl,
  })
  return { gate, engine }
}

describe('the flag', () => {
  it('is on only for exactly "1"', () => {
    expect(legacyRemoteOn({})).toBe(false)
    for (const v of ['', '0', 'true', 'yes', ' 1', '1 ']) expect(legacyRemoteOn({ UNDERSTUDY_LEGACY_REMOTE: v })).toBe(false)
    expect(legacyRemoteOn(ON)).toBe(true)
  })

  it('flag off: the gate refuses before it probes anything or calls the engine', async () => {
    let probed = 0
    const { gate, engine } = gateWith({ env: {}, gates: async () => (probed++, OPEN) })
    await expect(gate.authorize(call())).rejects.toMatchObject({ reason: 'flag_off' })
    expect(probed).toBe(0)
    expect(engine.seen).toHaveLength(0)
  })

  it('the process-wide gate is closed until configured (flag off says flag_off, flag on says ledger_unavailable) and never throws anything but a refusal', async () => {
    configureLegacyRemote(null)
    await expect(authorizeLegacy(call(), { env: {} })).rejects.toMatchObject({ reason: 'flag_off' })
    await expect(legacyRemote().authorize(call())).rejects.toBeInstanceOf(LegacyRemoteBlocked)
    process.env.UNDERSTUDY_LEGACY_REMOTE = '1'
    try {
      await expect(authorizeLegacy(call(), { env: ON })).rejects.toMatchObject({ reason: 'ledger_unavailable' })
    } finally {
      delete process.env.UNDERSTUDY_LEGACY_REMOTE
    }
  })

  it('authorizeLegacy checks the flag in the environment it is given before it reaches a configured gate', async () => {
    let reached = 0
    configureLegacyRemote({ authorize: async () => (reached++, { finish: () => undefined }) })
    try {
      await expect(authorizeLegacy(call(), { env: {} })).rejects.toMatchObject({ reason: 'flag_off' })
      expect(reached).toBe(0)
      await authorizeLegacy(call(), { env: ON })
      expect(reached).toBe(1)
    } finally {
      configureLegacyRemote(null)
    }
  })
})

describe('the engine announcement', () => {
  it('posts metadata only, to the direct route, as the worker with no Origin, before the caller may send', async () => {
    const { gate, engine } = gateWith()
    await gate.authorize(call({ kind: 'file_text', purpose: 'legacy.embed', provider: 'gemini', model: 'gemini-embedding-2', bytes: 10_000, count: 12 }))
    expect(engine.seen).toHaveLength(1)
    const s = engine.seen[0]
    expect(s.url).toBe('http://127.0.0.1:7700/privacy/ledger/direct')
    expect(s.headers['x-understudy-actor']).toBe('worker')
    expect(s.headers['content-type']).toBe('application/json')
    expect(Object.keys(s.headers).map((k) => k.toLowerCase())).not.toContain('origin')
    expect(s.body).toEqual({ kind: 'file_text', purpose: 'legacy.embed', provider: 'gemini', model: 'gemini-embedding-2', bytes: 10_000, count: 12, source: 'real_screen', gate: OPEN })
  })

  it('the ticket reports the outcome to the result route, with the ledger id', async () => {
    const { gate, engine } = gateWith()
    const t = await gate.authorize(call())
    t.finish({ ok: true, latencyMs: 812.4, inputTokens: 400, outputTokens: 60 })
    await new Promise((r) => setTimeout(r, 10))
    expect(engine.seen).toHaveLength(2)
    expect(engine.seen[1].url).toBe('http://127.0.0.1:7700/privacy/ledger/direct/result')
    expect(engine.seen[1].body).toEqual({ ref: ID, ok: true, latency_ms: 812, input_tokens: 400, output_tokens: 60 })
  })

  it('a failing result report never throws', async () => {
    let n = 0
    const { gate } = gateWith({ reply: () => (n++ === 0 ? allowed() : 'down') })
    const t = await gate.authorize(call())
    expect(() => t.finish({ ok: false, latencyMs: 5 })).not.toThrow()
    await new Promise((r) => setTimeout(r, 10))
  })

  it.each([
    ['a 503 (ledger unwritable)', { status: 503, json: { error: { code: 'ledger_unwritable' } } }],
    ['a 404 (privacy extension off)', { status: 404, json: { error: { code: 'extension_off' } } }],
    ['a 422', { status: 422, json: { error: { code: 'invalid_request' } } }],
    ['a 200 without a ledger id', { status: 200, json: { allowed: true } }],
    ['a 200 with a malformed ledger id', { status: 200, json: { allowed: true, ledger_id: 'row-1' } }],
    ['an unreadable 200', { status: 200, json: 'allowed' }],
    ['no engine at all', 'down' as const],
  ])('%s: no request may be made', async (_label, reply) => {
    const { gate } = gateWith({ reply: () => reply })
    await expect(gate.authorize(call())).rejects.toMatchObject({ reason: 'ledger_unavailable' })
  })

  it('a 200 allowed:false is a refusal with the engine\'s reason', async () => {
    const { gate } = gateWith({ reply: () => ({ status: 200, json: { allowed: false, status: 'blocked', reason: 'denylisted_app', ledger_id: ID } }) })
    await expect(gate.authorize(call())).rejects.toMatchObject({ reason: 'denylisted_app' })
    const { gate: g2 } = gateWith({ reply: () => ({ status: 200, json: { allowed: false, reason: 'something new' } }) })
    await expect(g2.authorize(call())).rejects.toMatchObject({ reason: 'ledger_unavailable' })
  })

  it('refuses to be built for a service that is not on this machine', () => {
    expect(() => createLegacyRemoteGate({ engineUrl: 'https://example.com', gates: async () => OPEN })).toThrow(/on this machine/)
  })

  it('does not announce a call the ledger would reject (bad purpose, model, size), and makes no request for it', async () => {
    const { gate, engine } = gateWith()
    for (const bad of [{ purpose: 'Ada Lovelace review' }, { model: 'models/gemini' }, { model: '' }, { bytes: -1 }, { bytes: 1.5 }, { count: 0 }, { provider: 'Gemini' }] as Array<Partial<LegacyCall>>) {
      await expect(gate.authorize(call(bad))).rejects.toMatchObject({ reason: 'bad_call' })
    }
    expect(engine.seen).toHaveLength(0)
  })

  it('the kill switch stops a call before anything is probed or sent', async () => {
    const { gate, engine } = gateWith({ killed: () => true })
    await expect(gate.authorize(call())).rejects.toMatchObject({ reason: 'killed' })
    expect(engine.seen).toHaveLength(0)
  })
})

describe('the four gates (privacy ImageGate precedence for real_screen)', () => {
  it('localReason: unattended, then secure input, then a denylisted app, then no consent', () => {
    expect(localReason(OPEN)).toBeNull()
    expect(localReason({ consent: false, denylisted_app: true, secure_input: true, unattended: true })).toBe('unattended')
    expect(localReason({ consent: false, denylisted_app: true, secure_input: true, unattended: false })).toBe('secure_input')
    expect(localReason({ consent: false, denylisted_app: true, secure_input: false, unattended: false })).toBe('denylisted_app')
    expect(localReason({ consent: false, denylisted_app: false, secure_input: false, unattended: false })).toBe('no_consent')
  })

  it.each<[Partial<GateBooleans>, string]>([
    [{ unattended: true }, 'unattended'],
    [{ secure_input: true }, 'secure_input'],
    [{ denylisted_app: true }, 'denylisted_app'],
    [{ consent: false }, 'no_consent'],
  ])('a closed gate (%j) refuses with %s and the refusal is still announced so the ledger shows it', async (closed, reason) => {
    const { gate, engine } = gateWith({ gates: { ...OPEN, ...closed } })
    await expect(gate.authorize(call())).rejects.toMatchObject({ reason })
    expect(engine.seen).toHaveLength(1)
    expect(engine.seen[0].body.gate).toEqual({ ...OPEN, ...closed })
  })

  it('unattended real_screen blocks even when the engine would have allowed it', async () => {
    const { gate } = gateWith({ gates: { ...OPEN, unattended: true }, reply: allowed })
    await expect(gate.authorize(call())).rejects.toMatchObject({ reason: 'unattended' })
  })

  it('there is no sandbox exception: a caller cannot claim one to get past unattended', async () => {
    const { gate, engine } = gateWith({ gates: { ...OPEN, unattended: true } })
    await expect(gate.authorize(call({ source: 'sandbox' }))).rejects.toMatchObject({ reason: 'unattended' })
    expect(engine.seen[0].body.source).toBe('sandbox') // announced as claimed; the local gate (always the real_screen precedence) still blocks
  })

  it('an unreadable gate state is a closed gate', async () => {
    const { gate } = gateWith({
      gates: async () => {
        throw new Error('probe failed')
      },
    })
    await expect(gate.authorize(call())).rejects.toMatchObject({ reason: 'unattended' })
  })
})

describe('legacyGateReader (the real probes, faked)', () => {
  const src = (over: Partial<Parameters<typeof legacyGateReader>[0]> = {}) =>
    legacyGateReader({
      frontmost: { read: async () => 'com.apple.finder' },
      console: { read: async () => ({ secureInput: 'off' as const, locked: false }) },
      deny: () => ({ strict: true, workerList: [] }),
      consent: () => true,
      idleSeconds: () => 4,
      awaySeconds: () => 60,
      ...over,
    })

  it('open when attended, a normal app, no password field and consent given', async () => {
    expect(await src()(call())).toEqual(OPEN)
  })

  it('a password manager, the worker\'s own list and (strict) a messaging app are denylisted', async () => {
    expect((await src({ frontmost: { read: async () => 'com.1password.1password' } })(call())).denylisted_app).toBe(true)
    expect((await src({ frontmost: { read: async () => 'com.example.mine' }, deny: () => ({ strict: true, workerList: ['com.example.mine'] }) })(call())).denylisted_app).toBe(true)
    expect((await src({ frontmost: { read: async () => 'com.tinyspeck.slackmacgap' } })(call())).denylisted_app).toBe(true)
    expect((await src({ frontmost: { read: async () => 'com.tinyspeck.slackmacgap' }, deny: () => ({ strict: false, workerList: [] }) })(call())).denylisted_app).toBe(false)
  })

  it('secure input on is a block; unknown is a block for images and audio in strict mode, but not for text', async () => {
    const unknown = { console: { read: async () => ({ secureInput: 'unknown' as const, locked: null }) } }
    expect((await src({ console: { read: async () => ({ secureInput: 'on' as const, locked: false }) } })(call({ kind: 'text' }))).secure_input).toBe(true)
    expect((await src(unknown)(call({ kind: 'image' }))).secure_input).toBe(true)
    expect((await src(unknown)(call({ kind: 'audio' }))).secure_input).toBe(true)
    expect((await src(unknown)(call({ kind: 'text' }))).secure_input).toBe(false)
    expect((await src({ ...unknown, deny: () => ({ strict: false, workerList: [] }) })(call({ kind: 'image' }))).secure_input).toBe(false)
  })

  it('an unreadable frontmost app counts as denylisted for images in strict mode only', async () => {
    const none = { frontmost: { read: async () => null } }
    expect((await src(none)(call({ kind: 'image' }))).denylisted_app).toBe(true)
    expect((await src(none)(call({ kind: 'file_text' }))).denylisted_app).toBe(false)
  })

  it('unattended after awaySeconds of idle (never under 3 s), or when idle time cannot be read', async () => {
    expect((await src({ idleSeconds: () => 59 })(call())).unattended).toBe(false)
    expect((await src({ idleSeconds: () => 60 })(call())).unattended).toBe(true)
    expect((await src({ idleSeconds: () => 2, awaySeconds: () => 0 })(call())).unattended).toBe(false)
    expect((await src({ idleSeconds: () => null })(call())).unattended).toBe(true)
  })

  it('consent comes from the caller per kind', async () => {
    const seen: string[] = []
    await src({ consent: (k) => (seen.push(k), false) })(call({ kind: 'audio' }))
    expect(seen).toEqual(['audio'])
    expect((await src({ consent: (k) => k === 'text' })(call({ kind: 'image' }))).consent).toBe(false)
  })
})

describe('helpers', () => {
  it('purposeId squeezes a call name into the ledger alphabet', () => {
    expect(purposeId('grounder.primary')).toBe('legacy.grounder_primary')
    expect(purposeId('port.vision')).toBe('legacy.port_vision')
    expect(purposeId('Files Extract!')).toBe('legacy.files_extract')
    expect(purposeId('9')).toBe('legacy.call')
    expect(purposeId('x'.repeat(80)).length).toBeLessThanOrEqual('legacy.'.length + 30)
    for (const n of ['grounder.primary', 'a b c', '!!', '']) expect(purposeId(n)).toMatch(/^[a-z][a-z0-9_]{1,30}(\.[a-z][a-z0-9_]{1,30}){0,2}$/)
  })

  it('base64Bytes and measureCompletion count bytes, never content', () => {
    expect(base64Bytes('QUJD')).toBe(3)
    expect(base64Bytes('QUI=')).toBe(2)
    expect(base64Bytes('QQ==')).toBe(1)
    expect(measureCompletion({ text: 'hello', system: 'sys' })).toEqual({ kind: 'text', bytes: 8, count: 1 })
    expect(measureCompletion({ text: 'hi', images: [{ jpegBase64: 'QUJD' }, { jpegBase64: 'QUJDQUJD' }] })).toEqual({ kind: 'image', bytes: 2 + 3 + 6, count: 2 })
  })
})
