import { beforeEach, describe, expect, it } from 'vitest'
import type { Capture, LessonArchitect, Verifier } from '../../../shared/contracts'
import type {
  Annotation,
  CompanionState,
  DoItForMeResult,
  GroundResult,
  HelpLevel,
  LessonPlan,
  LessonStepEvent,
  LevelChangedEvent,
  NormBox,
  SkillId,
  Verdict,
} from '../../../shared/protocol'
import { DEFAULT_SETTINGS } from '../../../shared/settings'
import type { Settings } from '../../../shared/settings'
import { TeachingLearnerStore } from '../learner-store'
import { levelEngine } from '../levels'
import { LessonRunnerImpl } from '../runner'
import type { Clock, RunnerConfig, RunnerDeps } from '../runner'
import { pickSkill } from '../skills/definitions'
import { fallbackPlan } from '../skills/plans'

// ---------- fakes ----------
class FakeClock implements Clock {
  t = Date.UTC(2026, 9, 31, 14, 0, 0)
  private seq = 0
  private timers = new Map<number, { at: number; fn: () => void }>()
  now = (): number => this.t
  setTimeout = (fn: () => void, ms: number): number => {
    const id = ++this.seq
    this.timers.set(id, { at: this.t + ms, fn })
    return id
  }
  clearTimeout = (h: unknown): void => {
    this.timers.delete(h as number)
  }
  pending(): number {
    return this.timers.size
  }
  async advance(ms: number): Promise<void> {
    const target = this.t + ms
    for (;;) {
      const due = [...this.timers.entries()].filter(([, v]) => v.at <= target).sort((a, b) => a[1].at - b[1].at || a[0] - b[0])
      if (!due.length) break
      const [id, timer] = due[0]
      this.timers.delete(id)
      this.t = Math.max(this.t, timer.at)
      timer.fn()
      await flush()
    }
    this.t = target
    await flush()
  }
}

async function flush(): Promise<void> {
  for (let i = 0; i < 40; i++) await Promise.resolve()
}

const BOX: NormBox = { xmin: 100, ymin: 200, xmax: 300, ymax: 280 }
const OK: Verdict = { completed: true, confidence: 0.92, evidence: 'looks right', uncertain: false }
const NOT_YET: Verdict = { completed: false, confidence: 0.9, evidence: 'nothing yet', uncertain: false }

interface Rig {
  clock: FakeClock
  runner: LessonRunnerImpl
  store: TeachingLearnerStore
  injects: string[]
  shown: Annotation[][]
  cleared: (string[] | undefined)[]
  levelEvents: LevelChangedEvent[]
  stepEvents: LessonStepEvent[]
  state: { cur: CompanionState; get(): CompanionState; patch(p: Partial<CompanionState>): void }
  watch: { fire(score?: number): void; subs: number }
  verdicts: Verdict[]
  verifyCalls: number
  groundCalls: { target: string; hasShot: boolean; precise?: boolean }[]
  prefetchCalls: string[]
  prefetchPrecise: (boolean | undefined)[]
  grabs: string[]
  groundResult: { current: GroundResult | null; delay: Promise<void> | null }
  architect: { impl: LessonArchitect['plan']; calls: Parameters<LessonArchitect['plan']>[0][] }
  settings: Settings
  last(n?: number): string
  settle(): Promise<void>
  sawShown(id: string): boolean
}

function makeRig(opts: { settings?: Partial<Settings>; prefetch?: boolean; stateLevel?: HelpLevel; config?: Partial<RunnerConfig>; assist?: RunnerDeps['assist'] } = {}): Rig {
  const clock = new FakeClock()
  const settings: Settings = { ...DEFAULT_SETTINGS, ...opts.settings }
  const injects: string[] = []
  const shown: Annotation[][] = []
  const cleared: (string[] | undefined)[] = []
  const levelEvents: LevelChangedEvent[] = []
  const stepEvents: LessonStepEvent[] = []
  const verdicts: Verdict[] = []
  const groundCalls: Rig['groundCalls'] = []
  const prefetchCalls: string[] = []
  const prefetchPrecise: (boolean | undefined)[] = []
  const grabs: string[] = []
  const groundResult: Rig['groundResult'] = {
    current: { found: true, box: BOX, point: undefined, confidence: 0.9, label: 'x', latencyMs: 5, model: 'fake' },
    delay: null,
  }
  const watch = { cb: null as null | ((s: number) => void), subs: 0, fire(score = 0.4) { this.cb?.(score) } }
  const state = {
    cur: {
      persona: 'marcus', phase: 'live', micMuted: false, level: opts.stateLevel ?? 2, levelLocked: false, captions: [], agents: [], settings,
    } as CompanionState,
    get() { return this.cur },
    patch(p: Partial<CompanionState>) { this.cur = { ...this.cur, ...p } },
  }
  const store = new TeachingLearnerStore({ dir: null, now: clock.now, engine: levelEngine, getSettings: () => settings })
  const capture: Capture = {
    async grab(purpose) {
      grabs.push(purpose)
      return { id: `s${grabs.length}`, displayId: 1, widthPx: 100, heightPx: 100, scaleFactor: 1, jpegBase64: 'x', takenAt: 0, overlayHidden: true }
    },
    async liveFrame() {
      return { jpegBase64: 'x', changeScore: 0 }
    },
    watch(on) {
      watch.cb = on
      watch.subs++
      return () => {
        watch.subs--
        watch.cb = null
      }
    },
  }
  const verifier: Verifier = {
    async verify() {
      rig.verifyCalls++
      return verdicts.shift() ?? NOT_YET
    },
  }
  const architect = { impl: (async (req) => fallbackPlan(pickSkill(req.goal) ?? 'video_call', req.goal)) as LessonArchitect['plan'], calls: [] as Parameters<LessonArchitect['plan']>[0][] }
  const grounder = {
    async ground(req: { target: string; shot?: unknown; precise?: boolean }): Promise<GroundResult> {
      groundCalls.push({ target: req.target, hasShot: req.shot !== undefined, precise: req.precise })
      if (groundResult.delay) await groundResult.delay
      return groundResult.current ?? { found: false, confidence: 0.1, latencyMs: 1, model: 'fake', reason: 'not sure' }
    },
    ...(opts.prefetch ? { prefetch: (r: { target: string; precise?: boolean }) => (prefetchCalls.push(r.target), void prefetchPrecise.push(r.precise)) } : {}),
  }
  const runner = new LessonRunnerImpl({
    capture,
    grounder,
    verifier,
    architect: { plan: (req) => (architect.calls.push(req), architect.impl(req)) },
    overlay: {
      show: (a) => void shown.push(a),
      clear: (ids) => void cleared.push(ids),
      caption: () => undefined,
      chip: () => undefined,
    },
    live: { inject: (t) => void injects.push(t) },
    learner: store,
    levels: levelEngine,
    state,
    bus: {
      emit: ((event: string, payload: unknown) => {
        if (event === 'level:changed') levelEvents.push(payload as LevelChangedEvent)
        else stepEvents.push(payload as LessonStepEvent)
      }) as never,
    },
    getSettings: () => settings,
    clock,
    config: opts.config,
    ...(opts.assist ? { assist: opts.assist } : {}),
  })
  const rig: Rig = {
    clock, runner, store, injects, shown, cleared, levelEvents, stepEvents, state, watch: watch as never, verdicts, verifyCalls: 0, groundCalls, prefetchCalls, prefetchPrecise, grabs,
    groundResult, architect, settings,
    last: (n = 1) => injects.slice(-n).join(' || '),
    settle: async () => {
      await flush()
      await runner.idle()
      await flush()
    },
    sawShown: (id) => shown.some((batch) => batch.some((a) => a.id === id)),
  }
  return rig
}

async function startLesson(rig: Rig, goal = 'I want to call Lily'): Promise<{ lessonId: string; skillId: SkillId; stepCount: number }> {
  const res = await rig.runner.start(goal)
  await rig.clock.advance(0)
  await rig.settle()
  return res
}

