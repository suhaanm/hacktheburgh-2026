import { describe, expect, it } from 'vitest'
import { buildFeedback, FEEDBACK_EVENTS, sanitizeFeedback } from './feedback'
import { FIXTURES } from './fixtures'
import { admit, cueCap, mayWhisper, readCueSettings, type Policy } from './guards'
import { CARD_SIDES, CHIP_SIDES, normBoxToRect, overlapArea, placePanel, type Rect } from './place'
import { CUE_TOKENS } from './tokens'
import { parseCueDecision } from './types'
import { createFakeEngine, createHttpEngine } from './source'
import { createFakeSpeaker, createFakeVoice, matchSpokenOption, nullSpeaker, nullVoice, OTHER_OPTION_ID } from './voice'

const dec = (name: string, patch: Record<string, unknown> = {}) => parseCueDecision({ ...(FIXTURES[name] as object), ...patch })
const POLICY: Policy = { enabled: true, proactivity: 'balanced', quietUntil: null, pausedUntil: null, killed: false, suppressed: null }

describe('settings', () => {
  it('missing keys mean off, balanced, no voice, not quiet', () => {
    expect(readCueSettings({})).toEqual({ cueEnabled: false, cueProactivity: 'balanced', cueVoice: false, cueQuietUntil: null, pausedUntil: null })
    expect(readCueSettings(undefined).cueEnabled).toBe(false)
  })
  it('valid keys are read, invalid ones fall back, and pausedUntil is honoured too', () => {
    const s = readCueSettings({ cueEnabled: true, cueProactivity: 'eager', cueVoice: 'yes', cueQuietUntil: 5, pausedUntil: 9 })
    expect(s).toMatchObject({ cueEnabled: true, cueProactivity: 'eager', cueVoice: false, cueQuietUntil: 5, pausedUntil: 9 })
    expect(readCueSettings({ cueProactivity: 'shouty' }).cueProactivity).toBe('balanced')
  })
})

describe('admit', () => {
  const ctx = (over: Partial<Parameters<typeof admit>[1]> = {}) => ({ now: 1_000_000, policy: POLICY, recent: [], episodeQuestions: 0, continuing: false, ...over })
  it('off, killed, quiet, paused and suppressed refuse everything but say why', () => {
    const d = dec('cue-t2-l2')
    expect(admit(d, ctx({ policy: { ...POLICY, enabled: false } }))).toEqual({ ok: false, reason: 'off' })
    expect(admit(d, ctx({ policy: { ...POLICY, killed: true } }))).toEqual({ ok: false, reason: 'killed' })
    expect(admit(d, ctx({ policy: { ...POLICY, quietUntil: 2_000_000 } }))).toEqual({ ok: false, reason: 'quiet' })
    expect(admit(d, ctx({ policy: { ...POLICY, pausedUntil: 2_000_000 } }))).toEqual({ ok: false, reason: 'quiet' })
    expect(admit(d, ctx({ policy: { ...POLICY, quietUntil: 1 } })).ok).toBe(true)
    expect(admit(d, ctx({ policy: { ...POLICY, suppressed: 'secure input' } }))).toEqual({ ok: false, reason: 'suppressed' })
  })
  it('quiet proactivity: no offers, nothing past tier 2, cap of 2', () => {
    const quiet = { ...POLICY, proactivity: 'quiet' as const }
    expect(admit(dec('offer'), ctx({ policy: quiet }))).toEqual({ ok: false, reason: 'quiet_offer' })
    expect(admit(dec('cue-t3'), ctx({ policy: quiet }))).toEqual({ ok: false, reason: 'quiet_tier' })
    expect(admit(dec('cue-t3', { trigger: 'asked' }), ctx({ policy: quiet })).ok).toBe(true)
    expect(admit(dec('cue-t2-l2'), ctx({ policy: quiet, recent: [999_000, 999_500] }))).toEqual({ ok: false, reason: 'cap' })
  })
  it('the hard cap is 3 in 10 minutes for every proactivity, even eager', () => {
    expect(cueCap('eager')).toBe(3)
    expect(cueCap('balanced')).toBe(3)
    const recent = [900_000, 950_000, 990_000]
    expect(admit(dec('cue-t2-l2'), ctx({ recent, policy: { ...POLICY, proactivity: 'eager' } }))).toEqual({ ok: false, reason: 'cap' })
    expect(admit(dec('cue-t2-l2'), ctx({ recent: [1, 2, 3] })).ok).toBe(true) // all older than ten minutes
  })
  it('a cue that is already on screen growing is not a new interruption', () => {
    expect(admit(dec('cue-t3'), ctx({ recent: [999_000, 999_100, 999_200], continuing: true })).ok).toBe(true)
  })
  it('one question per episode, level 4 only when asked, confirmations always', () => {
    expect(admit(dec('ask-3'), ctx({ episodeQuestions: 1 }))).toEqual({ ok: false, reason: 'one_question' })
    expect(admit(dec('ask-3', { trigger: 'asked' }), ctx({ episodeQuestions: 1 })).ok).toBe(true)
    expect(admit(dec('cue-t2-l2', { why: { level: 4 } }), ctx())).toEqual({ ok: false, reason: 'level4' })
    expect(admit(dec('confirm'), ctx({ recent: [1, 2, 3].map(() => 999_900) })).ok).toBe(true)
  })
})

