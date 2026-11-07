import { describe, expect, it } from 'vitest'
import { createHttpClient } from './client'
import { CALM_SIGNALS } from './signals'

function fakeFetch(answer: (url: string, init: RequestInit) => { status?: number; json?: unknown } | Error) {
  const calls: Array<{ url: string; init: RequestInit }> = []
  const impl = (async (url: string | URL | Request, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} })
    const a = answer(String(url), init ?? {})
    if (a instanceof Error) throw a
    return { ok: (a.status ?? 200) < 400, status: a.status ?? 200, json: async () => a.json } as Response
  }) as typeof fetch
  return { impl, calls }
}

describe('the http client', () => {
  it('asks GET /attention/next with the person and the worker state and parses the answer', async () => {
    const f = fakeFetch(() => ({ json: { data: { item: null, badges: { needs_you: 3, waiting: 0, marker: 'needs_you', stopped: false }, digest_ready: false, poll_after_s: 2 } } }))
    const c = createHttpClient({ baseUrl: 'http://127.0.0.1:7700', person: () => 'p_ada', fetchImpl: f.impl })
    const out = await c.next({ ...CALM_SIGNALS, dnd: true }, 1_800_000_000_000)
    expect(out?.badges.needs_you).toBe(3)
    expect(f.calls[0].url).toContain('/attention/next?person=p_ada&')
    expect(f.calls[0].url).toContain('dnd=1')
    expect((f.calls[0].init.headers as Record<string, string>)['X-Understudy-Actor']).toBe('desktop')
  })

  it('submit sends the actor and returns the admission answer; feedback is the worker', async () => {
    const f = fakeFetch((url) => (url.includes('/events') ? { json: { item_id: 'i_9', show: true, coalesced: false, decision: { reason_code: 'shown_now' } } } : { json: {} }))
    const c = createHttpClient({ baseUrl: 'http://localhost:7700/', person: () => 'p_ada', fetchImpl: f.impl })
    expect(await c.submit({ type: 'cue_cue', subject: 'e_1' })).toEqual({ itemId: 'i_9', show: true, coalesced: false, reason: 'shown_now' })
    await c.feedback('i_9', 'followed', 3)
    const fb = f.calls[1]
    expect(JSON.parse(String(fb.init.body))).toEqual({ item_id: 'i_9', event: 'followed', seconds: 3 })
    expect((fb.init.headers as Record<string, string>)['X-Understudy-Actor']).toBe('worker')
    expect((fb.init.headers as Record<string, string>)['Content-Type']).toBe('application/json')
  })

  it('answers null (never throws) when the engine is down, refuses, or is not on this machine', async () => {
    const down = createHttpClient({ baseUrl: 'http://127.0.0.1:7700', person: () => 'p_ada', fetchImpl: fakeFetch(() => new Error('ECONNREFUSED')).impl })
    expect(await down.next(CALM_SIGNALS, 0)).toBeNull()
    expect(await down.submit({ type: 'run_finished', subject: 'r1' })).toBeNull()
    await expect(down.feedback('i', 'dismissed')).resolves.toBeUndefined()
    const off = createHttpClient({ baseUrl: 'http://127.0.0.1:7700', person: () => 'p_ada', fetchImpl: fakeFetch(() => ({ status: 404 })).impl })
    expect(await off.next(CALM_SIGNALS, 0)).toBeNull()
    const f = fakeFetch(() => ({ json: {} }))
    const remote = createHttpClient({ baseUrl: 'http://example.com', person: () => 'p_ada', fetchImpl: f.impl })
    expect(await remote.next(CALM_SIGNALS, 0)).toBeNull()
    expect(f.calls).toEqual([])
    const noone = createHttpClient({ baseUrl: 'http://127.0.0.1:7700', person: () => null, fetchImpl: f.impl })
    expect(await noone.next(CALM_SIGNALS, 0)).toBeNull()
    expect(f.calls).toEqual([])
  })
})
