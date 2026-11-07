// Safety review, unit side (no API calls): privacy (store:false on the wire, log redaction) and failure honesty,
// through the model port (the real OpenAI provider over a fake fetch, and a fake port).
import fs from 'node:fs'
import path from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LearnerSnapshot } from '../../shared/protocol'
import { createModelPort, createOpenAiProvider, ModelPortError, plainFailure, redactArg, redactText, type ModelPort } from '../model-port'
import { apiError, fakePort, hasImage, modelOutput, sleep, testDeps, testShot, textInput } from '../model-port/fake-port.test-util'
import { withSafeLog, type ModelDeps } from './deps'
import { createGrounder as realCreateGrounder, type GroundConfig } from './grounder'
import { createLessonArchitect } from './lesson-architect'
import { createRouter } from './router'
import { createScamAnalyst } from './scam-analyst'
import { createVerifier } from './verifier'

// These scripts return boxes normalised to 0-1000 (the grounder's default is pixels; its own tests cover that).
const createGrounder = (deps: ModelDeps, cfg: GroundConfig = {}) => realCreateGrounder(deps, { coords: 'norm1000', ...cfg })

// Built at runtime so no key-shaped literal sits in the repo (secret scanners match the sk- and AIza shapes).
const aiza = (rest: string) => ['AI', 'za', rest].join('')
const FAKE_KEY = ['sk', '-proj-', 'FAKE'.repeat(8) + 'x1'].join('')
const ENV = { OPENAI_API_KEY: FAKE_KEY, OPENAI_MODEL_PLANNER: 'plan-x', OPENAI_MODEL_FAST: 'fast-x', OPENAI_MODEL_COMPUTER_USE: 'cu-x' }
const learner: LearnerSnapshot = {
  skills: {
    video_call: { level: 2, streakClean: 1, lastSeen: null, nextReview: null },
    spot_scam: { level: 1, streakClean: 0, lastSeen: null, nextReview: null },
    bigger_text: { level: 2, streakClean: 0, lastSeen: null, nextReview: null },
    custom: { level: 1, streakClean: 0, lastSeen: null, nextReview: null },
  } as LearnerSnapshot['skills'],
  confidenceLog: [],
  attempts: [],
  whatWorks: ['PROFILE-SECRET-NOTE likes short sentences'],
  avoidJargon: ['cursor'],
  lastSession: { at: 0, summary: 'PROFILE-SECRET-SUMMARY made a video call' },
}
const MESSAGE = 'Brightway Bank: your account is LOCKED. Pay the £1.45 fee within 24 hours or your money will be frozen. MESSAGE-SECRET-TEXT https://brightway-verify.example/login and more words to make this long enough to matter.'

/** Answers every service's prompt with a minimal valid reply, chosen from what the prompt asks. */
function answerFor(promptText: string) {
  if (promptText.includes('Find this one element')) return modelOutput({ found: true, box: [100, 100, 300, 150], label: 'Send', reason: '', confidence: 0.9 })
  if (promptText.includes('checking whether a learner')) return modelOutput({ completed: true, confidence: 0.95, uncertain: false, evidence: 'ok', learner_misstep: '', next_hint: '' })
  if (promptText.includes('plan a short, gentle computer lesson'))
    return modelOutput({ skillId: 'video_call', steps: [{ instruction: 'Press Send.', targetDescription: 'blue Send button', expectedOutcome: 'sent', hints: { l1: 'a', l2: 'b', l3: 'c' }, safetyCritical: false }] })
  if (promptText.includes('SPECIALIST: ORCHESTRATOR')) return modelOutput({ verdict: 'likely_scam', confidence: 0.8, message_text: MESSAGE, red_flags: [{ phrase: 'LOCKED', why: 'Threat.' }], advice: ["Don't click."] })
  if (promptText.includes('SPECIALIST:')) return modelOutput({ risk: 'high', summary: 's', findings: [{ phrase: 'LOCKED', why: 'Threat.' }] })
  if (promptText.includes('Classify what a person said')) return modelOutput({ intent: 'lesson', confidence: 0.9 })
  return modelOutput({})
}

/** A Responses API reply carrying `text` (what the OpenAI provider parses). */
const apiReply = (text: string) => ({ id: 'r1', status: 'completed', output: [{ type: 'message', content: [{ type: 'output_text', text }] }] })

/** The prompt text the service sent, read back out of a Responses API request body. */
function promptOf(body: { instructions?: string; input: Array<{ content: Array<{ type: string; text?: string }> }> }): string {
  return [body.instructions ?? '', ...body.input.flatMap((m) => m.content.filter((c) => c.type === 'input_text').map((c) => c.text ?? ''))].join('\n')
}

