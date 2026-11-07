import { describe, expect, it } from 'vitest'
import { DEFAULT_TRIGGER_CONFIG, StuckDetector, clampPeriodicMs, evaluateGates, gatesForService, periodicDue, type GateInputs } from './triggers'
import { UsageMeter, dayKey, parseLedgerUsage, type UsageSnapshot } from './usage'
import { SKIP_REASONS } from './types'

const NOW = 1_800_000_000_000
const clear: GateInputs = {
  nowMs: NOW,
  layerOn: true,
  consent: { trigger: true, periodic: true },
  killed: false,
  pausedUntilMs: 0,
  locked: false,
  asleep: false,
  idleS: 2,
  screenShare: false,
  thermal: 'nominal',
  secureInput: 'off',
  bundleId: 'com.microsoft.Excel',
  appKind: 'spreadsheet',
  workSession: true,
}
const fresh: UsageSnapshot = { lastGlanceAt: null, callsLastHour: 0, usdToday: 0, callsToday: 0 }
const cfg = DEFAULT_TRIGGER_CONFIG

const gate = (g: Partial<GateInputs> = {}, u: Partial<UsageSnapshot> = {}, reason: Parameters<typeof evaluateGates>[0] = 'stuck', c = cfg) =>
  evaluateGates(reason, { ...clear, ...g }, { ...fresh, ...u }, c).skip

describe('StuckDetector', () => {
  it('needs two readings in a row at or over the threshold', () => {
    const d = new StuckDetector(0.7, 2)
    expect(d.observe(0.9, 0)).toBe(false)
    expect(d.observe(0.9, 3000)).toBe(true)
  })

  it('a reading under the threshold, or an unreadable one, breaks the chain', () => {
    const d = new StuckDetector(0.7, 2)
    expect(d.observe(0.9, 0)).toBe(false)
    expect(d.observe(0.5, 3000)).toBe(false)
    expect(d.observe(0.9, 6000)).toBe(false)
    expect(d.observe(null, 9000)).toBe(false)
    expect(d.observe(0.9, 12000)).toBe(false)
    expect(d.observe(0.9, 15000)).toBe(true)
  })

  it('fires once per episode: no repeat while it stays over, until it drops under or the re-arm time passes', () => {
    const d = new StuckDetector(0.7, 2, 120_000)
    d.observe(0.9, 0)
    expect(d.observe(0.9, 3000)).toBe(true)
    expect(d.observe(0.95, 6000)).toBe(false)
    expect(d.observe(0.95, 9000)).toBe(false)
    // drops, then stuck again
    d.observe(0.2, 12000)
    d.observe(0.9, 15000)
    expect(d.observe(0.9, 18000)).toBe(true)
    // stays over for the re-arm time
    expect(d.observe(0.9, 21000)).toBe(false)
    expect(d.observe(0.9, 18000 + 125_000)).toBe(false) // the re-arm restarts the count
    expect(d.observe(0.9, 18000 + 128_000)).toBe(true)
  })

  it('NaN, negative infinity and out-of-range readings never fire', () => {
    const d = new StuckDetector(0.7, 2)
    expect(d.observe(NaN, 0)).toBe(false)
    expect(d.observe(Infinity, 1)).toBe(false)
    expect(d.observe(0.8, 2)).toBe(false)
  })
})

describe('periodic', () => {
  it('is due one interval after the last glance, or after the session start when there was none', () => {
    expect(periodicDue(NOW - 29_000, NOW, 30_000, null)).toBe(false)
    expect(periodicDue(NOW - 30_000, NOW, 30_000, null)).toBe(true)
    expect(periodicDue(null, NOW, 30_000, NOW - 31_000)).toBe(true)
    expect(periodicDue(null, NOW, 30_000, null)).toBe(false)
  })

  it('the interval defaults to 30 s and is never under 15 s', () => {
    expect(clampPeriodicMs(30)).toBe(30_000)
    expect(clampPeriodicMs(5)).toBe(15_000)
    expect(clampPeriodicMs(0)).toBe(15_000)
    expect(clampPeriodicMs(NaN)).toBe(30_000)
    expect(clampPeriodicMs(90)).toBe(90_000)
  })
})

