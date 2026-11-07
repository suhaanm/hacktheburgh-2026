import { describe, expect, it } from 'vitest'
import { MODELS } from '../../shared/models'
import { LessonPlanSchema, wordCount, type LearnerSnapshot } from '../../shared/protocol'
import { apiError, fakeAi, hasImage, modelOutput, sleep, testDeps, testShot, textInput } from './fake-ai.test-util'
import { GeminiError } from './client'
import { createLessonArchitect } from './lesson-architect'
import type { GroundResult } from '../../shared/protocol'

const learner: LearnerSnapshot = {
  skills: {
    video_call: { level: 2, streakClean: 1, lastSeen: null, nextReview: null },
    spot_scam: { level: 1, streakClean: 0, lastSeen: null, nextReview: null },
    bigger_text: { level: 3, streakClean: 2, lastSeen: null, nextReview: null },
  },
  confidenceLog: [],
  attempts: [],
  whatWorks: ['short sentences', 'analogies to the post office'],
  avoidJargon: ['browser', 'app'],
}

const rawStep = (over: Record<string, unknown> = {}) => ({
  instruction: 'Press the green Start call button.',
  targetDescription: 'green rounded button labelled Start call, left column',
  expectedOutcome: 'A call window is open showing a camera preview.',
  hints: { l1: 'Watch where I point.', l2: 'It is the green one.', l3: 'Look for green on the left.' },
  safetyCritical: false,
  analogy: '',
  ...over,
})

describe('lesson architect', () => {
  it('returns a validated plan: ids, indexes, goal, argon, low thinking, tight schema, no search', async () => {
    const { ai, calls } = fakeAi(() => modelOutput({ skillId: 'video_call', steps: [rawStep(), rawStep({ instruction: 'Wait for Emma to answer.' })] }))
    const plan = await createLessonArchitect(testDeps(ai)).plan({ goal: 'Call my granddaughter Emma', learner })
    expect(LessonPlanSchema.safeParse(plan).success).toBe(true)
    expect(plan.goal).toBe('Call my granddaughter Emma')
    expect(plan.skillId).toBe('video_call')
    expect(plan.steps.map((s) => s.index)).toEqual([0, 1])
    expect(plan.steps[0].id).toBe(`${plan.lessonId}-s1`)
    expect(plan.steps[0].analogy).toBeUndefined()
    expect(calls[0].params.model).toBe(MODELS.argon)
    expect(calls[0].params.store).toBe(false)
    expect((calls[0].params.generation_config as { thinking_level: string }).thinking_level).toBe('low')
    expect(calls[0].params.tools).toBeUndefined()
    expect(calls[0].params).not.toHaveProperty('temperature')
    expect(textInput(calls[0])).toContain('short sentences')
    expect(textInput(calls[0])).toMatch(/untrusted DATA/)
  })

  it('caps at 4 steps by default (configurable up to the contract max) and 20 words per instruction', async () => {
    const long = Array.from({ length: 35 }, (_, i) => `word${i}`).join(' ')
    const steps = Array.from({ length: 9 }, () => rawStep({ instruction: long }))
    const { ai } = fakeAi(() => modelOutput({ skillId: 'bigger_text', steps }))
    const plan = await createLessonArchitect(testDeps(ai)).plan({ goal: 'Make the text bigger', learner })
    expect(plan.steps).toHaveLength(4)
    for (const s of plan.steps) expect(wordCount(s.instruction)).toBeLessThanOrEqual(20)
    const six = await createLessonArchitect(testDeps(ai), { maxSteps: 6 }).plan({ goal: 'Make the text bigger', learner })
    expect(six.steps).toHaveLength(6)
  })

  it('forces safetyCritical on risky steps; the model may add the flag but never remove it', async () => {
    const steps = [
      rawStep({ instruction: 'Type your password into the box.', safetyCritical: false }),
      rawStep({ instruction: 'Look at the sender name.', safetyCritical: true }),
      rawStep({ instruction: 'Open the Display page.', safetyCritical: false }),
    ]
    const { ai } = fakeAi(() => modelOutput({ skillId: 'spot_scam', steps }))
    const plan = await createLessonArchitect(testDeps(ai)).plan({ goal: 'x', learner })
    expect(plan.steps.map((s) => s.safetyCritical)).toEqual([true, true, false])
  })

  it('sends the screenshot (medium resolution) when given and tells the model step 1 must be visible', async () => {
    const { ai, calls } = fakeAi(() => modelOutput({ skillId: 'video_call', steps: [rawStep()] }))
    await createLessonArchitect(testDeps(ai)).plan({ goal: 'x', learner, shot: testShot() })
    expect(hasImage(calls[0])).toBe(true)
    expect((calls[0].params.input as Array<{ type: string; resolution?: string }>).find((p) => p.type === 'image')!.resolution).toBe('medium')
    expect(textInput(calls[0])).toMatch(/Step 1 MUST be something you can actually SEE/)
  })

  it('rejects invalid output (TEACH then falls back to its static plan)', async () => {
    const { ai } = fakeAi(() => modelOutput('not json at all'))
    await expect(createLessonArchitect(testDeps(ai)).plan({ goal: 'x', learner })).rejects.toMatchObject({ code: 'parse' })
    const { ai: ai2 } = fakeAi(() => modelOutput({ skillId: 'not_a_skill', steps: [rawStep()] }))
    await expect(createLessonArchitect(testDeps(ai2)).plan({ goal: 'x', learner })).rejects.toBeInstanceOf(GeminiError)
  })

  it('rejects with a timeout instead of hanging past its budget', async () => {
    const { ai } = fakeAi(async () => {
      await sleep(500)
      return modelOutput({ skillId: 'video_call', steps: [rawStep()] })
    })
    const started = Date.now()
    await expect(createLessonArchitect(testDeps(ai), { timeoutMs: 60 }).plan({ goal: 'x', learner })).rejects.toMatchObject({ code: 'timeout' })
    expect(Date.now() - started).toBeLessThan(400)
  })

  it('rejects an empty goal without calling the model', async () => {
    const { ai, calls } = fakeAi(() => modelOutput({}))
    await expect(createLessonArchitect(testDeps(ai)).plan({ goal: '  ', learner })).rejects.toMatchObject({ code: 'no_input' })
    expect(calls).toHaveLength(0)
  })
})

