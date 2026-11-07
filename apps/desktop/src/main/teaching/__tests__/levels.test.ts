import { describe, expect, it } from 'vitest'
import type { AttemptRecord, HelpLevel, SkillState } from '../../../shared/protocol'
import {
  DAY_MS,
  HINT_CAP,
  REVIEW_DAYS,
  applyOverride,
  beginStepCounters,
  clampLevel,
  completeStep,
  createLevelEngine,
  decayState,
  detectAnxiety,
  detectOverride,
  evaluateAttempt,
  isCleanAttempt,
  isMastered,
  isReviewDue,
  levelEngine,
  levelLabel,
  nextReviewAt,
  recordSignal,
  startAttemptLevel,
  stepLevelFor,
  stepUpStreak,
} from '../levels'

const NOW = Date.UTC(2026, 9, 31, 14, 0, 0)

function state(level: HelpLevel, streakClean = 0, lastSeen: number | null = null): SkillState {
  return { level, streakClean, lastSeen, nextReview: null }
}

function attempt(over: Partial<AttemptRecord> = {}): AttemptRecord {
  return {
    id: 'a1',
    skillId: 'video_call',
    lessonId: 'l1',
    startedAt: NOW - 60_000,
    endedAt: NOW,
    levelAtStart: 2,
    levelAtEnd: 2,
    completed: true,
    hintsUsed: 0,
    errors: 0,
    stalls: 0,
    safetyFlag: false,
    anxietyPhrase: false,
    teachBackScore: 1,
    confidence: 4,
    clean: true,
    ...over,
  }
}

describe('isCleanAttempt', () => {
  const cases: [string, Partial<AttemptRecord>, boolean][] = [
    ['perfect', {}, true],
    ['not completed', { completed: false }, false],
    ['one error is fine', { errors: 1 }, true],
    ['two errors is not', { errors: 2 }, false],
    ['safety flag', { safetyFlag: true }, false],
    ['L2 allows one hint', { levelAtStart: 2, hintsUsed: 1 }, true],
    ['L2 two hints fails', { levelAtStart: 2, hintsUsed: 2 }, false],
    ['L3 allows two hints', { levelAtStart: 3, hintsUsed: 2 }, true],
    ['L3 three hints fails', { levelAtStart: 3, hintsUsed: 3 }, false],
    ['L4 allows none', { levelAtStart: 4, hintsUsed: 1 }, false],
    ['L4 zero hints', { levelAtStart: 4, hintsUsed: 0 }, true],
    ['L1 hints are not capped', { levelAtStart: 1, hintsUsed: 9 }, true],
  ]
  it.each(cases)('%s', (_name, over, expected) => {
    expect(isCleanAttempt(attempt(over))).toBe(expected)
  })

  it('exposes the same rule on the engine', () => {
    expect(levelEngine.isClean(attempt({ errors: 5 }))).toBe(false)
    expect(HINT_CAP[2]).toBe(1)
  })
})

