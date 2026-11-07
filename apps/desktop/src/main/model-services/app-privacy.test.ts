// In-process end-to-end privacy probe: the REAL dispatcher, agents, teaching bundle, state store and debug server
// wired to the REAL Gemini services (fake capture + overlay + live bridge, since those need Electron). Drives the app
// through the debug HTTP like QA does, then checks that nothing sensitive reached logs or debug responses.
// Two modes: always-on STUBBED network (no API calls, canned model replies) and RUN_LIVE=1 PRIVACY_E2E=1 (real API; expensive:
// the agents ground every red-flag phrase, so one run makes dozens of requests).
import fs from 'node:fs'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'
import util from 'node:util'
import { describe, expect, it, vi } from 'vitest'
import type { Capture, Services } from '../../shared/contracts'
import type { Shot } from '../../shared/protocol'
import { createAgentsFromServices } from '../agents/wire'
import { Bus } from '../bus'
import { ConfirmBroker } from '../confirm'
import type { ServiceContext } from '../context'
import { startDebugServer } from '../debug-server'
import { SettingsStore } from '../settings'
import { StateStore } from '../state'
import { teachingBundle } from '../teaching'
import { createDispatcher } from '../tools/dispatcher'
import { mockLiveBridge, mockOverlay } from '../mocks'
import { createAi } from './client'
import { createGrounder, groundingPresetFromEnv } from './grounder'
import { createLessonArchitect } from './lesson-architect'
import { createRouter } from './router'
import { createScamAnalyst } from './scam-analyst'
import { createVerifier } from './verifier'
import { geminiDeps } from './index'

const RUN = process.env.RUN_LIVE === '1' && process.env.PRIVACY_E2E === '1'
const aiza = (rest: string) => ['AI', 'za', rest].join('') // built at runtime: no key-shaped literal in the repo
const STUB_KEY = aiza('STUB'.repeat(8) + 'x1')
const root = path.resolve(__dirname, '../../..')
const SECRET_MESSAGE =
  'Brightway Bank: your account has been LOCKED after suspicious activity. To keep your money you must verify within 2 hours. MESSAGE-SECRET-TEXT Visit https://brightway-verify.example/login and enter your customer number, then read us the six digit code we text you.'
const PROFILE_NOTE = 'PROFILE-SECRET-NOTE prefers very short sentences and dislikes jargon'

const freePort = () =>
  new Promise<number>((resolve, reject) => {
    const srv = net.createServer()
    srv.listen(0, '127.0.0.1', () => {
      const { port } = srv.address() as net.AddressInfo
      srv.close(() => resolve(port))
    })
    srv.on('error', reject)
  })

/** Minimal valid model reply for whichever service asked (stub mode). */
function canned(prompt: string): unknown {
  const out = (body: unknown) => [{ type: 'model_output', content: [{ type: 'text', text: JSON.stringify(body) }] }]
  if (prompt.includes('Find this one element')) return out({ found: true, box_2d: [900, 900, 960, 980], label: 'Send', reason: '', confidence: 0.9 })
  if (prompt.includes('checking whether a learner')) return out({ completed: true, confidence: 0.95, uncertain: false, evidence: 'ok', learner_misstep: '', next_hint: '' })
  if (prompt.includes('plan a short, gentle computer lesson'))
    return out({ skillId: 'custom', steps: [{ instruction: 'Press Send.', targetDescription: 'blue Send button', expectedOutcome: 'sent', hints: { l1: 'a', l2: 'b', l3: 'c' }, safetyCritical: false }] })
  if (prompt.includes('SPECIALIST: ORCHESTRATOR')) return out({ verdict: 'likely_scam', confidence: 0.8, message_text: SECRET_MESSAGE, red_flags: [{ phrase: 'LOCKED', why: 'Threat.' }, { phrase: 'read us the six digit code', why: 'Codes are secret.' }], advice: ["Don't click the link."] })
  if (prompt.includes('SPECIALIST:')) return out({ risk: 'high', summary: 's', findings: [{ phrase: 'LOCKED', why: 'Threat.' }], message_text: SECRET_MESSAGE })
  if (prompt.includes('Classify what a person said')) return out({ intent: 'lesson', confidence: 0.9 })
  return out({})
}

