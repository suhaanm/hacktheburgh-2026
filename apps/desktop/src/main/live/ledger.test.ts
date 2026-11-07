import { describe, expect, it } from 'vitest'
import { createHttpLiveLedger, createMemoryLiveLedger, sha8Of, type LiveBatch } from './ledger'
import { isLoopbackUrl } from '../engine/endpoints'

const batch: LiveBatch = { count: 1, bytes: 12345, sha8: 'a'.repeat(16), width: 1024, height: 576, model: 'gemini-test-live', gate: { consent: true, denylisted_app: false, secure_input: false, unattended: false } }

function fakeFetch(handler: (url: string, init: RequestInit) => { status: number; body: unknown } | 'throw') {
  const calls: Array<{ url: string; init: RequestInit; body: any }> = []
  const f = (async (url: string, init: RequestInit) => {
    const r = handler(String(url), init)
    calls.push({ url: String(url), init, body: init.body ? JSON.parse(String(init.body)) : null })
    if (r === 'throw') throw new TypeError('connection refused')
    return { status: r.status, ok: r.status < 400, json: async () => r.body } as unknown as Response
  }) as unknown as typeof fetch
  return { f, calls }
}

describe('the frame batch rows', () => {
  it('announce with exactly the documented fields, before sending, to the engine on this machine', async () => {
    const { f, calls } = fakeFetch(() => ({ status: 200, body: { allowed: true, status: 'sending', reason: null, ledger_id: 'e_0123456789abcdef' } }))
    const l = createHttpLiveLedger({ engineUrl: 'http://127.0.0.1:7700/', isLoopback: isLoopbackUrl, fetchImpl: f })
    const a = await l.announce(batch)
    expect(a).toEqual({ allowed: true, reason: null, ref: 'e_0123456789abcdef' })
    expect(calls[0]!.url).toBe('http://127.0.0.1:7700/privacy/ledger/live')
    expect(Object.keys(calls[0]!.body).sort()).toEqual(['bytes', 'count', 'gate', 'height', 'model', 'provider', 'sha8', 'source', 'width'])
    expect(calls[0]!.body).toMatchObject({ source: 'real_screen', provider: 'gemini', gate: { consent: true, denylisted_app: false, secure_input: false, unattended: false } })
    expect(calls[0]!.body.latency_ms).toBeUndefined() // an announcement, not a report after the fact
    expect(JSON.stringify(calls[0]!.body).length).toBeLessThan(500) // far too small to carry a frame, audio or text
    expect((calls[0]!.init.headers as Record<string, string>)['x-understudy-actor']).toBe('worker')
  })
  it('completes the row with latency, ok and a cost estimate', async () => {
    const { f, calls } = fakeFetch(() => ({ status: 200, body: { ledger_id: 'e_0123456789abcdef', status: 'ok' } }))
    const l = createHttpLiveLedger({ engineUrl: 'http://127.0.0.1:7700', isLoopback: isLoopbackUrl, fetchImpl: f })
    await l.result('e_0123456789abcdef', { ok: true, latency_ms: 12.6, cost_estimate_usd: 0.000258123456 })
    expect(calls[0]!.url).toBe('http://127.0.0.1:7700/privacy/ledger/live/result')
    expect(calls[0]!.body).toEqual({ ref: 'e_0123456789abcdef', ok: true, latency_ms: 13, cost_estimate_usd: 0.000258 })
  })
  it.each([
    ['a refusal by the gate', { status: 200, body: { allowed: false, status: 'blocked', reason: 'secure_input', ledger_id: 'e_0123456789abcdef' } }, 'secure_input'],
    ['unattended', { status: 200, body: { allowed: false, reason: 'unattended' } }, 'unattended'],
    ['the extension being off (404 extension_off)', { status: 404, body: { error: { code: 'extension_off' } } }, 'ledger_unavailable'],
    ['the ledger not writable (503)', { status: 503, body: { error: { code: 'ledger_unwritable' } } }, 'ledger_unavailable'],
    ['a refused body (422)', { status: 422, body: { error: { code: 'invalid_request' } } }, 'ledger_unavailable'],
    ['an answer that is not an object', { status: 200, body: 'ok' }, 'ledger_unavailable'],
    ['an allowed answer without a usable ref', { status: 200, body: { allowed: true, ledger_id: 'nonsense' } }, 'ledger_unavailable'],
  ])('is not allowed on %s', async (_l, resp, reason) => {
    const { f } = fakeFetch(() => resp as never)
    const a = await createHttpLiveLedger({ engineUrl: 'http://127.0.0.1:7700', isLoopback: isLoopbackUrl, fetchImpl: f }).announce(batch)
    expect(a).toMatchObject({ allowed: false, reason, ref: null })
  })
  it('is not allowed when the engine cannot be reached (fail closed)', async () => {
    const { f } = fakeFetch(() => 'throw')
    expect(await createHttpLiveLedger({ engineUrl: 'http://127.0.0.1:7700', isLoopback: isLoopbackUrl, fetchImpl: f }).announce(batch)).toMatchObject({ allowed: false, reason: 'ledger_unavailable' })
  })
  it('refuses to be built for a host that is not this machine, and refuses a model id that is not shaped like one', async () => {
    expect(() => createHttpLiveLedger({ engineUrl: 'https://example.com', isLoopback: isLoopbackUrl })).toThrow(/this machine/)
    const { f, calls } = fakeFetch(() => ({ status: 200, body: {} }))
    const a = await createHttpLiveLedger({ engineUrl: 'http://127.0.0.1:7700', isLoopback: isLoopbackUrl, fetchImpl: f }).announce({ ...batch, model: 'a b/c' })
    expect(a.allowed).toBe(false)
    expect(calls).toHaveLength(0)
  })
  it('hashes a frame to sixteen hex characters without keeping it', () => {
    expect(sha8Of(Buffer.from('frame'))).toMatch(/^[0-9a-f]{16}$/)
    expect(sha8Of(Buffer.from('frame'))).toBe(sha8Of(Buffer.from('frame')))
  })
})

