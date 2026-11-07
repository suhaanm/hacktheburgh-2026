// LessonRunner: drives a lesson step by step. Plain code decides what is shown and when; the Live model only
// narrates the [RUNNER]/[STALL] directions it is sent. Nothing here ever clicks: guidance is overlay-only.
//
// Per step: inject the direction at once (never wait on grounding) -> ground the target (overlapping the
// narration) -> draw what the current level calls for -> watch the screen + stall timer -> verify -> tick
// (or repair hint) -> next step. At the end the model does the teach-back and calls end_lesson, which feeds
// the LevelEngine and the LearnerStore.
import { LessonPlanSchema, truncateWords } from '../../shared/protocol'
import type {
  Annotation,
  AttemptRecord,
  BuiltinSkillId,
  GroundResult,
  HelpLevel,
  LearnerSnapshot,
  LessonPlan,
  LessonStep,
  LessonStepEvent,
  LevelChangedEvent,
  NormBox,
  NormPoint,
  SkillId,
  SkillState,
  StepDoneResult,
  Verdict,
  CompanionState,
  DoItForMeResult,
} from '../../shared/protocol'
import type { Capture, Grounder, LearnerStore, LessonArchitect, LessonRunner, LevelDecision, LevelEngine, LiveBridge, OverlayController, Verifier } from '../../shared/contracts'
import type { Settings } from '../../shared/settings'
import {
  lessonCompleteDirective,
  planningDirective,
  pointerFallbackDirective,
  levelDirective,
  oneLine,
  repairDirective,
  stallDirective,
  stepDirective,
  uncertainDirective,
  verifiedDirective,
} from './directives'
import {
  applyOverride,
  beginStepCounters,
  clampLevel,
  completeStep,
  detectAnxiety,
  detectOverride,
  isCleanAttempt,
  recordSignal,
  startAttemptLevel,
} from './levels'
import type { AttemptLevelState, AttemptSignal, EvaluateOptions, OverrideKind } from './levels'
import { fallbackPlan, pointerPlan } from './skills/plans'
import { riskWords } from '../agency/policy'
import { SKILLS, pickSkill } from './skills/definitions'

export interface Clock {
  now(): number
  setTimeout(fn: () => void, ms: number): unknown
  clearTimeout(handle: unknown): void
}

export const systemClock: Clock = {
  now: () => Date.now(),
  setTimeout: (fn, ms) => setTimeout(fn, ms),
  clearTimeout: (h) => clearTimeout(h as NodeJS.Timeout),
}

export interface RunnerConfig {
  planTimeoutMs: number
  // Silence before the stall ladder starts, by effective step level (gentle pacing; "fast" scales it down).
  stallMs: Record<HelpLevel, number>
  // Gap between ladder rungs, as a fraction of the stall time.
  rungGapFactor: number
  verifyDebounceMs: number
  minVerifyGapMs: number
  // An explicit step_done / verify_step within this window of an advance acknowledges that advance (no double step).
  ackWindowMs: number
  maxVerifyGapMs: number
  // How long to wait for the model's end_lesson before closing the attempt ourselves.
  endTimeoutMs: number
  tickMs: number
  minVerifyConfidence: number
  grabShotForPlanMs: number
  // After the stall ladder is spent, how long before auto-assist offers to click (lets the last hint be heard).
  assistDelayMs: number
}

export const DEFAULT_RUNNER_CONFIG: RunnerConfig = {
  // Only novel goals wait for the architect (built-in skills start instantly from their static plans).
  planTimeoutMs: 15_000,
  stallMs: { 1: 15_000, 2: 12_000, 3: 8_000, 4: 20_000 },
  rungGapFactor: 0.75,
  verifyDebounceMs: 700,
  minVerifyGapMs: 1_500,
  ackWindowMs: 3_000,
  maxVerifyGapMs: 10_000,
  endTimeoutMs: 90_000,
  tickMs: 1_500,
  minVerifyConfidence: 0.6,
  grabShotForPlanMs: 3_000,
  assistDelayMs: 1_500,
}

export interface AttemptSink {
  snapshot(): LearnerSnapshot
  recordAttempt(attempt: AttemptRecord, extras?: { decision?: LevelDecision; override?: OverrideKind | null; summary?: string }): Promise<LearnerSnapshot>
}

export interface RunnerDeps {
  capture: Capture
  // prefetch/invalidate are optional on the contract; the runner works with or without them. Every lesson step is
  // grounded with precise:true (one wrong ring is a visible failure; the prefetch hides the extra latency).
  grounder: Grounder
  verifier: Verifier
  architect: LessonArchitect
  overlay: OverlayController
  live: LiveBridge
  learner: AttemptSink | LearnerStore
  levels: LevelEngine
  state: { get(): CompanionState; patch(partial: Partial<CompanionState>): unknown }
  bus: { emit(event: 'lesson:step', payload: LessonStepEvent): void; emit(event: 'level:changed', payload: LevelChangedEvent): void }
  getSettings(): Settings
  // Auto-assist on stall (optional, default off): the existing do_it_for_me flow, which owns the real-click confirmation,
  // the denylist, the scam/safety refusals, the audit and Stop. Absent = the feature does not exist.
  assist?: (args: { target: string }) => Promise<DoItForMeResult>
  // Persisted profile loaded (first start waits for it).
  ready?: Promise<unknown>
  clock?: Clock
  config?: Partial<RunnerConfig>
  planFor?: (skillId: SkillId, goal: string) => LessonPlan
  newId?: () => string
  log?: (...args: unknown[]) => void
}

const ANNOTATION_IDS = ['runner-ring', 'runner-arrow', 'runner-ghost', 'runner-glow', 'runner-tick']
const MAX_RUNGS: Record<HelpLevel, number> = { 1: 2, 2: 2, 3: 3, 4: 1 }

