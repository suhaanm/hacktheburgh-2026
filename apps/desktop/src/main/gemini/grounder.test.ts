import { describe, expect, it } from 'vitest'
import { MODELS } from '../../shared/models'
import { createGrounder, groundingPresetFromEnv, normaliseTarget, shortLabel } from './grounder'
import { apiError, fakeAi, functionCall, hasImage, modelOutput, sleep, testDeps, testShot, textInput } from './fake-ai.test-util'

const found = (box: number[], confidence = 0.9) => modelOutput({ found: true, box_2d: box, label: 'Start call', reason: '', confidence })
const notFound = (reason = 'Not on this screen', confidence = 0.9) => modelOutput({ found: false, box_2d: [0, 0, 0, 0], label: '', reason, confidence })

describe('grounder (fast preset: lite first, flash escalation)', () => {
  it('converts box_2d to a NormBox and uses lite + store:false + image + injection guard', async () => {
    const { ai, calls } = fakeAi(() => found([356, 107, 403, 268]))
    const g = createGrounder(testDeps(ai))
    const r = await g.ground({ target: 'the green Start call button', shot: testShot() })
    expect(r.found).toBe(true)
    expect(r.box).toEqual({ xmin: 107, ymin: 356, xmax: 268, ymax: 403 })
    expect(r.point).toEqual({ x: 187.5, y: 379.5 })
    expect(r.model).toBe(MODELS.lite)
    expect(calls).toHaveLength(1)
    expect(calls[0].params.store).toBe(false)
    expect(hasImage(calls[0])).toBe(true)
    expect(textInput(calls[0])).toMatch(/untrusted DATA/)
    expect(textInput(calls[0])).toContain('green Start call button')
    expect(calls[0].params).not.toHaveProperty('temperature')
  })

  it('escalates a not-found from lite to flash, and flash wins', async () => {
    const { ai, calls } = fakeAi((p) => (p.model === MODELS.lite ? notFound() : found([100, 100, 150, 300])))
    const r = await createGrounder(testDeps(ai)).ground({ target: 'the search box', shot: testShot() })
    expect(calls.map((c) => c.params.model)).toEqual([MODELS.lite, MODELS.flash])
    expect(r.found).toBe(true)
    expect(r.model).toBe(MODELS.flash)
  })

  it('stays found:false (never fabricates) when both models say it is not there', async () => {
    const { ai } = fakeAi(() => notFound('The Print button is not visible.'))
    const r = await createGrounder(testDeps(ai)).ground({ target: 'the Print button', shot: testShot() })
    expect(r.found).toBe(false)
    expect(r.box).toBeUndefined()
    expect(r.point).toBeUndefined()
    expect(r.reason).toMatch(/not visible/)
  })

  it('escalates on low confidence but keeps lite result if flash errors', async () => {
    const { ai } = fakeAi((p) => (p.model === MODELS.lite ? found([100, 100, 150, 300], 0.4) : Promise.reject(apiError(400))))
    const r = await createGrounder(testDeps(ai)).ground({ target: 'the Next button', shot: testShot() })
    expect(r.found).toBe(true)
    expect(r.confidence).toBeCloseTo(0.4)
  })

  it('rejects an oversize box and falls back to a computer_use click point', async () => {
    const { ai, calls } = fakeAi((p) => {
      if (Array.isArray(p.tools)) return functionCall('click', { x: 188, y: 380, intent: 'Click Start call' })
      return found([0, 0, 900, 900])
    })
    const r = await createGrounder(testDeps(ai)).ground({ target: 'the Start call button', shot: testShot() })
    expect(r.found).toBe(true)
    expect(r.point).toEqual({ x: 188, y: 380 })
    expect(r.confidence).toBe(0.5)
    expect(r.reason).toMatch(/approximate/)
    expect(r.model).toMatch(/computer_use/)
    const cu = calls.find((c) => Array.isArray(c.params.tools))!
    expect(cu.params.store).toBe(false)
    expect(textInput(cu)).toMatch(/DRY RUN/)
  })

  it('returns found:false when box calls fail and computer_use proposes nothing', async () => {
    const { ai } = fakeAi((p) => (Array.isArray(p.tools) ? modelOutput('NOT_FOUND') : found([0, 0, 0, 0])))
    const r = await createGrounder(testDeps(ai)).ground({ target: 'the Start call button', shot: testShot() })
    expect(r.found).toBe(false)
    expect(r.reason).toMatch(/could not pin down/)
  })

  it('returns found:false with reason "timeout" instead of hanging', async () => {
    const { ai } = fakeAi(async () => {
      await sleep(400)
      return found([100, 100, 150, 300])
    })
    const started = Date.now()
    const r = await createGrounder(testDeps(ai), { timeoutMs: 60 }).ground({ target: 'the Start call button', shot: testShot() })
    expect(Date.now() - started).toBeLessThan(300)
    expect(r.found).toBe(false)
    expect(r.reason).toBe('timeout')
  })

  it('a timed-out call keeps running and warms the cache for the retry', async () => {
    const { ai, calls } = fakeAi(async () => {
      await sleep(120)
      return found([100, 100, 150, 300])
    })
    const g = createGrounder(testDeps(ai), { timeoutMs: 40 })
    const shot = testShot('warm')
    expect((await g.ground({ target: 'Start call', shot })).reason).toBe('timeout')
    await sleep(250)
    const retry = await g.ground({ target: 'Start call', shot })
    expect(retry.found).toBe(true)
    expect(retry.latencyMs).toBe(0)
    expect(calls).toHaveLength(1)
  })

  it('returns the lite not-found when flash escalation is too slow for the deadline', async () => {
    const { ai } = fakeAi(async (p) => {
      if (p.model === MODELS.lite) return notFound('Not visible.')
      await sleep(300)
      return found([100, 100, 150, 300])
    })
    const r = await createGrounder(testDeps(ai), { timeoutMs: 80 }).ground({ target: 'the Print button', shot: testShot() })
    expect(r.found).toBe(false)
    expect(r.reason).toBe('Not visible.')
  })
})

