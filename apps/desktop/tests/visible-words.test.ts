// Nothing the worker reads in the desktop shell may say "demo" or "mock" (owner request of 8 Nov 2026): the pill, the cards, the tray, the Dock menu, the quit sheet, the Starting and error
// pages, the permission prompt and the voice status lines say "models are off" or "live models" instead. Only prose counts: a string literal with a space in it. Identifiers (the mode id
// 'demo', file names, env var names, a `make demo` command in a comment) are not read by anyone and stay.
import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { stripComments } from './brand-scan'

const src = path.resolve(__dirname, '../src')
// The whole word, not part of a hyphenated or dotted name (understudy-demo-data, mock.ts).
const WORD = /(?<![\w.-])(demo|mock)(?![\w-])/i
const LITERAL = /'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`/g

/** The string literals of a source text that read as prose and say demo or mock. */
export function proseHits(text: string): string[] {
  return (stripComments(text).match(LITERAL) ?? []).filter((lit) => /\s/.test(lit.slice(1, -1)) && /[A-Za-z]/.test(lit) && WORD.test(lit) && !/\b(ALONGSIDE|UNDERSTUDY)_/.test(lit) && !/make demo/.test(lit))
}

const walk = (dir: string): string[] =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) return walk(p)
    return /\.(ts|tsx|html)$/.test(e.name) && !/\.test\.|test-util|\.d\.ts$/.test(e.name) ? [p] : []
  })

const SURFACES = [
  ...walk(path.join(src, 'main/knack')).filter((f) => !f.endsWith('check-main.ts')),
  ...walk(path.join(src, 'renderer/hud')),
  ...walk(path.join(src, 'renderer/toast')),
  ...walk(path.join(src, 'renderer/hey-card')),
  ...['main/tray.ts', 'main/hud.ts', 'main/hud-model.ts', 'main/toast.ts', 'main/windows.ts', 'main/permissions.ts', 'main/wake/texts.ts', 'main/wake/guards.ts', 'shared/hud.ts', 'shared/knack.ts'].map((f) => path.join(src, f)),
].filter((f) => fs.existsSync(f))

describe('the scanner', () => {
  it('flags prose that says demo or mock and leaves identifiers alone', () => {
    const text = ["const a = 'Hey Knack is off in demo mode'", "const mode = 'demo'", "const b = `Mock check: nothing`", "// a demo in a comment", "const e = 'UNDERSTUDY_MOCK is on'", 'const f = "file .understudy-demo-data"'].join('\n')
    expect(proseHits(text)).toEqual(["'Hey Knack is off in demo mode'", '`Mock check: nothing`'])
  })
})

describe('no demo or mock wording in what the worker reads', () => {
  it('covers the shell surfaces', () => {
    expect(SURFACES.length).toBeGreaterThan(20)
  })
  it.each(SURFACES.map((f) => [path.relative(src, f), f] as const))('%s', (_name, file) => {
    expect(proseHits(fs.readFileSync(file, 'utf8'))).toEqual([])
  })
})
