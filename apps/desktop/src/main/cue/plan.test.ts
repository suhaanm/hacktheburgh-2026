import { describe, expect, it } from 'vitest'
import { FIXTURES } from './fixtures'
import { allMarkIds, buildMarks, markIds, planCue } from './plan'
import { CUE_TOKENS, levelTokens } from './tokens'
import { parseCueDecision, type CueDecision } from './types'

const d = (name: string, patch: Record<string, unknown> = {}): CueDecision => parseCueDecision({ ...(FIXTURES[name] as object), ...patch })
const whyAt = (level: number, extra: Record<string, unknown> = {}) => ({ why: { ...(FIXTURES['cue-t2-l2'] as { why: object }).why, level, ...extra } })

describe('planCue: tiers', () => {
  it('none and unknown plans show nothing', () => {
    expect(planCue(parseCueDecision(FIXTURES['none']), { stepN: null })).toBeNull()
  })

  it('tier 1 at level 3: a light ring and nothing else', () => {
    const p = planCue(d('cue-t1-l3'), { stepN: 2 })!
    expect(p.ring?.weight).toBe('light')
    expect(p.chip).toBeNull()
    expect(p.ghost).toBeNull()
    expect(p.whisper).toBeNull()
  })

  it('tier 2 at level 2: a regular ring and one chip, no pill', () => {
    const p = planCue(d('cue-t2-l2'), { stepN: 2 })!
    expect(p.ring?.weight).toBe('regular')
    expect(p.chip?.text).toBe('Next: Run calculator A')
    expect(p.chip?.stepN).toBeNull()
  })

  it('tier 2 at level 1: ring, chip and the step pill (the engine numbering wins over the count)', () => {
    const p = planCue(d('cue-t2-l1'), { stepN: 9 })!
    expect(p.chip?.stepN).toBe(3)
    expect(planCue(d('cue-t2-l1', { step: { id: 'cliff_a', label: 'Check cliff edges (A)', reason_id: 'why.cliff' } }), { stepN: 9 })!.chip?.stepN).toBe(9)
  })

  it('tier 2 at level 3 shows no chip (lighter as the level rises); tier 3 brings the chip back', () => {
    const t2l3 = planCue(d('cue-t2-l2', whyAt(3)), { stepN: 1 })!
    expect(t2l3.chip).toBeNull()
    expect(t2l3.ring?.weight).toBe('light')
    const t3l3 = planCue(d('cue-t3', whyAt(3)), { stepN: 1 })!
    expect(t3l3.chip).not.toBeNull()
    expect(t3l3.ring?.weight).toBe('regular')
  })

  it('tier 3 adds the ghost cursor, aimed at the middle of the box; so does a request for it at any tier', () => {
    const t3 = planCue(d('cue-t3'), { stepN: 1 })!
    expect(t3.ghost).not.toBeNull()
    const box = t3.ring!.box
    expect(t3.ghost!.to).toEqual({ x: (box.xmin + box.xmax) / 2, y: (box.ymin + box.ymax) / 2 })
    expect(planCue(d('cue-t2-l2'), { stepN: 1 })!.ghost).toBeNull()
    expect(planCue(d('cue-t2-l2'), { stepN: 1, ghostRequested: true })!.ghost).not.toBeNull()
  })

  it('tier 4 carries the whisper, as a fixed line id: the engine\'s own when it has the right form, else whisper.<step id>; never free text', () => {
    expect(planCue(d('cue-t4'), { stepN: 1 })!.whisper).toEqual({ lineId: 'whisper.write_note', text: 'Next, copy the figures across.' })
    const derived = planCue(d('cue-t4', { say: { chip: 'Next: x', whisper: 'Next, copy the figures across.', whisper_id: 'a sentence, not an id' } }), { stepN: 1 })!
    expect(derived.whisper?.lineId).toBe('whisper.write_note')
    expect(planCue(d('cue-t4', { say: { chip: 'Next: x', whisper: 'Next, copy the figures across.' } }), { stepN: 1 })!.whisper?.lineId).toBe('whisper.write_note')
    // No step and no usable id: nothing to speak.
    expect(planCue(d('cue-t4', { step: null, say: { chip: 'Next: x', whisper: 'Next, copy the figures across.' } }), { stepN: 1 })!.whisper).toBeNull()
    // No whisper words: nothing to speak.
    expect(planCue(d('cue-t4', { say: { chip: 'Next: x', whisper: null } }), { stepN: 1 })!.whisper).toBeNull()
  })

  it('a worker who asked is treated as at least level 2: the answer is not withheld', () => {
    const p = planCue(d('cue-t2-l2', { trigger: 'asked', ...whyAt(4) }), { stepN: 1 })!
    expect(p.chip).not.toBeNull()
    expect(levelTokens(4, true)).toBe(CUE_TOKENS.levels[2])
    expect(levelTokens(4, false)).toBe(CUE_TOKENS.levels[4])
    expect(levelTokens(null, false)).toBe(CUE_TOKENS.levels[2])
  })

  it('a cue with no box to ring stands alone as a chip whatever the level says', () => {
    const p = planCue(d('cue-no-target', whyAt(3)), { stepN: 1 })!
    expect(p.ring).toBeNull()
    expect(p.chip?.text).toBe('Next: Run calculator A')
    expect(p.anchor).toBeNull()
  })

  it('a box the engine is not sure of is not drawn as a ring', () => {
    const p = planCue(d('cue-t2-l2', { target: { box_2d: [100, 100, 200, 300], source: 'vision', confidence: 0.3 } }), { stepN: 1 })!
    expect(p.ring).toBeNull()
    expect(p.chip).not.toBeNull()
  })

  it('levels get lighter as the number rises: ring weight and chip tier only ever step one way', () => {
    const order = [1, 2, 3, 4].map((l) => CUE_TOKENS.levels[l as 1 | 2 | 3 | 4])
    for (let i = 1; i < order.length; i++) {
      expect(order[i].chipFromTier).toBeGreaterThanOrEqual(order[i - 1].chipFromTier)
      expect(Number(order[i].stepPill)).toBeLessThanOrEqual(Number(order[i - 1].stepPill))
    }
    expect(CUE_TOKENS.levels[1].ringWhenQuiet).toBe('regular')
    expect(CUE_TOKENS.levels[3].ringWhenQuiet).toBe('light')
  })
})

