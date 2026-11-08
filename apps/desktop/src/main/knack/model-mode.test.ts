import { describe, expect, it, vi } from 'vitest'
import { MODELS_OFF_NOTICE, boundedBootCheck, canSwitchModels, decideModels, keyPresent, modelStatus, planModels, wantsLive } from './model-mode'

describe('live or models off', () => {
  const base = { switchOn: true, hasKey: true, bootOk: true as boolean | null }
  it('is live with the switch on, a key and a passing check, and says nothing', () => {
    expect(decideModels(base)).toEqual({ mode: 'live', reason: 'live', notice: null })
  })
  it('falls back to models off with one calm line when the key is missing', () => {
    expect(decideModels({ ...base, hasKey: false, bootOk: null })).toEqual({ mode: 'demo', reason: 'no_key', notice: 'Models are off' })
  })
  it('falls back when the boot check fails', () => {
    expect(decideModels({ ...base, bootOk: false })).toEqual({ mode: 'demo', reason: 'boot_check_failed', notice: MODELS_OFF_NOTICE })
  })
  it('is models off when the worker switched live models off', () => {
    expect(decideModels({ ...base, switchOn: false })).toMatchObject({ mode: 'demo', reason: 'switched_off' })
  })
  it('KNACK_LIVE=0 forces models off; KNACK_LIVE=1 asks for live even with the switch off, but still needs the key and the check', () => {
    expect(wantsLive({ switchOn: true, envOverride: '0' })).toBe(false)
    expect(wantsLive({ switchOn: false, envOverride: '1' })).toBe(true)
    expect(decideModels({ ...base, switchOn: false, envOverride: '1' }).mode).toBe('live')
    expect(decideModels({ ...base, envOverride: '1', hasKey: false, bootOk: null }).reason).toBe('no_key')
  })
  it('the notice is one short line', () => {
    expect(MODELS_OFF_NOTICE.split(/\s+/).length).toBeLessThanOrEqual(5)
    expect(MODELS_OFF_NOTICE).not.toContain('\n')
  })
})

describe('the key', () => {
  it('is only tested for being there, never returned', () => {
    expect(keyPresent({ GEMINI_API_KEY: 'x' })).toBe(true)
    expect(keyPresent({ GEMINI_API_KEY: '   ' })).toBe(false)
    expect(keyPresent({})).toBe(false)
    expect(typeof keyPresent({ GEMINI_API_KEY: 'secret-value' })).toBe('boolean')
  })
})

describe('the boot check', () => {
  it('runs only when live is wanted and a key is present, and once', async () => {
    const check = vi.fn(async () => true)
    expect((await planModels({ switchOn: true, hasKey: false, bootCheck: check })).reason).toBe('no_key')
    expect((await planModels({ switchOn: false, hasKey: true, bootCheck: check })).reason).toBe('switched_off')
    expect(check).not.toHaveBeenCalled()
    expect((await planModels({ switchOn: true, hasKey: true, bootCheck: check })).mode).toBe('live')
    expect(check).toHaveBeenCalledTimes(1)
  })
  it('treats a failing, throwing or hanging check as failed, never as a hang', async () => {
    expect(await boundedBootCheck(async () => false, 100)).toBe(false)
    expect(await boundedBootCheck(async () => { throw new Error('no network') }, 100)).toBe(false)
    const never = (): Promise<boolean> => new Promise(() => undefined)
    expect(await boundedBootCheck(never, 50, async () => undefined)).toBe(false)
    expect((await planModels({ switchOn: true, hasKey: true, bootCheck: never, limitMs: 10, wait: async () => undefined })).reason).toBe('boot_check_failed')
  })
})

describe('the status next to the dot', () => {
  it('says what is running, from the agent service first', () => {
    expect(modelStatus(true, null)).toEqual({ live: false, text: 'Models are off' })
    expect(modelStatus(false, null)).toEqual({ live: true, text: 'Live models' })
    expect(modelStatus(null, decideModels({ switchOn: true, hasKey: true, bootOk: true }))).toEqual({ live: true, text: 'Live models' })
    expect(modelStatus(true, decideModels({ switchOn: true, hasKey: true, bootOk: true })).live).toBe(false) // an attached offline stack is shown as it is
    expect(modelStatus(null, null)).toEqual({ live: null, text: '' })
  })
})

describe('the Use live models switch', () => {
  it('may change when nothing runs and, to on, a key is there', () => {
    expect(canSwitchModels({ on: true, hasKey: true, running: false })).toEqual({ ok: true })
    expect(canSwitchModels({ on: false, hasKey: false, running: false })).toEqual({ ok: true }) // off needs no key
  })
  it('says why not: no key, a job is running, or the request is not a plain true or false', () => {
    expect(canSwitchModels({ on: true, hasKey: false, running: false })).toEqual({ ok: false, reason: 'no_key' })
    expect(canSwitchModels({ on: false, hasKey: true, running: true })).toEqual({ ok: false, reason: 'running' })
    for (const bad of ['yes', 1, null, undefined, {}]) expect(canSwitchModels({ on: bad, hasKey: true, running: false })).toEqual({ ok: false, reason: 'bad_request' })
  })
})
