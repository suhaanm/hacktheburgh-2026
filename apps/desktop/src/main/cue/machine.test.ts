import { describe, expect, it } from 'vitest'
import type { CueFeedbackEvent } from './feedback'
import { FIXTURES } from './fixtures'
import type { Policy } from './guards'
import { INITIAL_MACHINE, nextDeadline, reduce, type Effect, type Env, type MachineEvent, type MachineState } from './machine'
import { CUE_TOKENS } from './tokens'
import { parseCueDecision, type CueDecision } from './types'

const T = CUE_TOKENS.timing
const POLICY: Policy = { enabled: true, proactivity: 'balanced', quietUntil: null, pausedUntil: null, killed: false, suppressed: null }
const dec = (name: string, patch: Record<string, unknown> = {}): CueDecision => parseCueDecision({ ...(FIXTURES[name] as object), ...patch })

// A tiny driver: feeds events with a clock and keeps every effect.
function rig(policy: Partial<Policy> = {}) {
  let state: MachineState = INITIAL_MACHINE
  let now = 1_000_000
  const log: Effect[] = []
  const send = (ev: MachineEvent, at?: number): Effect[] => {
    if (at !== undefined) now = at
    const env: Env = { now, policy: { ...POLICY, ...policy }, chord: '⌥' }
    const r = reduce(state, ev, env)
    state = r.state
    log.push(...r.effects)
    return r.effects
  }
  const advance = (ms: number): void => void (now += ms)
  const fb = (effects: Effect[] = log): CueFeedbackEvent[] => effects.filter((e): e is Extract<Effect, { type: 'feedback' }> => e.type === 'feedback').map((e) => e.event)
  return { send, advance, fb, log, get state() { return state }, get now() { return now }, set now(v: number) { now = v } }
}

const overlay = (effects: Effect[]) => effects.filter((e): e is Extract<Effect, { type: 'overlay' }> => e.type === 'overlay')
const panel = (effects: Effect[]) => effects.filter((e): e is Extract<Effect, { type: 'panel' }> => e.type === 'panel')

describe('showing a cue', () => {
  it('a cue shows the ring and the panel together, reports shown once, and counts against the caps', () => {
    const r = rig()
    const fx = r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    expect(overlay(fx)[0].show.map((m) => m.kind)).toEqual(['ring'])
    expect(panel(fx)[0].view).toMatchObject({ mode: 'chip', text: 'Next: Run calculator A' })
    expect(r.fb(fx).map((e) => e.event)).toEqual(['shown'])
    expect(r.state.recent).toHaveLength(1)
    expect(r.state.visible?.seq).toBe(1)
  })

  it('the same decision again (the engine says persisting) changes nothing', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'decision', decision: dec('cue-t2-l2', { new: false }) }, r.now + 1500)
    expect(fx).toEqual([])
    expect(r.state.visible?.seq).toBe(1)
  })

  it('at most one cue is visible: a new cue replaces the old in ONE overlay effect (the cross-fade) and the old one is reported superseded', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'decision', decision: dec('cue-t2-l1', { episode_id: 'ep-0099' }) }, r.now + 3000)
    const ov = overlay(fx)
    expect(ov).toHaveLength(1)
    expect(ov[0].clear).toEqual(['cue-ring-1', 'cue-tick-1', 'cue-ghost-1'])
    expect(ov[0].show.map((m) => m.id)).toEqual(['cue-ring-2'])
    expect(r.state.visible?.seq).toBe(2)
    expect(r.fb(fx).map((e) => `${e.event}:${e.how ?? ''}`)).toContain('abandoned:superseded')
  })

  it('a new step in the same episode means the old step was done: accepted, not rejected', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'decision', decision: dec('cue-t2-l1') }, r.now + 4000)
    const events = r.fb(fx)
    expect(events[0]).toMatchObject({ event: 'accepted', how: 'progress', step_id: 'calc_a', seconds: 4 })
    expect(events[1]).toMatchObject({ event: 'shown', step_id: 'cliff_a' })
    expect(r.state.episode?.stepsDone).toBe(1)
  })

  it('a higher tier of the same cue grows in place: same ring id, ghost added, no new entrance, no second shown', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'decision', decision: dec('cue-t3', { step: (FIXTURES['cue-t2-l2'] as { step: object }).step, target: (FIXTURES['cue-t2-l2'] as { target: object }).target }) }, r.now + 12_000)
    expect(r.fb(fx)).toEqual([])
    const ov = overlay(fx)
    expect(ov).toHaveLength(1)
    expect(ov[0].clear).toEqual([])
    expect(ov[0].show.map((m) => m.id)).toContain('cue-ghost-1')
    expect(r.state.visible?.seq).toBe(1)
    expect(r.state.recent).toHaveLength(1)
  })

  it('a decision for a cue the worker already saw end is never drawn again', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    r.send({ type: 'dismiss', how: 'esc' })
    const fx = r.send({ type: 'decision', decision: dec('cue-t2-l2') }, r.now + 120_000)
    expect(fx).toEqual([])
    expect(r.state.visible).toBeNull()
  })

  it('a silent confirmation shows a tick only and does not count against the caps', () => {
    const r = rig()
    const fx = r.send({ type: 'decision', decision: dec('confirm') })
    expect(overlay(fx)[0].show.map((m) => m.kind)).toEqual(['tick'])
    expect(panel(fx)[0].view).toBeNull()
    expect(r.state.recent).toHaveLength(0)
  })
})

