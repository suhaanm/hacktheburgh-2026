import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { announcedLines } from './Captions'

const css = fs.readFileSync(path.join(__dirname, 'components.css'), 'utf8')

describe('reduced motion', () => {
  const block = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'))
  const first = block.indexOf('{') + 1
  const rule = block.slice(first, block.indexOf('{', first)) // the selector list of the first rule inside the media query
  it('stops the pill listening ripple and the listening-light ripple', () => {
    expect(rule).toContain('.al-orbwrap__light::after')
    expect(rule).toContain('.al-light__dot::after')
    expect(block).toMatch(/animation:\s*none\s*!important/)
  })

  it('every ripple animation targets a pseudo-element or orb the reduced-motion rule covers', () => {
    const ripples = [...css.matchAll(/([^{}]+)\{[^{}]*animation:\s*al-ripple[^{}]*\}/g)].map((m) => m[1].trim())
    expect(ripples.length).toBeGreaterThan(0)
    for (const sel of ripples.flatMap((r) => r.split(',')).map((x) => x.trim())) {
      const last = sel.split(/\s+/).pop() ?? ''
      const bare = last.replace(/\[[^\]]*\]/g, '')
      const covered = rule.includes(bare) || /\.al-orb\b/.test(sel) || sel.includes('.al-orb ')
      expect(covered, sel).toBe(true)
    }
  })
})

describe('segmented targets', () => {
  it('every segment is at least 44px tall, the compact chat pill extends its hit area instead', () => {
    expect(css).toMatch(/\.al-seg__btn\s*\{[^}]*min-height:\s*44px/)
    expect(css).toMatch(/\.al-chat__top \.al-seg__btn::before\s*\{[^}]*inset:\s*-6px 0/)
  })
})

describe('captions for screen readers', () => {
  it('announces final lines only', () => {
    const lines = [
      { id: '1', speaker: 'assistant', text: 'Hello', final: true, at: 1 },
      { id: '2', speaker: 'user', text: 'Hel', final: false, at: 2 },
    ] as const
    expect(announcedLines(lines).map((l) => l.id)).toEqual(['1'])
  })
})
