import { describe, expect, it, vi } from 'vitest'
import { applyChoice, AwarenessChoiceSchema, cardState, trayAwareness } from './awareness-card'
import { CONSENT_SHORT, CONSENT_VERSION } from './awareness/settings'

function fake(over: { recorded?: number; trigger?: boolean; periodic?: boolean } = {}) {
  const st = {
    consentText: 'the text the worker reads',
    enabled: true,
    strict: true,
    periodicIntervalSec: 30,
    consent: { trigger: over.trigger ?? false, periodic: over.periodic ?? false, recordedVersion: over.recorded ?? 0, currentVersion: CONSENT_VERSION, at: '' },
    usage: { dailyUsd: 0.5, callsToday: 4 },
    last: { skip: { reason: 'secure_input', trigger: 'hotkey', at: 1 } },
  }
  const setConsent = vi.fn(() => ({}) as never)
  const setSwitch = vi.fn(() => ({ state: {} as never, needsConsent: false }))
  return { aw: { getAwarenessState: () => st as never, setConsent, setSwitch }, setConsent, setSwitch, st }
}

describe('consent card state', () => {
  it('is unavailable (and carries no consent) when the module is missing or its flag is off', () => {
    expect(cardState(null, true)).toMatchObject({ available: false, agreed: false, trigger: false, periodic: false })
    expect(cardState(fake().aw, false)).toMatchObject({ available: false, agreed: false })
  })

  it('shows the module text, whether the CURRENT text was agreed, the switches, the count today and the last skip', () => {
    const f = fake({ recorded: CONSENT_VERSION, trigger: true })
    expect(cardState(f.aw, true)).toEqual({ available: true, consentText: 'the text the worker reads', consentShort: CONSENT_SHORT, agreed: true, enabled: true, trigger: true, periodic: false, strict: true, intervalSec: 30, dailyUsd: 0.5, callsToday: 4, lastSkip: 'secure_input' })
    expect(cardState(fake({ recorded: 0, trigger: true }).aw, true).agreed).toBe(false) // consent for an older text is not agreement
  })
})

describe('consent card write', () => {
  it('agreeing calls setConsent with exactly the choice; periodic cannot be on without triggered glances', () => {
    const f = fake()
    applyChoice(f.aw, { trigger: true, periodic: true, strict: false }, true)
    expect(f.setConsent).toHaveBeenCalledWith({ trigger: true, periodic: true, strict: false })
    f.setConsent.mockClear()
    applyChoice(f.aw, { trigger: false, periodic: true }, true)
    expect(f.setConsent).toHaveBeenCalledWith({ trigger: false, periodic: false })
    f.setConsent.mockClear()
    applyChoice(f.aw, { trigger: true }, true)
    expect(f.setConsent).toHaveBeenCalledWith({ trigger: true, periodic: false })
  })

  it('refuses anything that is not exactly the choice shape, and does nothing with the flag off', () => {
    const f = fake()
    for (const bad of [null, 'yes', {}, { trigger: 'true' }, { trigger: true, dailyUsd: 100 }, { trigger: true, intervalSec: 1 }, { trigger: true, extra: 1 }, [true]]) applyChoice(f.aw, bad, true)
    applyChoice(f.aw, { trigger: true }, false)
    expect(f.setConsent).not.toHaveBeenCalled()
    expect(AwarenessChoiceSchema.safeParse({ trigger: true, periodic: false, strict: true }).success).toBe(true)
  })
})

describe('tray adapter', () => {
  it('reads the module state and writes through its switches', () => {
    const f = fake({ recorded: CONSENT_VERSION, trigger: true, periodic: false })
    const t = trayAwareness(f.aw)
    expect(t.view()).toEqual({ enabled: true, onTrigger: true, periodic: false, calls: 4, lastSkip: 'secure_input' })
    expect(t.setSwitch('periodic', true)).toEqual({ needsConsent: false })
    expect(f.setSwitch).toHaveBeenCalledWith('periodic', true)
  })
})
