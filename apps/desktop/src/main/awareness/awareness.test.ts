import { describe, expect, it } from 'vitest'
import { createAwareness, type AwarenessDeps } from './index'
import { AwarenessSettingsStore, CONSENT_VERSION, consentPatch } from './settings'
import { createFakeFrameSource } from './capture-fake'
import { awarenessEventProblem } from './events'
import { GOOD_ANSWER, fakeConsole, fakeFrontmost, fakePower, fakeShare, manualTimers, recordingPost, scriptedPort } from './awareness.test-util'

const FLAG_ON = { UNDERSTUDY_X_AWARENESS: '1' }

function rig(opts: { ledgerRows?: unknown[] | null; env?: Record<string, string | undefined>; patch?: Record<string, unknown>; bundle?: string | null; point?: () => { x: number; y: number }; session?: () => boolean } = {}) {
  const timers = manualTimers()
  let now = 1_800_000_000_000
  const store = new AwarenessSettingsStore(null, () => now)
  if (opts.patch) store.patch(opts.patch, { trusted: true })
  const post = recordingPost()
  const port = scriptedPort()
  const frames = createFakeFrameSource({ width: 2880, height: 1800 })
  const front = fakeFrontmost(opts.bundle === undefined ? 'com.microsoft.Excel' : opts.bundle)
  const cons = fakeConsole()
  const power = fakePower({ idle: 1 })
  const urls: string[] = []
  const point = opts.point ?? (() => ({ x: 200, y: 200 }))
  const deps: AwarenessDeps = {
    settings: store,
    engineUrl: 'http://127.0.0.1:7700',
    identity: () => ({ person: 'p_demo01', role: 'benefits-processor' }),
    env: opts.env ?? FLAG_ON,
    getCursorPoint: point,
    power,
    getJson: async (u) => {
      urls.push(u)
      if (u.includes('/privacy/ledger')) return opts.ledgerRows === undefined ? null : opts.ledgerRows === null ? null : { meta: {}, data: opts.ledgerRows }
      return null
    },
    post,
    frontmost: front,
    console: cons,
    screenShare: fakeShare(false),
    frames,
    port,
    workSession: opts.session ?? (() => true),
    timers,
    now: () => now,
  }
  const awareness = createAwareness(deps)
  const run = async (ms: number, step = 67) => {
    for (let t = 0; t < ms; t += step) {
      now += step
      timers.advance(step)
      await Promise.resolve()
    }
    await new Promise((res) => setTimeout(res, 0))
  }
  return { awareness, store, timers, post, port, frames, front, cons, power, urls, run, setNow: (v: number) => void (now = v), now: () => now }
}

describe('with the flag off nothing runs', () => {
  it('no timer is created, nothing is sampled, captured or posted, even with every setting on', async () => {
    const r = rig({ env: {}, patch: consentPatch({ trigger: true, periodic: true }) })
    r.awareness.start()
    await r.run(10_000)
    expect(r.timers.created()).toBe(0)
    expect(r.frames.grabs()).toBe(0)
    expect(r.front.reads()).toBe(0)
    expect(r.cons.reads()).toBe(0)
    expect(r.urls).toEqual([])
    expect(r.post.posts).toEqual([])
    expect(await r.awareness.hotkey()).toMatchObject({ ok: false, skip: 'layer_off' })
    expect(r.frames.grabs()).toBe(0)
    const st = r.awareness.getAwarenessState()
    expect(st).toMatchObject({ flagOn: false, running: false })
  })

  it('with the flag on but the setting off (the default) it is just as quiet', async () => {
    const r = rig()
    r.awareness.start()
    await r.run(10_000)
    expect(r.timers.created()).toBe(0)
    expect(r.frames.grabs()).toBe(0)
    expect(await r.awareness.hotkey()).toMatchObject({ ok: false, skip: 'layer_off' })
  })
})