interface Active {
  lessonId: string
  plan: LessonPlan
  skillId: SkillId
  goal: string
  planSource: 'builtin' | 'architect' | 'pointer'
  index: number
  stepsVerified: number
  baseState: SkillState
  persistentLevel: HelpLevel
  chipLevel: HelpLevel
  attempt: AttemptLevelState
  startedAt: number
  safetyFlag: boolean
  rung: number
  stepLevel: HelpLevel
  ground: Promise<GroundResult | null> | null
  box: NormBox | null
  lastVerifyAt: number
  // Screen-triggered checks that found nothing yet on this step: each one doubles the wait for the next.
  notYet: number
  // When the last step was verified and what the verdict was: step_done/verify_step right after it is the same completion.
  advancedAt: number
  lastVerdict: Verdict | null
  verifying: Promise<VerifyOutcome> | null
  finished: boolean
  ended: boolean
  uncertainAt: number
  stallTimer: unknown
  verifyTimer: unknown
  endTimer: unknown
  unwatch: (() => void) | null
  token: number
}

interface VerifyOutcome {
  verdict: Verdict
  advanced: boolean
  stale: boolean
}

const CONFIDENCE_RE = /\bconfidence\D{0,15}([1-5])\b/i

export class LessonRunnerImpl implements LessonRunner {
  private active: Active | null = null
  private tokenSeq = 0
  private startSeq = 0
  private idSeq = 0
  private settled: Promise<unknown> = Promise.resolve()
  // Steps already offered auto-assist (lessonId:index): at most once per step.
  private readonly assistOffered = new Set<string>()
  private readonly clock: Clock
  private readonly cfg: RunnerConfig

  constructor(private readonly deps: RunnerDeps) {
    this.clock = deps.clock ?? systemClock
    this.cfg = { ...DEFAULT_RUNNER_CONFIG, ...deps.config }
  }

  // Resolves when the in-flight step set-up (grounding, drawing) has finished. For tests and graceful shutdown.
  idle(): Promise<unknown> {
    return this.settled
  }

  private track(p: Promise<unknown>): void {
    this.settled = Promise.all([this.settled, p.catch(() => undefined)])
  }

  get running(): boolean {
    return this.active !== null
  }

  // For the system prompt: what is running right now.
  currentLesson(): { skillId: SkillId; goal: string; step: number; stepCount: number } | undefined {
    const a = this.active
    return a ? { skillId: a.skillId, goal: a.goal, step: a.index + 1, stepCount: a.plan.steps.length } : undefined
  }

  get currentStepIndex(): number | null {
    return this.active ? this.active.index : null
  }

  // ---------------------------------------------------------------- start
  async start(goal: string): Promise<{ lessonId: string; skillId: SkillId; stepCount: number }> {
    // A session that ends (goodbye, Stop) while a plan is still being worked out must not start a lesson afterwards.
    const ticket = ++this.startSeq
    const cancelled = (): never => {
      throw new Error('The lesson was cancelled before it started.')
    }
    const ready = this.deps.ready
    if (ready) await ready
    if (ticket !== this.startSeq) cancelled()
    if (this.active) await this.teardown('replaced', false)
    const matched = pickSkill(goal)
    const { plan, source } = await this.obtainPlan(goal, matched)
    if (ticket !== this.startSeq) cancelled()
    const skillId = plan.skillId
    const now = this.clock.now()
    const settings = this.deps.getSettings()
    const snapshot = this.deps.learner.snapshot()
    // snapshot() already carries the derived absence decay; storedSkill (our store only) tells us whether it applied.
    const base = snapshot.skills[skillId] ?? this.deps.levels.initial(now)
    const stored = (this.deps.learner as { storedSkill?: (id: SkillId) => SkillState | undefined }).storedSkill?.(skillId) ?? base
    const locked = settings.helpLevelMode === 'locked'
    const level = locked ? settings.lockedLevel : base.level
    // A lesson with a safety-critical step is always tracked step by step (never the untracked whole-task mode of L4),
    // so that step can be lifted to Walk-with-me when it arrives.
    const cap = this.levelCap(plan)
    const effective = clampLevel(Math.min(level, cap))
    const a: Active = {
      lessonId: plan.lessonId,
      plan,
      skillId,
      goal,
      planSource: source,
      index: 0,
      stepsVerified: 0,
      baseState: base,
      persistentLevel: level,
      chipLevel: this.deps.state.get().level,
      attempt: startAttemptLevel(effective),
      startedAt: now,
      safetyFlag: false,
      rung: 0,
      stepLevel: effective,
      ground: null,
      box: null,
      lastVerifyAt: 0,
      notYet: 0,
      advancedAt: -Infinity,
      lastVerdict: null,
      verifying: null,
      finished: false,
      ended: false,
      uncertainAt: 0,
      stallTimer: null,
      verifyTimer: null,
      endTimer: null,
      unwatch: null,
      token: ++this.tokenSeq,
    }
    this.active = a
    // Overlap step 1's grounding with the assistant's opening line: start it now, not on the next tick.
    if (source !== 'architect') void this.deps.grounder.prefetch?.({ target: plan.steps[0].targetDescription, precise: true })
    this.setChip(a, effective, base.level !== stored.level ? 'quick refresher after time away' : effective < level ? 'this lesson keeps a safety net' : 'level for this skill', 'skill')
    this.deps.state.patch({ skill: { id: skillId, name: this.lessonName({ skillId, goal }), step: 1, stepCount: plan.steps.length } })
    a.unwatch = this.deps.capture.watch((score) => this.onScreenChange(a, score))
    // The tool result goes back first; step 1 is announced on the next tick so the model gets the answer before the direction.
    this.track(
      new Promise<void>((resolve) => {
        this.clock.setTimeout(() => {
          void this.beginStep(a, 0, true, source === 'pointer' ? `${pointerFallbackDirective()} ` : '').finally(resolve)
        }, 0)
      }),
    )
    return { lessonId: plan.lessonId, skillId, stepCount: plan.steps.length }
  }

