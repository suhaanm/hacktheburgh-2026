import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ANNOTATION_TONES, annotationStyle } from './annotation-style'
import { GLASS_CARD_FLOOR, GLASS_SHELL_FLOOR, glassAlphas } from './apply-settings'
import { blend, contrastRatio, parseGlassMix, parseHex, resolveTheme, type ThemeKey, type TokenMap } from './contrast'

const css = readFileSync(join(__dirname, 'tokens.css'), 'utf8')

const themes: { name: string; key: ThemeKey }[] = [
  { name: 'light', key: { dark: false, highContrast: false } },
  { name: 'dark', key: { dark: true, highContrast: false } },
  { name: 'high-contrast light', key: { dark: false, highContrast: true } },
  { name: 'high-contrast dark', key: { dark: true, highContrast: true } },
]
const personas: (ThemeKey['persona'] | undefined)[] = [undefined, 'marcus', 'amelia']

// [foreground, background, minimum ratio, why]
const pairs: [string, string, number, string][] = [
  ['ink', 'bg', 7, 'body text'],
  ['ink', 'surface', 7, 'body text on panel'],
  ['ink', 'surface-raised', 7, 'text on cards'],
  ['ink', 'surface-sunken', 7, 'text on sunken areas'],
  ['ink-muted', 'bg', 4.5, 'secondary text'],
  ['ink-muted', 'surface', 4.5, 'secondary text on panel'],
  ['ink-muted', 'surface-raised', 4.5, 'secondary text on cards'],
  ['ink-muted', 'surface-sunken', 4.5, 'unselected segment label'],
  ['ink-subtle', 'bg', 4.5, 'captions and dates'],
  ['ink-subtle', 'surface', 4.5, 'captions and dates on panel'],
  ['ink-subtle', 'surface-raised', 4.5, 'captions on cards'],
  ['line-strong', 'surface', 3, 'control boundaries'],
  ['line-strong', 'bg', 3, 'control boundaries on page'],
  ['line-strong', 'surface-sunken', 3, 'switch track edge'],
  ['focus', 'bg', 3, 'focus ring'],
  ['focus', 'surface', 3, 'focus ring on panel'],
  ['accent', 'surface', 4.5, 'accent used as text or icon'],
  ['accent', 'bg', 4.5, 'accent on page'],
  ['accent', 'surface-raised', 4.5, 'accent on cards'],
  ['on-accent', 'accent', 4.5, 'label on accent button'],
  ['ink', 'accent-soft', 7, 'level chip name'],
  ['ink-muted', 'accent-soft', 4.5, 'level chip kicker'],
  ['accent', 'accent-soft', 3, 'chip border and bars'],
  ['success-ink', 'surface', 4.5, 'success text'],
  ['success-ink', 'success-soft', 4.5, 'done pill'],
  ['warn-ink', 'surface', 4.5, 'warning text'],
  ['warn-ink', 'warn-soft', 4.5, 'warning note'],
  ['danger-ink', 'surface', 4.5, 'error text'],
  ['danger-ink', 'danger-soft', 4.5, 'error banner and failed pill'],
  ['danger-ink', 'bg', 3, 'listening dot on page'],
  ['ink', 'success-soft', 4.5, 'text on success wash'],
  ['ink', 'warn-soft', 4.5, 'text on warning wash'],
  ['ink', 'danger-soft', 4.5, 'text on error wash'],
  ['on-danger', 'danger-ink', 4.5, 'Stop button label'],
]

describe('tokens.css contrast', () => {
  for (const { name, key } of themes) {
    for (const persona of personas) {
      const label = `${name}${persona ? ` / ${persona}` : ''}`
      it(`${label}: every text and control pair meets its target`, () => {
        const t: TokenMap = resolveTheme(css, { ...key, persona })
        const failures: string[] = []
        for (const [fg, bg, min, why] of pairs) {
          const f = t[`--${fg}`]
          const b = t[`--${bg}`]
          if (!f || !b) {
            failures.push(`missing token for ${fg} on ${bg}`)
            continue
          }
          const ratio = contrastRatio(f, b)
          if (ratio < min) failures.push(`${fg} ${f} on ${bg} ${b} = ${ratio.toFixed(2)} (needs ${min}) [${why}]`)
        }
        expect(failures).toEqual([])
      })
    }
  }

  it('high contrast text reaches 15:1 or better', () => {
    for (const dark of [false, true]) {
      const t = resolveTheme(css, { dark, highContrast: true })
      expect(contrastRatio(t['--ink']!, t['--bg']!)).toBeGreaterThanOrEqual(15)
    }
  })
})

// Machado et al. 2009 matrices (severity 1.0), applied in linear RGB.
const CVD: Record<string, number[][]> = {
  protan: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  deutan: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
  tritan: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.3039]],
}
const toLinear = (v: number): number => (v / 255 <= 0.04045 ? v / 255 / 12.92 : Math.pow((v / 255 + 0.055) / 1.055, 2.4))
function lab(rgbLinear: number[]): [number, number, number] {
  const [r, g, b] = rgbLinear as [number, number, number]
  const x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
  const y = 0.2126 * r + 0.7152 * g + 0.0722 * b
  const z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
  const f = (v: number): number => (v > 0.008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116)
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))]
}
function simulate(hex: string, kind: keyof typeof CVD): [number, number, number] {
  const lin = parseHex(hex).map(toLinear)
  const m = CVD[kind]!
  return lab(m.map((row) => Math.min(1, Math.max(0, row[0]! * lin[0]! + row[1]! * lin[1]! + row[2]! * lin[2]!))))
}
const deltaE = (a: number[], b: number[]): number => Math.hypot(a[0]! - b[0]!, a[1]! - b[1]!, a[2]! - b[2]!)

