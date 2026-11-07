// Safety review, unit side (no API calls): privacy (store:false everywhere, log redaction) and failure honesty.
import fs from 'node:fs'
import path from 'node:path'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { LearnerSnapshot } from '../../shared/protocol'
import { MODELS } from '../../shared/models'
import { createAi, createGeminiDeps, GeminiError, plainFailure } from './client'
import { apiError, fakeAi, hasImage, modelOutput, sleep, testDeps, testShot, textInput } from './fake-ai.test-util'
import { createGrounder } from './grounder'
import { createLessonArchitect } from './lesson-architect'
import { redactArg, redactText } from './redact'
import { createRouter } from './router'
import { createScamAnalyst } from './scam-analyst'
import { createVerifier } from './verifier'

// Built at runtime so no key-shaped literal sits in the repo (secret scanners match the AIza shape).
const aiza = (rest: string) => ['AI', 'za', rest].join('')
const FAKE_KEY = aiza('FAKE'.repeat(8) + 'x1')
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
  if (promptText.includes('Find this one element')) return modelOutput({ found: true, box_2d: [100, 100, 150, 300], label: 'Send', reason: '', confidence: 0.9 })
  if (promptText.includes('checking whether a learner')) return modelOutput({ completed: true, confidence: 0.95, uncertain: false, evidence: 'ok', learner_misstep: '', next_hint: '' })
  if (promptText.includes('plan a short, gentle computer lesson'))
    return modelOutput({ skillId: 'video_call', steps: [{ instruction: 'Press Send.', targetDescription: 'blue Send button', expectedOutcome: 'sent', hints: { l1: 'a', l2: 'b', l3: 'c' }, safetyCritical: false }] })
  if (promptText.includes('SPECIALIST: ORCHESTRATOR')) return modelOutput({ verdict: 'likely_scam', confidence: 0.8, message_text: MESSAGE, red_flags: [{ phrase: 'LOCKED', why: 'Threat.' }], advice: ["Don't click."] })
  if (promptText.includes('SPECIALIST:')) return modelOutput({ risk: 'high', summary: 's', findings: [{ phrase: 'LOCKED', why: 'Threat.' }] })
  if (promptText.includes('Classify what a person said')) return modelOutput({ intent: 'lesson', confidence: 0.9 })
  return modelOutput({})
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

