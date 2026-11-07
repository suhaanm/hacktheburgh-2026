// D38 / H6: with UNDERSTUDY_LEGACY_REMOTE unset, none of the old Alongside paths that can send a screenshot, frame, file text or audio
// to OpenAI or Gemini can make a network request. Each path is run for real (the real provider, the real services, the real Gemini call
// path) against a stubbed global fetch that records every attempt. Then, with the flag ON, the same paths are checked for the order
// (announce to the ledger, then send, then report) and for a refusal that sends nothing.
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { LessonStep, LearnerSnapshot } from '../shared/protocol'
import { MODELS } from '../shared/models'
import { createAi, callModel, createGeminiDeps } from './gemini/client'
import { createEmbedderFromEnv } from './files/embed'
import { createGeminiExtractor } from './files/extract'
import { mintWakeToken } from './live-auth'
import { configureLegacyRemote, createLegacyRemoteGate, type GateBooleans } from './legacy-remote'
import { proposeNext } from './agency/computer-use'
import { createAgentModelPort } from './agents/model-port-adapter'
import { createModelPortFromEnv, ModelPortError } from './model-port'
import { createOpenAiProvider } from './model-port/openai'
import { testShot } from './model-port/fake-port.test-util'
import { createGrounder, createLessonArchitect, createRouter, createScamAnalyst, createVerifier } from './model-services'

const OPENAI_ENV = { OPENAI_API_KEY: 'sk-test-0123456789abcdefghijklmnop', OPENAI_MODEL_PLANNER: 'plan-x', OPENAI_MODEL_FAST: 'fast-x', OPENAI_MODEL_COMPUTER_USE: 'cu-x' }
const OPEN: GateBooleans = { consent: true, denylisted_app: false, secure_input: false, unattended: false }
const learner: LearnerSnapshot = { skills: {} as LearnerSnapshot['skills'], confidenceLog: [], attempts: [], whatWorks: [], avoidJargon: [] }
const step: LessonStep = { id: 's1', index: 0, instruction: 'Press Start.', targetDescription: 'green button', expectedOutcome: 'A window opens.', hints: { l1: 'a', l2: 'b', l3: 'c' }, safetyCritical: false }

let attempts: string[] = []
let savedEnv: NodeJS.ProcessEnv

beforeEach(() => {
  savedEnv = { ...process.env }
  delete process.env.UNDERSTUDY_LEGACY_REMOTE
  delete process.env.ALONGSIDE_MOCK
  delete process.env.ALONGSIDE_MOCK_LIVE_AUTH
  delete process.env.UNDERSTUDY_MOCK
  process.env.GEMINI_API_KEY = 'AIza-test-key-not-real'
  attempts = []
  configureLegacyRemote(null)
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: unknown) => {
      attempts.push(String((input as { url?: string })?.url ?? input))
      throw new Error('a legacy path reached the network')
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  process.env = savedEnv
  configureLegacyRemote(null)
})

const real = () => createModelPortFromEnv({ env: OPENAI_ENV })