// Learner acts: the screen changes, the debounce passes, the verifier answers.
async function actAndVerify(rig: Rig, verdict: Verdict = OK): Promise<void> {
  rig.verdicts.push(verdict)
  rig.watch.fire()
  await rig.clock.advance(1_600)
  await rig.settle()
}

let rig: Rig
beforeEach(() => {
  rig = makeRig()
})

// ---------- tests ----------
describe('happy path at level 2', () => {
  it('starts, directs the model first, draws ring/arrow/badge, ticks and finishes', async () => {
    await rig.store.setSkillLevel('video_call', 2, { lastSeen: rig.clock.now() - 1000 })
    const res = await startLesson(rig)
    expect(res).toMatchObject({ skillId: 'video_call', stepCount: 5 })
    expect(rig.runner.running).toBe(true)
    expect(rig.state.cur.skill).toMatchObject({ id: 'video_call', step: 1, stepCount: 5 })
    expect(rig.injects[0]).toContain('lesson "Start a video call" started')
    expect(rig.injects[0]).toContain('step 1 of 5, level 2 "Walk with me"')
    const first = rig.shown[0]
    expect(first.map((a) => a.kind).sort()).toEqual(['arrow', 'ring'])
    expect(first.find((a) => a.kind === 'ring')).toMatchObject({ box: BOX, step: 1 })

    for (let i = 1; i <= 4; i++) {
      await actAndVerify(rig)
      expect(rig.state.cur.skill?.step).toBe(i + 1)
      expect(rig.last()).toContain(`step ${i} of 5 verified`)
      expect(rig.last()).toContain(`step ${i + 1} of 5`)
    }
    expect(rig.shown.some((b) => b.some((a) => a.kind === 'tick' && a.tone === 'success'))).toBe(true)

    await actAndVerify(rig)
    expect(rig.last()).toContain('That was the last step')
    expect(rig.last()).toContain('teach-back')
    expect(rig.watch.subs).toBe(0)

    await rig.runner.end('Learned to start a video call. Confidence 4 out of 5.', 0.9)
    const snap = rig.store.snapshot()
    expect(snap.attempts).toHaveLength(1)
    expect(snap.attempts[0]).toMatchObject({ skillId: 'video_call', completed: true, hintsUsed: 0, errors: 0, stalls: 0, clean: true, teachBackScore: 0.9, confidence: 4, levelAtStart: 2, levelAtEnd: 3 })
    expect(snap.skills.video_call.level).toBe(3)
    expect(snap.lastSession?.summary).toContain('video call')
    // the chip already eased off inside the lesson (after step 2); finishing confirms it for next time
    expect(rig.levelEvents.at(-1)).toMatchObject({ from: 2, to: 3, scope: 'attempt' })
    expect(rig.state.cur.level).toBe(3)
    expect(rig.state.cur.skill).toBeUndefined()
    expect(rig.runner.running).toBe(false)
    expect(rig.stepEvents.map((e) => e.phase)).toContain('done')
  })

  it('never blocks narration on grounding: the direction is sent before the screen is read', async () => {
    let release!: () => void
    rig.groundResult.delay = new Promise<void>((r) => (release = r))
    await rig.runner.start('call Lily')
    await rig.clock.advance(0)
    await flush()
    expect(rig.injects).toHaveLength(1)
    expect(rig.injects[0]).toContain('step 1 of 5')
    expect(rig.shown).toHaveLength(0)
    release()
    await rig.settle()
    expect(rig.shown.length).toBeGreaterThan(0)
  })

  it('uses prefetch when the grounder has it: warm the next target on screen change, ground without a shot', async () => {
    rig = makeRig({ prefetch: true })
    await startLesson(rig)
    expect(rig.prefetchCalls[0]).toContain('VideoChat')
    expect(rig.groundCalls[0].hasShot).toBe(false)
    rig.watch.fire()
    expect(rig.prefetchCalls.at(-1)).toContain('Lily')
    await rig.clock.advance(1_600)
    await rig.settle()
  })

  it('grounds and prefetches EVERY step precisely, and warms step 1 the moment start_lesson begins', async () => {
    rig = makeRig({ prefetch: true })
    await rig.runner.start('I want to call Lily')
    // before the first tick: step 1's target is already being fetched, precisely
    expect(rig.prefetchCalls).toHaveLength(1)
    expect(rig.prefetchCalls[0]).toContain('VideoChat')
    await rig.clock.advance(0)
    await rig.settle()
    rig.watch.fire()
    await rig.clock.advance(1_600)
    await actAndVerify(rig)
    await actAndVerify(rig)
    expect(rig.prefetchPrecise.length).toBeGreaterThan(2)
    expect(rig.prefetchPrecise.every((p) => p === true)).toBe(true)
    expect(rig.groundCalls.length).toBeGreaterThan(0)
    expect(rig.groundCalls.every((g) => g.precise === true)).toBe(true)
  })

  it('hands the grounder a shot when it has no prefetch', async () => {
    await startLesson(rig)
    expect(rig.groundCalls[0].hasShot).toBe(true)
    expect(rig.grabs).toContain('ground')
  })

  it('step_done verifies at once and reports the next step', async () => {
    await startLesson(rig)
    rig.verdicts.push(OK)
    const res = await rig.runner.onStepDone('I clicked it')
    expect(res).toMatchObject({ ok: true, done: false, step: { index: 1 } })
    expect(res.step?.instruction).toContain('Lily')
    rig.verdicts.push(NOT_YET)
    expect(await rig.runner.onStepDone()).toMatchObject({ ok: false, done: false, step: { index: 1 } })
  })

  it('step_done on the last step reports done', async () => {
    await rig.store.setSkillLevel('bigger_text', 2)
    await startLesson(rig, 'make the text bigger')
    for (let i = 0; i < 2; i++) {
      rig.verdicts.push(OK)
      await rig.runner.onStepDone()
    }
    rig.verdicts.push(OK)
    expect(await rig.runner.onStepDone()).toEqual({ ok: true, done: true })
    expect(await rig.runner.onStepDone()).toEqual({ ok: true, done: true })
  })

  it('verifyStep without a lesson verifies the stated outcome', async () => {
    rig.verdicts.push(OK)
    expect(await rig.runner.verifyStep('the call screen is showing')).toEqual(OK)
    expect(await rig.runner.onStepDone()).toEqual({ ok: false, done: false })
  })
})

