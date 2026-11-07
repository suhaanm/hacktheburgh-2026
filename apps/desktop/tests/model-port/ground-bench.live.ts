// Manual, small live benchmark of the REAL grounder on the practice-desktop screenshots that have ground truth
// (spikes/grounding/shots/manifest-stage.json). Costs real calls: GROUND_BENCH_N (default 12) targets, evenly sampled.
// Run: GROUND_BENCH_N=12 npx vitest run --config tests/model-port/vitest.probe.config.ts -t grounding --reporter=verbose --silent=false
// Reports hit rate (the centre of the answer lies inside the true box), mean IoU, latency and false finds on absent targets.
import fs from 'node:fs'
import path from 'node:path'
import { describe, it } from 'vitest'
import { createModelPortFromEnv } from '../../src/main/model-port'
import { createGrounder, type GroundPreset } from '../../src/main/model-services/grounder'
import { iou, pointInBox } from '../../src/main/model-services/grounding-utils'
import type { NormBox, Shot } from '../../src/shared/protocol'

const ENV_FILE = path.resolve(process.cwd(), '../../.env')
if (fs.existsSync(ENV_FILE)) {
  try {
    process.loadEnvFile(ENV_FILE)
  } catch {
    /* the shell must provide the variables */
  }
}
const root = process.cwd()
interface StageTarget { desc: string; negative: boolean; kind: string; gt: NormBox | null }
interface StageShot { shotId: string; jpg: string; w: number; h: number; targets: StageTarget[] }

describe('live: grounding on saved practice-desktop screenshots', () => {
  for (const preset of (process.env.GROUND_BENCH_PRESETS ?? 'fast').split(',') as GroundPreset[]) {
    it(`grounding preset=${preset}`, async () => {
      const manifest = JSON.parse(fs.readFileSync(path.join(root, 'spikes/grounding/shots/manifest-stage.json'), 'utf8')) as StageShot[]
      const all = manifest.flatMap((s) => s.targets.map((t) => ({ s, t })))
      const n = Math.min(all.length, Number(process.env.GROUND_BENCH_N ?? 12))
      const picked = Array.from({ length: n }, (_, i) => all[Math.floor((i * all.length) / n)])
      const port = createModelPortFromEnv({ env: { ...process.env, UNDERSTUDY_MOCK: '', ALONGSIDE_MOCK: '' } })
      const grounder = createGrounder({ port, log: () => undefined }, { preset, timeoutMs: 30_000, coords: (process.env.GROUND_BENCH_COORDS as 'norm1000' | 'pixels') || undefined })
      const rows: Array<{ hit: boolean; iou: number; ms: number; negative: boolean; found: boolean }> = []
      let i = 0
      const worker = async () => {
        while (i < picked.length) {
          const { s, t } = picked[i++]
          const shot: Shot = { id: s.shotId, displayId: 1, widthPx: s.w, heightPx: s.h, scaleFactor: 1, jpegBase64: fs.readFileSync(path.resolve(root, s.jpg)).toString('base64'), takenAt: Date.now(), overlayHidden: true }
          const r = await grounder.ground({ target: t.desc, shot })
          const hit = !!(r.found && r.point && t.gt && pointInBox(r.point, t.gt))
          rows.push({ hit, iou: r.found && r.box && t.gt ? iou(r.box, t.gt) : 0, ms: r.latencyMs, negative: t.negative, found: r.found })
        }
      }
      await Promise.all(Array.from({ length: 3 }, worker))
      const pos = rows.filter((r) => !r.negative)
      const neg = rows.filter((r) => r.negative)
      const ms = rows.map((r) => r.ms).sort((a, b) => a - b)
      console.log(
        '[ground-bench]',
        JSON.stringify({
          preset,
          coords: process.env.GROUND_BENCH_COORDS || 'pixels (default)',
          present: pos.length,
          hits: pos.filter((r) => r.hit).length,
          hitRate: pos.length ? +(pos.filter((r) => r.hit).length / pos.length).toFixed(2) : null,
          meanIoU: pos.length ? +(pos.reduce((a, r) => a + r.iou, 0) / pos.length).toFixed(2) : null,
          absent: neg.length,
          falseFinds: neg.filter((r) => r.found).length,
          p50ms: ms[Math.floor(ms.length / 2)],
          p95ms: ms[Math.min(ms.length - 1, Math.floor(ms.length * 0.95))],
        }),
      )
    }, 600_000)
  }
})
