import { describe, expect, it } from 'vitest'
import { AUTH_TOKENS_URL, TokenError, checkLiveModel, createTokenMinter } from './token'

const KEY = 'AIzaSy-THIS-IS-A-FAKE-TEST-KEY-0000000000'
const env = { GEMINI_API_KEY: KEY }

function fakeFetch(resp: { status: number; body?: unknown } | 'throw' | 'badjson') {
  const calls: Array<{ url: string; init: RequestInit }> = []
  const f = (async (url: string, init: RequestInit) => {
    calls.push({ url: String(url), init })
    if (resp === 'throw') throw new TypeError(`fetch failed for ${String(url)} with ${KEY}`)
    return { status: resp === 'badjson' ? 200 : resp.status, ok: resp === 'badjson' ? true : resp.status < 400, json: async () => (resp === 'badjson' ? Promise.reject(new Error('x')) : resp.body) } as unknown as Response
  }) as unknown as typeof fetch
  return { f, calls }
}

describe('the token minter', () => {
  it('sends the key in one header only, asks for a one-use model-locked token, and returns only the token', async () => {
    const { f, calls } = fakeFetch({ status: 200, body: { name: 'auth_tokens/ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuv' } })
    const t = await createTokenMinter({ env, fetchImpl: f, now: () => 1_000_000 }).mint('some-live-model')
    expect(t.token.startsWith('auth_tokens/')).toBe(true)
    expect(t.expiresAt).toBe(1_000_000 + 600_000)
    const c = calls[0]!
    expect(c.url).toBe(AUTH_TOKENS_URL)
    expect(c.url).not.toContain(KEY)
    expect((c.init.headers as Record<string, string>)['x-goog-api-key']).toBe(KEY)
    const body = JSON.parse(String(c.init.body))
    // The field mask names ONLY the model. Without it the server locks the whole setup to the one in the token (no tools), and the model
    // never sees a declared tool: found by the real-model probe on 7 Nov 2026.
    expect(body).toMatchObject({ uses: 1, bidiGenerateContentSetup: { model: 'models/some-live-model' }, fieldMask: 'model' })
    expect(JSON.stringify(body)).not.toContain(KEY)
    expect(new Date(body.newSessionExpireTime).getTime() - 1_000_000).toBe(60_000)
    expect(JSON.stringify(t)).not.toContain(KEY)
  })
  it('can leave the token open (no constraint at all) or lock the whole setup; the default locks only the model', async () => {
    const body = async (lock?: 'model' | 'none' | 'setup') => {
      const { f, calls } = fakeFetch({ status: 200, body: { name: 'auth_tokens/ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuv' } })
      await createTokenMinter({ env, fetchImpl: f, lock }).mint('m1')
      return JSON.parse(String(calls[0]!.init.body))
    }
    expect(await body()).toMatchObject({ fieldMask: 'model', bidiGenerateContentSetup: { model: 'models/m1' } })
    expect(await body('none')).not.toHaveProperty('bidiGenerateContentSetup')
    expect(await body('none')).not.toHaveProperty('fieldMask')
    expect(await body('setup')).not.toHaveProperty('fieldMask')
  })
  it('says there is no key, without trying the network', async () => {
    const { f, calls } = fakeFetch({ status: 200, body: {} })
    await expect(createTokenMinter({ env: {}, fetchImpl: f }).mint('m')).rejects.toMatchObject({ code: 'no_key' })
    await expect(createTokenMinter({ env: { GEMINI_API_KEY: '  ' }, fetchImpl: f }).mint('m')).rejects.toMatchObject({ code: 'no_key' })
    expect(calls).toHaveLength(0)
  })
  it.each([
    [{ status: 401, body: { error: { message: `bad key ${KEY}` } } }, 'refused'],
    [{ status: 403, body: {} }, 'refused'],
    [{ status: 400, body: {} }, 'refused'],
    [{ status: 429, body: {} }, 'refused'],
    [{ status: 500, body: {} }, 'network'],
    ['throw', 'network'],
    ['badjson', 'bad_response'],
    [{ status: 200, body: { name: 'not-a-token' } }, 'bad_response'],
    [{ status: 200, body: { name: 'auth_tokens/short' } }, 'bad_response'],
    [{ status: 200, body: null }, 'bad_response'],
  ] as const)('maps %j to %s, and no error message ever carries the key or the response', async (resp, code) => {
    const { f } = fakeFetch(resp as never)
    const err = await createTokenMinter({ env, fetchImpl: f }).mint('m').then(() => null, (e: unknown) => e)
    expect(err).toBeInstanceOf(TokenError)
    expect((err as TokenError).code).toBe(code)
    expect(String((err as Error).message)).not.toContain(KEY)
    expect(String((err as Error).message)).not.toContain('AIza')
    expect(JSON.stringify(err)).not.toContain(KEY)
  })
  it('only talks to https (or a loopback test server)', () => {
    expect(() => createTokenMinter({ env, url: 'http://example.com/auth_tokens' })).toThrow()
    expect(() => createTokenMinter({ env, url: 'http://127.0.0.1:9/auth_tokens' })).not.toThrow()
  })
})

describe('the boot check of the configured model', () => {
  it('passes for a model that can stream, and says why when it cannot', async () => {
    const ok = fakeFetch({ status: 200, body: { supportedGenerationMethods: ['generateContent', 'bidiGenerateContent'] } })
    expect(await checkLiveModel('m1', { env, fetchImpl: ok.f })).toEqual({ ok: true, reason: 'ok' })
    expect(ok.calls[0]!.url).toContain('/models/m1')
    expect(ok.calls[0]!.url).not.toContain(KEY)
    expect(await checkLiveModel('m1', { env, fetchImpl: fakeFetch({ status: 200, body: { supportedGenerationMethods: ['generateContent'] } }).f })).toEqual({ ok: false, reason: 'cannot_stream' })
    expect(await checkLiveModel('m1', { env, fetchImpl: fakeFetch({ status: 404, body: {} }).f })).toEqual({ ok: false, reason: 'unknown_model' })
    expect(await checkLiveModel('m1', { env, fetchImpl: fakeFetch('throw').f })).toEqual({ ok: false, reason: 'unreachable' })
    expect(await checkLiveModel(null, { env })).toEqual({ ok: false, reason: 'no_model' })
    expect(await checkLiveModel('m1', { env: {} })).toEqual({ ok: false, reason: 'no_key' })
  })
})
