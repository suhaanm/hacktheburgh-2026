import { describe, expect, it } from 'vitest'
import { readRung, rungDigest, type RungRecord } from './rung'

const base = { schema: 1 as const, rung: 'R1' as const, at: '2026-11-08T09:00:00Z', targets: ['TextEdit'], postcondition: 'passed' as const, real: true as const }
const good = (over: Partial<RungRecord> = {}): string => JSON.stringify({ ...base, ...over, digest: rungDigest({ ...base, ...over }) })
const read = (text: string | Error) => readRung('/d', () => {
  if (text instanceof Error) throw text
  return text
})

describe('the rung record', () => {
  it('is cleared only by a well-formed, passed, real R1 record with a matching digest', () => {
    expect(read(good())).toEqual({ cleared: true, targets: ['TextEdit'], at: base.at })
  })
  it('absent means pending, and so does anything unreadable', () => {
    expect(read(Object.assign(new Error('x'), { code: 'ENOENT' }))).toEqual({ cleared: false, why: 'absent' })
    expect(read(Object.assign(new Error('x'), { code: 'EACCES' }))).toEqual({ cleared: false, why: 'unreadable' })
  })
  it.each([
    ['not json', 'nope', 'malformed'],
    ['an array', '[]', 'malformed'],
    ['a missing field', JSON.stringify({ schema: 1, rung: 'R1' }), 'malformed'],
    ['targets of the wrong type', JSON.stringify({ ...base, targets: [1], digest: 'x' }), 'malformed'],
  ])('fails closed on %s', (_l, text, why) => {
    expect(read(text)).toEqual({ cleared: false, why })
  })
  it('refuses another rung, a failed check, a dry run and a tampered record', () => {
    expect(read(JSON.stringify({ ...base, rung: 'R2', digest: rungDigest(base) }))).toEqual({ cleared: false, why: 'wrong_rung' })
    expect(read(JSON.stringify({ ...base, postcondition: 'failed', digest: 'x' }))).toEqual({ cleared: false, why: 'not_passed' })
    expect(read(JSON.stringify({ ...base, real: false, digest: 'x' }))).toEqual({ cleared: false, why: 'not_passed' })
    const tampered = JSON.parse(good()) as Record<string, unknown>
    tampered.targets = ['TextEdit', 'Safari']
    expect(read(JSON.stringify(tampered))).toEqual({ cleared: false, why: 'digest' })
  })
  it('the digest does not depend on the order of the targets', () => {
    expect(rungDigest({ ...base, targets: ['b', 'a'] })).toBe(rungDigest({ ...base, targets: ['a', 'b'] }))
  })
})