async function exerciseEveryService(deps: ReturnType<typeof testDeps>) {
  const shot = testShot('exercise')
  const grounder = createGrounder(deps)
  await grounder.ground({ target: 'the Send button', shot })
  await grounder.ground({ target: 'the Pay button', shot, precise: true })
  grounder.prefetch({ target: 'the Cancel button', shot })
  await sleep(20)
  await createVerifier(deps).verify({ expected: 'The message was sent.', shot })
  await createLessonArchitect(deps, { grounder }).plan({ goal: 'send a message', learner, shot })
  const scam = createScamAnalyst(deps)
  await scam.analyze({ text: MESSAGE })
  await scam.analyze({ shot })
  await createRouter(deps).classify('please help me send a message')
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe('log redaction', () => {
  it('removes API keys in every shape we could meet', () => {
    expect(redactText(`key ${FAKE_KEY} end`)).not.toContain(FAKE_KEY)
    expect(redactText(`https://x.googleapis.com/v1beta/interactions?key=${FAKE_KEY}&alt=json`)).not.toContain(FAKE_KEY)
    expect(redactText(`x-goog-api-key: ${FAKE_KEY}`)).not.toContain(FAKE_KEY)
    expect(redactText(`{"x-goog-api-key":"${FAKE_KEY}"}`)).not.toContain(FAKE_KEY)
    expect(redactText('Authorization: Bearer ya29.a0AfH6SMBabcdefghijklmnopqrstuvwxyz')).toContain('<redacted>')
    expect(redactText(`Error: API key not valid. key=${aiza('SyAbCdEfGhIjKlMnOpQrStUvWxYz0123456')}`)).not.toMatch(/AIza/)
    expect(redactText(`Incorrect API key provided: ${FAKE_KEY}.`)).not.toContain(FAKE_KEY)
    expect(redactText(`OPENAI_API_KEY=${FAKE_KEY}`)).not.toContain(FAKE_KEY)
    expect(redactText(`{"authorization":"Bearer ${FAKE_KEY}"}`)).not.toContain(FAKE_KEY)
  })
  it('removes screenshot-sized base64 and data URLs, keeps normal sentences', () => {
    const b64 = 'QUJD'.repeat(500)
    expect(redactText(`image ${b64} done`)).not.toContain(b64.slice(0, 200))
    expect(redactText(`<img src="data:image/jpeg;base64,${b64}">`)).toContain('<redacted image>')
    expect(redactText('Pay a fee within 24 hours please')).toBe('Pay a fee within 24 hours please')
  })
  it('cuts long arguments so a whole message cannot be logged, and handles Errors and objects', () => {
    const long = 'word '.repeat(200)
    expect(redactArg(long).length).toBeLessThan(400)
    expect(redactArg(new Error(`bad ${FAKE_KEY}`))).not.toContain(FAKE_KEY)
    expect(redactArg({ k: FAKE_KEY })).not.toContain(FAKE_KEY)
  })
})

describe('privacy: nothing is retained, and the key travels only in a header', () => {
  it('on the wire: every request from every service and path carries "store":false, with the key only in the Authorization header', async () => {
    const requests: Array<{ url: string; headers: Record<string, string>; body: string }> = []
    const fetchImpl = (async (url: string, init: RequestInit) => {
      const body = String(init.body ?? '')
      requests.push({ url: String(url), headers: Object.fromEntries(Object.entries((init.headers ?? {}) as Record<string, string>)), body })
      return new Response(JSON.stringify(apiReply(answerFor(promptOf(JSON.parse(body))))), { status: 200 })
    }) as unknown as typeof fetch
    const logs: string[] = []
    const port = createModelPort(createOpenAiProvider({ env: ENV, fetchImpl, log: (s, ...a) => logs.push(`${s} ${a.join(' ')}`) }))
    await exerciseEveryService(testDeps(port, { log: (s, ...a) => logs.push(`${s} ${a.join(' ')}`) }))
    expect(requests.length).toBeGreaterThanOrEqual(10)
    for (const r of requests) {
      expect(r.url).toBe('https://api.openai.com/v1/responses')
      expect(JSON.parse(r.body).store).toBe(false)
      expect(r.url).not.toContain(FAKE_KEY)
      expect(r.body).not.toContain(FAKE_KEY)
      expect(r.headers.authorization).toBe(`Bearer ${FAKE_KEY}`)
    }
    expect(requests.some((r) => r.body.includes('"type":"input_image"'))).toBe(true)
    // models come from the environment, per tier
    expect(new Set(requests.map((r) => JSON.parse(r.body).model))).toEqual(new Set(['fast-x', 'plan-x']))
    expect(logs.join('\n')).not.toContain(FAKE_KEY)
  })

  it('also on the paths that only run when something goes wrong (planner escalation, computer-tool fallback)', async () => {
    const requests: string[] = []
    const fetchImpl = (async (_url: string, init: RequestInit) => {
      const body = String(init.body ?? '')
      requests.push(body)
      const parsed = JSON.parse(body) as { instructions?: string; input: Array<{ content: Array<{ type: string; text?: string }> }>; tools?: unknown[] }
      const t = promptOf(parsed)
      if (Array.isArray(parsed.tools) && t.includes('DRY RUN')) return new Response(JSON.stringify({ output: [{ type: 'computer_call', call_id: 'c', actions: [{ type: 'click', x: 10, y: 10 }] }] }), { status: 200 })
      if (t.includes('Find this one element')) return new Response(JSON.stringify(apiReply(modelOutput({ found: true, box: [0, 0, 900, 900], label: '', reason: '', confidence: 0.9 }))), { status: 200 }) // oversize: forces the computer-tool fallback
      if (t.includes('checking whether a learner')) return new Response(JSON.stringify(apiReply(modelOutput({ completed: true, confidence: 0.4, uncertain: true, evidence: '', learner_misstep: '', next_hint: '' }))), { status: 200 }) // forces both verifier tiers
      return new Response(JSON.stringify(apiReply(answerFor(t))), { status: 200 })
    }) as unknown as typeof fetch
    const port = createModelPort(createOpenAiProvider({ env: ENV, fetchImpl }))
    const deps = testDeps(port)
    const shot = testShot('failpaths')
    await createGrounder(deps).ground({ target: 'abc', shot })
    await createVerifier(deps).verify({ expected: 'x', shot })
    expect(requests.some((b) => JSON.stringify(JSON.parse(b).tools ?? []).includes('"computer"'))).toBe(true)
    expect(new Set(requests.map((b) => JSON.parse(b).model))).toEqual(new Set(['fast-x', 'plan-x', 'cu-x']))
    for (const b of requests) expect(JSON.parse(b).store).toBe(false)
  })

  it('static: the only code that builds a /responses request body is the OpenAI provider, and it forces store:false', () => {
    const root = path.resolve(__dirname, '..')
    const offenders: string[] = []
    const walk = (dir: string) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, e.name)
        if (e.isDirectory()) walk(full)
        else if (/\.ts$/.test(e.name) && !/\.test\.|test-util|\.live\./.test(e.name)) {
          const src = fs.readFileSync(full, 'utf8')
          const rel = path.relative(root, full)
          if (/api\.openai\.com|\/responses['"`]/.test(src) && rel !== path.join('model-port', 'openai.ts')) offenders.push(`${rel}: talks to the OpenAI API outside the provider`)
          if (rel === path.join('model-port', 'openai.ts') && (src.match(/store:\s*false/g)?.length ?? 0) < 2) offenders.push(`${rel}: store:false missing on a request builder`)
        }
      }
    }
    walk(root)
    expect(offenders).toEqual([])
  })

  it('static: no model name is hard-coded in the port, the services, the agents or the agency (IDs come from OPENAI_MODEL_*)', () => {
    const root = path.resolve(__dirname, '..')
    const offenders: string[] = []
    for (const dir of ['model-port', 'model-services', 'agents', 'agency']) {
      const walk = (d: string) => {
        for (const e of fs.readdirSync(d, { withFileTypes: true })) {
          const full = path.join(d, e.name)
          if (e.isDirectory()) walk(full)
          else if (/\.ts$/.test(e.name) && !/\.test\.|test-util/.test(e.name)) {
            const hits = fs.readFileSync(full, 'utf8').match(/['"`](?:gpt-[\w.-]+|o[134]-[\w.-]+|gemini-[\w.-]+|computer-use-[\w.-]+|text-embedding-[\w.-]+)['"`]/g)
            if (hits) offenders.push(`${path.relative(root, full)}: ${hits.join(', ')}`)
          }
        }
      }
      walk(path.join(root, dir))
    }
    expect(offenders).toEqual([])
  })
})

describe('privacy: logs never contain screenshots, keys, profile text or message text', () => {
  it('across every service, including when the SDK errors with a key and a screenshot inside the message', async () => {
    const logs: string[] = []
    const shotB64 = 'QUJD'.repeat(2000)
    const shot = { ...testShot('log'), jpegBase64: shotB64 }
    const log = (s: string, ...a: unknown[]) => logs.push(`[${s}] ${a.map(String).join(' ')}`)
    // Healthy run
    const { port } = fakePort((p) => answerFor(textInput(p)))
    const deps = withSafeLog(testDeps(port, { log }))
    const grounder = createGrounder(deps)
    await grounder.ground({ target: 'the Send button', shot })
    await createVerifier(deps).verify({ expected: 'sent', shot })
    await createLessonArchitect(deps, { grounder }).plan({ goal: 'send a message', learner, shot })
    await createScamAnalyst(deps).analyze({ text: MESSAGE })
    await createRouter(deps).classify('please help me send a message')
    // Failing run: the error text carries a key, the screenshot and the message
    const failing = fakePort(() => {
      throw new ModelPortError('api', `400 bad request key=${FAKE_KEY} body=${shotB64} message=${MESSAGE}`, 400)
    })
    const fdeps = withSafeLog(testDeps(failing.port, { log }))
    await createGrounder(fdeps).ground({ target: 'the Send button', shot })
    await createVerifier(fdeps).verify({ expected: 'sent', shot })
    await createScamAnalyst(fdeps).analyze({ text: MESSAGE })
    await createRouter(fdeps).classify('please help me send a message')
    await createLessonArchitect(fdeps).plan({ goal: 'send a message', learner, shot }).catch(() => undefined)

    const all = logs.join('\n')
    expect(logs.length).toBeGreaterThan(5)
    expect(all).not.toContain(FAKE_KEY)
    expect(all).not.toContain(shotB64.slice(0, 200))
    expect(all).not.toContain('MESSAGE-SECRET-TEXT')
    expect(all).not.toContain('PROFILE-SECRET')
    expect(all).not.toMatch(/AIza[0-9A-Za-z_-]{16,}|sk-[0-9A-Za-z_-]{16,}/)
    expect(all).not.toMatch(/[A-Za-z0-9+/]{120,}/)
  })

  it('the redacting layer itself: whatever any code hands deps.log is scrubbed (defence in depth for future log lines)', () => {
    const lines: string[] = []
    const deps = withSafeLog(testDeps(fakePort(() => modelOutput({})).port, { log: (s, ...a) => lines.push(`${s} ${a.join(' ')}`) }))
    deps.log('x', `token ${FAKE_KEY}`, 'QUJD'.repeat(500), new Error(`boom ${FAKE_KEY}`), { nested: FAKE_KEY })
    expect(lines.join('\n')).not.toContain(FAKE_KEY)
    expect(lines.join('\n')).not.toMatch(/[A-Za-z0-9+/]{120,}/)
  })

  it('even a hand-built deps object with a raw logger is redacted by every factory', async () => {
    const lines: string[] = []
    const failing = fakePort(() => {
      throw new ModelPortError('api', `oops ${FAKE_KEY}`, 500)
    })
    const deps = { port: failing.port, log: (s: string, ...a: unknown[]) => lines.push(`${s} ${a.join(' ')}`) }
    await createGrounder(deps).ground({ target: 'x', shot: testShot('raw') })
    await createVerifier(deps).verify({ expected: 'x', shot: testShot('raw2') })
    expect(lines.join('\n')).not.toContain(FAKE_KEY)
  })
})

describe('failure honesty: plain English, never a fabricated box or verdict', () => {
  const PLAIN_BAD = /ModelPortError|\b(401|403|429|500|503)\b|undefined|\[object|at .*\.ts|stack|ECONN|fetch failed|api key|status|OPENAI/i
  const realProvider = (env: Record<string, string>, fetchImpl?: typeof fetch): ModelPort => createModelPort(createOpenAiProvider({ env, fetchImpl }))
  const scenarios: Array<{ name: string; make: () => ModelPort; expects: RegExp }> = [
    { name: 'no key (setup missing)', make: () => realProvider({ OPENAI_MODEL_PLANNER: 'p', OPENAI_MODEL_FAST: 'f', OPENAI_MODEL_COMPUTER_USE: 'c' }), expects: /isn't set up/i },
    { name: 'a model name is not configured', make: () => realProvider({ OPENAI_API_KEY: FAKE_KEY }), expects: /model name is missing/i },
    { name: 'key rejected (401)', make: () => realProvider(ENV, (async () => new Response('{}', { status: 401 })) as unknown as typeof fetch), expects: /isn't set up/i },
    { name: 'network down', make: () => realProvider(ENV, (async () => { throw new TypeError('fetch failed') }) as unknown as typeof fetch), expects: /can't reach the internet/i },
    { name: 'rate limited (429)', make: () => fakePort(() => { throw apiError(429, 'Resource exhausted') }).port, expects: /too many requests/i },
  ]

  for (const sc of scenarios) {
    describe(sc.name, () => {
      it('grounder: found:false with a plain reason, no box or point', async () => {
        const r = await createGrounder(testDeps(sc.make())).ground({ target: 'the Send button', shot: testShot(`g-${sc.name}`) })
        expect(r.found).toBe(false)
        expect(r.box).toBeUndefined()
        expect(r.point).toBeUndefined()
        expect(r.reason).toMatch(sc.expects)
        expect(r.reason).not.toMatch(PLAIN_BAD)
      })
      it('verifier: not completed, uncertain, plain evidence', async () => {
        const v = await createVerifier(testDeps(sc.make())).verify({ expected: 'sent', shot: testShot(`v-${sc.name}`) })
        expect(v.completed).toBe(false)
        expect(v.uncertain).toBe(true)
        expect(v.evidence).toMatch(sc.expects)
        expect(v.evidence).not.toMatch(PLAIN_BAD)
      })
      it('scam analyst: cannot_tell, never genuine, still points to a human', async () => {
        const r = await createScamAnalyst(testDeps(sc.make())).analyze({ text: MESSAGE })
        expect(r.verdict).toBe('cannot_tell')
        expect(r.redFlags).toEqual([])
        expect(r.advice.join(' ')).toMatch(sc.expects)
        expect(r.advice.join(' ')).not.toMatch(PLAIN_BAD)
        expect(r.humanHelp).toMatch(/back of your bank card/)
      })
      it('architect: rejects with a typed error that has a plain-English message (TEACH falls back)', async () => {
        const err = await createLessonArchitect(testDeps(sc.make())).plan({ goal: 'x', learner }).catch((e: unknown) => e)
        expect(err).toBeInstanceOf(ModelPortError)
        expect(plainFailure(err)).toMatch(sc.expects)
        expect(plainFailure(err)).not.toMatch(PLAIN_BAD)
      })
      it('router: falls back to keywords, never invents an intent for gibberish', async () => {
        const r = await createRouter(testDeps(sc.make())).classify('purple monkey dishwasher')
        expect(r.intent).toBe('unknown')
      })
    })
  }

  describe('a model that stalls (15 s in production, shortened here)', () => {
    const stall = () => fakePort(async () => { await sleep(5000); return modelOutput({}) }).port
    it('grounder returns found:false reason "timeout" promptly', async () => {
      const t0 = Date.now()
      const r = await createGrounder(testDeps(stall()), { timeoutMs: 120 }).ground({ target: 'x', shot: testShot('stall-g') })
      expect(r).toMatchObject({ found: false, reason: 'timeout' })
      expect(r.box).toBeUndefined()
      expect(Date.now() - t0).toBeLessThan(600)
    })
    it('verifier never ticks on a stall', async () => {
      const v = await createVerifier(testDeps(stall()), { fastTimeoutMs: 500, plannerTimeoutMs: 500 }).verify({ expected: 'x', shot: testShot('stall-v') })
      expect(v).toMatchObject({ completed: false, uncertain: true })
    })
    it('scam analyst gives up at its hard cap with cannot_tell', async () => {
      const t0 = Date.now()
      const r = await createScamAnalyst(testDeps(stall()), { stageATimeoutMs: 500, totalTimeoutMs: 900 }).analyze({ text: MESSAGE })
      expect(r.verdict).toBe('cannot_tell')
      expect(Date.now() - t0).toBeLessThan(2500)
    })
    it('architect rejects with a timeout inside its budget', async () => {
      const t0 = Date.now()
      await expect(createLessonArchitect(testDeps(stall()), { timeoutMs: 600, hedgeAfterMs: 0 }).plan({ goal: 'x', learner })).rejects.toMatchObject({ code: 'timeout' })
      expect(Date.now() - t0).toBeLessThan(1500)
    })
  })

  it('garbage from the model never becomes a verdict, a box or a tick', async () => {
    const { port } = fakePort(() => modelOutput('I am a helpful assistant and everything is fine!'))
    const deps = testDeps(port)
    expect((await createGrounder(deps).ground({ target: 'x', shot: testShot('junk-g') })).found).toBe(false)
    expect((await createVerifier(deps).verify({ expected: 'x', shot: testShot('junk-v') })).completed).toBe(false)
    expect((await createScamAnalyst(deps).analyze({ text: MESSAGE })).verdict).toBe('cannot_tell')
  })
})