  // Built-in skills start at once from their static plans (fast, deterministic, matched to the stage). Anything else
  // is planned by the architect from the live screen; if that fails we say so and just point, never a wrong lesson.
  private async obtainPlan(goal: string, matched: BuiltinSkillId | null): Promise<{ plan: LessonPlan; source: 'builtin' | 'architect' | 'pointer' }> {
    if (matched) return { plan: (this.deps.planFor ?? fallbackPlan)(matched, goal), source: 'builtin' }
    // Keep the assistant talking while the plan is worked out.
    this.deps.live.inject(planningDirective(goal))
    try {
      // One hard deadline for the whole plan request, shot included.
      const deadline = this.clock.now() + this.cfg.planTimeoutMs
      const learner = this.deps.learner.snapshot()
      const shot = await this.race(this.deps.capture.grab('ground'), this.cfg.grabShotForPlanMs).catch(() => undefined)
      const raw = await this.race(this.deps.architect.plan({ goal, learner, shot: shot ?? undefined }), Math.max(1, deadline - this.clock.now()))
      const parsed = LessonPlanSchema.safeParse(raw)
      if (!parsed.success) throw new Error('plan failed validation')
      const plan: LessonPlan = {
        ...parsed.data,
        skillId: 'custom',
        goal: oneLine(goal).slice(0, 120) || parsed.data.goal,
        steps: parsed.data.steps.map((st, i) => ({ ...st, index: i, instruction: truncateWords(st.instruction) })),
      }
      return { plan, source: 'architect' }
    } catch (err) {
      this.log('could not plan a new lesson, pointing instead:', err instanceof Error ? err.message : err)
      return { plan: pointerPlan(goal), source: 'pointer' }
    }
  }

  private levelCap(plan: LessonPlan): HelpLevel {
    return plan.steps.some((st) => st.safetyCritical) ? 3 : 4
  }

  private lessonName(a: Pick<Active, 'skillId' | 'goal'>): string {
    return a.skillId === 'custom' ? oneLine(a.goal).slice(0, 80) : SKILLS[a.skillId].name
  }

  private race<T>(p: Promise<T>, ms: number): Promise<T | undefined> {
    return new Promise<T | undefined>((resolve, reject) => {
      const timer = this.clock.setTimeout(() => reject(new Error(`timed out after ${ms} ms`)), ms)
      p.then(
        (v) => {
          this.clock.clearTimeout(timer)
          resolve(v)
        },
        (e) => {
          this.clock.clearTimeout(timer)
          reject(e)
        },
      )
    })
  }

  // ---------------------------------------------------------------- step lifecycle
  private current(a: Active): boolean {
    return this.active === a
  }

  private levelForStep(a: Active, step: LessonStep): HelpLevel {
    return this.deps.levels.stepLevel({ level: a.attempt.current, streakClean: 0, lastSeen: null, nextReview: null }, step)
  }

  private async beginStep(a: Active, index: number, first: boolean, lead = ''): Promise<void> {
    if (!this.current(a)) return
    const step = a.plan.steps[index]
    a.index = index
    a.rung = 0
    a.box = null
    a.notYet = 0
    a.attempt = beginStepCounters(a.attempt)
    a.stepLevel = this.levelForStep(a, step)
    this.clearTimer(a, 'stallTimer')
    this.clearTimer(a, 'verifyTimer')
    this.deps.overlay.clear(ANNOTATION_IDS)
    this.deps.state.patch({ skill: { id: a.skillId, name: this.lessonName(a), step: index + 1, stepCount: a.plan.steps.length } })
    this.deps.bus.emit('lesson:step', { lessonId: a.lessonId, skillId: a.skillId, stepIndex: index, stepCount: a.plan.steps.length, phase: 'started', step })
    if (a.stepLevel !== a.chipLevel && !this.isLocked()) this.setChip(a, a.stepLevel, a.stepLevel < a.chipLevel ? 'this step is safety-critical' : 'back to your level', 'step')

    // 1. Narration first. Grounding (seconds) overlaps it; the model is never blocked on the screen.
    const needsPicture = a.stepLevel <= 3
    if (needsPicture && !(first && a.planSource === 'architect')) void this.deps.grounder.prefetch?.({ target: step.targetDescription, precise: true })
    // Nothing to say for a quiet L4 step: skip the direction unless there is a lead (level change, acknowledgement).
    const quietStep = a.stepLevel >= 4 && !first && !step.safetyCritical && lead.trim() === ''
    if (!quietStep) this.deps.live.inject(
      lead +
        stepDirective({
          stepNumber: index + 1,
          stepCount: a.plan.steps.length,
          level: a.stepLevel,
          instruction: step.instruction,
          demoNarration: step.hints.l1,
          analogy: first || a.stepLevel === 1 ? step.analogy : undefined,
          safetyCritical: step.safetyCritical,
          pauseForCheck: a.stepLevel === 1 && ((index + 1) % 3 === 0 || index === a.plan.steps.length - 1),
          lessonStart: first ? { name: this.lessonName(a), goal: a.goal } : undefined,
          annotated: needsPicture,
        }),
    )

    // 2. Ground in parallel (L3 holds the result for the stall ladder; L4 draws nothing).
    if (needsPicture) {
      a.ground = this.groundStep(a, step)
      const res = await a.ground
      if (!this.current(a) || a.index !== index) return
      if (res?.box) a.box = res.box
      if (a.stepLevel <= 2) this.present(a, step, a.stepLevel)
      if (a.stepLevel <= 2 && !res?.box) this.deps.live.inject(`[RUNNER] step ${index + 1}: nothing could be drawn because the target was not found clearly. Say you can't see it clearly, describe where to look in words and ask what they see.`)
    } else {
      a.ground = null
    }
    this.armStall(a)
  }

