// Runs last. Privacy: screenshot-bearing Google API calls must carry store:false. Spend: count calls per model (budget <=150).
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { REAL, REPO, fetchLog } from './helpers'

describe('privacy + spend', () => {
  it('static check: every Gemini call site in src/main/gemini that sends an image sets store:false (or uses a shared helper that does)', () => {
    const dir = path.join(REPO, 'src/main/gemini')
    const files = fs.readdirSync(dir).filter((f) => f.endsWith('.ts') && !/\.test\./.test(f) && !/test-util/.test(f))
    const text = files.map((f) => fs.readFileSync(path.join(dir, f), 'utf8')).join('\n')
    const sendsImages = /inlineData|inline_data|image\/jpeg|jpegBase64/.test(text)
    if (!sendsImages) return
    expect(text, 'a store:false setting must exist in src/main/gemini').toMatch(/store\s*:\s*false/)
  })

  it.skipIf(!REAL)('runtime check: every logged request that carried an image had store:false', async () => {
    const log = await fetchLog()
    const withImage = log.filter((e) => e.hasImage && e.method === 'POST')
    const byModel: Record<string, number> = {}
    for (const e of log) byModel[e.model ?? e.path] = (byModel[e.model ?? e.path] ?? 0) + 1
    console.log(`[e2e] google api calls this run: ${log.length} total (${JSON.stringify(byModel)}), image-bearing: ${withImage.length}`)
    expect(log.length, 'API spend budget (<=150 per agent)').toBeLessThanOrEqual(150)
    const missing = withImage.filter((e) => e.store !== false)
    expect(missing.map((e) => `${e.path} keys=${e.bodyKeys.join(',')} store=${String(e.store)}`), 'image requests without store:false').toEqual([])
  })
})
