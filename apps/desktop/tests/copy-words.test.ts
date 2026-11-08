// Owner decision D57 (8 Nov 2026): the words "synthetic", "synthetically" and "simulated" are not in anything a person can see or hear in the desktop app
// (tray, corner pill, cards, wake texts, error page, panel, dock, overlay). Say where numbers come from concretely ("generated people", "language-model
// participants", "a stand-in actuator") and draw no tag. The dashboard's guard (apps/dashboard/src/lib/words.test.ts) scans the renderer too; this one holds
// the main process, shared code and preloads as well, with the same scanner (comments and identifiers are not text; a literal that is exactly the bare word is
// a data enum such as origin: 'synthetic' and is skipped). The list of files not clean yet is empty; add a file with its owner's name here only as a ratchet, and
// it must be gone by 05:00 on 8 Nov.
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { scanSource } from '../../dashboard/src/lib/visibleWords'
import { listVisibleSources } from './brand-scan'

const desktop = path.resolve(__dirname, '..')
const repo = path.resolve(desktop, '../..')
// 8 Nov 05:00 (owner): no example-data vocabulary either. The desktop says what is true in plain words ("Models are off"), never that data is an example.
const WORDS = [
  'synthetic', 'synthetically', 'simulated', 'made-up', 'made up',
  'example data', 'example week', 'example calendar', 'sample data', 'stand-in', 'stand-ins', 'stands in', 'for this build', 'not real workers', 'not real people',
] as const
const PENDING: Record<string, string> = {}

const files = ['src/main', 'src/shared', 'src/preload', 'src/renderer']
  .flatMap((d) => listVisibleSources(path.join(desktop, d)))
  .filter((f) => /\.(ts|tsx)$/.test(f) && !/[\\/]overlay[\\/]demo\./.test(f))

describe('no visible "synthetic", "simulated" or example-data wording in the desktop app', () => {
  it('is scanning real files', () => {
    expect(files.length).toBeGreaterThan(100)
  })

  it('the scanner finds a tag and a sentence, and leaves the data enum and identifiers alone', () => {
    expect(scanSource('<span aria-label="Simulated experts">Simulated</span>', 'simulated').length).toBeGreaterThan(0)
    expect(scanSource("const t = 'a synthetic firm'", 'synthetic').length).toBe(1)
    expect(scanSource("type O = 'real' | 'synthetic'; const o = 'synthetic'; const synthetic = true", 'synthetic')).toEqual([])
    expect(scanSource("const t = 'Running with example data'", 'example data').length).toBe(1)
    expect(scanSource("const t = 'a stand-in token'", 'stand-in').length).toBe(1)
  })

  it('says it nowhere a person reads or hears', () => {
    const bad: string[] = []
    for (const f of files) {
      const rel = path.relative(repo, f)
      if (rel in PENDING) continue
      const src = fs.readFileSync(f, 'utf8')
      for (const w of WORDS) for (const h of scanSource(src, w)) bad.push(`${rel}:${h.line}  [${w}] ${h.text.slice(0, 90)}`)
    }
    expect(bad).toEqual([])
  })

  it('the pending list is empty or still needed', () => {
    for (const rel of Object.keys(PENDING)) {
      const src = fs.readFileSync(path.join(repo, rel), 'utf8')
      expect(WORDS.some((w) => scanSource(src, w).length > 0), `${rel} is clean: delete it from PENDING`).toBe(true)
    }
  })
})
