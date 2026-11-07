import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { contrastRatio } from '../../design/contrast'

const css = readFileSync(join(__dirname, 'cue.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')

// The custom properties of the block that starts with this exact selector (the rules are small and flat).
function tokens(selector: string): Record<string, string> {
  const at = css.indexOf(`${selector} {`)
  if (at < 0) throw new Error(`no rule ${selector}`)
  const body = css.slice(css.indexOf('{', at) + 1, css.indexOf('}', at))
  const out: Record<string, string> = {}
  for (const m of body.matchAll(/--([a-z-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) out[m[1]] = m[2]
  return out
}
const light = tokens(':root')
const dark = { ...light, ...tokens(":root[data-theme='dark']") }
// The dark rule inside the media query must agree with the explicit one: the same palette however dark mode is switched on.
const darkMedia = (() => {
  const at = css.indexOf(":root:not([data-theme='light']) {")
  const body = css.slice(css.indexOf('{', at) + 1, css.indexOf('}', at))
  const out: Record<string, string> = {}
  for (const m of body.matchAll(/--([a-z-]+):\s*(#[0-9a-fA-F]{6})\s*;/g)) out[m[1]] = m[2]
  return out
})()

// [foreground, background, minimum ratio, what it is]
const PAIRS: [string, string, number, string][] = [
  ['fg', 'panel', 7, 'chip, question, reason text'],
  ['muted', 'panel', 4.5, 'phrase, "Something else", caret'],
  ['muted', 'sunk', 4.5, 'key cap digits'],
  ['on-accent', 'accent', 4.5, 'the step pill'],
  ['accent', 'panel', 3, 'the focus ring'],
  ['control-line', 'panel', 3, 'button edges'],
]

describe('the Cue panel palette passes WCAG AA in light and dark', () => {
  for (const [name, set] of [['light', light], ['dark', dark]] as const) {
    for (const [fg, bg, min, what] of PAIRS) {
      it(`${name}: ${fg} on ${bg} (${what}) is at least ${min}:1`, () => {
        expect(contrastRatio(set[fg], set[bg])).toBeGreaterThanOrEqual(min)
      })
    }
  }
  it('the dark palette is the same whether it comes from the system or from the data-theme switch', () => {
    for (const k of Object.keys(darkMedia)) expect(darkMedia[k], k).toBe(dark[k])
  })
})