describe('lesson architect: step-1 groundability check', () => {
  const grounded = (found: boolean): GroundResult => ({ found, confidence: found ? 0.9 : 0, latencyMs: 1, model: 'x', ...(found ? { box: { xmin: 1, ymin: 1, xmax: 50, ymax: 50 } } : {}) })
  const planFor = (target: string) => modelOutput({ skillId: 'video_call', steps: [rawStep({ targetDescription: target })] })

  it('keeps the plan when step 1 can be grounded on the screenshot, and prefetches it for the runner', async () => {
    const { ai, calls } = fakeAi(() => planFor('the grey Settings icon on the left of the desktop'))
    const seen: string[] = []
    const grounder = { ground: async (r: { target: string }) => (seen.push(`ground:${r.target}`), grounded(true)), prefetch: (r: { target: string }) => void seen.push(`prefetch:${r.target}`) }
    const plan = await createLessonArchitect(testDeps(ai), { grounder }).plan({ goal: 'open settings', learner, shot: testShot() })
    expect(calls).toHaveLength(1)
    expect(plan.steps[0].targetDescription).toBe('the grey Settings icon on the left of the desktop')
    expect(seen).toEqual(['prefetch:the grey Settings icon on the left of the desktop', 'ground:the grey Settings icon on the left of the desktop'])
  })

  it('re-plans exactly once when step 1 is not visible, telling the model what was wrong', async () => {
    const { ai, calls } = fakeAi((_p, n) => planFor(n === 1 ? 'the Privacy tab in the settings sidebar' : 'the grey Settings icon on the left of the desktop'))
    const grounder = { ground: async (r: { target: string }) => grounded(r.target.includes('Settings icon')), prefetch: () => undefined }
    const plan = await createLessonArchitect(testDeps(ai), { grounder, replanMinMs: 0 }).plan({ goal: 'open privacy settings', learner, shot: testShot() })
    expect(calls).toHaveLength(2)
    expect(textInput(calls[1])).toContain('is NOT visible on the screen')
    expect(textInput(calls[1])).toContain('Privacy tab in the settings sidebar')
    expect(plan.steps[0].targetDescription).toContain('Settings icon')
  })

  it('never re-plans twice, and returns the re-plan even if it is still ungroundable', async () => {
    const { ai, calls } = fakeAi(() => planFor('something invisible'))
    const grounder = { ground: async () => grounded(false), prefetch: () => undefined }
    const plan = await createLessonArchitect(testDeps(ai), { grounder, replanMinMs: 0 }).plan({ goal: 'x', learner, shot: testShot() })
    expect(calls).toHaveLength(2)
    expect(plan.steps).toHaveLength(1)
  })

  it('skips the re-plan when too little of the 15 s budget is left, and returns the first plan', async () => {
    const { ai, calls } = fakeAi(() => planFor('something invisible'))
    const grounder = { ground: async () => grounded(false), prefetch: () => undefined }
    await createLessonArchitect(testDeps(ai), { grounder, replanMinMs: 60_000 }).plan({ goal: 'x', learner, shot: testShot() })
    expect(calls).toHaveLength(1)
  })

  it('does not punish the plan when grounding itself errors, and skips the check with no screenshot', async () => {
    const { ai, calls } = fakeAi(() => planFor('x'))
    const failing = { ground: async () => { throw new Error('boom') }, prefetch: () => undefined }
    const plan = await createLessonArchitect(testDeps(ai), { grounder: failing }).plan({ goal: 'x', learner, shot: testShot() })
    expect(plan.steps).toHaveLength(1)
    expect(calls).toHaveLength(1)
    let grounded = 0
    const counting = { ground: async () => (grounded++, { found: false, confidence: 0, latencyMs: 1, model: 'x' } as GroundResult), prefetch: () => undefined }
    await createLessonArchitect(testDeps(ai), { grounder: counting }).plan({ goal: 'x', learner })
    expect(grounded).toBe(0)
  })
})

