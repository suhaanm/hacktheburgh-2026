import { describe, expect, it } from 'vitest'
import { DEFAULT_COOLDOWN_MS, FIT, GREETINGS, NAMES_CLOSE, NAMES_EXACT, NAMES_WEAK, STRICT_FIT, createWakeMatcher, matchWake, tokenize } from './matching'

const accept = (s: string, settled = true): boolean => matchWake(s, { settled }).verdict === 'accept'

describe('tokenize', () => {
  it('lower-cases, straightens apostrophes and flags boundaries', () => {
    expect(tokenize("Hey, Knack. What’s next?").map((t) => [t.word, t.boundaryBefore])).toEqual([['hey', true], ['knack', true], ["what's", true], ['next', false]])
  })
  it('is total: any string tokenises, nothing throws', () => {
    for (const s of ['', '   ', '!!!', '\n\n', '‮\u0000', 'ünïcödé', '🙂 hey 🙂', "'''", 'a'.repeat(5000)]) expect(() => tokenize(s)).not.toThrow()
    expect(tokenize('')).toEqual([])
  })
})

describe('the accept list', () => {
  it('accepts the exact name right away, even before the utterance settles', () => {
    expect(matchWake('hey knack', { settled: false })).toEqual({ verdict: 'accept', variant: 'exact' })
    expect(matchWake('Hey, Knack!', {})).toEqual({ verdict: 'accept', variant: 'exact' })
    expect(accept('hay knack', false)).toBe(true)
    expect(accept('heya Knack how do I do this', false)).toBe(true)
  })
  it('lets lead-in words and a sentence mark come before the greeting', () => {
    expect(accept('okay hey knack', false)).toBe(true)
    expect(accept('Oh, hey Knack, can you look at this?', false)).toBe(true)
    expect(accept('so um hey knack', false)).toBe(true)
    expect(accept('That is all from me. Hey Knack, what next?', false)).toBe(true)
  })
  it('a comma alone does not start an utterance, a full stop does', () => {
    expect(accept('Look, hey, knack aside, we need more time.', false)).toBe(false)
    expect(accept('Look. Hey knack, we need more time.', false)).toBe(true)
    expect(tokenize('a, b. c').map((t) => [t.word, t.boundaryBefore, t.sentenceBefore])).toEqual([['a', true, true], ['b', true, false], ['c', true, true]])
  })
  it('does not accept the greeting in the middle of a sentence', () => {
    expect(accept('he said hey knack to the room')).toBe(false)
    expect(accept('you can say hey knack and then talk')).toBe(false)
    expect(accept('tell her hey knack is great')).toBe(false)
  })
  it('waits on a close spelling at the end, then accepts it once settled', () => {
    expect(matchWake('hey nack', { settled: false })).toEqual({ verdict: 'wait', variant: 'close' })
    expect(matchWake('hey nack', { settled: true })).toEqual({ verdict: 'accept', variant: 'close' })
    expect(accept('Hey Nac.', true)).toBe(true)
  })
  it('accepts a close spelling followed by a clause mark or a request word, and refuses it glued to an ordinary word', () => {
    expect(accept('hey nack where is the tab', false)).toBe(true)
    expect(accept('hey nack, the server is slow', false)).toBe(true)
    expect(accept('hey nack off', true)).toBe(false)
    expect(accept('hey nack for the win', true)).toBe(false)
  })
  it('accepts knock only when the next words fit, and never at the end', () => {
    expect(accept('hey knock can you help me with this', false)).toBe(true)
    expect(accept('Hey knock, show me the submit button', false)).toBe(true)
    expect(matchWake('hey knock', { settled: false }).verdict).toBe('wait')
    expect(matchWake('hey knock', { settled: true }).verdict).toBe('reject')
    for (const s of ['hey knock it off', 'hey knock knock', 'hey knock on the door', 'Hey, knock it off, I am busy.']) expect(accept(s)).toBe(false)
  })
  it('refuses near misses and ordinary sentences', () => {
    for (const s of ['hey Jack', 'hey neck', 'hey Nick', 'hey Mac', 'knack', 'She has a knack for it.', 'a knack', 'hey knackered', 'hey knacks', 'hey', 'hey hey', 'okay knack', 'hi knack', 'hey a knack for it', 'hey knack for the details', 'hey knack knack', '', '   ']) expect(accept(s)).toBe(false)
  })
  it('names are a closed list that contains no common near-miss', () => {
    for (const bad of ['neck', 'nick', 'jack', 'mack', 'mac', 'back', 'snack', 'knacks', 'knackered', 'knuckle', 'nacho', 'nak']) {
      expect([...NAMES_EXACT, ...NAMES_CLOSE, ...NAMES_WEAK]).not.toContain(bad)
    }
    expect(GREETINGS).not.toContain('hi')
    for (const w of STRICT_FIT) expect(FIT.includes(w) || w === 'ok' || w === 'okay').toBe(true)
  })
  it('is stable when the transcript grows word by word (partials)', () => {
    const words = 'hey knack can you show me where to click'.split(' ')
    const verdicts = words.map((_, i) => matchWake(words.slice(0, i + 1).join(' '), { settled: false }).verdict)
    expect(verdicts.slice(0, 1)).toEqual(['reject'])
    expect(verdicts.slice(1).every((v) => v === 'accept')).toBe(true)
  })
  it('never throws on hostile input', () => {
    for (const s of ['hey ' + 'knack '.repeat(2000), '\u0000hey\u0000knack', 'HEY\tKNACK', 'hey   knack', "hey' knack'", 'hey‮knack']) expect(() => matchWake(s, { settled: true })).not.toThrow()
    expect(accept('HEY\tKNACK')).toBe(true)
    expect(accept('hey   knack')).toBe(true)
  })
})

describe('the same words twice', () => {
  it('"Hey Knack, hey Knack" is one wake: the second is inside the cooldown', () => {
    let t = 0
    const m = createWakeMatcher({ now: () => t })
    expect(matchWake('hey knack hey knack', { settled: true }).verdict).toBe('accept')
    expect(m.feed('hey knack hey knack', { settled: true }).accepted).toBe(true)
    t += 500
    expect(m.feed('hey knack', { settled: true })).toMatchObject({ accepted: false, reason: 'cooldown' })
  })
})

describe('the cooldown', () => {
  it('accepts once, then refuses for the cooldown, then accepts again', () => {
    let t = 1000
    const m = createWakeMatcher({ now: () => t })
    expect(m.feed('hey knack', { settled: true }).accepted).toBe(true)
    t += DEFAULT_COOLDOWN_MS - 1
    expect(m.feed('hey knack', { settled: true })).toMatchObject({ accepted: false, reason: 'cooldown' })
    t += 2
    expect(m.feed('hey knack', { settled: true }).accepted).toBe(true)
  })
  it('does not start a cooldown for a reject or a wait', () => {
    const t = 0
    const m = createWakeMatcher({ now: () => t, cooldownMs: 5000 })
    expect(m.feed('hey jack').reason).toBe('reject')
    expect(m.feed('hey nack', { settled: false }).reason).toBe('wait')
    expect(m.feed('hey nack', { settled: true }).accepted).toBe(true)
  })
  it('reset clears the cooldown', () => {
    const m = createWakeMatcher({ now: () => 0 })
    m.feed('hey knack')
    expect(m.feed('hey knack').reason).toBe('cooldown')
    m.reset()
    expect(m.feed('hey knack').accepted).toBe(true)
  })
})