describe('wrong tap, uncertainty and honest limits', () => {
  it('repairs a wrong tap calmly and counts it as an error and a hint', async () => {
    await startLesson(rig)
    await actAndVerify(rig, { completed: false, confidence: 0.9, evidence: 'opened Files', uncertain: false, learnerMisstep: 'opened the Files app', nextHint: 'The camera icon is the top one.' })
    expect(rig.last()).toContain('did not work')
    expect(rig.last()).toContain('opened the Files app')
    expect(rig.last()).toContain('The camera icon is the top one.')
    const repair = rig.shown.at(-1) ?? []
    expect(repair.find((a) => a.kind === 'ring')).toMatchObject({ tone: 'warn', box: BOX })
    expect(rig.stepEvents.map((e) => e.phase)).toContain('repair')
    expect(rig.state.cur.skill?.step).toBe(1)
    await actAndVerify(rig)
    expect(rig.state.cur.skill?.step).toBe(2)
    for (let i = 0; i < 3; i++) await actAndVerify(rig)
    await actAndVerify(rig)
    await rig.runner.end('done', 0.8)
    expect(rig.store.snapshot().attempts[0]).toMatchObject({ errors: 1, hintsUsed: 1, clean: true })
  })

  it('two wrong taps on a step drop the lesson one level and say so', async () => {
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    const wrong: Verdict = { completed: false, confidence: 0.9, evidence: 'x', uncertain: false, learnerMisstep: 'wrong place' }
    await actAndVerify(rig, wrong)
    await actAndVerify(rig, wrong)
    expect(rig.levelEvents.some((e) => e.scope === 'attempt' && e.to === 2)).toBe(true)
    expect(rig.injects.some((t) => t.includes('level=2 "Walk with me"'))).toBe(true)
    expect(rig.state.cur.level).toBe(2)
  })

  it('uncertain verdicts ask instead of guessing and are never counted', async () => {
    await startLesson(rig)
    rig.verdicts.push({ completed: false, confidence: 0.3, evidence: 'blurry', uncertain: true })
    await rig.runner.onStepDone()
    expect(rig.last()).toContain("I can't quite see that")
    // the same uncertainty from the screen watcher does not nag
    const before = rig.injects.length
    await actAndVerify(rig, { completed: false, confidence: 0.3, evidence: 'blurry', uncertain: true })
    expect(rig.injects).toHaveLength(before)
    // low-confidence "completed" is not accepted either
    await actAndVerify(rig, { completed: true, confidence: 0.4, evidence: 'maybe', uncertain: false })
    expect(rig.state.cur.skill?.step).toBe(1)
  })

  it('a verifier outage is treated as uncertain, not as a wrong tap', async () => {
    await startLesson(rig)
    ;(rig.runner as unknown as { deps: { verifier: Verifier } }).deps.verifier = {
      verify: async () => {
        throw new Error('network')
      },
    }
    const res = await rig.runner.onStepDone()
    expect(res.ok).toBe(false)
    expect(rig.last()).toContain("I can't quite see that")
  })

  it('repeated not-yet checks back off so the dock captions cannot burn the verifier', async () => {
    await startLesson(rig)
    const before = rig.verifyCalls
    for (let i = 0; i < 6; i++) {
      rig.verdicts.push(NOT_YET)
      rig.watch.fire()
      await rig.clock.advance(1_000)
    }
    expect(rig.verifyCalls - before).toBeLessThanOrEqual(3)
  })

  it('not-yet verdicts without a misstep cost nothing', async () => {
    await startLesson(rig)
    await actAndVerify(rig, NOT_YET)
    expect(rig.state.cur.skill?.step).toBe(1)
    expect(rig.stepEvents.map((e) => e.phase)).not.toContain('repair')
  })

  it('says it cannot draw when grounding fails', async () => {
    rig.groundResult.current = null
    await startLesson(rig)
    expect(rig.sawShown('runner-ring')).toBe(false)
    expect(rig.injects.some((t) => t.includes('nothing could be drawn'))).toBe(true)
  })

  it('waiting on a step the app could not draw is not held against the learner', async () => {
    rig.groundResult.current = null
    await rig.store.setSkillLevel('video_call', 2)
    await startLesson(rig)
    await rig.clock.advance(12_000)
    await rig.clock.advance(9_000)
    expect(rig.last()).toContain('See the little camera picture') // the model still gets the clues
    await rig.runner.end('gave up')
    const a = rig.store.snapshot().attempts[0]
    expect(a).toMatchObject({ hintsUsed: 0, stalls: 0 })
    expect(rig.store.snapshot().skills.video_call.level).toBe(2) // no demotion for the app's failure
  })

  it('treats a grounder that throws like not found', async () => {
    ;(rig.runner as unknown as { deps: { grounder: { ground: () => Promise<never> } } }).deps.grounder.ground = async () => {
      throw new Error('boom')
    }
    await startLesson(rig)
    expect(rig.sawShown('runner-ring')).toBe(false)
    expect(rig.runner.running).toBe(true)
  })

  it('a misstep on a safety-critical step sets the safety flag, so the attempt is not clean', async () => {
    await rig.store.setSkillLevel('spot_scam', 2)
    await startLesson(rig, 'is this text a scam?')
    await actAndVerify(rig)
    await actAndVerify(rig)
    expect(rig.state.cur.skill?.step).toBe(3)
    await actAndVerify(rig, { completed: false, confidence: 0.9, evidence: 'link opened', uncertain: false, learnerMisstep: 'tapped the link' })
    await actAndVerify(rig)
    await actAndVerify(rig)
    await actAndVerify(rig)
    await rig.runner.end('done', 1)
    expect(rig.store.snapshot().attempts[0]).toMatchObject({ safetyFlag: true, clean: false })
    expect(rig.store.snapshot().skills.spot_scam.level).toBe(2)
  })
})

describe('stall ladder', () => {
  it('level 3: draws nothing, then glow, spoken clue, arrow (step drops to L2)', async () => {
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    expect(rig.state.cur.level).toBe(3)
    expect(rig.sawShown('runner-ring')).toBe(false)
    expect(rig.injects[0]).toContain('Say only the goal')

    await rig.clock.advance(7_999)
    expect(rig.injects).toHaveLength(1)
    await rig.clock.advance(1)
    expect(rig.shown.at(-1)?.[0]).toMatchObject({ kind: 'spotlight', box: BOX })
    expect(rig.last()).toContain('[STALL]')
    expect(rig.last()).toContain('soft glow')

    await rig.clock.advance(6_000)
    expect(rig.last()).toContain('Give this clue')
    expect(rig.last()).toContain('Look along the left edge')
    expect(rig.sawShown('runner-ring')).toBe(false)

    await rig.clock.advance(6_000)
    expect(rig.last()).toContain('An arrow is now showing')
    expect(rig.sawShown('runner-ring')).toBe(true)
    expect(rig.sawShown('runner-arrow')).toBe(true)
    // two hints on one step: the rest of the attempt is at L2
    expect(rig.levelEvents.some((e) => e.scope === 'attempt' && e.to === 2)).toBe(true)
    const injected = rig.injects.length
    await rig.clock.advance(60_000)
    expect(rig.injects).toHaveLength(injected) // ladder exhausted: no more nagging
  })

  it('level 2: re-points with the l2 hint, then a ghost-cursor demo of the step', async () => {
    await rig.store.setSkillLevel('video_call', 2)
    await startLesson(rig)
    await rig.clock.advance(12_000)
    expect(rig.last()).toContain('Click the teal VideoChat icon')
    await rig.clock.advance(9_000)
    expect(rig.last()).toContain('See the little camera picture')
    expect(rig.shown.at(-1)?.[0]).toMatchObject({ kind: 'ghostCursor', pressAtEnd: true })
  })

  it('level 4: only a gentle offer, once', async () => {
    await rig.store.setSkillLevel('video_call', 4)
    await startLesson(rig)
    expect(rig.injects[0]).toContain('Stay silent')
    expect(rig.sawShown('runner-ring')).toBe(false)
    expect(rig.groundCalls).toHaveLength(0)
    await rig.clock.advance(20_000)
    expect(rig.last()).toContain('Would you like a hint?')
    const n = rig.injects.length
    await rig.clock.advance(120_000)
    expect(rig.injects).toHaveLength(n)
  })

  it('level 1: repeats the demo', async () => {
    await startLesson(rig)
    expect(rig.state.cur.level).toBe(1)
    expect(rig.injects[0]).toContain('ghost cursor')
    expect(rig.shown[0].map((a) => a.kind)).toContain('ghostCursor')
    await rig.clock.advance(15_000)
    expect(rig.last()).toContain('once more')
  })

  it('onStall() advances the ladder on demand, and does nothing when idle', async () => {
    await rig.runner.onStall()
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    await rig.runner.onStall()
    expect(rig.last()).toContain('soft glow')
    await rig.runner.onStall()
    expect(rig.last()).toContain('Give this clue')
  })

  it('a verified step cancels the stall timer; fast pacing shortens it', async () => {
    rig = makeRig({ settings: { pacing: 'fast' } })
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    await rig.clock.advance(6_000)
    expect(rig.last()).toContain('soft glow')
    await actAndVerify(rig)
    const n = rig.injects.length
    await rig.clock.advance(1_000)
    expect(rig.injects).toHaveLength(n)
  })
})

const mutePlan = (): LessonPlan => ({
  lessonId: 'argon-mute',
  skillId: 'bigger_text', // Argon's guess is ignored: novel goals are one generic "custom" skill
  goal: 'ignored',
  steps: [
    {
      id: 'mute.find',
      index: 0,
      instruction: 'Find the microphone button in the bar at the bottom of the call.',
      targetDescription: 'round microphone button in the bottom control bar of the call screen',
      expectedOutcome: 'The microphone button is highlighted',
      hints: { l1: 'The microphone is the round button on the left of the bottom bar.', l2: 'Look at the bottom bar for the microphone.', l3: 'Bottom of the call window.' },
      safetyCritical: false,
    },
    {
      id: 'mute.press',
      index: 1,
      instruction: 'Click the microphone button once to mute yourself. Please go and do this slowly and calmly right now thanks very much indeed.',
      targetDescription: 'round microphone button in the bottom control bar of the call screen',
      expectedOutcome: 'The microphone icon has a red line through it',
      hints: { l1: 'One click mutes you.', l2: 'Click the microphone once.', l3: 'The same round button.' },
      safetyCritical: false,
    },
  ],
})