  // Step 1 of an architect plan was already grounded (and prefetched) from the screenshot it was planned on: reuse it.
  private preciseFor(a: Active): boolean {
    return !(a.planSource === 'architect' && a.index === 0 && a.stepsVerified === 0)
  }

  private async groundStep(a: Active, step: LessonStep): Promise<GroundResult | null> {
    try {
      // With prefetch the grounder owns its screenshot (warm cache); otherwise we hand it one.
      const prefetching = typeof this.deps.grounder.prefetch === 'function'
      const shot = prefetching ? undefined : await this.deps.capture.grab('ground')
      if (!this.current(a)) return null
      const res = await this.deps.grounder.ground({ target: step.targetDescription, shot, precise: this.preciseFor(a) })
      return res.found && res.box ? res : null
    } catch (err) {
      this.log('grounding failed:', err instanceof Error ? err.message : err)
      return null
    }
  }

  private centre(box: NormBox): NormPoint {
    return { x: (box.xmin + box.xmax) / 2, y: (box.ymin + box.ymax) / 2 }
  }

  // What each level draws for a step. L3 and L4 draw nothing until the stall ladder asks.
  private present(a: Active, step: LessonStep, level: HelpLevel): void {
    const box = a.box
    if (!box || level >= 3) return
    const n = a.index + 1
    // The overlay draws the numbered badge from ring.step; no separate badge annotation.
    const annotations: Annotation[] = [{ id: 'runner-ring', kind: 'ring', tone: 'guide', box, label: truncateWords(step.instruction, 6), step: n }]
    if (level === 2) annotations.push({ id: 'runner-arrow', kind: 'arrow', tone: 'guide', to: box })
    if (level === 1) annotations.push(this.ghost(box))
    this.deps.overlay.show(annotations)
  }

  private ghost(box: NormBox): Annotation {
    const end = this.centre(box)
    const from: NormPoint = { x: Math.max(0, Math.min(1000, end.x < 500 ? end.x + 260 : end.x - 260)), y: Math.min(1000, end.y + 220) }
    const mid: NormPoint = { x: (from.x + end.x) / 2, y: Math.min(from.y, end.y) - 60 }
    return { id: 'runner-ghost', kind: 'ghostCursor', tone: 'guide', path: [from, mid, end], pressAtEnd: true }
  }

  // ---------------------------------------------------------------- stall ladder
  private armStall(a: Active, delayMs?: number): void {
    this.clearTimer(a, 'stallTimer')
    if (!this.current(a) || a.finished) return
    const scale = this.deps.getSettings().pacing === 'fast' ? 0.75 : 1
    const base = this.cfg.stallMs[a.stepLevel] * scale
    const delay = delayMs ?? (a.rung === 0 ? base : base * this.cfg.rungGapFactor)
    const token = a.token
    a.stallTimer = this.clock.setTimeout(() => {
      if (!this.active || this.active.token !== token) return
      void this.stallRung(a)
    }, delay)
  }

  async onStall(): Promise<void> {
    const a = this.active
    if (!a || a.finished) return
    await this.stallRung(a)
  }

  private async stallRung(a: Active): Promise<void> {
    if (!this.current(a) || a.finished) return
    this.clearTimer(a, 'stallTimer')
    const step = a.plan.steps[a.index]
    const index = a.index
    const level = a.stepLevel
    if (a.rung >= MAX_RUNGS[level]) return
    a.rung++
    const rung = a.rung

    // One stall episode counts once; every spoken clue or arrow after that is a hint. If the app could not
    // draw the target (grounding failed, no screen access), waiting is the app's fault, not the learner's.
    const learnerSaw = (): boolean => a.box !== null
    if (rung === 1 && (level >= 3 || learnerSaw())) this.signal(a, 'stall')
    if (level === 4) {
      this.deps.live.inject(stallDirective(level, 1, '', true))
    } else if (level === 3) {
      const res = a.ground ? await a.ground : null
      if (!this.current(a) || a.index !== index) return
      if (res?.box) a.box = res.box
      if (rung === 1) {
        if (res?.box) this.deps.overlay.show([{ id: 'runner-glow', kind: 'spotlight', tone: 'guide', box: res.box, ttlMs: 8_000 }])
        this.deps.live.inject(stallDirective(3, 1, step.hints.l3, false))
      } else if (rung === 2) {
        this.signal(a, 'hint')
        this.deps.live.inject(stallDirective(3, 2, step.hints.l3, false))
      } else {
        if (learnerSaw()) this.signal(a, 'hint')
        a.stepLevel = 2 // that step drops to Walk-with-me
        this.deps.overlay.clear(['runner-glow'])
        this.present(a, step, 2)
        this.deps.live.inject(stallDirective(3, 3, step.hints.l2, false))
      }
    } else if (level === 2) {
      if (!a.box) {
        a.ground = this.groundStep(a, step)
        a.box = (await a.ground)?.box ?? null
        if (!this.current(a) || a.index !== index) return
      }
      if (learnerSaw()) this.signal(a, 'hint')
      this.present(a, step, 2)
      this.deps.live.inject(stallDirective(2, rung === 1 ? 2 : 3, rung === 1 ? step.hints.l2 : step.hints.l1, false))
      if (rung === 2 && a.box) this.deps.overlay.show([this.ghost(a.box)])
    } else {
      // L1: show it again.
      if (a.box) this.deps.overlay.show([this.ghost(a.box)])
      this.deps.live.inject(`[STALL] The learner has not acted yet. Narrate the step once more, slowly, in different words: "${oneLine(step.hints.l1)}".`)
    }
    if (this.current(a) && a.rung < MAX_RUNGS[a.stepLevel]) this.armStall(a)
    else if (this.current(a) && !a.finished && a.index === index && a.stepLevel >= 2 && a.stepLevel <= 3) this.armAssist(a, index)
  }