function windows(text: string, size = 80, step = 20): string[] {
  const out: string[] = []
  for (let i = 0; i + size <= text.length; i += step) out.push(text.slice(i, i + size))
  return out
}

async function probe(stub: boolean) {
  {
    {
      if (stub) vi.stubEnv('GEMINI_API_KEY', STUB_KEY)
      createAi() // live: loads REPO/.env into process.env
      const key = process.env.GEMINI_API_KEY ?? ''
      expect(key.length).toBeGreaterThan(10)

      // Record (never print) every outbound request while passing it through.
      const requests: Array<{ url: string; body: string; hasKeyHeader: boolean }> = []
      const realFetch = globalThis.fetch
      const innerFetch: typeof fetch = stub
        ? (async (input: unknown, init?: { body?: unknown }) => {
            const req = input instanceof Request ? input : null
            const body = typeof init?.body === 'string' ? init.body : req ? await req.clone().text() : ''
            const parsed = JSON.parse(body || '{}') as { input?: unknown }
            const promptText = JSON.stringify(parsed.input ?? '').replace(/\\n/g, '\n').replace(/\\"/g, '"')
            return new Response(JSON.stringify({ id: 'stub', status: 'completed', steps: canned(promptText) }), { status: 200, headers: { 'content-type': 'application/json' } })
          }) as typeof fetch
        : realFetch
      globalThis.fetch = (async (input: unknown, init?: { headers?: HeadersInit; body?: unknown }) => {
        const req = input instanceof Request ? input : null
        const body = typeof init?.body === 'string' ? init.body : req ? await req.clone().text() : ''
        const headers = new Headers(init?.headers ?? req?.headers)
        const url = req ? req.url : String(input)
        if (/generativelanguage\.googleapis\.com/.test(url)) requests.push({ url, body, hasKeyHeader: headers.has('x-goog-api-key') }) // loopback debug calls are not Google traffic
        return innerFetch(input as RequestInfo, init as RequestInit)
      }) as typeof fetch

      const logs: string[] = []
      const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'alongside-privacy-'))
      const settings = new SettingsStore(userDataDir)
      const state = new StateStore(settings.get())
      const bus = new Bus()
      // Same shape as src/main/index.ts: console.log(`[${scope}]`, ...args)
      const ctx: ServiceContext = {
        state, bus, settings, userDataDir,
        sendOverlay: () => undefined,
        sendDock: () => undefined,
        log: (scope, ...args) => logs.push(util.format(`[${scope}]`, ...args)),
      }

      const jpegBase64 = fs.readFileSync(path.join(root, 'spikes/grounding/shots/safety/scam-inject.jpg')).toString('base64')
      const shot = (): Shot => ({ id: 's', displayId: 1, widthPx: 1440, heightPx: 900, scaleFactor: 1, jpegBase64, takenAt: Date.now(), overlayHidden: true })
      const capture: Capture = { grab: async () => shot(), liveFrame: async () => ({ jpegBase64, changeScore: 0 }), watch: () => () => undefined }

      const s = {} as Services
      s.capture = capture
      s.overlay = mockOverlay(ctx)
      s.live = mockLiveBridge(ctx)
      s.grounder = createGrounder(geminiDeps(ctx, s), { preset: groundingPresetFromEnv() })
      s.verifier = createVerifier(geminiDeps(ctx, s))
      s.architect = createLessonArchitect(geminiDeps(ctx, s), { grounder: { ground: (r) => s.grounder.ground(r), prefetch: (r) => s.grounder.prefetch?.(r) } })
      s.scam = createScamAnalyst(geminiDeps(ctx, s))
      s.router = createRouter(geminiDeps(ctx, s))
      const bundle = teachingBundle(ctx, s)
      s.learner = bundle.learner
      s.levels = bundle.levels
      s.runner = bundle.runner
      s.teaching = bundle.teaching
      s.agents = createAgentsFromServices(ctx, s)

      const port = await freePort()
      process.env.ALONGSIDE_DEBUG_PORT = String(port)
      const dispatch = createDispatcher(ctx, s, new ConfirmBroker(state))
      const server = startDebugServer({ ctx, services: s, dispatch, session: { stop: () => undefined } as never })
      await new Promise((r) => setTimeout(r, 200))

      const responses: string[] = []
      const call = async (route: string, body?: unknown): Promise<unknown> => {
        const res = await realFetch(`http://127.0.0.1:${port}${route}`, body === undefined ? undefined : { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
        const text = await res.text()
        responses.push(text)
        return JSON.parse(text)
      }
      const tool = (name: string, args: unknown) => call('/tool', { name, args })
      const waitAgent = async (maxMs: number) => {
        const deadline = Date.now() + maxMs
        while (Date.now() < deadline) {
          const st = (await call('/state')) as { agents: Array<{ status: string }> }
          if (st.agents.length > 0 && st.agents.every((a) => a.status !== 'running')) return st
          await new Promise((r) => setTimeout(r, 1000))
        }
        return call('/state')
      }

      try {
        await call('/health')
        await tool('update_profile', { note: PROFILE_NOTE })
        const found = (await tool('point_at', { target: 'the Send button' })) as { found: boolean }
        await tool('spawn_agent', { kind: 'scam_check', task: 'Check this message', payload: { text: SECRET_MESSAGE } })
        await waitAgent(60_000)
        await tool('spawn_agent', { kind: 'scam_check', task: 'Check the message on my screen', payload: { useScreen: true } })
        await waitAgent(60_000)
        await tool('start_lesson', { goal: 'send a message to my friend' })
        await call('/state')

        const finalState = JSON.stringify(await call('/state'))
        const logBlob = logs.join('\n')
        const respBlob = responses.join('\n')
        const both = `${logBlob}\n${respBlob}`
        const imageRequests = requests.filter((r) => r.body.includes('"type":"image"'))

        const report = {
          debugRoutesCalled: responses.length,
          logLines: logs.length,
          googleRequests: requests.length,
          imageRequests: imageRequests.length,
          pointAtFound: found.found,
          stateBytes: finalState.length,
        }
        fs.writeFileSync(path.join(root, 'fixtures/safety/app-privacy.json'), JSON.stringify(report, null, 1))
        console.log('[app-privacy]', JSON.stringify(report))

        expect(logs.length, 'the run must actually have logged something').toBeGreaterThan(5)
        expect(imageRequests.length, 'screenshot-bearing requests were made').toBeGreaterThan(0)
        for (const r of imageRequests) expect(JSON.parse(r.body).store, 'screenshot request without store:false').toBe(false)
        for (const r of requests) {
          const keys = Object.keys(JSON.parse(r.body || '{}')).join(',')
          expect(JSON.parse(r.body || '{}').store, `request without store:false: ${new URL(r.url).pathname} keys=[${keys}]`).toBe(false)
          expect(r.url).not.toContain(key)
          expect(r.body).not.toContain(key)
          expect(r.hasKeyHeader).toBe(true)
        }
        expect(both).not.toContain(key)
        expect(both).not.toMatch(/AIza[0-9A-Za-z_-]{16,}/)
        expect(both).not.toContain(jpegBase64.slice(0, 200))
        expect(both).not.toMatch(/[A-Za-z0-9+/]{120,}/)
        expect(both).not.toContain('PROFILE-SECRET')
        expect(logBlob).not.toContain('MESSAGE-SECRET-TEXT')
        for (const w of windows(SECRET_MESSAGE)) {
          expect(logBlob.includes(w), `a log line contains message text: "${w.slice(0, 30)}…"`).toBe(false)
          expect(respBlob.includes(w), `a debug response contains message text: "${w.slice(0, 30)}…"`).toBe(false)
        }
      } finally {
        globalThis.fetch = realFetch
        server.close()
        s.agents.dispose?.()
      }
    }
  }
}

describe('app-level privacy probe (real dispatcher, agents, teaching, state, debug server)', () => {
  it('stubbed network: logs and debug responses carry no key, screenshot, profile text or full message text; every request is store:false', () => probe(true), 120_000)
  it.skipIf(!RUN)('live API: same checks against the real models', () => probe(false), 420_000)
})
