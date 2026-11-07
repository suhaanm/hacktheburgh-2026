import { describe, expect, it, vi } from 'vitest'
import type { Grounder, Verifier } from '../../shared/contracts'
import type { GroundResult, NormBox, Verdict } from '../../shared/protocol'
import { fallbackPlan } from '../teaching/skills/plans'
import {
  createStageTruthGrounder,
  createStageTruthVerifier,
  installStageTruth,
  resolveTargetId,
  type StageEventLite,
  type StageStateLite,
  type StageTruthSource,
} from './stage-truth'

const box = (xmin: number, ymin: number, xmax: number, ymax: number): NormBox => ({ xmin, ymin, xmax, ymax })

const RECTS: Record<string, NormBox> = {
  'desk.icon.video': box(20, 60, 80, 140),
  'desk.icon.messages': box(20, 150, 80, 230),
  'desk.icon.settings': box(20, 240, 80, 320),
  'video.contact.lily': box(100, 200, 300, 260),
  'video.start_call': box(500, 400, 700, 460),
  'video.precall.join': box(520, 600, 680, 660),
  'video.toolbar.join': box(900, 100, 940, 130),
  'video.call.hangup': box(800, 900, 900, 960),
}

interface FakeStage extends StageTruthSource {
  state: StageStateLite
  events: StageEventLite[]
  rectMap: Record<string, NormBox>
  up: boolean
  fail: boolean
  rectCalls: number
}
function fakeStage(): FakeStage {
  const f: FakeStage = {
    state: { app: null, running: [], video: { view: 'contacts', selected: null, callState: 'idle' }, settings: { section: 'general' }, textStep: 0 },
    events: [],
    rectMap: RECTS,
    up: true,
    fail: false,
    rectCalls: 0,
    available: () => f.up,
    rects: async () => {
      f.rectCalls++
      if (f.fail) throw new Error('page gone')
      return f.rectMap
    },
    snapshot: async () => {
      if (f.fail) throw new Error('page gone')
      return { state: f.state, events: f.events }
    },
  }
  return f
}

const realGround = (): { grounder: Grounder; ground: ReturnType<typeof vi.fn>; prefetch: ReturnType<typeof vi.fn> } => {
  const ground = vi.fn(
    async (): Promise<GroundResult> => ({ found: true, box: box(1, 1, 2, 2), confidence: 0.8, label: 'model', latencyMs: 2500, model: 'gemini' }),
  )
  const prefetch = vi.fn()
  return { grounder: { ground, prefetch, invalidate: vi.fn() }, ground, prefetch }
}

const plan = fallbackPlan('video_call')
const step = (n: number) => plan.steps[n - 1]

