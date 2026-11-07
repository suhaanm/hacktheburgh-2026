// ONE poll, two readers: the coach brain's GET /coach/next carries p_stuck, and the awareness layer's stuck trigger reads it from the
// decision (onDecision) instead of polling the engine itself.
import { describe, expect, it } from 'vitest'
import { createCoachBrain } from './coach-brain'
import { parseCoachNext, pStuckForTrigger, type CoachDecision } from './engine/coach-next'

const body = (over: Record<string, unknown> = {}) => ({ meta: {}, data: { action: 'silent', message: '', why: '', reason_codes: ['on_track'], ...over } })

describe('p_stuck in the coach decision', () => {
  it('is read when finite and in 0..1, else null', () => {
    expect(parseCoachNext(body({ p_stuck: 0.82 }))?.pStuck).toBe(0.82)
    expect(parseCoachNext(body({ p_stuck: 0 }))?.pStuck).toBe(0)
    expect(parseCoachNext(body({ p_stuck: 1 }))?.pStuck).toBe(1)
    for (const bad of [-0.01, 1.01, NaN, Infinity, '0.5', null, undefined, {}, [0.5]]) expect(parseCoachNext(body({ p_stuck: bad }))?.pStuck, String(bad)).toBeNull()
    expect(parseCoachNext(body())?.pStuck).toBeNull()
  })

  it('also reads it from an unwrapped body', () => {
    expect(parseCoachNext({ action: 'silent', p_stuck: 0.4 })?.pStuck).toBe(0.4)
  })

  it('pStuckForTrigger gives no reading when the engine has no episode to score', () => {
    expect(pStuckForTrigger({ pStuck: 0.9, reasons: ['on_track'] })).toBe(0.9)
    expect(pStuckForTrigger({ pStuck: null, reasons: [] })).toBeNull()
    for (const r of ['no_events', 'no_pack', 'no_active_task', 'study_mode', 'study_post_test', 'study_off']) expect(pStuckForTrigger({ pStuck: 0.9, reasons: ['on_track', r] }), r).toBeNull()
  })
})

describe('coach brain onDecision', () => {
  const decision = (over: Partial<CoachDecision> = {}): CoachDecision => ({ action: 'silent', message: '', why: '', target: null, level: null, chip: null, decisionId: null, reasons: [], step: null, missed: [], pStuck: 0.77, ...over })
  const rig = (answer: () => CoachDecision | null, onDecision?: (d: CoachDecision) => void) =>
    createCoachBrain({
      engine: { coachNext: async () => answer(), coachFeedback: async () => ({ ok: true, recorded: true, note: null }) },
      state: () => ({ task: { step: 1, stepsTotal: 3 } as never, level: 2, chip: 'full', message: '' }) as never,
      ring: { point: () => undefined, clear: () => undefined, followed: () => undefined, current: () => null },
      onDecision,
      immediate: false,
      setTimer: () => 0,
      clearTimer: () => undefined,
    })

  it('is called once per answered poll with the decision, and the status keeps p_stuck', async () => {
    const seen: CoachDecision[] = []
    const b = rig(() => decision(), (d) => void seen.push(d))
    await b.tick()
    await b.tick()
    expect(seen).toHaveLength(2)
    expect(seen[0]!.pStuck).toBe(0.77)
    expect(b.status().lastDecision?.pStuck).toBe(0.77)
  })

  it('is not called when the engine did not answer, and is not called with no task in progress', async () => {
    const seen: CoachDecision[] = []
    const b = rig(() => null, (d) => void seen.push(d))
    await b.tick()
    expect(seen).toHaveLength(0)
    const idle = createCoachBrain({ engine: { coachNext: async () => decision(), coachFeedback: async () => ({ ok: true, recorded: true, note: null }) }, state: () => null, ring: { point: () => undefined, clear: () => undefined, followed: () => undefined, current: () => null }, onDecision: (d) => void seen.push(d), immediate: false, setTimer: () => 0, clearTimer: () => undefined })
    await idle.tick()
    expect(seen).toHaveLength(0)
  })

  it('a throwing listener never stops the brain acting on the decision', async () => {
    const calls: unknown[] = []
    const b = createCoachBrain({
      engine: { coachNext: async () => decision({ action: 'annotate', target: { zone: 'calc_result' } as never, decisionId: 'd_9', message: 'Check.' }), coachFeedback: async () => ({ ok: true, recorded: true, note: null }) },
      state: () => ({ task: { step: 1, stepsTotal: 3 } as never, level: 2, chip: 'full', message: '' }) as never,
      ring: { point: (...a: unknown[]) => void calls.push(a), clear: () => undefined, followed: () => undefined, current: () => null },
      onDecision: () => {
        throw new Error('listener failed')
      },
      immediate: false,
      setTimer: () => 0,
      clearTimer: () => undefined,
    })
    await b.tick()
    expect(calls).toHaveLength(1)
  })
})