describe('plan: built-in skills start instantly, novel goals are planned by Argon from the screen', () => {
  it('a built-in goal starts at once from its static plan: no architect call, no screenshot, no waiting', async () => {
    const res = await rig.runner.start('I want to call Lily')
    expect(res).toMatchObject({ skillId: 'video_call', stepCount: 5 })
    expect(res.lessonId).toMatch(/^fallback-video_call/)
    expect(rig.architect.calls).toHaveLength(0)
    expect(rig.grabs).toHaveLength(0)
    expect(rig.injects).toHaveLength(0) // nothing before the first step direction
    await rig.clock.advance(0)
    await rig.settle()
    expect(rig.injects[0]).toContain('step 1 of 5')
  })

  it.each([
    ['is this text a scam?', 'spot_scam'],
    ['make the text bigger', 'bigger_text'],
  ])('%s -> %s without Argon', async (goal, skill) => {
    expect((await rig.runner.start(goal)).skillId).toBe(skill)
    expect(rig.architect.calls).toHaveLength(0)
  })

  it('a novel goal: keeps the model talking, plans from the live screenshot, runs as the generic custom skill', async () => {
    rig.architect.impl = async () => mutePlan()
    const res = await rig.runner.start('how do I mute myself?')
    expect(rig.injects[0]).toContain('The learner asked for something new: "how do I mute myself?"')
    expect(rig.injects[0]).toContain('Do not guess any steps yet')
    expect(rig.architect.calls).toHaveLength(1)
    expect(rig.architect.calls[0]).toMatchObject({ goal: 'how do I mute myself?' })
    expect(rig.architect.calls[0].shot).toBeDefined()
    expect(rig.grabs[0]).toBe('ground')
    expect(res).toEqual({ lessonId: 'argon-mute', skillId: 'custom', stepCount: 2 })
    await rig.clock.advance(0)
    await rig.settle()
    expect(rig.state.cur.skill).toMatchObject({ id: 'custom', name: 'how do I mute myself?', step: 1, stepCount: 2 })
    expect(rig.state.cur.level).toBe(1) // a brand-new generic skill starts at Watch me
    const direction = rig.injects.find((t) => t.includes('step 1 of 2'))!
    expect(direction).toContain('lesson "how do I mute myself?" started')
    expect(rig.shown[0].map((a) => a.kind)).toContain('ghostCursor')
    await actAndVerify(rig)
    await actAndVerify(rig)
    expect(rig.last()).toContain('teach-back')
    expect(rig.last()).toContain('Find the microphone button') // the rubric for a custom lesson is its own steps
    // instructions from Argon are capped at 20 words
    expect(rig.injects.some((t) => t.includes('indeed'))).toBe(false)
    await rig.runner.end('Learned how to mute. Confidence 5.', 0.9, 5)
    const snap = rig.store.snapshot()
    expect(snap.skills.custom).toBeDefined()
    expect(snap.skills.custom?.level).toBe(2)
    expect(snap.attempts[0]).toMatchObject({ skillId: 'custom', completed: true, clean: true })
    expect(snap.lastSession?.summary).toBe('Learned how to mute.')
    expect(rig.store.snapshot().skills.video_call.level).toBe(1) // built-in levels untouched
  })

  it('an architect plan reuses the architect\'s own step-1 grounding (not precise, no new prefetch); later steps are precise', async () => {
    rig = makeRig({ prefetch: true })
    rig.architect.impl = async () => mutePlan()
    await rig.runner.start('how do I mute myself?')
    expect(rig.prefetchCalls).toHaveLength(0)
    await rig.clock.advance(0)
    await rig.settle()
    expect(rig.groundCalls[0].precise).toBe(false)
    expect(rig.prefetchCalls).toHaveLength(0)
    rig.verdicts.push(OK)
    rig.watch.fire() // warms step 2 precisely
    expect(rig.prefetchPrecise.at(-1)).toBe(true)
    await rig.clock.advance(1_600)
    await rig.settle()
    expect(rig.groundCalls.slice(1).every((g) => g.precise === true)).toBe(true)
  })

  it('the custom skill shows up in the profile file and the built-ins stay put', async () => {
    rig.architect.impl = async () => mutePlan()
    await startLesson(rig, 'how do I mute myself?')
    await actAndVerify(rig)
    await actAndVerify(rig)
    await rig.runner.end('done', 1)
    const text = (await rig.store.editMarkdown({ op: 'read' })).content
    expect(text).toContain('| Something new |')
    expect(text).not.toContain('Start a video call')
  })

  it('Argon taking too long: honest pointer fallback after 15 s, never a built-in lesson', async () => {
    rig.architect.impl = () => new Promise(() => undefined)
    let result: { lessonId: string; skillId: SkillId; stepCount: number } | null = null
    const p = rig.runner.start('how do I mute myself?').then((r) => (result = r))
    await flush()
    await rig.clock.advance(14_999)
    expect(result).toBeNull()
    await rig.clock.advance(1)
    await p
    expect(result).toMatchObject({ skillId: 'custom', stepCount: 1 })
    expect((result as unknown as { lessonId: string }).lessonId).toMatch(/^pointer-/)
    await rig.clock.advance(0)
    await rig.settle()
    expect(rig.injects.some((t) => t.includes('could not be worked out in time') && t.includes('step 1 of 1'))).toBe(true)
    expect(rig.state.cur.skill?.stepCount).toBe(1)
    // the one step looks for exactly what was asked about
    expect(rig.groundCalls[0].target).toBe('how do I mute myself?')
  })

  it('Argon failing or returning junk also ends in the pointer, not a wrong lesson', async () => {
    rig.architect.impl = async () => {
      throw new Error('503')
    }
    expect(await rig.runner.start('help me with my email')).toMatchObject({ skillId: 'custom', stepCount: 1 })
    rig.architect.impl = (async () => ({ nonsense: true })) as never
    expect(await rig.runner.start('how do I attach a photo?')).toMatchObject({ skillId: 'custom', stepCount: 1 })
  })

  it('no screenshot (no screen access) still lets the architect try; then points', async () => {
    ;(rig.runner as unknown as { deps: { capture: Capture } }).deps.capture = {
      grab: async () => {
        throw new Error('no screen access')
      },
      liveFrame: async () => ({ jpegBase64: '', changeScore: 0 }),
      watch: () => () => undefined,
    }
    rig.architect.impl = async () => {
      throw new Error('needs a screenshot')
    }
    const res = await rig.runner.start('how do I mute myself?')
    expect(res.skillId).toBe('custom')
    expect(rig.architect.calls[0].shot).toBeUndefined()
  })

  it('ALONGSIDE_PLAN_TIMEOUT_MS style override shortens the wait', async () => {
    rig = makeRig({ config: { planTimeoutMs: 3_000 } })
    rig.architect.impl = () => new Promise(() => undefined)
    let done = false
    const p = rig.runner.start('how do I mute myself?').then(() => (done = true))
    await flush()
    await rig.clock.advance(3_000)
    await p
    expect(done).toBe(true)
  })

  it('starting a new lesson replaces the old one cleanly', async () => {
    await startLesson(rig)
    const res = await rig.runner.start('make the text bigger')
    await rig.clock.advance(0)
    await rig.settle()
    expect(res.skillId).toBe('bigger_text')
    expect(rig.watch.subs).toBe(1)
    expect(rig.store.snapshot().attempts).toHaveLength(0)
  })
})

