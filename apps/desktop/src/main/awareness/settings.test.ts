import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { AwarenessSettingsStore, CONSENT_TEXT, CONSENT_VERSION, DEFAULT_AWARENESS_SETTINGS, coerceAwarenessSettings, consentFor, consentPatch, normaliseDenylist } from './settings'
import { awarenessFlagOn } from './flags'

describe('defaults: everything off', () => {
  it('the layer, both consents and the consent record are off; strict is on; the periodic interval is 30 s', () => {
    expect(DEFAULT_AWARENESS_SETTINGS).toMatchObject({
      awarenessEnabled: false,
      glanceOnTrigger: false,
      glancePeriodic: false,
      glanceIntervalSec: 30,
      glanceStrict: true,
      glanceDenylist: [],
      glanceConsentVersion: 0,
      glanceMaxPerHour: 60,
    })
    expect(DEFAULT_AWARENESS_SETTINGS.glanceDailyUsd).toBeGreaterThan(0)
    expect(consentFor(DEFAULT_AWARENESS_SETTINGS, 'trigger')).toBe(false)
  })

  it('the flag is off unless UNDERSTUDY_X_AWARENESS or UNDERSTUDY_X is set, even under a test runner', () => {
    expect(awarenessFlagOn({})).toBe(false)
    expect(awarenessFlagOn({ VITEST: 'true' })).toBe(false)
    expect(awarenessFlagOn({ UNDERSTUDY_X_AWARENESS: '1' })).toBe(true)
    expect(awarenessFlagOn({ UNDERSTUDY_X: 'true' })).toBe(true)
    expect(awarenessFlagOn({ UNDERSTUDY_X_AWARENESS: '0' })).toBe(false)
    expect(awarenessFlagOn({ UNDERSTUDY_X: '' })).toBe(false)
  })
})

describe('consent', () => {
  it('a consent switch counts only with a record for the current consent text', () => {
    const s = { ...DEFAULT_AWARENESS_SETTINGS, glanceOnTrigger: true, glancePeriodic: true }
    expect(consentFor(s, 'trigger')).toBe(false)
    expect(consentFor({ ...s, glanceConsentVersion: CONSENT_VERSION }, 'trigger')).toBe(true)
    expect(consentFor({ ...s, glanceConsentVersion: CONSENT_VERSION }, 'periodic')).toBe(true)
    expect(consentFor({ ...s, glanceConsentVersion: CONSENT_VERSION - 1 }, 'trigger')).toBe(false)
  })

  it('consentPatch records the version and time; periodic is separate; withdrawing clears everything', () => {
    const at = new Date('2026-11-07T18:00:00.000Z')
    expect(consentPatch({ trigger: true }, at)).toMatchObject({ awarenessEnabled: true, glanceOnTrigger: true, glancePeriodic: false, glanceConsentVersion: CONSENT_VERSION, glanceConsentAt: at.toISOString() })
    expect(consentPatch({ trigger: true, periodic: true, intervalSec: 5 }, at)).toMatchObject({ glancePeriodic: true, glanceIntervalSec: 15 })
    expect(consentPatch({ trigger: false }, at)).toEqual({ glanceOnTrigger: false, glancePeriodic: false, glanceConsentVersion: 0, glanceConsentAt: '' })
  })

  it('the consent text is one short, plain paragraph that says what is sent, skipped, kept, where to look and how to stop', () => {
    expect(CONSENT_TEXT.includes('\n')).toBe(false)
    expect(CONSENT_TEXT.length).toBeLessThan(1400)
    for (const word of [/picture/i, /memory/i, /never saved/i, /password manager/i, /locked or shared/i, /Privacy/, /pause/i, /strict mode/i]) expect(CONSENT_TEXT).toMatch(word)
  })
})

