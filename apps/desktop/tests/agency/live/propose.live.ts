// Manual live check (NOT part of npm test): a few real computer_use calls on saved stage screenshots, no actuation.
// Run with a vitest config whose include is tests/agency/live/*.live.ts (needs GEMINI_API_KEY in .env).
import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, it } from 'vitest'
import { proposeNext } from '../../../src/main/agency/computer-use'
import { createGeminiDeps } from '../../../src/main/gemini/client'
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
const deps = createGeminiDeps({ log: (...a) => console.log('[gemini]', ...a.map(String)) })
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