describe('ending a cue', () => {
  it('Escape: dismissed, marks and panel gone, keys released, and the same cue is not redrawn', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'dismiss', how: 'esc' }, r.now + 2500)
    expect(r.fb(fx)).toEqual([expect.objectContaining({ event: 'dismissed', how: 'esc', seconds: 2.5 })])
    expect(overlay(fx)[0].clear).toContain('cue-ring-1')
    expect(panel(fx)[0].view).toBeNull()
    expect(fx).toContainEqual({ type: 'keys', on: false, options: 0 })
    expect(r.state.visible).toBeNull()
  })

  it('progress on its step within 10 s is accepted; later it is accepted late', () => {
    const a = rig()
    a.send({ type: 'decision', decision: dec('cue-t2-l2') })
    expect(a.fb(a.send({ type: 'progress', stepId: 'calc_a' }, a.now + 6000))[0]).toMatchObject({ event: 'accepted', how: 'progress', seconds: 6 })
    const b = rig()
    b.send({ type: 'decision', decision: dec('cue-t2-l2') })
    expect(b.fb(b.send({ type: 'progress', stepId: 'calc_a' }, b.now + 15_000))[0]).toMatchObject({ event: 'accepted', how: 'late' })
  })

  it('progress on some other step is not the cue being followed', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'progress', stepId: 'write_note' })
    expect(fx).toEqual([])
    expect(r.state.visible).not.toBeNull()
  })

  it('20 seconds untouched: abandoned, and the clock restarts on every touch', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    expect(nextDeadline(r.state)).toBe(r.now + T.untouchedMs)
    r.send({ type: 'touch' }, r.now + 15_000)
    expect(nextDeadline(r.state)).toBe(r.now + T.untouchedMs)
    expect(r.send({ type: 'tick' }, r.now + T.untouchedMs - 1)).toEqual([])
    const fx = r.send({ type: 'tick' }, r.now + 1)
    expect(r.fb(fx)).toEqual([expect.objectContaining({ event: 'abandoned', how: 'timeout' })])
    expect(r.state.visible).toBeNull()
  })

  it('the engine display limit can only shorten the life', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2', { expires_in_s: 12 }) })
    expect(nextDeadline(r.state)).toBe(r.now + 12_000)
    const long = rig()
    long.send({ type: 'decision', decision: dec('cue-t2-l2', { expires_in_s: 120 }) })
    expect(nextDeadline(long.state)).toBe(long.now + T.untouchedMs)
  })

  it('any quiet answer from the engine takes the cue down, and its reason says how it ended', () => {
    const cases: Array<[string, string, string]> = [
      ['progress', 'accepted', 'progress'],
      ['recovered', 'accepted', 'progress'],
      ['timeout', 'abandoned', 'timeout'],
      ['waiting_escalation', 'abandoned', 'timeout'],
      ['quiet', 'abandoned', 'quiet'],
      ['denied', 'abandoned', 'off'],
      ['flow', 'abandoned', 'superseded'],
    ]
    for (const [reason, event, how] of cases) {
      const r = rig()
      r.send({ type: 'decision', decision: dec('cue-t2-l2') })
      const fx = r.send({ type: 'decision', decision: parseCueDecision({ kind: 'none', episode_id: 'ep-0042', why: { reasons: [reason] } }) }, r.now + 3000)
      expect(r.fb(fx)[0], reason).toMatchObject({ event, how })
      expect(r.state.visible, reason).toBeNull()
      expect(overlay(fx)[0].clear, reason).toContain('cue-ring-1')
    }
  })

  it('a bare none (no episode, no reasons) also takes the cue down', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    r.send({ type: 'decision', decision: parseCueDecision({ kind: 'none' }) }, r.now + 3000)
    expect(r.state.visible).toBeNull()
  })

  it('but a none does not cut the silent confirmation tick short', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('confirm') })
    r.send({ type: 'decision', decision: parseCueDecision({ kind: 'none', episode_id: 'ep-0042', why: { reasons: ['not_stuck'] } }) }, r.now + 1500)
    expect(r.state.visible).not.toBeNull()
    r.send({ type: 'tick' }, r.now + T.confirmMs)
    expect(r.state.visible).toBeNull()
  })

  it('progress that closes the episode reports resolved once, with the episode age', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'decision', decision: parseCueDecision({ kind: 'none', episode_id: 'ep-0042', why: { reasons: ['progress'] } }) }, r.now + 8000)
    const resolved = r.fb(fx).filter((e) => e.event === 'resolved')
    expect(resolved).toHaveLength(1)
    expect(resolved[0]).toMatchObject({ scope: 'episode', seconds: 8 })
    expect(r.state.episode).toBeNull()
  })

  it('a new episode closes the old one: abandoned when nothing progressed', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'decision', decision: dec('cue-t2-l1', { episode_id: 'ep-0100' }) }, r.now + 30_000)
    expect(r.fb(fx).some((e) => e.event === 'abandoned' && e.scope === 'episode' && e.episode_id === 'ep-0042')).toBe(true)
  })

  it('stop: the kill switch clears everything and says nothing; off or quiet reports abandoned', () => {
    const a = rig()
    a.send({ type: 'decision', decision: dec('cue-t2-l2') })
    expect(a.fb(a.send({ type: 'stop', how: 'killed' }))).toEqual([])
    expect(a.state.visible).toBeNull()
    const b = rig()
    b.send({ type: 'decision', decision: dec('cue-t2-l2') })
    expect(b.fb(b.send({ type: 'stop', how: 'quiet' }))[0]).toMatchObject({ event: 'abandoned', how: 'quiet' })
  })
})