describe('gates, in order', () => {
  it('all clear: no skip', () => expect(gate()).toBeNull())

  it('the reasons are tested in the order of SKIP_REASONS', () => {
    const order: Array<[Partial<GateInputs>, Partial<UsageSnapshot>, string]> = [
      [{ layerOn: false }, {}, 'layer_off'],
      [{ consent: { trigger: false, periodic: false } }, {}, 'no_consent'],
      [{ killed: true }, {}, 'killed'],
      [{ pausedUntilMs: NOW + 1000 }, {}, 'paused'],
      [{ locked: true }, {}, 'locked'],
      [{ asleep: true }, {}, 'asleep'],
      [{ idleS: 61 }, {}, 'idle'],
      [{ screenShare: true }, {}, 'screen_share'],
      [{ thermal: 'serious' }, {}, 'thermal'],
      [{ secureInput: 'on' }, {}, 'secure_input'],
      [{ secureInput: 'unknown' }, {}, 'secure_input_unknown'],
      [{ bundleId: 'com.1password.1password', appKind: 'other' }, {}, 'app_denied'],
      [{ bundleId: null, appKind: 'unknown' }, {}, 'app_unknown'],
      [{}, { lastGlanceAt: NOW - 5000 }, 'too_soon'],
      [{}, { callsLastHour: 60 }, 'hourly_cap'],
      [{}, { usdToday: 0.499 }, 'daily_cap'],
    ]
    for (const [g, u, want] of order) expect(gate(g, u), want).toBe(want)
    const idx = (r: string): number => SKIP_REASONS.indexOf(r as never)
    const got = order.map((o) => o[2])
    expect(got.map(idx)).toEqual([...got.map(idx)].sort((a, b) => a - b))
  })

  it('earlier reasons win: killed beats secure input beats a denied app beats the caps', () => {
    expect(gate({ killed: true, secureInput: 'on', bundleId: 'com.1password.1password' }, { callsLastHour: 99 })).toBe('killed')
    expect(gate({ secureInput: 'on', bundleId: 'com.1password.1password' }, { callsLastHour: 99 })).toBe('secure_input')
    expect(gate({ bundleId: 'com.1password.1password' }, { callsLastHour: 99 })).toBe('app_denied')
  })

  it('unknown signals are skipped, not guessed: an unreadable idle time, screen share or thermal state do not block', () => {
    expect(gate({ idleS: null, screenShare: null, thermal: 'unknown' })).toBeNull()
  })

  it('strict mode is what turns unknown secure input and an unknown app into "no"; lax mode lets them through', () => {
    const lax = { ...cfg, strict: false }
    expect(gate({ secureInput: 'unknown' }, {}, 'stuck', lax)).toBeNull()
    expect(gate({ bundleId: null, appKind: 'unknown' }, {}, 'stuck', lax)).toBeNull()
    expect(gate({ secureInput: 'on' }, {}, 'stuck', lax)).toBe('secure_input') // known-on always blocks
    expect(gate({ bundleId: 'com.1password.1password', appKind: 'other' }, {}, 'stuck', lax)).toBe('app_denied')
  })

  it('messaging is denied in strict mode only; a worker denylist entry applies in both', () => {
    expect(gate({ bundleId: 'com.tinyspeck.slackmacgap', appKind: 'chat' })).toBe('app_denied')
    expect(gate({ bundleId: 'com.tinyspeck.slackmacgap', appKind: 'chat' }, {}, 'stuck', { ...cfg, strict: false })).toBeNull()
    expect(gate({ bundleId: 'com.example.mine', appKind: 'other' }, {}, 'stuck', { ...cfg, strict: false, workerDenylist: ['com.example.mine'] })).toBe('app_denied')
  })

  it('the three caps: 10 s apart, 60 an hour, and the dollar cap for the day', () => {
    expect(gate({}, { lastGlanceAt: NOW - 9_999 })).toBe('too_soon')
    expect(gate({}, { lastGlanceAt: NOW - 10_000 })).toBeNull()
    expect(gate({}, { callsLastHour: 59 })).toBeNull()
    expect(gate({}, { callsLastHour: 60 })).toBe('hourly_cap')
    // the call that could take the day past the cap is not made
    expect(gate({}, { usdToday: 0.5 - cfg.estCostUsd })).toBeNull()
    expect(gate({}, { usdToday: 0.5 - cfg.estCostUsd + 0.0001 })).toBe('daily_cap')
    expect(gate({}, {}, 'stuck', { ...cfg, dailyUsd: 0 })).toBe('daily_cap') // a zero cap means none
  })

  it('periodic needs its own consent and a work session; the other triggers do not need a session', () => {
    expect(gate({ consent: { trigger: true, periodic: false } }, {}, 'periodic')).toBe('no_consent')
    expect(gate({ consent: { trigger: true, periodic: false } }, {}, 'hotkey')).toBeNull()
    expect(gate({ workSession: false }, {}, 'periodic')).toBe('no_work_session')
    expect(gate({ workSession: false }, {}, 'stuck')).toBeNull()
    expect(gate({ workSession: false }, {}, 'hotkey')).toBeNull()
  })

  it('the hotkey is gated like the rest: it cannot reach a password manager or secure input', () => {
    expect(gate({ secureInput: 'on' }, {}, 'hotkey')).toBe('secure_input')
    expect(gate({ bundleId: 'com.bitwarden.desktop', appKind: 'other' }, {}, 'hotkey')).toBe('app_denied')
    expect(gate({}, { lastGlanceAt: NOW - 1000 }, 'hotkey')).toBe('too_soon')
  })
})

