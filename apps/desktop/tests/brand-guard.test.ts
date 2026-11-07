// The rename is enforceable: nothing a person can read in the desktop app or the dashboard may carry an old product name.
// Internal names stay (env vars, module and folder names, header names, log lines, file paths): see tests/brand-scan.ts for the allow-list.
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { APP_NAME, BUNDLE_ID, BRAND_FILES, titled } from '../src/shared/brand'
import { scanSource, scanTree, type Hit } from './brand-scan'

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