describe('a stale target', () => {
  it('the ring goes at once and is re-grounded; found again it returns, not found it is dropped as stale', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'stale' }, r.now + 3000)
    expect(overlay(fx)[0].clear).toContain('cue-ring-1')
    // The chip goes with the ring: it would be pointing at nothing.
    expect(panel(fx)[0].view).toBeNull()
    expect(fx.some((e) => e.type === 'reground')).toBe(true)
    expect(nextDeadline(r.state)).toBe(r.now + T.regroundMs)

    const found = r.send({ type: 'retarget', box: [300, 300, 360, 420] }, r.now + 500)
    expect(overlay(found)[0].show.map((m) => m.kind)).toEqual(['ring'])
    expect(r.state.visible?.hiddenAt).toBeNull()

    r.send({ type: 'stale' }, r.now + 100)
    r.send({ type: 'tick' }, r.now + T.regroundMs - 1)
    expect(r.state.visible).not.toBeNull()
    const dropped = r.send({ type: 'tick' }, r.now + 1)
    expect(r.fb(dropped)).toEqual([expect.objectContaining({ event: 'abandoned', how: 'stale' })])
    expect(r.state.visible).toBeNull()
  })

  it('a cue with no ring has nothing to go stale', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-no-target') })
    expect(r.send({ type: 'stale' })).toEqual([])
  })
})