describe('abort', () => {
  it('stops everything mid-step: no timers, no drawings, no attempt, chip back', async () => {
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    await rig.clock.advance(8_000)
    await rig.runner.abort('session ended: stop')
    expect(rig.runner.running).toBe(false)
    expect(rig.state.cur.skill).toBeUndefined()
    expect(rig.watch.subs).toBe(0)
    expect(rig.cleared.at(-1)).toContain('runner-ring')
    expect(rig.stepEvents.at(-1)?.phase).toBe('aborted')
    const n = rig.injects.length
    await rig.clock.advance(300_000)
    expect(rig.injects).toHaveLength(n)
    expect(rig.clock.pending()).toBe(0)
    expect(rig.store.snapshot().attempts).toHaveLength(0)
    await rig.runner.abort() // idempotent
  })

  it('a verification that returns after abort is ignored', async () => {
    await startLesson(rig)
    let release!: (v: Verdict) => void
    ;(rig.runner as unknown as { deps: { verifier: Verifier } }).deps.verifier = { verify: () => new Promise<Verdict>((r) => (release = r)) }
    const pending = rig.runner.onStepDone()
    await flush()
    await rig.runner.abort('x')
    release(OK)
    expect(await pending).toEqual({ ok: false, done: false })
    expect(rig.stepEvents.map((e) => e.phase)).not.toContain('verified')
  })

  it('grounding that finishes after abort draws nothing', async () => {
    let release!: () => void
    rig.groundResult.delay = new Promise<void>((r) => (release = r))
    await rig.runner.start('call Lily')
    await rig.clock.advance(0)
    await flush()
    await rig.runner.abort('x')
    release()
    await rig.settle()
    expect(rig.shown).toHaveLength(0)
  })

  it('aborting after the last step still counts the finished attempt', async () => {
    await rig.store.setSkillLevel('bigger_text', 2)
    await startLesson(rig, 'make the text bigger')
    for (let i = 0; i < 3; i++) await actAndVerify(rig)
    await rig.runner.abort('session ended: goodbye')
    const snap = rig.store.snapshot()
    expect(snap.attempts).toHaveLength(1)
    expect(snap.attempts[0].completed).toBe(true)
    expect(snap.attempts[0].teachBackScore).toBeNull()
    expect(snap.skills.bigger_text.level).toBe(3)
  })

  it('the end timeout closes the attempt if the model never calls end_lesson', async () => {
    await rig.store.setSkillLevel('bigger_text', 2)
    await startLesson(rig, 'make the text bigger')
    for (let i = 0; i < 3; i++) await actAndVerify(rig)
    expect(rig.store.snapshot().attempts).toHaveLength(0)
    await rig.clock.advance(90_000)
    expect(rig.store.snapshot().attempts).toHaveLength(1)
    expect(rig.runner.running).toBe(false)
  })
})

describe('a model that calls both step_done and verify_step is not double-stepped', () => {
  it('step_done / verify_step right after the app advanced acknowledge that step instead of checking the next', async () => {
    await startLesson(rig)
    await actAndVerify(rig) // the watcher verified step 1 and moved on
    const calls = rig.verifyCalls
    rig.verdicts.push(OK) // would wrongly complete step 2 if consulted
    const done = await rig.runner.onStepDone()
    expect(done).toMatchObject({ ok: true, done: false, step: { index: 1 } })
    expect((await rig.runner.verifyStep()).completed).toBe(true)
    expect(rig.verifyCalls).toBe(calls)
    expect(rig.state.cur.skill?.step).toBe(2)
    // later (outside the window) an explicit step_done checks for real
    await rig.clock.advance(4_000)
    expect(await rig.runner.onStepDone()).toMatchObject({ ok: true, step: { index: 2 } })
    expect(rig.state.cur.skill?.step).toBe(3)
  })
})

describe('goodbye / Stop mid-lesson leaves the profile consistent', () => {
  const profile = async (r: Rig): Promise<string> => (await r.store.editMarkdown({ op: 'read' })).content

  it('abort at any point records nothing: the profile file is byte-identical, state is clean', async () => {
    await rig.store.setSkillLevel('video_call', 3, { lastSeen: rig.clock.now() - 1000 })
    const before = await profile(rig)
    const phase = rig.state.cur.phase
    await startLesson(rig)
    await rig.clock.advance(8_000) // glow
    await rig.clock.advance(6_000) // clue
    rig.verdicts.push({ completed: false, confidence: 0.9, evidence: 'x', uncertain: false, learnerMisstep: 'wrong' })
    rig.watch.fire()
    await rig.clock.advance(1_600)
    await rig.runner.abort('session ended: goodbye')
    expect(await profile(rig)).toBe(before)
    expect(rig.store.snapshot().attempts).toEqual([])
    expect(rig.state.cur.skill).toBeUndefined()
    expect(rig.state.cur.phase).toBe(phase) // the runner never touches the session phase
    expect(rig.state.cur.level).toBe(3) // chip back to the saved level
    expect(rig.clock.pending()).toBe(0)
    expect(rig.watch.subs).toBe(0)
  })

  it('Stop during step set-up, while a verification is in flight, and twice in a row', async () => {
    await startLesson(rig)
    let release!: (v: Verdict) => void
    ;(rig.runner as unknown as { deps: { verifier: Verifier } }).deps.verifier = { verify: () => new Promise<Verdict>((r) => (release = r)) }
    rig.watch.fire()
    await rig.clock.advance(1_600)
    await Promise.all([rig.runner.abort('stop'), rig.runner.abort('stop')])
    release(OK)
    await flush()
    expect(rig.runner.running).toBe(false)
    expect(rig.state.cur.skill).toBeUndefined()
    expect(rig.store.snapshot().attempts).toEqual([])
    expect(rig.stepEvents.filter((e) => e.phase === 'aborted')).toHaveLength(1)
  })

  it('Stop while Argon is still planning a novel goal: nothing starts afterwards', async () => {
    let release!: (p: LessonPlan) => void
    rig.architect.impl = () => new Promise<LessonPlan>((r) => (release = r))
    const started = rig.runner.start('how do I mute myself?')
    const outcome = started.then(() => 'started', (e: Error) => e.message)
    await flush()
    await rig.runner.abort('session ended: stop')
    release(mutePlan())
    await rig.clock.advance(0)
    await rig.settle()
    expect(await outcome).toMatch(/cancelled/)
    expect(rig.runner.running).toBe(false)
    expect(rig.state.cur.skill).toBeUndefined()
    expect(rig.watch.subs).toBe(0)
    expect(rig.clock.pending()).toBe(0)
    expect(rig.store.snapshot().attempts).toEqual([])
    // and a fresh lesson still works afterwards
    rig.architect.impl = async () => mutePlan()
    expect((await rig.runner.start('how do I mute myself?')).skillId).toBe('custom')
    await rig.runner.abort('x')
  })

  it('Stop after the last step but before end_lesson still keeps the finished attempt, once', async () => {
    await rig.store.setSkillLevel('bigger_text', 2)
    await startLesson(rig, 'make the text bigger')
    for (let i = 0; i < 3; i++) await actAndVerify(rig)
    await Promise.all([rig.runner.abort('goodbye'), rig.runner.abort('goodbye')])
    expect(rig.store.snapshot().attempts).toHaveLength(1)
    expect(rig.runner.running).toBe(false)
  })
})

