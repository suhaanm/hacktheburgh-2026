// Manual live check (NOT part of npm test): a few real computer-tool calls on saved stage screenshots, no actuation.
// Run with a vitest config whose include is tests/agency/live/*.live.ts (needs OPENAI_API_KEY and OPENAI_MODEL_COMPUTER_USE exported in the shell;
// the actuator is never involved, but a live call costs money: run it only on purpose).
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, it } from 'vitest'
import { proposeNext } from '../../../src/main/agency/computer-use'
import { createModelPortFromEnv } from '../../../src/main/model-port'
import type { Shot } from '../../../src/shared/protocol'

const dir = path.join(process.cwd(), 'spikes/grounding/shots/stage')
const shotOf = (name: string): Shot => ({
  id: name,
  displayId: 1,
  widthPx: 1440,
  heightPx: 900,
  scaleFactor: 1,
  takenAt: Date.now(),
  overlayHidden: true,
  jpegBase64: readFileSync(path.join(dir, name)).toString('base64'),
})
const deps = { port: createModelPortFromEnv({ log: (...a) => console.log('[model-port]', ...a.map(String)) }) }
const cases: Array<[string, string, string[]]> = [
  ['stage-settings_display@1440x900.jpg', 'Make the text on this computer bigger', []],
  ['stage-settings_display@1440x900.jpg', 'Open the text size options', ['clicked the Display entry in the sidebar -> the screen changed']],
  ['stage-messages_scam@1440x900.jpg', 'Reply to the message from the sender', []],
]

describe('live computer_use proposals', () => {
  for (const [file, goal, history] of cases) {
    it(`${file}: ${goal}`, async () => {
      const t0 = Date.now()
      const out = await proposeNext(deps, { goal, history, shot: shotOf(file), timeoutMs: 40_000 })
      console.log('RESULT', JSON.stringify({ goal, ms: Date.now() - t0, out }))
    }, 60_000)
  }
})