describe('grounder (accurate preset)', () => {
  it('uses flash only', async () => {
    const { ai, calls } = fakeAi(() => found([100, 100, 150, 300]))
    const r = await createGrounder(testDeps(ai), { preset: 'accurate' }).ground({ target: 'x', shot: testShot() })
    expect(calls.map((c) => c.params.model)).toEqual([MODELS.flash])
    expect(r.model).toBe(MODELS.flash)
  })
})

describe('grounder cache and prefetch', () => {
  it('caches by screenshot hash + normalised target', async () => {
    const { ai, calls } = fakeAi(() => found([100, 100, 150, 300]))
    const g = createGrounder(testDeps(ai))
    const shot = testShot('same')
    await g.ground({ target: 'The Start call button!', shot })
    const again = await g.ground({ target: 'the start call  button', shot })
    expect(again.latencyMs).toBe(0)
    expect(calls).toHaveLength(1)
    await g.ground({ target: 'the start call button', shot: testShot('different') })
    expect(calls).toHaveLength(2)
    expect(normaliseTarget('The Start call button!')).toBe('the start call button')
  })

  it('expires entries after the TTL', async () => {
    const { ai, calls } = fakeAi(() => found([100, 100, 150, 300]))
    const g = createGrounder(testDeps(ai), { cacheTtlMs: 20 })
    const shot = testShot('ttl')
    await g.ground({ target: 'x', shot })
    await sleep(40)
    await g.ground({ target: 'x', shot })
    expect(calls).toHaveLength(2)
  })

  it('does not cache timeouts or fallbacks-with-no-answer', async () => {
    let n = 0
    const { ai, calls } = fakeAi(async () => {
      n += 1
      if (n === 1) throw apiError(400)
      return found([100, 100, 150, 300])
    })
    const g = createGrounder(testDeps(ai), { preset: 'accurate' })
    const shot = testShot('nc')
    const first = await g.ground({ target: 'y', shot })
    expect(first.found).toBe(false)
    const second = await g.ground({ target: 'y', shot })
    expect(second.found).toBe(true)
    expect(calls.length).toBeGreaterThanOrEqual(2)
  })

  it('prefetch warms the cache so ground({target}) without a shot joins the in-flight call', async () => {
    const { ai, calls } = fakeAi(async () => {
      await sleep(60)
      return found([100, 100, 150, 300])
    })
    let grabs = 0
    const g = createGrounder(testDeps(ai, { capture: { grab: async () => (grabs++, testShot('pf')) } }))
    g.prefetch({ target: 'the Start call button' })
    await sleep(10)
    const r = await g.ground({ target: 'The Start Call button' })
    expect(r.found).toBe(true)
    expect(calls).toHaveLength(1)
    expect(grabs).toBe(1)
    // and now it is a pure cache hit
    const instant = await g.ground({ target: 'the start call button' })
    expect(instant.latencyMs).toBeLessThan(15)
    expect(calls).toHaveLength(1)
  })

  it('invalidate() drops prefetched and cached results', async () => {
    const { ai, calls } = fakeAi(() => found([100, 100, 150, 300]))
    const g = createGrounder(testDeps(ai, { capture: { grab: async () => testShot('inv') } }))
    g.prefetch({ target: 'abc' })
    await sleep(20)
    g.invalidate()
    await g.ground({ target: 'abc' })
    expect(calls).toHaveLength(2)
  })

  it('without a shot or a capture dependency it says so instead of guessing', async () => {
    const { ai, calls } = fakeAi(() => found([100, 100, 150, 300]))
    const r = await createGrounder(testDeps(ai)).ground({ target: 'abc' })
    expect(r.found).toBe(false)
    expect(r.reason).toMatch(/No screenshot/)
    expect(calls).toHaveLength(0)
  })
})