describe('fading across attempts (the demo moment)', () => {
  async function runClean(rig: Rig, goal: string, steps: number, score = 0.9): Promise<void> {
    await startLesson(rig, goal)
    for (let i = 0; i < steps; i++) await actAndVerify(rig)
    await rig.runner.end('well done. Confidence 5.', score)
  }

  it('Watch -> Walk -> Nudge with one clean attempt each, hints per task never rising', async () => {
    await runClean(rig, 'make the text bigger', 3)
    expect(rig.store.snapshot().skills.bigger_text.level).toBe(2)
    expect(rig.state.cur.level).toBe(2)
    await runClean(rig, 'make the text bigger', 3)
    expect(rig.store.snapshot().skills.bigger_text.level).toBe(3)
    expect(rig.state.cur.level).toBe(3)
    expect(rig.injects.some((t) => t.includes('level 2 "Walk with me"'))).toBe(true)
    const attempts = rig.store.snapshot().attempts
    expect(attempts.map((a) => [a.levelAtStart, a.levelAtEnd])).toEqual([[1, 2], [2, 3]])
    expect(attempts.map((a) => a.hintsUsed)).toEqual([0, 0])
    expect(rig.levelEvents.map((e) => e.to)).toEqual([1, 2, 3])
  })

  it('a weak teach-back holds the level; the next clean attempt then steps up', async () => {
    await runClean(rig, 'make the text bigger', 3, 0.4)
    expect(rig.store.snapshot().skills.bigger_text.level).toBe(1)
    await runClean(rig, 'make the text bigger', 3, 0.9)
    expect(rig.store.snapshot().skills.bigger_text.level).toBe(2)
  })

  it('normal mode needs two clean attempts at L2', async () => {
    rig = makeRig({ settings: { demoMode: false } })
    await rig.store.setSkillLevel('bigger_text', 2)
    await runClean(rig, 'make the text bigger', 3)
    expect(rig.store.snapshot().skills.bigger_text.level).toBe(2)
    await runClean(rig, 'make the text bigger', 3)
    expect(rig.store.snapshot().skills.bigger_text.level).toBe(3)
  })

  it('a struggle (hints, errors) keeps the level and is recorded for the chart', async () => {
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    await rig.clock.advance(8_000)
    await rig.clock.advance(6_000)
    await rig.clock.advance(6_000)
    for (let i = 0; i < 5; i++) await actAndVerify(rig)
    await rig.runner.end('finished', 0.8)
    const a = rig.store.snapshot().attempts[0]
    expect(a).toMatchObject({ stalls: 1, hintsUsed: 2, clean: true })
    expect(rig.store.snapshot().skills.video_call.level).toBe(3 + 1 > 4 ? 4 : 4)
  })

  it('absence decays the starting level and says so', async () => {
    rig = makeRig({ stateLevel: 3 })
    await rig.store.setSkillLevel('video_call', 3, { lastSeen: rig.clock.now() - 10 * 86_400_000 })
    await startLesson(rig)
    expect(rig.state.cur.level).toBe(2)
    expect(rig.levelEvents.at(-1)?.reason).toMatch(/refresher/)
  })
})

describe('safety floor and level 4', () => {
  it('a lesson with a safety-critical step never runs untracked: L4 is held at L3, the safety step is lifted to L2', async () => {
    await rig.store.setSkillLevel('spot_scam', 4)
    await startLesson(rig, 'is this text a scam?')
    expect(rig.state.cur.level).toBe(3)
    expect(rig.levelEvents.at(-1)?.reason).toBe('this lesson keeps a safety net')
    expect(rig.sawShown('runner-ring')).toBe(false) // L3 draws nothing until a stall
    await actAndVerify(rig)
    await actAndVerify(rig) // steps are still tracked, so the safety step is reached
    expect(rig.state.cur.skill?.step).toBe(3)
    expect(rig.last()).toContain('safety-critical')
    expect(rig.sawShown('runner-ring')).toBe(true)
    expect(rig.levelEvents.some((e) => e.scope === 'step' && e.to === 2)).toBe(true)
    await actAndVerify(rig)
    expect(rig.levelEvents.at(-1)).toMatchObject({ scope: 'step', to: 3 })
    expect(rig.state.cur.level).toBe(3)
  })

  it('the in-lesson fade stops at L3 on a lesson with a safety-critical step', async () => {
    await rig.store.setSkillLevel('spot_scam', 3)
    await startLesson(rig, 'is this text a scam?')
    await actAndVerify(rig)
    await actAndVerify(rig)
    expect(rig.levelEvents.filter((e) => e.scope === 'attempt')).toHaveLength(0)
    expect(rig.state.cur.skill?.step).toBe(3)
    expect(rig.levelEvents.some((e) => e.scope === 'step' && e.to === 2)).toBe(true)
  })

  it('L4 on a lesson without safety steps: silent, no per-step tracking, a silent check for the finished task', async () => {
    await rig.store.setSkillLevel('video_call', 4)
    await startLesson(rig)
    expect(rig.state.cur.level).toBe(4)
    expect(rig.injects[0]).toContain('Stay silent')
    expect(rig.groundCalls).toHaveLength(0)
    const before = rig.injects.length
    // the learner is part way through: the check finds the task unfinished and says nothing
    rig.verdicts.push(NOT_YET)
    rig.watch.fire()
    await rig.clock.advance(1_600)
    await rig.settle()
    expect(rig.verifyCalls).toBe(1)
    expect(rig.injects).toHaveLength(before)
    expect(rig.state.cur.skill?.step).toBe(1)
    // the task is finished: the lesson completes by itself and the model is told to do the teach-back
    rig.verdicts.push(OK)
    rig.watch.fire()
    await rig.clock.advance(4_000)
    await rig.settle()
    expect(rig.last()).toContain('teach-back')
    expect(rig.watch.subs).toBe(0)
    // explicit asks also check the whole task
    await rig.runner.end('did it alone', 1)
    expect(rig.store.snapshot().attempts[0]).toMatchObject({ completed: true, hintsUsed: 0, clean: true })
  })

  it('L4: step_done / verify_step mean "I finished": checked against the end state', async () => {
    await rig.store.setSkillLevel('video_call', 4)
    await startLesson(rig)
    rig.verdicts.push({ completed: false, confidence: 0.9, evidence: 'not there yet', uncertain: false })
    expect(await rig.runner.onStepDone()).toMatchObject({ ok: false, done: false })
    rig.verdicts.push(OK)
    expect((await rig.runner.verifyStep()).completed).toBe(true)
    expect(rig.last()).toContain('teach-back')
    await rig.runner.end('spotted it', 1)
    expect(rig.store.snapshot().attempts[0]).toMatchObject({ completed: true, hintsUsed: 1 })
  })

  it('fading into L4 mid-lesson goes quiet: the chip moves, later steps are not announced', async () => {
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    await actAndVerify(rig)
    await actAndVerify(rig) // two clean steps: L3 -> L4 for the rest
    expect(rig.state.cur.level).toBe(4)
    expect(rig.last()).toContain('level=4 "On my own"')
    const n = rig.injects.length
    await rig.clock.advance(5_000)
    expect(rig.injects).toHaveLength(n)
    rig.verdicts.push(OK)
    rig.watch.fire()
    await rig.clock.advance(4_000)
    await rig.settle()
    expect(rig.last()).toContain('teach-back') // end state reached
  })
})

describe('requestLevel, overrides and locking', () => {
  it('lowering the level is always granted, free of penalty, and redrawn', async () => {
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    const res = await rig.runner.requestLevel(1, 'show me again')
    expect(res).toEqual({ applied: true, level: 1 })
    expect(rig.state.cur.level).toBe(1)
    expect(rig.last()).toContain('level=1 "Watch me"')
    expect(rig.shown.at(-1)?.map((a) => a.kind)).toContain('ghostCursor')
    for (let i = 0; i < 5; i++) await actAndVerify(rig)
    await rig.runner.end('ok', 0.9)
    expect(rig.store.snapshot().skills.video_call.level).toBe(3) // no change either way
  })

  it('raising the level needs the learner to have asked', async () => {
    await rig.store.setSkillLevel('video_call', 2)
    await startLesson(rig)
    expect(await rig.runner.requestLevel(4, 'they seem fine')).toMatchObject({ applied: false, level: 2 })
    expect(await rig.runner.requestLevel(3, 'let me try on my own')).toEqual({ applied: true, level: 3 })
    expect(rig.state.cur.level).toBe(3)
    expect(await rig.runner.requestLevel(3, 'again')).toMatchObject({ applied: false })
  })

  it('an anxious reason steps down on top of the request', async () => {
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    const res = await rig.runner.requestLevel(2, "I'm stuck and worried")
    expect(res).toMatchObject({ applied: true, level: 2 })
    expect(rig.levelEvents.some((e) => e.to === 2)).toBe(true)
  })

  it('nothing to change when no lesson runs or the learner locked the level', async () => {
    expect((await rig.runner.requestLevel(1)).applied).toBe(false)
    rig = makeRig({ settings: { helpLevelMode: 'locked', lockedLevel: 3 } })
    await startLesson(rig)
    expect(rig.state.cur.level).toBe(3)
    expect(await rig.runner.requestLevel(1, 'show me')).toMatchObject({ applied: false, level: 3 })
    rig.runner.noteUtterance("I'm stuck")
    rig.runner.noteUtterance('show me again')
    expect(rig.state.cur.level).toBe(3)
    for (let i = 0; i < 5; i++) await actAndVerify(rig)
    await rig.runner.end('ok', 1)
    expect(rig.store.snapshot().skills.video_call.level).toBe(1) // locked: attempts recorded, level never moved
    expect(rig.store.snapshot().attempts).toHaveLength(1)
  })

  it('noteUtterance reacts to worry and to "show me again" / "let me try"', async () => {
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    rig.runner.noteUtterance("oh no, I've broken it")
    expect(rig.state.cur.level).toBe(2)
    rig.runner.noteUtterance('can you show me again')
    expect(rig.state.cur.level).toBe(1)
    expect(rig.shown.at(-1)?.map((a) => a.kind)).toContain('ghostCursor')
    rig.runner.noteUtterance('actually let me try')
    expect(rig.state.cur.level).toBe(4)
    rig.runner.noteUtterance('hello there') // nothing
    const idle = makeRig()
    idle.runner.noteUtterance("I'm stuck") // no lesson: ignored
    expect(idle.levelEvents).toHaveLength(0)
  })
})