describe('annotation style', () => {
  const lightScreens = ['#FFFFFF', '#F2F2F7', '#E5E5EA']
  const darkScreens = ['#000000', '#1C1C1E', '#2C2C2E']
  for (const highContrast of [false, true]) {
    for (const bigAnnotations of [false, true]) {
      const style = annotationStyle({ bigAnnotations, highContrast })
      const label = `${highContrast ? 'high contrast' : 'normal'}, ${bigAnnotations ? 'big' : 'standard'}`

      it(`${label}: each tone clears 3:1 on light and dark screens through its casing and halo`, () => {
        for (const tone of ANNOTATION_TONES) {
          const t = style.tones[tone]
          expect(contrastRatio(t.core, t.casing)).toBeGreaterThanOrEqual(3)
          expect(contrastRatio(t.onCore, t.core)).toBeGreaterThanOrEqual(4.5)
          for (const bg of lightScreens) expect(contrastRatio(t.casing, bg)).toBeGreaterThanOrEqual(3)
          for (const bg of darkScreens) expect(contrastRatio(t.halo, bg)).toBeGreaterThanOrEqual(3)
        }
      })

      it(`${label}: tones stay apart for colour-blind viewers, and never rely on colour alone`, () => {
        const failures: string[] = []
        for (const kind of Object.keys(CVD)) {
          for (let i = 0; i < ANNOTATION_TONES.length; i++) {
            for (let j = i + 1; j < ANNOTATION_TONES.length; j++) {
              const a = ANNOTATION_TONES[i]!
              const b = ANNOTATION_TONES[j]!
              const d = deltaE(simulate(style.tones[a].core, kind), simulate(style.tones[b].core, kind))
              // Pairs that look alike must at least differ in glyph and dash, which they always do.
              if (d < 12 && style.tones[a].glyph === style.tones[b].glyph) failures.push(`${a}/${b} ${kind} dE ${d.toFixed(1)}`)
            }
          }
        }
        expect(failures).toEqual([])
        expect(new Set(ANNOTATION_TONES.map((t) => style.tones[t].glyph)).size).toBe(ANNOTATION_TONES.length)
      })
    }
  }

  it('bigAnnotations scales marks by 1.6', () => {
    const a = annotationStyle({ bigAnnotations: false, highContrast: false })
    const b = annotationStyle({ bigAnnotations: true, highContrast: false })
    expect(b.scale).toBe(1.6)
    expect(b.badge.diameter / a.badge.diameter).toBeCloseTo(1.6, 1)
    expect(b.caption.fontSize / a.caption.fontSize).toBeCloseTo(1.6, 1)
    expect(b.stroke.core / a.stroke.core).toBeCloseTo(1.6, 1)
  })

  it('reduced motion stops the pulse', () => {
    const s = annotationStyle({ bigAnnotations: false, highContrast: false }, { reducedMotion: true })
    expect(s.pulse.enabled).toBe(false)
    expect(s.ghostCursor.press.durationMs).toBe(0)
  })
})

describe('glass', () => {
  it('maps the opacity setting into safe alphas', () => {
    expect(glassAlphas(0.35).shell).toBeCloseTo(GLASS_SHELL_FLOOR, 5)
    expect(glassAlphas(1).shell).toBeCloseTo(1, 5)
    expect(glassAlphas(0.01).shell).toBeCloseTo(GLASS_SHELL_FLOOR, 5)
    expect(glassAlphas(0.35).card).toBeGreaterThanOrEqual(GLASS_CARD_FLOOR)
    expect(glassAlphas(0.78).shell).toBeGreaterThan(glassAlphas(0.5).shell)
  })

  for (const dark of [false, true]) {
    it(`${dark ? 'dark' : 'light'}: text stays readable over the worst desktops (pure black and pure white)`, () => {
      const t = resolveTheme(css, { dark, highContrast: false, glass: true })
      const layer = (token: string): { hex: string; alpha: number } => {
        const m = parseGlassMix(t[token]!)
        if (!m) throw new Error(`${token} is not a glass mix: ${t[token]}`)
        return { hex: m.hex, alpha: m.layer === 'shell' ? GLASS_SHELL_FLOOR : GLASS_CARD_FLOOR }
      }
      const failures: string[] = []
      for (const backdrop of ['#000000', '#ffffff']) {
        const paint = (token: string): string => {
          const l = layer(token)
          return blend(l.hex, l.alpha, backdrop)
        }
        const check = (fg: string, bgToken: string, min: number): void => {
          const ratio = contrastRatio(t[`--${fg}`]!, paint(`--${bgToken}`))
          if (ratio < min) failures.push(`${fg} on ${bgToken} over ${backdrop} = ${ratio.toFixed(2)} (needs ${min})`)
        }
        for (const bg of ['bg', 'surface']) {
          check('ink', bg, 4.5)
          check('ink-muted', bg, 4.5)
          check('ink-subtle', bg, 4.5)
        }
        for (const bg of ['surface-raised', 'surface-sunken']) {
          check('ink', bg, 4.5)
          check('ink-muted', bg, 4.5)
          check('ink-subtle', bg, 4.5)
        }
      }
      expect(failures).toEqual([])
    })
  }
})