describe('evaluateAttempt: stepping up', () => {
  it('demo mode: one clean attempt steps up at every level below 4', () => {
    for (const level of [1, 2, 3] as HelpLevel[]) {
      const d = evaluateAttempt(attempt({ levelAtStart: level }), state(level), { demoMode: true, now: NOW })
      expect(d.change).toBe('up')
      expect(d.state.level).toBe(level + 1)
      expect(d.state.streakClean).toBe(0)
      expect(d.state.lastSeen).toBe(NOW)
      expect(d.state.nextReview).toBe(NOW + DAY_MS)
    }
  })

  it('normal mode: L1 needs 1, L2 and L3 need 2 clean attempts', () => {
    const l1 = evaluateAttempt(attempt({ levelAtStart: 1 }), state(1), { demoMode: false, now: NOW })
    expect(l1.change).toBe('up')

    const first = evaluateAttempt(attempt({ levelAtStart: 2 }), state(2), { demoMode: false, now: NOW })
    expect(first.change).toBe('hold')
    expect(first.state.streakClean).toBe(1)
    expect(first.state.nextReview).toBe(NOW + 3 * DAY_MS)
    const second = evaluateAttempt(attempt({ levelAtStart: 2 }), first.state, { demoMode: false, now: NOW })
    expect(second.change).toBe('up')
    expect(second.state).toMatchObject({ level: 3, streakClean: 0 })
  })

  it('level 4 never exceeds 4 and counts as mastered after the streak', () => {
    const first = evaluateAttempt(attempt({ levelAtStart: 4 }), state(4), { demoMode: false, now: NOW })
    expect(first.change).toBe('hold')
    expect(isMastered(first.state, false)).toBe(false)
    const second = evaluateAttempt(attempt({ levelAtStart: 4 }), first.state, { demoMode: false, now: NOW })
    expect(second.state.level).toBe(4)
    expect(isMastered(second.state, false)).toBe(true)
    expect(second.reason).toMatch(/mastered/)
    expect(isMastered(state(4, 1), true)).toBe(true)
    expect(isMastered(state(3, 9), true)).toBe(false)
  })

  it('needs teach-back >= 0.67 to step up (even in demo mode)', () => {
    const weak = evaluateAttempt(attempt({ teachBackScore: 0.5 }), state(2, 1), { demoMode: true, now: NOW })
    expect(weak.change).toBe('hold')
    expect(weak.state.streakClean).toBe(1)
    const edge = evaluateAttempt(attempt({ teachBackScore: 0.67 }), state(2), { demoMode: true, now: NOW })
    expect(edge.change).toBe('up')
  })

  it('a skipped teach-back does not block unless required', () => {
    const skipped = attempt({ teachBackScore: null })
    expect(evaluateAttempt(skipped, state(2), { demoMode: true, now: NOW }).change).toBe('up')
    const strict = evaluateAttempt(skipped, state(2), { demoMode: true, now: NOW, requireTeachBack: true })
    expect(strict.change).toBe('hold')
  })

  it('an anxious but clean attempt holds the level', () => {
    const d = evaluateAttempt(attempt({ anxietyPhrase: true }), state(2, 1), { demoMode: true, now: NOW })
    expect(d.change).toBe('hold')
    expect(d.state.streakClean).toBe(1)
  })
})

describe('evaluateAttempt: holding and stepping down', () => {
  it('a non-clean attempt holds, resets the streak and is reviewed tomorrow', () => {
    const d = evaluateAttempt(attempt({ clean: false, errors: 2 }), state(3, 1), { demoMode: true, now: NOW })
    expect(d.change).toBe('hold')
    expect(d.state).toMatchObject({ level: 3, streakClean: 0, nextReview: NOW + DAY_MS })
  })

  it('two non-clean attempts in a row step down one level', () => {
    const miss = attempt({ clean: false, errors: 3, levelAtEnd: 3, levelAtStart: 3 })
    const d = evaluateAttempt(miss, state(3), { demoMode: true, now: NOW, recentAttempts: [attempt({ clean: true }), miss] })
    expect(d.change).toBe('down')
    expect(d.state.level).toBe(2)
  })

  it('a clean attempt in between breaks the run', () => {
    const miss = attempt({ clean: false, errors: 3 })
    const d = evaluateAttempt(miss, state(3), { demoMode: true, now: NOW, recentAttempts: [miss, attempt({ clean: true })] })
    expect(d.change).toBe('hold')
  })

  it('a miss that already caused a step down starts the count afresh', () => {
    const demoted = attempt({ clean: false, levelAtStart: 3, levelAtEnd: 2 })
    const d = evaluateAttempt(attempt({ clean: false, errors: 3, levelAtStart: 2 }), state(2), {
      demoMode: true,
      now: NOW,
      recentAttempts: [demoted],
    })
    expect(d.change).toBe('hold')
  })

  it('never steps below L1', () => {
    const miss = attempt({ clean: false, errors: 3, levelAtStart: 1 })
    const d = evaluateAttempt(miss, state(1), { demoMode: true, now: NOW, recentAttempts: [miss, miss] })
    expect(d.state.level).toBe(1)
    expect(d.change).toBe('hold')
  })

  it('an abandoned attempt steps down at once', () => {
    const d = evaluateAttempt(attempt({ completed: false, clean: false }), state(3, 1), { demoMode: true, now: NOW })
    expect(d).toMatchObject({ change: 'down', reason: 'attempt abandoned' })
    expect(d.state).toMatchObject({ level: 2, streakClean: 0 })
    const atBottom = evaluateAttempt(attempt({ completed: false, clean: false }), state(1), { demoMode: true, now: NOW })
    expect(atBottom.change).toBe('hold')
  })
})

