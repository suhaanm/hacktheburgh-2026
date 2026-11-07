import { describe, expect, it } from 'vitest'
import { compactNote } from './note-text'

describe('compactNote: one short line, the thought kept whole', () => {
  it('leaves a short line alone (minus the full stop)', () => {
    expect(compactNote('Check cliff edges.')).toBe('Check cliff edges')
    expect(compactNote('  Look   here  ')).toBe('Look here')
    expect(compactNote('')).toBe('')
  })

  it('keeps the action and drops the reason when the sentence is long', () => {
    expect(compactNote('Check cliff edges before you reconcile the results.')).toBe('Check cliff edges')
    expect(compactNote('Copy the household from the record after you open the calculator.', 40)).toBe('Copy the household from the record')
  })

  it('falls back to the first sentence, then to a word boundary with an ellipsis, never past the limit', () => {
    expect(compactNote('Is any figure close to a limit? What changes if it moves a little?')).toBe('Is any figure close to a limit?')
    const long = compactNote('Read every line of the result carefully and compare each figure with the household record in front of you')
    expect(long.length).toBeLessThanOrEqual(40)
    expect(long.endsWith('…')).toBe(true)
    expect(long).not.toMatch(/\s…$/)
    for (const max of [12, 24, 40, 60]) expect(compactNote('x'.repeat(200), max).length).toBeLessThanOrEqual(max)
  })
})
