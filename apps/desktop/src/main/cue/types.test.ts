import { describe, expect, it } from 'vitest'
import { FIXTURES, MALFORMED } from './fixtures'
import { capChars, CHIP_MAX_CHARS, cleanText, isProgress, NONE_DECISION, parseCueDecision, pathPhrase, reasonLine, sameCue, WHISPER_MAX_WORDS } from './types'

describe('parseCueDecision: fixtures', () => {
  it('every fixture parses to its own kind', () => {
    for (const [name, raw] of Object.entries(FIXTURES)) {
      const d = parseCueDecision(raw)
      const wanted = (raw as { kind: string }).kind
      expect(d.kind, name).toBe(wanted)
    }
  })

  it('every malformed input becomes none', () => {
    for (const m of MALFORMED) expect(parseCueDecision(m.raw).kind, m.name).toBe('none')
  })

  it('keeps the tier, step, options and reason table', () => {
    const t3 = parseCueDecision(FIXTURES['cue-t3'])
    expect(t3.tier).toBe(3)
    expect(t3.step?.id).toBe('write_note')
    expect(t3.target?.box_2d).toEqual([222, 681, 467, 917])
    expect(t3.new).toBe(true)
    // The engine's fixed "other" row is stripped from the options (the card always draws its own); the question text comes from question.text.
    const ask = parseCueDecision(FIXTURES['ask-4'])
    expect(ask.options?.map((o) => o.id)).toEqual(['read_case', 'calc_a', 'cliff_a', 'write_note'])
    expect(ask.say.question).toBe('I cannot tell where you are. What is next?')
    expect(ask.question_type).toBe('unclear')
    expect(reasonLine(parseCueDecision(FIXTURES['cue-t2-l2']))).toBe('Copy the household from the record; retyping invites mistakes.')
    expect(parseCueDecision(FIXTURES['confirm']).retrieval).toBe(true)
  })

  it('accepts the { data } and { meta, data } wrappers', () => {
    const raw = FIXTURES['cue-t2-l2']
    expect(parseCueDecision({ data: raw }).kind).toBe('cue')
    expect(parseCueDecision({ meta: { v: 1 }, data: raw }).kind).toBe('cue')
  })
})

describe('parseCueDecision: strictness', () => {
  const cue = (patch: Record<string, unknown>): unknown => ({ ...(FIXTURES['cue-t2-l2'] as object), ...patch })

  it('drops unknown fields (nothing unvalidated survives)', () => {
    const d = parseCueDecision(cue({ evil: 'x', say: { chip: 'Hi', html: '<b>x</b>', whisper: null } }))
    expect(JSON.stringify(d)).not.toContain('evil')
    expect(JSON.stringify(d)).not.toContain('html')
  })

  it('caps the chip at 40 characters, at a word where one is close', () => {
    const long = 'Enter the number of children in the household now please'
    const d = parseCueDecision(cue({ say: { chip: long } }))
    expect([...d.say.chip].length).toBeLessThanOrEqual(CHIP_MAX_CHARS)
    expect(d.say.chip.endsWith('…')).toBe(true)
    expect(d.say.chip.startsWith('Enter the number of children')).toBe(true)
  })

  it('drops (not cuts) a whisper over eight words and keeps one of eight', () => {
    expect(parseCueDecision(cue({ tier: 4, say: { chip: 'x', whisper: 'one two three four five six seven eight nine' } })).say.whisper).toBeNull()
    const eight = 'one two three four five six seven eight'
    expect(eight.split(' ')).toHaveLength(WHISPER_MAX_WORDS)
    expect(parseCueDecision(cue({ tier: 4, say: { chip: 'x', whisper: eight, whisper_id: 'line_1' } })).say.whisper).toBe(eight)
    // No whisper, no audio id.
    expect(parseCueDecision(cue({ say: { chip: 'x', whisper: null, whisper_id: 'line_1' } })).say.whisper_id).toBeNull()
  })

  it('removes hidden and bidi characters and collapses whitespace', () => {
    expect(cleanText('He‮llo​  \n there\u0007')).toBe('He llo there')
    const d = parseCueDecision(cue({ say: { chip: 'Press‮ Calculate\u0000' } }))
    expect(d.say.chip).toBe('Press Calculate')
  })

  it('clamps boxes into the grid, fixes swapped corners and rejects degenerate or huge ones', () => {
    const box = (b: unknown): unknown => parseCueDecision(cue({ target: { box_2d: b, source: 'dom', confidence: 2 } })).target?.box_2d ?? null
    expect(box([-50, -20, 100, 1200])).toEqual([0, 0, 100, 1000])
    expect(box([500, 600, 400, 300])).toEqual([400, 300, 500, 600])
    expect(box([100, 100, 102, 400])).toBeNull() // too thin
    expect(box([0, 0, 900, 900])).toBeNull() // more than a third of the screen
    expect(box([1, 2, 3])).toBeNull()
    expect(box(['1', '2', '30', '40'])).toBeNull()
    expect(parseCueDecision(cue({ target: { box_2d: [0, 0, 100, 100], source: 'dom', confidence: 7 } })).target?.confidence).toBe(1)
  })

  it('a cue whose box failed the checks keeps its chip, and loses the box', () => {
    const d = parseCueDecision(cue({ target: { box_2d: [0, 0, 900, 900], source: 'vision', confidence: 0.9 } }))
    expect(d.kind).toBe('cue')
    expect(d.target?.box_2d ?? null).toBeNull()
  })

  it('validates enums: tier, level, source, trigger, origin', () => {
    const d = parseCueDecision(cue({ source: 'oracle', trigger: 'always', expires_in_s: 'never', why: { level: 7, origin: 'invented', path_prob: 3, reasons: ['ok_id', 'why.dotted', 'Not An Id', 5] } }))
    expect(d.expires_in_s).toBeNull()
    expect(d.source).toBe('rule')
    expect(d.trigger).toBe('auto')
    expect(d.why.level).toBeNull()
    expect(d.why.origin).toBeNull()
    expect(d.why.path_prob).toBe(1)
    expect(d.why.reasons).toEqual(['ok_id', 'why.dotted'])
  })

  it('keeps 2 to 4 options: more than four are cut, duplicates and non-ids are skipped', () => {
    const opts = Array.from({ length: 6 }, (_, i) => ({ id: `o${i}`, label: `Option ${i}` }))
    const d = parseCueDecision({ ...(FIXTURES['ask-3'] as object), options: [...opts, { id: 'other', label: 'Something else' }] })
    expect(d.options).toHaveLength(4)
  })

  it('texts: only slug keys, capped, no prototype tricks', () => {
    const texts = JSON.parse('{"__proto__": "x", "ok_id": "Fine.", "Bad Key": "no", "long": "' + 'a'.repeat(400) + '"}') as Record<string, string>
    const d = parseCueDecision(cue({ texts }))
    expect(Object.keys(d.texts).sort()).toEqual(['long', 'ok_id'])
    expect([...d.texts.long].length).toBeLessThanOrEqual(100)
    expect(({} as Record<string, unknown>).x).toBeUndefined()
  })

  it('numbers that are not numbers are ignored, cooldown and budget are bounded', () => {
    const d = parseCueDecision(cue({ cooldown_s: 'soon', budget_left: -3 }))
    expect(d.cooldown_s).toBe(0)
    expect(d.budget_left).toBeNull()
    expect(parseCueDecision(cue({ cooldown_s: 1e12 })).cooldown_s).toBe(86_400)
  })

  it('a none decision is the frozen default', () => {
    expect(parseCueDecision({ kind: 'none', episode_id: 'ep-1' })).toBe(NONE_DECISION)
  })
})