describe('evaluateAttempt: overrides and locking cost nothing', () => {
  it('"show me again" never changes level or streak', () => {
    const d = evaluateAttempt(attempt({ clean: false, errors: 4 }), state(3, 1), { demoMode: true, now: NOW, override: 'show_again' })
    expect(d.change).toBe('hold')
    expect(d.state).toMatchObject({ level: 3, streakClean: 1 })
  })

  it('"let me try" going badly or abandoned is free', () => {
    const bad = evaluateAttempt(attempt({ clean: false, errors: 4, levelAtStart: 4 }), state(2, 1), {
      demoMode: true,
      now: NOW,
      override: 'let_me_try',
      recentAttempts: [attempt({ clean: false })],
    })
    expect(bad.change).toBe('hold')
    expect(bad.state.level).toBe(2)
    const quit = evaluateAttempt(attempt({ completed: false, clean: false }), state(2), { demoMode: true, now: NOW, override: 'let_me_try' })
    expect(quit.change).toBe('hold')
  })

  it('"let me try" going well still earns a step up', () => {
    const d = evaluateAttempt(attempt({ levelAtStart: 4 }), state(2), { demoMode: true, now: NOW, override: 'let_me_try' })
    expect(d.change).toBe('up')
    expect(d.state.level).toBe(3)
  })

  it('a locked level records the attempt but never moves', () => {
    const d = evaluateAttempt(attempt(), state(2, 1), { demoMode: true, now: NOW, locked: true })
    expect(d.change).toBe('hold')
    expect(d.state).toMatchObject({ level: 2, streakClean: 1, lastSeen: NOW })
    expect(d.reason).toMatch(/locked/)
  })
})

describe('decay after absence', () => {
  const cases: [HelpLevel, number, HelpLevel][] = [
    [4, 14, 4],
    [4, 15, 3],
    [3, 7, 3],
    [3, 8, 2],
    [2, 3, 2],
    [2, 4, 1],
    [1, 400, 1],
  ]
  it.each(cases)('L%i absent %i days -> L%i', (level, days, expected) => {
    const s = state(level, 2, NOW - days * DAY_MS)
    expect(decayState(s, NOW).level).toBe(expected)
  })

  it('resets the streak when it drops and leaves lastSeen alone', () => {
    const s = state(3, 1, NOW - 10 * DAY_MS)
    const out = decayState(s, NOW)
    expect(out).toMatchObject({ level: 2, streakClean: 0, lastSeen: s.lastSeen })
  })

  it('is a derived view: the same stored state always gives the same one-level drop', () => {
    const s = state(4, 0, NOW - 100 * DAY_MS)
    expect(decayState(s, NOW)).toEqual(decayState(s, NOW))
    expect(decayState(s, NOW).level).toBe(3)
  })

  it('never practised means nothing to decay', () => {
    expect(decayState(state(3), NOW).level).toBe(3)
  })
})

