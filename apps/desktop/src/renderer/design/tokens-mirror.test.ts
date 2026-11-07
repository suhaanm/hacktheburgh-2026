// The desktop's tokens.css mirrors packages/design/tokens.css for every colour the two share. If the design system moves on, this fails
// until tokens.css here is updated (it is the one file the desktop's windows take their values from).
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parseTokenRules } from './contrast'

const read = (p: string): string => readFileSync(p, 'utf8')
const mine = read(join(__dirname, 'tokens.css'))
const theirs = read(join(__dirname, '../../../../../packages/design/tokens.css'))

const pick = (css: string, dark: boolean): Record<string, string> => {
  const out: Record<string, string> = {}
  for (const r of parseTokenRules(css)) {
    const isDark = /data-theme=['"]dark['"]/.test(r.selector)
    const plain = r.selector === ':root'
    if ((dark && isDark && !/high-contrast|data-glass/.test(r.selector)) || (!dark && plain)) Object.assign(out, r.decls)
  }
  return out
}

// [token here, token in the design system]
const SHARED: [string, string][] = [
  ['--bg', '--bg'],
  ['--surface', '--panel'],
  ['--surface-sunken', '--sunk'],
  ['--ink', '--fg'],
  ['--ink-muted', '--muted'],
  ['--line', '--line'],
  ['--line-strong', '--control-line'],
  ['--accent-default', '--accent'],
  ['--accent-default-soft', '--accent-soft'],
  ['--on-accent-default', '--on-accent'],
  ['--success-ink', '--good'],
  ['--success-soft', '--good-soft'],
  ['--warn-ink', '--warn'],
  ['--warn-soft', '--warn-soft'],
  ['--danger-ink', '--bad'],
  ['--danger-soft', '--bad-soft'],
  ['--on-danger', '--on-bad'],
]

describe('tokens.css mirrors packages/design/tokens.css', () => {
  for (const dark of [false, true]) {
    it(`${dark ? 'dark' : 'light'}: every shared colour has the design system's value`, () => {
      const a = pick(mine, dark)
      const b = pick(theirs, dark)
      const drift = SHARED.filter(([x, y]) => a[x]?.toLowerCase() !== b[y]?.toLowerCase()).map(([x, y]) => `${x} ${a[x]} vs ${y} ${b[y]}`)
      expect(drift).toEqual([])
    })
  }

  it('the faces are the design system\'s, with system fallbacks, and the scale is small and calm', () => {
    const a = pick(mine, false)
    expect(a['--font-ui']).toMatch(/Source Sans 3/)
    expect(a['--font-display']).toMatch(/Bricolage Grotesque/)
    expect(a['--font-mono']).toMatch(/JetBrains Mono/)
    expect(a['--font-ui']).toMatch(/system-ui/)
    expect(a['--border-w']).toBe('1px')
    expect(a['--fs-base']).toMatch(/14px/)
  })

  it('has no gradient and no glow in the tokens', () => {
    expect(mine.replace(/\/\*[\s\S]*?\*\//g, '')).not.toMatch(/gradient|glow/i)
  })
})
