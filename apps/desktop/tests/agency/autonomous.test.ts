// Autonomous agency: no confirmation click ONLY when the owner opted in (trusted settings click), the system is idle, a lesson
// step is stalled, and no floor rule applies. Fake clock, fake actuator: never a real click.
import { describe, expect, it } from 'vitest'
import { Situation } from '../../src/main/agency/common'
import { createOpenForMe } from '../../src/main/agency/open-for-me'
import { ActionLimiter, evaluateAction, type PolicyContext } from '../../src/main/agency/policy'
import { ConfirmBroker } from '../../src/main/confirm'
import { SettingsStore } from '../../src/main/settings'
import { StateStore } from '../../src/main/state'
import { coerceSettings, DEFAULT_SETTINGS, SettingsSchema } from '../../src/shared/settings'
import { makeEnv } from './helpers'

const step = (i: number) => ({ lessonId: 'l', skillId: 'bigger_text' as const, stepIndex: i, stepCount: 5, phase: 'started' as const })

function setup(opts: { agency?: 'autonomous' | 'ask_each'; idle?: number } = {}) {
  const env = makeEnv({ agency: opts.agency ?? 'autonomous' })
  const idle = { s: opts.idle ?? 120 }
  env.deps.idleSeconds = () => idle.s
  const sit = new Situation(env.ctx, env.deps.now)
  const open = createOpenForMe(env.deps, sit, new ActionLimiter(1_000_000, 0, 100), () => undefined)
  const startStep = (i: number, stalled = true) => {
    env.bus.emit('lesson:step', step(i))
    if (stalled) env.clock.t += 100_000
  }
  return { env, sit, open, idle, startStep }
}
const URL1 = { kind: 'url' as const, value: 'https://www.ageuk.org.uk' }

describe('autonomous agency', () => {
  it('away + stalled step: no modal, performed through the actuator, audited auto-away', async () => {
    const { env, open, startStep } = setup()
    startStep(0)
    const r = await open(URL1)
    expect(r).toMatchObject({ done: true, code: 'done' })
    expect(env.asked).toEqual([])
    expect(env.calls).toEqual(['openUrl https://www.ageuk.org.uk'])
    expect(env.shown[0][0]).toMatchObject({ kind: 'bubble' }) // announced on screen before it ran
    expect(env.auditLines().at(-1)).toMatchObject({ decision: 'allowed', ok: true, approval: 'auto-away' })
  })

  it('user active (idle below the threshold): the normal modal is shown', async () => {
    const { env, open, startStep } = setup({ idle: 5 })
    startStep(0)
    await open(URL1)
    expect(env.asked).toHaveLength(1)
    expect(env.auditLines().at(-1)?.approval).toBeUndefined()
  })

  it('no active/stalled lesson step: the modal is shown', async () => {
    const a = setup()
    await a.open(URL1)
    expect(a.env.asked).toHaveLength(1)
    const b = setup()
    b.startStep(0, false) // step just started, not stalled yet
    await b.open(URL1)
    expect(b.env.asked).toHaveLength(1)
  })

  it('one action per step, three per session, then the modal', async () => {
    const { env, open, startStep } = setup()
    startStep(0)
    await open(URL1)
    await open(URL1) // second action in the same step
    expect(env.asked).toHaveLength(1)
    for (const i of [1, 2, 3]) {
      startStep(i)
      await open(URL1)
    }
    expect(env.asked).toHaveLength(2) // steps 1,2 auto (cap 3 incl. step 0); step 3 asked
  })

  it('floor still holds: denylisted label blocked, scam context and safety-critical step refuse', async () => {
    const ctx: PolicyContext = { agency: 'autonomous', safetyCriticalStep: false, scamContext: false, planApproved: false, stageOrigin: 'http://127.0.0.1:5180', fileRoots: [], homeDir: '/Users/lily' }
    expect(evaluateAction({ kind: 'click', label: 'Pay now' }, ctx)).toMatchObject({ allowed: false })
    expect(evaluateAction({ kind: 'click', label: 'Next' }, ctx)).toMatchObject({ allowed: true, ask: true })
    expect(evaluateAction({ kind: 'click', label: 'Next', secureField: true }, ctx)).toMatchObject({ allowed: false })
    const a = setup()
    a.startStep(0)
    a.env.state.patch({ skill: { id: 'spot_scam', name: 'Spot a scam', step: 1, stepCount: 3 } })
    expect(await a.open(URL1)).toMatchObject({ allowed: false, code: 'scam_check' })
    expect(a.env.calls).toEqual([])
    const b = setup()
    b.env.bus.emit('lesson:step', { ...step(0), step: { id: 's', index: 0, instruction: 'x', targetDescription: 'x', expectedOutcome: 'x', hints: { l1: '', l2: '', l3: '' }, safetyCritical: true } })
    b.env.clock.t += 100_000
    expect(await b.open(URL1)).toMatchObject({ allowed: false, code: 'safety_step' })
  })

  it('Stop cancels and switches autonomous off for the session', async () => {
    const { env, open, startStep } = setup()
    startStep(0)
    const p = open(URL1)
    env.bus.emit('session:ended', { reason: 'stop' }) // lands during the lead-in
    expect(await p).toMatchObject({ code: 'stopped' })
    expect(env.calls).toEqual([])
    expect(env.settings.get().agency).toBe('ask_each')
    startStep(1)
    await open(URL1)
    expect(env.asked).toHaveLength(1)
  })

  it('ask_each: idle and stalled change nothing; a synthetic click or wrong id cannot approve', async () => {
    const { env, open, startStep } = setup({ agency: 'ask_each' })
    startStep(0)
    await open(URL1)
    expect(env.asked).toHaveLength(1)
    const st = new StateStore(env.settings.get())
    const broker = new ConfirmBroker(st)
    const p = broker.ask('ok?', ['Yes', 'No'])
    expect(broker.answer('forged-id', 'Yes')).toBe(false)
    broker.cancel()
    expect(await p).toBeNull()
  })
})

describe('autonomous settings', () => {
  it('zod and migration accept autonomous; default is ask_per_task and 60 s', () => {
    expect(DEFAULT_SETTINGS.agency).toBe('ask_per_task')
    expect(DEFAULT_SETTINGS.awaySeconds).toBe(60)
    expect(SettingsSchema.shape.agency.safeParse('autonomous').success).toBe(true)
    expect(SettingsSchema.shape.awaySeconds.safeParse(2).success).toBe(false)
    const c = coerceSettings({ agency: 'autonomous' })
    expect(c).toMatchObject({ agency: 'autonomous', doItForMeAllowed: true })
  })

  it('only a trusted (dock UI) patch can switch it on', () => {
    const s = new SettingsStore(null)
    expect(s.patch({ agency: 'autonomous', awaySeconds: 3 }).agency).toBe('ask_per_task')
    expect(s.get().awaySeconds).toBe(60)
    expect(s.patch({ agency: 'autonomous' }, { trusted: true }).agency).toBe('autonomous')
    expect(s.get().doItForMeAllowed).toBe(true)
    expect(s.patch({ agency: 'ask_each' }).agency).toBe('ask_each')
  })
})