describe('flag off (the default): not one request from any legacy path', () => {
  it('the OpenAI provider: complete, vision, plan, read, check, computerStep and the boot check', async () => {
    const port = real()
    const shot = { jpegBase64: 'QUJD', detail: 'high' as const }
    await expect(port.vision(shot, 'what is this?')).rejects.toMatchObject({ code: 'blocked' })
    await expect(port.plan([{ role: 'user', content: 'hello' }])).rejects.toMatchObject({ code: 'blocked' })
    await expect(port.read('some page text', { name: 'x', schema: { type: 'object', properties: {} } })).rejects.toMatchObject({ code: 'blocked' })
    await expect(port.check('is it ok?', { name: 'x', schema: { type: 'object', properties: {} } })).rejects.toMatchObject({ code: 'blocked' })
    await expect(port.complete({ name: 't.x', tier: 'fast', text: 'hi', timeoutMs: 2000 })).rejects.toBeInstanceOf(ModelPortError)
    await expect(port.computerStep({ goal: 'press five', history: [], screenshot: { ...shot, widthPx: 10, heightPx: 10 }, timeoutMs: 2000 })).rejects.toMatchObject({ code: 'blocked' })
    const boot = await port.bootCheck()
    expect(boot.ok).toBe(false)
    expect(boot.problem).toMatch(/UNDERSTUDY_LEGACY_REMOTE/)
    expect(attempts).toEqual([])
  })

  it('a provider given its own fetch and a permissive gate still sends nothing without the flag', async () => {
    const own = vi.fn()
    const p = createOpenAiProvider({ env: OPENAI_ENV, fetchImpl: own as unknown as typeof fetch, remote: { authorize: async () => ({ finish: () => undefined }) } })
    await expect(p.complete({ name: 't.x', tier: 'fast', text: 'hi', timeoutMs: 2000 })).rejects.toMatchObject({ code: 'blocked' })
    expect(own).not.toHaveBeenCalled()
  })

  it('the model services: grounder, verifier, scam analyst, lesson architect and router', async () => {
    const port = real()
    const deps = { port, log: () => undefined }
    const shot = testShot('flag-off')
    const g = await createGrounder(deps).ground({ target: 'the green button', shot, precise: true }).catch((e: unknown) => e)
    const v = await createVerifier(deps).verify({ step, shot }).catch((e: unknown) => e)
    const s = await createScamAnalyst(deps).analyze({ text: 'Your parcel is held, pay a fee at http://example.test/x', shot }).catch((e: unknown) => e)
    const a = await createLessonArchitect(deps).plan({ goal: 'Call my granddaughter', learner }).catch((e: unknown) => e)
    const r = await createRouter(deps).classify('please make the text on my screen bigger and easier to read').catch((e: unknown) => e)
    void [g, v, s, a, r] // each degrades or throws in its own plain way; what matters is that nothing was sent
    expect(attempts).toEqual([])
  })

  it('act-for-me: the computer step', async () => {
    await expect(proposeNext({ port: real() }, { goal: 'open Calculator', history: [], shot: testShot('cu'), timeoutMs: 2000 })).rejects.toMatchObject({ code: 'blocked' })
    expect(attempts).toEqual([])
  })

  it('the coach agents: the web-search answer', async () => {
    const ctl = new AbortController()
    await expect(createAgentModelPort(real()).searchAnswer({ system: 's', prompt: 'is this site real?', signal: ctl.signal })).rejects.toBeDefined()
    expect(attempts).toEqual([])
  })

  it('the Gemini call path: createAi never builds a client, callModel is blocked, and an injected client is never called', async () => {
    await expect(createAi().interactions.create({ model: 'm', input: [] })).rejects.toMatchObject({ status: 403 })
    const deps = createGeminiDeps({ log: () => undefined })
    await expect(callModel(deps, { name: 'files.extract', model: 'm', timeoutMs: 3000, params: { input: [{ type: 'text', text: 'hi' }, { type: 'document', data: 'QUJD', mime_type: 'application/pdf' }] } })).rejects.toMatchObject({ code: 'blocked' })
    const create = vi.fn()
    await expect(callModel({ ...deps, ai: { interactions: { create } } }, { name: 'x.y', model: 'm', timeoutMs: 3000, params: { input: [] } })).rejects.toMatchObject({ code: 'blocked' })
    expect(create).not.toHaveBeenCalled()
    expect(attempts).toEqual([])
  })

  it('file embeddings: no embedder is built even with a key; file reading by Gemini defers', async () => {
    expect(createEmbedderFromEnv()).toBeNull()
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'legacy-files-'))
    const abs = path.join(dir, 'scan.pdf')
    fs.writeFileSync(abs, '%PDF-1.4 not a real pdf')
    const st = fs.statSync(abs)
    const r = await createGeminiExtractor(createGeminiDeps({ log: () => undefined })).extract({ abs, folder: dir, rel: 'scan.pdf', name: 'scan.pdf', ext: '.pdf', size: st.size, mtimeMs: st.mtimeMs })
    expect(r).toEqual({ ok: false, reason: 'deferred' })
    expect(attempts).toEqual([])
  })

  it('the wake-word token: no token is minted (no Gemini auth call)', async () => {
    await expect(mintWakeToken()).rejects.toThrow(/switched off/)
    expect(attempts).toEqual([])
  })

  it('the old renderer Live path cannot mint a token either', async () => {
    const { mintLiveToken } = await import('./live-auth')
    await expect(mintLiveToken()).rejects.toThrow(/talk key/)
    expect(attempts).toEqual([])
  })
})