describe('the layer on, no consent: features only, nothing captured', () => {
  it('samples the cursor and the app kind, posts window events, never polls the engine for a stuck score and never captures', async () => {
    const r = rig({ patch: { awarenessEnabled: true } })
    r.awareness.start()
    expect(r.timers.intervals().sort((a, b) => a - b)).toEqual([67, 2000]) // cursor 15 Hz, frontmost every 2 s; no periodic
    await r.run(7000)
    expect(r.urls.filter((u) => u.includes('/coach/next'))).toEqual([]) // awareness never polls /coach/next: the coach brain poll is shared (observeStuck)
    expect(r.frames.grabs()).toBe(0)
    await r.awareness.getAwarenessState()
    expect(r.awareness.getAwarenessState().queued).toBeGreaterThan(0)
    expect(await r.awareness.hotkey()).toMatchObject({ ok: false, skip: 'no_consent' })
    expect(r.frames.grabs()).toBe(0)
  })

  it('window events carry the app kind and validate; a denied app produces none', async () => {
    const r = rig({ patch: { awarenessEnabled: true } })
    r.awareness.start()
    await r.run(6000)
    await r.awareness.glancer() // touch
    // flush through the sink by reading the queue via a second call path: the sink posts on batch size, so force it with more time
    await r.run(30_000)
    const posted = r.post.posts.flatMap((p) => p.body as unknown[])
    expect(posted.length).toBeGreaterThan(0)
    for (const e of posted) expect(awarenessEventProblem(e)).toBeNull()
    expect(posted.every((e: any) => e.type === 'window' && e.app_kind === 'spreadsheet' && e.origin === 'real')).toBe(true)

    const d = rig({ patch: { awarenessEnabled: true }, bundle: 'com.1password.1password' })
    d.awareness.start()
    await d.run(40_000)
    expect(d.post.posts.flatMap((p) => p.body as unknown[])).toEqual([])
    expect(d.awareness.getAwarenessState().queued).toBe(0)
  })
})

describe('consent turns the pieces on, and withdrawing turns them off', () => {
  it('trigger consent starts no timer of its own (the stuck score is fed by the coach brain poll); periodic consent starts the one-second check; withdrawing stops it', async () => {
    const r = rig({ patch: { awarenessEnabled: true } })
    r.awareness.start()
    r.awareness.setConsent({ trigger: true })
    expect(r.timers.intervals().sort((a, b) => a - b)).toEqual([67, 2000])
    r.awareness.setConsent({ trigger: true, periodic: true })
    expect(r.timers.intervals().sort((a, b) => a - b)).toEqual([67, 1000, 2000])
    r.awareness.setConsent({ trigger: false })
    expect(r.timers.intervals().sort((a, b) => a - b)).toEqual([67, 2000])
    const st = r.awareness.getAwarenessState()
    expect(st.consent).toMatchObject({ trigger: false, periodic: false, recordedVersion: 0 })
    r.awareness.stop()
    expect(r.timers.active()).toBe(0)
  })

  it('setConsent records the consent version and exposes the consent text', () => {
    const r = rig()
    const st = r.awareness.setConsent({ trigger: true, strict: true })
    expect(st.consent).toMatchObject({ trigger: true, periodic: false, recordedVersion: CONSENT_VERSION, currentVersion: CONSENT_VERSION })
    expect(st.consent.at).toMatch(/^\d{4}-\d\d-\d\dT/)
    expect(st.consentText.length).toBeGreaterThan(100)
    expect(st.enabled).toBe(true)
  })
})

