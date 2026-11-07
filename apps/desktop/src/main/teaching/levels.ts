// LevelEngine: the Help Ladder as pure functions. No I/O, no clocks (time is passed in), no LLM.
// Deterministic code owns the level so a chatty model cannot talk the product out of fading.
//
// Direction of travel: L1 "Watch me" (most help) ... L4 "On my own" (least help). "Step up" = more
// independent (level + 1); "step down" = more help (level - 1).
import { HELP_LEVEL_LABELS } from '../../shared/protocol'
import type { AttemptRecord, HelpLevel, LessonStep, SkillState } from '../../shared/protocol'
import type { LevelDecision, LevelEngine } from '../../shared/contracts'

export const DAY_MS = 86_400_000
export const TEACH_BACK_PASS = 0.67
export const MAX_CLEAN_ERRORS = 1
export const LEVELS: readonly HelpLevel[] = [1, 2, 3, 4]

export const LEVEL_LABEL: Record<HelpLevel, string> = HELP_LEVEL_LABELS

// Hints allowed in a "clean" attempt, by the level the attempt started at (L1 is a demonstration: n/a).
export const HINT_CAP: Record<HelpLevel, number> = { 1: Number.POSITIVE_INFINITY, 2: 1, 3: 2, 4: 0 }
// Consecutive clean attempts needed to step up. Level 4 "needs" it to count as mastered.
export const STEP_UP_STREAK: Record<HelpLevel, number> = { 1: 1, 2: 2, 3: 2, 4: 2 }
export const DEMO_STEP_UP_STREAK = 1
// Absence (days) after which a level decays by one. L1 has nowhere lower to go.
export const DECAY_AFTER_DAYS: Partial<Record<HelpLevel, number>> = { 2: 3, 3: 7, 4: 14 }
// Expanding review intervals indexed by consecutive clean attempts.
export const REVIEW_DAYS = [1, 3, 7, 14, 30] as const
// Attempt-scope step-down triggers (per step).
export const STEP_DOWN_AT = { hints: 2, errors: 2, stalls: 2 } as const
// In-lesson adaptive fading: this many clean steps in a row ease the help off for the remaining steps;
// this many struggling steps in a row bring it back.
export const FADE_AFTER_CLEAN_STEPS = 2
export const REGRESS_AFTER_STRUGGLE_STEPS = 2

export type OverrideKind = 'show_again' | 'let_me_try'

export function clampLevel(n: number): HelpLevel {
  return Math.min(4, Math.max(1, Math.round(n))) as HelpLevel
}

export function levelLabel(level: HelpLevel): string {
  return LEVEL_LABEL[level]
}

export function stepUpStreak(level: HelpLevel, demoMode: boolean): number {
  return demoMode ? DEMO_STEP_UP_STREAK : STEP_UP_STREAK[level]
}

export function nextReviewAt(now: number, streakClean: number): number {
  const idx = Math.min(Math.max(Math.floor(streakClean), 0), REVIEW_DAYS.length - 1)
  return now + REVIEW_DAYS[idx] * DAY_MS
}

export function isReviewDue(state: Pick<SkillState, 'nextReview'>, now: number): boolean {
  return state.nextReview !== null && state.nextReview <= now
}

export function isMastered(state: SkillState, demoMode: boolean): boolean {
  return state.level === 4 && state.streakClean >= stepUpStreak(4, demoMode)
}

export function isCleanAttempt(a: Pick<AttemptRecord, 'completed' | 'hintsUsed' | 'errors' | 'safetyFlag' | 'levelAtStart'>): boolean {
  return a.completed && a.hintsUsed <= HINT_CAP[a.levelAtStart] && a.errors <= MAX_CLEAN_ERRORS && !a.safetyFlag
}

