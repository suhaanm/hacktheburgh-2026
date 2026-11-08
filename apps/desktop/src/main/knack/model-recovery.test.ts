import { describe, expect, it, vi } from 'vitest'
import { MODE_ENV_KEYS, RECOVERED_ARG, RECOVERED_LINE, RECOVERY_INTERVAL_MS, RECOVERY_MIN_GAP_MS, createModelRecovery, recoveredAtFromArgs, relaunchArgs, restoreEnv, snapshotEnv, type ModelRecoveryDeps, type RecoveryTimers } from './model-recovery'

// Fake timers: nothing waits for real, every look is run by hand.
function fakeTimers(): RecoveryTimers & { pending(): number; fire(): Promise<void>; lastMs(): number } {
  let next: { fn: () => void; ms: number } | null = null
  return {
    set: (fn, ms) => {
      next = { fn, ms }
      return next
    },
    clear: (h) => {
      if (next === h) next = null
    },
    pending: () => (next ? 1 : 0),
    lastMs: () => next?.ms ?? -1,
    async fire() {
      const t = next
      next = null
      t?.fn()
      for (let i = 0; i < 8; i += 1) await Promise.resolve()
    },
  }
}

function rig(over: Partial<ModelRecoveryDeps> & { checks?: boolean[] } = {}) {
  const timers = fakeTimers()
  const answers = [...(over.checks ?? [])]
  const calls = { check: 0, relaunch: 0, said: [] as string[] }
  const { checks: _checks, ...rest } = over
  void _checks
  const r = createModelRecovery({
    check: async () => {
      calls.check += 1
      return answers.length ? (answers.shift() as boolean) : false
    },
    wanted: () => true,
    idle: () => true,
    relaunch: () => {
      calls.relaunch += 1
    },
    say: (l) => {
      calls.said.push(l)
    },
    log: () => undefined,
    timers,
    wait: () => new Promise(() => undefined), // the limit never fires in these tests
    now: () => 1_000_000,
    ...rest,
  })
  return { r, timers, calls }
}