describe('the store', () => {
  it('an untrusted source can pause and turn things down, never up', () => {
    const store = new AwarenessSettingsStore(null, () => 1_000)
    store.patch({ awarenessEnabled: true, glanceOnTrigger: true, glancePeriodic: true, glanceConsentVersion: CONSENT_VERSION })
    expect(store.get()).toMatchObject({ awarenessEnabled: false, glanceOnTrigger: false, glanceConsentVersion: 0 })
    store.patch({ glanceStrict: false, glanceDailyUsd: 50, glanceMaxPerHour: 600, glanceIntervalSec: 15, glanceDenylist: [] })
    expect(store.get()).toMatchObject({ glanceStrict: true, glanceMaxPerHour: 60, glanceIntervalSec: 30 })
    store.patch({ glancePausedUntilMs: 5000 })
    expect(store.get().glancePausedUntilMs).toBe(5000)
  })

  it('the trusted path (the consent card) can turn things up; an untrusted patch can still turn them down', () => {
    const store = new AwarenessSettingsStore(null)
    store.patch(consentPatch({ trigger: true, periodic: true }), { trusted: true })
    expect(consentFor(store.get(), 'trigger')).toBe(true)
    expect(consentFor(store.get(), 'periodic')).toBe(true)
    store.patch({ glancePeriodic: false })
    expect(consentFor(store.get(), 'periodic')).toBe(false)
    store.patch({ awarenessEnabled: false })
    expect(store.get().awarenessEnabled).toBe(false)
  })

  it('an untrusted denylist patch may add apps but never remove one', () => {
    const store = new AwarenessSettingsStore(null)
    store.patch({ glanceDenylist: ['com.example.a'] }, { trusted: true })
    store.patch({ glanceDenylist: ['com.example.a', 'com.example.b'] })
    expect(store.get().glanceDenylist).toEqual(['com.example.a', 'com.example.b'])
    store.patch({ glanceDenylist: ['com.example.b'] })
    expect(store.get().glanceDenylist).toEqual(['com.example.a', 'com.example.b'])
    store.patch({ glanceDenylist: ['com.example.b'] }, { trusted: true })
    expect(store.get().glanceDenylist).toEqual(['com.example.b'])
  })

  it('pause for an hour and resume', () => {
    let now = 10_000
    const store = new AwarenessSettingsStore(null, () => now)
    store.pauseFor()
    expect(store.get().glancePausedUntilMs).toBe(10_000 + 3_600_000)
    store.resume()
    expect(store.get().glancePausedUntilMs).toBe(0)
  })

  it('invalid values are dropped key by key; listeners hear accepted patches', () => {
    const store = new AwarenessSettingsStore(null)
    const heard: string[][] = []
    store.onChange((_s, p) => heard.push(Object.keys(p)))
    store.patch({ glanceIntervalSec: 3, glanceDailyUsd: -4, glanceDenylist: ['has space'], bogus: 1 }, { trusted: true })
    expect(store.get()).toMatchObject({ glanceIntervalSec: 30 })
    expect(heard).toEqual([])
    store.patch({ glanceIntervalSec: 45, glanceDailyUsd: 2 }, { trusted: true })
    expect(heard).toEqual([['glanceIntervalSec', 'glanceDailyUsd']])
  })

  it('persists to awareness.json in the given directory and reads it back, ignoring junk keys', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'awareness-settings-'))
    try {
      const a = new AwarenessSettingsStore(dir)
      a.patch(consentPatch({ trigger: true, strict: false }), { trusted: true })
      const b = new AwarenessSettingsStore(dir)
      expect(b.get()).toMatchObject({ awarenessEnabled: true, glanceOnTrigger: true, glanceStrict: false, glanceConsentVersion: CONSENT_VERSION })
      fs.writeFileSync(path.join(dir, 'awareness.json'), '{ not json')
      expect(new AwarenessSettingsStore(dir).get()).toEqual(DEFAULT_AWARENESS_SETTINGS)
    } finally {
      fs.rmSync(dir, { recursive: true, force: true })
    }
  })

  it('coerce keeps valid keys and normalises the denylist', () => {
    expect(coerceAwarenessSettings({ glanceStrict: false, glanceIntervalSec: 'x', glanceDenylist: ['COM.Acme.*', 'com.acme.*', 'bad id'] })).toMatchObject({ glanceStrict: false, glanceIntervalSec: 30, glanceDenylist: ['com.acme.*'] })
    expect(coerceAwarenessSettings(null)).toEqual(DEFAULT_AWARENESS_SETTINGS)
    expect(normaliseDenylist([' Com.Foo.Bar ', 'com.foo.bar', 'x'])).toEqual(['com.foo.bar'])
  })
})