describe('helpers', () => {
  it('capChars never exceeds the cap', () => {
    for (const s of ['', 'short', 'a'.repeat(200), 'word '.repeat(40)]) expect([...capChars(s.trim(), 20)].length).toBeLessThanOrEqual(20)
  })

  it('pathPhrase is a plain phrase, never a number, and null when unknown', () => {
    expect(pathPhrase(null)).toBeNull()
    expect(pathPhrase(0.78)).toBe('most experts do this next')
    expect(pathPhrase(0.9)).toMatch(/^nearly every expert/)
    expect(pathPhrase(0.05)).toMatch(/^few experts/)
    for (const p of [0, 0.1, 0.3, 0.5, 0.7, 0.9, 1]) expect(pathPhrase(p)).not.toMatch(/\d/)
  })

  it('reasonLine: inline text, else the table, else nothing', () => {
    const base = parseCueDecision(FIXTURES['cue-t2-l2'])
    expect(reasonLine({ ...base, step: { ...base.step!, reason_text: 'Inline.' } })).toBe('Inline.')
    expect(reasonLine({ ...base, step: { ...base.step!, reason_text: null }, texts: { 'why.enter_once': 'From the table.' } })).toBe('From the table.')
    expect(reasonLine({ ...base, step: { ...base.step!, reason_text: null }, texts: {} })).toBeNull()
    expect(reasonLine({ ...base, step: null })).toBeNull()
  })

  it('sameCue: a higher tier is the same cue; another step is a new one', () => {
    const a = parseCueDecision(FIXTURES['cue-t2-l2'])
    expect(sameCue(a, { ...a, tier: 3 })).toBe(true)
    expect(sameCue(a, parseCueDecision(FIXTURES['cue-t2-l1']))).toBe(false)
  })
})

describe('quiet decisions', () => {
  it('a none with an episode keeps the engine reason codes, so Cue can tell a cue is over', () => {
    const d = parseCueDecision({ kind: 'none', episode_id: 'ep-1', why: { reasons: ['step_done', 'Not An Id'] }, tier: 3, say: { chip: 'ignored' } })
    expect(d.kind).toBe('none')
    expect(d.episode_id).toBe('ep-1')
    expect(d.why.reasons).toEqual(['step_done'])
    expect(d.say.chip).toBe('')
    expect(isProgress(d)).toBe(true)
    expect(isProgress(parseCueDecision({ kind: 'none', episode_id: 'ep-1', why: { reasons: ['gate_cooldown'] } }))).toBe(false)
  })
})