describe('recovering from models off because the service could not be reached', () => {
  it('looks lightly: first after 20 seconds, then every 20 seconds, for as long as it runs', async () => {
    const { r, timers, calls } = rig()
    r.start()
    expect(timers.lastMs()).toBe(RECOVERY_INTERVAL_MS)
    expect(RECOVERY_INTERVAL_MS).toBe(20_000)
    expect(calls.check).toBe(0) // nothing at once: the start just tried
    for (let n = 1; n <= 5; n += 1) {
      await timers.fire()
      expect(calls.check).toBe(n)
      expect(timers.pending()).toBe(1)
      expect(timers.lastMs()).toBe(RECOVERY_INTERVAL_MS)
    }
    expect(r.phase()).toBe('watching')
    expect(calls.relaunch).toBe(0)
  })

  it('reopens the app once when the check passes and nothing is running, with one calm line first', async () => {
    const { r, timers, calls } = rig({ checks: [false, false, true] })
    r.start()
    await timers.fire()
    await timers.fire()
    expect(calls.relaunch).toBe(0)
    await timers.fire()
    expect(calls.said).toEqual([RECOVERED_LINE])
    expect(calls.relaunch).toBe(1)
    expect(r.phase()).toBe('reopening')
    expect(timers.pending()).toBe(0) // it does not look again, so it cannot reopen twice
    expect(RECOVERED_LINE.split(/\s+/).length).toBeLessThanOrEqual(22)
    expect(RECOVERED_LINE).not.toMatch(/mock|demo|sample|synthetic|example/i)
  })

  it('never reopens over a running job: it waits, and reopens at a later look once idle', async () => {
    let busy = true
    const { r, timers, calls } = rig({ checks: [true, true, true], idle: () => !busy })
    r.start()
    await timers.fire()
    expect(calls.relaunch).toBe(0)
    expect(r.phase()).toBe('waiting_for_idle')
    await timers.fire()
    expect(calls.relaunch).toBe(0)
    busy = false
    await timers.fire()
    expect(calls.relaunch).toBe(1)
    expect(calls.said).toEqual([RECOVERED_LINE])
  })

  it('does not look while the switch is off or the key is gone, and does not reopen then', async () => {
    let wanted = false
    const { r, timers, calls } = rig({ checks: [true, true], wanted: () => wanted })
    r.start()
    await timers.fire()
    expect(calls.check).toBe(0)
    expect(timers.pending()).toBe(1)
    wanted = true
    await timers.fire()
    expect(calls.check).toBe(1)
    expect(calls.relaunch).toBe(1)
  })

  it('a switch turned off while the check ran stops the reopening', async () => {
    let wanted = true
    const { r, timers, calls } = rig({
      check: async () => {
        wanted = false
        return true
      },
      wanted: () => wanted,
    })
    r.start()
    await timers.fire()
    expect(calls.relaunch).toBe(0)
    expect(timers.pending()).toBe(1)
    expect(r.phase()).toBe('watching')
  })

  it('a throwing check or a check that never answers counts as not yet, and the next look comes', async () => {
    const { r, timers, calls } = rig({
      check: async () => {
        throw new Error('no network')
      },
    })
    r.start()
    await timers.fire()
    expect(calls.relaunch).toBe(0)
    expect(timers.pending()).toBe(1)
    const hang = rig({ check: () => new Promise<boolean>(() => undefined), wait: async () => undefined, limitMs: 5 })
    hang.r.start()
    await hang.timers.fire()
    expect(hang.calls.relaunch).toBe(0)
    expect(hang.timers.pending()).toBe(1)
  })

  it('after an automatic reopening it waits out a gap before another, then may reopen again', async () => {
    let t = 5_000_000
    const recent = rig({ checks: [true, true], recoveredAtMs: t - 60_000, now: () => t })
    recent.r.start()
    await recent.timers.fire()
    expect(recent.calls.relaunch).toBe(0) // reopened a minute ago: not again
    expect(recent.r.phase()).toBe('waiting_for_idle')
    t += RECOVERY_MIN_GAP_MS
    await recent.timers.fire()
    expect(recent.calls.relaunch).toBe(1)
  })

  it('stop() ends the watching at once (the app is closing)', async () => {
    const { r, timers, calls } = rig({ checks: [true] })
    r.start()
    r.stop()
    expect(timers.pending()).toBe(0)
    expect(r.phase()).toBe('stopped')
    await timers.fire()
    expect(calls.relaunch).toBe(0)
  })

  it('a line that cannot be shown does not stop the reopening', async () => {
    const say = vi.fn(() => {
      throw new Error('no notifications')
    })
    const { r, timers, calls } = rig({ checks: [true], say })
    r.start()
    await timers.fire()
    expect(calls.relaunch).toBe(1)
  })
})

describe('the reopened app', () => {
  it('carries the time of the reopening in its arguments, and reads it back', () => {
    const args = relaunchArgs(['--some-flag', `${RECOVERED_ARG}1`, 'x'], 1234.9)
    expect(args).toEqual(['--some-flag', 'x', `${RECOVERED_ARG}1234`])
    expect(recoveredAtFromArgs(args)).toBe(1234)
    expect(recoveredAtFromArgs(['--a'])).toBeNull()
    expect(recoveredAtFromArgs([`${RECOVERED_ARG}soon`])).toBeNull()
    expect(recoveredAtFromArgs([`${RECOVERED_ARG}-5`])).toBeNull()
  })

  it('starts from the environment the launch gave it, not from the mode the last run chose', () => {
    const env: Record<string, string | undefined> = { PATH: '/bin', UNDERSTUDY_ENGINE_URL: 'http://127.0.0.1:7700' }
    const snap = snapshotEnv(env)
    env.UNDERSTUDY_MOCK = '1'
    env.UNDERSTUDY_X = '1'
    env.UNDERSTUDY_DATA_DIR = '/repo/data/demo-data'
    env.KNACK_MODELS_REASON = 'boot_check_failed'
    env.UNDERSTUDY_ENGINE_URL = 'http://127.0.0.1:9999'
    restoreEnv(env, snap)
    expect(env.UNDERSTUDY_MOCK).toBeUndefined()
    expect('UNDERSTUDY_X' in env).toBe(false)
    expect(env.UNDERSTUDY_DATA_DIR).toBeUndefined()
    expect(env.KNACK_MODELS_REASON).toBeUndefined()
    expect(env.UNDERSTUDY_ENGINE_URL).toBe('http://127.0.0.1:7700')
    expect(env.PATH).toBe('/bin') // anything else is left alone
    expect(MODE_ENV_KEYS).toContain('UNDERSTUDY_MOCK')
  })
})