// Persistent decay for absence. Derived view: it never mutates lastSeen, so calling it twice for the same
// absence gives the same answer (one level), and nothing is saved until the next attempt is evaluated.
export function decayState(state: SkillState, now: number): SkillState {
  if (state.lastSeen === null) return state
  const limitDays = DECAY_AFTER_DAYS[state.level]
  if (limitDays === undefined) return state
  if (now - state.lastSeen <= limitDays * DAY_MS) return state
  return { ...state, level: clampLevel(state.level - 1), streakClean: 0 }
}

// Safety-critical steps (money, passwords, links in unsolicited messages) are exempt from fading: they
// always get at least Walk-with-me help (level <= 2). A learner asking to see it again (L1) is still honoured.
export function stepLevelFor(level: HelpLevel, step: Pick<LessonStep, 'safetyCritical'>, override?: HelpLevel): HelpLevel {
  const requested = override ?? level
  return step.safetyCritical ? clampLevel(Math.min(requested, 2)) : requested
}

export interface EvaluateOptions {
  demoMode: boolean
  now: number
  // Earlier attempts at this skill, oldest first (the LearnerStore passes its history). Drives the
  // "two non-clean attempts in a row" rule without adding fields to SkillState.
  recentAttempts?: readonly AttemptRecord[]
  // The learner used an override during this attempt. Overrides never cost the learner anything.
  override?: OverrideKind | null
  // Settings helpLevelMode === 'locked': record the attempt, never move the level.
  locked?: boolean
  // When false (default) a skipped / unscored teach-back does not block a step up.
  requireTeachBack?: boolean
}

function consecutiveMisses(recent: readonly AttemptRecord[]): number {
  let misses = 0
  for (let i = recent.length - 1; i >= 0; i--) {
    const a = recent[i]
    if (a.clean) break
    // A miss that already caused a step down starts the count afresh.
    if (a.levelAtEnd < a.levelAtStart) break
    misses++
  }
  return misses
}

export function evaluateAttempt(attempt: AttemptRecord, state: SkillState, opts: EvaluateOptions): LevelDecision {
  const { now } = opts
  const seen = { lastSeen: now }
  const hold = (streakClean: number, reason: string): LevelDecision => ({
    state: { ...state, ...seen, streakClean, nextReview: nextReviewAt(now, streakClean) },
    change: 'hold',
    reason,
  })

  if (opts.locked) return hold(state.streakClean, 'level is locked by the learner')
  if (opts.override === 'show_again') return hold(state.streakClean, 'asked to see it again; no penalty')

  if (!attempt.completed) {
    if (opts.override === 'let_me_try') return hold(state.streakClean, 'tried on their own and stopped; no penalty')
    const level = clampLevel(state.level - 1)
    if (level === state.level) return hold(0, 'attempt abandoned at the lowest level')
    return {
      state: { ...state, ...seen, level, streakClean: 0, nextReview: nextReviewAt(now, 0) },
      change: 'down',
      reason: 'attempt abandoned',
    }
  }

  const clean = isCleanAttempt(attempt)
  if (!clean) {
    if (opts.override === 'let_me_try') return hold(0, 'going solo was hard; no penalty')
    const misses = consecutiveMisses(opts.recentAttempts ?? []) + 1
    if (misses >= 2 && state.level > 1) {
      const level = clampLevel(state.level - 1)
      return {
        state: { ...state, ...seen, level, streakClean: 0, nextReview: nextReviewAt(now, 0) },
        change: 'down',
        reason: 'two attempts in a row needed more help than this level gives',
      }
    }
    return hold(0, 'needed more help than this level allows; try again at the same level')
  }

  if (attempt.anxietyPhrase) return hold(state.streakClean, 'worried moment; hold the level and let it settle')
  const score = attempt.teachBackScore
  if (score !== null && score < TEACH_BACK_PASS) return hold(state.streakClean, 'teach-back below the pass mark; hold')
  if (score === null && opts.requireTeachBack) return hold(state.streakClean, 'no teach-back yet; hold')

  const streakClean = state.streakClean + 1
  const need = stepUpStreak(state.level, opts.demoMode)
  if (streakClean < need) return hold(streakClean, `clean attempt ${streakClean} of ${need}`)
  if (state.level === 4) return hold(streakClean, 'mastered: clean again at the top level')
  const level = clampLevel(state.level + 1)
  return {
    state: { ...state, ...seen, level, streakClean: 0, nextReview: nextReviewAt(now, 0) },
    change: 'up',
    reason: opts.demoMode ? 'one clean attempt (demo mode)' : `${need} clean attempts`,
  }
}

