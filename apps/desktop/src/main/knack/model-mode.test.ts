import { describe, expect, it, vi } from 'vitest'
import { BOOT_LIMITS_MS, BOOT_PAUSE_MS, MODELS_OFF_NOTICE, MODELS_RETRY_NOTICE, MODELS_UNREACHABLE_LINE, boundedBootCheck, canSwitchModels, decideModels, keyPresent, modelStatus, planModels, wantsLive } from './model-mode'

describe('live or models off', () => {
  const base = { switchOn: true, hasKey: true, bootOk: true as boolean | null }
  it('is live with the switch on, a key and a passing check, and says nothing', () => {
    expect(decideModels(base)).toEqual({ mode: 'live', reason: 'live', notice: null })
  })
  it('falls back to models off with one calm line when the key is missing', () => {
    expect(decideModels({ ...base, hasKey: false, bootOk: null })).toEqual({ mode: 'demo', reason: 'no_key', notice: 'Models are off' })
  })
  it('falls back when the boot check fails', () => {
    expect(decideModels({ ...base, bootOk: false })).toEqual({ mode: 'demo', reason: 'boot_check_failed', notice: MODELS_RETRY_NOTICE })
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
  it('tries a failed check again, up to three times, so one slow start does not switch the models off for the session', async () => {
    let n = 0
    const slowThenFine = vi.fn(async () => { n += 1; return n > 1 })
    expect((await planModels({ switchOn: true, hasKey: true, bootCheck: slowThenFine, wait: async () => undefined })).mode).toBe('live')
    expect(slowThenFine).toHaveBeenCalledTimes(2)
    let m = 0
    const thirdTime = vi.fn(async () => { m += 1; return m > 2 })
    expect((await planModels({ switchOn: true, hasKey: true, bootCheck: thirdTime, wait: async () => undefined })).mode).toBe('live')
    expect(thirdTime).toHaveBeenCalledTimes(3)
    const always = vi.fn(async () => false)
    expect((await planModels({ switchOn: true, hasKey: true, bootCheck: always, wait: async () => undefined })).reason).toBe('boot_check_failed')
    expect(always).toHaveBeenCalledTimes(3)
  })
  it('gives each attempt a little longer, none longer than twelve seconds', async () => {
    expect([...BOOT_LIMITS_MS]).toEqual([...BOOT_LIMITS_MS].sort((a, b) => a - b))
    expect(Math.max(...BOOT_LIMITS_MS)).toBeLessThanOrEqual(12_000)
    expect(BOOT_LIMITS_MS.length).toBe(3)
    // A check that never answers: the limits the timer is asked for are the growing ones, in order.
    const asked: number[] = []
    const never = (): Promise<boolean> => new Promise(() => undefined)
    const wait = (ms: number): Promise<void> => { asked.push(ms); return Promise.resolve() }
    const d = await planModels({ switchOn: true, hasKey: true, bootCheck: never, wait })
    expect(d.reason).toBe('boot_check_failed')
    // wait() is used both for the limit and the short pause between attempts
    expect(asked.filter((ms) => ms !== BOOT_PAUSE_MS)).toEqual([...BOOT_LIMITS_MS])
  })
  it('a failure that comes at once (no network) is not waited for: the pauses add up to about two seconds', async () => {
    const pauses: number[] = []
    const wait = (ms: number): Promise<void> => { pauses.push(ms); return Promise.resolve() }
    const noNetwork = vi.fn(async () => { throw new Error('ENOTFOUND') })
    const d = await planModels({ switchOn: true, hasKey: true, bootCheck: noNetwork, wait: (ms) => (ms === BOOT_PAUSE_MS ? wait(ms) : new Promise(() => undefined)) })
    expect(d.reason).toBe('boot_check_failed')
    expect(noNetwork).toHaveBeenCalledTimes(3)
    expect(pauses.reduce((a, b) => a + b, 0)).toBeLessThanOrEqual(2000)
  })
  it('a models-off start that is only a failed check says it is trying again, and says the real reason in plain words', () => {
    expect(MODELS_RETRY_NOTICE.split(/\s+/).length).toBeLessThanOrEqual(5)
    const d = decideModels({ switchOn: true, hasKey: true, bootOk: false })
    expect(d.notice).toBe(MODELS_RETRY_NOTICE)
    expect(modelStatus(true, d).text).toBe(MODELS_RETRY_NOTICE)
    expect(modelStatus(null, d).text).toBe(MODELS_RETRY_NOTICE)
    expect(modelStatus(false, d)).toEqual({ live: true, text: 'Live models' }) // once the service itself says live, it is live
    expect(modelStatus(true, decideModels({ switchOn: false, hasKey: true, bootOk: null })).text).toBe(MODELS_OFF_NOTICE) // switched off stays plain
    expect(MODELS_UNREACHABLE_LINE).toBe('Knack could not reach the model service. It keeps trying and will switch on by itself.')
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
