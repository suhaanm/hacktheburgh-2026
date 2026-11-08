import { describe, expect, it, vi } from 'vitest'
import { checkGeminiKey } from './token'

const reply = (status: number) => vi.fn(async () => new Response('{}', { status })) as unknown as typeof fetch

describe('the models boot check (Gemini)', () => {
  const env = { GEMINI_API_KEY: 'k-test', GEMINI_MODEL_ACCURATE: 'acc-model', GEMINI_MODEL_FAST: 'fast-model' }
  it('passes when the key is set and the service knows the configured model, and sends only the key header', async () => {
    const f = reply(200)
    expect(await checkGeminiKey({ env, fetchImpl: f })).toEqual({ ok: true, reason: 'ok' })
    const [url, init] = (f as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls[0]
    expect(url).toContain('/acc-model')
    expect(url).not.toContain('k-test')
    expect(init.headers).toEqual({ 'x-goog-api-key': 'k-test' })
  })
  it('says why it failed: no key, no model, an unknown model, or no answer', async () => {
    expect((await checkGeminiKey({ env: {}, fetchImpl: reply(200) })).reason).toBe('no_key')
    expect((await checkGeminiKey({ env: { GEMINI_API_KEY: 'k' }, fetchImpl: reply(200) })).reason).toBe('no_model')
    expect((await checkGeminiKey({ env, fetchImpl: reply(404) })).reason).toBe('unknown_model')
    expect((await checkGeminiKey({ env, fetchImpl: reply(500) })).reason).toBe('unreachable')
    expect((await checkGeminiKey({ env, fetchImpl: vi.fn(async () => { throw new Error('offline') }) as unknown as typeof fetch })).reason).toBe('unreachable')
  })
  it('falls back to the fast and then the live model id', async () => {
    const f = reply(200)
    await checkGeminiKey({ env: { GEMINI_API_KEY: 'k', GEMINI_MODEL_LIVE: 'live-model' }, fetchImpl: f })
    expect(((f as unknown as { mock: { calls: [string][] } }).mock.calls[0][0])).toContain('/live-model')
  })
})