describe('the popover and the worker actions', () => {
  it('"Why this?" opens the popover in the chip view and counts as a touch', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'why', open: true }, r.now + 9000)
    expect(panel(fx)[0].view).toMatchObject({ mode: 'chip', open: true, why: { phrase: 'most experts do this next' } })
    expect(nextDeadline(r.state)).toBe(r.now + T.untouchedMs)
  })

  it('"I know this": know_this to the engine, the cue collapses, and the step stays quiet this episode', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'know_this' }, r.now + 3000)
    expect(r.fb(fx)).toEqual([expect.objectContaining({ event: 'know_this', step_id: 'calc_a' })])
    expect(r.state.visible).toBeNull()
    // Even a higher tier of the same step stays quiet.
    expect(r.send({ type: 'decision', decision: dec('cue-t3', { step: (FIXTURES['cue-t2-l2'] as { step: object }).step }) }, r.now + 200_000)).toEqual([])
  })

  it('"Show me" plays the ghost once, at any tier, and is not offered again', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const fx = r.send({ type: 'show_me' })
    expect(overlay(fx)[0].show.map((m) => m.kind)).toContain('ghostCursor')
    expect(panel(fx)[0].view).toMatchObject({ canShowMe: false })
    expect(r.send({ type: 'show_me' })).toEqual([])
  })

  it('a dismissal starts the decision cooldown: no new unprompted cue until it passes, but an asked cue gets through', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    r.send({ type: 'dismiss', how: 'esc' })
    const other = dec('cue-t2-l1', { episode_id: 'ep-0050' })
    expect(r.send({ type: 'decision', decision: other }, r.now + 30_000)).toEqual([])
    expect(r.send({ type: 'decision', decision: { ...other, trigger: 'asked' } }, r.now + 31_000).length).toBeGreaterThan(0)
  })
})

describe('the question card', () => {
  it('shows the card with numbered options, registers the keys, and waits for the voice', () => {
    const r = rig()
    const fx = r.send({ type: 'decision', decision: dec('ask-3') })
    const view = panel(fx)[0].view
    expect(view).toMatchObject({ mode: 'question', question: 'Which of these is next?', chord: '⌥' })
    expect(panel(fx)[0].kind).toBe('card')
    expect(fx).toContainEqual({ type: 'keys', on: true, options: 3 })
    expect(fx.find((e) => e.type === 'listen')).toBeTruthy()
    expect(overlay(fx)[0].show).toEqual([])
  })

  it('answering collapses the card into the chip for the chosen step, reports the option id, and asks the engine again', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('ask-3') })
    const fx = r.send({ type: 'answer', id: 'cliff_a' }, r.now + 4200)
    expect(r.fb(fx)).toEqual([expect.objectContaining({ event: 'answered', option_id: 'cliff_a', seconds: 4.2 })])
    expect(panel(fx)[0].view).toMatchObject({ mode: 'chip', text: 'Check cliff edges (A)', pending: true, from: 'question' })
    // The collapsed chip stays where the card was; it is not an answer about the old target.
    expect(panel(fx)[0].keep).toBe(true)
    expect(fx).toContainEqual({ type: 'keys', on: false, options: 0 })
    expect(fx).toContainEqual({ type: 'poll', asked: false })
    expect(r.state.visible?.pending).toBe(true)
    expect(nextDeadline(r.state)).toBe(r.now + T.answerWaitMs)
  })

  it('the collapsed chip goes without a second label when the wait ends, and is replaced by the engine cue for the step', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('ask-3') })
    r.send({ type: 'answer', id: 'cliff_a' })
    const fx = r.send({ type: 'tick' }, r.now + T.answerWaitMs)
    expect(r.fb(fx)).toEqual([])
    expect(r.state.visible).toBeNull()

    const r2 = rig()
    r2.send({ type: 'decision', decision: dec('ask-3') })
    r2.send({ type: 'answer', id: 'cliff_a' })
    const next = r2.send({ type: 'decision', decision: dec('cue-t2-l1') }, r2.now + 800)
    expect(r2.fb(next).map((e) => e.event)).toEqual(['shown']) // no label for the pending chip
    expect(overlay(next)[0].show.map((m) => m.kind)).toEqual(['ring'])
  })

  it('"something else" is answered with the fixed id, nothing is guessed, and the conversation is the controller\'s to open', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('ask-3') })
    const fx = r.send({ type: 'answer', id: 'other' })
    expect(r.fb(fx)).toEqual([expect.objectContaining({ event: 'answered', option_id: 'other' })])
    expect(fx).toContainEqual({ type: 'converse' })
    expect(r.state.visible).toBeNull()
  })

  it('an option that is not on the card is ignored', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('ask-3') })
    expect(r.send({ type: 'answer', id: 'enter_rent' })).toEqual([])
    expect(r.state.visible?.decision.kind).toBe('ask')
  })

  it('12 seconds of ignoring dismisses the question (ignoring is an answer)', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('ask-3') })
    expect(nextDeadline(r.state)).toBe(r.now + T.questionIgnoreMs)
    const fx = r.send({ type: 'tick' }, r.now + T.questionIgnoreMs)
    expect(r.fb(fx)).toEqual([expect.objectContaining({ event: 'dismissed', how: 'timeout' })])
  })

  it('one question per episode: a second question in the same episode is refused unless asked', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('ask-3') })
    r.send({ type: 'answer', id: 'cliff_a' })
    r.send({ type: 'tick' }, r.now + T.answerWaitMs)
    const again = dec('ask-2')
    expect(r.send({ type: 'decision', decision: again }, r.now + 2000)).toEqual([])
    expect(r.send({ type: 'decision', decision: { ...again, trigger: 'asked' } }, r.now + 3000).length).toBeGreaterThan(0)
  })

  it('an offer: yes asks the engine straight away as asked; not now is dismissed as declined', () => {
    const yes = rig()
    yes.send({ type: 'decision', decision: dec('offer') })
    const fx = yes.send({ type: 'offer', yes: true })
    expect(yes.fb(fx)).toEqual([expect.objectContaining({ event: 'accepted', how: 'accepted_offer' })])
    expect(fx).toContainEqual({ type: 'poll', asked: true })
    const no = rig()
    no.send({ type: 'decision', decision: dec('offer') })
    expect(no.fb(no.send({ type: 'offer', yes: false }))).toEqual([expect.objectContaining({ event: 'dismissed', how: 'declined' })])
  })
})