// ---------- attempt-scope (temporary) level ----------
export interface AttemptLevelState {
  base: HelpLevel
  current: HelpLevel
  override: OverrideKind | null
  stepHints: number
  stepErrors: number
  stepStalls: number
  hints: number
  errors: number
  stalls: number
  anxiety: boolean
  steppedDown: boolean
  // Consecutive clean / struggling steps; drive the in-lesson fade.
  cleanRun: number
  struggleRun: number
}

export type AttemptSignal = 'hint' | 'error' | 'stall' | 'anxiety'

export function startAttemptLevel(base: HelpLevel): AttemptLevelState {
  return {
    base,
    current: base,
    override: null,
    stepHints: 0,
    stepErrors: 0,
    stepStalls: 0,
    hints: 0,
    errors: 0,
    stalls: 0,
    anxiety: false,
    steppedDown: false,
    cleanRun: 0,
    struggleRun: 0,
  }
}

export function beginStepCounters(s: AttemptLevelState): AttemptLevelState {
  return { ...s, stepHints: 0, stepErrors: 0, stepStalls: 0 }
}

// One level more help than now, but never more than one below where the attempt started.
function regressTarget(s: AttemptLevelState): HelpLevel {
  // Someone who took over ("let me try") and struggles goes straight back to where they were, not below it.
  if (s.override === 'let_me_try') return clampLevel(Math.min(s.current, s.base))
  return clampLevel(Math.max(s.current - 1, s.base - 1))
}

export function recordSignal(s: AttemptLevelState, signal: AttemptSignal): { state: AttemptLevelState; stepDown: boolean } {
  const next: AttemptLevelState = { ...s }
  // Edge-triggered: a third hint on the same step must not cascade the level down again.
  let triggered = false
  if (signal === 'hint') {
    next.stepHints++
    next.hints++
    triggered = next.stepHints === STEP_DOWN_AT.hints
  } else if (signal === 'error') {
    next.stepErrors++
    next.errors++
    triggered = next.stepErrors === STEP_DOWN_AT.errors
  } else if (signal === 'stall') {
    next.stepStalls++
    next.stalls++
    triggered = next.stepStalls === STEP_DOWN_AT.stalls
  } else {
    triggered = !next.anxiety
    next.anxiety = true
  }
  if (!triggered) return { state: next, stepDown: false }
  const lowered = regressTarget(next)
  const changed = lowered < next.current
  if (changed) {
    next.current = lowered
    next.steppedDown = true
    next.cleanRun = 0
  }
  return { state: next, stepDown: changed }
}

export interface StepCompletion {
  state: AttemptLevelState
  change: 'fade' | 'regress' | 'none'
  from: HelpLevel
  to: HelpLevel
}

