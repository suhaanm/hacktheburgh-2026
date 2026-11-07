import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { createReplayFetch, replayModeFromEnv, requestKey } from './index'

const BIG = 'A'.repeat(5000)
const URL_ = 'https://generativelanguage.googleapis.com/v1beta/interactions'
const body = (target: string, pixels: string) =>
  JSON.stringify({ model: 'gemini-3.8-flash', store: false, input: [{ type: 'image', data: pixels, mime_type: 'image/jpeg' }, { type: 'text', text: `Find: ${target}` }] })

describe('requestKey', () => {
  it('ignores image bytes and key order but not the prompt text', () => {
    const a = requestKey('POST', '/v1beta/interactions', body('Start call button', BIG))
    const b = requestKey('POST', '/v1beta/interactions', body('Start call button', 'B'.repeat(7000)))
    const c = requestKey('POST', '/v1beta/interactions', body('Join button', BIG))
    expect(a).toBe(b)
    expect(a).not.toBe(c)
    const reordered = JSON.stringify({ input: JSON.parse(body('Start call button', BIG)).input, store: false, model: 'gemini-3.8-flash' })
    expect(requestKey('POST', '/v1beta/interactions', reordered)).toBe(a)
  })
})

describe('Request-object calls (what the Google SDK sends)', () => {
  it('keys on the body inside a Request, so different prompts get different keys', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'replay-test-'))
    const fake = (async () => new Response('{"steps":[]}', { status: 200, headers: { 'content-type': 'application/json' } })) as unknown as typeof fetch
    const rec = createReplayFetch({ dir, mode: 'record', realFetch: fake })
    await rec.fetch(new Request(URL_, { method: 'POST', body: body('Start call button', BIG) }))
    await rec.fetch(new Request(URL_, { method: 'POST', body: body('Join button', BIG) }))
    expect(fs.readdirSync(dir)).toHaveLength(2)
    const offline = createReplayFetch({ dir, mode: 'replay', realFetch: fake })
    expect((await offline.fetch(new Request(URL_, { method: 'POST', body: body('Join button', 'D'.repeat(6000)) }))).status).toBe(200)
    await expect(offline.fetch(new Request(URL_, { method: 'POST', body: body('Other', BIG) }))).rejects.toThrow('fetch failed')
  })
})

describe('record then replay', () => {
  it('records a JSON response and serves it offline; a miss fails like a dead network', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'replay-test-'))
    let network = 0
    const fake = (async () => {
      network++
      return new Response(JSON.stringify({ steps: [{ type: 'model_output', content: [{ type: 'text', text: '{"found":true}' }] }] }), { status: 200, headers: { 'content-type': 'application/json' } })
    }) as unknown as typeof fetch

    const rec = createReplayFetch({ dir, mode: 'record', realFetch: fake })
    const live = await rec.fetch(URL_, { method: 'POST', body: body('Start call button', BIG) })
    expect(live.status).toBe(200)
    expect(rec.stats.recorded).toBe(1)
    expect(fs.readdirSync(dir)).toHaveLength(1)

    const offline = createReplayFetch({ dir, mode: 'replay', realFetch: fake })
    const hit = await offline.fetch(URL_, { method: 'POST', body: body('Start call button', 'C'.repeat(6000)) })
    expect(await hit.json()).toMatchObject({ steps: expect.any(Array) })
    expect(network).toBe(1)
    await expect(offline.fetch(URL_, { method: 'POST', body: body('Something else', BIG) })).rejects.toThrow('fetch failed')
    expect(offline.stats).toMatchObject({ hits: 1, misses: 1 })
    expect(network).toBe(1)
  })

  it('does not record errors or token requests', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'replay-test-'))
    const fail = (async () => new Response('{"error":{}}', { status: 500, headers: { 'content-type': 'application/json' } })) as unknown as typeof fetch
    const rec = createReplayFetch({ dir, mode: 'record', realFetch: fail })
    await rec.fetch(URL_, { method: 'POST', body: body('x', BIG) })
    await rec.fetch('https://generativelanguage.googleapis.com/v1alpha/auth_tokens', { method: 'POST', body: '{}' })
    expect(rec.stats.recorded).toBe(0)
  })
})

describe('replayModeFromEnv', () => {
  it('maps the flags', () => {
    expect(replayModeFromEnv({})).toBe('off')
    expect(replayModeFromEnv({ ALONGSIDE_RECORD: '1' })).toBe('record')
    expect(replayModeFromEnv({ ALONGSIDE_REPLAY: '1' })).toBe('replay')
    expect(replayModeFromEnv({ ALONGSIDE_REPLAY: 'hybrid' })).toBe('hybrid')
  })
})