describe('spaced review', () => {
  it('uses 1/3/7/14/30 day intervals and clamps', () => {
    expect([0, 1, 2, 3, 4, 9].map((n) => (nextReviewAt(NOW, n) - NOW) / DAY_MS)).toEqual([1, 3, 7, 14, 30, 30])
    expect(REVIEW_DAYS).toEqual([1, 3, 7, 14, 30])
  })
  it('knows when a review is due', () => {
    expect(isReviewDue({ nextReview: null }, NOW)).toBe(false)
    expect(isReviewDue({ nextReview: NOW + 1 }, NOW)).toBe(false)
    expect(isReviewDue({ nextReview: NOW }, NOW)).toBe(true)
  })
  it('follows the streak through evaluateAttempt', () => {
    const s = state(2, 2)
    const d = evaluateAttempt(attempt(), s, { demoMode: false, now: NOW })
    expect(d.change).toBe('up')
    expect(d.state.nextReview).toBe(NOW + DAY_MS)
    const holding = evaluateAttempt(attempt({ levelAtStart: 4 }), state(4), { demoMode: false, now: NOW })
    expect(holding.state.nextReview).toBe(NOW + 3 * DAY_MS)
  })
})

describe('stepLevel: safety floor and overrides', () => {
  const normal = { safetyCritical: false }
  const safe = { safetyCritical: true }
  const cases: [string, HelpLevel, { safetyCritical: boolean }, HelpLevel | undefined, HelpLevel][] = [
    ['plain step keeps level', 3, normal, undefined, 3],
    ['safety step at L4 is held at L2', 4, safe, undefined, 2],
    ['safety step at L3 is held at L2', 3, safe, undefined, 2],
    ['safety step at L1 stays L1', 1, safe, undefined, 1],
    ['safety step at L2 stays L2', 2, safe, undefined, 2],
    ['show me again -> L1', 3, normal, 1, 1],
    ['let me try -> L4', 2, normal, 4, 4],
    ['let me try on a safety step is still L2', 2, safe, 4, 2],
  ]
  it.each(cases)('%s', (_n, level, step, override, expected) => {
    expect(stepLevelFor(level, step, override)).toBe(expected)
    expect(levelEngine.stepLevel(state(level), step, override)).toBe(expected)
  })
})

describe('attempt-scope step down', () => {
  it('two hints on one step steps down for the rest of the attempt', () => {
    let s = startAttemptLevel(3)
    s = recordSignal(s, 'hint').state
    expect(s.current).toBe(3)
    const r = recordSignal(s, 'hint')
    expect(r.stepDown).toBe(true)
    expect(r.state.current).toBe(2)
    // persists into the next step; counters reset but the lowered level stays
    const next = beginStepCounters(r.state)
    expect(next).toMatchObject({ current: 2, stepHints: 0, hints: 2 })
  })

  it.each(['error', 'stall'] as const)('two %ss on one step trigger it', (signal) => {
    const once = recordSignal(startAttemptLevel(4), signal)
    expect(once.stepDown).toBe(false)
    const twice = recordSignal(once.state, signal)
    expect(twice.stepDown).toBe(true)
    expect(twice.state.current).toBe(3)
  })

  it('spreading signals across steps does not trigger', () => {
    let s = startAttemptLevel(3)
    s = recordSignal(s, 'error').state
    s = beginStepCounters(s)
    const r = recordSignal(s, 'error')
    expect(r.stepDown).toBe(false)
    expect(r.state.errors).toBe(2)
  })

  it('an anxiety phrase steps down immediately and is idempotent', () => {
    const r = recordSignal(startAttemptLevel(3), 'anxiety')
    expect(r.stepDown).toBe(true)
    expect(r.state).toMatchObject({ current: 2, anxiety: true })
    const again = recordSignal(r.state, 'anxiety')
    expect(again.stepDown).toBe(false)
    expect(again.state.current).toBe(2)
  })

  it('stays within L1', () => {
    const r = recordSignal(startAttemptLevel(1), 'anxiety')
    expect(r.state.current).toBe(1)
    expect(r.stepDown).toBe(false)
  })

  it('overrides set the temporary level; a struggling solo attempt falls back to base', () => {
    expect(applyOverride(startAttemptLevel(3), 'show_again').current).toBe(1)
    let s = applyOverride(startAttemptLevel(2), 'let_me_try')
    expect(s.current).toBe(4)
    s = recordSignal(recordSignal(s, 'error').state, 'error').state
    expect(s.current).toBe(2)
  })
})