describe('policy', () => {
  it('off, killed, quiet and suppressed show nothing and take down what is up', () => {
    for (const patch of [{ enabled: false }, { killed: true }, { quietUntil: 9e12 }, { suppressed: 'denylisted app' }] as Partial<Policy>[]) {
      const r = rig(patch)
      expect(r.send({ type: 'decision', decision: dec('cue-t2-l2') }), JSON.stringify(patch)).toEqual([])
    }
    const r = rig()
    r.send({ type: 'decision', decision: dec('cue-t2-l2') })
    const off = reduce(r.state, { type: 'decision', decision: dec('cue-t2-l2', { new: false }) }, { now: r.now + 1000, policy: { ...POLICY, killed: true } })
    expect(off.state.visible).toBeNull()
  })

  it('the cap: no fourth cue inside ten minutes, a cue the worker asked for excepted', () => {
    const r = rig()
    for (let i = 0; i < 3; i++) {
      r.send({ type: 'decision', decision: dec('cue-t2-l2', { episode_id: `ep-${i}` }) }, 1_000_000 + i * 60_000)
      r.send({ type: 'progress', stepId: 'calc_a' })
    }
    expect(r.state.recent).toHaveLength(3)
    const fourth = dec('cue-t2-l2', { episode_id: 'ep-9' })
    expect(r.send({ type: 'decision', decision: fourth }, 1_000_000 + 4 * 60_000)).toEqual([])
    expect(r.send({ type: 'decision', decision: { ...fourth, trigger: 'asked' } }, 1_000_000 + 4 * 60_000 + 1).length).toBeGreaterThan(0)
    // Ten minutes later the window has passed.
    const later = rig()
    for (let i = 0; i < 3; i++) later.send({ type: 'decision', decision: dec('cue-t2-l2', { episode_id: `ep-${i}` }) }, 1_000_000 + i * 1000)
    expect(later.send({ type: 'decision', decision: dec('cue-t2-l2', { episode_id: 'ep-9' }) }, 1_000_000 + 11 * 60_000).length).toBeGreaterThan(0)
  })

  it('level 4 stays silent unless asked', () => {
    const r = rig()
    const l4 = dec('cue-t2-l2', { why: { level: 4 } })
    expect(r.send({ type: 'decision', decision: l4 })).toEqual([])
    expect(r.send({ type: 'decision', decision: { ...l4, trigger: 'asked' } }).length).toBeGreaterThan(0)
  })

  it('every feedback event the machine emits is ids and numbers only', () => {
    const r = rig()
    r.send({ type: 'decision', decision: dec('ask-3') })
    r.send({ type: 'answer', id: 'cliff_a' })
    r.send({ type: 'decision', decision: dec('cue-t2-l1') })
    r.send({ type: 'why', open: true })
    r.send({ type: 'know_this' })
    for (const e of r.fb()) {
      for (const [k, v] of Object.entries(e)) {
        if (typeof v === 'string') expect(v, k).toMatch(/^[A-Za-z0-9_.:-]{1,80}$/)
        else expect(['number', 'object'].includes(typeof v), k).toBe(true)
      }
      expect(JSON.stringify(e)).not.toMatch(/Run calculator|Next:|Which of these/)
    }
  })
})