describe('StageTruthGrounder', () => {
  it('resolves every video_call step instantly from the page, exactly the stage rect', async () => {
    const stage = fakeStage()
    const real = realGround()
    const g = createStageTruthGrounder(real.grounder, () => stage)
    const want = ['desk.icon.video', 'video.contact.lily', 'video.start_call', 'video.precall.join', 'video.call.hangup']
    for (let i = 0; i < 5; i++) {
      const res = await g.ground({ target: step(i + 1).targetDescription, precise: true })
      expect(res.found).toBe(true)
      expect(res.model).toBe('stage-truth')
      expect(res.confidence).toBe(1)
      expect(res.box).toEqual(RECTS[want[i]])
      expect(res.label).toBeTruthy()
      expect(res.latencyMs).toBeLessThan(50)
      // coordinate sanity: inside the display, point at the box centre
      const b = res.box!
      expect(b.xmin).toBeGreaterThanOrEqual(0)
      expect(b.xmax).toBeLessThanOrEqual(1000)
      expect(b.ymax).toBeLessThanOrEqual(1000)
      expect(b.xmax).toBeGreaterThan(b.xmin)
      expect(res.point).toEqual({ x: (b.xmin + b.xmax) / 2, y: (b.ymin + b.ymax) / 2 })
    }
    expect(real.ground).not.toHaveBeenCalled()
  })

  it('points at the desktop icons from free wording (point_at) and does not confuse the Join decoy', async () => {
    const stage = fakeStage()
    const g = createStageTruthGrounder(realGround().grounder, () => stage)
    expect((await g.ground({ target: 'the Settings app' })).box).toEqual(RECTS['desk.icon.settings'])
    expect((await g.ground({ target: 'Messages icon' })).box).toEqual(RECTS['desk.icon.messages'])
    expect((await g.ground({ target: 'VideoChat app icon on the desktop' })).box).toEqual(RECTS['desk.icon.video'])
    expect((await g.ground({ target: 'the big blue JOIN button on the Ready to join screen' })).box).toEqual(RECTS['video.precall.join'])
    expect((await g.ground({ target: 'Lily in the contacts list' })).box).toEqual(RECTS['video.contact.lily'])
    expect((await g.ground({ target: 'video.start_call' })).box).toEqual(RECTS['video.start_call'])
  })

  it('delegates unknown targets, hidden elements, an unavailable stage and errors to the real grounder', async () => {
    const stage = fakeStage()
    const real = realGround()
    const g = createStageTruthGrounder(real.grounder, () => stage, { appearWaitMs: 0 })
    expect((await g.ground({ target: 'the red Report junk phrase in the bank text' })).model).toBe('gemini')
    delete stage.rectMap['video.start_call']
    stage.rectMap = { ...RECTS }
    delete stage.rectMap['video.start_call']
    expect((await g.ground({ target: step(3).targetDescription })).model).toBe('gemini') // not visible
    stage.rectMap = RECTS
    stage.up = false
    expect((await g.ground({ target: step(2).targetDescription })).model).toBe('gemini') // stage hidden
    stage.up = true
    stage.fail = true
    expect((await g.ground({ target: step(2).targetDescription })).model).toBe('gemini') // page error
    const none = createStageTruthGrounder(real.grounder, () => null)
    expect((await none.ground({ target: step(2).targetDescription })).model).toBe('gemini') // no stage window at all
    expect(real.ground).toHaveBeenCalledTimes(5)
  })

  it('waits briefly for an element that is about to appear before asking the model', async () => {
    const stage = fakeStage()
    const late = { ...RECTS }
    delete late['video.precall.join']
    stage.rectMap = late
    let now = 0
    const sleep = vi.fn(async (ms: number) => {
      now += ms
      if (now >= 120) stage.rectMap = RECTS
    })
    const real = realGround()
    const g = createStageTruthGrounder(real.grounder, () => stage, { now: () => now, sleep })
    const res = await g.ground({ target: step(4).targetDescription })
    expect(res.model).toBe('stage-truth')
    expect(real.ground).not.toHaveBeenCalled()
  })

  it('prefetch is a no-op for visible known targets and warms the real grounder otherwise', async () => {
    const stage = fakeStage()
    const real = realGround()
    const g = createStageTruthGrounder(real.grounder, () => stage)
    g.prefetch?.({ target: step(2).targetDescription })
    g.prefetch?.({ target: 'something on the bank text' })
    await new Promise((r) => setTimeout(r, 20))
    expect(real.prefetch).toHaveBeenCalledTimes(1)
    expect(real.prefetch).toHaveBeenCalledWith({ target: 'something on the bank text' })
    g.invalidate?.()
    expect(real.grounder.invalidate).toHaveBeenCalled()
  })
})

describe('resolveTargetId', () => {
  it('knows the known step descriptions, ids and tolerates casing and punctuation', () => {
    expect(resolveTargetId(step(1).targetDescription.toUpperCase())).toBe('desk.icon.video')
    expect(resolveTargetId('video_call.pick_lily')).toBe('video.contact.lily')
    expect(resolveTargetId('  Large   BLUE button reading Join, below the camera preview... ')).toBe('video.precall.join')
    expect(resolveTargetId('the Aldermoor Bank scam text bubble')).toBeNull()
    expect(resolveTargetId('')).toBeNull()
  })
})

const click = (seq: number, id: string, t: number): StageEventLite => ({ seq, t, type: 'click', id })

