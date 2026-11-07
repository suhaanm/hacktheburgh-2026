// Live: LessonArchitect latency + step-1 groundability on novel goals against STAGE's call screen.
// RUN_LIVE=1 ARCH_BENCH=1 [ARCH_THINKING=low|medium] npx vitest run src/main/gemini/architect-bench.live.test.ts
import fs from 'node:fs'
import path from 'node:path'
import { describe, it } from 'vitest'
import type { LearnerSnapshot, Shot } from '../../shared/protocol'
import { createGeminiDeps, latencySummary, resetLatency } from './client'
import { createGrounder } from './grounder'
import { createLessonArchitect } from './lesson-architect'

const RUN = process.env.RUN_LIVE === '1' && process.env.ARCH_BENCH === '1'
const root = path.resolve(__dirname, '../../..')
const thinking = (process.env.ARCH_THINKING ?? 'low') as 'low' | 'medium'

const learner: LearnerSnapshot = {
  skills: {
    video_call: { level: 2, streakClean: 1, lastSeen: null, nextReview: null },
    spot_scam: { level: 1, streakClean: 0, lastSeen: null, nextReview: null },
    bigger_text: { level: 2, streakClean: 0, lastSeen: null, nextReview: null },
  },
  confidenceLog: [],
  attempts: [],
  whatWorks: ['short sentences'],
  avoidJargon: ['cursor'],
}
const pct = (a: number[], p: number) => {
  const s = [...a].sort((x, y) => x - y)
  return s[Math.min(s.length - 1, Math.floor(p * s.length))]
}

describe.skipIf(!RUN)('live: architect latency', () => {
  it(
    `novel goals on the call screen (thinking=${thinking})`,
    async () => {
      const lines: string[] = []
      const deps = createGeminiDeps({ log: (scope, ...a) => lines.push(`${scope}: ${a.join(' ')}`) })
      const shot: Shot = {
        id: 'call', displayId: 1, widthPx: 1440, heightPx: 900, scaleFactor: 1, takenAt: Date.now(), overlayHidden: true,
        jpegBase64: fs.readFileSync(path.join(root, 'spikes/grounding/shots/stage/stage-video_call-screen@1440x900.jpg')).toString('base64'),
      }
      const grounder = createGrounder(deps)
      const architect = createLessonArchitect(deps, { thinking, grounder })
      const goals = ['mute my microphone', 'turn my camera off', 'make the text bigger in settings', 'open the privacy settings', 'share my screen']
      resetLatency()
      const rows: Array<Record<string, unknown>> = []
      for (let round = 0; round < 2; round++) {
        for (const goal of goals) {
          const t0 = Date.now()
          lines.length = 0
          let row: Record<string, unknown>
          try {
            const plan = await architect.plan({ goal, learner, shot })
            const ms = Date.now() - t0
            const g = await grounder.ground({ target: plan.steps[0].targetDescription, shot })
            row = { round, goal, ok: true, ms, replanned: lines.some((l) => l.includes('re-planning')), skillId: plan.skillId, steps: plan.steps.length, step1: plan.steps[0].targetDescription, step1Found: g.found, instr: plan.steps.map((s) => s.instruction) }
          } catch (e) {
            row = { round, goal, ok: false, ms: Date.now() - t0, error: e instanceof Error ? e.message : String(e) }
          }
          rows.push(row)
        }
      }
      const ms = rows.map((r) => r.ms as number)
      const summary = { thinking, n: rows.length, p50: pct(ms, 0.5), p95: pct(ms, 0.95), max: Math.max(...ms), ok: rows.filter((r) => r.ok).length, step1Found: rows.filter((r) => r.step1Found).length, replanned: rows.filter((r) => r.replanned).length, perCall: latencySummary(), rows }
      fs.writeFileSync(path.join(root, 'spikes/grounding/results', `architect_${thinking}.json`), JSON.stringify(summary, null, 1))
    },
    600_000,
  )
})