describe('flag on, no gate configured: still nothing is sent (fail closed)', () => {
  it('the provider, the Gemini path and the wake token all refuse', async () => {
    process.env.UNDERSTUDY_LEGACY_REMOTE = '1'
    const port = createModelPortFromEnv({ env: { ...OPENAI_ENV, UNDERSTUDY_LEGACY_REMOTE: '1' } })
    await expect(port.vision({ jpegBase64: 'QUJD' }, 'x')).rejects.toMatchObject({ code: 'blocked' })
    await expect(callModel(createGeminiDeps({ log: () => undefined, ai: { interactions: { create: vi.fn() } } }), { name: 'x.y', model: 'm', timeoutMs: 3000, params: { input: [] } })).rejects.toMatchObject({ code: 'blocked' })
    await expect(mintWakeToken()).rejects.toBeDefined()
    expect(attempts).toEqual([])
  })
})

describe('flag on with a gate and a (fake) engine: announce, then send, then report', () => {
  function stack(opts: { gates?: GateBooleans; engine?: 'ok' | 'refuse' | 'down' | 'unwritable' } = {}) {
    const order: string[] = []
    const bodies: Array<Record<string, unknown>> = []
    const engineFetch = (async (url: string, init: RequestInit) => {
      const p = new URL(String(url)).pathname
      order.push(`engine:${p}`)
      bodies.push(JSON.parse(String(init.body)) as Record<string, unknown>)
      const e = opts.engine ?? 'ok'
      if (e === 'down') throw new Error('ECONNREFUSED')
      if (e === 'unwritable') return new Response(JSON.stringify({ error: { code: 'ledger_unwritable' } }), { status: 503 })
      if (p.endsWith('/result')) return new Response(JSON.stringify({ ledger_id: 'e_0123456789abcdef', status: 'ok' }), { status: 200 })
      return new Response(JSON.stringify(e === 'refuse' ? { allowed: false, status: 'blocked', reason: 'denylisted_app', ledger_id: 'e_0123456789abcdef' } : { allowed: true, status: 'sending', reason: null, ledger_id: 'e_0123456789abcdef' }), { status: 200 })
    }) as unknown as typeof fetch
    const openaiFetch = (async (url: string) => {
      order.push(`openai:${new URL(String(url)).pathname}`)
      return new Response(JSON.stringify({ id: 'r', status: 'completed', output: [{ type: 'message', content: [{ type: 'output_text', text: '{"ok":true}' }] }], usage: { input_tokens: 7, output_tokens: 3 } }), { status: 200 })
    }) as unknown as typeof fetch
    const remote = createLegacyRemoteGate({ env: { UNDERSTUDY_LEGACY_REMOTE: '1' }, engineUrl: 'http://127.0.0.1:7700', gates: async () => opts.gates ?? OPEN, fetchImpl: engineFetch })
    const provider = createOpenAiProvider({ env: { ...OPENAI_ENV, UNDERSTUDY_LEGACY_REMOTE: '1' }, fetchImpl: openaiFetch, remote })
    return { order, bodies, provider }
  }
  const shot = { jpegBase64: 'QUJDQUJD', detail: 'high' as const }

  it('an image request is announced (image kind, bytes, count, gates, no content), then sent, then its result is reported', async () => {
    process.env.UNDERSTUDY_LEGACY_REMOTE = '1'
    const { order, bodies, provider } = stack()
    const r = await provider.complete({ name: 'grounder.primary', tier: 'fast', text: 'where is the button?', images: [shot], timeoutMs: 3000, retries: 0 })
    expect(r.text).toContain('ok')
    await new Promise((res) => setTimeout(res, 20))
    expect(order).toEqual(['engine:/privacy/ledger/direct', 'openai:/v1/responses', 'engine:/privacy/ledger/direct/result'])
    expect(bodies[0]).toEqual({ kind: 'image', purpose: 'legacy.grounder_primary', provider: 'openai', model: 'fast-x', bytes: 20 + 6, count: 1, source: 'real_screen', gate: OPEN })
    expect(bodies[1]).toMatchObject({ ref: 'e_0123456789abcdef', ok: true, input_tokens: 7, output_tokens: 3 })
    expect(JSON.stringify(bodies)).not.toContain('QUJD')
    expect(JSON.stringify(bodies)).not.toContain('where is the button')
  })

  it.each([
    ['a denylisted app in front', { gates: { ...OPEN, denylisted_app: true } }],
    ['secure input on', { gates: { ...OPEN, secure_input: true } }],
    ['the worker away (unattended real_screen)', { gates: { ...OPEN, unattended: true } }],
    ['no consent', { gates: { ...OPEN, consent: false } }],
    ['the engine refusing', { engine: 'refuse' as const }],
    ['the ledger unwritable (503)', { engine: 'unwritable' as const }],
    ['the engine down', { engine: 'down' as const }],
  ])('%s: the request is never sent', async (_l, o) => {
    process.env.UNDERSTUDY_LEGACY_REMOTE = '1'
    const { order, provider } = stack(o)
    await expect(provider.complete({ name: 't.x', tier: 'fast', text: 'hi', images: [shot], timeoutMs: 3000, retries: 1 })).rejects.toMatchObject({ code: 'blocked' })
    expect(order.some((x) => x.startsWith('openai:'))).toBe(false)
  })

  it('each retry is announced again (every upload is an egress)', async () => {
    process.env.UNDERSTUDY_LEGACY_REMOTE = '1'
    const order: string[] = []
    const remote = { authorize: async () => (order.push('announce'), { finish: () => order.push('finish') }) }
    let n = 0
    const flaky = (async () => {
      order.push('send')
      return n++ === 0 ? new Response('{}', { status: 503 }) : new Response(JSON.stringify({ status: 'completed', output: [{ type: 'message', content: [{ type: 'output_text', text: 'ok' }] }] }), { status: 200 })
    }) as unknown as typeof fetch
    const p = createOpenAiProvider({ env: { ...OPENAI_ENV, UNDERSTUDY_LEGACY_REMOTE: '1' }, fetchImpl: flaky, remote })
    await p.complete({ name: 't.x', tier: 'fast', text: 'hi', timeoutMs: 5000, retries: 1 })
    expect(order.filter((x) => x === 'announce')).toHaveLength(2)
    expect(order.indexOf('announce')).toBeLessThan(order.indexOf('send'))
  })
})

describe('the legacy files are only reachable behind the gate', () => {
  it('no module outside the gated ones imports the SDK or names a provider URL', () => {
    const root = path.resolve(__dirname)
    const hits: string[] = []
    const walk = (dir: string): void => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const p = path.join(dir, e.name)
        if (e.isDirectory()) walk(p)
        else if (/\.tsx?$/.test(e.name) && !/\.test\.ts$/.test(e.name) && !/test-util/.test(e.name)) {
          const text = fs.readFileSync(p, 'utf8')
          if (/@google\/genai|api\.openai\.com|generativelanguage\.googleapis/.test(text)) hits.push(path.relative(root, p))
        }
      }
    }
    walk(root)
    // The gated legacy modules, plus main/live (its own gates, ledger and token minting; see src/main/live/static.test.ts).
    const allowed = ['gemini/client.ts', 'files/embed.ts', 'live-auth.ts', 'model-port/openai.ts', 'model-port/index.ts', 'model-port/env.ts', 'model-port/types.ts', 'model-services/scam-analyst.ts', 'agency/computer-use.ts']
    const stray = hits.filter((h) => !allowed.includes(h) && !h.startsWith('live/') && !h.startsWith('awareness/'))
    expect(stray).toEqual([])
    void MODELS
  })
})