describe('the audio turn rows', () => {
  const turn = { model: 'gemini-test-live', gate: batch.gate, turn: 'converse' as const }
  it('announce with exactly the proposed fields; a 404 of ANY kind (route missing, extension off) is a hard no, never a pass-through', async () => {
    const ok = fakeFetch(() => ({ status: 200, body: { allowed: true, ledger_id: 'e_0123456789abcdef' } }))
    expect(await createHttpLiveLedger({ engineUrl: 'http://127.0.0.1:7700', isLoopback: isLoopbackUrl, fetchImpl: ok.f }).announceAudio(turn)).toEqual({ allowed: true, reason: null, ref: 'e_0123456789abcdef' })
    expect(ok.calls[0]!.url).toBe('http://127.0.0.1:7700/privacy/ledger/live/audio')
    expect(Object.keys(ok.calls[0]!.body).sort()).toEqual(['gate', 'model', 'provider', 'source', 'turn'])
    const missing = fakeFetch(() => ({ status: 404, body: { detail: 'Not Found' } }))
    expect(await createHttpLiveLedger({ engineUrl: 'http://127.0.0.1:7700', isLoopback: isLoopbackUrl, fetchImpl: missing.f }).announceAudio(turn)).toEqual({ allowed: false, reason: 'ledger_unavailable', ref: null })
    const off = fakeFetch(() => ({ status: 404, body: { error: { code: 'extension_off' } } }))
    expect(await createHttpLiveLedger({ engineUrl: 'http://127.0.0.1:7700', isLoopback: isLoopbackUrl, fetchImpl: off.f }).announceAudio(turn)).toMatchObject({ allowed: false, reason: 'ledger_unavailable' })
    const blocked = fakeFetch(() => ({ status: 200, body: { allowed: false, reason: 'denylisted_app' } }))
    expect(await createHttpLiveLedger({ engineUrl: 'http://127.0.0.1:7700', isLoopback: isLoopbackUrl, fetchImpl: blocked.f }).announceAudio(turn)).toMatchObject({ allowed: false, reason: 'denylisted_app' })
  })
  it('complete with seconds (capped), bytes and latency, and nothing else', async () => {
    const { f, calls } = fakeFetch(() => ({ status: 200, body: {} }))
    await createHttpLiveLedger({ engineUrl: 'http://127.0.0.1:7700', isLoopback: isLoopbackUrl, fetchImpl: f }).audioResult('e_0123456789abcdef', { ok: true, seconds: 12.345, bytes: 395_000.4, latency_ms: 9000 })
    expect(calls[0]!.url).toBe('http://127.0.0.1:7700/privacy/ledger/live/audio/result')
    expect(calls[0]!.body).toEqual({ ref: 'e_0123456789abcdef', ok: true, seconds: 12.3, bytes: 395_000, latency_ms: 9000 })
  })
})

describe('the in-memory ledger (tests, mock mode)', () => {
  it('records and refuses on demand', async () => {
    const l = createMemoryLiveLedger()
    expect((await l.announce(batch)).allowed).toBe(true)
    l.refuse('no_consent')
    expect(await l.announce(batch)).toMatchObject({ allowed: false, reason: 'no_consent' })
    expect(l.announced).toHaveLength(2)
  })
})