describe('triggers end to end', () => {
  it('two stuck readings over the threshold make one glance, with the reason stuck', async () => {
    const r = rig()
    r.awareness.start()
    r.awareness.setConsent({ trigger: true })
    r.awareness.observeStuck(0.85)
    expect(r.port.calls).toHaveLength(0) // one reading is not enough
    r.awareness.observeStuck(0.86)
    await r.run(200)
    expect(r.port.calls).toHaveLength(1)
    expect(r.port.calls[0].trigger).toBe('stuck')
    const st = r.awareness.getAwarenessState()
    expect(st.last.glance).toMatchObject({ trigger: 'stuck', app_kind: GOOD_ANSWER.app_kind, blocker: 'cannot_find_control' })
    expect(st.usage.callsToday).toBe(1)
    expect(st.sources.stuck).toMatch(/shared coach poll/)
    expect(r.urls.filter((u) => u.includes('/coach/next'))).toEqual([])
  })

  it('a low stuck probability never glances, and neither does a broken chain', async () => {
    const r = rig()
    r.awareness.start()
    r.awareness.setConsent({ trigger: true })
    for (let i = 0; i < 10; i++) r.awareness.observeStuck(0.2)
    r.awareness.observeStuck(0.9)
    r.awareness.observeStuck(null) // an unreadable reading breaks the chain
    r.awareness.observeStuck(0.9)
    await r.run(500)
    expect(r.port.calls).toHaveLength(0)
    expect(r.frames.grabs()).toBe(0)
  })

  it('stuck readings are ignored without consent, with the layer off, while paused or killed, and with the flag off', async () => {
    const none = rig({ patch: { awarenessEnabled: true } })
    none.awareness.start()
    none.awareness.observeStuck(0.95)
    none.awareness.observeStuck(0.95)
    await none.run(200)
    expect(none.port.calls).toHaveLength(0)
    const off = rig({ env: {} })
    off.awareness.start()
    off.awareness.observeStuck(0.95)
    off.awareness.observeStuck(0.95)
    await off.run(200)
    expect(off.port.calls).toHaveLength(0)
    const paused = rig()
    paused.awareness.start()
    paused.awareness.setConsent({ trigger: true })
    paused.awareness.pause()
    paused.awareness.observeStuck(0.95)
    paused.awareness.observeStuck(0.95)
    await paused.run(200)
    expect(paused.port.calls).toHaveLength(0)
  })

  it('the hotkey glances once, then is rate-limited for 10 s', async () => {
    const r = rig()
    r.awareness.start()
    r.awareness.setConsent({ trigger: true })
    expect((await r.awareness.hotkey()).ok).toBe(true)
    expect(await r.awareness.hotkey()).toMatchObject({ ok: false, skip: 'too_soon' })
    expect(r.awareness.getAwarenessState().last.skip).toMatchObject({ reason: 'too_soon', trigger: 'hotkey' })
    r.setNow(r.now() + 11_000)
    expect((await r.awareness.hotkey()).ok).toBe(true)
  })

  it('the periodic glance fires about every interval while a work session is on, and not without one', async () => {
    const r = rig({ patch: { glanceIntervalSec: 30 } })
    r.awareness.start()
    r.awareness.setConsent({ trigger: true, periodic: true, intervalSec: 30 })
    await r.run(95_000, 250)
    const n = r.port.calls.length
    expect(n).toBeGreaterThanOrEqual(2)
    expect(n).toBeLessThanOrEqual(4)
    expect(r.port.calls.every((c) => c.trigger === 'periodic')).toBe(true)

    let session = false
    const q = rig({ session: () => session })
    q.awareness.start()
    q.awareness.setConsent({ trigger: true, periodic: true })
    await q.run(95_000, 250)
    expect(q.port.calls).toHaveLength(0)
    session = true
    await q.run(40_000, 250)
    expect(q.port.calls.length).toBeGreaterThanOrEqual(1)
  })

  it('a loop (the cursor returns to the same place four times) glances with the reason loop', async () => {
    // 6 s cycles: 4 s resting at one place, then 2 s of sweeping across the screen. Four rests make the same stop four times.
    const START = 1_800_000_000_000
    let rr: ReturnType<typeof rig> | null = null
    const point = () => {
      const c = (rr ? rr.now() - START : 0) % 6000
      return c < 4000 ? { x: 480, y: 300 } : { x: 480 + (c - 4000) * 0.36, y: 300 + 80 * Math.sin(c / 90) }
    }
    rr = rig({ point })
    rr.awareness.start()
    rr.awareness.setConsent({ trigger: true })
    for (let i = 0; i < 6 && rr.port.calls.length === 0; i++) await rr.run(6000)
    expect(rr.port.calls.length).toBeGreaterThanOrEqual(1)
    expect(rr.port.calls[0].trigger).toBe('loop')
  })

  it('a cursor that rests once, or wanders, is not a loop', async () => {
    const START = 1_800_000_000_000
    let rr: ReturnType<typeof rig> | null = null
    const point = () => {
      const t = rr ? rr.now() - START : 0
      return { x: 300 + ((t * 0.7) % 900), y: 300 + ((t * 0.3) % 400) } // always moving
    }
    rr = rig({ point })
    rr.awareness.start()
    rr.awareness.setConsent({ trigger: true })
    await rr.run(60_000)
    expect(rr.port.calls).toHaveLength(0)
  })

  it('pausing stops glances and window events; resuming brings them back', async () => {
    const r = rig()
    r.awareness.start()
    r.awareness.setConsent({ trigger: true })
    r.awareness.pause()
    expect(r.awareness.getAwarenessState().paused).toBe(true)
    expect(await r.awareness.hotkey()).toMatchObject({ ok: false, skip: 'paused' })
    r.awareness.resume()
    expect((await r.awareness.hotkey()).ok).toBe(true)
  })

  it('lock and sleep events block glances until unlock and resume', async () => {
    const r = rig()
    r.awareness.start()
    r.awareness.setConsent({ trigger: true })
    r.power.fire('lock-screen')
    expect(await r.awareness.hotkey()).toMatchObject({ ok: false, skip: 'locked' })
    r.power.fire('unlock-screen')
    r.power.fire('suspend')
    expect(await r.awareness.hotkey()).toMatchObject({ ok: false, skip: 'asleep' })
    r.power.fire('resume')
    expect((await r.awareness.hotkey()).ok).toBe(true)
  })
})