describe('what the service is told', () => {
  it('unattended is always false, consent is the worker consent, and strict turns unknowns into true', () => {
    const app = { verdict: 'allow' } as const
    expect(gatesForService({ secureInput: 'off' }, app, { strict: true }, true)).toEqual({ consent: true, denylisted_app: false, secure_input: false, unattended: false })
    expect(gatesForService({ secureInput: 'unknown' }, app, { strict: true }, true).secure_input).toBe(true)
    expect(gatesForService({ secureInput: 'unknown' }, app, { strict: false }, true).secure_input).toBe(false)
    expect(gatesForService({ secureInput: 'on' }, app, { strict: false }, true).secure_input).toBe(true)
    expect(gatesForService({ secureInput: 'off' }, { verdict: 'unknown' }, { strict: true }, true).denylisted_app).toBe(true)
    expect(gatesForService({ secureInput: 'off' }, { verdict: 'deny', category: 'worker_list' }, { strict: false }, false)).toMatchObject({ consent: false, denylisted_app: true, unattended: false })
  })
})

describe('UsageMeter', () => {
  it('counts the rolling hour and the local day, and reports the last call', () => {
    const t0 = new Date(2026, 10, 7, 12, 0, 0).getTime()
    let now = t0
    const m = new UsageMeter(() => now)
    m.record(0.001, t0 - 3 * 3_600_000)
    m.record(0.002, t0 - 30 * 60_000)
    m.record(0.003, t0 - 5 * 60_000)
    const s = m.snapshot(now)
    expect(s.callsLastHour).toBe(2)
    expect(s.callsToday).toBe(3)
    expect(s.usdToday).toBeCloseTo(0.006, 6)
    expect(s.lastGlanceAt).toBe(t0 - 5 * 60_000)
    now = new Date(2026, 10, 8, 0, 5, 0).getTime() // the next local day
    expect(m.snapshot(now).usdToday).toBe(0)
    expect(m.snapshot(now).callsToday).toBe(0)
  })

  it('seeds from a ledger so a restart does not reset the cap, and ignores junk', () => {
    const t0 = new Date(2026, 10, 7, 12, 0, 0).getTime()
    const m = new UsageMeter(() => t0)
    m.seed([{ at: t0 - 1000, usd: 0.4 }, { at: NaN, usd: 1 }, { at: t0 - 2000, usd: -5 }])
    expect(m.snapshot().usdToday).toBeCloseTo(0.4, 6)
    expect(dayKey(t0)).toBe(20261107)
  })
})

describe('parseLedgerUsage', () => {
  it('keeps only glance rows with a readable time, with their cost when reported', () => {
    const rows = [
      { t: '2026-11-07T10:00:00.000Z', purpose: 'awareness.glance', status: 'ok', cost_estimate_usd: 0.0003 },
      { t: '2026-11-07T10:01:00.000Z', purpose: 'awareness.glance', status: 'blocked' },
      { t: 'garbage', purpose: 'awareness.glance' },
      { t: '2026-11-07T10:02:00.000Z', purpose: 'digest.meta', cost_estimate_usd: 5 },
      { t: '2026-11-07T10:03:00.000Z', purpose: 'awareness.glance', cost_estimate_usd: -3 },
      null,
      'x',
    ]
    const want = [
      { at: Date.parse('2026-11-07T10:00:00.000Z'), usd: 0.0003 },
      { at: Date.parse('2026-11-07T10:01:00.000Z'), usd: 0 },
      { at: Date.parse('2026-11-07T10:03:00.000Z'), usd: 0 },
    ]
    expect(parseLedgerUsage({ meta: {}, data: rows })).toEqual(want)
    expect(parseLedgerUsage(rows)).toEqual(want)
    expect(parseLedgerUsage(null)).toEqual([])
    expect(parseLedgerUsage({ error: { code: 'extension_off' } })).toEqual([])
  })
})