describe('mayWhisper: nothing speaks by default', () => {
  const ok = { cueVoice: true, buildVoiceOn: true, workerUsedVoice: true, asked: false, typingNow: false, cardUp: false }
  it('every gate is needed', () => {
    expect(mayWhisper(ok)).toBe(true)
    expect(mayWhisper({ ...ok, cueVoice: false })).toBe(false)
    expect(mayWhisper({ ...ok, buildVoiceOn: false })).toBe(false)
    expect(mayWhisper({ ...ok, workerUsedVoice: false })).toBe(false)
    expect(mayWhisper({ ...ok, workerUsedVoice: false, asked: true })).toBe(true)
    expect(mayWhisper({ ...ok, typingNow: true })).toBe(false)
    expect(mayWhisper({ ...ok, cardUp: true })).toBe(false)
  })
  it('the defaults are deaf and silent', async () => {
    expect(await nullVoice.listenOnce([{ id: 'a', label: 'A' }])).toBeNull()
    expect(await nullSpeaker.say('line')).toBeUndefined()
  })
})

describe('feedback carries ids and numbers only', () => {
  it('buildFeedback copies ids, enums and rounded seconds, never a label', () => {
    const e = buildFeedback({ event: 'answered', decision: dec('ask-3'), optionId: 'cliff_a', elapsedMs: 4234 })
    expect(e).toEqual({ event: 'answered', scope: 'cue', episode_id: 'ep-0042', decision_id: null, kind: 'ask', tier: null, step_id: null, option_id: 'cliff_a', how: null, seconds: 4.2, level: 2 })
    expect(JSON.stringify(buildFeedback({ event: 'shown', decision: dec('cue-t2-l2'), elapsedMs: 0 }))).not.toMatch(/calculator|Next:/i)
  })
  it('sanitizeFeedback drops anything unknown and rejects bad events', () => {
    const e = sanitizeFeedback({ ...buildFeedback({ event: 'shown', decision: dec('cue-t2-l2'), elapsedMs: 100 }), label: 'Run calculator A', box: [1, 2, 3, 4], title: 'secret' })!
    expect(Object.keys(e).sort()).toEqual(['decision_id', 'episode_id', 'event', 'how', 'kind', 'level', 'option_id', 'scope', 'seconds', 'step_id', 'tier'])
    expect(sanitizeFeedback({ event: 'exploded' })).toBeNull()
    expect(sanitizeFeedback({ ...e, episode_id: 'has space' })).toBeNull()
    expect(sanitizeFeedback({ ...e, seconds: Number.NaN })).toBeNull()
    expect(sanitizeFeedback({ ...e, seconds: 1e9 })!.seconds).toBe(86_400)
    expect(sanitizeFeedback({ ...e, how: 'because' })!.how).toBeNull()
    expect(sanitizeFeedback({ ...e, event: 'accepted', how: 'show_me' })!.how).toBe('show_me')
    expect(sanitizeFeedback('x')).toBeNull()
  })
  it('the engine accepts exactly these event names', () => {
    expect([...FEEDBACK_EVENTS]).toEqual(['shown', 'accepted', 'dismissed', 'answered', 'resolved', 'abandoned', 'know_this'])
  })
})