describe('the caps survive a restart', () => {
  it('seeds the usage from the engine ledger once at start, so the daily dollar cap still holds', async () => {
    const START = 1_800_000_000_000
    const rows = [
      { t: new Date(START - 60_000).toISOString(), purpose: 'awareness.glance', status: 'ok', cost_estimate_usd: 0.4995 },
      { t: new Date(START - 120_000).toISOString(), purpose: 'calendar.suggestion_wording', status: 'ok', cost_estimate_usd: 9 }, // another purpose: ignored
    ]
    const r = rig({ patch: consentPatch({ trigger: true }), ledgerRows: rows })
    r.awareness.start()
    await new Promise((res) => setTimeout(res, 5))
    expect(r.urls.filter((u) => u.includes('/privacy/ledger'))).toEqual(['http://127.0.0.1:7700/privacy/ledger?limit=500'])
    const st = r.awareness.getAwarenessState()
    expect(st.usage.usdToday).toBeCloseTo(0.4995, 4)
    expect(await r.awareness.hotkey()).toMatchObject({ ok: false, skip: 'daily_cap' })
    expect(r.frames.grabs()).toBe(0)
    r.awareness.stop()
    r.awareness.start() // a second start does not seed twice
    await new Promise((res) => setTimeout(res, 5))
    expect(r.urls.filter((u) => u.includes('/privacy/ledger'))).toHaveLength(1)
  })

  it('an engine without the privacy ledger (404 or away) seeds nothing and nothing breaks', async () => {
    const r = rig({ patch: consentPatch({ trigger: true }), ledgerRows: null })
    r.awareness.start()
    await new Promise((res) => setTimeout(res, 5))
    expect(r.awareness.getAwarenessState().usage.callsToday).toBe(0)
    expect((await r.awareness.hotkey()).ok).toBe(true)
  })

  it('with the flag off the ledger is not even asked', async () => {
    const r = rig({ env: {}, patch: consentPatch({ trigger: true }) })
    r.awareness.start()
    await new Promise((res) => setTimeout(res, 5))
    expect(r.urls).toEqual([])
  })
})

describe('the state for the Privacy screen', () => {
  it('reports what was read from where, honestly', () => {
    const r = rig({ patch: { awarenessEnabled: true } })
    const st = r.awareness.getAwarenessState()
    expect(st.sources.clicks).toMatch(/unavailable/)
    expect(st.sources.screenCapture).toBe('fake')
    expect(st.sources.frontmost).toMatch(/never read/)
    expect(st.denyDefaults.always.password_manager.length).toBeGreaterThan(3)
    expect(st.usage).toMatchObject({ maxPerHour: 60, callsToday: 0 })
  })

  it('dispose releases every timer and listener', () => {
    const r = rig({ patch: consentPatch({ trigger: true, periodic: true }) })
    r.awareness.start()
    expect(r.timers.active()).toBeGreaterThan(0)
    r.awareness.dispose()
    expect(r.timers.active()).toBe(0)
  })
})

describe('setSwitch (the tray checkboxes)', () => {
  it('turning anything down is always allowed; turning glances up needs the consent already recorded, else it says so and changes nothing', () => {
    const r = rig()
    let o = r.awareness.setSwitch('trigger', true)
    expect(o.needsConsent).toBe(true)
    expect(o.state.consent.trigger).toBe(false)
    o = r.awareness.setSwitch('periodic', true)
    expect(o.needsConsent).toBe(true)
    expect(o.state.consent.periodic).toBe(false)
    o = r.awareness.setSwitch('enabled', true) // the always-on layer sends nothing by itself
    expect(o).toMatchObject({ needsConsent: false, state: { enabled: true } })
    r.awareness.setConsent({ trigger: true, periodic: true })
    o = r.awareness.setSwitch('periodic', false)
    expect(o.state.consent).toMatchObject({ trigger: true, periodic: false })
    o = r.awareness.setSwitch('periodic', true) // same consent text: no card needed
    expect(o).toMatchObject({ needsConsent: false, state: { consent: { trigger: true, periodic: true } } })
    o = r.awareness.setSwitch('trigger', false) // withdrawing clears the record, and periodic with it
    expect(o.state.consent).toMatchObject({ trigger: false, periodic: false, recordedVersion: 0 })
    expect(r.awareness.setSwitch('trigger', true).needsConsent).toBe(true) // back to the card
    expect(r.awareness.setSwitch('enabled', false).state.enabled).toBe(false)
  })

  it('periodic cannot be on without triggered glances', () => {
    const r = rig()
    r.awareness.setConsent({ trigger: true, periodic: false })
    r.awareness.setSwitch('periodic', true)
    expect(r.awareness.getAwarenessState().consent.periodic).toBe(true)
    const r2 = rig({ patch: { glanceConsentVersion: CONSENT_VERSION, glanceOnTrigger: false } })
    expect(r2.awareness.setSwitch('periodic', true)).toMatchObject({ needsConsent: true })
  })
})