  // ---------------------------------------------------------------- auto-assist on stall
  // Ladder spent and the learner still has not done the step: OFFER to click it via the existing do_it_for_me flow.
  private armAssist(a: Active, index: number): void {
    if (!this.deps.assist || this.deps.getSettings().agency === 'off') return
    const token = a.token
    // Shares the stall timer slot, so every existing teardown / step change / Stop path cancels it.
    a.stallTimer = this.clock.setTimeout(() => {
      if (!this.active || this.active.token !== token || a.index !== index) return
      void this.offerAssist(a, index) // not tracked by idle(): an open confirmation panel must not block shutdown
    }, this.cfg.assistDelayMs)
  }

  private async offerAssist(a: Active, index: number): Promise<void> {
    const assist = this.deps.assist
    if (!assist || !this.current(a) || a.finished || a.index !== index) return
    const step = a.plan.steps[index]
    const key = `${a.lessonId}:${index}`
    const state = this.deps.state.get()
    if (
      this.deps.getSettings().agency === 'off' ||
      step.safetyCritical ||
      a.safetyFlag ||
      a.skillId === 'spot_scam' ||
      state.skill?.id === 'spot_scam' ||
      state.agents.some((ag) => ag.kind === 'scam_check' && ag.status === 'running') ||
      this.assistOffered.has(key) ||
      riskWords(step.targetDescription, step.instruction)
    ) {
      return
    }
    this.assistOffered.add(key)
    this.deps.live.inject(
      '[ASSIST] The learner has not managed this step yet. Offer a choice in one warm sentence: "I can click it for you, or you can try once more. Which would you like?" A confirmation panel is on screen; only a real click on it approves. Do not click anything yourself.',
    )
    let res: DoItForMeResult
    try {
      res = await assist({ target: step.targetDescription })
    } catch (err) {
      this.log('auto-assist failed:', err instanceof Error ? err.message : err)
      return
    }
    // Stop / lesson end while the panel was open: say and do nothing more.
    if (!this.current(a) || a.finished || a.index !== index || res.code === 'stopped') return
    if (res.done && res.code === 'clicked' && !res.dryRun) {
      const label = oneLine(res.label ?? step.instruction).slice(0, 40)
      const learner = this.deps.learner as Partial<LearnerStore>
      try {
        await learner.recordDoneForMe?.(`click ${label}`)
      } catch (err) {
        this.log('doneForMe count failed:', err instanceof Error ? err.message : err)
      }
      this.deps.live.inject(`[ASSIST] You clicked "${label}" for the learner, once. Say in one short sentence what you did, then offer to show them how to do it themselves next time. Do not click again.`)
    } else if (res.code === 'declined') {
      this.deps.live.inject('[ASSIST] The learner chose to do it themselves. Encourage them and guide gently; do not click.')
    } else if (!res.done) {
      this.deps.live.inject(`[ASSIST] Nothing was clicked (${oneLine(res.reason).slice(0, 120)}). Show the learner where to click instead; they stay in control.`)
    }
  }

  // ---------------------------------------------------------------- signals and levels
  private isLocked(): boolean {
    return this.deps.getSettings().helpLevelMode === 'locked'
  }

  private signal(a: Active, kind: AttemptSignal): void {
    const before = a.attempt.current
    const { state, stepDown } = recordSignal(a.attempt, kind)
    // A locked level never moves; the counts still feed the attempt record.
    a.attempt = this.isLocked() ? { ...state, current: before } : state
    if (!stepDown || this.isLocked()) return
    const to = a.attempt.current
    this.setChip(a, to, 'extra help for the rest of this lesson', 'attempt')
    this.deps.live.inject(levelDirective(to, 'extra help for the rest of this lesson'))
    if (this.current(a) && !a.finished) {
      const step = a.plan.steps[a.index]
      a.stepLevel = this.levelForStep(a, step)
      this.present(a, step, a.stepLevel)
    }
  }

  private setChip(a: Active, level: HelpLevel, reason: string, scope: LevelChangedEvent['scope']): void {
    if (level === a.chipLevel) return
    const from = a.chipLevel
    a.chipLevel = level
    this.deps.state.patch({ level })
    this.deps.bus.emit('level:changed', { skillId: a.skillId, from, to: level, reason, scope })
  }

  async requestLevel(level: HelpLevel, reason?: string): Promise<{ applied: boolean; level: HelpLevel; note?: string }> {
    const a = this.active
    const shown = a ? a.chipLevel : this.deps.state.get().level
    if (!a || a.finished) return { applied: false, level: shown, note: 'No lesson is running, so there is nothing to change.' }
    if (this.isLocked()) return { applied: false, level: shown, note: 'The learner locked the help level.' }
    const target = clampLevel(level)
    const why = reason ?? 'asked for'
    const before = a.attempt.current
    if (detectAnxiety(why)) this.signal(a, 'anxiety')
    const from = a.attempt.current
    if (target >= from && from < before) return { applied: true, level: from, note: 'Stepped down because they sounded worried.' }
    if (target < from) {
      a.attempt = { ...a.attempt, override: a.attempt.override ?? 'show_again', current: target }
    } else if (target > from) {
      const asked = detectOverride(why) === 'let_me_try' || /\b(?:on my own|by myself|try (?:it )?(?:alone|myself))\b/i.test(why)
      if (!asked) return { applied: false, level: shown, note: 'The level goes up when you have shown you are ready. Keep going.' }
      a.attempt = { ...applyOverride(a.attempt, 'let_me_try'), current: clampLevel(Math.min(target, this.levelCap(a.plan))) }
    } else {
      return { applied: false, level: shown, note: 'Already at that level.' }
    }
    const to = a.attempt.current
    this.setChip(a, to, why, 'manual')
    this.deps.live.inject(levelDirective(to, why))
    const step = a.plan.steps[a.index]
    a.stepLevel = this.levelForStep(a, step)
    this.deps.overlay.clear(ANNOTATION_IDS)
    if (a.stepLevel <= 2) {
      if (!a.box && a.ground) a.box = (await a.ground)?.box ?? null
      this.present(a, step, a.stepLevel)
    }
    this.armStall(a)
    return { applied: true, level: to }
  }

