// Live: runs ScamAnalyst over fixtures/scam (10 scam + 10 genuine UK-flavoured messages) and prints a confusion matrix.
// RUN_LIVE=1 SCAM_FIXTURES=1 SCAM_TAG=before npx vitest run src/main/gemini/scam-fixtures.live.test.ts
import fs from 'node:fs'
import path from 'node:path'
import { describe, it } from 'vitest'
import type { ScamReport } from '../../shared/protocol'
import { createGeminiDeps } from './client'
import { createScamAnalyst } from './scam-analyst'

const RUN = process.env.RUN_LIVE === '1' && process.env.SCAM_FIXTURES === '1'
const root = path.resolve(__dirname, '../../..')
const dir = path.join(root, 'fixtures/scam')
const tag = process.env.SCAM_TAG ?? 'run'

const load = (kind: 'scam' | 'genuine') =>
  fs
    .readdirSync(path.join(dir, kind))
    .filter((f) => f.endsWith('.txt'))
    .sort()
    .map((f) => ({ id: `${kind}/${f.replace('.txt', '')}`, truth: kind, text: fs.readFileSync(path.join(dir, kind, f), 'utf8').trim() }))

const pctl = (a: number[], p: number) => {
  const s = [...a].sort((x, y) => x - y)
  return s.length ? s[Math.min(s.length - 1, Math.floor(p * s.length))] : NaN
}

describe.skipIf(!RUN)('live: scam fixtures', () => {
  it(
    `confusion matrix (${tag})`,
    async () => {
      const callLog = path.join(dir, `calls-${tag}.log`)
      fs.writeFileSync(callLog, '')
      const analyst = createScamAnalyst(createGeminiDeps({ log: (scope, ...a) => fs.appendFileSync(callLog, `${new Date().toISOString().slice(11, 23)} [${scope}] ${a.join(' ')}\n`) }))
      const only = process.env.SCAM_ONLY?.split(',')
      const items = [...load('scam'), ...load('genuine')].filter((x) => !only || only.some((o) => x.id.includes(o)))
      const results: Array<{ id: string; truth: string; report: ScamReport; verbatimOk: boolean; saidSafe: boolean; humanOk: boolean; progress: string[] }> = []
      let i = 0
      const worker = async () => {
        while (i < items.length) {
          const it = items[i++]
          const progress: string[] = []
          // The second argument exists after the pipeline upgrade; before it, extra args are ignored.
          const report = await (analyst.analyze as (req: { text: string }, opts?: { onProgress?: (m: string) => void }) => Promise<ScamReport>)({ text: it.text }, { onProgress: (m) => progress.push(m) })
          results.push({
            id: it.id,
            truth: it.truth,
            report,
            verbatimOk: report.redFlags.every((f) => it.text.includes(f.phrase)),
            saidSafe: report.advice.some((a) => /\bsafe\b/i.test(a) && !/\b(not|never|n't)\b/i.test(a)),
            humanOk: /back of your bank card/i.test(report.humanHelp),
            progress,
          })
        }
      }
      await Promise.all(Array.from({ length: Number(process.env.SCAM_CONC ?? 4) }, worker))
      results.sort((a, b) => a.id.localeCompare(b.id))

      const scamPred = (v: string) => v === 'likely_scam' || v === 'suspicious'
      const sc = results.filter((r) => r.truth === 'scam')
      const ge = results.filter((r) => r.truth === 'genuine')
      const tp = sc.filter((r) => scamPred(r.report.verdict)).length
      const fn = sc.filter((r) => r.report.verdict === 'likely_genuine').length
      const scAbstain = sc.filter((r) => r.report.verdict === 'cannot_tell').length
      const tn = ge.filter((r) => r.report.verdict === 'likely_genuine').length
      const fp = ge.filter((r) => scamPred(r.report.verdict)).length
      const geAbstain = ge.filter((r) => r.report.verdict === 'cannot_tell').length
      const lat = results.map((r) => r.report.latencyMs)
      const lines = [
        `\n=== scam confusion matrix [${tag}] ===`,
        `                  pred scam(+suspicious)  pred genuine  cannot_tell`,
        `truth scam (10)   ${String(tp).padStart(10)}              ${String(fn).padStart(6)}        ${String(scAbstain).padStart(6)}`,
        `truth genuine(10) ${String(fp).padStart(10)}              ${String(tn).padStart(6)}        ${String(geAbstain).padStart(6)}`,
        `latency p50=${pctl(lat, 0.5)}ms p95=${pctl(lat, 0.95)}ms max=${Math.max(...lat)}ms`,
        `verbatim phrases ok: ${results.filter((r) => r.verbatimOk).length}/${results.length}; said safe: ${results.filter((r) => r.saidSafe).length}; humanHelp ok: ${results.filter((r) => r.humanOk).length}/${results.length}`,
        ...results.map((r) => `${r.id.padEnd(30)} ${r.report.verdict.padEnd(15)} conf=${r.report.confidence.toFixed(2)} flags=${r.report.redFlags.length} ${String(r.report.latencyMs).padStart(6)}ms models=${r.report.models.length}`),
      ]
      console.log(lines.join('\n'))
      fs.writeFileSync(path.join(dir, `results-${tag}.json`), JSON.stringify({ tag, tp, fn, scAbstain, fp, tn, geAbstain, p50: pctl(lat, 0.5), p95: pctl(lat, 0.95), results }, null, 1))
    },
    1_200_000,
  )
})
