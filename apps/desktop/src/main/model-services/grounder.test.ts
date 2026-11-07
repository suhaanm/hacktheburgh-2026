import { describe, expect, it } from 'vitest'
import { createGrounder, groundingPresetFromEnv, normaliseTarget, shortLabel } from './grounder'
import { apiError, fakePort, hasImage, modelOutput, sleep, TEST_IDS, testDeps, testShot, textInput } from '../model-port/fake-port.test-util'

const found = (box: number[], confidence = 0.9) => modelOutput({ found: true, box: box, label: 'Start call', reason: '', confidence })
const notFound = (reason = 'Not on this screen', confidence = 0.9) => modelOutput({ found: false, box: [0, 0, 0, 0], label: '', reason, confidence })

describe('grounder (fast preset: fast tier first, planner escalation)', () => {
  it('converts the box to a NormBox and uses the fast tier + image + injection guard', async () => {
    const { port, calls } = fakePort(() => found([107, 356, 268, 403]))
    const g = createGrounder(testDeps(port))
    const r = await g.ground({ target: 'the green Start call button', shot: testShot() })
    expect(r.found).toBe(true)
    expect(r.box).toEqual({ xmin: 107, ymin: 356, xmax: 268, ymax: 403 })
    expect(r.point).toEqual({ x: 187.5, y: 379.5 })
    expect(r.model).toBe(TEST_IDS.fast)
    expect(calls).toHaveLength(1)
    expect(calls[0].tier).toBe('fast')
    expect(hasImage(calls[0])).toBe(true)
    expect(textInput(calls[0])).toMatch(/untrusted DATA/)
    expect(textInput(calls[0])).toContain('green Start call button')
    expect(calls[0].schema?.name).toBe('ground_box')
  })

  it('escalates a not-found from the fast tier to the planner, and the planner wins', async () => {
    const { port, calls } = fakePort((req) => (req.tier === 'fast' ? notFound() : found([100, 100, 300, 150])))
    const r = await createGrounder(testDeps(port)).ground({ target: 'the search box', shot: testShot() })
    expect(calls.map((c) => c.tier)).toEqual(['fast', 'planner'])
    expect(r.found).toBe(true)
    expect(r.model).toBe(TEST_IDS.planner)
  })

  it('stays found:false (never fabricates) when both tiers say it is not there', async () => {
    const { port } = fakePort(() => notFound('The Print button is not visible.'))
    const r = await createGrounder(testDeps(port)).ground({ target: 'the Print button', shot: testShot() })
    expect(r.found).toBe(false)
    expect(r.box).toBeUndefined()
    expect(r.point).toBeUndefined()
    expect(r.reason).toMatch(/not visible/)
  })

  it('escalates on low confidence but keeps the fast result if the planner errors', async () => {
    const { port } = fakePort((req) => (req.tier === 'fast' ? found([100, 100, 300, 150], 0.4) : Promise.reject(apiError(400))))
    const r = await createGrounder(testDeps(port)).ground({ target: 'the Next button', shot: testShot() })
    expect(r.found).toBe(true)
    expect(r.confidence).toBeCloseTo(0.4)
  })

  it('rejects an oversize box and falls back to a computer-tool click point (a dry run, nothing is executed)', async () => {
    const { port, calls, steps } = fakePort(() => found([0, 0, 900, 900]), {
      computerStep: () => ({ kind: 'actions', actions: [{ type: 'click', x: 360, y: 410 }], callId: 'c', widthPx: 1920, heightPx: 1080, model: 'test-cu', ms: 1 }),
    })
    const r = await createGrounder(testDeps(port)).ground({ target: 'the Start call button', shot: testShot() })
    expect(calls.length).toBeGreaterThanOrEqual(1)
    expect(r.found).toBe(true)
    expect(r.point).toEqual({ x: 188, y: 380 })
    expect(r.confidence).toBe(0.5)
    expect(r.reason).toMatch(/approximate/)
    expect(r.model).toMatch(/computer_use/)
    expect(steps).toHaveLength(1)
    expect(steps[0].goal).toMatch(/DRY RUN/)
    expect(steps[0].history).toEqual([])
  })

  it('returns found:false when box calls fail and the computer tool proposes nothing', async () => {
    const { port } = fakePort(() => found([0, 0, 0, 0]), { computerStep: () => ({ kind: 'done', text: 'NOT_FOUND', model: 'test-cu', ms: 1 }) })
    const r = await createGrounder(testDeps(port)).ground({ target: 'the Start call button', shot: testShot() })
    expect(r.found).toBe(false)
    expect(r.reason).toMatch(/could not pin down/)
  })

  it('returns found:false with reason "timeout" instead of hanging', async () => {
    const { port } = fakePort(async () => {
      await sleep(400)
      return found([100, 100, 300, 150])
    })
    const started = Date.now()
    const r = await createGrounder(testDeps(port), { timeoutMs: 60 }).ground({ target: 'the Start call button', shot: testShot() })
    expect(Date.now() - started).toBeLessThan(300)
    expect(r.found).toBe(false)
    expect(r.reason).toBe('timeout')
  })

  it('a timed-out call keeps running and warms the cache for the retry', async () => {
    const { port, calls } = fakePort(async () => {
      await sleep(120)
      return found([100, 100, 300, 150])
    })
    const g = createGrounder(testDeps(port), { timeoutMs: 40 })
    const shot = testShot('warm')
    expect((await g.ground({ target: 'Start call', shot })).reason).toBe('timeout')
    await sleep(250)
    const retry = await g.ground({ target: 'Start call', shot })
    expect(retry.found).toBe(true)
    expect(retry.latencyMs).toBe(0)
    expect(calls).toHaveLength(1)
  })

  it('returns the fast not-found when planner escalation is too slow for the deadline', async () => {
    const { port } = fakePort(async (req) => {
      if (req.tier === 'fast') return notFound('Not visible.')
      await sleep(300)
      return found([100, 100, 300, 150])
    })
    const r = await createGrounder(testDeps(port), { timeoutMs: 80 }).ground({ target: 'the Print button', shot: testShot() })
    expect(r.found).toBe(false)
    expect(r.reason).toBe('Not visible.')
  })
})