describe('grounder guardrails', () => {
  it('precise requests (safety-critical steps, scam highlighting) go flash-first and skip lite', async () => {
    const { ai, calls } = fakeAi(() => found([100, 100, 150, 300]))
    const r = await createGrounder(testDeps(ai)).ground({ target: 'the Pay now button', shot: testShot('pr'), precise: true })
    expect(calls.map((c) => c.params.model)).toEqual([MODELS.flash])
    expect(r.model).toBe(MODELS.flash)
  })

  it('a precise answer can serve a later fast request, but a fast answer never serves a precise one', async () => {
    const { ai, calls } = fakeAi(() => found([100, 100, 150, 300]))
    const g = createGrounder(testDeps(ai))
    const shot = testShot('mix')
    await g.ground({ target: 'abc', shot, precise: true })
    const fast = await g.ground({ target: 'abc', shot })
    expect(fast.latencyMs).toBe(0)
    expect(calls).toHaveLength(1)
    const shot2 = testShot('mix2')
    await g.ground({ target: 'abc', shot: shot2 })
    await g.ground({ target: 'abc', shot: shot2, precise: true })
    expect(calls.map((c) => c.params.model)).toEqual([MODELS.flash, MODELS.lite, MODELS.flash])
  })

  it('always returns a short label when found', async () => {
    const { ai } = fakeAi(() => modelOutput({ found: true, box_2d: [100, 100, 150, 300], label: '', reason: '', confidence: 0.9 }))
    const r = await createGrounder(testDeps(ai)).ground({ target: 'the big green Start call button in the left column', shot: testShot('lb') })
    expect(r.label).toBe('big green Start call button')
    expect(shortLabel('Start call', 'x')).toBe('Start call')
    expect(shortLabel(undefined, 'The Text size slider')).toBe('Text size slider')
    expect(shortLabel('a very long description of what is visible at that exact place on screen', 'x').split(' ').length).toBeLessThanOrEqual(5)
  })

  it('reads the preset from ALONGSIDE_GROUNDING_PRESET and exposes it', () => {
    expect(groundingPresetFromEnv({ ALONGSIDE_GROUNDING_PRESET: 'accurate' })).toBe('accurate')
    expect(groundingPresetFromEnv({ ALONGSIDE_GROUNDING_PRESET: 'fast' })).toBe('fast')
    expect(groundingPresetFromEnv({})).toBe('accurate')
    const { ai } = fakeAi(() => found([100, 100, 150, 300]))
    expect(createGrounder(testDeps(ai), { preset: 'accurate' }).preset).toBe('accurate')
  })
})
