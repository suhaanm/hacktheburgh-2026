// Manual live probe of the model port (spike S1 helper). NOT part of `npm test`. It makes four TINY calls with the real key:
//   1 boot check (GET /v1/models: which models can this key use, are OPENAI_MODEL_* valid)
//   2 one structured chat call on the fast tier
//   3 one vision call (a 1x1 image) on the fast tier
//   4 one computer-tool request with a 1x1 screenshot (shape check only: nothing is executed; a safety check would come back as `blocked`)
// Run:  npm run probe:models      (loads ../../.env into the process with process.loadEnvFile; the key is never printed)
// Each step prints a one-line verdict. API errors are reported, not thrown: the point is to see what this key can do.
import fs from 'node:fs'
import path from 'node:path'
import { describe, it } from 'vitest'
import { createModelPortFromEnv, ModelPortError, type ModelPort } from '../../src/main/model-port'

const ENV_FILE = path.resolve(process.cwd(), '../../.env')
if (fs.existsSync(ENV_FILE)) {
  try {
    process.loadEnvFile(ENV_FILE) // does not override variables that are already set
  } catch {
    /* an unreadable file just means the shell must provide the variables */
  }
}
// A valid 1x1 PNG.
const PNG_1X1 = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='

const say = (...a: unknown[]) => console.log('[probe]', ...a)
const why = (e: unknown): string => (e instanceof ModelPortError ? `${e.code}${e.status ? ` ${e.status}` : ''}: ${e.message}` : String((e as Error)?.message ?? e))

describe('model port live probe', () => {
  const port: ModelPort = createModelPortFromEnv({ env: { ...process.env, UNDERSTUDY_MOCK: '', ALONGSIDE_MOCK: '' } })

  it('1 boot check', async () => {
    const r = await port.bootCheck()
    say(`boot ok=${r.ok} provider=${r.provider} planner=${r.configured.planner || '(unset)'} fast=${r.configured.fast || '(unset)'} computer_use=${r.configured.computer_use || '(unset)'} listed=${r.listed}`)
    if (!r.ok) say('PROBLEM:', r.problem)
    else say('usable (first 25):', r.usable.slice(0, 25).join(', '))
  }, 30_000)

  it('2 structured chat on the fast tier', async () => {
    try {
      const r = await port.complete({
        name: 'probe.chat',
        tier: 'fast',
        text: 'Reply with the JSON {"ok": true} and nothing else.',
        schema: { name: 'probe', schema: { type: 'object', properties: { ok: { type: 'boolean' } }, required: ['ok'] } },
        effort: 'low',
        timeoutMs: 40_000,
        retries: 0,
      })
      say(`chat OK model=${r.model} ${r.ms}ms usage=${JSON.stringify(r.usage)} text=${r.text.slice(0, 60)}`)
    } catch (e) {
      say('chat FAILED:', why(e))
    }
  }, 60_000)

  it('3 vision on the fast tier', async () => {
    try {
      const r = await port.complete({
        name: 'probe.vision',
        tier: 'fast',
        text: 'This is a tiny test image. Reply with JSON {"seen": true}.',
        images: [{ jpegBase64: PNG_1X1, mime: 'image/png', detail: 'low' }],
        schema: { name: 'probe_vision', schema: { type: 'object', properties: { seen: { type: 'boolean' } }, required: ['seen'] } },
        effort: 'low',
        timeoutMs: 40_000,
        retries: 0,
      })
      say(`vision OK model=${r.model} ${r.ms}ms text=${r.text.slice(0, 60)}`)
    } catch (e) {
      say('vision FAILED:', why(e))
    }
  }, 60_000)

  it('4 computer tool request shape (nothing is executed)', async () => {
    try {
      const r = await port.computerStep({ goal: 'Say that you are finished. Do not act.', history: [], screenshot: { jpegBase64: PNG_1X1, mime: 'image/png', widthPx: 1, heightPx: 1 }, timeoutMs: 45_000 })
      say(`computer step OK kind=${r.kind} model=${r.model} ${r.ms}ms${r.kind === 'actions' ? ` actions=${JSON.stringify(r.actions)}` : r.kind === 'done' ? ` text=${r.text.slice(0, 80)}` : ` reason=${r.reason}`}`)
    } catch (e) {
      say('computer step FAILED:', why(e))
    }
  }, 70_000)

  it('5 computer tool on a saved practice-desktop screenshot (a real proposal; nothing is executed)', async () => {
    const dir = path.resolve(process.cwd(), 'spikes/grounding/shots/stage')
    const file = fs.existsSync(dir) ? fs.readdirSync(dir).find((f) => /settings_display.*\.jpg$/.test(f)) : undefined
    if (!file) return say('no saved practice-desktop screenshot here; skipped')
    try {
      const r = await port.computerStep({ goal: 'Open the text size options', history: [], screenshot: { jpegBase64: fs.readFileSync(path.join(dir, file)).toString('base64'), widthPx: 1440, heightPx: 900 }, timeoutMs: 60_000 })
      say(`computer proposal kind=${r.kind} model=${r.model} ${r.ms}ms ${r.kind === 'actions' ? `actions=${JSON.stringify(r.actions)} callId=${r.callId ? 'present' : 'missing'}` : r.kind === 'done' ? `text=${r.text.slice(0, 100)}` : `reason=${r.reason}`}`)
    } catch (e) {
      say('computer proposal FAILED:', why(e))
    }
  }, 90_000)
})
