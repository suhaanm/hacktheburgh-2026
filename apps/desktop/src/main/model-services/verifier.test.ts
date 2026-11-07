import { describe, expect, it } from 'vitest'
import type { LessonStep } from '../../shared/protocol'
import { apiError, fakePort, hasImage, modelOutput, testDeps, testShot, textInput } from '../model-port/fake-port.test-util'
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
    const { port, calls } = fakePort(() => verdict({ completed: true, confidence: 0.92 }))
    const v = await createVerifier(testDeps(port)).verify({ step, shot: testShot() })
    expect(v.completed).toBe(true)
    expect(v.uncertain).toBe(false)
    expect(calls).toHaveLength(1)
    expect(calls[0].tier).toBe('fast')
    expect(hasImage(calls[0])).toBe(true)
    expect(textInput(calls[0])).toContain('A call window is open')
    expect(textInput(calls[0])).toMatch(/untrusted DATA/)
  })

  it('escalates fast -> planner only while the answer is not decisive', async () => {
    const { port, calls } = fakePort((req) => {
      if (req.tier === 'planner') return verdict({ completed: true, confidence: 0.95 })
      return verdict({ completed: true, confidence: 0.55, uncertain: true })
    })
    const v = await createVerifier(testDeps(port)).verify({ expected: 'The Dark mode switch is on.', shot: testShot() })
    expect(calls.map((c) => c.tier)).toEqual(['fast', 'planner'])
    expect(v.completed).toBe(true)
  })

  it('never ticks when every tier is unsure', async () => {
    const { port } = fakePort(() => verdict({ completed: true, confidence: 0.6, uncertain: true }))
    const v = await createVerifier(testDeps(port)).verify({ expected: 'x', shot: testShot() })
    expect(v.completed).toBe(false)
    expect(v.uncertain).toBe(true)
  })

  it('treats completed+uncertain as not completed', async () => {
    const { port } = fakePort(() => verdict({ completed: true, confidence: 0.95, uncertain: true }))
    const v = await createVerifier(testDeps(port), { usePlanner: false }).verify({ expected: 'x', shot: testShot() })
    expect(v.completed).toBe(false)
  })

  it('keeps going when a tier errors', async () => {
    const { port, calls } = fakePort((req) => {
      if (req.tier === 'fast') throw apiError(400)
      return verdict({ completed: false, confidence: 0.9, learner_misstep: 'Opened Settings instead', next_hint: 'Look for the green button near the top.' })
    })
    const v = await createVerifier(testDeps(port)).verify({ step, shot: testShot() })
    expect(calls[1].tier).toBe('planner')
    expect(v.completed).toBe(false)
    expect(v.learnerMisstep).toBe('Opened Settings instead')
    expect(v.nextHint).toBe('Look for the green button near the top.')
  })

  it('caps the hint at 20 words and drops hints when completed', async () => {
    const long = Array.from({ length: 40 }, (_, i) => `w${i}`).join(' ')
    const { port } = fakePort(() => verdict({ completed: false, confidence: 0.9, next_hint: long }))
    const v = await createVerifier(testDeps(port)).verify({ step, shot: testShot() })
    expect(v.nextHint!.split(' ')).toHaveLength(20)
    const { port: port2 } = fakePort(() => verdict({ completed: true, confidence: 0.9, next_hint: 'ignored', learner_misstep: 'ignored' }))
    const done = await createVerifier(testDeps(port2)).verify({ step, shot: testShot() })
    expect(done.nextHint).toBeUndefined()
    expect(done.learnerMisstep).toBeUndefined()
  })

  it('says it could not check when nothing works, and when there is no screenshot', async () => {
    const { port } = fakePort(() => {
      throw apiError(400)
    })
    const v = await createVerifier(testDeps(port)).verify({ step, shot: testShot() })
    expect(v).toMatchObject({ completed: false, uncertain: true, confidence: 0 })
    const { port: port2, calls } = fakePort(() => verdict({}))
    const none = await createVerifier(testDeps(port2)).verify({ step })
    expect(none.uncertain).toBe(true)
    expect(calls).toHaveLength(0)
  })

  it('grabs its own verify shot when a capture dependency exists', async () => {
    const purposes: string[] = []
    const { port } = fakePort(() => verdict({ completed: true, confidence: 0.9 }))
    const v = await createVerifier(testDeps(port, { capture: { grab: async (p) => (purposes.push(p), testShot()) } })).verify({ step })
    expect(purposes).toEqual(['verify'])
    expect(v.completed).toBe(true)
  })
})