describe('privacy: store:false on every model call', () => {
  it('every call from every service and path (fast, escalation, precise, fallback, hedge, replan, tiers, screenshot scam) is store:false', async () => {
    const { ai, calls } = fakeAi((p) => answerFor(textInput({ params: p })))
    await exerciseEveryService(testDeps(ai))
    expect(calls.length).toBeGreaterThanOrEqual(10)
    for (const c of calls) expect(c.params.store).toBe(false)
    expect(calls.filter(hasImage).length).toBeGreaterThanOrEqual(5)
  })

  it('also on the paths that only run when something goes wrong', async () => {
    const { ai, calls } = fakeAi((p) => {
      const t = textInput({ params: p })
      if (Array.isArray(p.tools) && t.includes('DRY RUN')) return { status: 'completed', steps: [{ type: 'function_call', name: 'click', arguments: { x: 10, y: 10 } }] }
      if (t.includes('Find this one element')) return modelOutput({ found: true, box_2d: [0, 0, 900, 900], label: '', reason: '', confidence: 0.9 }) // oversize: forces the computer_use fallback
      if (t.includes('checking whether a learner')) return modelOutput({ completed: true, confidence: 0.4, uncertain: true, evidence: '', learner_misstep: '', next_hint: '' }) // forces all three verifier tiers
      return answerFor(t)
    })
    const deps = testDeps(ai)
    const shot = testShot('failpaths')
    await createGrounder(deps).ground({ target: 'abc', shot })
    await createVerifier(deps).verify({ expected: 'x', shot })
    expect(calls.some((c) => Array.isArray(c.params.tools))).toBe(true)
    expect(new Set(calls.map((c) => c.params.model))).toEqual(new Set([MODELS.lite, MODELS.flash, MODELS.argon]))
    for (const c of calls) expect(c.params.store).toBe(false)
  })

  it('on the wire: the real SDK sends "store":false in the HTTP body, with the key only in a header', async () => {
    vi.stubEnv('GEMINI_API_KEY', FAKE_KEY)
    const requests: Array<{ url: string; headers: Headers; body: string }> = []
    vi.stubGlobal('fetch', async (input: unknown, init?: { headers?: HeadersInit; body?: unknown }) => {
      const req = input instanceof Request ? input : null
      const body = typeof init?.body === 'string' ? init.body : req ? await req.text() : ''
      requests.push({ url: req ? req.url : String(input), headers: new Headers(init?.headers ?? req?.headers), body })
      const parsed = JSON.parse(body) as { input: unknown }
      const reply = answerFor(JSON.stringify(parsed.input).replace(/\\n/g, '\n').replace(/\\"/g, '"'))
      return new Response(JSON.stringify({ id: 'i1', status: 'completed', steps: reply.steps }), { status: 200, headers: { 'content-type': 'application/json' } })
    })
    const logs: string[] = []
    const deps = createGeminiDeps({ log: (s, ...a) => logs.push(`${s} ${a.join(' ')}`), ai: createAi() })
    await exerciseEveryService(deps)
    expect(requests.length).toBeGreaterThanOrEqual(10)
    for (const r of requests) {
      expect(JSON.parse(r.body).store).toBe(false)
      expect(r.url).not.toContain(FAKE_KEY)
      expect(r.body).not.toContain(FAKE_KEY)
      expect(r.headers.get('x-goog-api-key')).toBe(FAKE_KEY)
    }
    expect(requests.some((r) => r.body.includes('"type":"image"'))).toBe(true)
    expect(logs.join('\n')).not.toContain(FAKE_KEY)
  })

  it('static: every interactions.create( call site in src/main passes store:false', () => {
    const root = path.resolve(__dirname, '..')
    const offenders: string[] = []
    const walk = (dir: string) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, e.name)
        if (e.isDirectory()) walk(full)
        else if (/\.ts$/.test(e.name) && !/\.test\.|test-util|\.live\./.test(e.name)) {
          const src = fs.readFileSync(full, 'utf8')
          const sites = src.match(/interactions\.create\(/g)?.length ?? 0
          const stores = src.match(/store:\s*false/g)?.length ?? 0
          if (sites > stores) offenders.push(`${path.relative(root, full)}: ${sites} call site(s), ${stores} store:false`)
        }
      }
    }
    walk(root)
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
    const { ai } = fakeAi((p) => answerFor(textInput({ params: p })))
    const deps = createGeminiDeps({ ai, log })
    const grounder = createGrounder(deps)
    await grounder.ground({ target: 'the Send button', shot })
    await createVerifier(deps).verify({ expected: 'sent', shot })
    await createLessonArchitect(deps, { grounder }).plan({ goal: 'send a message', learner, shot })
    await createScamAnalyst(deps).analyze({ text: MESSAGE })
    await createRouter(deps).classify('please help me send a message')
    // Failing run: the error text carries a key, the screenshot and the message
    const failing = fakeAi(() => {
      throw Object.assign(new Error(`400 bad request key=${FAKE_KEY} body=${shotB64} message=${MESSAGE}`), { status: 400 })
    })
    const fdeps = createGeminiDeps({ ai: failing.ai, log })
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
    expect(all).not.toMatch(/AIza[0-9A-Za-z_-]{16,}/)
    expect(all).not.toMatch(/[A-Za-z0-9+/]{120,}/)
  })

  it('the redacting layer itself: whatever any code hands deps.log is scrubbed (defence in depth for future log lines)', () => {
    const lines: string[] = []
    const deps = createGeminiDeps({ ai: fakeAi(() => modelOutput({})).ai, log: (s, ...a) => lines.push(`${s} ${a.join(' ')}`) })
    deps.log('x', `token ${FAKE_KEY}`, 'QUJD'.repeat(500), new Error(`boom ${FAKE_KEY}`), { nested: FAKE_KEY })
    expect(lines.join('\n')).not.toContain(FAKE_KEY)
    expect(lines.join('\n')).not.toMatch(/[A-Za-z0-9+/]{120,}/)
  })

  it('even a hand-built deps object with a raw logger is redacted by every factory', async () => {
    const lines: string[] = []
    const failing = fakeAi(() => {
      throw Object.assign(new Error(`oops ${FAKE_KEY}`), { status: 500 })
    })
    const deps = { ai: failing.ai, models: MODELS, log: (s: string, ...a: unknown[]) => lines.push(`${s} ${a.join(' ')}`) }
    await createGrounder(deps).ground({ target: 'x', shot: testShot('raw') })
    await createVerifier(deps).verify({ expected: 'x', shot: testShot('raw2') })
    expect(lines.join('\n')).not.toContain(FAKE_KEY)
  })
})

describe('failure honesty: plain English, never a fabricated box or verdict', () => {
  const PLAIN_BAD = /GeminiError|\b(401|403|429|500|503)\b|undefined|\[object|at .*\.ts|stack|ECONN|fetch failed|api key|status/i
  const scenarios: Array<{ name: string; make: () => ReturnType<typeof fakeAi>['ai']; expects: RegExp }> = [
    {
      name: 'no key (setup missing)',
      make: () => {
        vi.stubEnv('GEMINI_API_KEY', '')
        return createAi()
      },
      expects: /isn't set up/i,
    },
    { name: 'network down', make: () => fakeAi(() => { throw new TypeError('fetch failed') }).ai, expects: /can't reach the internet/i },
    { name: 'rate limited (429)', make: () => fakeAi(() => { throw apiError(429, 'Resource exhausted') }).ai, expects: /too many requests/i },
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
        expect(err).toBeInstanceOf(GeminiError)
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
    const stall = () => fakeAi(async () => { await sleep(5000); return modelOutput({}) }).ai
    it('grounder returns found:false reason "timeout" promptly', async () => {
      const t0 = Date.now()
      const r = await createGrounder(testDeps(stall()), { timeoutMs: 120 }).ground({ target: 'x', shot: testShot('stall-g') })
      expect(r).toMatchObject({ found: false, reason: 'timeout' })
      expect(r.box).toBeUndefined()
      expect(Date.now() - t0).toBeLessThan(600)
    })
    it('verifier never ticks on a stall', async () => {
      const v = await createVerifier(testDeps(stall()), { liteTimeoutMs: 500, flashTimeoutMs: 500, argonTimeoutMs: 500 }).verify({ expected: 'x', shot: testShot('stall-v') })
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
    const { ai } = fakeAi(() => modelOutput('I am a helpful assistant and everything is fine!'))
    const deps = testDeps(ai)
    expect((await createGrounder(deps).ground({ target: 'x', shot: testShot('junk-g') })).found).toBe(false)
    expect((await createVerifier(deps).verify({ expected: 'x', shot: testShot('junk-v') })).completed).toBe(false)
    expect((await createScamAnalyst(deps).analyze({ text: MESSAGE })).verdict).toBe('cannot_tell')
  })
})