describe('voice matcher', () => {
  const options = [
    { id: 'calc_a', label: 'Run calculator A' },
    { id: 'cliff_a', label: 'Check cliff edges (A)' },
    { id: 'write_note', label: 'Copy figures to the note' },
  ]
  it('ordinals, numbers and "the last one"', () => {
    for (const [said, id] of [['the second one', 'cliff_a'], ['number two', 'cliff_a'], ['2', 'cliff_a'], ['first', 'calc_a'], ['the first one please', 'calc_a'], ['number one', 'calc_a'], ['one', 'calc_a'], ['the third', 'write_note'], ['last one', 'write_note'], ['option 3', 'write_note'], ['the 2nd one', 'cliff_a']] as const) {
      expect(matchSpokenOption(said, options), said).toBe(id)
    }
  })
  it('the option\'s own words, even with filler', () => {
    expect(matchSpokenOption('check cliff edges', options)).toBe('cliff_a')
    expect(matchSpokenOption("um I think it's copy the figures", options)).toBe('write_note')
    expect(matchSpokenOption('calculator', options)).toBe('calc_a')
  })
  it('something else, silence, nonsense and ambiguity never guess', () => {
    expect(matchSpokenOption('something else', options)).toBe(OTHER_OPTION_ID)
    expect(matchSpokenOption('none of those', options)).toBe(OTHER_OPTION_ID)
    expect(matchSpokenOption('', options)).toBeNull()
    expect(matchSpokenOption('banana', options)).toBeNull()
    expect(matchSpokenOption('the fifth one', options)).toBeNull()
    expect(matchSpokenOption('A', options)).toBeNull() // "a" is filler: nothing to match
    const twins = [{ id: 'a', label: 'Run calculator' }, { id: 'b', label: 'Run calculator' }]
    expect(matchSpokenOption('run calculator', twins)).toBeNull()
  })
  it('the fake voice plays a script through the matcher, and the fake speaker records ids', async () => {
    const v = createFakeVoice(['the second one', null, 'banana'])
    expect(await v.listenOnce(options)).toBe('cliff_a')
    expect(await v.listenOnce(options)).toBeNull()
    expect(await v.listenOnce(options)).toBeNull()
    expect(v.calls).toBe(3)
    const s = createFakeSpeaker()
    s.say('line_a')
    expect(s.said).toEqual(['line_a'])
  })
})

describe('placement', () => {
  const work: Rect = { x: 0, y: 25, w: 1440, h: 800 }
  const target: Rect = { x: 500, y: 400, w: 140, h: 46 }
  it('the chip goes below the target by default, the card to its right; neither covers it', () => {
    const chip = placePanel({ w: 220, h: 30 }, target, work, { prefer: CHIP_SIDES })
    expect(chip.side).toBe('below')
    const card = placePanel({ w: 280, h: 200 }, target, work, { prefer: CARD_SIDES, gap: CUE_TOKENS.card.gap })
    expect(card.side).toBe('right')
    for (const r of [chip.rect, card.rect]) expect(overlapArea(r, target)).toBe(0)
  })
  it('always inside the work area with the margin, whatever the target', () => {
    const margin = CUE_TOKENS.placement.margin
    for (const t of [{ x: 0, y: 25, w: 60, h: 30 }, { x: 1380, y: 790, w: 60, h: 30 }, { x: 700, y: 25, w: 100, h: 30 }, { x: 0, y: 400, w: 1440, h: 60 }]) {
      for (const prefer of [CHIP_SIDES, CARD_SIDES]) {
        const { rect } = placePanel({ w: 280, h: 200 }, t, work, { prefer })
        expect(rect.x).toBeGreaterThanOrEqual(work.x + margin - 0.01)
        expect(rect.y).toBeGreaterThanOrEqual(work.y + margin - 0.01)
        expect(rect.x + rect.w).toBeLessThanOrEqual(work.x + work.w - margin + 0.01)
        expect(rect.y + rect.h).toBeLessThanOrEqual(work.y + work.h - margin + 0.01)
      }
    }
  })
  it('never over the target even when the target is wide: it goes above or below', () => {
    const wide: Rect = { x: 14, y: 300, w: 1412, h: 120 }
    const { rect } = placePanel({ w: 280, h: 200 }, wide, work, { prefer: CARD_SIDES })
    expect(overlapArea(rect, wide)).toBe(0)
  })
  it('the narrowest window (390 wide): the card still fits inside it', () => {
    const phone: Rect = { x: 0, y: 24, w: 390, h: 800 }
    const t: Rect = { x: 40, y: 300, w: 300, h: 44 }
    const { rect } = placePanel({ w: 280, h: 210 }, t, phone, { prefer: CARD_SIDES })
    expect(rect.x).toBeGreaterThanOrEqual(14)
    expect(rect.x + rect.w).toBeLessThanOrEqual(390 - 14)
    expect(overlapArea(rect, t)).toBe(0)
  })
  it('with no target it sits near the point, or in the bottom-right corner above the Dock', () => {
    const near = placePanel({ w: 280, h: 200 }, null, work, { anchorPoint: { x: 400, y: 300 } })
    expect(near.side).toBe('near')
    expect(near.rect.x).toBeGreaterThan(400)
    const corner = placePanel({ w: 280, h: 200 }, null, work)
    expect(corner.side).toBe('corner')
    expect(corner.rect.x + corner.rect.w).toBe(work.x + work.w - CUE_TOKENS.placement.margin)
    expect(corner.rect.y + corner.rect.h).toBe(work.y + work.h - CUE_TOKENS.placement.margin)
  })
  it('keeps clear of other rects and maps norm boxes through the display', () => {
    const ghost: Rect = { x: 650, y: 380, w: 80, h: 80 }
    const { rect } = placePanel({ w: 220, h: 30 }, target, work, { prefer: ['right', 'below'], avoid: [ghost] })
    expect(overlapArea(rect, ghost)).toBe(0)
    expect(normBoxToRect({ xmin: 500, ymin: 250, xmax: 750, ymax: 500 }, { x: 100, y: 0, w: 1000, h: 800 })).toEqual({ x: 600, y: 200, w: 250, h: 200 })
  })
})

