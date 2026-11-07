// The offline measurement of the wake phrase matcher, pinned: the false-accept rate over ordinary sentences and the miss rate over accepted
// variants, with Wilson intervals. The numbers are about the matching logic on these strings, not about a microphone (see corpus-dev.ts).
import { describe, expect, it } from 'vitest'
import { NEGATIVES_DEV, POSITIVES_DEV } from './corpus-dev'
import { NEGATIVES_HELDOUT, POSITIVES_HELDOUT } from './corpus-heldout'
import { measure, report } from './measure'

// A false accept the held-out set found and nobody tuned away: a close spelling ("nack") followed by a comma is accepted at once ("hey nack,"
// is how a recogniser writes the vocative). Fixing it would spend the held-out set, so it is listed here and in docs/knack-ux/09-wake-voice.md.
const KNOWN_HELDOUT_FALSE_ACCEPTS = ['Hey nack, nack, nack, that is all I hear from this network.']

describe('corpus sizes', () => {
  const neg = [...NEGATIVES_DEV, ...NEGATIVES_HELDOUT]
  const pos = [...POSITIVES_DEV, ...POSITIVES_HELDOUT]
  const uniq = (xs: string[]): number => new Set(xs.map((s) => s.toLowerCase().replace(/[^a-z' ]+/g, ' ').replace(/\s+/g, ' ').trim())).size
  it('has at least 300 different ordinary sentences and at least 40 different accepted variants (case and punctuation ignored)', () => {
    expect(uniq(neg)).toBeGreaterThanOrEqual(300)
    expect(uniq(pos)).toBeGreaterThanOrEqual(40)
  })
  it('has no sentence in both the negatives and the positives', () => {
    const n = new Set(neg.map((s) => s.toLowerCase()))
    expect(pos.filter((s) => n.has(s.toLowerCase()))).toEqual([])
  })
})

describe('measured on the development set (the matcher was tuned on it)', () => {
  const m = measure(NEGATIVES_DEV, POSITIVES_DEV)
  it('accepts every variant and none of the ordinary sentences', () => {
    console.log(report('development', m))
    expect(m.falseAccepts).toEqual([])
    expect(m.misses).toEqual([])
  })
})

describe('measured on the held-out set (written after the freeze)', () => {
  const m = measure(NEGATIVES_HELDOUT, POSITIVES_HELDOUT)
  it('has exactly the known false accepts and no misses', () => {
    console.log(report('held-out', m))
    expect(m.falseAccepts).toEqual(KNOWN_HELDOUT_FALSE_ACCEPTS)
    expect(m.misses).toEqual([])
    expect(m.falseAccept.high).toBeLessThan(0.05)
  })
})

describe('measured on both sets together', () => {
  const m = measure([...NEGATIVES_DEV, ...NEGATIVES_HELDOUT], [...POSITIVES_DEV, ...POSITIVES_HELDOUT])
  it('reports the rates with their intervals', () => {
    console.log(report('all', m))
    expect(m.falseAccept.n).toBeGreaterThanOrEqual(300)
    expect(m.falseAccept.k).toBe(KNOWN_HELDOUT_FALSE_ACCEPTS.length)
    expect(m.miss.k).toBe(0)
    expect(m.falseAccept.high).toBeLessThan(0.02)
    expect(m.miss.high).toBeLessThan(0.07)
  })
})
