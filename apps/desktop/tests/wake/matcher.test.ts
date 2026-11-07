import { describe, expect, it } from 'vitest'
import { PERSONA_LIST } from '../../src/shared/personas'
import { createWakeMatcher, editDistance, normalize, phoneticKey, similarity } from '../../src/renderer/wake/matcher'
import fixtures from './fixtures/asr-transcripts.json'

const matcher = createWakeMatcher(PERSONA_LIST)
const who = (text: string, final = false): string | null => matcher.match(text, { final })?.personaId ?? null

describe('helpers', () => {
  it('normalises case, punctuation, apostrophes and diacritics', () => {
    expect(normalize("  Hey, MARCUS!! It's  ")).toBe('hey marcus its')
    expect(normalize('Amélia')).toBe('amelia')
  })
  it('edit distance counts a transposition as one edit', () => {
    expect(editDistance('marcus', 'marucs')).toBe(1)
    expect(editDistance('', 'abc')).toBe(3)
    expect(similarity('marcus', 'marcus')).toBe(1)
  })
  it('phonetic keys collapse spelling variants of the same sound', () => {
    expect(phoneticKey('marcus')).toBe(phoneticKey('marcos'))
    expect(phoneticKey('marcus')).toBe(phoneticKey('markus'))
    expect(phoneticKey('amelia')).toBe(phoneticKey('emilia'))
    expect(phoneticKey('marcus')).not.toBe(phoneticKey('amelia'))
  })
})

describe('positive matches', () => {
  it.each([
    ['Hey Marcus', 'marcus'],
    ['hey marcus.', 'marcus'],
    ['Hey, Marcus!', 'marcus'],
    ['HI MARCUS', 'marcus'],
    ['okay Marcus can you help me', 'marcus'],
    ['Ok marcus', 'marcus'],
    ['Hello Marcus', 'marcus'],
    ['Hey Amelia', 'amelia'],
    ['hi amelia, how do I join the video call?', 'amelia'],
    ['Okay, Amelia', 'amelia'],
  ])('%s -> %s', (text, id) => expect(who(text)).toBe(id))

  it('accepts configured aliases and ASR variants by fuzzy/phonetic match', () => {
    for (const t of ['hey marcos', 'hey markus', 'hey marcas', 'hey marquis', 'hey mark us', 'hay marcus', 'hey maracas', 'hey marcuss']) expect(who(t), t).toBe('marcus')
    for (const t of ['hey emilia', 'hey amelie', 'hey amalia', 'hey emelia', 'hey amelya', 'hey a mealia', 'hay amelia', 'hey amelea']) expect(who(t), t).toBe('amelia')
  })

  it('hands back what was said after the name', () => {
    const m = matcher.match('Hey Marcus, make the text bigger.')
    expect(m?.trailing).toBe('make the text bigger')
    expect(m?.exact).toBe(true)
    expect(m?.score).toBe(1)
  })

  it('fuzzy hits score below an exact hit', () => {
    const m = matcher.match('hey marcuz')
    expect(m?.exact).toBe(false)
    expect(m!.score).toBeLessThan(1)
    expect(m!.score).toBeGreaterThanOrEqual(0.8)
  })

  it('works on a partial (interim) transcript as soon as the name appears', () => {
    expect(who('Hey')).toBeNull()
    expect(who('Hey Marc')).toBeNull()
    expect(who('Hey Marcus')).toBe('marcus')
  })
})

describe('false positives that must NOT fire', () => {
  it.each([
    'Hey Google, what is the weather',
    'Hey Alexa set a timer',
    'Hey Siri',
    'Hey Mark, are you coming to dinner',
    'Hey Marks',
    'Hey market',
    'Hey Marcia, pass the salt',
    'Hey America',
    'Hey Emily, did you see the news',
    'Hey Amy',
    'The camellia bush is lovely',
    'I went to the market to buy apples',
    'Marcus Aurelius was a Roman emperor',
    'I spoke to my friend Amelia yesterday',
    'We should video call grandma and make the text bigger',
    'Hey there, I need some help',
    'Hey you',
    'hello everyone',
    'ok',
    '',
    '   ',
  ])('%j', (text) => expect(who(text)).toBeNull())

  it('does not glue words across a comma ("Hey Mark, us two...")', () => {
    expect(who('Hey Mark, us two should go')).toBeNull()
    expect(who('Hey mark us two should go')).toBe('marcus')
  })

  it('a bare name never fires on an interim transcript, nor inside a longer final', () => {
    expect(who('Marcus')).toBeNull()
    expect(who('Marcus Aurelius was a Roman emperor', true)).toBeNull()
    expect(who('Amelia Earhart flew across the Atlantic', true)).toBeNull()
  })

  it('the other persona name does not trigger this persona, and ambiguity fires nothing', () => {
    expect(who('hey amelia')).toBe('amelia')
    expect(who('hey marcus')).toBe('marcus')
    // Two close names: the matcher must refuse rather than guess.
    const close = createWakeMatcher([
      { id: 'a', wakePhrases: ['hey maya'], wakeAliases: [] },
      { id: 'b', wakePhrases: ['hey mia'], wakeAliases: [] },
    ])
    expect(close.match('hey maya')?.personaId).toBe('a')
    expect(close.match('hey mia')?.personaId).toBe('b')
    const insp = close.inspect('hey maia')
    expect(insp.match).toBeNull()
    expect(insp.ambiguous).toBe(true)
  })
})