describe('utterance detectors', () => {
  it.each(["I'm stuck", "I'm scared of this", 'oh no', "I've broken it", 'I always get this wrong', "I can't do this"])('flags anxiety: %s', (t) => {
    expect(detectAnxiety(t)).toBe(true)
  })
  it.each(['I want to call Lily', 'what does this button do', 'thank you'])('does not flag: %s', (t) => {
    expect(detectAnxiety(t)).toBe(false)
  })
  it('detects the two overrides', () => {
    expect(detectOverride('Can you show me again?')).toBe('show_again')
    expect(detectOverride('one more time please')).toBe('show_again')
    expect(detectOverride('no, let me try')).toBe('let_me_try')
    expect(detectOverride("I'll do it myself")).toBe('let_me_try')
    expect(detectOverride('I want to do this on my own')).toBe('let_me_try')
    expect(detectOverride('hello')).toBeNull()
  })
})

describe('engine factory and helpers', () => {
  it('starts new skills at L1 by default and honours a custom start', () => {
    expect(levelEngine.initial(NOW)).toEqual({ level: 1, streakClean: 0, lastSeen: null, nextReview: null })
    expect(createLevelEngine({ initialLevel: 2 }).initial(NOW).level).toBe(2)
  })
  it('clamps and labels levels', () => {
    expect(clampLevel(0)).toBe(1)
    expect(clampLevel(9)).toBe(4)
    expect(clampLevel(2.4)).toBe(2)
    expect([1, 2, 3, 4].map((l) => levelLabel(l as HelpLevel))).toEqual(['Watch me', 'Walk with me', 'Nudge me', 'On my own'])
    expect(stepUpStreak(3, true)).toBe(1)
    expect(stepUpStreak(3, false)).toBe(2)
  })
  it('delegates decay and evaluation', () => {
    expect(levelEngine.decay(state(3, 0, NOW - 30 * DAY_MS), NOW).level).toBe(2)
    const d = levelEngine.evaluateAttempt(attempt(), state(2), { demoMode: true, now: NOW })
    expect(d.change).toBe('up')
  })
})

// Fading is visible across two consecutive attempts (the demo moment).
describe('fade over two attempts', () => {
  it('L2 -> L3 -> L4 with one clean attempt each in demo mode', () => {
    let s = state(2)
    for (const expected of [3, 4] as HelpLevel[]) {
      const d = evaluateAttempt(attempt({ levelAtStart: s.level }), s, { demoMode: true, now: NOW })
      expect(d.state.level).toBe(expected)
      s = d.state
    }
  })
})