describe('engine port', () => {
  it('the fake plays the script and then says nothing, and records feedback and polls', async () => {
    const e = createFakeEngine([FIXTURES['cue-t2-l2']])
    expect(await e.next({ asked: true })).toBe(FIXTURES['cue-t2-l2'])
    expect(await e.next()).toBeNull()
    expect(e.polls[0]).toEqual({ asked: true })
    await e.feedback(buildFeedback({ event: 'shown', decision: dec('cue-t2-l2'), elapsedMs: 0 }))
    expect(e.sent).toHaveLength(1)
  })
  it('the http port only talks to loopback, sends the poll flags, and posts sanitised feedback', async () => {
    const calls: Array<{ url: string; body?: string }> = []
    const fetchImpl = (async (url: string, init?: { body?: string }) => {
      calls.push({ url, body: init?.body })
      return { ok: true, json: async () => ({ data: { kind: 'none' } }) }
    }) as unknown as typeof fetch
    const port = createHttpEngine({ baseUrl: 'http://127.0.0.1:7700', person: () => 'p1', fetchImpl })
    await port.next({ asked: true, voiceOk: false, proactivity: 'quiet', denied: true, quietS: 3.26 })
    expect(calls[0].url).toBe('http://127.0.0.1:7700/cue/next?person=p1&voice_ok=0&asked=1&proactivity=quiet&denied=1&quiet_s=3.3')
    await port.feedback({ ...buildFeedback({ event: 'shown', decision: dec('cue-t2-l2'), elapsedMs: 0 }), label: 'leak' } as never)
    expect(calls[1].url).toBe('http://127.0.0.1:7700/cue/feedback')
    expect(calls[1].body).not.toMatch(/leak|label/)
    const remote = createHttpEngine({ baseUrl: 'https://example.com', person: () => null, fetchImpl })
    expect(await remote.next()).toBeNull()
    await remote.feedback(buildFeedback({ event: 'shown', decision: dec('cue-t2-l2'), elapsedMs: 0 }))
    expect(calls).toHaveLength(2)
  })
  it('a failing engine is silence, never an exception', async () => {
    const fetchImpl = (async () => {
      throw new Error('down')
    }) as unknown as typeof fetch
    const port = createHttpEngine({ baseUrl: 'http://127.0.0.1:7700', person: () => null, fetchImpl })
    expect(await port.next()).toBeNull()
    await expect(port.feedback(buildFeedback({ event: 'shown', decision: dec('cue-t2-l2'), elapsedMs: 0 }))).resolves.toBeUndefined()
  })
})