  // Learner speech the app can classify without the model ("I'm stuck", "show me again", "let me try").
  noteUtterance(text: string): void {
    const a = this.active
    if (!a || a.finished) return
    if (detectAnxiety(text)) this.signal(a, 'anxiety')
    const override = detectOverride(text)
    if (override && !this.isLocked()) {
      a.attempt = applyOverride(a.attempt, override)
      a.attempt = { ...a.attempt, current: clampLevel(Math.min(a.attempt.current, this.levelCap(a.plan))) }
      this.setChip(a, a.attempt.current, override === 'show_again' ? 'asked to see it again' : 'asked to try alone', 'manual')
      this.deps.live.inject(levelDirective(a.attempt.current, override === 'show_again' ? 'asked to see it again' : 'asked to try alone'))
      const step = a.plan.steps[a.index]
      a.stepLevel = this.levelForStep(a, step)
      this.deps.overlay.clear(ANNOTATION_IDS)
      this.present(a, step, a.stepLevel)
      this.armStall(a)
    }
  }

  // ---------------------------------------------------------------- watching and verifying
  private onScreenChange(a: Active, _score: number): void {
    if (!this.current(a) || a.finished) return
    // Overlap: warm the next target while the verifier is still thinking.
    const next = a.plan.steps[a.index + 1]
    this.deps.grounder.invalidate?.()
    if (next) void this.deps.grounder.prefetch?.({ target: next.targetDescription, precise: true })
    this.clearTimer(a, 'verifyTimer')
    // The dock's own captions also change the screen: back off when checks keep finding nothing.
    const gap = Math.min(this.cfg.maxVerifyGapMs, this.cfg.minVerifyGapMs * 2 ** a.notYet)
    const wait = Math.max(this.cfg.verifyDebounceMs, a.lastVerifyAt + gap - this.clock.now())
    const token = a.token
    a.verifyTimer = this.clock.setTimeout(() => {
      if (!this.active || this.active.token !== token) return
      // At L4 the learner is on their own: steps are not tracked, only a silent check for the finished task.
      if (a.stepLevel >= 4) void this.endStateCheck(a)
      else void this.verifyAndAdvance(a, 'screen')
    }, wait)
  }

  async onStepDone(note?: string): Promise<StepDoneResult> {
    const a = this.active
    if (!a) return { ok: false, done: false }
    if (note) this.noteUtterance(note)
    if (a.finished) return { ok: true, done: true }
    const pending = a.verifying
    if (pending) await pending.catch(() => undefined)
    if (!this.current(a)) return { ok: false, done: false }
    if (a.finished) return { ok: true, done: true }
    if (a.stepLevel >= 4) {
      const v = await this.verifyWholeTask(a)
      return { ok: this.accepts(v), done: a.finished }
    }
    // Called right after the app itself verified and advanced (a model that calls both tools): same completion.
    if (this.clock.now() - a.advancedAt < this.cfg.ackWindowMs && a.index > 0) {
      return { ok: true, done: false, step: { index: a.index, instruction: a.plan.steps[a.index].instruction } }
    }
    const idx = a.index
    const outcome = await this.verifyAndAdvance(a, 'step_done')
    if (outcome.stale) return { ok: false, done: false }
    const ok = outcome.advanced
    const next = a.plan.steps[a.index]
    if (ok && a.finished) return { ok: true, done: true }
    return { ok, done: false, step: { index: ok ? a.index : idx, instruction: ok ? next.instruction : a.plan.steps[idx].instruction } }
  }

  async verifyStep(expectedOutcome?: string): Promise<Verdict> {
    const a = this.active
    if (!a || a.finished) {
      const shot = await this.deps.capture.grab('verify')
      return this.deps.verifier.verify({ expected: expectedOutcome ?? 'the task is complete', shot })
    }
    if (a.stepLevel >= 4) return this.verifyWholeTask(a)
    if (a.lastVerdict && this.clock.now() - a.advancedAt < this.cfg.ackWindowMs && a.index > 0) return a.lastVerdict
    const outcome = await this.verifyAndAdvance(a, 'tool')
    return outcome.verdict
  }

  // L4 checks the end state only, when the learner asks.
  private async verifyWholeTask(a: Active): Promise<Verdict> {
    const last = a.plan.steps[a.plan.steps.length - 1]
    const shot = await this.deps.capture.grab('verify')
    const verdict = await this.deps.verifier.verify({ step: last, shot })
    if (!this.current(a)) return verdict
    if (this.accepts(verdict)) {
      a.stepsVerified = a.plan.steps.length
      await this.completeLesson(a, true)
    } else {
      this.signal(a, 'hint')
    }
    return verdict
  }

  private async endStateCheck(a: Active): Promise<void> {
    if (a.verifying || !this.current(a) || a.finished) return
    const last = a.plan.steps[a.plan.steps.length - 1]
    a.lastVerifyAt = this.clock.now()
    const run = (async (): Promise<VerifyOutcome> => {
      let verdict: Verdict
      try {
        const shot = await this.deps.capture.grab('verify')
        verdict = await this.deps.verifier.verify({ step: last, shot })
      } catch {
        verdict = { completed: false, confidence: 0, evidence: 'The check could not run.', uncertain: true }
      }
      if (!this.current(a) || a.finished) return { verdict, advanced: false, stale: true }
      if (this.accepts(verdict)) {
        a.stepsVerified = a.plan.steps.length
        await this.completeLesson(a, true)
        return { verdict, advanced: true, stale: false }
      }
      a.notYet++
      return { verdict, advanced: false, stale: false }
    })().finally(() => {
      if (a.verifying === run) a.verifying = null
    })
    a.verifying = run
    await run
  }