describe('in-lesson adaptive fading', () => {
  // Drive a sequence of steps through the reducer. Each step: [hints, errors, stalls].
  type Step = [hints: number, errors: number, stalls: number]
  function run(base: HelpLevel, steps: Step[], opts: { locked?: boolean; override?: 'show_again' | 'let_me_try' } = {}) {
    let s = startAttemptLevel(base)
    if (opts.override) s = applyOverride(s, opts.override)
    const trace: { level: HelpLevel; change: string }[] = []
    steps.forEach((step, i) => {
      s = beginStepCounters(s)
      for (let h = 0; h < step[0]; h++) s = recordSignal(s, 'hint').state
      for (let e = 0; e < step[1]; e++) s = recordSignal(s, 'error').state
      for (let t = 0; t < step[2]; t++) s = recordSignal(s, 'stall').state
      const done = completeStep(s, { remainingSteps: steps.length - i - 1, locked: opts.locked })
      s = done.state
      trace.push({ level: s.current, change: done.change })
    })
    return trace
  }
  const CLEAN: Step = [0, 0, 0]

  const cases: [string, HelpLevel, Step[], string[]][] = [
    ['two clean steps ease off after step 2', 2, [CLEAN, CLEAN, CLEAN, CLEAN, CLEAN], ['2:none', '3:fade', '3:none', '3:none', '3:none']],
    ['L1 start fades to L2', 1, [CLEAN, CLEAN, CLEAN], ['1:none', '2:fade', '2:none']],
    ['never past base+1 within an attempt', 3, [CLEAN, CLEAN, CLEAN, CLEAN, CLEAN, CLEAN], ['3:none', '4:fade', '4:none', '4:none', '4:none', '4:none']],
    ['a fade on the last step has nothing left to ease', 2, [CLEAN, CLEAN], ['2:none', '2:none']],
    ['a hint breaks the clean run', 2, [CLEAN, [1, 0, 0], CLEAN, CLEAN, CLEAN], ['2:none', '2:none', '2:none', '3:fade', '3:none']],
    ['an error breaks it too', 2, [CLEAN, [0, 1, 0], CLEAN], ['2:none', '2:none', '2:none']],
    ['a stall breaks it too', 2, [[0, 0, 1], CLEAN, CLEAN, CLEAN], ['2:none', '2:none', '3:fade', '3:none']],
    ['two struggling steps in a row bring help back after a fade', 2, [CLEAN, CLEAN, [1, 0, 0], [0, 1, 0], CLEAN], ['2:none', '3:fade', '3:none', '2:regress', '2:none']],
    ['a clean step between struggles resets the run', 2, [CLEAN, CLEAN, [1, 0, 0], CLEAN, [0, 1, 0], CLEAN], ['2:none', '3:fade', '3:none', '3:none', '3:none', '3:none']],
    ['regress never goes more than one below where the attempt started', 2, [[1, 0, 0], [1, 0, 0], [1, 0, 0], [1, 0, 0], [1, 0, 0]], ['2:none', '1:regress', '1:none', '1:none', '1:none']],
  ]
  it.each(cases)('%s', (_name, base, steps, expected) => {
    const trace = run(base, steps).map((t) => `${t.level}:${t.change}`)
    expect(trace).toEqual(expected)
  })

  it('a locked level never fades or regresses', () => {
    expect(run(2, [CLEAN, CLEAN, CLEAN, [1, 0, 0], [1, 0, 0]], { locked: true }).map((t) => t.change)).toEqual(['none', 'none', 'none', 'none', 'none'])
  })

  it('a level the learner chose is left alone', () => {
    expect(run(2, [CLEAN, CLEAN, CLEAN], { override: 'show_again' }).map((t) => `${t.level}:${t.change}`)).toEqual(['1:none', '1:none', '1:none'])
    expect(run(2, [CLEAN, CLEAN, CLEAN], { override: 'let_me_try' }).map((t) => `${t.level}:${t.change}`)).toEqual(['4:none', '4:none', '4:none'])
  })

  it('a step-down inside a step resets the clean run', () => {
    let s = startAttemptLevel(3)
    s = completeStep(beginStepCounters(s), { remainingSteps: 5 }).state
    expect(s.cleanRun).toBe(1)
    s = beginStepCounters(s)
    s = recordSignal(recordSignal(s, 'hint').state, 'hint').state
    expect(s.current).toBe(2)
    expect(s.cleanRun).toBe(0)
  })

  it('does not cascade: a third hint on one step is not a new trigger', () => {
    let s = startAttemptLevel(4)
    for (let i = 0; i < 4; i++) s = recordSignal(s, 'hint').state
    expect(s.current).toBe(3)
  })

  it('exposes the fade through the between-attempt rule unchanged', () => {
    // An attempt that faded L2 -> L3 inside the lesson is still judged at the level it started at.
    const d = evaluateAttempt(attempt({ levelAtStart: 2, hintsUsed: 1 }), state(2), { demoMode: true, now: NOW })
    expect(d.state.level).toBe(3)
  })
})