describe('StageTruthVerifier', () => {
  const realVerdict: Verdict = { completed: false, confidence: 0.5, uncertain: true, evidence: 'model' }
  const realVerifier = (): { verifier: Verifier; verify: ReturnType<typeof vi.fn> } => {
    const verify = vi.fn(async () => realVerdict)
    return { verifier: { verify }, verify }
  }
  // A fake clock whose sleep() advances it, so the settle loop terminates exactly as it does with real time.
  const at = (t: number) => {
    let now = t
    return { now: () => now, sleep: async (ms: number) => void (now += ms) }
  }

  it('completes each video_call step from the page state, with no model call', async () => {
    const stage = fakeStage()
    const real = realVerifier()
    const v = createStageTruthVerifier(real.verifier, () => stage, at(10_000))
    const states: StageStateLite[] = [
      { app: 'video', running: ['video'], video: { view: 'contacts', selected: null, callState: 'idle' } },
      { app: 'video', running: ['video'], video: { view: 'contacts', selected: 'lily', callState: 'idle' } },
      { app: 'video', running: ['video'], video: { view: 'precall', selected: 'lily', callState: 'idle' } },
      { app: 'video', running: ['video'], video: { view: 'call', selected: 'lily', callState: 'ringing' } },
      { app: 'video', running: ['video'], video: { view: 'ended', selected: 'lily', callState: 'idle' } },
    ]
    for (let n = 1; n <= 5; n++) {
      stage.state = states[n - 1]
      const verdict = await v.verify({ step: step(n) })
      expect(verdict).toMatchObject({ completed: true, confidence: 1, uncertain: false })
      expect(verdict.evidence.length).toBeGreaterThan(5)
      // and the step before the page reached it is not done
      if (n > 1) {
        stage.state = states[n - 2]
        expect((await v.verify({ step: step(n) })).completed).toBe(false)
      }
    }
    expect(real.verify).not.toHaveBeenCalled()
  })

  it('a wrong click is not completed and names the right target (repair path); no click is a plain not-yet', async () => {
    const stage = fakeStage()
    const v = createStageTruthVerifier(realVerifier().verifier, () => stage, at(10_000))
    stage.state = { app: 'video', running: ['video'], video: { view: 'contacts', selected: 'dave', callState: 'idle' } }
    stage.events = [click(1, 'video.contact.dave', 9_800)]
    const wrong = await v.verify({ step: step(2) })
    expect(wrong.completed).toBe(false)
    expect(wrong.uncertain).toBe(false)
    expect(wrong.learnerMisstep).toMatch(/dave/i)
    expect(wrong.learnerMisstep).toMatch(/Lily/)
    expect(wrong.nextHint).toContain(step(2).hints.l2)
    // the same click is not held against the learner twice
    const again = await v.verify({ step: step(2) })
    expect(again.completed).toBe(false)
    expect(again.learnerMisstep).toBeUndefined()
    // the Join decoy in the contacts toolbar on step 4
    stage.state = { app: 'video', running: ['video'], video: { view: 'precall', selected: 'lily', callState: 'idle' } }
    stage.events = [click(2, 'video.toolbar.join', 9_900)]
    const decoy = await v.verify({ step: step(4) })
    expect(decoy.completed).toBe(false)
    expect(decoy.nextHint).toContain(step(4).hints.l2)
  })

  it('waits for the screen to settle before it answers (the tick does not flash at 0 ms)', async () => {
    const stage = fakeStage()
    stage.state = { app: 'video', running: ['video'], video: { view: 'contacts', selected: null, callState: 'idle' } }
    let now = 10_000
    stage.events = [click(1, 'desk.icon.video', 9_900)]
    const sleep = vi.fn(async (ms: number) => {
      now += ms
    })
    const v = createStageTruthVerifier(realVerifier().verifier, () => stage, { now: () => now, sleep, settleMs: 250 })
    const verdict = await v.verify({ step: step(1) })
    expect(verdict.completed).toBe(true)
    expect(sleep).toHaveBeenCalled()
    expect(now - 10_000).toBeGreaterThanOrEqual(150)
    expect(now - 10_000).toBeLessThanOrEqual(500)
  })

  it('delegates unknown steps, free-form expectations, an unavailable stage and page errors to the real verifier', async () => {
    const stage = fakeStage()
    const real = realVerifier()
    const v = createStageTruthVerifier(real.verifier, () => stage, at(10_000))
    const unknown = { ...step(1), id: 'custom.point', targetDescription: 'the weather widget top right', instruction: 'Look at it' }
    expect((await v.verify({ step: unknown })).evidence).toBe('model')
    expect((await v.verify({ expected: 'the task is complete' })).evidence).toBe('model')
    stage.up = false
    expect((await v.verify({ step: step(1) })).evidence).toBe('model')
    stage.up = true
    stage.fail = true
    expect((await v.verify({ step: step(1) })).evidence).toBe('model')
    expect(real.verify).toHaveBeenCalledTimes(4)
  })

  it('verifies an architect-style step by what it points at, not by its id', async () => {
    const stage = fakeStage()
    const v = createStageTruthVerifier(realVerifier().verifier, () => stage, at(10_000))
    stage.state = { app: 'video', running: ['video'], video: { view: 'precall', selected: 'lily', callState: 'idle' } }
    const architect = { ...step(4), id: 'step-4', targetDescription: 'The big blue Join button under the camera preview' }
    expect((await v.verify({ step: architect })).completed).toBe(false)
    stage.state = { app: 'video', running: ['video'], video: { view: 'call', selected: 'lily', callState: 'connected' } }
    expect((await v.verify({ step: architect })).completed).toBe(true)
  })
})

describe('installStageTruth', () => {
  const bag = () => {
    const real = realGround()
    return { grounder: real.grounder, verifier: { verify: vi.fn() } as unknown as Verifier }
  }
  it('does nothing without ALONGSIDE_DEMO_DIRECTOR=1', () => {
    const s = bag()
    const g = s.grounder
    installStageTruth(s, {}, {})
    expect(s.grounder).toBe(g)
  })
  it('wraps both services when the flag is set', () => {
    const s = bag()
    const g = s.grounder
    installStageTruth(s, {}, { ALONGSIDE_DEMO_DIRECTOR: '1' })
    expect(s.grounder).not.toBe(g)
    expect(typeof s.verifier.verify).toBe('function')
  })
})