  private accepts(v: Verdict): boolean {
    return v.completed && !v.uncertain && v.confidence >= this.cfg.minVerifyConfidence
  }

  private verifyAndAdvance(a: Active, source: 'screen' | 'step_done' | 'tool'): Promise<VerifyOutcome> {
    if (a.verifying) return a.verifying
    const run = this.verifyOnce(a, source).finally(() => {
      if (a.verifying === run) a.verifying = null
    })
    a.verifying = run
    return run
  }

  private async verifyOnce(a: Active, source: 'screen' | 'step_done' | 'tool'): Promise<VerifyOutcome> {
    const index = a.index
    const step = a.plan.steps[index]
    a.lastVerifyAt = this.clock.now()
    let verdict: Verdict
    try {
      const shot = await this.deps.capture.grab('verify')
      verdict = await this.deps.verifier.verify({ step, shot })
    } catch (err) {
      this.log('verify failed:', err instanceof Error ? err.message : err)
      verdict = { completed: false, confidence: 0, evidence: 'The check could not run.', uncertain: true }
    }
    if (!this.current(a) || a.index !== index || a.finished) return { verdict, advanced: false, stale: true }

    if (this.accepts(verdict)) {
      a.lastVerdict = verdict
      await this.onStepVerified(a, step, index, source)
      return { verdict, advanced: true, stale: false }
    }
    if (verdict.uncertain || verdict.confidence < this.cfg.minVerifyConfidence) {
      // Honest uncertainty: ask, never guess. Rate-limited so a flickering screen does not nag.
      if (source !== 'screen' && this.clock.now() - a.uncertainAt > 5_000) {
        a.uncertainAt = this.clock.now()
        this.deps.live.inject(uncertainDirective(index + 1))
      }
      return { verdict, advanced: false, stale: false }
    }
    if (verdict.learnerMisstep) await this.onMisstep(a, step, index, verdict)
    else {
      a.notYet++
      if (source !== 'screen') this.armStall(a, this.cfg.stallMs[a.stepLevel] * 0.5)
    }
    return { verdict, advanced: false, stale: false }
  }

  private async onMisstep(a: Active, step: LessonStep, index: number, verdict: Verdict): Promise<void> {
    this.clearTimer(a, 'stallTimer')
    this.signal(a, 'error')
    this.signal(a, 'hint')
    if (step.safetyCritical) a.safetyFlag = true
    this.deps.bus.emit('lesson:step', { lessonId: a.lessonId, skillId: a.skillId, stepIndex: index, stepCount: a.plan.steps.length, phase: 'repair', step })
    const hint = verdict.nextHint?.trim() || step.hints.l2
    if (!a.box && a.ground) a.box = (await a.ground)?.box ?? null
    if (!this.current(a) || a.index !== index) return
    if (a.box) {
      this.deps.overlay.show([
        { id: 'runner-ring', kind: 'ring', tone: 'warn', box: a.box, label: truncateWords(step.instruction, 6), step: index + 1 },
        { id: 'runner-arrow', kind: 'arrow', tone: 'warn', to: a.box },
      ])
    }
    this.deps.live.inject(repairDirective(index + 1, hint, verdict.learnerMisstep))
    a.rung = 0
    this.armStall(a)
  }

  private async onStepVerified(a: Active, step: LessonStep, index: number, source: 'screen' | 'step_done' | 'tool'): Promise<void> {
    this.clearTimer(a, 'stallTimer')
    this.clearTimer(a, 'verifyTimer')
    a.stepsVerified++
    // Only a screen-triggered advance can be "double reported" by a model that also calls step_done / verify_step.
    a.advancedAt = source === 'screen' ? this.clock.now() : -Infinity
    const total = a.plan.steps.length
    const last = index === total - 1
    this.deps.bus.emit('lesson:step', { lessonId: a.lessonId, skillId: a.skillId, stepIndex: index, stepCount: total, phase: 'verified', step })
    const level = a.stepLevel
    this.deps.overlay.clear(ANNOTATION_IDS.filter((id) => id !== 'runner-tick'))
    if (a.box && level <= 3) this.deps.overlay.show([{ id: 'runner-tick', kind: 'tick', tone: 'success', box: a.box, ok: true, ttlMs: this.cfg.tickMs }])
    // At L4 the learner works alone: say nothing between steps.
    const ack = level >= 4 && !last ? '' : verifiedDirective(index + 1, total, level, last)
    if (last) {
      await this.completeLesson(a, false, ack)
      return
    }
    // Adaptive fading inside the lesson: the help eases off for the remaining steps as competence shows
    // (and comes back after two struggling steps). The chip animates; the model is told in the same message.
    const done = completeStep(a.attempt, { remainingSteps: total - index - 1, locked: this.isLocked(), maxLevel: this.levelCap(a.plan) })
    a.attempt = done.state
    let lead = ack ? `${ack} ` : ''
    if (done.change !== 'none') {
      const reason = done.change === 'fade' ? 'two steps without help, so the help eases off' : 'two steps in a row needed help, so more help is back'
      this.setChip(a, done.to, reason, 'attempt')
      lead += `${levelDirective(done.to, reason)} `
    }
    // The next step starts at once: its grounding overlaps the tick and the model's acknowledgement.
    a.ground = null
    // Not awaited: index/overlay/direction are set synchronously and grounding must never hold up verification.
    this.track(this.beginStep(a, index + 1, false, lead))
  }