describe('planCue: other kinds', () => {
  it('confirm is a silent tick on the step: no chip, no words', () => {
    const p = planCue(d('confirm'), { stepN: 1 })!
    expect(p.tick).not.toBeNull()
    expect(p.chip).toBeNull()
    expect(p.ring).toBeNull()
    expect(buildMarks(p, 1).map((m) => m.kind)).toEqual(['tick'])
  })

  it('ask: the engine question text, up to four numbered options, a target to keep clear of but no ring', () => {
    const p = planCue(d('ask-4'), { stepN: null })!
    expect(p.question?.text).toBe('I cannot tell where you are. What is next?')
    expect(p.question?.options.map((o) => o.key)).toEqual(['1', '2', '3', '4'])
    expect(p.ring).toBeNull()
    expect(planCue(d('ask-3'), { stepN: null })!.anchor).not.toBeNull()
    expect(planCue(d('ask-4'), { stepN: null })!.anchor).toBeNull()
  })

  it('ask without any question text falls back to a fixed line, never to nothing', () => {
    const p = planCue(d('ask-2', { question: null }), { stepN: null })!
    expect(p.question?.text).toBe('What are you trying to do?')
  })

  it('offer is a small card with the engine words', () => {
    expect(planCue(d('offer'), { stepN: null })!.offer?.text).toBe('Want a hand?')
  })

  it('the why popover has the reason and the plain phrase, flags simulated experts, and is null when there is nothing to say', () => {
    const p = planCue(d('cue-t2-l2'), { stepN: 1 })!
    expect(p.why).toEqual({ reason: 'Copy the household from the record; retyping invites mistakes.', phrase: 'most experts do this next', simulated: true })
    const bare = planCue(d('cue-t2-l2', { step: { id: 'calc_a', label: 'Run calculator A' }, why: { level: 2 } }), { stepN: 1 })!
    expect(bare.why).toBeNull()
  })
})

describe('buildMarks', () => {
  it('a ring with the weight field, the overlay ids with the Cue prefix, and a guard ttl', () => {
    const marks = buildMarks(planCue(d('cue-t1-l3'), { stepN: 1 })!, 7)
    expect(marks).toHaveLength(1)
    const ring = marks[0] as { id: string; kind: string; weight: string; ttlMs: number; exact: boolean; step?: number; label?: string; note?: string }
    expect(ring.id).toBe('cue-ring-7')
    expect(ring.weight).toBe('light')
    expect(ring.exact).toBe(true)
    expect(ring.ttlMs).toBeGreaterThan(CUE_TOKENS.timing.untouchedMs)
    // The ring carries no words: the chip is the panel's, so it can be tapped.
    expect(ring.step).toBeUndefined()
    expect(ring.label).toBeUndefined()
    expect(ring.note).toBeUndefined()
  })

  it('tier 3 adds a one-point ghost cursor that ends with the press echo (a picture, never a click)', () => {
    const marks = buildMarks(planCue(d('cue-t3'), { stepN: 1 })!, 2)
    const ghost = marks.find((m) => m.kind === 'ghostCursor') as { path: unknown[]; pressAtEnd: boolean; id: string }
    expect(ghost.id).toBe('cue-ghost-2')
    expect(ghost.path).toHaveLength(1)
    expect(ghost.pressAtEnd).toBe(true)
    expect(buildMarks(planCue(d('cue-t3'), { stepN: 1 })!, 2, { ghost: false }).some((m) => m.kind === 'ghostCursor')).toBe(false)
  })

  it('vision-grounded boxes are not drawn "exact" (the overlay caps them to a pointer size)', () => {
    const p = planCue(d('cue-t2-l2', { target: { box_2d: [100, 100, 200, 300], source: 'vision', confidence: 0.9 } }), { stepN: 1 })!
    expect((buildMarks(p, 1)[0] as { exact: boolean }).exact).toBe(false)
  })

  it('every id belongs to Cue and clearing covers all of them', () => {
    for (const id of allMarkIds(3)) expect(id.startsWith(CUE_TOKENS.idPrefix)).toBe(true)
    expect(Object.values(markIds(3))).toEqual(allMarkIds(3))
  })
})