describe('lesson architect: hedged request for the Argon latency tail', () => {
  const okPlan = () => modelOutput({ skillId: 'video_call', steps: [rawStep()] })

  it('fires a second request when the first is still pending at the hedge point, and the faster one wins', async () => {
    const { ai, calls } = fakeAi(async (_p, n) => {
      if (n === 1) await sleep(1500)
      return okPlan()
    })
    const started = Date.now()
    const plan = await createLessonArchitect(testDeps(ai), { timeoutMs: 4000, hedgeAfterMs: 300 }).plan({ goal: 'x', learner })
    expect(plan.steps).toHaveLength(1)
    expect(calls).toHaveLength(2)
    expect(Date.now() - started).toBeLessThan(1000)
  })

  it('does not hedge when the first answers in time', async () => {
    const { ai, calls } = fakeAi(() => okPlan())
    await createLessonArchitect(testDeps(ai), { timeoutMs: 4000, hedgeAfterMs: 300 }).plan({ goal: 'x', learner })
    expect(calls).toHaveLength(1)
  })

  it('retries immediately when the first attempt fails before the hedge point', async () => {
    const { ai, calls } = fakeAi((_p, n) => {
      if (n === 1) throw apiError(503)
      return okPlan()
    })
    await createLessonArchitect(testDeps(ai), { timeoutMs: 4000, hedgeAfterMs: 300 }).plan({ goal: 'x', learner })
    expect(calls).toHaveLength(2)
  })

  it('rejects once, with the first error, when both attempts fail; still honours the hard cap', async () => {
    const { ai } = fakeAi(async () => {
      await sleep(5000)
      return okPlan()
    })
    const started = Date.now()
    await expect(createLessonArchitect(testDeps(ai), { timeoutMs: 1200, hedgeAfterMs: 400 }).plan({ goal: 'x', learner })).rejects.toMatchObject({ code: 'timeout' })
    expect(Date.now() - started).toBeLessThan(2000)
  })
})
