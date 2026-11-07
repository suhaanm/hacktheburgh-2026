// Live benchmark of the REAL grounder (fast vs accurate preset) on STAGE captures with auto ground truth.
// Gated: RUN_LIVE=1 STAGE_BENCH=1 npx vitest run src/main/gemini/stage-bench.live.test.ts
// Inputs come from spikes/grounding/capture-stage.mjs (shots/manifest-stage.json). Results: spikes/grounding/results/stage_<preset>.jsonl
import fs from 'node:fs'
import path from 'node:path'
import { describe, it } from 'vitest'
import type { Shot } from '../../shared/protocol'
import { createGeminiDeps } from './client'
import { createGrounder, type GroundPreset } from './grounder'

const RUN = process.env.RUN_LIVE === '1' && process.env.STAGE_BENCH === '1'
const root = path.resolve(__dirname, '../../..')
const manifestPath = path.join(root, 'spikes/grounding/shots/manifest-stage.json')

interface StageTarget {
  desc: string
  negative: boolean
  kind: 'ui' | 'phrase' | 'negative'
  gt: { xmin: number; ymin: number; xmax: number; ymax: number } | null
}
interface StageShot {
  shotId: string
  jpg: string
  w: number
  h: number
  targets: StageTarget[]
}

describe.skipIf(!RUN)('live: STAGE grounding benchmark', () => {
  for (const preset of (process.env.STAGE_PRESETS ?? 'fast,accurate').split(',') as GroundPreset[]) {
    it(
      `preset=${preset}`,
      async () => {
        const manifest: StageShot[] = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
        const deps = createGeminiDeps({ log: () => undefined })
        // 20 s cap here: we want the intrinsic latency/accuracy; "would it have timed out at 6 s" is derived from latencyMs.
        const grounder = createGrounder(deps, { preset, timeoutMs: 20_000 })
        const out = path.join(root, 'spikes/grounding/results', `stage_${preset}.jsonl`)
        fs.mkdirSync(path.dirname(out), { recursive: true })
        const done = new Set(fs.existsSync(out) ? fs.readFileSync(out, 'utf8').split('\n').filter(Boolean).map((l) => { const j = JSON.parse(l); return `${j.shotId}|${j.desc}` }) : [])

        const jobs: Array<{ s: StageShot; t: StageTarget }> = []
        for (const s of manifest) for (const t of s.targets) if (!done.has(`${s.shotId}|${t.desc}`)) jobs.push({ s, t })
        let i = 0
        const worker = async () => {
          while (i < jobs.length) {
            const { s, t } = jobs[i++]
            const shot: Shot = {
              id: s.shotId, displayId: 1, widthPx: s.w, heightPx: s.h, scaleFactor: 1,
              jpegBase64: fs.readFileSync(s.jpg).toString('base64'), takenAt: Date.now(), overlayHidden: true,
            }
            const r = await grounder.ground({ target: t.desc, shot })
            fs.appendFileSync(out, JSON.stringify({ preset, shotId: s.shotId, w: s.w, desc: t.desc, kind: t.kind, negative: t.negative, gt: t.gt, found: r.found, box: r.box, point: r.point, model: r.model, confidence: r.confidence, label: r.label, reason: r.reason, latencyMs: r.latencyMs }) + '\n')
          }
        }
        await Promise.all(Array.from({ length: 5 }, worker))
      },
      1_800_000,
    )
  }
})
