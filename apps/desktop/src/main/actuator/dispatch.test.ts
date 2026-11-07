import { describe, expect, it, vi } from 'vitest'
import { DEFAULT_SETTINGS } from '../../shared/settings'
import { Bus } from '../bus'
import type { ServiceContext } from '../context'
import { createDispatcher } from '../tools/dispatcher'
import { createActuator } from './index'

function setup(doItForMeAllowed: boolean) {
  const ctx = {
    bus: new Bus(),
    userDataDir: null,
    log: vi.fn(),
    settings: { get: () => ({ ...DEFAULT_SETTINGS, doItForMeAllowed }) },
    state: { get: () => ({ phase: 'live', agents: [], skill: undefined }) },
  } as unknown as ServiceContext
  const ground = vi.fn()
  const s = { capture: { grab: vi.fn() }, grounder: { ground }, overlay: { show: vi.fn(), clear: vi.fn() }, verifier: { verify: vi.fn() } } as never
  const actuator = createActuator({ dryRun: true, displayBounds: () => ({ x: 0, y: 0, width: 100, height: 100 }) })
  return { dispatch: createDispatcher(ctx, s, { ask: vi.fn(), cancel: vi.fn(), answer: vi.fn() } as never, actuator), ground }
}

describe('do_it_for_me through the dispatcher', () => {
  it('is registered, validated, and refuses when the setting is off (default)', async () => {
    const t = setup(false)
    expect(await t.dispatch('do_it_for_me', { target: 'Settings icon' }, 'live')).toMatchObject({ allowed: false, done: false, code: 'setting_off' })
    expect(t.ground).not.toHaveBeenCalled()
  })
  it('rejects bad arguments', async () => {
    const t = setup(true)
    expect(await t.dispatch('do_it_for_me', {}, 'live')).toMatchObject({ error: expect.stringContaining('Bad arguments for do_it_for_me') })
    expect(await t.dispatch('do_it_for_me', { target: '' }, 'live')).toHaveProperty('error')
  })
  it('default setting value is on (ask each time)', () => {
    expect(DEFAULT_SETTINGS.doItForMeAllowed).toBe(true)
  })
})