describe('grounder (accurate preset)', () => {
  it('uses the planner tier only', async () => {
    const { port, calls } = fakePort(() => found([100, 100, 300, 150]))
    const r = await createGrounder(testDeps(port), { preset: 'accurate' }).ground({ target: 'x', shot: testShot() })
    expect(calls.map((c) => c.tier)).toEqual(['planner'])
    expect(r.model).toBe(TEST_IDS.planner)
  })
})

describe('grounder cache and prefetch', () => {
  it('caches by screenshot hash + normalised target', async () => {
    const { port, calls } = fakePort(() => found([100, 100, 300, 150]))
    const g = createGrounder(testDeps(port))
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
    const { port, calls } = fakePort(() => found([100, 100, 300, 150]))
    const g = createGrounder(testDeps(port), { cacheTtlMs: 20 })
    const shot = testShot('ttl')
    await g.ground({ target: 'x', shot })
    await sleep(40)
    await g.ground({ target: 'x', shot })
    expect(calls).toHaveLength(2)
  })

  it('does not cache timeouts or fallbacks-with-no-answer', async () => {
    let n = 0
    const { port, calls } = fakePort(async () => {
      n += 1
      if (n === 1) throw apiError(400)
      return found([100, 100, 300, 150])
    })
    const g = createGrounder(testDeps(port), { preset: 'accurate' })
    const shot = testShot('nc')
    const first = await g.ground({ target: 'y', shot })
    expect(first.found).toBe(false)
    const second = await g.ground({ target: 'y', shot })
    expect(second.found).toBe(true)
    expect(calls.length).toBeGreaterThanOrEqual(2)
  })

  it('prefetch warms the cache so ground({target}) without a shot joins the in-flight call', async () => {
    const { port, calls } = fakePort(async () => {
      await sleep(60)
      return found([100, 100, 300, 150])
    })
    let grabs = 0
    const g = createGrounder(testDeps(port, { capture: { grab: async () => (grabs++, testShot('pf')) } }))
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
    const { port, calls } = fakePort(() => found([100, 100, 300, 150]))
    const g = createGrounder(testDeps(port, { capture: { grab: async () => testShot('inv') } }))
    g.prefetch({ target: 'abc' })
    await sleep(20)
    g.invalidate()
    await g.ground({ target: 'abc' })
    expect(calls).toHaveLength(2)
  })

  it('without a shot or a capture dependency it says so instead of guessing', async () => {
    const { port, calls } = fakePort(() => found([100, 100, 300, 150]))
    const r = await createGrounder(testDeps(port)).ground({ target: 'abc' })
    expect(r.found).toBe(false)
    expect(r.reason).toMatch(/No screenshot/)
    expect(calls).toHaveLength(0)
  })
})

describe('grounder guardrails', () => {
  it('precise requests (safety-critical steps, scam highlighting) go planner-first and skip the fast tier', async () => {
    const { port, calls } = fakePort(() => found([100, 100, 300, 150]))
    const r = await createGrounder(testDeps(port)).ground({ target: 'the Pay now button', shot: testShot('pr'), precise: true })
    expect(calls.map((c) => c.tier)).toEqual(['planner'])
    expect(r.model).toBe(TEST_IDS.planner)
  })

  it('a precise answer can serve a later fast request, but a fast answer never serves a precise one', async () => {
    const { port, calls } = fakePort(() => found([100, 100, 300, 150]))
    const g = createGrounder(testDeps(port))
    const shot = testShot('mix')
    await g.ground({ target: 'abc', shot, precise: true })
    const fast = await g.ground({ target: 'abc', shot })
    expect(fast.latencyMs).toBe(0)
    expect(calls).toHaveLength(1)
    const shot2 = testShot('mix2')
    await g.ground({ target: 'abc', shot: shot2 })
    await g.ground({ target: 'abc', shot: shot2, precise: true })
    expect(calls.map((c) => c.tier)).toEqual(['planner', 'fast', 'planner'])
  })

  it('always returns a short label when found', async () => {
    const { port } = fakePort(() => modelOutput({ found: true, box: [100, 100, 300, 150], label: '', reason: '', confidence: 0.9 }))
    const r = await createGrounder(testDeps(port)).ground({ target: 'the big green Start call button in the left column', shot: testShot('lb') })
    expect(r.label).toBe('big green Start call button')
    expect(shortLabel('Start call', 'x')).toBe('Start call')
    expect(shortLabel(undefined, 'The Text size slider')).toBe('Text size slider')
    expect(shortLabel('a very long description of what is visible at that exact place on screen', 'x').split(' ').length).toBeLessThanOrEqual(5)
  })

  it('reads the preset from ALONGSIDE_GROUNDING_PRESET and exposes it', () => {
    expect(groundingPresetFromEnv({ ALONGSIDE_GROUNDING_PRESET: 'accurate' })).toBe('accurate')
    expect(groundingPresetFromEnv({ ALONGSIDE_GROUNDING_PRESET: 'fast' })).toBe('fast')
    expect(groundingPresetFromEnv({})).toBe('accurate')
    const { port } = fakePort(() => found([100, 100, 300, 150]))
    expect(createGrounder(testDeps(port), { preset: 'accurate' }).preset).toBe('accurate')
  })
})