describe('end()', () => {
  it('reads the confidence dial from the summary when the tool arg is missing, and prefers the arg', async () => {
    await rig.store.setSkillLevel('bigger_text', 2)
    await startLesson(rig, 'make the text bigger')
    for (let i = 0; i < 3; i++) await actAndVerify(rig)
    await rig.runner.end('Learned to make text bigger. Confidence: 3 out of 5', 0.8)
    expect(rig.store.snapshot().attempts[0].confidence).toBe(3)
    expect(rig.store.snapshot().lastSession?.summary).toBe('Learned to make text bigger.')
    await startLesson(rig, 'make the text bigger')
    for (let i = 0; i < 3; i++) await actAndVerify(rig)
    await rig.runner.end('Done', undefined, 9)
    const second = rig.store.snapshot().attempts[1]
    expect(second.confidence).toBe(5)
    expect(second.teachBackScore).toBeNull()
  })

  it('stopping early without struggle changes nothing; struggling then quitting steps down', async () => {
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    await rig.runner.end('they had to go')
    expect(rig.store.snapshot().skills.video_call.level).toBe(3)
    expect(rig.store.snapshot().attempts[0].completed).toBe(false)

    await startLesson(rig)
    await rig.clock.advance(8_000)
    await rig.clock.advance(6_000)
    await rig.runner.end('gave up')
    expect(rig.store.snapshot().skills.video_call.level).toBe(2)
  })

  it('is a no-op without a lesson and ignores a second call', async () => {
    await rig.runner.end('nothing')
    await rig.store.setSkillLevel('bigger_text', 2)
    await startLesson(rig, 'make the text bigger')
    for (let i = 0; i < 3; i++) await actAndVerify(rig)
    await Promise.all([rig.runner.end('a', 1), rig.runner.end('b', 1)])
    expect(rig.store.snapshot().attempts).toHaveLength(1)
  })

  it('teach-back off: the directive tells the model to just wrap up', async () => {
    rig = makeRig({ settings: { teachBack: false } })
    await rig.store.setSkillLevel('bigger_text', 2)
    await startLesson(rig, 'make the text bigger')
    for (let i = 0; i < 3; i++) await actAndVerify(rig)
    expect(rig.last()).toContain('Teach-back is switched off')
  })

  it('survives a store that fails to save', async () => {
    await rig.store.setSkillLevel('bigger_text', 2)
    await startLesson(rig, 'make the text bigger')
    for (let i = 0; i < 3; i++) await actAndVerify(rig)
    ;(rig.runner as unknown as { deps: { learner: unknown } }).deps.learner = {
      snapshot: () => rig.store.snapshot(),
      recordAttempt: async () => {
        throw new Error('disk full')
      },
    }
    await expect(rig.runner.end('ok', 1)).resolves.toBeUndefined()
    expect(rig.runner.running).toBe(false)
  })
})

describe('in-lesson adaptive fading (the hero moment)', () => {
  const fades = (r: Rig) => r.levelEvents.filter((e) => e.scope === 'attempt')

  it('L2 for steps 1-2, then L3 for the remaining steps, with the chip following', async () => {
    await rig.store.setSkillLevel('video_call', 2)
    await startLesson(rig)
    expect(rig.state.cur.level).toBe(2)
    expect(rig.shown[0].map((a) => a.kind).sort()).toEqual(['arrow', 'ring'])

    await actAndVerify(rig) // step 1 clean
    expect(rig.state.cur.level).toBe(2)
    expect(rig.state.cur.skill?.step).toBe(2)
    const drawn = rig.shown.length

    await actAndVerify(rig) // step 2 clean -> ease off
    expect(rig.state.cur.skill?.step).toBe(3)
    expect(fades(rig)).toHaveLength(1)
    expect(fades(rig)[0]).toMatchObject({ from: 2, to: 3, scope: 'attempt' })
    expect(rig.state.cur.level).toBe(3)
    expect(rig.last()).toContain('step 2 of 5 verified')
    expect(rig.last()).toContain('level=3 "Nudge me"')
    expect(rig.last()).toContain('step 3 of 5, level 3 "Nudge me"')
    expect(rig.last()).toContain('Stay quiet')
    // steps 3+ at L3: no ring/arrow beyond the tick for step 2
    expect(rig.shown.slice(drawn).flat().filter((a) => a.kind === 'ring' || a.kind === 'arrow')).toHaveLength(0)

    await actAndVerify(rig)
    await actAndVerify(rig)
    expect(rig.state.cur.level).toBe(3) // never further than one level above where the attempt began
    await actAndVerify(rig)
    await rig.runner.end('good. Confidence 4', 0.9)
    expect(fades(rig)).toHaveLength(1)
    const attempt = rig.store.snapshot().attempts[0]
    expect(attempt).toMatchObject({ levelAtStart: 2, levelAtEnd: 3, hintsUsed: 0, clean: true })
    expect(rig.store.snapshot().skills.video_call.level).toBe(3)
  })

  it('the same rule applies in normal mode, and the between-attempt rule is unchanged', async () => {
    rig = makeRig({ settings: { demoMode: false } })
    await rig.store.setSkillLevel('video_call', 2)
    await startLesson(rig)
    await actAndVerify(rig)
    await actAndVerify(rig)
    expect(rig.state.cur.level).toBe(3)
    for (let i = 0; i < 3; i++) await actAndVerify(rig)
    await rig.runner.end('ok', 0.9)
    // normal mode still needs two clean attempts to make L3 the saved level
    expect(rig.store.snapshot().skills.video_call.level).toBe(2)
    expect(rig.state.cur.level).toBe(2)
  })

  it('two struggling steps in a row bring the help back', async () => {
    await rig.store.setSkillLevel('video_call', 2)
    await startLesson(rig)
    await actAndVerify(rig)
    await actAndVerify(rig) // L3 now
    expect(rig.state.cur.level).toBe(3)
    const wrong: Verdict = { completed: false, confidence: 0.9, evidence: 'x', uncertain: false, learnerMisstep: 'wrong place' }
    await actAndVerify(rig, wrong) // step 3 needs a repair hint
    await actAndVerify(rig) // ...then done
    expect(rig.state.cur.skill?.step).toBe(4)
    await actAndVerify(rig, wrong)
    await actAndVerify(rig) // second struggling step in a row
    expect(rig.state.cur.level).toBe(2)
    expect(fades(rig).map((e) => e.to)).toEqual([3, 2])
    expect(rig.last()).toContain('level=2 "Walk with me"')
    expect(rig.last()).toContain('more help is back')
    expect(rig.shown.at(-1)?.map((a) => a.kind)).toContain('ring')
  })

  it('a safety-critical step never fades past L2, then the chip eases back', async () => {
    await rig.store.setSkillLevel('spot_scam', 2)
    await startLesson(rig, 'is this text a scam?')
    await actAndVerify(rig)
    await actAndVerify(rig) // faded to L3; step 3 (inspect) is safety-critical
    expect(rig.state.cur.skill?.step).toBe(3)
    expect(rig.levelEvents.map((e) => `${e.scope}:${e.to}`)).toEqual(['attempt:3', 'step:2'])
    expect(rig.sawShown('runner-ring')).toBe(true)
    await actAndVerify(rig)
    expect(rig.state.cur.level).toBe(3)
  })

  it('never fades when the learner locked the level or chose one themselves', async () => {
    rig = makeRig({ settings: { helpLevelMode: 'locked', lockedLevel: 2 } })
    await startLesson(rig)
    for (let i = 0; i < 4; i++) await actAndVerify(rig)
    expect(fades(rig)).toHaveLength(0)
    expect(rig.state.cur.level).toBe(2)

    const other = makeRig()
    await other.store.setSkillLevel('video_call', 3)
    await startLesson(other)
    await other.runner.requestLevel(1, 'show me again')
    for (let i = 0; i < 4; i++) await actAndVerify(other)
    expect(other.levelEvents.filter((e) => e.scope === 'attempt')).toHaveLength(0)
    expect(other.state.cur.level).toBe(1)
  })

  it('a lesson whose last two steps are clean has nothing left to ease off', async () => {
    await rig.store.setSkillLevel('bigger_text', 2)
    await startLesson(rig, 'make the text bigger') // 3 steps: the fade comes after step 2 and applies to step 3
    await actAndVerify(rig)
    await actAndVerify(rig)
    expect(rig.state.cur.level).toBe(3)
    await actAndVerify(rig)
    expect(fades(rig)).toHaveLength(1)
  })
})