describe('bare name on a final transcript (ASR dropped "hey")', () => {
  it('fires for exactly the name, or the name as a vocative', () => {
    expect(who('Amelia.', true)).toBe('amelia')
    expect(who('Marcus', true)).toBe('marcus')
    expect(who('Amelia, how do I join a video call?', true)).toBe('amelia')
    expect(who('Amelia, how do I join a video call?', false)).toBeNull()
  })
  it('can be switched off', () => {
    const strict = createWakeMatcher(PERSONA_LIST, { bareNameOnFinal: false })
    expect(strict.match('Amelia.', { final: true })).toBeNull()
  })
})

describe('tunable threshold', () => {
  it('a stricter threshold rejects fuzzy hits but keeps exact ones', () => {
    const strict = createWakeMatcher(PERSONA_LIST, { threshold: 0.94, rejectWords: [] })
    expect(strict.match('hey maracas')?.personaId).toBe('marcus') // phonetic route is capped at 0.95
    expect(strict.match('hey marlus')).toBeNull()
    const stricter = createWakeMatcher(PERSONA_LIST, { threshold: 0.99, rejectWords: [] })
    expect(stricter.match('hey maracas')).toBeNull()
    expect(stricter.match('hey marcus')?.personaId).toBe('marcus')
    expect(stricter.match('hey marcos')?.personaId).toBe('marcus') // explicit alias
  })
  it('a looser threshold catches more, at the cost of false positives', () => {
    const loose = createWakeMatcher(PERSONA_LIST, { threshold: 0.6, rejectWords: [] })
    expect(loose.match('hey marlus')?.personaId).toBe('marcus')
  })
})

describe('driven only by config: a renamed persona works with no code change', () => {
  const renamed = createWakeMatcher([
    { id: 'marcus', wakePhrases: ['hey jarvis', 'ok jarvis'], wakeAliases: ['hey service', 'hey jarvas'] },
    { id: 'amelia', wakePhrases: ['hey nova'], wakeAliases: ['hey noah'] },
  ])
  it('matches the new names and drops the old ones', () => {
    expect(renamed.match('Hey Jarvis')?.personaId).toBe('marcus')
    expect(renamed.match('hey jarvas')?.personaId).toBe('marcus')
    expect(renamed.match('hey nova')?.personaId).toBe('amelia')
    expect(renamed.match('hey marcus')).toBeNull()
    expect(renamed.match('hey amelia')).toBeNull()
  })
  it('multi-word names work, and a multi-word prefix-less alias only fires at the start', () => {
    const m = createWakeMatcher([{ id: 'x', wakePhrases: ['hey mister bean'], wakeAliases: ['mr bean'] }])
    expect(m.match('hey mister bean')?.personaId).toBe('x')
    expect(m.match('mr bean, are you there')?.personaId).toBe('x')
    expect(m.match('I watched mr bean last night')).toBeNull()
  })
})

describe('real gemini-3.5-transcribe-live transcripts (macOS say voices, 18 accents)', () => {
  const clips = fixtures.clips
  const fires = (c: (typeof clips)[number]): (string | null)[] => c.transcripts.map((t) => who(t.text, t.final))

  it('never fires the wrong persona or any persona on non-wake speech (0 false triggers over every interim and final)', () => {
    const wrong: string[] = []
    for (const c of clips) {
      for (const got of fires(c)) {
        if (got === null) continue
        if (c.kind === 'neg') wrong.push(`${c.clip} fired ${got}`)
        else if (got !== c.expect) wrong.push(`${c.clip} fired ${got}, wanted ${c.expect}`)
      }
    }
    expect(wrong).toEqual([])
  })

  it('wakes the right persona on >= 90% of clips where the recogniser returned any text', () => {
    const pos = clips.filter((c) => c.kind === 'pos')
    const woke = pos.filter((c) => fires(c).includes(c.expect as string))
    const missed = pos.filter((c) => !woke.includes(c)).map((c) => `${c.clip}: ${c.transcripts.at(-1)?.text}`)
    // Remaining misses are the recogniser mangling the name itself ("Hema kas", "miúdo"); the hotkey covers those.
    expect(woke.length / pos.length, JSON.stringify(missed)).toBeGreaterThanOrEqual(0.9)
  })
})
