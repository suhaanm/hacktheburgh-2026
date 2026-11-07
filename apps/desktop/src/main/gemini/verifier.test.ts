import { describe, expect, it } from 'vitest'
import { MODELS } from '../../shared/models'
import type { LessonStep } from '../../shared/protocol'
import { apiError, fakeAi, hasImage, modelOutput, testDeps, testShot, textInput } from './fake-ai.test-util'
import { createVerifier } from './verifier'

const verdict = (o: Partial<{ completed: boolean; confidence: number; uncertain: boolean; evidence: string; learner_misstep: string; next_hint: string }>) =>
  modelOutput({ completed: false, confidence: 0.9, uncertain: false, evidence: 'I can see it.', learner_misstep: '', next_hint: '', ...o })

const step: LessonStep = {
  id: 's1',
  index: 0,
  instruction: 'Press the green Start call button.',
  targetDescription: 'green Start call button',
  expectedOutcome: 'A call window is open with a camera preview.',
  hints: { l1: 'a', l2: 'b', l3: 'c' },
  safetyCritical: false,
}

describe('verifier', () => {
  it('accepts a decisive lite answer without escalating, with store:false and the expected outcome in the prompt', async () => {
    const { ai, calls } = fakeAi(() => verdict({ completed: true, confidence: 0.92 }))
    const v = await createVerifier(testDeps(ai)).verify({ step, shot: testShot() })
    expect(v.completed).toBe(true)
    expect(v.uncertain).toBe(false)
    expect(calls).toHaveLength(1)
    expect(calls[0].params.model).toBe(MODELS.lite)
    expect(calls[0].params.store).toBe(false)
    expect(hasImage(calls[0])).toBe(true)
    expect(textInput(calls[0])).toContain('A call window is open')
    expect(textInput(calls[0])).toMatch(/untrusted DATA/)
  })

  it('escalates lite -> flash -> argon only while the answer is not decisive', async () => {
    const { ai, calls } = fakeAi((p) => {
      if (p.model === MODELS.argon) return verdict({ completed: true, confidence: 0.95 })
      return verdict({ completed: true, confidence: 0.55, uncertain: true })
    })
    const v = await createVerifier(testDeps(ai)).verify({ expected: 'The Dark mode switch is on.', shot: testShot() })
    expect(calls.map((c) => c.params.model)).toEqual([MODELS.lite, MODELS.flash, MODELS.argon])
    expect(v.completed).toBe(true)
  })

  it('never ticks when every tier is unsure', async () => {
    const { ai } = fakeAi(() => verdict({ completed: true, confidence: 0.6, uncertain: true }))
    const v = await createVerifier(testDeps(ai)).verify({ expected: 'x', shot: testShot() })
    expect(v.completed).toBe(false)
    expect(v.uncertain).toBe(true)
  })

  it('treats completed+uncertain as not completed', async () => {
    const { ai } = fakeAi(() => verdict({ completed: true, confidence: 0.95, uncertain: true }))
    const v = await createVerifier(testDeps(ai), { useArgon: false }).verify({ expected: 'x', shot: testShot() })
    expect(v.completed).toBe(false)
  })

  it('keeps going when a tier errors', async () => {
    const { ai, calls } = fakeAi((p) => {
      if (p.model === MODELS.lite) throw apiError(400)
      return verdict({ completed: false, confidence: 0.9, learner_misstep: 'Opened Settings instead', next_hint: 'Look for the green button near the top.' })
    })
    const v = await createVerifier(testDeps(ai)).verify({ step, shot: testShot() })
    expect(calls[1].params.model).toBe(MODELS.flash)
    expect(v.completed).toBe(false)
    expect(v.learnerMisstep).toBe('Opened Settings instead')
    expect(v.nextHint).toBe('Look for the green button near the top.')
  })

  it('caps the hint at 20 words and drops hints when completed', async () => {
    const long = Array.from({ length: 40 }, (_, i) => `w${i}`).join(' ')
    const { ai } = fakeAi(() => verdict({ completed: false, confidence: 0.9, next_hint: long }))
    const v = await createVerifier(testDeps(ai)).verify({ step, shot: testShot() })
    expect(v.nextHint!.split(' ')).toHaveLength(20)
    const { ai: ai2 } = fakeAi(() => verdict({ completed: true, confidence: 0.9, next_hint: 'ignored', learner_misstep: 'ignored' }))
    const done = await createVerifier(testDeps(ai2)).verify({ step, shot: testShot() })
    expect(done.nextHint).toBeUndefined()
    expect(done.learnerMisstep).toBeUndefined()
  })

  it('says it could not check when nothing works, and when there is no screenshot', async () => {
    const { ai } = fakeAi(() => {
      throw apiError(400)
    })
    const v = await createVerifier(testDeps(ai)).verify({ step, shot: testShot() })
    expect(v).toMatchObject({ completed: false, uncertain: true, confidence: 0 })
    const { ai: ai2, calls } = fakeAi(() => verdict({}))
    const none = await createVerifier(testDeps(ai2)).verify({ step })
    expect(none.uncertain).toBe(true)
    expect(calls).toHaveLength(0)
  })

  it('grabs its own verify shot when a capture dependency exists', async () => {
    const purposes: string[] = []
    const { ai } = fakeAi(() => verdict({ completed: true, confidence: 0.9 }))
    const v = await createVerifier(testDeps(ai, { capture: { grab: async (p) => (purposes.push(p), testShot()) } })).verify({ step })
    expect(purposes).toEqual(['verify'])
    expect(v.completed).toBe(true)
  })
})
