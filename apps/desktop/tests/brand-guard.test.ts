// The rename is enforceable: nothing a person can read in the desktop app or the dashboard may carry an old product name.
// Internal names stay (env vars, module and folder names, header names, log lines, file paths): see tests/brand-scan.ts for the allow-list.
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { APP_NAME, BUNDLE_ID, BRAND_FILES, titled } from '../src/shared/brand'
import { listVisibleSources, scanSource, scanTree, type Hit } from './brand-scan'
import { scanSource as scanWords } from '../../dashboard/src/lib/visibleWords'

const desktop = path.resolve(__dirname, '..')
const repo = path.resolve(desktop, '../..')
const fmt = (hits: Hit[]): string => hits.map((h) => `${h.file}:${h.line}  ${h.text}`).join('\n')

describe('the brand seam', () => {
  it('names the product Knack, from the one brand file', () => {
    expect(APP_NAME).toBe('Knack')
    expect(BUNDLE_ID).toBe('app.knack.desktop')
    expect(titled('Today')).toBe('Today · Knack')
    const json = JSON.parse(fs.readFileSync(path.join(repo, 'packages/design/brand/brand.json'), 'utf8')) as { name: string }
    expect(json.name).toBe(APP_NAME)
  })
  it('points at brand files that exist, with the brand name in their accessible label', () => {
    for (const file of Object.values(BRAND_FILES)) {
      const p = path.join(repo, 'packages/design/brand', file)
      expect(fs.existsSync(p), file).toBe(true)
      expect(fs.readFileSync(p, 'utf8')).toContain(`aria-label="${APP_NAME}"`)
    }
  })
})

describe('the scanner', () => {
  it('flags visible copy and ignores comments, identifiers, env vars, header names, paths and log lines', () => {
    const src = [
      '// Understudy in a comment is fine',
      '/* and Alongside in a block comment */',
      'const a = "Welcome to Understudy"',
      'const b = <p>Alongside you</p>',
      'const url = "http://example.test/x" // Understudy trailing comment',
      'createUnderstudyCore(); window.understudyHud; process.env.UNDERSTUDY_X',
      'const h = { "X-Understudy-Actor": "worker" }',
      'const p = "~/.understudy/memory.md"',
      "console.log('Understudy booted')",
      'ctx.log("tray", "Understudy ready")',
      'const note = `It\'s ${n} things Understudy knows`',
    ].join('\n')
    const hits = scanSource(src, 'x.tsx')
    expect(hits.map((h) => h.line)).toEqual([3, 4, 11])
  })
  it('keeps line numbers when it removes comments', () => {
    expect(scanSource('/* a\nb */\nconst s = "Understudy"', 'x.ts').map((h) => h.line)).toEqual([3])
  })
})

describe('no visible old name in the desktop app', () => {
  // The dashboard carries its own check (Track D's copy-lint.test.ts scans it); this one holds the desktop app.
  it('the desktop renderer, shared code and preloads say Knack', () => {
    const hits = ['src/renderer', 'src/shared', 'src/preload'].flatMap((d) => scanTree(path.join(desktop, d), repo))
    expect(fmt(hits)).toBe('')
  })
  it('the desktop main process says Knack wherever it shows text', () => {
    expect(fmt(scanTree(path.join(desktop, 'src/main'), repo))).toBe('')
  })
})

// 8 Nov 2026, 05:00 (owner): nothing a person reads or hears in the desktop app says that data is an example. The desktop states what is true ("Models are off",
// "Voice needs a Gemini key") and draws no tag. Same scanner as tests/copy-words.test.ts; this block names the phrases the owner listed so a change to that list is noticed here.
describe('no example-data vocabulary in the desktop app', () => {
  const PHRASES = ['example data', 'sample data', 'stand-in', 'for this build', 'not real workers'] as const
  const files = ['src/main', 'src/shared', 'src/preload', 'src/renderer']
    .flatMap((d) => listVisibleSources(path.join(desktop, d)))
    .filter((f) => /\.(ts|tsx)$/.test(f) && !/[\\/]overlay[\\/]demo\./.test(f))

  it('the scanner sees each phrase in a sentence', () => {
    for (const p of PHRASES) expect(scanWords(`const t = 'This says ${p} once'`, p).length, p).toBe(1)
  })

  it('says none of them in text a person reads', () => {
    const bad: string[] = []
    for (const f of files) {
      const src = fs.readFileSync(f, 'utf8')
      for (const p of PHRASES) for (const h of scanWords(src, p)) bad.push(`${path.relative(repo, f)}:${h.line}  [${p}] ${h.text.slice(0, 80)}`)
    }
    expect(bad).toEqual([])
  })
})