// Called when a step is verified. Adaptive fading as in the expertise-reversal effect: guidance eases off as
// competence shows (never past base+1 within one attempt, never when the learner chose a level themselves or
// the level is locked, never when nothing remains) and returns after two struggling steps in a row.
export function completeStep(s: AttemptLevelState, opts: { remainingSteps: number; locked?: boolean; maxLevel?: HelpLevel }): StepCompletion {
  const clean = s.stepHints === 0 && s.stepErrors === 0 && s.stepStalls === 0
  const next: AttemptLevelState = { ...s, cleanRun: clean ? s.cleanRun + 1 : 0, struggleRun: clean ? 0 : s.struggleRun + 1 }
  const from = s.current
  if (opts.locked || s.override !== null) return { state: next, change: 'none', from, to: from }
  if (clean && next.cleanRun >= FADE_AFTER_CLEAN_STEPS && opts.remainingSteps > 0) {
    const ceiling = clampLevel(Math.min(opts.maxLevel ?? 4, s.base + 1))
    if (s.current < ceiling) {
      next.current = clampLevel(s.current + 1)
      next.cleanRun = 0
      return { state: next, change: 'fade', from, to: next.current }
    }
  }
  if (!clean && next.struggleRun >= REGRESS_AFTER_STRUGGLE_STEPS) {
    const lowered = regressTarget(next)
    if (lowered < s.current) {
      next.current = lowered
      next.struggleRun = 0
      next.steppedDown = true
      return { state: next, change: 'regress', from, to: lowered }
    }
  }
  return { state: next, change: 'none', from, to: from }
}

export function applyOverride(s: AttemptLevelState, kind: OverrideKind): AttemptLevelState {
  return { ...s, override: kind, current: kind === 'show_again' ? 1 : 4 }
}

// ---------- utterance classifiers (cheap, deterministic; the model's own judgement is advisory) ----------
const ANXIETY_PATTERNS: readonly RegExp[] = [
  /\bi'?m (?:stuck|scared|worried|nervous|lost|confused|frightened|afraid|panicking)\b/i,
  /\bi (?:can'?t|cannot) (?:do|see|find|work)\b/i,
  /\bi'?m (?:stupid|useless|hopeless|no good|too old)\b/i,
  /\bi always get (?:this|it) wrong\b/i,
  /\boh no\b/i,
  /\bi'?ve (?:broken|ruined|messed up|done something wrong)\b/i,
  /\bi don'?t understand\b/i,
  /\bi'?m (?:going to|gonna) (?:break|mess)\b/i,
]
const SHOW_AGAIN_PATTERNS: readonly RegExp[] = [/\bshow me again\b/i, /\bshow me (?:how|once more)\b/i, /\bwatch me\b.*\bagain\b/i, /\bdo (?:it|that) again\b/i, /\bone more time\b/i]
const LET_ME_TRY_PATTERNS: readonly RegExp[] = [/\blet me try\b/i, /\bi'?ll (?:do|try) it\b/i, /\bon my own\b/i, /\bby myself\b/i, /\blet me do it\b/i, /\bi (?:can|want to) do (?:it|this) myself\b/i]

export function detectAnxiety(text: string): boolean {
  return ANXIETY_PATTERNS.some((p) => p.test(text))
}

export function detectOverride(text: string): OverrideKind | null {
  if (SHOW_AGAIN_PATTERNS.some((p) => p.test(text))) return 'show_again'
  if (LET_ME_TRY_PATTERNS.some((p) => p.test(text))) return 'let_me_try'
  return null
}

// ---------- the engine object that goes into the services bag ----------
export interface TeachingLevelEngine extends LevelEngine {
  evaluateAttempt(attempt: AttemptRecord, state: SkillState, opts: EvaluateOptions): LevelDecision
}

export interface LevelEngineConfig {
  // Where a brand-new skill starts. L1 ("Watch me") is the pedagogically honest default.
  initialLevel?: HelpLevel
}

export function createLevelEngine(config: LevelEngineConfig = {}): TeachingLevelEngine {
  const initialLevel = config.initialLevel ?? 1
  return {
    initial: () => ({ level: initialLevel, streakClean: 0, lastSeen: null, nextReview: null }),
    isClean: isCleanAttempt,
    evaluateAttempt,
    decay: decayState,
    stepLevel: (state, step, override) => stepLevelFor(state.level, step, override),
  }
}

export const levelEngine: TeachingLevelEngine = createLevelEngine()