describe('auto-assist on stall', () => {
  const NOVEL = 'help me use my strange gizmo' // goes to the architect, whose plan the test controls
  const LADDER_MS = 8_000 + 6_000 + 6_000 // L3: three rungs
  const res = (code: DoItForMeResult['code'], extra: Partial<DoItForMeResult> = {}): DoItForMeResult => ({
    allowed: true, done: code === 'clicked', code, reason: code === 'clicked' ? 'I clicked it once.' : `not clicked: ${code}`, label: 'Start call', ...extra,
  })
  const setup = async (settings: Partial<Settings>, impl: (t: string) => Promise<DoItForMeResult>) => {
    const calls: string[] = []
    const rig = makeRig({ settings, assist: async ({ target }) => (calls.push(target), impl(target)) })
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    return { rig, calls }
  }
  const assistInjects = (rig: Rig): string[] => rig.injects.filter((t) => t.startsWith('[ASSIST]'))

  it('offers a choice after the ladder is spent, and counts a approved click as done-for-me', async () => {
    const { rig, calls } = await setup({ agency: 'ask_each' }, async () => res('clicked'))
    await rig.clock.advance(LADDER_MS - 1)
    expect(calls).toHaveLength(0)
    await rig.clock.advance(1_500 + 1)
    await rig.settle()
    expect(calls).toHaveLength(1)
    expect(assistInjects(rig)[0]).toContain('I can click it for you, or you can try once more. Which would you like?')
    expect(assistInjects(rig)[1]).toContain('offer to show them how')
    expect(rig.store.snapshot().doneForMe).toEqual({ 'click Start call': 1 })
  })

  it('offers at most once per step', async () => {
    const { rig, calls } = await setup({ agency: 'ask_each' }, async () => res('declined'))
    await rig.clock.advance(LADDER_MS + 2_000)
    await rig.settle()
    await rig.clock.advance(120_000)
    await rig.runner.onStall()
    await rig.clock.advance(120_000)
    await rig.settle()
    expect(calls).toHaveLength(1)
  })

  it('a declined offer leaves the learner in control and counts nothing', async () => {
    const { rig } = await setup({ agency: 'ask_per_task' }, async () => res('declined'))
    await rig.clock.advance(LADDER_MS + 2_000)
    await rig.settle()
    expect(assistInjects(rig).at(-1)).toContain('chose to do it themselves')
    expect(rig.store.snapshot().doneForMe ?? {}).toEqual({})
    expect(rig.runner.running).toBe(true)
  })

  it('never when agency is off', async () => {
    const { rig, calls } = await setup({ agency: 'off' }, async () => res('clicked'))
    await rig.clock.advance(LADDER_MS + 10_000)
    await rig.settle()
    expect(calls).toHaveLength(0)
    expect(assistInjects(rig)).toHaveLength(0)
  })

  it('never for a safety-critical step', async () => {
    const calls: string[] = []
    const rig = makeRig({ settings: { agency: 'ask_each' }, assist: async ({ target }) => (calls.push(target), res('clicked')) })
    rig.architect.impl = async (req) => {
      const plan = fallbackPlan('video_call', req.goal)
      return { ...plan, steps: plan.steps.map((st) => ({ ...st, safetyCritical: true })) }
    }
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig, NOVEL)
    await rig.clock.advance(LADDER_MS + 10_000)
    await rig.settle()
    expect(calls).toHaveLength(0)
  })

  it('never during a scam check', async () => {
    const calls: string[] = []
    const rig = makeRig({ settings: { agency: 'ask_each' }, assist: async ({ target }) => (calls.push(target), res('clicked')) })
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig)
    rig.state.patch({ agents: [{ id: 'a1', kind: 'scam_check', status: 'running', title: 'scam check' } as never] })
    await rig.clock.advance(LADDER_MS + 10_000)
    await rig.settle()
    expect(calls).toHaveLength(0)
    const rig2 = makeRig({ settings: { agency: 'ask_each' }, assist: async ({ target }) => (calls.push(target), res('clicked')) })
    await startLesson(rig2, 'Is this message a scam?')
    await rig2.clock.advance(60_000)
    await rig2.settle()
    expect(calls).toHaveLength(0)
  })

  it('never offers for a denylisted label', async () => {
    const calls: string[] = []
    const rig = makeRig({ settings: { agency: 'ask_each' }, assist: async ({ target }) => (calls.push(target), res('clicked')) })
    rig.architect.impl = async (req) => {
      const plan = fallbackPlan('video_call', req.goal)
      return { ...plan, steps: plan.steps.map((st) => ({ ...st, targetDescription: 'green button labelled Pay now' })) }
    }
    await rig.store.setSkillLevel('video_call', 3)
    await startLesson(rig, NOVEL)
    await rig.clock.advance(LADDER_MS + 10_000)
    await rig.settle()
    expect(calls).toHaveLength(0)
  })

  it('a refusal from the do_it_for_me flow clicks nothing and is not counted', async () => {
    const { rig } = await setup({ agency: 'ask_each' }, async () => res('sensitive', { allowed: false }))
    await rig.clock.advance(LADDER_MS + 2_000)
    await rig.settle()
    expect(assistInjects(rig).at(-1)).toContain('Nothing was clicked')
    expect(rig.store.snapshot().doneForMe ?? {}).toEqual({})
  })

  it('Stop (lesson aborted) before the offer cancels it; Stop while the panel is open says nothing more', async () => {
    const a = await setup({ agency: 'ask_each' }, async () => res('clicked'))
    await a.rig.clock.advance(LADDER_MS - 1_000)
    await a.rig.runner.abort('stop')
    await a.rig.clock.advance(60_000)
    await a.rig.settle()
    expect(a.calls).toHaveLength(0)

    let release: (r: DoItForMeResult) => void = () => undefined
    const b = await setup({ agency: 'ask_each' }, () => new Promise<DoItForMeResult>((r) => (release = r)))
    await b.rig.clock.advance(LADDER_MS + 2_000)
    await b.rig.settle()
    expect(b.calls).toHaveLength(1)
    await b.rig.runner.abort('stop')
    release(res('stopped'))
    await b.rig.settle()
    expect(assistInjects(b.rig)).toHaveLength(1) // only the offer, no narration
    expect(b.rig.store.snapshot().doneForMe ?? {}).toEqual({})
  })
})
