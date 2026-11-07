import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { DEFAULT_LIVE_SETTINGS, LIVE_CONSENT_VERSION } from '../live/settings'
import { DEFAULT_WAKE_SETTINGS, NOT_NOW_SCREEN_MS, NOT_NOW_VOICE_MS, WakeSettingsStore, coerceWakeSettings, consentOutcome, consentStep } from './settings'

const consented = { liveEnabled: true, liveConsentVersion: LIVE_CONSENT_VERSION, liveFrames: false }
const NOW = Date.UTC(2026, 10, 8, 9, 0, 0)

describe('wake settings', () => {
  it('listening is ON by default (D52) and the chime too; nothing is decided yet', () => {
    expect(DEFAULT_WAKE_SETTINGS).toEqual({ wakeListen: true, wakeChime: true, voiceAnswer: 'unset', voiceAskAfterMs: 0, screenAnswer: 'unset', screenAskAfterMs: 0 })
    expect(new WakeSettingsStore(null).get().wakeListen).toBe(true)
  })
  it('keeps what is valid and drops what is not, key by key', () => {
    expect(coerceWakeSettings({ wakeListen: false, wakeChime: 'loud', voiceAnswer: 'maybe', screenAnswer: 'never' })).toMatchObject({ wakeListen: false, wakeChime: true, voiceAnswer: 'unset', screenAnswer: 'never' })
    expect(coerceWakeSettings(null)).toEqual(DEFAULT_WAKE_SETTINGS)
    expect(coerceWakeSettings('x')).toEqual(DEFAULT_WAKE_SETTINGS)
  })
  it('persists to wake.json (mode 0600) and reloads', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wake-set-'))
    const a = new WakeSettingsStore(dir)
    a.patch({ wakeListen: false, screenAnswer: 'never' }, { trusted: true })
    const file = path.join(dir, 'wake.json')
    expect(fs.statSync(file).mode & 0o777).toBe(0o600)
    expect(new WakeSettingsStore(dir).get()).toMatchObject({ wakeListen: false, screenAnswer: 'never' })
    fs.rmSync(dir, { recursive: true })
  })
  it('an untrusted source may turn listening down but never up, and cannot touch the consent answers', () => {
    const s = new WakeSettingsStore(null)
    s.patch({ wakeListen: false })
    expect(s.get().wakeListen).toBe(false)
    s.patch({ wakeListen: true })
    expect(s.get().wakeListen).toBe(false)
    s.patch({ voiceAnswer: 'yes', screenAnswer: 'yes' })
    expect(s.get()).toMatchObject({ voiceAnswer: 'unset', screenAnswer: 'unset' })
    s.patch({ wakeListen: true }, { trusted: true })
    expect(s.get().wakeListen).toBe(true)
  })
  it('tells listeners what changed', () => {
    const s = new WakeSettingsStore(null)
    const seen: unknown[] = []
    const off = s.onChange((_s, p) => void seen.push(p))
    s.patch({ wakeChime: false })
    off()
    s.patch({ wakeChime: true }, { trusted: true })
    expect(seen).toEqual([{ wakeChime: false }])
  })
})

describe('the first-wake consent steps', () => {
  const unset = DEFAULT_WAKE_SETTINGS
  it('asks the voice question first, then the screen question, then goes', () => {
    expect(consentStep(unset, DEFAULT_LIVE_SETTINGS, NOW)).toEqual({ step: 'ask', card: 'voice' })
    expect(consentStep(unset, consented, NOW)).toEqual({ step: 'ask', card: 'screen' })
    expect(consentStep({ ...unset, screenAnswer: 'yes' }, { ...consented, liveFrames: true }, NOW)).toEqual({ step: 'go' })
  })
  it('remembers the answers: never is never asked again, not now waits (a day for voice, a week for the screen)', () => {
    expect(consentStep({ ...unset, voiceAnswer: 'never' }, DEFAULT_LIVE_SETTINGS, NOW)).toEqual({ step: 'refused', reason: 'voice_never' })
    expect(consentStep({ ...unset, voiceAnswer: 'not_now', voiceAskAfterMs: NOW + 1 }, DEFAULT_LIVE_SETTINGS, NOW)).toEqual({ step: 'refused', reason: 'voice_not_now' })
    expect(consentStep({ ...unset, voiceAnswer: 'not_now', voiceAskAfterMs: NOW }, DEFAULT_LIVE_SETTINGS, NOW)).toEqual({ step: 'ask', card: 'voice' })
    expect(consentStep({ ...unset, screenAnswer: 'never' }, consented, NOW)).toEqual({ step: 'go' })
    expect(consentStep({ ...unset, screenAnswer: 'not_now', screenAskAfterMs: NOW + 5 }, consented, NOW)).toEqual({ step: 'go' })
    expect(consentStep({ ...unset, screenAnswer: 'not_now', screenAskAfterMs: NOW }, consented, NOW)).toEqual({ step: 'ask', card: 'screen' })
  })
  it('a Live consent from an older text does not count', () => {
    expect(consentStep(unset, { liveEnabled: true, liveConsentVersion: 0, liveFrames: false }, NOW)).toEqual({ step: 'ask', card: 'voice' })
  })
  it('turns each answer into the right patches', () => {
    const now = new Date(NOW)
    expect(consentOutcome('voice', 'yes', false, now)).toMatchObject({ wake: { voiceAnswer: 'yes' }, live: { liveEnabled: true, liveFrames: false, liveConsentVersion: LIVE_CONSENT_VERSION } })
    expect(consentOutcome('voice', 'never', false, now)).toEqual({ wake: { voiceAnswer: 'never', wakeListen: false }, live: {} })
    expect(consentOutcome('voice', 'not_now', false, now)).toEqual({ wake: { voiceAnswer: 'not_now', voiceAskAfterMs: NOW + NOT_NOW_VOICE_MS }, live: {} })
    expect(consentOutcome('screen', 'yes', false, now)).toEqual({ wake: { screenAnswer: 'yes' }, live: { liveFrames: true } })
    expect(consentOutcome('screen', 'never', true, now)).toEqual({ wake: { screenAnswer: 'never' }, live: { liveFrames: false } })
    expect(consentOutcome('screen', 'not_now', false, now)).toEqual({ wake: { screenAnswer: 'not_now', screenAskAfterMs: NOW + NOT_NOW_SCREEN_MS }, live: {} })
  })
})