  private async completeLesson(a: Active, silent: boolean, lead = ''): Promise<void> {
    if (!this.current(a) || a.finished) return
    a.finished = true
    this.clearTimer(a, 'stallTimer')
    this.clearTimer(a, 'verifyTimer')
    a.unwatch?.()
    a.unwatch = null
    if (silent) this.deps.overlay.clear(ANNOTATION_IDS)
    const settings = this.deps.getSettings()
    const def = SKILLS[a.skillId]
    const rubric = a.skillId === 'custom' ? a.plan.steps.map((st) => st.instruction) : def.teachBackRubric
    this.deps.bus.emit('lesson:step', { lessonId: a.lessonId, skillId: a.skillId, stepIndex: a.plan.steps.length - 1, stepCount: a.plan.steps.length, phase: 'done' })
    this.deps.live.inject(`${lead}${lessonCompleteDirective({ skillName: this.lessonName(a), teachBack: settings.teachBack, rubric, retrievalQuestion: def.retrievalQuestion })}`)
    const token = a.token
    a.endTimer = this.clock.setTimeout(() => {
      if (!this.active || this.active.token !== token) return
      void this.end(`Finished "${this.lessonName(a)}".`)
    }, this.cfg.endTimeoutMs)
  }

  // ---------------------------------------------------------------- ending
  async end(summary: string, teachBackScore?: number, confidence?: number): Promise<void> {
    const a = this.active
    if (!a || a.ended) return
    a.ended = true
    const now = this.clock.now()
    const settings = this.deps.getSettings()
    const score = teachBackScore === undefined || Number.isNaN(teachBackScore) ? null : Math.min(1, Math.max(0, teachBackScore))
    const fromSummary = CONFIDENCE_RE.exec(summary)
    const dial = confidence ?? (fromSummary ? Number(fromSummary[1]) : undefined)
    const rating = dial !== undefined && Number.isFinite(dial) ? Math.min(5, Math.max(1, Math.round(dial))) : null
    const completed = a.finished
    const persistentBefore = a.baseState.level
    const override = a.attempt.override
    const history = this.deps.learner.snapshot().attempts.filter((x) => x.skillId === a.skillId)
    const draft: AttemptRecord = {
      id: `att-${a.lessonId}-${now}`,
      skillId: a.skillId,
      lessonId: a.lessonId,
      startedAt: a.startedAt,
      endedAt: now,
      levelAtStart: a.persistentLevel,
      levelAtEnd: a.persistentLevel,
      completed,
      hintsUsed: a.attempt.hints,
      errors: a.attempt.errors,
      stalls: a.attempt.stalls,
      safetyFlag: a.safetyFlag,
      anxietyPhrase: a.attempt.anxiety,
      teachBackScore: score,
      confidence: rating,
      clean: false,
    }
    draft.clean = isCleanAttempt(draft)
    const opts: EvaluateOptions = { demoMode: settings.demoMode, now, recentAttempts: history, override, locked: settings.helpLevelMode === 'locked' }
    // Stopping early without any struggle is not a failure; only a struggle followed by quitting steps the level down.
    const quitCalmly = !completed && a.attempt.hints + a.attempt.errors + a.attempt.stalls < 2
    const decision: LevelDecision = quitCalmly
      ? { state: { ...a.baseState, lastSeen: now }, change: 'hold', reason: 'stopped early; no change' }
      : this.deps.levels.evaluateAttempt(draft, a.baseState, opts)
    draft.levelAtEnd = decision.state.level
    // The dial belongs in the confidence log, not in the sentence the memory callback later speaks.
    const text = oneLine(summary.replace(/\bconfidence\D{0,15}[1-5](?:\s*(?:out of|\/)\s*5)?\.?/gi, '')).slice(0, 160)
    try {
      await (this.deps.learner as AttemptSink).recordAttempt(draft, { decision, override, summary: text || undefined })
    } catch (err) {
      this.log('could not save the attempt:', err instanceof Error ? err.message : err)
    }
    // The fade becomes visible: the chip moves to the level the learner has earned.
    this.setChip(a, decision.state.level, decision.reason, 'skill')
    this.log(`attempt ended: ${a.skillId} ${persistentBefore} -> ${decision.state.level} (${decision.change}): ${decision.reason}`)
    await this.teardown('ended', false)
  }

  async abort(reason = 'aborted'): Promise<void> {
    this.startSeq++ // also cancels a start() that is still planning
    const a = this.active
    if (!a) return
    // A learner who finished every step but never got to the teach-back still gets their attempt counted.
    if (a.finished && !a.ended) {
      await this.end(`Finished "${this.lessonName(a)}".`)
      return
    }
    await this.teardown(reason, true)
  }

  private async teardown(reason: string, resetChip: boolean): Promise<void> {
    const a = this.active
    if (!a) return
    this.clearTimer(a, 'stallTimer')
    this.clearTimer(a, 'verifyTimer')
    this.clearTimer(a, 'endTimer')
    a.unwatch?.()
    a.unwatch = null
    a.token = -1
    this.active = null
    this.deps.overlay.clear(ANNOTATION_IDS)
    if (reason !== 'ended') {
      this.deps.bus.emit('lesson:step', { lessonId: a.lessonId, skillId: a.skillId, stepIndex: a.index, stepCount: a.plan.steps.length, phase: 'aborted' })
    }
    if (resetChip && !this.isLocked()) this.setChip(a, a.persistentLevel, `lesson stopped (${oneLine(reason)})`, 'attempt')
    this.deps.state.patch({ skill: undefined })
  }

  private clearTimer(a: Active, key: 'stallTimer' | 'verifyTimer' | 'endTimer'): void {
    if (a[key] !== null) this.clock.clearTimeout(a[key])
    a[key] = null
  }

  private log(...args: unknown[]): void {
    this.deps.log?.('runner', ...args)
  }
}

export function createLessonRunner(deps: RunnerDeps): LessonRunnerImpl {
  return new LessonRunnerImpl(deps)
}
